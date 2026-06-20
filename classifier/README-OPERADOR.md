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
| 2 | Fin Fase 1 | tabla rich "5/5 OK · sin errores" + tamaño total | Ítem 3 (Bronze) |
| 3 | UI MinIO | navegar a `https://group-one.duckdns.org/minio/` → bucket `examen-parcial` → carpeta `grupo3_ciberseguridad/bronze/papers/` mostrando los 2000 PDFs | Ítem 3 (Bronze) |
| 4 | Fin Fase 2 | tabla rich con conteos de título/abstract/keywords/año | Ítem 4 (Silver) |
| 5 | Fin Fase 3 | tabla rich distribución de scores 1-5 | Ítem 1 (Algoritmo) |
| 6 | Fin Fase 4 | "Papers Gold: N (score 5: a, score 4: b)" en terminal | Ítem 5 (Gold) |
| 7 | Fin Fase 5 | tabla rich con el Top-10 ranking | Ítem 6 (Ranking) |
| 8 | Excel | `outputs/silver.xlsx`, `outputs/gold.xlsx`, `outputs/ranking.xlsx` abiertos con datos visibles | Ítems 4, 5, 6 |
| 9 | Markdown | `outputs/report.md` renderizado | Ítem 8 (Informe) |

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
| 10 | Pre-run | `make up-vps` mostrando "docker ps" con classifier-g3 healthy |
| 11 | Durante run | `make run-vps` mostrando las fases en vivo dentro del container |
| 12 | Post-run | `ssh root@... 'ls -la /root/proyecto_papers/grupo3_ciberseguridad/outputs'` mostrando los .xlsx/.md |
| 13 | MinIO UI | bucket `examen-parcial` con las carpetas `bronze/`, `silver/`, `gold/`, `reports/` populadas |

## Iteraciones rápidas (recalibrar percentiles sin recomputar SBERT)

El cuello de botella en re-runs es la capa SBERT (~2 min). Los embeddings se cachean en `outputs/embeddings.npy` (y se suben a MinIO). Para experimentar con otro mapeo a 1-5:

```bash
# editar SCORE_BUCKETS en src/config.py
make score              # ~10s (usa cache)
make silver gold ranking report
```

## Troubleshooting

| Síntoma | Fix |
|---|---|
| `Fase 1 ✗ tunnel down` | `make tunnel` desde `examen/` |
| `Authentication failed` en Mongo (smoke) | revisar `MONGO_USER=admin` en `.env` |
| `make run-vps` cuelga | abrir terminal aparte y `make logs-vps` para ver progreso real |
| Distribución de Gold rara (<50 o >800 papers) | ajustar `SCORE_BUCKETS` en `config.py` y re-correr `make score` (usa cache) |
| Container clasificador no levanta | `ssh root@vps 'docker logs classifier-g3'` |
