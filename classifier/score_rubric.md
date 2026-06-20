# Score Rubric — Grupo 3 / Ciberseguridad

Documenta la metodología del clasificador. Es la base del **ítem 1 (Algoritmo)** y **ítem 8 (Informe)** de la rúbrica.

## 1. Pipeline

```
PDFs (Bronze) → metadata (Silver-raw) → score 1-5 (Silver final) → Gold (4-5 + año en rango) → Ranking
```

## 2. Cadena de búsqueda

Refinada desde el ejemplo del enunciado, con sinónimos técnicos para mejorar el recall semántico (ver `search_query.py`):

```
(zero trust OR zero-trust architecture OR ZTNA OR BeyondCorp OR NIST 800-207 OR SDP OR SASE OR microsegmentation OR …)
AND
(cybersecurity OR information security OR cloud security OR hybrid cloud security OR ciberseguridad OR …)
AND
(threat detection OR intrusion detection OR anomaly detection OR attack detection OR detección de amenazas OR …)
AND
(artificial intelligence OR machine learning OR deep learning OR neural network OR LLM OR transformer OR …)
```

Ejes temáticos (`KEYWORDS_BY_AXIS` en `search_query.py`):

| Eje | Ejemplos |
|---|---|
| `zero_trust` | zero trust, ZTNA, BeyondCorp, NIST 800-207, microsegmentation, SDP, SASE |
| `cybersecurity` | cybersecurity, cloud security, hybrid cloud security, ciberseguridad |
| `detection` | threat detection, intrusion detection, anomaly detection, malware detection |
| `ai` | artificial intelligence, machine learning, deep learning, LLM, transformer |

## 3. Score híbrido en 3 capas

```
score_raw = 0.40 · keyword_score  +  0.30 · tfidf_cosine  +  0.30 · sbert_cosine
                ───────── todos normalizados a [0,1] vía min-max ─────────
```

### 3.1 Keyword score (capa léxica)

Cuenta apariciones de cada keyword del set en distintas secciones del paper, con pesos:

| Sección | Peso |
|---|---:|
| Título | 3.0 |
| Abstract | 2.0 |
| Keywords (sección "Keywords:") | 1.5 |
| Cuerpo (3 primeras páginas) | 0.5 |

Aplica además dos bonus:

- **Cobertura multi-eje**: si el paper toca 1, 2, 3 o 4 ejes → multiplicador 1.00, 1.15, 1.30, 1.45.
- **Topic-tag local**: bonus 1.05 si el `topic-tag` del nombre del archivo contiene `cyber`, `security`, `zero`, `ai`, etc.

### 3.2 TF-IDF cosine (capa léxica estadística)

- `sklearn.feature_extraction.text.TfidfVectorizer` con n-gram (1, 2), `max_df=0.95`, `min_df=2`, max 50k features.
- Fit sobre `title + ". " + abstract` de **todo el corpus**.
- Transform de la query (versión natural-language, sin operadores booleanos) y cálculo de cosine similarity contra cada paper.

### 3.3 Sentence-BERT cosine (capa semántica)

- Modelo: `sentence-transformers/all-MiniLM-L6-v2` (80 MB, balance calidad/velocidad).
- Embedding del corpus en batches; embedding de la query; cosine sim.
- **Esta capa es la que captura conceptos sinónimos** que ninguna keyword literal alcanza: NIST 800-207, microsegmentation network slicing, identity-aware proxy, etc.
- Los embeddings del corpus se cachean en `s3://examen-parcial/grupo3_ciberseguridad/silver/embeddings.npy` para recalibrar pesos sin recomputar.

## 4. Mapeo raw → 1-5 (percentiles)

| Percentil del raw | Score |
|---:|---:|
| ≥ 90% | 5 |
| 70-90% | 4 |
| 40-70% | 3 |
| 15-40% | 2 |
| < 15% | 1 |

Los percentiles se calculan sobre el corpus completo. Si la distribución por año cambia significativamente o el resultado se ve muy concentrado, los cortes se ajustan en `config.py::SCORE_BUCKETS`.

## 5. Filtro temporal + decisión

| Score | Año | Decisión |
|:---:|:---:|---|
| 5 | 2016-2026 | Gold — muy relacionado |
| 4 | 2016-2026 | Gold — claramente relacionado |
| 5 ó 4 | < 2016 | Fuera del rango temporal |
| 3 | cualquiera | Revisar (parcial) |
| 2 | cualquiera | No prioritario |
| 1 | cualquiera | Excluido |

## 6. Justificación textual

Cada paper trae en Silver una columna `justificacion` con:

- Keywords matcheadas (top 6).
- `tfidf=<valor>`
- `sbert=<valor>`
- `raw=<valor>` (post combinación)

Esto hace el resultado **auditable** (ítem 4 de la rúbrica).

## 7. Detección de año (multi-señal)

Tres fuentes votan; mayoría simple. Confianza alta si arxiv-id coincide con extraído, media si dos fuentes coinciden, baja si solo una.

1. **Primaria**: arxiv-id en el nombre del archivo (formato `YYMM.NNNNN`).
2. **Secundaria**: regex `\b(19|20)\d{2}\b` sobre la primera página del PDF.
3. **Terciaria**: metadata XMP del PDF (`/CreationDate`).

## 8. Extracción de título / abstract / keywords (PyMuPDF)

- **Título**: heurística font-size — el bloque de texto con mayor tamaño en el primer 50% vertical de la página 1.
- **Abstract**: regex multi-idioma `(?is)\babstract\b\s*[:\-.]?\s*(.{120,4000}?)(?=\n\s*(?:keywords?|1\.|introduction|resumen)...)` con fallback en español a `\bresumen\b`.
- **Keywords**: regex sobre la sección "Keywords:" / "Palabras clave:" + fallback a YAKE (top-8 sobre el abstract) si la sección no existe.

## 9. Reproducibilidad

- Random seeds fijos (`DetectorFactory.seed=0` para langdetect).
- Cache de embeddings SBERT por código de paper.
- Manifest de Bronze persiste sha256 + etag de cada PDF para auditoría.
