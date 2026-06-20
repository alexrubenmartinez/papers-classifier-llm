FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/root/.cache/huggingface \
    TRANSFORMERS_OFFLINE=0 \
    TOKENIZERS_PARALLELISM=false

COPY requirements.txt .
# torch CPU-only para no descargar las wheels CUDA (mucho mas grande).
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# Pre-download del modelo SBERT al build para que el primer startup sea rapido.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
