"""Fase 3 — Scoring híbrido: keyword + TF-IDF + Sentence-BERT.

Combina las 3 señales en un score raw [0,1], mapea a 1-5 por percentiles,
aplica filtro temporal y produce la justificación textual.

Salidas en s3://examen-parcial-silver-g3/:
- silver.parquet           (todo el corpus con score, decisión, justificación)
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
        BUCKET, KEY_BRONZE_INDEX, KEY_SILVER_METADATA,
        KEY_SILVER_FINAL, KEY_SILVER_EMBEDDINGS,
        OUTPUTS, SBERT_MODEL,
        SCORE_BUCKETS, SECTION_WEIGHTS,
        W_KEYWORD, W_TFIDF, W_SBERT,
        YEAR_MIN, YEAR_MAX,
    )
    from classifier.search_query import (
        ALL_KEYWORDS, KEYWORDS_BY_AXIS, query_as_natural_text,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from classifier.src.config import (
        BUCKET, KEY_BRONZE_INDEX, KEY_SILVER_METADATA,
        KEY_SILVER_FINAL, KEY_SILVER_EMBEDDINGS,
        OUTPUTS, SBERT_MODEL,
        SCORE_BUCKETS, SECTION_WEIGHTS,
        W_KEYWORD, W_TFIDF, W_SBERT,
        YEAR_MIN, YEAR_MAX,
    )
    from classifier.search_query import (
        ALL_KEYWORDS, KEYWORDS_BY_AXIS, query_as_natural_text,
    )

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from classifier.src._minio_client import minio  # noqa: E402

console = Console()


# ─────────────────────────────────────────────────────────────── #
# Cargar bronze + silver_metadata y joinarlos                    #
# ─────────────────────────────────────────────────────────────── #
def load_inputs() -> pl.DataFrame:
    s3 = minio()
    # bronze
    buf = io.BytesIO()
    s3.download_fileobj(BUCKET, KEY_BRONZE_INDEX, buf)
    buf.seek(0)
    bronze = pl.read_parquet(buf)

    # silver metadata
    buf = io.BytesIO()
    s3.download_fileobj(BUCKET, KEY_SILVER_METADATA, buf)
    buf.seek(0)
    meta = pl.read_parquet(buf)

    cols_bronze = ["code", "original_filename", "year_from_arxiv",
                   "topic_tag_local", "title_from_filename", "size_bytes"]
    df = bronze.select(cols_bronze).join(meta, on="code", how="left")

    # Año final con prioridad: extracted (high) > arxiv > extracted (medium/low)
    df = df.with_columns(
        pl.when(pl.col("year_confidence") == "high")
          .then(pl.col("year_extracted"))
          .when(pl.col("year_from_arxiv").is_not_null())
          .then(pl.col("year_from_arxiv"))
          .otherwise(pl.col("year_extracted"))
          .alias("year")
    )

    # Título final: prioridad al extraído del PDF, fallback al del filename
    df = df.with_columns(
        pl.coalesce(["title_extracted", "title_from_filename"]).alias("title")
    )
    return df


# ─────────────────────────────────────────────────────────────── #
# Capa 1 — Keyword score                                         #
# ─────────────────────────────────────────────────────────────── #
def normalize_text(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[\s\-_/]+", " ", s)
    s = re.sub(r"[^\w\s.+]", " ", s)
    return s


def keyword_score_row(title: str | None, abstract: str | None,
                      keywords: list[str] | None,
                      topic_tag: str | None) -> tuple[float, list[str], dict]:
    t = normalize_text(title)
    a = normalize_text(abstract)
    kw_text = normalize_text(" ".join(keywords or []))
    topic = normalize_text(topic_tag)

    matched: dict[str, list[str]] = {axis: [] for axis in KEYWORDS_BY_AXIS}
    score = 0.0
    for axis, kws in KEYWORDS_BY_AXIS.items():
        for kw in kws:
            kw_n = normalize_text(kw)
            in_title = kw_n in t
            in_abstract = kw_n in a
            in_kw = kw_n in kw_text
            if in_title:
                score += SECTION_WEIGHTS["title"]
            if in_abstract:
                score += SECTION_WEIGHTS["abstract"]
            if in_kw:
                score += SECTION_WEIGHTS["keywords"]
            if in_title or in_abstract or in_kw:
                matched[axis].append(kw)

    # Bonus por cubrir múltiples ejes
    axes_hit = sum(1 for v in matched.values() if v)
    score *= (1.0 + 0.15 * (axes_hit - 1))  # 1 eje =1.0, 2 =1.15, 3 =1.30, 4 =1.45

    # Bonus pequeño si el topic-tag local menciona algo del set
    topic_bonus = any(part in topic for part in ("cyber", "security", "zero", "trust",
                                                  "ia", "ai", "ml", "ml-", "deep"))
    if topic_bonus:
        score *= 1.05

    matched_flat = sorted({kw for v in matched.values() for kw in v})
    return score, matched_flat, matched


# ─────────────────────────────────────────────────────────────── #
# Capa 2 — TF-IDF cosine                                         #
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
    sims = cosine_similarity(q, X).ravel()
    return sims


# ─────────────────────────────────────────────────────────────── #
# Capa 3 — Sentence-BERT cosine (con cache + ONNX int8)          #
# ─────────────────────────────────────────────────────────────── #
SBERT_BATCH_SIZE = 128                  # (B) era 32

# Variantes ONNX cuantizadas (en orden de preferencia por hardware típico)
ONNX_VARIANTS = [
    "onnx/model_qint8_avx512_vnni.onnx",   # Intel/AMD Zen3+ con VNNI (mejor)
    "onnx/model_qint8_avx512.onnx",        # Intel/AMD con AVX-512
    "onnx/model_quint8_avx2.onnx",         # x86 con AVX2 (default seguro)
    "onnx/model_qint8_arm64.onnx",         # Apple Silicon / ARM
]


def _load_sbert_model():
    """Carga SBERT con backend ONNX int8 si está disponible; fallback a PyTorch."""
    # Tunear PyTorch threads (importa incluso con backend ONNX para preprocessing)
    try:
        import os as _os
        import torch
        n_threads = min(_os.cpu_count() or 4, 4)
        torch.set_num_threads(n_threads)
        torch.set_num_interop_threads(max(1, n_threads // 2))
    except Exception:
        pass

    from sentence_transformers import SentenceTransformer

    # Intentar cada variante ONNX en orden hasta encontrar una que funcione
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

    # Default ONNX (no cuantizado)
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

    # Cache hit
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

    # Query embedding (mismo modelo si ya cargado)
    if model is None:
        model = _load_sbert_model()
    query_emb = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
    sims = (corpus_emb @ query_emb.T).ravel()
    return sims


# ─────────────────────────────────────────────────────────────── #
# Combinar + mapear a 1-5                                        #
# ─────────────────────────────────────────────────────────────── #
def minmax(x: np.ndarray) -> np.ndarray:
    a, b = x.min(), x.max()
    return (x - a) / (b - a) if b > a else np.zeros_like(x)


def percentile_buckets(raw: np.ndarray) -> np.ndarray:
    """Mapea valores a buckets 1-5 según SCORE_BUCKETS."""
    out = np.ones_like(raw, dtype=int)
    for thresh_p, bucket in SCORE_BUCKETS:
        cutoff = np.quantile(raw, thresh_p)
        out = np.where((raw >= cutoff) & (out < bucket), bucket, out)
    return out


def decision_for(score: int, year: int | None) -> str:
    in_range = (year is not None) and (YEAR_MIN <= year <= YEAR_MAX)
    if score >= 4 and in_range:
        return "Gold — muy relacionado" if score == 5 else "Gold — claramente relacionado"
    if score >= 4 and not in_range:
        return "Fuera del rango temporal"
    if score == 3:
        return "Revisar (parcial)"
    if score == 2:
        return "No prioritario"
    return "Excluido"


# ─────────────────────────────────────────────────────────────── #
# Driver                                                         #
# ─────────────────────────────────────────────────────────────── #
def run(skip_sbert: bool = False, use_cache: bool = True) -> int:
    console.rule("[bold]Fase 3 — Scoring híbrido[/bold]")
    df = load_inputs()
    n = df.height
    console.print(f"Papers a scorear: [bold]{n}[/bold]")

    # Texto del corpus para TF-IDF y SBERT
    df = df.with_columns(
        pl.concat_str([
            pl.col("title").fill_null(""),
            pl.lit(". "),
            pl.col("abstract").fill_null(""),
        ]).alias("text_for_score")
    )
    corpus_text = df["text_for_score"].to_list()
    codes = df["code"].to_list()

    # ── Capa 1 ── #
    started = time.perf_counter()
    kw_scores, matched_lists, matched_dicts = [], [], []
    with Progress(SpinnerColumn(), TextColumn("[bold]Keyword score[/bold]"),
                   BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
                   console=console) as progress:
        task = progress.add_task("kw", total=n)
        for row in df.iter_rows(named=True):
            s, matched, mdict = keyword_score_row(
                row["title"], row["abstract"],
                row["keywords_extracted"], row["topic_tag_local"],
            )
            kw_scores.append(s); matched_lists.append(matched); matched_dicts.append(mdict)
            progress.advance(task)
    kw_arr = np.array(kw_scores)
    console.print(f"[dim]keyword in {time.perf_counter()-started:.1f}s[/dim]")

    # ── Capa 2 ── #
    started = time.perf_counter()
    tfidf_arr = tfidf_scores(corpus_text, query_as_natural_text())
    console.print(f"[dim]tfidf in {time.perf_counter()-started:.1f}s[/dim]")

    # ── Capa 3 ── #
    if skip_sbert:
        sbert_arr = np.zeros(n)
        console.print("[yellow]SBERT saltado por --skip-sbert[/yellow]")
    else:
        started = time.perf_counter()
        sbert_arr = sbert_scores(corpus_text, query_as_natural_text(), codes, use_cache)
        console.print(f"[dim]sbert in {time.perf_counter()-started:.1f}s[/dim]")
        # Subir cache a MinIO
        s3 = minio()
        cache_local = OUTPUTS / "embeddings.npy"
        if cache_local.exists():
            s3.upload_file(str(cache_local), BUCKET, KEY_SILVER_EMBEDDINGS)

    # Normalización min-max y combinación
    kw_n = minmax(kw_arr)
    tfidf_n = minmax(tfidf_arr)
    sbert_n = minmax(sbert_arr) if not skip_sbert else np.zeros(n)

    if skip_sbert:
        raw = 0.55 * kw_n + 0.45 * tfidf_n
    else:
        raw = W_KEYWORD * kw_n + W_TFIDF * tfidf_n + W_SBERT * sbert_n

    scores = percentile_buckets(raw)

    # Justificación textual
    just = []
    for i in range(n):
        parts = []
        if matched_lists[i]:
            parts.append(f"kws: {', '.join(matched_lists[i][:6])}")
        parts.append(f"tfidf={tfidf_arr[i]:.3f}")
        if not skip_sbert:
            parts.append(f"sbert={sbert_arr[i]:.3f}")
        parts.append(f"raw={raw[i]:.3f}")
        just.append(" · ".join(parts))

    years = df["year"].to_list()
    decisions = [decision_for(s, y) for s, y in zip(scores.tolist(), years)]

    df = df.with_columns(
        pl.Series("keyword_raw", kw_arr),
        pl.Series("tfidf_cosine", tfidf_arr),
        pl.Series("sbert_cosine", sbert_arr),
        pl.Series("score_raw", raw),
        pl.Series("score", scores),
        pl.Series("keywords_matched", matched_lists),
        pl.Series("justificacion", just),
        pl.Series("decision", decisions),
        pl.col("year").map_elements(
            lambda y: (y is not None) and YEAR_MIN <= y <= YEAR_MAX,
            return_dtype=pl.Boolean,
        ).alias("en_rango_temporal"),
    )

    # Persistir silver final
    out_local = OUTPUTS / "silver.parquet"
    df.write_parquet(out_local)
    s3 = minio()
    s3.upload_file(str(out_local), BUCKET, KEY_SILVER_FINAL)
    console.print(f"\n[green]✓ silver[/green] → s3://{BUCKET}/{KEY_SILVER_FINAL}")

    # Distribución score / decisión
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Score"); table.add_column("Conteo", justify="right")
    for s in [5, 4, 3, 2, 1]:
        c = (df["score"] == s).sum()
        table.add_row(str(s), str(c))
    console.print(table)

    table2 = Table(show_header=True, header_style="bold cyan")
    table2.add_column("Decisión"); table2.add_column("Conteo", justify="right")
    for dec, c in df.group_by("decision").agg(pl.len().alias("c")).sort("c", descending=True).iter_rows():
        table2.add_row(dec, str(c))
    console.print(table2)

    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-sbert", action="store_true", help="debug: salta SBERT")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    raise SystemExit(run(skip_sbert=args.skip_sbert, use_cache=not args.no_cache))


if __name__ == "__main__":
    main()
