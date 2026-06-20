"""Fase 6 — Reporte markdown con resumen ejecutivo + top-20 + distribución."""
from __future__ import annotations

import io
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
from rich.console import Console

try:
    from classifier.src.config import (
        BUCKET, GOLD_KEYWORD_THRESHOLD, GROUP_PREFIX,
        KEY_GOLD_PARQUET, KEY_SILVER_FINAL,
        KEY_REPORT_MD, OUTPUTS, YEAR_MIN, YEAR_MAX,
    )
    from classifier.search_query import KEYWORDS_FLAT, SEARCH_QUERY
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from classifier.src.config import (
        BUCKET, GOLD_KEYWORD_THRESHOLD, GROUP_PREFIX,
        KEY_GOLD_PARQUET, KEY_SILVER_FINAL,
        KEY_REPORT_MD, OUTPUTS, YEAR_MIN, YEAR_MAX,
    )
    from classifier.search_query import KEYWORDS_FLAT, SEARCH_QUERY

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from classifier.src._minio_client import minio  # noqa: E402

console = Console()


def _download_parquet(s3, key: str) -> pl.DataFrame:
    buf = io.BytesIO()
    s3.download_fileobj(BUCKET, key, buf)
    buf.seek(0)
    return pl.read_parquet(buf)


def run() -> int:
    console.rule("[bold]Fase 6 — report.md[/bold]")
    s3 = minio()
    silver = _download_parquet(s3, KEY_SILVER_FINAL)
    gold = _download_parquet(s3, KEY_GOLD_PARQUET)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    score_dist = Counter(silver["score"].to_list())
    decision_dist = Counter(silver["decision"].to_list())
    years = [y for y in silver["year"].to_list() if y is not None]
    year_dist = Counter(years)
    max_score = int(silver["score"].max()) if silver.height else 0

    lines: list[str] = []
    lines.append(f"# Reporte de clasificación — {GROUP_PREFIX}")
    lines.append("")
    lines.append(f"Generado: {ts}")
    lines.append("")
    lines.append("## Resumen ejecutivo")
    lines.append("")
    lines.append(f"- Corpus total: **{silver.height}** papers en Bronze.")
    lines.append(f"- Papers con título extraído: **{silver['title'].is_not_null().sum()}** "
                 f"({silver['title'].is_not_null().sum()*100/max(silver.height,1):.0f}%)")
    lines.append(f"- Papers con abstract: **{silver['abstract'].is_not_null().sum()}**")
    lines.append(f"- Papers con año detectado: **{silver['year'].is_not_null().sum()}**")
    lines.append(f"- Rango temporal aplicado: **{YEAR_MIN}–{YEAR_MAX}**")
    lines.append(f"- Papers en rango: **{silver['en_rango_temporal'].sum()}**")
    lines.append(
        f"- Umbral Gold: **score ≥ {GOLD_KEYWORD_THRESHOLD}** "
        f"(de {len(KEYWORDS_FLAT)} keywords totales)."
    )
    lines.append(f"- Papers seleccionados a Gold: **{gold.height}**")
    lines.append("")

    lines.append("## Distribución por score (Silver completo)")
    lines.append("")
    lines.append("`score = # keywords distintas matched en title ∪ keywords ∪ abstract`")
    lines.append("")
    lines.append("| Score | Conteo | % |")
    lines.append("|---:|---:|---:|")
    for s in range(max(max_score, GOLD_KEYWORD_THRESHOLD), -1, -1):
        c = score_dist.get(s, 0)
        marker = "  ← Gold ≥" if s == GOLD_KEYWORD_THRESHOLD else ""
        lines.append(f"| {s}{marker} | {c} | {c*100/max(silver.height,1):.1f}% |")
    lines.append("")

    lines.append("## Distribución por decisión")
    lines.append("")
    lines.append("| Decisión | Conteo |")
    lines.append("|---|---:|")
    for dec, c in sorted(decision_dist.items(), key=lambda x: -x[1]):
        lines.append(f"| {dec} | {c} |")
    lines.append("")

    lines.append("## Distribución por año (corpus completo)")
    lines.append("")
    lines.append("| Año | Conteo |")
    lines.append("|---:|---:|")
    for y in sorted(year_dist.keys()):
        lines.append(f"| {y} | {year_dist[y]} |")
    lines.append("")

    lines.append("## Top-20 papers (ranking Gold)")
    lines.append("")
    lines.append("| # | Code | Año | Score | Título |")
    lines.append("|---:|---|---:|---:|---|")
    for i, row in enumerate(gold.head(20).iter_rows(named=True), start=1):
        title = (row["title"] or "").replace("|", "/").strip()[:120]
        lines.append(f"| {i} | {row['code']} | {row['year']} | {row['score']} | {title} |")
    lines.append("")

    lines.append("## Metodología")
    lines.append("")
    lines.append("Pipeline en 3 capas, todas en MinIO bajo el prefijo `" + GROUP_PREFIX + "/`:")
    lines.append("")
    lines.append("1. **Bronze** (inmutable): PDFs originales en `bronze/papers/` + manifiesto (`index.parquet`).")
    lines.append("2. **Silver**: para cada PDF en bronze: metadata extraída con PyMuPDF (título, abstract, "
                 "keywords, año), score = `# keywords distintas matched`, y **copia del PDF** a `silver/papers/`.")
    lines.append(f"3. **Gold**: subconjunto con `score ≥ {GOLD_KEYWORD_THRESHOLD}` y año ∈ "
                 f"[{YEAR_MIN}, {YEAR_MAX}]; los PDFs se copian a `gold/papers/`.")
    lines.append("")
    lines.append("### Score (regla única de tier)")
    lines.append("")
    lines.append(
        f"Para cada paper se cuenta cuántas de las **{len(KEYWORDS_FLAT)} keywords** "
        "aparecen al menos una vez (substring match, case-insensitive) en el texto "
        "concatenado de **título ∪ keywords ∪ abstract**. Ese conteo es el `score`."
    )
    lines.append("")
    lines.append(f"- **Gold**: `score ≥ {GOLD_KEYWORD_THRESHOLD}` y año en rango.")
    lines.append("- **Silver**: todos los demás.")
    lines.append("")
    lines.append("Las columnas `tfidf_cosine` y `sbert_cosine` se calculan y persisten "
                 "como métricas auxiliares informativas en el CSV, pero **no intervienen** "
                 "en la decisión de tier.")
    lines.append("")

    lines.append("### Lista de keywords")
    lines.append("")
    for kw in KEYWORDS_FLAT:
        lines.append(f"- `{kw}`")
    lines.append("")

    lines.append("### Cadena de búsqueda (Scopus)")
    lines.append("")
    lines.append("```")
    lines.append(SEARCH_QUERY)
    lines.append("```")
    lines.append("")

    report = "\n".join(lines)
    out = OUTPUTS / "report.md"
    out.write_text(report, encoding="utf-8")
    s3.upload_file(str(out), BUCKET, KEY_REPORT_MD,
                   ExtraArgs={"ContentType": "text/markdown; charset=utf-8"})
    console.print(f"[green]✓ report.md[/green] → s3://{BUCKET}/{KEY_REPORT_MD}")
    console.print(f"[green]✓ local[/green] → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
