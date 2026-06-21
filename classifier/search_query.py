"""Cadena de búsqueda — keywords del tema activo.

Las keywords se leen DINAMICAMENTE desde `http://examen-api:8000/config` al
primer uso. Si la API no responde (offline, smoke tests locales) cae a la
lista hardcoded de Iceberg como fallback. La regla de scoring sigue siendo
`score = #keywords distintas que aparecen en title ∪ keywords ∪ abstract`.

El fetch se cachea durante el proceso. Cualquier worker que necesite refrescar
(p.ej. tras un PUT /config) tiene que reiniciar el container — pero como el
container es one-shot (`pipeline run`), cada run arranca con la última config.
"""
from __future__ import annotations

import os
import sys

# Default estatico — usado si la API no responde.
_FALLBACK_KEYWORDS: list[str] = [
    "data lakehouse",
    "apache iceberg",
    "open table format",
    "object storage",
    "cybersecurity",
    "threat detection",
    "security logs",
    "siem",
    "telemetry data",
    "machine learning",
    "artificial intelligence",
    "offline training",
    "feature store",
    "predictive models",
    "big data",
    "data pipeline",
    "scalability",
    "query performance",
    "data retention",
    "schema evolution",
    "historical data",
    "time-travel query",
]

_FALLBACK_TOPIC = (
    "Security data lakehouse based on Apache Iceberg and open table formats over "
    "object storage. Offline training of machine learning and artificial intelligence "
    "predictive models using a feature store fed from cybersecurity threat detection, "
    "SIEM, security logs and telemetry data. Big data pipelines with horizontal "
    "scalability, strong query performance, data retention, schema evolution, historical "
    "data analysis and time-travel queries."
)


_API_URL = os.environ.get("CLASSIFIER_API_URL", "http://examen-api:8000")
_API_TIMEOUT_SECONDS = float(os.environ.get("CLASSIFIER_API_TIMEOUT", "5"))

# Cache por proceso. Se setea en la primera lectura.
_cache_keywords: list[str] | None = None
_cache_query: str | None = None
_cache_topic: str | None = None


def _fetch_config_once() -> None:
    """Hace UN solo GET al API y popula los caches. Silencioso si falla."""
    global _cache_keywords, _cache_query, _cache_topic
    if _cache_keywords is not None:
        return
    try:
        import urllib.request
        import json
        url = f"{_API_URL.rstrip('/')}/config"
        with urllib.request.urlopen(url, timeout=_API_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        axes = data.get("axes") or {}
        flat: list[str] = []
        seen: set[str] = set()
        for kws in axes.values():
            for kw in (kws or []):
                norm = (kw or "").strip()
                key = norm.lower()
                if norm and key not in seen:
                    seen.add(key)
                    flat.append(norm)
        if not flat:
            raise RuntimeError("axes vacios en /config")
        _cache_keywords = flat
        _cache_topic = data.get("topic_name") or _FALLBACK_TOPIC
        _cache_query = data.get("query_text") or _cache_topic or _FALLBACK_TOPIC
        print(
            f"[search_query] keywords cargadas desde {url}: "
            f"{len(flat)} keywords, topic={_cache_topic!r}",
            file=sys.stderr,
        )
    except Exception as exc:
        _cache_keywords = list(_FALLBACK_KEYWORDS)
        _cache_topic = _FALLBACK_TOPIC
        _cache_query = _FALLBACK_TOPIC
        print(
            f"[search_query] fallback a lista estatica ({len(_cache_keywords)} kws). "
            f"Razon: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


class _DynamicKeywordList(list):
    """List proxy que carga las keywords la primera vez que se accede."""

    def _hydrate(self) -> list[str]:
        _fetch_config_once()
        assert _cache_keywords is not None
        # Refrescar el contenido del propio objeto para que `iter(KEYWORDS_FLAT)`
        # tambien refleje el nuevo estado.
        if list.__len__(self) == 0:
            list.extend(self, _cache_keywords)
        return _cache_keywords

    def __iter__(self):
        self._hydrate()
        return list.__iter__(self)

    def __len__(self):
        self._hydrate()
        return list.__len__(self)

    def __getitem__(self, index):
        self._hydrate()
        return list.__getitem__(self, index)

    def __contains__(self, item):
        self._hydrate()
        return list.__contains__(self, item)

    def __repr__(self):
        self._hydrate()
        return list.__repr__(self)


KEYWORDS_FLAT: list[str] = _DynamicKeywordList()
ALL_KEYWORDS: list[str] = KEYWORDS_FLAT


def query_as_natural_text() -> str:
    """Texto natural para TF-IDF / SBERT — viene del topic_name + query_text del API."""
    _fetch_config_once()
    return _cache_query or _FALLBACK_TOPIC


# SEARCH_QUERY se mantiene como string informativa para reportes. Refleja la
# version estatica de Iceberg porque generar booleanos dinamicos no aporta valor.
SEARCH_QUERY = (
    'TITLE-ABS-KEY ('
    '("data lakehouse" OR "Apache Iceberg" OR "open table format" OR "object storage") AND '
    '("cybersecurity" OR "threat detection" OR "security logs" OR "SIEM" OR "telemetry data") AND '
    '("machine learning" OR "artificial intelligence" OR "offline training" OR "feature store" OR "predictive models") AND '
    '("big data" OR "data pipeline" OR "scalability" OR "query performance" OR "data retention" OR '
    '"schema evolution" OR "historical data" OR "time-travel query")'
    ')'
)
