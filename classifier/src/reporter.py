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
        BUCKET, GROUP_PREFIX, KEY_GOLD_PARQUET, KEY_SILVER_FINAL,
        KEY_REPORT_MD, OUTPUTS, YEAR_MIN, YEAR_MAX,
    )
    from classifier.search_query import SEARCH_QUERY, KEYWORDS_BY_AXIS
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from classifier.src.config import (
        BUCKET, GROUP_PREFIX, KEY_GOLD_PARQUET, KEY_SILVER_FINAL,
        KEY_REPORT_MD, OUTPUTS, YEAR_MIN, YEAR_MAX,
    )
    from classifier.search_query import SEARCH_QUERY, KEYWORDS_BY_AXIS

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
    lines.append(f"- Papers seleccionados a Gold: **{gold.height}**")
    if gold.height:
        score5 = (gold['score'] == 5).sum()
        score4 = (gold['score'] == 4).sum()
        lines.append(f"  - score 5: {score5}")
        lines.append(f"  - score 4: {score4}")
    lines.append("")

    lines.append("## Distribución por score (Silver completo)")
    lines.append("")
    lines.append("| Score | Conteo | % |")
    lines.append("|---:|---:|---:|")
    for s in [5, 4, 3, 2, 1]:
        c = score_dist.get(s, 0)
        lines.append(f"| {s} | {c} | {c*100/max(silver.height,1):.1f}% |")
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
    lines.append("1. **Bronze**: PDFs originales inmutables + manifiesto (`index.parquet`) + tabla de control.")
    lines.append("2. **Silver**: metadata extraída con PyMuPDF (título, abstract, keywords, año) + score híbrido.")
    lines.append("3. **Gold**: subconjunto con score ∈ {4,5} y año ∈ [" + str(YEAR_MIN) + ", " + str(YEAR_MAX) + "].")
    lines.append("")
    lines.append("### Score híbrido (3 capas, pesos 0.40 / 0.30 / 0.30)")
    lines.append("")
    lines.append("- **Keyword matching pesado**: título×3.0 · abstract×2.0 · keywords×1.5, "
                 "con bonus por cobertura de múltiples ejes temáticos (zero_trust, cybersecurity, detection, ai).")
    lines.append("- **TF-IDF cosine similarity**: vectorizer (1,2)-gram sobre el corpus, "
                 "cosine vs la query natural-language.")
    lines.append("- **Sentence-BERT (`all-MiniLM-L6-v2`)**: embeddings semánticos cosine vs la query. "
                 "Captura conceptos como NIST 800-207, BeyondCorp, microsegmentation aunque no aparezcan literales.")
    lines.append("")
    lines.append("Score raw normalizado [0,1] → score 1-5 por percentiles sobre el corpus completo.")
    lines.append("")

    lines.append("### Cadena de búsqueda")
    lines.append("")
    lines.append("```")
    lines.append(SEARCH_QUERY)
    lines.append("```")
    lines.append("")

    lines.append("### Ejes temáticos")
    lines.append("")
    for axis, kws in KEYWORDS_BY_AXIS.items():
        lines.append(f"- **{axis}**: {', '.join(kws[:8])}{' …' if len(kws) > 8 else ''}")
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
