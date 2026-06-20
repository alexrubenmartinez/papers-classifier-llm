"""Fase 1 — Sube los 2000 PDFs de Articulos/ a MinIO bucket Bronze.

Genera:
- s3://examen-parcial-bronze-g3/papers/PAPER_NNNN.pdf
- s3://examen-parcial-bronze-g3/index.parquet      (manifest interno)
- s3://examen-parcial-bronze-g3/bronze_control.xlsx (ítem 3 rúbrica)
- examen/classifier/outputs/bronze_control.xlsx    (copia local)

Convenciones:
- Renombra a PAPER_0001..PAPER_2000 preservando el orden lexicográfico del filename original.
- Parsea arxiv-id y topic-tag del nombre original (formato NNNN_topic_id_title.pdf).
- Calcula SHA256 + MD5 en stream y verifica el etag de MinIO (single-part = MD5).
- Reanudable: si el objeto ya existe con MD5 que coincide, salta.
- Paralelo: ThreadPoolExecutor (upload es I/O-bound).
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
from botocore.exceptions import ClientError
from rich.console import Console
from rich.progress import (
    BarColumn, MofNCompleteColumn, Progress, SpinnerColumn,
    TextColumn, TimeElapsedColumn, TimeRemainingColumn,
)
from rich.table import Table

# Imports relativos al paquete (cuando se llama via -m classifier.src.upload_bronze)
try:
    from classifier.src.config import (
        ARTICULOS_DIR, BUCKET, GROUP_PREFIX,
        KEY_BRONZE_INDEX, KEY_BRONZE_CONTROL_XLSX, KEY_BRONZE_PAPERS_PREFIX,
        OUTPUTS, UPLOAD_WORKERS,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from classifier.src.config import (
        ARTICULOS_DIR, BUCKET, GROUP_PREFIX,
        KEY_BRONZE_INDEX, KEY_BRONZE_CONTROL_XLSX, KEY_BRONZE_PAPERS_PREFIX,
        OUTPUTS, UPLOAD_WORKERS,
    )

# Reusa el cliente boto3 del entorno previo
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # examen/
from classifier.src._minio_client import minio  # noqa: E402

console = Console()


# ───────────────────────────────────────────────────────────────────── #
# Parser del nombre: NNNN_topic-tag_arxiv-id_Title.pdf                  #
# ───────────────────────────────────────────────────────────────────── #
RE_FILENAME_MODERN = re.compile(
    r"^(?P<seq>\d{4})_(?P<topic>[a-z0-9-]+)_(?P<arxiv>\d{4}\.\d{4,5})_(?P<title>.+)\.pdf$",
    re.IGNORECASE,
)
RE_FILENAME_LEGACY = re.compile(
    r"^(?P<seq>\d{4})_(?P<topic>[a-z0-9-]+)_(?P<arxiv>[a-z-]+/\d{7})_(?P<title>.+)\.pdf$",
    re.IGNORECASE,
)


def parse_filename(name: str) -> dict:
    """Extrae seq, topic, arxiv_id, title, year."""
    out = {
        "seq_original": None, "topic_tag_local": None,
        "arxiv_id": None, "title_from_filename": None,
        "year_from_arxiv": None,
    }
    m = RE_FILENAME_MODERN.match(name) or RE_FILENAME_LEGACY.match(name)
    if not m:
        return out
    out["seq_original"] = int(m["seq"])
    out["topic_tag_local"] = m["topic"].lower()
    out["arxiv_id"] = m["arxiv"]
    out["title_from_filename"] = m["title"].replace("_", " ").strip()

    # Año: arxiv moderno (YYMM.NNNNN) → 20YY (válido 91-26, asumimos siglo correcto)
    if "." in m["arxiv"]:
        yymm = m["arxiv"].split(".")[0]
        yy = int(yymm[:2])
        # YY 91-99 → 19YY, 00-30 → 20YY
        out["year_from_arxiv"] = 2000 + yy if yy <= 30 else 1900 + yy
    return out


# ───────────────────────────────────────────────────────────────────── #
# Buckets — crear si no existen                                        #
# ───────────────────────────────────────────────────────────────────── #
def ensure_bucket(s3) -> bool:
    """Crea el bucket único si falta. True si fue creado, False si ya existía."""
    existing = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
    if BUCKET in existing:
        return False
    s3.create_bucket(Bucket=BUCKET)
    return True


# ───────────────────────────────────────────────────────────────────── #
# Hashing stream                                                       #
# ───────────────────────────────────────────────────────────────────── #
def hash_file(path: Path, bufsize: int = 1024 * 1024) -> tuple[str, str, int]:
    """Calcula MD5 + SHA256 + tamaño en una sola pasada."""
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while chunk := f.read(bufsize):
            md5.update(chunk)
            sha.update(chunk)
            size += len(chunk)
    return md5.hexdigest(), sha.hexdigest(), size


# ───────────────────────────────────────────────────────────────────── #
# Upload de un solo PDF                                                #
# ───────────────────────────────────────────────────────────────────── #
@dataclass
class UploadResult:
    code: str
    original_filename: str
    key: str
    arxiv_id: str | None
    topic_tag_local: str | None
    title_from_filename: str | None
    year_from_arxiv: int | None
    size_bytes: int
    md5: str
    sha256: str
    etag: str
    etag_ok: bool
    skipped: bool
    error: str | None
    uploaded_at: str


def upload_one(pdf_path: Path, code: str, s3, resume: bool = True) -> UploadResult:
    key = f"{KEY_BRONZE_PAPERS_PREFIX}{code}.pdf"
    parsed = parse_filename(pdf_path.name)

    try:
        md5, sha256, size = hash_file(pdf_path)
    except Exception as e:
        return UploadResult(
            code=code, original_filename=pdf_path.name, key=key,
            arxiv_id=parsed["arxiv_id"], topic_tag_local=parsed["topic_tag_local"],
            title_from_filename=parsed["title_from_filename"],
            year_from_arxiv=parsed["year_from_arxiv"],
            size_bytes=0, md5="", sha256="", etag="", etag_ok=False,
            skipped=False, error=f"hash_failed: {e}",
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )

    # Resume — si ya está en MinIO con etag == md5, no resubir
    if resume:
        try:
            head = s3.head_object(Bucket=BUCKET, Key=key)
            remote_etag = head["ETag"].strip('"')
            if remote_etag.lower() == md5.lower():
                return UploadResult(
                    code=code, original_filename=pdf_path.name, key=key,
                    arxiv_id=parsed["arxiv_id"], topic_tag_local=parsed["topic_tag_local"],
                    title_from_filename=parsed["title_from_filename"],
                    year_from_arxiv=parsed["year_from_arxiv"],
                    size_bytes=size, md5=md5, sha256=sha256, etag=remote_etag,
                    etag_ok=True, skipped=True, error=None,
                    uploaded_at=head["LastModified"].isoformat(),
                )
        except ClientError as e:
            if e.response["Error"]["Code"] not in {"404", "NoSuchKey", "NotFound"}:
                raise

    # Sube
    try:
        s3.upload_file(
            str(pdf_path), BUCKET, key,
            ExtraArgs={
                "ContentType": "application/pdf",
                "Metadata": {
                    "code": code,
                    "original-name": pdf_path.name[:1023],
                    "arxiv-id": parsed["arxiv_id"] or "",
                    "topic-tag-local": parsed["topic_tag_local"] or "",
                    "sha256": sha256,
                },
            },
        )
        head = s3.head_object(Bucket=BUCKET, Key=key)
        etag = head["ETag"].strip('"')
        return UploadResult(
            code=code, original_filename=pdf_path.name, key=key,
            arxiv_id=parsed["arxiv_id"], topic_tag_local=parsed["topic_tag_local"],
            title_from_filename=parsed["title_from_filename"],
            year_from_arxiv=parsed["year_from_arxiv"],
            size_bytes=size, md5=md5, sha256=sha256, etag=etag,
            etag_ok=etag.lower() == md5.lower(),
            skipped=False, error=None,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        return UploadResult(
            code=code, original_filename=pdf_path.name, key=key,
            arxiv_id=parsed["arxiv_id"], topic_tag_local=parsed["topic_tag_local"],
            title_from_filename=parsed["title_from_filename"],
            year_from_arxiv=parsed["year_from_arxiv"],
            size_bytes=size, md5=md5, sha256=sha256, etag="", etag_ok=False,
            skipped=False, error=f"upload_failed: {e}",
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )


# ───────────────────────────────────────────────────────────────────── #
# Driver principal                                                     #
# ───────────────────────────────────────────────────────────────────── #
def collect_pdfs(src: Path) -> list[Path]:
    """Devuelve los PDFs ordenados por su seq numérico (los 4 primeros dígitos)."""
    pdfs = sorted(p for p in src.rglob("*.pdf") if p.is_file())
    return pdfs


def assign_codes(pdfs: list[Path]) -> list[tuple[Path, str]]:
    """Asigna PAPER_NNNN con NNNN de 4 dígitos, 1-based."""
    width = max(4, len(str(len(pdfs))))
    return [(p, f"PAPER_{i:0{width}d}") for i, p in enumerate(pdfs, start=1)]


def run(limit: int | None = None, workers: int = UPLOAD_WORKERS, resume: bool = True) -> int:
    if not ARTICULOS_DIR.exists():
        console.print(f"[red]✗ No existe la carpeta {ARTICULOS_DIR}[/red]")
        return 2

    console.rule("[bold]Fase 1 — Bronze upload[/bold]")
    console.print(f"Source : [cyan]{ARTICULOS_DIR}[/cyan]")
    console.print(f"Bucket : [cyan]s3://{BUCKET}/{KEY_BRONZE_PAPERS_PREFIX}[/cyan]")

    pdfs = collect_pdfs(ARTICULOS_DIR)
    console.print(f"PDFs en disco: [bold]{len(pdfs)}[/bold]")
    if limit:
        pdfs = pdfs[:limit]
        console.print(f"[yellow]--limit={limit}: subiendo solo los primeros {limit}[/yellow]")

    if not pdfs:
        console.print("[red]✗ No hay PDFs para subir[/red]")
        return 2

    s3 = minio()
    created = ensure_bucket(s3)
    if created:
        console.print(f"[green]✓ Bucket creado:[/green] {BUCKET}")
    else:
        console.print(f"[dim]Bucket {BUCKET} ya existía — OK[/dim]")

    coded = assign_codes(pdfs)

    results: list[UploadResult] = []
    started = time.perf_counter()

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]Uploading[/bold]"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("upload", total=len(coded))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(upload_one, p, code, s3, resume): (p, code) for p, code in coded}
            for fut in as_completed(futures):
                results.append(fut.result())
                progress.advance(task)

    elapsed = time.perf_counter() - started
    # Resumen
    ok = sum(1 for r in results if r.error is None)
    skipped = sum(1 for r in results if r.skipped)
    failed = sum(1 for r in results if r.error)
    bad_etag = sum(1 for r in results if not r.etag_ok and not r.error)
    total_bytes = sum(r.size_bytes for r in results)
    mb = total_bytes / (1024 * 1024)

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Métrica"); table.add_column("Valor", justify="right")
    table.add_row("Total procesados", str(len(results)))
    table.add_row("OK", f"[green]{ok}[/green]")
    table.add_row("Saltados (resume)", f"[yellow]{skipped}[/yellow]")
    table.add_row("Fallidos", f"[red]{failed}[/red]" if failed else "0")
    table.add_row("Etag mismatch", f"[red]{bad_etag}[/red]" if bad_etag else "0")
    table.add_row("Tamaño total", f"{mb:,.1f} MB")
    table.add_row("Wall-time", f"{elapsed:.1f} s")
    table.add_row("Throughput", f"{mb/max(elapsed,0.001):.1f} MB/s")
    console.print(table)

    if failed:
        console.print("\n[red]Primeros 5 errores:[/red]")
        for r in [x for x in results if x.error][:5]:
            console.print(f"  {r.code} — {r.error}")

    # Manifest → index.parquet en MinIO + bronze_control.xlsx (en MinIO y local)
    rows = [asdict(r) for r in sorted(results, key=lambda r: r.code)]
    df = pl.DataFrame(rows)

    index_local = OUTPUTS / "bronze_index.parquet"
    df.write_parquet(index_local)
    s3.upload_file(str(index_local), BUCKET, KEY_BRONZE_INDEX,
                   ExtraArgs={"ContentType": "application/octet-stream"})

    xlsx_local = OUTPUTS / "bronze_control.xlsx"
    df.write_excel(str(xlsx_local), worksheet="bronze_control", autofit=True)
    s3.upload_file(str(xlsx_local), BUCKET, KEY_BRONZE_CONTROL_XLSX,
                   ExtraArgs={"ContentType":
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})

    console.print(f"\n[green]✓ manifiesto[/green] → s3://{BUCKET}/{KEY_BRONZE_INDEX}")
    console.print(f"[green]✓ control xlsx[/green] → s3://{BUCKET}/{KEY_BRONZE_CONTROL_XLSX}")
    console.print(f"[green]✓ control xlsx local[/green] → {xlsx_local}")

    return 0 if failed == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="subir solo los primeros N (debug)")
    ap.add_argument("--workers", type=int, default=UPLOAD_WORKERS)
    ap.add_argument("--no-resume", action="store_true", help="resubir incluso si etag coincide")
    args = ap.parse_args()
    raise SystemExit(run(limit=args.limit, workers=args.workers, resume=not args.no_resume))


if __name__ == "__main__":
    main()
