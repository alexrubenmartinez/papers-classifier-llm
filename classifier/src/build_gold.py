"""Fase 4b — Filtra a Gold (score ≥ 4 + año en rango)."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import polars as pl
from rich.console import Console

try:
    from classifier.src.config import (
        BUCKET, KEY_SILVER_FINAL, KEY_GOLD_PARQUET, KEY_GOLD_XLSX,
        OUTPUTS, YEAR_MIN, YEAR_MAX,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from classifier.src.config import (
        BUCKET, KEY_SILVER_FINAL, KEY_GOLD_PARQUET, KEY_GOLD_XLSX,
        OUTPUTS, YEAR_MIN, YEAR_MAX,
    )

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from classifier.src._minio_client import minio  # noqa: E402

console = Console()


GOLD_COLUMNS = [
    "code", "original_filename", "year", "title",
    "score", "decision", "keywords_matched",
    "justificacion", "tfidf_cosine", "sbert_cosine", "abstract",
]


def run() -> int:
    console.rule("[bold]Fase 4b — Gold[/bold]")
    s3 = minio()
    buf = io.BytesIO()
    s3.download_fileobj(BUCKET, KEY_SILVER_FINAL, buf)
    buf.seek(0)
    silver = pl.read_parquet(buf)

    gold = silver.filter(
        (pl.col("score") >= 4)
        & (pl.col("year").is_not_null())
        & (pl.col("year") >= YEAR_MIN)
        & (pl.col("year") <= YEAR_MAX)
    ).sort(["score", "sbert_cosine", "year"], descending=[True, True, True])

    gold_xlsx = gold.select([c for c in GOLD_COLUMNS if c in gold.columns])
    for col in gold_xlsx.columns:
        if gold_xlsx[col].dtype == pl.List:
            gold_xlsx = gold_xlsx.with_columns(pl.col(col).list.join(", ").alias(col))

    # parquet
    out_pq = OUTPUTS / "gold.parquet"
    gold.write_parquet(out_pq)
    s3.upload_file(str(out_pq), BUCKET, KEY_GOLD_PARQUET)

    # xlsx
    out_xlsx = OUTPUTS / "gold.xlsx"
    gold_xlsx.write_excel(
        str(out_xlsx), worksheet="gold", autofit=True,
        header_format={"bold": True, "bg_color": "#B7950B", "font_color": "white"},
    )
    s3.upload_file(str(out_xlsx), BUCKET, KEY_GOLD_XLSX)

    console.print(f"[green]✓ gold.parquet[/green] → s3://{BUCKET}/{KEY_GOLD_PARQUET}")
    console.print(f"[green]✓ gold.xlsx[/green] → s3://{BUCKET}/{KEY_GOLD_XLSX}")
    console.print(f"Papers Gold: [bold]{gold.height}[/bold]  "
                  f"(score 5: {(gold['score']==5).sum()}, score 4: {(gold['score']==4).sum()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
