"""Fase 3 — Scoring por conteo de keywords distintas.

Regla única de tier:
    score = # de keywords distintas de KEYWORDS_FLAT que aparecen
            en title ∪ keywords ∪ abstract (case-insensitive, normalizado).
    decision = Gold si score ≥ GOLD_KEYWORD_THRESHOLD y año en rango;
               Silver en caso contrario.

TF-IDF y SBERT siguen calculándose y persistiéndose en silver como columnas
informativas (tfidf_cosine, sbert_cosine) para análisis posterior, pero NO
intervienen en la decisión de tier.

Salidas en MinIO:
- silver.parquet           (corpus con score, decision, justificación, métricas aux)
- embeddings.npy           (cache de SBERT — para recalibrar sin recomputar)
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl
from rich.console import Console
from rich.progress import (
    BarColumn, MofNCompleteColumn, Progress, SpinnerColumn,
    TextColumn, TimeElapsedColumn,
)
from rich.table import Table

try:
    from classifier.src.config import (
        BUCKET, GOLD_KEYWORD_THRESHOLD, SILVER_KEYWORD_THRESHOLD,
        KEY_BRONZE_INDEX, KEY_SILVER_METADATA,
        KEY_SILVER_FINAL, KEY_SILVER_EMBEDDINGS,
        MAX_SCORE, OUTPUTS, SBERT_MODEL,
        YEAR_MIN, YEAR_MAX,
    )
    from classifier.search_query import KEYWORDS_FLAT, query_as_natural_text
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from classifier.src.config import (
        BUCKET, GOLD_KEYWORD_THRESHOLD, SILVER_KEYWORD_THRESHOLD,
        KEY_BRONZE_INDEX, KEY_SILVER_METADATA,
        KEY_SILVER_FINAL, KEY_SILVER_EMBEDDINGS,
        MAX_SCORE, OUTPUTS, SBERT_MODEL,
        YEAR_MIN, YEAR_MAX,
    )
    from classifier.search_query import KEYWORDS_FLAT, query_as_natural_text

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from classifier.src._minio_client import minio  # noqa: E402

console = Console()


# ─────────────────────────────────────────────────────────────── #
# Cargar bronze + silver_metadata y joinarlos                    #
# ─────────────────────────────────────────────────────────────── #
def load_inputs() -> pl.DataFrame:
    s3 = minio()
    buf = io.BytesIO()
    s3.download_fileobj(BUCKET, KEY_BRONZE_INDEX, buf)
    buf.seek(0)
    bronze = pl.read_parquet(buf)

    buf = io.BytesIO()
    s3.download_fileobj(BUCKET, KEY_SILVER_METADATA, buf)
    buf.seek(0)
    meta = pl.read_parquet(buf)

    cols_bronze = ["code", "original_filename", "year_from_arxiv",
                   "topic_tag_local", "title_from_filename", "size_bytes"]
    df = bronze.select(cols_bronze).join(meta, on="code", how="left")

    df = df.with_columns(
        pl.when(pl.col("year_confidence") == "high")
          .then(pl.col("year_extracted"))
          .when(pl.col("year_from_arxiv").is_not_null())
          .then(pl.col("year_from_arxiv"))
          .otherwise(pl.col("year_extracted"))
          .alias("year")
    )

    # Título: 1) extraído del PDF; 2) parseado del filename arxiv; 3) filename crudo
    # (sin .pdf) como último recurso para que ninguna fila quede vacía en el reporte.
    df = df.with_columns(
        pl.coalesce([
            "title_extracted",
            "title_from_filename",
            pl.col("original_filename").str.replace(r"\.pdf$", "", literal=False),
        ]).alias("title")
    )
    return df


# ─────────────────────────────────────────────────────────────── #
# Capa única — Keyword score = # keywords distintas matched      #
# ─────────────────────────────────────────────────────────────── #
def normalize_text(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[\s\-_/]+", " ", s)
    s = re.sub(r"[^\w\s.+]", " ", s)
    return s


_KEYWORDS_NORMALIZED: list[tuple[str, str]] = [
    (kw, normalize_text(kw)) for kw in KEYWORDS_FLAT
]


def keyword_score_row(title: str | None, abstract: str | None,
                      keywords: list[str] | None) -> tuple[int, list[str]]:
    """Cuenta cuántas keywords distintas de KEYWORDS_FLAT aparecen en el texto.

    El haystack es la concatenación normalizada de title + keywords + abstract.
    Cada keyword cuenta 1 si aparece al menos una vez (substring match).
    """
    haystack = " ".join([
        normalize_text(title),
        normalize_text(" ".join(keywords or [])),
        normalize_text(abstract),
    ])
    matched = [kw for kw, kw_n in _KEYWORDS_NORMALIZED if kw_n and kw_n in haystack]
    return len(matched), matched


# ─────────────────────────────────────────────────────────────── #
# Métricas auxiliares (informativas, no deciden tier)            #
# ─────────────────────────────────────────────────────────────── #
def tfidf_scores(corpus: list[str], query: str) -> np.ndarray:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vec = TfidfVectorizer(
        lowercase=True, strip_accents="unicode",
        ngram_range=(1, 2), max_df=0.95, min_df=2,
        max_features=50_000,
    )
    X = vec.fit_transform(corpus)
    q = vec.transform([query])
    return cosine_similarity(q, X).ravel()


SBERT_BATCH_SIZE = 128

ONNX_VARIANTS = [
    "onnx/model_qint8_avx512_vnni.onnx",
    "onnx/model_qint8_avx512.onnx",
    "onnx/model_quint8_avx2.onnx",
    "onnx/model_qint8_arm64.onnx",
]


def _load_sbert_model():
    try:
        import os as _os
        import torch
        n_threads = min(_os.cpu_count() or 4, 4)
        torch.set_num_threads(n_threads)
        torch.set_num_interop_threads(max(1, n_threads // 2))
    except Exception:
        pass

    from sentence_transformers import SentenceTransformer

    for variant in ONNX_VARIANTS:
        try:
            model = SentenceTransformer(
                SBERT_MODEL,
                backend="onnx",
                model_kwargs={"file_name": variant, "provider": "CPUExecutionProvider"},
            )
            console.print(f"[dim]SBERT backend: ONNX [bold]{variant}[/bold][/dim]")
            return model
        except Exception:
            continue

    try:
        model = SentenceTransformer(SBERT_MODEL, backend="onnx")
        console.print("[dim]SBERT backend: ONNX (no cuantizado)[/dim]")
        return model
    except Exception as e:
        console.print(f"[yellow]ONNX no disponible ({type(e).__name__}); fallback a PyTorch[/yellow]")
        return SentenceTransformer(SBERT_MODEL)


def sbert_scores(corpus: list[str], query: str, codes: list[str],
                 use_cache: bool = True) -> np.ndarray:
    cache_local = OUTPUTS / "embeddings.npy"
    cache_codes_local = OUTPUTS / "embeddings_codes.npy"

    if use_cache and cache_local.exists() and cache_codes_local.exists():
        cached_codes = np.load(cache_codes_local, allow_pickle=True).tolist()
        if cached_codes == codes:
            corpus_emb = np.load(cache_local)
            console.print("[dim](usando cache local de embeddings)[/dim]")
        else:
            corpus_emb = None
    else:
        corpus_emb = None

    model = None
    if corpus_emb is None:
        console.print(f"[bold]Cargando SBERT[/bold] [cyan]{SBERT_MODEL}[/cyan]…")
        model = _load_sbert_model()
        console.print(f"[bold]Encoding {len(corpus)} documents[/bold] (batch={SBERT_BATCH_SIZE})…")
        corpus_emb = model.encode(
            corpus, batch_size=SBERT_BATCH_SIZE, show_progress_bar=True,
            convert_to_numpy=True, normalize_embeddings=True,
        )
        np.save(cache_local, corpus_emb)
        np.save(cache_codes_local, np.array(codes, dtype=object))

    if model is None:
        model = _load_sbert_model()
    query_emb = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
    return (corpus_emb @ query_emb.T).ravel()


# ─────────────────────────────────────────────────────────────── #
# Decisión de tier                                               #
# ─────────────────────────────────────────────────────────────── #
def decision_for(matches: int, year: int | None) -> str:
    """Regla de tier — filtros aplicados en cascada:
    1) sin año o fuera de rango → Descartado
    2) score < SILVER_KEYWORD_THRESHOLD → Descartado (score bajo)
    3) score ≥ GOLD_KEYWORD_THRESHOLD → Gold
    4) en otro caso (≥ Silver, < Gold) → Silver
    """
    if year is None:
        return "Descartado (sin año)"
    if not (YEAR_MIN <= year <= YEAR_MAX):
        return "Descartado (fuera de rango temporal)"
    if matches < SILVER_KEYWORD_THRESHOLD:
        return "Descartado (score bajo)"
    if matches >= GOLD_KEYWORD_THRESHOLD:
        return "Gold"
    return "Silver"


# ─────────────────────────────────────────────────────────────── #
# Driver                                                         #
# ─────────────────────────────────────────────────────────────── #
def run(skip_sbert: bool = False, use_cache: bool = True) -> int:
    console.rule("[bold]Fase 3 — Scoring (conteo de keywords)[/bold]")
    df = load_inputs()
    n = df.height
    console.print(f"Papers a scorear: [bold]{n}[/bold]  ·  "
                  f"keywords: [bold]{len(KEYWORDS_FLAT)}[/bold]  ·  "
                  f"score capado a {MAX_SCORE}  ·  "
                  f"Gold threshold: ≥ [bold]{GOLD_KEYWORD_THRESHOLD}[/bold]  ·  "
                  f"año ∈ [{YEAR_MIN}, {YEAR_MAX}]")

    df = df.with_columns(
        pl.concat_str([
            pl.col("title").fill_null(""),
            pl.lit(". "),
            pl.col("abstract").fill_null(""),
        ]).alias("text_for_score")
    )
    corpus_text = df["text_for_score"].to_list()
    codes = df["code"].to_list()

    # ── Score = # keywords distintas ── #
    started = time.perf_counter()
    match_counts, matched_lists = [], []
    with Progress(SpinnerColumn(), TextColumn("[bold]Keyword score[/bold]"),
                  BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
                  console=console) as progress:
        task = progress.add_task("kw", total=n)
        for row in df.iter_rows(named=True):
            count, matched = keyword_score_row(
                row["title"], row["abstract"], row["keywords_extracted"],
            )
            match_counts.append(count)
            matched_lists.append(matched)
            progress.advance(task)
    # score = #keywords distintas matched, capado a MAX_SCORE.
    # El raw count se conserva en la justificación para trazabilidad.
    raw_counts = np.array(match_counts, dtype=int)
    score_arr = np.minimum(raw_counts, MAX_SCORE)
    console.print(f"[dim]keyword in {time.perf_counter()-started:.1f}s[/dim]")

    # ── TF-IDF (informativo) ── #
    started = time.perf_counter()
    tfidf_arr = tfidf_scores(corpus_text, query_as_natural_text())
    console.print(f"[dim]tfidf in {time.perf_counter()-started:.1f}s[/dim]")

    # ── SBERT (informativo) ── #
    if skip_sbert:
        sbert_arr = np.zeros(n)
        console.print("[yellow]SBERT saltado por --skip-sbert[/yellow]")
    else:
        started = time.perf_counter()
        sbert_arr = sbert_scores(corpus_text, query_as_natural_text(), codes, use_cache)
        console.print(f"[dim]sbert in {time.perf_counter()-started:.1f}s[/dim]")
        s3 = minio()
        cache_local = OUTPUTS / "embeddings.npy"
        if cache_local.exists():
            s3.upload_file(str(cache_local), BUCKET, KEY_SILVER_EMBEDDINGS)

    # ── Justificación textual (incluye métricas aux para trazabilidad) ── #
    just = []
    for i in range(n):
        parts = [f"matches={match_counts[i]}/{len(KEYWORDS_FLAT)}"]
        if matched_lists[i]:
            parts.append(f"kws: {', '.join(matched_lists[i][:8])}")
        parts.append(f"tfidf={tfidf_arr[i]:.3f}")
        if not skip_sbert:
            parts.append(f"sbert={sbert_arr[i]:.3f}")
        just.append(" · ".join(parts))

    years = df["year"].to_list()
    decisions = [decision_for(c, y) for c, y in zip(match_counts, years)]

    df = df.with_columns(
        pl.Series("score", score_arr),
        pl.Series("keywords_matched", matched_lists),
        pl.Series("tfidf_cosine", tfidf_arr),
        pl.Series("sbert_cosine", sbert_arr),
        pl.Series("justificacion", just),
        pl.Series("decision", decisions),
        pl.col("year").map_elements(
            lambda y: (y is not None) and YEAR_MIN <= y <= YEAR_MAX,
            return_dtype=pl.Boolean,
        ).alias("en_rango_temporal"),
    )

    out_local = OUTPUTS / "silver.parquet"
    df.write_parquet(out_local)
    s3 = minio()
    s3.upload_file(str(out_local), BUCKET, KEY_SILVER_FINAL)
    console.print(f"\n[green]✓ silver[/green] → s3://{BUCKET}/{KEY_SILVER_FINAL}")

    # Histograma de scores (0..MAX_SCORE, marca de Gold en threshold)
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Score (capado a {})".format(MAX_SCORE))
    table.add_column("Conteo", justify="right")
    score_series = df["score"]
    for s in range(0, MAX_SCORE + 1):
        c = (score_series == s).sum()
        marker = " ← Gold" if s >= GOLD_KEYWORD_THRESHOLD else ""
        table.add_row(f"{s}{marker}", str(c))
    console.print(table)

    table2 = Table(show_header=True, header_style="bold cyan")
    table2.add_column("Decisión")
    table2.add_column("Conteo", justify="right")
    for dec, c in (df.group_by("decision")
                     .agg(pl.len().alias("c"))
                     .sort("c", descending=True)
                     .iter_rows()):
        table2.add_row(dec, str(c))
    console.print(table2)

    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-sbert", action="store_true",
                    help="debug: salta SBERT (la métrica queda en 0)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    raise SystemExit(run(skip_sbert=args.skip_sbert, use_cache=not args.no_cache))


if __name__ == "__main__":
    main()
