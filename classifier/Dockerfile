# Container del clasificador Grupo 3 — Ciberseguridad / Zero Trust + IA
# Corre en el VPS sobre la red Docker `web` para alcanzar minio sin tunnel.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/work/.cache/huggingface \
    TRANSFORMERS_CACHE=/work/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/work/.cache/sentence-transformers

# Deps de sistema mínimas (curl para healthcheck, libgomp1 para sklearn/torch)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

# 1) Torch CPU-only primero — ahorra ~2 GB vs la rueda con CUDA
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
    torch==2.4.0+cpu

# 2) Resto de deps desde requirements.txt
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# 3) Código del clasificador — el package vive en /work/classifier/
#    así `python -m classifier.src.pipeline` funciona dentro del container.
COPY __init__.py /work/classifier/__init__.py
COPY src /work/classifier/src
COPY search_query.py /work/classifier/search_query.py
COPY score_rubric.md /work/classifier/score_rubric.md

ENV PYTHONPATH=/work

# Pre-bajar el modelo SBERT en variantes PyTorch + ONNX cuantizadas
# Esto evita descargar 80-200MB en runtime y permite que el clasificador
# use ONNX int8 (3-5x más rápido en CPU que PyTorch float32).
RUN python - <<'PY'
from sentence_transformers import SentenceTransformer
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# 1) PyTorch (fallback)
SentenceTransformer(MODEL)
# 2) ONNX cuantizado — probar las variantes en orden de preferencia
for variant in [
    "onnx/model_qint8_avx512_vnni.onnx",
    "onnx/model_qint8_avx512.onnx",
    "onnx/model_quint8_avx2.onnx",
]:
    try:
        SentenceTransformer(MODEL, backend="onnx", model_kwargs={"file_name": variant})
        print(f"pre-cached ONNX variant: {variant}")
    except Exception as e:
        print(f"skip {variant}: {e}")
PY

# Default: queda vivo para que el operador ejecute fases con `docker exec`
# (más amigable para capturas de pantalla del proceso real)
CMD ["sleep", "infinity"]
