"""Pipeline real: extraer metadata de PDF, embed SBERT, scoring hibrido vs query.

Score hibrido = keyword(0.40) + tfidf(0.30) + sbert_cosine(0.30) [pesos default; configurable].

El TF-IDF vectorizer se fitea sobre TODO el corpus (papers en Mongo). Para uploads
individuales, si todavia no hay vectorizer fiteado (primer paper), TF-IDF cae a 0.5
neutral. El reclassify_all refitea y aplica TF-IDF real a todos los papers.
"""
from __future__ import annotations

import re
from typing import Any

import fitz  # PyMuPDF
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_model: SentenceTransformer | None = None
_vectorizer: TfidfVectorizer | None = None

# Patrones que descartan una linea como candidata a titulo.
_TITLE_BAD_PREFIXES = (
    "arxiv:", "doi:", "issn", "isbn", "vol.", "volume ",
    "ieee", "acm transactions", "journal of",
    "page ", "https://", "http://", "www.",
    "copyright", "©", "downloaded", "received",
    "accepted", "published",
)
_TITLE_BAD_RE = re.compile(
    r"^(arxiv:|doi:|page\s+\d|https?://|www\.|received\s+\d)",
    re.IGNORECASE,
)


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model


def embed_text(text: str) -> list[float]:
    model = get_model()
    vec = model.encode([text or " "], normalize_embeddings=True)[0]
    return vec.tolist()


def fit_vectorizer(corpus: list[str]) -> None:
    global _vectorizer
    corpus = [t for t in corpus if t and t.strip()]
    if len(corpus) < 2:
        _vectorizer = None
        return
    _vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        max_df=0.95,
        min_df=1,
        stop_words="english",
        max_features=20000,
    )
    _vectorizer.fit(corpus)


def has_vectorizer() -> bool:
    return _vectorizer is not None


def _looks_like_title(line: str) -> bool:
    """Heuristica: una linea es candidato a titulo si tiene 25-300 chars, mezcla
    mayusculas/minusculas, no es solo numeros/citaciones, y no empieza con marcadores
    de header tipo arXiv/DOI/journal."""
    s = line.strip()
    if not (25 <= len(s) <= 300):
        return False
    if _TITLE_BAD_RE.match(s):
        return False
    if any(s.lower().startswith(p) for p in _TITLE_BAD_PREFIXES):
        return False
    # Debe tener al menos una letra minuscula y una palabra de >3 chars.
    if not re.search(r"[a-z]", s):
        return False
    words = [w for w in re.split(r"\s+", s) if len(w) > 3]
    if len(words) < 3:
        return False
    return True


_TITLE_END_RE = re.compile(
    r"^(abstract|introduction|keywords|index terms|1\.\s|i\.\s|chapter\s|"
    r"author|contents|table of contents|copyright|received|accepted|published|"
    r"published online|email|e-mail|@|school of|department of|"
    r"university of|institute of|faculty of|laboratory|"
    r"\d+\s*$)",  # numero solo (page number / footnote)
    re.IGNORECASE,
)

# Marcadores que indican "ya entramos al bloque de autores" — cortar el titulo aca.
_TITLE_INLINE_AUTHOR_RE = re.compile(
    r"(@[\w.-]+\.[a-z]{2,}|\bschool of\b|\bdepartment of\b|\buniversity of\b|"
    r"\binstitute of\b|\bfaculty of\b|\blaboratory\b)",
    re.IGNORECASE,
)


def _pick_title(metadata_title: str, full_text: str) -> str:
    """Devuelve el mejor candidato a titulo.

    Heuristica:
    1. Metadata title si pasa la check de `_looks_like_title`.
    2. Concatena lineas consecutivas a partir de la primera que parece titulo
       hasta encontrar abstract / autor / linea vacia / linea demasiado larga.
       Esto resuelve papers donde el titulo viene partido en 2-3 lineas.
    3. Fallback: primera linea no vacia.
    """
    if metadata_title and _looks_like_title(metadata_title):
        return metadata_title.strip()

    lines = full_text.split("\n")
    parts: list[str] = []
    started = False

    for raw in lines:
        s = raw.strip()
        if not started:
            if _looks_like_title(s):
                parts.append(s)
                started = True
                if len(s) >= 120:
                    break
            continue
        # Ya empezamos: decidir si esta linea continua o termina el titulo.
        if not s:
            break
        if _TITLE_END_RE.match(s):
            break
        if _TITLE_BAD_RE.match(s):
            break
        if any(s.lower().startswith(p) for p in _TITLE_BAD_PREFIXES):
            break
        if len(s) > 250:
            # Linea muy larga: ya entramos al cuerpo del paper.
            break
        # Mantener si parece continuacion (sin signo de cierre fuerte en el anterior).
        last = parts[-1]
        if last.endswith(".") or last.endswith("!") or last.endswith("?"):
            break
        parts.append(s)
        if sum(len(p) for p in parts) > 250:
            break

    if parts:
        title = " ".join(parts)
        # Cortar inline si una linea contiene email o marker academico (autor/institucion).
        m = _TITLE_INLINE_AUTHOR_RE.search(title)
        if m:
            title = title[: m.start()].rstrip(" -–—,·*⋆")
        return title[:300]

    for raw in lines:
        s = raw.strip()
        if s:
            return s[:200]
    return "(sin titulo)"


def extract_metadata(pdf_bytes: bytes) -> dict[str, Any]:
    """Extrae title, abstract, year, text de las primeras 3 paginas."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        return {
            "title": "(unparseable)",
            "abstract": "",
            "year": 2024,
            "text": "",
            "parse_error": str(exc)[:200],
        }

    metadata_title = (doc.metadata.get("title") or "").strip()
    full_text = ""
    for page in doc[:3]:
        full_text += page.get_text() + "\n"
    doc.close()

    title = _pick_title(metadata_title, full_text)

    abstract = ""
    m = re.search(
        r"(?i)abstract[\s:.\n]+(.+?)(?:\n\s*\n|introduction|keywords|index terms|1\.\s|i\.\s)",
        full_text,
        re.DOTALL,
    )
    if m:
        abstract = re.sub(r"\s+", " ", m.group(1)).strip()[:2000]

    # Year: prioriza el año mayor encontrado en las primeras 3000 chars.
    years = re.findall(r"\b(19[9]\d|20[0-2]\d|203\d)\b", full_text[:3000])
    year = int(max(years)) if years else 2024

    return {
        "title": title,
        "abstract": abstract,
        "year": year,
        "text": f"{title} {abstract}".strip(),
    }


def _kw_matches(text_lower: str, kw: str) -> bool:
    """Match con word-boundary para keywords de una palabra; substring para multi-word.

    Asi 'AI' matchea 'AI-driven' o 'AI threat' pero NO 'PAIN' o 'AIRPORT'.
    'zero trust' como multi-word usa substring (matchea 'zero trust architecture').
    """
    kw_lower = kw.lower().strip()
    if not kw_lower:
        return False
    if " " in kw_lower or "-" in kw_lower:
        return kw_lower in text_lower
    return re.search(rf"\b{re.escape(kw_lower)}\b", text_lower) is not None


def keyword_score(text: str, axes: dict[str, list[str]]) -> float:
    """Cobertura de ejes tematicos (0-1). Cuanta proporcion de ejes tienen al menos 1 match."""
    if not text or not axes:
        return 0.0
    text_lower = text.lower()
    matched_axes = sum(
        1 for kws in axes.values() if any(_kw_matches(text_lower, kw) for kw in kws)
    )
    return matched_axes / len(axes)


def tfidf_score(paper_text: str, query_text: str) -> float:
    if _vectorizer is None or not paper_text or not query_text:
        return 0.5
    p = _vectorizer.transform([paper_text])
    q = _vectorizer.transform([query_text])
    return float(cosine_similarity(p, q)[0][0])


def sbert_score(paper_emb: list[float] | None, query_emb: list[float] | None) -> float:
    if not paper_emb or not query_emb:
        return 0.5
    a = np.asarray(paper_emb, dtype=np.float32)
    b = np.asarray(query_emb, dtype=np.float32)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.5
    cos = float(a @ b / denom)
    return (cos + 1.0) / 2.0


def compute_score(
    text: str,
    paper_emb: list[float] | None,
    axes: dict[str, list[str]],
    query_text: str,
    query_emb: list[float] | None,
    weights: dict[str, float],
) -> dict[str, float]:
    kw = keyword_score(text, axes)
    tf = tfidf_score(text, query_text)
    sb = sbert_score(paper_emb, query_emb)
    w = weights
    weighted = kw * w.get("keyword", 0.4) + tf * w.get("tfidf", 0.3) + sb * w.get("sbert", 0.3)
    return {
        "keyword": round(kw, 4),
        "tfidf": round(tf, 4),
        "sbert": round(sb, 4),
        "weighted": round(weighted, 4),
    }


# Default thresholds (uso si el config no define `thresholds`).
DEFAULT_THRESHOLDS = {
    "gold_muy": 0.65,
    "gold_claro": 0.50,
    "revisar": 0.35,
    "no_prioritario": 0.20,
}


def score_to_decision(
    weighted: float,
    year: int,
    year_range: list[int],
    thresholds: dict[str, float] | None = None,
) -> tuple[int, str]:
    if year < year_range[0] or year > year_range[1]:
        return 0, "Fuera del rango temporal"
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    if weighted >= t["gold_muy"]:
        return 5, "Gold — muy relacionado"
    if weighted >= t["gold_claro"]:
        return 4, "Gold — claramente relacionado"
    if weighted >= t["revisar"]:
        return 3, "Revisar (parcial)"
    if weighted >= t["no_prioritario"]:
        return 2, "No prioritario"
    return 1, "Excluido"
