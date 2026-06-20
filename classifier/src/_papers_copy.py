"""Helper compartido — copia server-side de PDFs entre tiers en MinIO.

Bronze siempre contiene los PDFs originales en `KEY_BRONZE_PAPERS_PREFIX`.
Silver y Gold reciben copias 1-a-1 vía `s3.copy_object`, que es server-side
(no descarga el objeto al cliente), por eso es órdenes de magnitud más rápido
que re-uploadar.
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn, MofNCompleteColumn, Progress, SpinnerColumn,
    TextColumn, TimeElapsedColumn,
)

try:
    from classifier.src.config import (
        BUCKET, COPY_WORKERS, KEY_BRONZE_PAPERS_PREFIX,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from classifier.src.config import (
        BUCKET, COPY_WORKERS, KEY_BRONZE_PAPERS_PREFIX,
    )

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from classifier.src._minio_client import minio  # noqa: E402

console = Console()


def _copy_one(s3, code: str, dst_prefix: str) -> tuple[str, str | None]:
    src_key = f"{KEY_BRONZE_PAPERS_PREFIX}{code}.pdf"
    dst_key = f"{dst_prefix}{code}.pdf"
    try:
        s3.copy_object(
            Bucket=BUCKET,
            CopySource={"Bucket": BUCKET, "Key": src_key},
            Key=dst_key,
            MetadataDirective="COPY",
        )
        return code, None
    except Exception as e:
        return code, f"{type(e).__name__}: {e}"


def copy_papers_to_tier(codes: list[str], dst_prefix: str,
                        tier_label: str = "tier") -> tuple[int, int]:
    """Copia bronze/papers/{code}.pdf → {dst_prefix}{code}.pdf en paralelo.

    Devuelve (ok, fallidos). Imprime barra de progreso y, al final, los códigos
    que fallaron (típicamente porque el PDF no existe en bronze).
    """
    if not codes:
        console.print(f"[yellow]No hay códigos para copiar a {tier_label}[/yellow]")
        return 0, 0

    s3 = minio()
    ok, failed_msgs = 0, []
    with Progress(SpinnerColumn(), TextColumn(f"[bold]Copy → {tier_label}[/bold]"),
                  BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
                  console=console) as progress:
        task = progress.add_task("copy", total=len(codes))
        with ThreadPoolExecutor(max_workers=COPY_WORKERS) as ex:
            futures = [ex.submit(_copy_one, s3, c, dst_prefix) for c in codes]
            for fut in as_completed(futures):
                code, err = fut.result()
                if err is None:
                    ok += 1
                else:
                    failed_msgs.append(f"{code}: {err}")
                progress.advance(task)

    failed = len(failed_msgs)
    if failed:
        console.print(f"[red]✗ {failed} fallidos[/red] (primeros 5):")
        for msg in failed_msgs[:5]:
            console.print(f"  · {msg}")
    console.print(f"[green]✓ {ok}/{len(codes)} PDFs copiados a {tier_label}[/green]")
    return ok, failed
