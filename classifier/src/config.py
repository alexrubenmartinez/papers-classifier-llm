"""Configuración del clasificador — bucket único + prefijos por grupo."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = CLASSIFIER_ROOT / "outputs"
OUTPUTS.mkdir(parents=True, exist_ok=True)


# ───── Source local ───── #
ARTICULOS_DIR = ROOT / "Articulos"


# ───── Bucket único MinIO ───── #
BUCKET = os.environ.get("BUCKET", "examen-parcial")

# Prefijo del grupo dentro del bucket. Permite que cada grupo viva sin colisionar.
GROUP_PREFIX = os.environ.get("GROUP_PREFIX", "grupo3_ciberseguridad")

# Subprefijos por capa
PFX_BRONZE = f"{GROUP_PREFIX}/bronze"
PFX_SILVER = f"{GROUP_PREFIX}/silver"
PFX_GOLD = f"{GROUP_PREFIX}/gold"
PFX_REPORTS = f"{GROUP_PREFIX}/reports"


# ───── Llaves concretas ───── #
KEY_BRONZE_PAPERS_PREFIX = f"{PFX_BRONZE}/papers/"      # papers/PAPER_NNNN.pdf
KEY_BRONZE_INDEX = f"{PFX_BRONZE}/index.parquet"
KEY_BRONZE_CONTROL_XLSX = f"{PFX_BRONZE}/bronze_control.xlsx"

KEY_SILVER_METADATA = f"{PFX_SILVER}/metadata.parquet"
KEY_SILVER_FINAL = f"{PFX_SILVER}/silver.parquet"
KEY_SILVER_XLSX = f"{PFX_SILVER}/silver.xlsx"
KEY_SILVER_EMBEDDINGS = f"{PFX_SILVER}/embeddings.npy"

KEY_GOLD_PARQUET = f"{PFX_GOLD}/gold.parquet"
KEY_GOLD_XLSX = f"{PFX_GOLD}/gold.xlsx"
KEY_GOLD_RANKING_XLSX = f"{PFX_GOLD}/ranking.xlsx"

KEY_REPORT_MD = f"{PFX_REPORTS}/report.md"


# ───── Scoring weights ───── #
W_KEYWORD = 0.40
W_TFIDF = 0.30
W_SBERT = 0.30

SECTION_WEIGHTS = {
    "title": 3.0,
    "abstract": 2.0,
    "keywords": 1.5,
    "body": 0.5,
}

SCORE_BUCKETS = [
    (0.90, 5),
    (0.70, 4),
    (0.40, 3),
    (0.15, 2),
    (0.00, 1),
]


# ───── Filtro temporal ───── #
YEAR_MIN = 2016
YEAR_MAX = 2026


# ───── Upload paralelo ───── #
UPLOAD_WORKERS = 24
UPLOAD_MULTIPART_THRESHOLD = 64 * 1024 * 1024


# ───── Modelo SBERT ───── #
SBERT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


# ───── Paginación de extracción ───── #
PDF_BODY_MAX_PAGES = 3
