"""Fase 4a — Genera silver.xlsx (vista completa para la rúbrica)."""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import polars as pl
from rich.console import Console

try:
    from classifier.src.config import (
        BUCKET, KEY_SILVER_FINAL, KEY_SILVER_XLSX, OUTPUTS,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from classifier.src.config import (
        BUCKET, KEY_SILVER_FINAL, KEY_SILVER_XLSX, OUTPUTS,
    )

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from classifier.src._minio_client import minio  # noqa: E402

console = Console()


SILVER_COLUMNS_XLSX = [
    "code", "original_filename", "year", "year_confidence",
    "title", "keywords_matched",
    "language", "score", "decision", "en_rango_temporal",
    "justificacion", "tfidf_cosine", "sbert_cosine",
    "keyword_raw", "score_raw",
    "abstract",
]


def run() -> int:
    console.rule("[bold]Fase 4a — silver.xlsx[/bold]")
    s3 = minio()
    buf = io.BytesIO()
    s3.download_fileobj(BUCKET, KEY_SILVER_FINAL, buf)
    buf.seek(0)
    df = pl.read_parquet(buf)

    df_xlsx = df.select([c for c in SILVER_COLUMNS_XLSX if c in df.columns]).sort("code")
    # Convertir listas a strings para Excel
    for col in df_xlsx.columns:
        if df_xlsx[col].dtype == pl.List:
            df_xlsx = df_xlsx.with_columns(
                pl.col(col).list.join(", ").alias(col)
            )

    out_local = OUTPUTS / "silver.xlsx"
    df_xlsx.write_excel(
        str(out_local), worksheet="silver", autofit=True,
        header_format={"bold": True, "bg_color": "#1F4E78", "font_color": "white"},
    )
    s3.upload_file(str(out_local), BUCKET, KEY_SILVER_XLSX)
    console.print(f"[green]✓ silver.xlsx[/green] → s3://{BUCKET}/{KEY_SILVER_XLSX}")
    console.print(f"[green]✓ local[/green] → {out_local}")
    console.print(f"Filas: [bold]{df_xlsx.height}[/bold]")
    return 0


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    raise SystemExit(run())
