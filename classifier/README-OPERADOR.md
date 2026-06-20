# Guía de operador — Examen Grupo 3

Esta guía explica **paso a paso** cómo correr el pipeline y **dónde tomar las capturas** que pide la rúbrica.

## Pre-requisitos (una vez)

```bash
cd "<repo>/examen"
make setup              # venv + deps + kernel Jupyter
make tunnel             # SSH multi-port-forward al VPS
make smoke              # 5/5 motores OK
```

## Camino feliz (todo en una pasada local)

```bash
cd "<repo>/examen/classifier"
make run                # Fases 1→6 secuenciales
```

Mientras corre, **captura**:

| # | Cuándo | Qué | Por qué (rúbrica) |
|---:|---|---|---|
| 1 | Inicio | terminal mostrando "Fase 1 — Bronze upload" + bucket destino | Evidencia de pipeline corriendo |
| 2 | Fin Fase 1 | tabla rich "N/N OK · sin errores" + tamaño total | Ítem 3 (Bronze) |
| 3 | UI MinIO | navegar a `https://group-one.duckdns.org/minio/` → bucket `examen-parcial` → carpeta `grupo3_ciberseguridad/bronze/papers/` mostrando los PDFs | Ítem 3 (Bronze) |
| 4 | Fin Fase 2 | tabla rich con conteos de título/abstract/keywords/año | Ítem 4 (Silver) |
| 5 | Fin Fase 3 | tabla rich distribución de scores (0..22, con corte `≥5 (Gold)`) | Ítem 1 (Algoritmo) |
| 6 | Fin Fase 4a | "✓ silver.csv → s3://…" + "✓ N/N PDFs copiados a silver" | Ítem 4 (Silver tier completo) |
| 7 | Fin Fase 4b | "Papers Gold: N (score ≥ 5)" + "✓ N/N PDFs copiados a gold" | Ítem 5 (Gold) |
| 8 | Fin Fase 5 | tabla rich con el Top-10 ranking | Ítem 6 (Ranking) |
| 9 | MinIO UI | bucket `examen-parcial/grupo3_ciberseguridad/silver/papers/` y `…/gold/papers/` con los PDFs visibles | Ítems 4, 5 (PDFs físicos por tier) |
| 10 | CSV/XLSX | `outputs/silver.csv`, `outputs/gold.csv`, `outputs/ranking.csv` (y `.xlsx` opcionales) abiertos con datos visibles | Ítems 4, 5, 6 |
| 11 | Markdown | `outputs/report.md` renderizado | Ítem 8 (Informe) |

## Camino "VPS" (evidencia oficial — ítem 7 de la rúbrica)

```bash
cd "<repo>/examen/classifier"
make deploy             # rsync de scripts al VPS
make build-vps          # docker compose build (también dispara deploy)
make up-vps             # arranca container classifier-g3
make run-vps            # docker exec → corre la pipeline DENTRO del container
```

Capturar también:

| # | Cuándo | Qué |
|---:|---|---|
| 12 | Pre-run | `make up-vps` mostrando "docker ps" con classifier-g3 healthy |
| 13 | Durante run | `make run-vps` mostrando las fases en vivo dentro del container |
| 14 | Post-run | `ssh root@... 'ls -la /root/proyecto_papers/grupo3_ciberseguridad/outputs'` mostrando los .csv/.md |
| 15 | MinIO UI | bucket `examen-parcial` con las carpetas `bronze/`, `silver/papers/`, `silver/silver.csv`, `gold/papers/`, `gold/gold.csv`, `reports/` populadas |

## Iteraciones rápidas (cambiar keywords o umbral sin recomputar SBERT)

El cuello de botella en re-runs es la capa SBERT (~84 s). Los embeddings se cachean
en `outputs/embeddings.npy` (y se suben a MinIO). Para experimentar:

```bash
# editar KEYWORDS_FLAT en classifier/search_query.py
# o editar GOLD_KEYWORD_THRESHOLD en src/config.py
make score              # ~10s (usa cache de embeddings) — recalcula score y decisión
make silver gold ranking report
```

**Importante**: si cambiás keywords, también cambia la query natural-language que
alimenta SBERT/TF-IDF. El cache de SBERT sigue siendo válido (cachea embeddings del
**corpus**, no de la query), pero las columnas `tfidf_cosine` / `sbert_cosine` se
recalcularán contra la nueva query.

## Troubleshooting

| Síntoma | Fix |
|---|---|
| `Fase 1 ✗ tunnel down` | `make tunnel` desde `examen/` |
| `make run-vps` cuelga | abrir terminal aparte y `make logs-vps` para ver progreso real |
| Pocos Gold (<50) | bajar `GOLD_KEYWORD_THRESHOLD` en `config.py` o agregar keywords a `KEYWORDS_FLAT`; correr `make score gold ranking report` |
| Muchos Gold (>800) | subir `GOLD_KEYWORD_THRESHOLD` o quitar keywords genéricas |
| PDFs no copiados a silver/gold | revisar permisos del bucket; correr `make build-silver gold` |
| Container clasificador no levanta | `ssh root@vps 'docker logs classifier-g3'` |
