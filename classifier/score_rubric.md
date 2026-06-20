# Score Rubric — Grupo 3 / Security Data Lakehouse

Documenta la metodología del clasificador. Es la base del **ítem 1 (Algoritmo)** y **ítem 8 (Informe)** de la rúbrica.

## 1. Pipeline

```
PDFs (Bronze, inmutable)
   │
   ├── extract metadata (Silver-raw)            → metadata.parquet
   │
   ├── score = # keywords distintas matched     → silver.parquet (corpus completo)
   │           en title ∪ keywords ∪ abstract     + copia 1-a-1 de PDFs a silver/papers/
   │                                              + silver.csv (primario) + silver.xlsx (opcional)
   │
   ├── Gold (score ≥ 5 + año en rango)          → gold.parquet
   │                                              + copia de PDFs a gold/papers/
   │                                              + gold.csv (primario) + gold.xlsx (opcional)
   │
   └── ranking + report                         → ranking.csv + report.md
```

Bronze contiene los PDFs originales sin tocar. Silver y Gold son tiers derivados con copia
física de los PDFs vía `s3.copy_object` (server-side, no descarga al cliente).

## 2. Cadena de búsqueda (Scopus)

```
TITLE-ABS-KEY (
  ("data lakehouse" OR "Apache Iceberg" OR "open table format" OR "object storage") AND
  ("cybersecurity" OR "threat detection" OR "security logs" OR "SIEM" OR "telemetry data") AND
  ("machine learning" OR "artificial intelligence" OR "offline training" OR "feature store" OR "predictive models") AND
  ("big data" OR "data pipeline" OR "scalability" OR "query performance" OR "data retention" OR
   "schema evolution" OR "historical data" OR "time-travel query")
)
```

Internamente la lista se aplana a **22 keywords** sin agrupación por ejes; cada keyword
cuenta 1 si aparece al menos una vez en el texto combinado del paper.

## 3. Score (regla única de tier)

```
score = | { kw ∈ KEYWORDS_FLAT : kw aparece en normalize(title ⊔ keywords ⊔ abstract) } |
```

- Frases multi-palabra (`"data lakehouse"`, `"time-travel query"`) cuentan como 1.
- Comparación case-insensitive, con normalización de separadores (`-`, `_`, `/`, espacios múltiples).
- Substring match (no requiere bordes de palabra), para tolerar variantes de tokenización del extractor.

Rango posible del score: `0 .. 22` (`len(KEYWORDS_FLAT)`).

## 4. Decisión

| Score | Año | Decisión |
|:---:|:---:|---|
| ≥ 5 | 2016-2026 | **Gold** |
| ≥ 5 | fuera de rango | Gold fuera de rango temporal |
| < 5 | cualquiera | Silver |

El umbral `5` se define en `config.py::GOLD_KEYWORD_THRESHOLD` y es la única decisión de tier.

## 5. Métricas auxiliares (informativas, NO deciden tier)

El pipeline también calcula y persiste en `silver.csv` dos columnas auxiliares para
análisis posterior y trazabilidad:

- `tfidf_cosine`: cosine similarity entre la query natural-language y el corpus
  (`TfidfVectorizer` con n-gram (1,2), `max_df=0.95`, `min_df=2`, 50k features).
- `sbert_cosine`: `sentence-transformers/all-MiniLM-L6-v2` (ONNX int8) embeddings
  del corpus vs la query.

Los embeddings se cachean en `s3://examen-parcial/grupo3_ciberseguridad/silver/embeddings.npy`
para no recomputar si cambia solo el umbral.

## 6. Justificación textual

Cada paper trae en `silver.csv` la columna `justificacion` con:

```
matches=N/22 · kws: kw1, kw2, … · tfidf=0.42 · sbert=0.51
```

Esto hace el resultado **auditable** (ítem 4 de la rúbrica): cualquier evaluador puede
abrir el PDF en `silver/papers/` y verificar a mano qué keywords aparecen.

## 7. Detección de año (multi-señal)

Tres fuentes votan; mayoría simple. Confianza alta si arxiv-id coincide con extraído,
media si dos fuentes coinciden, baja si solo una.

1. **Primaria**: arxiv-id en el nombre del archivo (formato `YYMM.NNNNN`).
2. **Secundaria**: regex `\b(19|20)\d{2}\b` sobre la primera página del PDF.
3. **Terciaria**: metadata XMP del PDF (`/CreationDate`).

## 8. Extracción de título / abstract / keywords (PyMuPDF)

- **Título**: heurística font-size — el bloque de texto con mayor tamaño en el primer
  50% vertical de la página 1.
- **Abstract**: regex multi-idioma con fallback en español a `\bresumen\b`.
- **Keywords**: regex sobre la sección "Keywords:" / "Palabras clave:" + fallback a
  YAKE (top-8 sobre el abstract) si la sección no existe.

## 9. Reproducibilidad

- Random seeds fijos (`DetectorFactory.seed=0` para langdetect).
- Cache de embeddings SBERT por código de paper.
- Manifest de Bronze persiste sha256 + etag de cada PDF para auditoría.
- El score depende solo de la lista de keywords + extracción → re-calcular score es
  determinístico al 100%.
