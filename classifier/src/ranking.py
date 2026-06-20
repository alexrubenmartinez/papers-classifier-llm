"""Fase 5 — Ranking final ordenado por (score, year).

CSV es el formato primario; XLSX es opcional para abrir desde MinIO UI.
El sort usa solo el score (= # keywords matched) y año como tiebreaker, en línea
con la regla de tier basada únicamente en keywords.
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import polars as pl
from rich.console import Console
from rich.table import Table

try:
    from classifier.src.config import (
        BUCKET, KEY_GOLD_PARQUET, KEY_GOLD_RANKING_CSV, KEY_GOLD_RANKING_XLSX, OUTPUTS,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from classifier.src.config import (
        BUCKET, KEY_GOLD_PARQUET, KEY_GOLD_RANKING_CSV, KEY_GOLD_RANKING_XLSX, OUTPUTS,
    )

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from classifier.src._minio_client import minio  # noqa: E402

console = Console()


def run(no_xlsx: bool = False) -> int:
    console.rule("[bold]Fase 5 — Ranking[/bold]")
    s3 = minio()
    buf = io.BytesIO()
    s3.download_fileobj(BUCKET, KEY_GOLD_PARQUET, buf)
    buf.seek(0)
    gold = pl.read_parquet(buf)

    ranking = (
        gold.sort(["score", "year"], descending=[True, True])
            .with_row_index(name="ranking", offset=1)
            .select([
                "ranking", "code", "year", "title", "score",
                "keywords_matched", "decision",
                "tfidf_cosine", "sbert_cosine",
            ])
    )

    for col in ranking.columns:
        if ranking[col].dtype == pl.List:
            ranking = ranking.with_columns(pl.col(col).list.join(", ").alias(col))

    out_csv = OUTPUTS / "ranking.csv"
    ranking.write_csv(out_csv)
    s3.upload_file(str(out_csv), BUCKET, KEY_GOLD_RANKING_CSV)
    console.print(f"[green]✓ ranking.csv[/green] → s3://{BUCKET}/{KEY_GOLD_RANKING_CSV}")

    if not no_xlsx:
        out_xlsx = OUTPUTS / "ranking.xlsx"
        ranking.write_excel(
            str(out_xlsx), worksheet="ranking", autofit=True,
            header_format={"bold": True, "bg_color": "#7D6608", "font_color": "white"},
        )
        s3.upload_file(str(out_xlsx), BUCKET, KEY_GOLD_RANKING_XLSX)
        console.print(f"[green]✓ ranking.xlsx[/green] → s3://{BUCKET}/{KEY_GOLD_RANKING_XLSX}")

    console.print(f"Total ranked: [bold]{ranking.height}[/bold]")

    t = Table(show_header=True, header_style="bold cyan")
    t.add_column("#", justify="right")
    t.add_column("Code")
    t.add_column("Año", justify="right")
    t.add_column("Score", justify="right")
    t.add_column("Título")
    for row in ranking.head(10).iter_rows(named=True):
        title = (row["title"] or "")[:80]
        t.add_row(str(row["ranking"]), row["code"], str(row["year"]),
                  str(row["score"]), title)
    console.print(t)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-xlsx", action="store_true",
                    help="omitir ranking.xlsx")
    args = ap.parse_args()
    raise SystemExit(run(no_xlsx=args.no_xlsx))


if __name__ == "__main__":
    main()
