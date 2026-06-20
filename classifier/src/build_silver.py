"""Fase 4a — Silver: CSV + (XLSX opcional) + copia de PDFs a silver/papers/.

silver.csv es el formato primario (rápido de escribir, abre en cualquier herramienta).
silver.xlsx queda como vista humana opcional para abrir directo desde MinIO UI.
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import polars as pl
from rich.console import Console

try:
    from classifier.src.config import (
        BUCKET, KEY_SILVER_CSV, KEY_SILVER_FINAL, KEY_SILVER_PAPERS_PREFIX,
        KEY_SILVER_XLSX, OUTPUTS, SILVER_KEYWORD_THRESHOLD, YEAR_MIN, YEAR_MAX,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from classifier.src.config import (
        BUCKET, KEY_SILVER_CSV, KEY_SILVER_FINAL, KEY_SILVER_PAPERS_PREFIX,
        KEY_SILVER_XLSX, OUTPUTS, SILVER_KEYWORD_THRESHOLD, YEAR_MIN, YEAR_MAX,
    )

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from classifier.src._minio_client import minio  # noqa: E402
from classifier.src._papers_copy import copy_papers_to_tier  # noqa: E402

console = Console()


SILVER_COLUMNS = [
    "code", "original_filename", "year", "year_confidence",
    "title", "keywords_matched",
    "language", "score", "decision", "en_rango_temporal",
    "justificacion", "tfidf_cosine", "sbert_cosine",
    "abstract",
]


def _flatten_list_cols(df: pl.DataFrame) -> pl.DataFrame:
    for col in df.columns:
        if df[col].dtype == pl.List:
            df = df.with_columns(pl.col(col).list.join(", ").alias(col))
    return df


def run(no_xlsx: bool = False, no_copy: bool = False) -> int:
    console.rule("[bold]Fase 4a — Silver (CSV + papers)[/bold]")
    s3 = minio()
    buf = io.BytesIO()
    s3.download_fileobj(BUCKET, KEY_SILVER_FINAL, buf)
    buf.seek(0)
    df = pl.read_parquet(buf)

    # Filtros duros para entrar a Silver:
    #   1) año conocido y en [YEAR_MIN, YEAR_MAX] (últimos 10 años)
    #   2) score ≥ SILVER_KEYWORD_THRESHOLD (papers con muy pocas keywords matched
    #      no aportan al análisis y se descartan)
    # Los papers descartados quedan en silver.parquet interno con
    # decision = "Descartado…" para trazabilidad, pero NO van al CSV/XLSX ni a
    # silver/papers/.
    total = df.height
    silver_in = df.filter(
        pl.col("year").is_not_null()
        & (pl.col("year") >= YEAR_MIN)
        & (pl.col("year") <= YEAR_MAX)
        & (pl.col("score") >= SILVER_KEYWORD_THRESHOLD)
    )
    discarded = total - silver_in.height
    console.print(
        f"Filtros [año ∈ [{YEAR_MIN}-{YEAR_MAX}], score ≥ {SILVER_KEYWORD_THRESHOLD}]: "
        f"[green]{silver_in.height}[/green] entran a Silver · "
        f"[yellow]{discarded}[/yellow] descartados"
    )

    df_flat = _flatten_list_cols(
        silver_in.select([c for c in SILVER_COLUMNS if c in silver_in.columns]).sort("code")
    )

    # CSV — primario
    out_csv = OUTPUTS / "silver.csv"
    df_flat.write_csv(out_csv)
    s3.upload_file(str(out_csv), BUCKET, KEY_SILVER_CSV)
    console.print(f"[green]✓ silver.csv[/green] → s3://{BUCKET}/{KEY_SILVER_CSV}")
    console.print(f"[green]✓ local[/green] → {out_csv}")

    # XLSX — opcional
    if not no_xlsx:
        out_xlsx = OUTPUTS / "silver.xlsx"
        df_flat.write_excel(
            str(out_xlsx), worksheet="silver", autofit=True,
            header_format={"bold": True, "bg_color": "#1F4E78", "font_color": "white"},
        )
        s3.upload_file(str(out_xlsx), BUCKET, KEY_SILVER_XLSX)
        console.print(f"[green]✓ silver.xlsx[/green] → s3://{BUCKET}/{KEY_SILVER_XLSX}")

    console.print(f"Filas: [bold]{df_flat.height}[/bold]")

    # Copia de PDFs — solo los que pasaron los filtros
    if no_copy:
        console.print("[yellow]Copia de PDFs saltada por --no-copy[/yellow]")
    else:
        codes = silver_in["code"].to_list()
        copy_papers_to_tier(codes, KEY_SILVER_PAPERS_PREFIX, tier_label="silver")

    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-xlsx", action="store_true",
                    help="omitir silver.xlsx (más rápido)")
    ap.add_argument("--no-copy", action="store_true",
                    help="omitir copia de PDFs a silver/papers/")
    args = ap.parse_args()
    raise SystemExit(run(no_xlsx=args.no_xlsx, no_copy=args.no_copy))


if __name__ == "__main__":
    main()
