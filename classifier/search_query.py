"""Cadena de búsqueda Grupo 3 — Security Data Lakehouse + Apache Iceberg + IA / threat detection.

La lista plana `KEYWORDS_FLAT` define el universo de términos contra los que se mide
cada paper: `score = #keywords distintas que aparecen en title ∪ keywords ∪ abstract`.
"""

SEARCH_QUERY = (
    'TITLE-ABS-KEY ('
    '("data lakehouse" OR "Apache Iceberg" OR "open table format" OR "object storage") AND '
    '("cybersecurity" OR "threat detection" OR "security logs" OR "SIEM" OR "telemetry data") AND '
    '("machine learning" OR "artificial intelligence" OR "offline training" OR "feature store" OR "predictive models") AND '
    '("big data" OR "data pipeline" OR "scalability" OR "query performance" OR "data retention" OR '
    '"schema evolution" OR "historical data" OR "time-travel query")'
    ')'
)


# Lista plana — orden de definición conservado para que el reporte muestre los grupos
# en el orden semántico que tipeó el usuario, aunque la decisión use la lista entera.
KEYWORDS_FLAT: list[str] = [
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


# Alias retrocompatible.
ALL_KEYWORDS: list[str] = list(KEYWORDS_FLAT)


def query_as_natural_text() -> str:
    """Versión en texto natural para alimentar TF-IDF / Sentence-BERT.

    Las búsquedas booleanas confunden a los embeddings; mejor pasar la
    intención como un párrafo descriptivo.
    """
    return (
        "Security data lakehouse based on Apache Iceberg and open table formats over "
        "object storage. Offline training of machine learning and artificial intelligence "
        "predictive models using a feature store fed from cybersecurity threat detection, "
        "SIEM, security logs and telemetry data. Big data pipelines with horizontal "
        "scalability, strong query performance, data retention, schema evolution, historical "
        "data analysis and time-travel queries."
    )
