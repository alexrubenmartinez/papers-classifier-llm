"""Fase 4a — Silver: CSV + XLSX con TODAS las 2000 filas (sin PDFs).

Silver es la "tabla de contabilidad" del corpus: una fila por cada paper de Bronze
con su score y decision actuales. No tiene PDFs — los originales viven en bronze/
(inmutables) y los seleccionados en gold/. Cualquier reclasificación lo regenera
desde cero contra `silver.parquet` interno.
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
        KEY_SILVER_XLSX, OUTPUTS,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from classifier.src.config import (
        BUCKET, KEY_SILVER_CSV, KEY_SILVER_FINAL, KEY_SILVER_PAPERS_PREFIX,
        KEY_SILVER_XLSX, OUTPUTS,
    )

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from classifier.src._minio_client import minio  # noqa: E402
from classifier.src._papers_copy import clean_tier_prefix  # noqa: E402

console = Console()


# (col_interno, header_es). Orden = orden de las columnas en CSV/XLSX.
SILVER_OUTPUT_COLUMNS: list[tuple[str, str]] = [
    ("code",              "Código"),
    ("code_pdf",          "Nombre del paper"),
    ("year",              "Año"),
    ("title",             "Título"),
    ("keywords_matched",  "Keywords detectadas"),
    ("score",             "Score"),
    ("decision",          "Decisión"),
]


def _flatten_list_cols(df: pl.DataFrame) -> pl.DataFrame:
    for col in df.columns:
        if df[col].dtype == pl.List:
            df = df.with_columns(pl.col(col).list.join(", ").alias(col))
    return df


def run(no_xlsx: bool = False) -> int:
    console.rule("[bold]Fase 4a — Silver (XLSX con 2000 filas)[/bold]")
    s3 = minio()
    buf = io.BytesIO()
    s3.download_fileobj(BUCKET, KEY_SILVER_FINAL, buf)
    buf.seek(0)
    df = pl.read_parquet(buf)
    console.print(f"Filas totales: [bold]{df.height}[/bold] (todos los papers, sin filtro)")

    # Columna derivada con el filename canónico del PDF en MinIO.
    df = df.with_columns((pl.col("code") + ".pdf").alias("code_pdf"))

    internal_cols = [internal for internal, _ in SILVER_OUTPUT_COLUMNS]
    headers_es    = [header_es for _, header_es in SILVER_OUTPUT_COLUMNS]
    df_out = _flatten_list_cols(df.select(internal_cols).sort("code"))
    df_out = df_out.rename(dict(zip(internal_cols, headers_es)))

    # CSV — primario
    out_csv = OUTPUTS / "silver.csv"
    df_out.write_csv(out_csv)
    s3.upload_file(str(out_csv), BUCKET, KEY_SILVER_CSV)
    console.print(f"[green]✓ silver.csv[/green] → s3://{BUCKET}/{KEY_SILVER_CSV}")
    console.print(f"[green]✓ local[/green] → {out_csv}")

    # XLSX — opcional
    if not no_xlsx:
        out_xlsx = OUTPUTS / "silver.xlsx"
        df_out.write_excel(
            str(out_xlsx), worksheet="silver", autofit=True,
            header_format={"bold": True, "bg_color": "#1F4E78", "font_color": "white"},
        )
        s3.upload_file(str(out_xlsx), BUCKET, KEY_SILVER_XLSX)
        console.print(f"[green]✓ silver.xlsx[/green] → s3://{BUCKET}/{KEY_SILVER_XLSX}")

    # Silver NO tiene PDFs. Si quedaron de runs previos (la versión vieja copiaba
    # 2000 PDFs acá), los borramos. Tras el primer rescore post-fix queda vacío y
    # los siguientes son no-op.
    clean_tier_prefix(KEY_SILVER_PAPERS_PREFIX, keep_codes=None, tier_label="silver")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-xlsx", action="store_true",
                    help="omitir silver.xlsx (más rápido)")
    args = ap.parse_args()
    raise SystemExit(run(no_xlsx=args.no_xlsx))


if __name__ == "__main__":
    main()
