# papers-classifier — pipeline Bronze / Silver / Gold

Clasificador de artículos científicos para selección automática de papers relevantes a una tesis. Implementa una arquitectura **data lakehouse en MinIO** con scoring híbrido **keyword + TF-IDF + Sentence-BERT (ONNX int8)**. Diseñado para correr **dentro de un container Docker en el VPS**, conectado a la red del stack del curso.

Caso de uso de referencia: clasificación de 2000 PDFs para la tesis del Grupo 3 — *"Diseño e implementación de una arquitectura Zero Trust potenciada con IA para detección temprana de amenazas en entornos cloud híbridos"* (Bases de Datos Avanzadas y Big Data, UNMSM 2026-I).

## Resultado en producción

| Métrica | Valor |
|---|---|
| Corpus | 2000 PDFs (3.5 GB) |
| Pipeline cold-cache en VPS | **127 s** (2 m 07 s) |
| Pipeline con cache de embeddings | **62 s** (1 m 02 s) |
| Throughput extract | 56-60 papers/s (8 cores) |
| Papers Gold | 588 (199 score 5 + 389 score 4) |
| Top-10 on-topic Zero Trust + AI + Cloud | 10/10 |

Sin pérdida de calidad respecto a la versión PyTorch float32 — los embeddings cuantizados int8 dan diferencias <1% en cosine similarity.

## Arquitectura

```
local Mac / laptop                        VPS (red docker stack_web)
─────────────────                         ───────────────────────────
classifier/src/upload_bronze   ──── SSH ─→  MinIO (examen-parcial)
                                                │
                                                ├── grupo3_ciberseguridad/bronze/papers/*.pdf
                                                ├── grupo3_ciberseguridad/bronze/index.parquet
                                                │
container classifier-g3 (corre dentro VPS)      │
  ├── extract_metadata    (PyMuPDF + ProcessPool 8w + early-exit)
  ├── score               (kw matching + TF-IDF + SBERT ONNX int8)
  ├── build_silver / gold (parquet + xlsx)
  ├── ranking             (xlsx ordenado)
  └── reporter            (markdown)
                                                │
                                                ├── grupo3_ciberseguridad/silver/{metadata,silver}.parquet
                                                ├── grupo3_ciberseguridad/silver/silver.xlsx
                                                ├── grupo3_ciberseguridad/silver/embeddings.npy
                                                ├── grupo3_ciberseguridad/gold/{gold,ranking}.xlsx
                                                └── grupo3_ciberseguridad/reports/report.md
```

## Estructura del repo

```
classifier/
├── Dockerfile                          # python:3.11-slim + torch CPU + sentence-transformers + ONNX
├── docker-compose.classifier.yml       # se engancha a la red stack_web del VPS
├── requirements.txt                    # deps del container (pin estricto)
├── Makefile                            # upload / extract / score / gold / ranking / report / deploy / run-vps
├── search_query.py                     # cadena de búsqueda + ejes temáticos
├── score_rubric.md                     # metodología del scoring (para informe)
├── README-OPERADOR.md                  # guía paso a paso con puntos de captura
├── __init__.py                         # package classifier
├── src/
│   ├── config.py                       # bucket, prefijos, pesos, percentiles
│   ├── pipeline.py                     # CLI: `python -m classifier.src.pipeline run`
│   ├── upload_bronze.py                # Fase 1: PDFs locales → MinIO (paralelo)
│   ├── extract_metadata.py             # Fase 2: PyMuPDF ProcessPool + early-exit
│   ├── score.py                        # Fase 3: kw + TF-IDF + SBERT ONNX
│   ├── build_silver.py                 # Fase 4a: silver.xlsx
│   ├── build_gold.py                   # Fase 4b: gold.parquet + gold.xlsx
│   ├── ranking.py                      # Fase 5: ranking.xlsx
│   ├── reporter.py                     # Fase 6: report.md
│   └── _minio_client.py                # cliente boto3 standalone (sin lib/ externa)
└── notebooks/
    └── 10_classifier_walkthrough.ipynb # narra el pipeline para capturas
```

## Quick start

### 1. Local — preparar Bronze (upload de PDFs)

```bash
cp .env.example .env  # editá VPS_PASS y MINIO_*
# Pone tus PDFs en ./Articulos/ (formato esperado: NNNN_topic_arxiv-id_Title.pdf)
python -m classifier.src.upload_bronze --workers 24
```

### 2. VPS — deploy y run dockerizado

```bash
# 1) rsync del código al VPS bajo /root/proyecto_papers/grupo3_ciberseguridad/
# 2) build + up
ssh root@vps "cd /root/proyecto_papers/grupo3_ciberseguridad && \
    docker compose -f docker-compose.classifier.yml build && \
    docker compose -f docker-compose.classifier.yml up -d"
# 3) ejecutá el pipeline (fases 2-6) dentro del container
ssh root@vps "docker exec classifier-g3 python -m classifier.src.pipeline run"
```

El `Makefile` del directorio `classifier/` envuelve estos comandos: `make deploy`, `make build-vps`, `make up-vps`, `make run-vps`, `make logs-vps`.

## Optimizaciones aplicadas (vs baseline)

| Capa | Antes | Después | Speedup | Cómo |
|---|---:|---:|---:|---|
| Extract metadata | 231 s | 33 s | **6.9×** | ProcessPoolExecutor 8 workers + early-exit en página 1 |
| SBERT encode | 150 s | 84 s | 1.8× | sentence-transformers 3.4 con `backend="onnx"` + variante `qint8_avx512_vnni` + `batch_size=128` |
| TF-IDF | 9 s | 4.5 s | 2× | beneficio colateral |
| **Pipeline total** | **395 s** | **127 s** | **3.1×** | |

## Scoring híbrido

```
final_score_raw = 0.40 · keyword_score
                + 0.30 · tfidf_cosine
                + 0.30 · sbert_cosine
                ───────── todos normalizados a [0,1] vía min-max ─────────
```

- **Keyword matching pesado**: título×3.0, abstract×2.0, keywords×1.5, bonus por cobertura multi-eje (zero_trust, cybersecurity, detection, ai).
- **TF-IDF**: ngrams (1,2), `max_df=0.95`, `min_df=2`, 50k features, cosine vs la query natural-language.
- **Sentence-BERT** `all-MiniLM-L6-v2` cuantizado int8 (ONNX) — captura conceptos semánticos como NIST 800-207, microsegmentation, BeyondCorp sin keyword literal.

Mapeo raw → 1-5 por percentiles (10/20/30/25/15). Decisión final aplica filtro temporal 2016-2026 sobre score ∈ {4,5}.

Detalle metodológico completo en [`classifier/score_rubric.md`](classifier/score_rubric.md). Guía de operador con puntos de captura para rúbrica en [`classifier/README-OPERADOR.md`](classifier/README-OPERADOR.md).

## Convenciones

- **Bucket único** `examen-parcial` con prefijo por grupo (`grupo3_ciberseguridad/`).
- **Dockerize everything** — nada se instala en el host del VPS.
- **Pinned image tags** — torch, sentence-transformers, optimum + onnxruntime en versiones fijas para reproducibilidad.
- **Sin LLM en el batch** — Ollama / GPT son 10-30× más lentos por inferencia. El batch usa ONNX para CPU eficiente.

## Stack del container

- Base: `python:3.11-slim`
- PyTorch: 2.4.0+cpu (sin CUDA)
- sentence-transformers: 3.4.1
- ONNX runtime: 1.20.1
- PyMuPDF: 1.24.10
- Polars, scikit-learn, boto3, openpyxl, xlsxwriter

Imagen final ~3 GB, con los modelos pre-descargados en build.
