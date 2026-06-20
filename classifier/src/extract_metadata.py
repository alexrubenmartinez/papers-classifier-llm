"""Fase 2 — Extrae metadata de los PDFs del bucket Bronze.

Para cada paper:
- Descarga el PDF en memoria desde MinIO (stream, sin tempfile).
- Usa PyMuPDF para leer las primeras páginas (early-exit cuando halla abstract).
- Detecta título por tamaño de fuente (heurística robusta).
- Detecta abstract con regex multi-idioma (en/es).
- Detecta keywords con regex y fallback a YAKE.
- Detecta año con 3 señales: arxiv-id (del Bronze), regex sobre página 1, metadata XMP.
- Detecta idioma con langdetect.

Paraleliza con ProcessPoolExecutor — cada worker mantiene su propio cliente boto3
y libera el GIL para que PyMuPDF aproveche todos los cores.

Persiste a s3://examen-parcial/{group}/silver/metadata.parquet.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import polars as pl
from rich.console import Console
from rich.progress import (
    BarColumn, MofNCompleteColumn, Progress, SpinnerColumn,
    TextColumn, TimeElapsedColumn, TimeRemainingColumn,
)
from rich.table import Table

try:
    from classifier.src.config import (
        BUCKET, KEY_BRONZE_INDEX, KEY_SILVER_METADATA,
        OUTPUTS, PDF_BODY_MAX_PAGES, YEAR_MIN, YEAR_MAX,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from classifier.src.config import (
        BUCKET, KEY_BRONZE_INDEX, KEY_SILVER_METADATA,
        OUTPUTS, PDF_BODY_MAX_PAGES, YEAR_MIN, YEAR_MAX,
    )

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # examen/
from classifier.src._minio_client import minio  # noqa: E402

console = Console()


# ─────────────────────────────────────────────────────────────── #
# Extractores                                                    #
# ─────────────────────────────────────────────────────────────── #
RE_ABSTRACT = re.compile(
    r"(?is)\babstract\b\s*[:\-—.]?\s*(.{120,4000}?)(?=\n\s*(?:keywords?|kw|"
    r"index\s+terms?|categories\s+and\s+subject|1\.?\s*introduction|"
    r"i\.?\s*introduction|introduction|resumen|índice)\b|\n\s*\n\s*\n|$)"
)
RE_ABSTRACT_ES = re.compile(
    r"(?is)\bresumen\b\s*[:\-—.]?\s*(.{120,4000}?)(?=\n\s*(?:palabras?\s+clave|"
    r"1\.?\s*introducción|introducción|abstract)\b|\n\s*\n\s*\n|$)"
)
RE_KEYWORDS = re.compile(
    r"(?is)\b(?:keywords?|key\s*words|index\s+terms?|palabras?\s+clave)\b\s*[:\-—.]?\s*"
    r"(.{5,800}?)(?=\n\s*\n|\n\s*(?:1\.?\s*introduction|i\.?\s*introduction|"
    r"introduction|introducción|abstract|resumen|categories)\b|$)"
)
RE_YEAR = re.compile(r"\b(19[89]\d|20[0-2]\d)\b")

# Early-exit threshold: si la pág 1 ya tiene >= este largo de abstract, no se leen más páginas.
ABSTRACT_GOOD_ENOUGH = 200


# ── Validación de título ──────────────────────────────────────── #
# Placeholders típicos de plantillas (LaTeX, Word) que no son títulos reales.
TITLE_BLACKLIST = [
    re.compile(r"^\s*this\s+is\s+(?:a|the|my|your)?\s*(?:sample\s+)?(?:title|paper|template)\s*\.?\s*$", re.IGNORECASE),
    re.compile(r"^\s*title\s+(?:goes\s+)?here\s*$", re.IGNORECASE),
    re.compile(r"^\s*(?:paper|article|document)\s+title\s*$", re.IGNORECASE),
    re.compile(r"^\s*untitled\s*$", re.IGNORECASE),
    re.compile(r"^\s*title\s*$", re.IGNORECASE),
    re.compile(r"^\s*abstract\s*$", re.IGNORECASE),
]

# Tokens de cabecera de revista / running header — versión all-caps (estricta,
# para detectar "INTERNATIONAL JOURNAL OF…" como header solitario).
JOURNAL_HEADER_TOKENS = re.compile(
    r"\b(?:JOURNAL|PROCEEDINGS|TRANSACTIONS|CONFERENCE|SYMPOSIUM|WORKSHOP|"
    r"REVIEW|LETTERS|MAGAZINE|BULLETIN|ANNALS|ACTA|ACM|IEEE|IEEE/ACM|"
    r"SPRINGER|ELSEVIER|VOL\.?|VOLUME|ISSUE|PP\.|PAGES?|ISSN|DOI)\b"
)

# Prefijo de nombre de revista — case-insensitive, captura "Transactions on …",
# "Journal of …", "IEEE Transactions on …", etc. cuando aparecen al INICIO del
# texto extraído como título. Si va seguido de un separador (underscores, dashes
# o muchos espacios), el título real está después del separador.
JOURNAL_NAME_PREFIX = re.compile(
    r"^\s*(?:(?:IEEE|ACM|IEEE/ACM|Springer|Elsevier|International)\s+)*"
    r"(?:Journal|Proceedings|Transactions|Conference|Symposium|Workshop|"
    r"Review|Letters|Magazine|Bulletin|Annals|Acta)"
    r"(?:\s+(?:on|of|in|for)\b[^_\-\n]{0,120})?",
    re.IGNORECASE,
)

# Separador típico entre header de revista y título: ≥3 underscores/guiones
# o ≥6 espacios consecutivos.
TITLE_SEPARATOR = re.compile(r"(?:_{3,}|-{4,}|\s{6,})")

# Stamp de arXiv (lo imprime el preprint en el margen izquierdo de la pág. 1):
#   arXiv:2504.20768v2 [cs.DB] 17 Oct 2025
#   arXiv:2512.22305v1 [cs.LG] 26 Dec 2025
#   arXiv:cs/0501123  (legacy)
RE_ARXIV_STAMP = re.compile(
    r"\barXiv\s*:\s*(?:\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+/\d{7})",
    re.IGNORECASE,
)
# Categoría arXiv suelta: [cs.LG], [stat.ML], [cond-mat.dis-nn], etc.
RE_ARXIV_CATEGORY = re.compile(
    r"\[(?:cs|stat|math|physics|astro-ph|cond-mat|gr-qc|hep-[a-z]+|nlin|"
    r"nucl-[a-z]+|quant-ph|q-bio|q-fin|eess|econ)\.[A-Za-z\-]+\]",
    re.IGNORECASE,
)


def strip_journal_header(text: str) -> str:
    """Si el texto empieza con un nombre de revista y hay un separador, devuelve
    la parte después del separador (el título real). Si no, devuelve el texto tal cual."""
    if not text:
        return text
    m = JOURNAL_NAME_PREFIX.match(text)
    if not m:
        return text
    sep = TITLE_SEPARATOR.search(text, m.end())
    if not sep:
        # Empieza con nombre de revista PERO no hay separador → puede ser el
        # header solo (sin título adelante). Lo dejamos para que looks_like_title decida.
        return text
    after = text[sep.end():].strip()
    return after or text


def looks_like_title(text: str | None) -> bool:
    """Heurística de validación: descarta placeholders y running headers."""
    if not text:
        return False
    s = text.strip()
    if len(s) < 8 or len(s) > 500:
        return False
    for pat in TITLE_BLACKLIST:
        if pat.match(s):
            return False
    # Running header all-caps + token de revista (caso "INTERNATIONAL JOURNAL OF").
    letters = [c for c in s if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.85 and JOURNAL_HEADER_TOKENS.search(s):
            return False
    # Running header NO-all-caps tipo "Transactions on Sustainable …" sin separador
    # → es solo el cabezote. Si hubiera separador, strip_journal_header ya lo cortó
    # antes de llegar acá.
    if JOURNAL_NAME_PREFIX.match(s) and not TITLE_SEPARATOR.search(s):
        return False
    # Stamp arXiv (margen izquierdo de la primera página del preprint).
    # Aparece como "arXiv:2504.20768v2 [cs.DB] 17 Oct 2025" — no es título.
    if RE_ARXIV_STAMP.search(s) or RE_ARXIV_CATEGORY.search(s):
        return False
    # Solo dígitos / símbolos: no es título
    if not any(c.isalpha() for c in s):
        return False
    return True


def extract_title_from_page(page) -> str | None:
    try:
        d = page.get_text("dict")
    except Exception:
        return None
    page_h = page.rect.height
    candidates: list[tuple[float, float, str]] = []
    for blk in d.get("blocks", []):
        if blk.get("type") != 0:
            continue
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                size = float(span.get("size") or 0)
                text = (span.get("text") or "").strip()
                if not text or len(text) < 4 or size < 10:
                    continue
                y_top = blk["bbox"][1]
                if y_top > page_h * 0.55:
                    continue
                # Stamp arXiv vertical / margen: descartarlo aquí evita que se mezcle
                # con el título real cuando comparten tamaño de fuente.
                if RE_ARXIV_STAMP.search(text) or RE_ARXIV_CATEGORY.search(text):
                    continue
                candidates.append((size, y_top, text))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (-c[0], c[1]))
    # Probar tamaños de fuente en orden decreciente — si el más grande es un
    # running header, caemos al siguiente nivel.
    seen_sizes: set[float] = set()
    for size, _, _ in candidates:
        size_key = round(size * 2) / 2
        if size_key in seen_sizes:
            continue
        seen_sizes.add(size_key)
        title_parts = [t for s, _, t in candidates if abs(s - size) < 0.5]
        title = " ".join(title_parts).strip()
        # Antes del collapse de whitespace probamos a cortar por separador (los
        # `___` o múltiples espacios desaparecen al colapsar).
        title = strip_journal_header(title)
        title = re.sub(r"\s+", " ", title).strip()
        if looks_like_title(title):
            return title[:500]
    return None


def extract_abstract(full_text: str) -> str | None:
    for pat in (RE_ABSTRACT, RE_ABSTRACT_ES):
        m = pat.search(full_text)
        if m:
            abstract = re.sub(r"\s+", " ", m.group(1)).strip()
            if 80 <= len(abstract) <= 4000:
                return abstract
    return None


def extract_keywords(full_text: str) -> list[str]:
    m = RE_KEYWORDS.search(full_text)
    if not m:
        return []
    raw = m.group(1)
    parts = re.split(r"[,;·•·\n]|\s—\s|\s-\s|\s·\s", raw)
    out = []
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip(" .:-——")
        if 2 <= len(p) <= 80:
            out.append(p)
        if len(out) >= 15:
            break
    return out


def yake_keywords(text: str, top_k: int = 8) -> list[str]:
    try:
        import yake
        kw_extractor = yake.KeywordExtractor(lan="en", n=2, top=top_k, dedupLim=0.85)
        return [kw for kw, _ in kw_extractor.extract_keywords(text)]
    except Exception:
        return []


def extract_year(first_page_text: str, xmp_meta: dict, year_from_arxiv: int | None) -> tuple[int | None, str]:
    votes: list[int] = []
    if year_from_arxiv:
        votes.append(year_from_arxiv)
    cd = xmp_meta.get("creationDate") or ""
    m = re.search(r"D:(\d{4})", cd)
    if m:
        votes.append(int(m.group(1)))
    for y_str in RE_YEAR.findall(first_page_text):
        votes.append(int(y_str))
    valid = [y for y in votes if 1990 <= y <= YEAR_MAX]
    if not valid:
        return None, "none"
    from collections import Counter
    counter = Counter(valid)
    year, count = counter.most_common(1)[0]
    if year_from_arxiv and year == year_from_arxiv and count >= 1:
        return year, "high"
    if count >= 2:
        return year, "medium"
    return year, "low"


def detect_language(text: str) -> str | None:
    if not text or len(text) < 50:
        return None
    try:
        from langdetect import detect, DetectorFactory
        DetectorFactory.seed = 0
        return detect(text[:2000])
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────── #
# Worker                                                         #
# ─────────────────────────────────────────────────────────────── #
@dataclass
class ExtractResult:
    code: str
    title_extracted: str | None
    abstract: str | None
    keywords_extracted: list[str]
    keywords_yake: list[str]
    language: str | None
    year_extracted: int | None
    year_confidence: str
    n_pages: int
    chars_first_pages: int
    pages_read: int          # cuántas páginas se leyeron realmente (early-exit)
    error: str | None


def extract_one(code: str, key: str, year_from_arxiv: int | None, s3) -> ExtractResult:
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        pdf_bytes = obj["Body"].read()
    except Exception as e:
        return ExtractResult(
            code=code, title_extracted=None, abstract=None,
            keywords_extracted=[], keywords_yake=[], language=None,
            year_extracted=None, year_confidence="none",
            n_pages=0, chars_first_pages=0, pages_read=0,
            error=f"s3_get: {e}",
        )

    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        n_pages = len(doc)

        # ── Página 1 siempre — para título + primer pase de abstract ──
        try:
            page1_text = doc[0].get_text() if n_pages else ""
        except Exception:
            page1_text = ""
        pages_text = [page1_text]
        title = extract_title_from_page(doc[0]) if n_pages else None

        full = page1_text
        abstract = extract_abstract(full)
        keywords = extract_keywords(full)

        # ── Early-exit: si la pág 1 ya tiene abstract + (keywords o no las buscamos), no leemos más ──
        need_more = (
            (abstract is None or len(abstract) < ABSTRACT_GOOD_ENOUGH)
            or (not keywords and n_pages > 1)
        )
        pages_read = 1

        if need_more:
            for i in range(1, min(PDF_BODY_MAX_PAGES, n_pages)):
                try:
                    pg = doc[i].get_text()
                except Exception:
                    pg = ""
                pages_text.append(pg)
                pages_read += 1
                full = "\n".join(pages_text)
                abstract = abstract or extract_abstract(full)
                keywords = keywords or extract_keywords(full)
                # corte temprano si ya tenemos ambos
                if abstract and (keywords or i == PDF_BODY_MAX_PAGES - 1):
                    break

        # Fallback título XMP si la heurística falló — pasa por strip_journal_header
        # y el mismo validador para no aceptar placeholders ni running headers.
        if not title:
            xmp_title = (doc.metadata or {}).get("title", "")
            xmp_title = strip_journal_header(xmp_title or "")
            xmp_title = re.sub(r"\s+", " ", xmp_title).strip()
            if looks_like_title(xmp_title):
                title = xmp_title

        # YAKE solo si no hay keywords explícitas Y hay abstract
        keywords_yake_top = []
        if not keywords and abstract:
            keywords_yake_top = yake_keywords(abstract, top_k=8)

        year, year_conf = extract_year(page1_text, doc.metadata or {}, year_from_arxiv)
        lang = detect_language(full[:3000])
        doc.close()

        return ExtractResult(
            code=code, title_extracted=title, abstract=abstract,
            keywords_extracted=keywords, keywords_yake=keywords_yake_top,
            language=lang, year_extracted=year, year_confidence=year_conf,
            n_pages=n_pages, chars_first_pages=len(full),
            pages_read=pages_read,
            error=None,
        )
    except Exception as e:
        return ExtractResult(
            code=code, title_extracted=None, abstract=None,
            keywords_extracted=[], keywords_yake=[], language=None,
            year_extracted=None, year_confidence="none",
            n_pages=0, chars_first_pages=0, pages_read=0,
            error=f"parse: {e}",
        )


# ─────────────────────────────────────────────────────────────── #
# ProcessPool — initializer per-worker (cliente boto3 NO es picklable) #
# ─────────────────────────────────────────────────────────────── #
_WORKER_S3 = None


def _init_worker():
    global _WORKER_S3
    from classifier.src._minio_client import minio as _mk
    _WORKER_S3 = _mk()


def _extract_task(args: tuple[str, str, int | None]) -> ExtractResult:
    code, key, year_from_arxiv = args
    return extract_one(code, key, year_from_arxiv, _WORKER_S3)


# ─────────────────────────────────────────────────────────────── #
# Driver                                                         #
# ─────────────────────────────────────────────────────────────── #
def load_bronze_index() -> pl.DataFrame:
    s3 = minio()
    buf = io.BytesIO()
    s3.download_fileobj(BUCKET, KEY_BRONZE_INDEX, buf)
    buf.seek(0)
    return pl.read_parquet(buf)


def run(limit: int | None = None, workers: int | None = None) -> int:
    console.rule("[bold]Fase 2 — Extracción metadata Silver[/bold]")

    bronze = load_bronze_index()
    bronze = bronze.filter(pl.col("error").is_null())
    if limit:
        bronze = bronze.head(limit)
        console.print(f"[yellow]--limit={limit}[/yellow]")
    n = bronze.height
    cpu = os.cpu_count() or 4
    if workers is None:
        workers = cpu
    console.print(f"Papers a procesar: [bold]{n}[/bold]  ·  workers (ProcessPool): [bold]{workers}[/bold]  ·  cores: {cpu}")

    tasks = [(r["code"], r["key"], r["year_from_arxiv"]) for r in bronze.iter_rows(named=True)]

    rows: list[ExtractResult] = []
    started = time.perf_counter()

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]Extracting[/bold]"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("extract", total=n)
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
            for result in ex.map(_extract_task, tasks, chunksize=4):
                rows.append(result)
                progress.advance(task_id)

    elapsed = time.perf_counter() - started

    with_title = sum(1 for r in rows if r.title_extracted)
    with_abstract = sum(1 for r in rows if r.abstract)
    with_keywords = sum(1 for r in rows if r.keywords_extracted)
    with_yake = sum(1 for r in rows if r.keywords_yake)
    with_year = sum(1 for r in rows if r.year_extracted)
    in_range = sum(1 for r in rows if r.year_extracted and YEAR_MIN <= r.year_extracted <= YEAR_MAX)
    errors = sum(1 for r in rows if r.error)
    avg_pages_read = sum(r.pages_read for r in rows) / max(len(rows), 1)

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Métrica"); table.add_column("Valor", justify="right")
    table.add_row("Total", str(len(rows)))
    table.add_row("Con título", f"{with_title} ({with_title*100/max(len(rows),1):.0f}%)")
    table.add_row("Con abstract", f"{with_abstract} ({with_abstract*100/max(len(rows),1):.0f}%)")
    table.add_row("Con keywords explícitas", f"{with_keywords}")
    table.add_row("Con keywords YAKE", f"{with_yake}")
    table.add_row("Con año detectado", f"{with_year}")
    table.add_row(f"En rango {YEAR_MIN}-{YEAR_MAX}", f"{in_range}")
    table.add_row("Páginas/paper (media)", f"{avg_pages_read:.2f}")
    table.add_row("Errores", f"[red]{errors}[/red]" if errors else "0")
    table.add_row("Wall-time", f"{elapsed:.1f} s")
    table.add_row("Throughput", f"{len(rows)/max(elapsed,0.001):.1f} papers/s")
    console.print(table)

    df = pl.DataFrame([asdict(r) for r in rows])
    out_local = OUTPUTS / "silver_metadata.parquet"
    df.write_parquet(out_local)
    s3 = minio()
    s3.upload_file(str(out_local), BUCKET, KEY_SILVER_METADATA,
                   ExtraArgs={"ContentType": "application/octet-stream"})
    console.print(f"\n[green]✓ metadata[/green] → s3://{BUCKET}/{KEY_SILVER_METADATA}")
    console.print(f"[green]✓ local[/green] → {out_local}")

    return 0 if errors == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=None, help="default: cpu_count()")
    args = ap.parse_args()
    raise SystemExit(run(limit=args.limit, workers=args.workers))


if __name__ == "__main__":
    main()
