# papers-classifier — pipeline Bronze / Silver / Gold

Clasificador batch de artículos científicos sobre una arquitectura **data lakehouse** en MinIO. Cada paper recibe un `score ∈ {0,1,2,3,4,5}` calculado como el **número de keywords distintas** del tema activo que aparecen en `title ∪ keywords ∪ abstract`. El subset con `score ≥ 4` y año dentro de los últimos 10 se promueve a Gold.

El tema (título + keywords) se carga **dinámicamente** desde el endpoint `/config` del API de la UI: cambiar el tema desde el frontend dispara una reclasificación end-to-end sin redeploy del classifier.

Caso de uso de referencia: **"Implementación de un Security Data Lakehouse basado en Apache Iceberg para el entrenamiento offline de modelos de IA aplicados a la detección de amenazas"** (UNMSM 2026-I, Bases de Datos Avanzadas y Big Data, Grupo 3).

---

## Tabla de contenidos

1. [Arquitectura del lakehouse](#arquitectura-del-lakehouse)
2. [Fórmula de scoring](#fórmula-de-scoring)
3. [Pipeline batch — fases](#pipeline-batch--fases)
4. [Quick start](#quick-start)
5. [Reclasificación dinámica desde la UI](#reclasificación-dinámica-desde-la-ui)
6. [Estructura del repo](#estructura-del-repo)
7. [Convenciones y stack](#convenciones-y-stack)

---

## Arquitectura del lakehouse

Un bucket único `examen-parcial` con prefijo por grupo (`grupo3_ciberseguridad/`). Cada tier tiene un rol distinto:

| Tier | Contenido | Mutabilidad |
|---|---|---|
| **Bronze** | 2000 PDFs originales en `bronze/papers/` + manifiesto `bronze/index.parquet`. | Inmutable. Se sube una sola vez. |
| **Silver** | Tabla de contabilidad: `silver/silver.csv` y `silver/silver.xlsx` con **todas** las 2000 filas (incluyendo descartados). Columnas: `Código \| Nombre del paper \| Año \| Título \| Keywords detectadas \| Score \| Decisión`. **Sin PDFs.** | Se regenera completa en cada rescore. |
| **Gold** | Subset con `score ≥ 4` y año en `[YEAR_MIN, YEAR_MAX]`: `gold/papers/{code}.pdf` (copia 1-a-1 server-side desde bronze) + `gold/gold.csv` + `gold/gold.xlsx` + `gold/gold.parquet`. | **Sincronizado** en cada rescore: agrega los nuevos y borra los que ya no califican. |
| **Reports** | `reports/report.md` con resumen y top-N. | Reemplazado en cada run. |

```
                                  MinIO bucket examen-parcial
local Mac / laptop                ───────────────────────────────────────────────
─────────────────                 grupo3_ciberseguridad/
upload_bronze ─SSH→ MinIO  ──→     ├── bronze/
                                   │   ├── papers/PAPER_NNNN.pdf  ← 2000 inmutables
                                   │   └── index.parquet
                                   │
container classifier-g3            ├── silver/
(ejecuta dentro del VPS)           │   ├── silver.csv   ← 2000 filas, 7 columnas ES
  · extract_metadata               │   ├── silver.xlsx  ← idem
  · score                          │   ├── silver.parquet     (interno)
  · build_silver                   │   ├── metadata.parquet   (interno)
  · build_gold                     │   └── embeddings.npy     (cache SBERT)
  · ranking                        │
  · reporter                       ├── gold/
                                   │   ├── papers/PAPER_NNNN.pdf  ← sincronizados
                                   │   ├── gold.csv / gold.xlsx / gold.parquet
                                   │   └── ranking.csv / ranking.xlsx
                                   │
                                   └── reports/report.md
```

---

## Fórmula de scoring

```
text       = normalize(title ⊔ keywords ⊔ abstract)
              ├── lowercase
              ├── `-`, `_`, `/` y whitespace → ' '
              └── strip caracteres especiales (preserva letras, dígitos, '.', '+')

matches    = | { kw ∈ KEYWORDS : kw_normalized ∈ text } |
score      = min(matches, 5)                            ∈ {0, 1, 2, 3, 4, 5}

decision   = "Gold"                              si score ≥ 4 y año ∈ [YEAR_MIN, YEAR_MAX]
           = "Silver"                            si score == 3 y año en rango
           = "Descartado (score bajo)"           si score ≤ 2 y año en rango
           = "Descartado (fuera de rango temporal)"   si año fuera de rango
           = "Descartado (sin año)"              si no se pudo extraer
```

**Constantes** (en `classifier/src/config.py`):
- `GOLD_KEYWORD_THRESHOLD = 4`
- `SILVER_KEYWORD_THRESHOLD = 3`
- `MAX_SCORE = 5`
- `YEAR_MAX = current_year`, `YEAR_MIN = YEAR_MAX - 10` (rolling)

**KEYWORDS** se cargan dinámicamente desde el API en cada run del classifier — ver [reclasificación dinámica](#reclasificación-dinámica-desde-la-ui). Si el API no responde, cae a la lista hardcodeada en `classifier/search_query.py` como fallback.

`tfidf_cosine` y `sbert_cosine` se calculan y persisten en `silver.parquet` como métricas informativas, pero **no participan** del score ni de la decisión. Sirven para validar manualmente que el ranking semántico coincide con el ranking por keywords.

---

## Pipeline batch — fases

Las fases son módulos independientes en `classifier/src/`. El orquestador `pipeline.py` expone una CLI con dos modos:

```bash
python -m classifier.src.pipeline run       # extract → score → build-silver → build-gold → ranking → report
python -m classifier.src.pipeline rescore   # score → build-silver → build-gold → ranking → report  (skip extract)
```

`rescore` es el modo usado por la UI cuando solo cambian las keywords (no los PDFs).

| Fase | Módulo | Entrada | Salida | Costo aprox. |
|---|---|---|---|---|
| 1 — Upload Bronze | `upload_bronze.py` | PDFs locales en `Articulos/` | `bronze/papers/*.pdf` + `bronze/index.parquet` | ~30s (paralelo, 24 workers) |
| 2 — Extract metadata | `extract_metadata.py` | `bronze/index.parquet` + PDFs | `silver/metadata.parquet` (title, abstract, year, keywords) | ~90s (PyMuPDF, ProcessPool 8w) |
| 3 — Score | `score.py` | `silver/metadata.parquet` | `silver/silver.parquet` (+ score, decision, tfidf, sbert) | ~17s (con cache SBERT) |
| 4a — Build Silver | `build_silver.py` | `silver/silver.parquet` | `silver/silver.{csv,xlsx}` (7 cols ES, 2000 filas) | ~2s |
| 4b — Build Gold | `build_gold.py` | `silver/silver.parquet` | `gold/{papers/,gold.csv,gold.xlsx,gold.parquet}` + cleanup de orphans | ~3s + paralelo en MinIO |
| 5 — Ranking | `ranking.py` | `gold/gold.parquet` | `gold/ranking.{csv,xlsx}` | <1s |
| 6 — Report | `reporter.py` | `gold/ranking.parquet` | `reports/report.md` | <1s |

**Total**: `run` ≈ 2-3 min (incluye extract); `rescore` ≈ 25-35s (solo scoring + outputs).

### Optimizaciones aplicadas

| Capa | Cómo |
|---|---|
| Extract metadata | `ProcessPoolExecutor(8)` + early-exit en página 1 |
| SBERT encode | `sentence-transformers 3.4` con `backend="onnx"` + `qint8_avx512_vnni` + `batch_size=128`; cache local `embeddings.npy` |
| Copia entre tiers | `s3.copy_object` server-side en `ThreadPoolExecutor(16)` — no descarga al cliente |
| Cleanup de orphans | `s3.delete_object` paralelo (16 workers); list paginado para soportar >1000 keys |
| Formato primario | CSV (10× más rápido de escribir que XLSX); el XLSX queda como vista humana |

---

## Quick start

### 1. Local — preparar Bronze (una sola vez)

```bash
cp .env.example .env             # editá VPS_PASS, MINIO_ACCESS_KEY, etc.
# Poné tus PDFs en ./Articulos/  (formato: NNNN_topic_arxiv-id_Title.pdf)
python -m classifier.src.upload_bronze --workers 24
```

### 2. VPS — build y run del container

```bash
make -C classifier deploy        # rsync del código al VPS
make -C classifier build-vps     # docker compose build dentro del VPS
make -C classifier up-vps        # docker compose up -d
make -C classifier run-vps       # ejecuta fases 2-6 dentro del container
make -C classifier logs-vps      # tail de logs
```

### 3. Outputs

- **Silver** (todos): `s3://examen-parcial/grupo3_ciberseguridad/silver/silver.xlsx`
- **Gold** (seleccionados): `s3://examen-parcial/grupo3_ciberseguridad/gold/gold.xlsx`
- **PDFs Gold**: `s3://examen-parcial/grupo3_ciberseguridad/gold/papers/`
- **Reporte**: `s3://examen-parcial/grupo3_ciberseguridad/reports/report.md`

---

## Reclasificación dinámica desde la UI

El tema (título + lista de keywords) no está hardcoded — se lee desde el endpoint `GET /config` del API de la UI en cada run del classifier. Esto permite:

1. **Usuario edita** el título del tema y los keywords desde la vista `/reclassify` de la UI.
2. **UI hace** `PUT /api/config` (guarda el tema) + `POST /api/reclassify`.
3. **API** dispara `docker exec classifier-g3 python -m classifier.src.pipeline rescore` vía el socket Unix de Docker.
4. **Classifier** lee las keywords desde `http://examen-api:8000/config` al arrancar (`classifier/search_query.py`), corre `rescore`, escribe `silver/silver.parquet` y todos los outputs.
5. **API** baja `silver.parquet` y sincroniza la colección Mongo de la UI.
6. **Dashboard** refleja los nuevos números en ~30 segundos end-to-end.

Si el API no responde (smoke tests locales, desarrollo offline), el classifier cae a la lista hardcodeada de Iceberg en `classifier/search_query.py` y loguea un warning. La regla de scoring y el contrato de outputs son idénticos en ambos modos.

---

## Estructura del repo

```
classifier/
├── Dockerfile                            # python:3.11-slim + torch CPU + sentence-transformers + ONNX
├── docker-compose.classifier.yml         # red stack_web del VPS
├── requirements.txt                      # pin estricto
├── Makefile                              # targets: upload / extract / score / gold / ranking / report / deploy / run-vps
├── search_query.py                       # carga dinámica de keywords desde API + fallback estático
├── score_rubric.md                       # metodología detallada del scoring (para informe académico)
├── README-OPERADOR.md                    # guía paso a paso con puntos de captura para la rúbrica
├── __init__.py
├── src/
│   ├── config.py                         # bucket, prefijos, thresholds, YEAR_MIN/YEAR_MAX
│   ├── pipeline.py                       # CLI: `run` y `rescore`
│   ├── upload_bronze.py                  # Fase 1: PDFs locales → MinIO Bronze (24 workers)
│   ├── extract_metadata.py               # Fase 2: PyMuPDF ProcessPool (8 workers) + early-exit
│   ├── score.py                          # Fase 3: # keywords distintas + métricas auxiliares
│   ├── build_silver.py                   # Fase 4a: silver.csv/xlsx (2000 filas, sin PDFs)
│   ├── build_gold.py                     # Fase 4b: gold.{csv,xlsx,parquet} + sync de gold/papers/
│   ├── ranking.py                        # Fase 5: ranking ordenado por score
│   ├── reporter.py                       # Fase 6: report.md
│   ├── _papers_copy.py                   # helper: copy_papers_to_tier + clean_tier_prefix (paralelo)
│   └── _minio_client.py                  # cliente boto3 standalone
└── notebooks/
    └── 10_classifier_walkthrough.ipynb   # narra el pipeline para capturas
```

---

## Convenciones y stack

### Convenciones

- **Bucket único** `examen-parcial`, prefijo por grupo (`grupo3_ciberseguridad/`).
- **Dockerize everything** — nada se instala en el host del VPS.
- **Image tags pinneados** — torch, sentence-transformers, onnxruntime en versiones fijas para reproducibilidad.
- **Sin LLM en el batch** — Ollama / GPT son 10-30× más lentos por inferencia. ONNX en CPU es suficiente para los scores auxiliares.
- **Idempotencia** — cada `run` o `rescore` puede correrse N veces sin acumular ghosts; `build_silver` regenera el XLSX completo y `build_gold` sincroniza `gold/papers/` (agrega + borra).

### Stack del container

| Componente | Versión |
|---|---|
| Base | `python:3.11-slim` |
| PyTorch | `2.4.0+cpu` (sin CUDA) |
| sentence-transformers | `3.4.1` |
| ONNX runtime | `1.20.1` |
| PyMuPDF | `1.24.10` |
| Polars, scikit-learn, boto3, openpyxl, xlsxwriter | (ver `requirements.txt`) |

Imagen final ≈ 3 GB con los modelos SBERT pre-descargados en build (PyTorch + 3 variantes ONNX cuantizadas).

### Documentación complementaria

- [`classifier/score_rubric.md`](classifier/score_rubric.md) — metodología detallada del scoring, justificación de decisiones, comparación con alternativas (TF-IDF only, SBERT only, etc.).
- [`classifier/README-OPERADOR.md`](classifier/README-OPERADOR.md) — guía paso a paso con puntos de captura de pantalla para la rúbrica.
