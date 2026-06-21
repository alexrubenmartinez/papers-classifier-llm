"""Fase 4b — Gold: filtrar por score ≥ GOLD_KEYWORD_THRESHOLD + año en rango.

Outputs:
- gold.csv (primario), gold.xlsx (opcional), gold.parquet (formato interno)
- gold/papers/{code}.pdf — copia 1-a-1 desde bronze/papers/
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
        BUCKET, GOLD_KEYWORD_THRESHOLD, KEY_GOLD_CSV, KEY_GOLD_PAPERS_PREFIX,
        KEY_GOLD_PARQUET, KEY_GOLD_XLSX, KEY_SILVER_FINAL,
        OUTPUTS, YEAR_MIN, YEAR_MAX,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from classifier.src.config import (
        BUCKET, GOLD_KEYWORD_THRESHOLD, KEY_GOLD_CSV, KEY_GOLD_PAPERS_PREFIX,
        KEY_GOLD_PARQUET, KEY_GOLD_XLSX, KEY_SILVER_FINAL,
        OUTPUTS, YEAR_MIN, YEAR_MAX,
    )

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from classifier.src._minio_client import minio  # noqa: E402
from classifier.src._papers_copy import (  # noqa: E402
    clean_tier_prefix, copy_papers_to_tier,
)

console = Console()


GOLD_COLUMNS = [
    "code", "original_filename", "year", "title",
    "score", "decision", "keywords_matched",
    "justificacion", "tfidf_cosine", "sbert_cosine", "abstract",
]


def _flatten_list_cols(df: pl.DataFrame) -> pl.DataFrame:
    for col in df.columns:
        if df[col].dtype == pl.List:
            df = df.with_columns(pl.col(col).list.join(", ").alias(col))
    return df


def run(no_xlsx: bool = False, no_copy: bool = False) -> int:
    console.rule("[bold]Fase 4b — Gold[/bold]")
    s3 = minio()
    buf = io.BytesIO()
    s3.download_fileobj(BUCKET, KEY_SILVER_FINAL, buf)
    buf.seek(0)
    silver = pl.read_parquet(buf)

    gold = silver.filter(
        (pl.col("score") >= GOLD_KEYWORD_THRESHOLD)
        & (pl.col("year").is_not_null())
        & (pl.col("year") >= YEAR_MIN)
        & (pl.col("year") <= YEAR_MAX)
    ).sort(["score", "year"], descending=[True, True])

    gold_flat = _flatten_list_cols(
        gold.select([c for c in GOLD_COLUMNS if c in gold.columns])
    )

    # parquet — formato interno
    out_pq = OUTPUTS / "gold.parquet"
    gold.write_parquet(out_pq)
    s3.upload_file(str(out_pq), BUCKET, KEY_GOLD_PARQUET)
    console.print(f"[green]✓ gold.parquet[/green] → s3://{BUCKET}/{KEY_GOLD_PARQUET}")

    # CSV — primario
    out_csv = OUTPUTS / "gold.csv"
    gold_flat.write_csv(out_csv)
    s3.upload_file(str(out_csv), BUCKET, KEY_GOLD_CSV)
    console.print(f"[green]✓ gold.csv[/green] → s3://{BUCKET}/{KEY_GOLD_CSV}")

    # XLSX — opcional
    if not no_xlsx:
        out_xlsx = OUTPUTS / "gold.xlsx"
        gold_flat.write_excel(
            str(out_xlsx), worksheet="gold", autofit=True,
            header_format={"bold": True, "bg_color": "#B7950B", "font_color": "white"},
        )
        s3.upload_file(str(out_xlsx), BUCKET, KEY_GOLD_XLSX)
        console.print(f"[green]✓ gold.xlsx[/green] → s3://{BUCKET}/{KEY_GOLD_XLSX}")

    console.print(
        f"Papers Gold: [bold]{gold.height}[/bold] "
        f"(score ≥ {GOLD_KEYWORD_THRESHOLD}, año {YEAR_MIN}-{YEAR_MAX})"
    )

    # Sincronizar gold/papers/: copia los nuevos y BORRA los que ya no califican
    # (en cada reclasificación, gold/ refleja exacto el set actual — sin ghosts).
    if no_copy:
        console.print("[yellow]Copia/cleanup de PDFs saltada por --no-copy[/yellow]")
    else:
        codes = gold["code"].to_list()
        copy_papers_to_tier(codes, KEY_GOLD_PAPERS_PREFIX, tier_label="gold")
        clean_tier_prefix(KEY_GOLD_PAPERS_PREFIX, keep_codes=codes, tier_label="gold")

    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-xlsx", action="store_true",
                    help="omitir gold.xlsx")
    ap.add_argument("--no-copy", action="store_true",
                    help="omitir copia de PDFs a gold/papers/")
    args = ap.parse_args()
    raise SystemExit(run(no_xlsx=args.no_xlsx, no_copy=args.no_copy))


if __name__ == "__main__":
    main()
