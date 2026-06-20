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

# Silver: el .parquet es el formato interno del pipeline (lee/escribe entre fases);
# el CSV es el formato primario para el operador, el XLSX queda como vista humana
# opcional para abrir directo desde MinIO UI.
KEY_SILVER_PAPERS_PREFIX = f"{PFX_SILVER}/papers/"      # copia 1-a-1 de bronze
KEY_SILVER_METADATA = f"{PFX_SILVER}/metadata.parquet"
KEY_SILVER_FINAL = f"{PFX_SILVER}/silver.parquet"
KEY_SILVER_CSV = f"{PFX_SILVER}/silver.csv"
KEY_SILVER_XLSX = f"{PFX_SILVER}/silver.xlsx"
KEY_SILVER_EMBEDDINGS = f"{PFX_SILVER}/embeddings.npy"

KEY_GOLD_PAPERS_PREFIX = f"{PFX_GOLD}/papers/"          # solo papers con score ≥ threshold
KEY_GOLD_PARQUET = f"{PFX_GOLD}/gold.parquet"
KEY_GOLD_CSV = f"{PFX_GOLD}/gold.csv"
KEY_GOLD_XLSX = f"{PFX_GOLD}/gold.xlsx"
KEY_GOLD_RANKING_CSV = f"{PFX_GOLD}/ranking.csv"
KEY_GOLD_RANKING_XLSX = f"{PFX_GOLD}/ranking.xlsx"

KEY_REPORT_MD = f"{PFX_REPORTS}/report.md"


# ───── Regla de tier (única regla que decide Gold) ───── #
# El score de cada paper es el conteo de keywords distintas de KEYWORDS_FLAT que
# aparecen en title ∪ keywords ∪ abstract. ≥ threshold ⇒ Gold.
GOLD_KEYWORD_THRESHOLD = 5


# ───── Filtro temporal (se aplica además del threshold) ───── #
YEAR_MIN = 2016
YEAR_MAX = 2026


# ───── Métricas auxiliares (informativas, NO deciden tier) ───── #
# TF-IDF y SBERT siguen calculándose y persistiéndose en silver.parquet/csv
# como columnas para análisis posterior. Los pesos quedan documentados pero
# no entran en la fórmula del score.
W_KEYWORD = 1.0
W_TFIDF = 0.0
W_SBERT = 0.0


# ───── Upload paralelo ───── #
UPLOAD_WORKERS = 24
UPLOAD_MULTIPART_THRESHOLD = 64 * 1024 * 1024

# Server-side copy paralelo (build_silver / build_gold).
COPY_WORKERS = 16


# ───── Modelo SBERT ───── #
SBERT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


# ───── Paginación de extracción ───── #
PDF_BODY_MAX_PAGES = 3
