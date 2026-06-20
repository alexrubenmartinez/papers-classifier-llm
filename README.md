# papers-classifier — pipeline Bronze / Silver / Gold

Clasificador de artículos científicos para selección automática de papers relevantes a una tesis. Implementa una arquitectura **data lakehouse en MinIO** con scoring por **conteo de keywords distintas** sobre title ∪ keywords ∪ abstract. Diseñado para correr **dentro de un container Docker en el VPS**, conectado a la red del stack del curso.

Caso de uso de referencia: clasificación de PDFs para la tesis del Grupo 3 — *"Implementación de un Security Data Lakehouse basado en Apache Iceberg para el entrenamiento offline de modelos de IA aplicados a la detección de amenazas"* (Bases de Datos Avanzadas y Big Data, UNMSM 2026-I).

## Cómo decide cada tier

- **Bronze**: PDFs originales, inmutables, subidos una sola vez.
- **Silver**: TODOS los papers procesados — metadata extraída + `score = min(#keywords distintas matched, 5)` + **copia 1-a-1 del PDF** a `silver/papers/`.
- **Gold**: subconjunto con `score ≥ 4` y año dentro de los **últimos 10 años** (computado dinámicamente); los PDFs se **copian** a `gold/papers/`.

Las métricas auxiliares `tfidf_cosine` y `sbert_cosine` se siguen calculando y persisten como columnas informativas en el CSV, pero **no intervienen** en la decisión de tier.

## Arquitectura

```
local Mac / laptop                        VPS (red docker stack_web)
─────────────────                         ───────────────────────────
classifier/src/upload_bronze   ──── SSH ─→  MinIO (examen-parcial)
                                                │
                                                ├── grupo3_ciberseguridad/bronze/papers/*.pdf   ← inmutable
                                                ├── grupo3_ciberseguridad/bronze/index.parquet
                                                │
container classifier-g3 (corre dentro VPS)      │
  ├── extract_metadata    (PyMuPDF + ProcessPool 8w + early-exit)
  ├── score               (# keywords matched + TF-IDF + SBERT informativos)
  ├── build_silver        (CSV + XLSX + copy_object → silver/papers/)
  ├── build_gold          (filtra score ≥ 5 + copy_object → gold/papers/)
  ├── ranking             (csv + xlsx ordenado por score)
  └── reporter            (markdown)
                                                │
                                                ├── grupo3_ciberseguridad/silver/papers/*.pdf   ← copia 1-a-1
                                                ├── grupo3_ciberseguridad/silver/silver.csv     ← primario
                                                ├── grupo3_ciberseguridad/silver/silver.xlsx    ← opcional
                                                ├── grupo3_ciberseguridad/silver/{metadata,silver}.parquet
                                                ├── grupo3_ciberseguridad/silver/embeddings.npy
                                                ├── grupo3_ciberseguridad/gold/papers/*.pdf     ← solo score ≥ 5
                                                ├── grupo3_ciberseguridad/gold/{gold,ranking}.csv
                                                ├── grupo3_ciberseguridad/gold/{gold,ranking}.xlsx (opcional)
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
│   ├── config.py                       # bucket, prefijos, GOLD_KEYWORD_THRESHOLD
│   ├── pipeline.py                     # CLI: `python -m classifier.src.pipeline run`
│   ├── upload_bronze.py                # Fase 1: PDFs locales → MinIO (paralelo)
│   ├── extract_metadata.py             # Fase 2: PyMuPDF ProcessPool + early-exit
│   ├── score.py                        # Fase 3: score = # keywords distintas matched
│   ├── build_silver.py                 # Fase 4a: silver.csv + xlsx + copy → silver/papers/
│   ├── build_gold.py                   # Fase 4b: gold.csv + xlsx + copy → gold/papers/
│   ├── ranking.py                      # Fase 5: ranking.csv (+xlsx)
│   ├── reporter.py                     # Fase 6: report.md
│   ├── _papers_copy.py                 # helper: s3.copy_object server-side paralelo
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

## Optimizaciones aplicadas

| Capa | Cómo |
|---|---|
| Extract metadata | ProcessPoolExecutor 8 workers + early-exit en página 1 |
| SBERT encode (auxiliar) | sentence-transformers 3.4 con `backend="onnx"` + variante `qint8_avx512_vnni` + `batch_size=128` |
| Copia de PDFs entre tiers | `s3.copy_object` server-side (no descarga al cliente) en `ThreadPoolExecutor(16)` |
| Formato primario | CSV en vez de XLSX (un orden de magnitud más rápido al escribir) |

## Scoring

```
raw_matches = | { kw ∈ KEYWORDS_FLAT : kw aparece en normalize(title ⊔ keywords ⊔ abstract) } |
score       = min(raw_matches, MAX_SCORE)        # MAX_SCORE = 5 → score ∈ {0,1,2,3,4,5}
decision    = "Gold"   si score ≥ GOLD_KEYWORD_THRESHOLD (4) y año ∈ últimos 10 años
            = "Silver" en caso contrario
```

- **22 keywords** organizadas semánticamente en la query Scopus (lakehouse / security /
  AI-ML / big-data), pero **aplanadas a una sola lista plana** para el scoring — cada
  keyword cuenta 1 sin importar su grupo.
- Frases multi-palabra (`"data lakehouse"`, `"time-travel query"`) cuentan como 1.
- Substring match case-insensitive sobre texto normalizado (`-`, `_`, `/`, espacios múltiples colapsados).

Las columnas `tfidf_cosine` y `sbert_cosine` se calculan y persisten como métricas
informativas, pero **no entran** en la fórmula del score. Sirven para análisis posterior
y para validar manualmente cuán "semánticamente cerca" está un paper sin matches literales.

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
