# papers-classifier-llm

Pipeline de clasificación de papers académicos con scoring híbrido (keyword + TF-IDF + SBERT) y justificación generada por LLM (Ollama). Backend FastAPI + frontend Angular 22 + Mongo + MinIO, todo orquestado con Docker detrás de nginx.

Permite subir PDFs de papers, clasificarlos contra una query temática editable, reordenar el corpus cada vez que cambia el tema, y opcionalmente generar una justificación con LLM por cada paper.

## Arquitectura

```
                    ┌──────────────────────────┐
                    │  Browser / Postman       │
                    └─────────────┬────────────┘
                                  │ HTTPS
                                  ▼
       ┌────────────────────────────────────────────────────┐
       │  nginx central del stack (cert wildcard)            │
       │  Rutea por subdomain:                               │
       │   ui.*       → examen-ui                            │
       │   api.*      → examen-api  (con API key check)      │
       │   ollama-api.*→ ollama     (con API key check)      │
       └─────────────────┬───────────────┬──────────────────┘
                         │               │
              ┌──────────▼──┐    ┌───────▼─────────┐
              │  examen-ui  │    │   examen-api    │
              │  (nginx +   │    │   (FastAPI)     │
              │   Angular)  │    │                 │
              │             │    │   ┌──────────┐  │
              │ Proxy /api/ │───▶│   │ SBERT    │  │
              │ con X-API-  │    │   │ PyMuPDF  │  │
              │ Key inyect. │    │   │ TF-IDF   │  │
              │             │    │   └──────────┘  │
              └─────────────┘    └─┬─────┬─────┬───┘
                                   │     │     │
                              ┌────▼─┐ ┌─▼──┐ ┌▼──────┐
                              │Mongo │ │MinIO│ │Ollama │
                              │      │ │     │ │qwen2.5│
                              └──────┘ └─────┘ └───────┘
```

**Capas Bronze / Silver / Gold:**

| Tier | Score | Decisión backend |
|---|---|---|
| Gold | 4–5 | Gold muy / Gold claramente |
| Silver | 3 | Revisar parcial |
| Bronze | 1–2 | No prioritario / Excluido |
| Fuera de rango | 0 | Año fuera del rango temporal |

## Pre-requisitos del VPS

1. **Linux + Docker + Docker Compose v2** (probado en Rocky 9).
2. **Stack Docker existente** corriendo en una network externa `stack_web` con estos containers ya activos:
   - `mongodb` (puerto 27017 interno, autenticado con `admin`)
   - `minio` (puerto 9000 interno)
   - `nginx` (proxy reverso central) montando configs desde `/root/stack/data/nginx/conf.d/`
3. **Certificado TLS wildcard** (`*.tu-vps.example.com`) presente en `/etc/letsencrypt/live/tu-vps.example.com/`. Si no lo tenés: `certbot certonly --dns-* ...`.
4. **DNS** con wildcard al VPS (ej. DuckDNS `*.tu-vps.example.com → tu IP`).
5. **23+ GB RAM libres** (Ollama qwen2.5:1.5b usa ~1.2 GB, SBERT ~500 MB, etc.).

## Variables de entorno

Copiá `.env.example` a `.env` y completá:

```bash
cp .env.example .env
$EDITOR .env
```

La `API_KEY` se inyecta server-side en los nginx vhosts (no se distribuye al cliente). Generala con `openssl rand -hex 32`.

## Despliegue paso a paso

Asumiendo que clonás el repo en tu máquina local y subís cada pieza al VPS por SSH/SCP.

### 1) Ollama (~5 min)

```bash
# En tu máquina local:
scp -r infra/ollama root@$VPS_HOST:/root/papers/ollama

# En el VPS:
ssh root@$VPS_HOST
cd /root/papers/ollama
docker compose up -d
docker exec ollama ollama pull $OLLAMA_DEFAULT_MODEL
```

Aplicá el vhost del API público de Ollama (reemplazá el placeholder de la API key en el .conf antes):

```bash
# Editar con la API_KEY real:
sed -i "s|REPLACE_API_KEY|$API_KEY|g" infra/nginx/06-ollama-api.conf
sed -i "s|REPLACE_DOMAIN|$OLLAMA_DOMAIN|g" infra/nginx/06-ollama-api.conf

scp infra/nginx/06-ollama-api.conf root@$VPS_HOST:/root/stack/data/nginx/conf.d/
ssh root@$VPS_HOST "docker exec nginx nginx -t && docker exec nginx nginx -s reload"

# Verificar:
curl -H "X-API-Key: $API_KEY" https://$OLLAMA_DOMAIN/
# → "Ollama is running"
```

### 2) FastAPI (`examen-api`, ~10 min)

```bash
# En tu máquina local:
scp -r api root@$VPS_HOST:/root/papers/api

# En el VPS:
ssh root@$VPS_HOST
cd /root/papers/api
docker compose up -d --build
# ~ 6-8 min: descarga torch CPU + sentence-transformers, pre-descarga SBERT
docker logs -f examen-api  # esperá "[startup] SBERT model loaded"
```

Aplicá el vhost del API:

```bash
sed -i "s|REPLACE_API_KEY|$API_KEY|g" infra/nginx/09-examen-api.conf
sed -i "s|REPLACE_DOMAIN|$API_DOMAIN|g" infra/nginx/09-examen-api.conf
scp infra/nginx/09-examen-api.conf root@$VPS_HOST:/root/stack/data/nginx/conf.d/
ssh root@$VPS_HOST "docker exec nginx nginx -t && docker exec nginx nginx -s reload"

# Verificar:
curl -H "X-API-Key: $API_KEY" https://$API_DOMAIN/health
# → {"status":"ok","papers":3,"sbert_loaded":true,...}
```

### 3) UI Angular (`examen-ui`, ~3 min)

```bash
# En tu máquina local:
scp -r ui root@$VPS_HOST:/root/papers/ui

# En el VPS:
ssh root@$VPS_HOST
cd /root/papers/ui

# Editar nginx.conf para inyectar TU API_KEY:
sed -i "s|REPLACE_API_KEY|$API_KEY|g" nginx.conf

docker compose up -d --build
```

Aplicá el vhost de la UI (este NO requiere API key — la UI es pública, el proxy interno inyecta la key):

```bash
sed -i "s|REPLACE_DOMAIN|$UI_DOMAIN|g" infra/nginx/10-examen-ui.conf
scp infra/nginx/10-examen-ui.conf root@$VPS_HOST:/root/stack/data/nginx/conf.d/
ssh root@$VPS_HOST "docker exec nginx nginx -t && docker exec nginx nginx -s reload"

# Verificar:
curl -o /dev/null -w "%{http_code}\n" https://$UI_DOMAIN/
# → 200
```

Abrí `https://$UI_DOMAIN/` en el browser.

## Verificación end-to-end

1. **Dashboard carga** con counts Bronze/Silver/Gold + donut chart.
2. **Subir un PDF** desde `/upload` con `justify=auto` → redirige a `/jobs/:id` → SSE muestra `extracting_metadata → embedding_sbert → scoring → ollama_justify → completed`.
3. **Cambiar tema** en `/config` (ej. de "zero trust" a "blockchain") + "Guardar + Reclasificar" → modal de costo → ranking se reordena en segundos.
4. **`/reclassify` con `justify=all`** sobre 2000 papers → modal **danger con doble confirmación** (~11 horas).
5. **`/chat`** → respuesta de qwen2.5:1.5b en ~5-20s warm.
6. **DevTools → Network**: ninguna request expone `X-API-Key` (server-side).

## Estructura del repo

```
.
├── api/                # FastAPI con pipeline SBERT + Mongo + MinIO + Ollama
│   ├── app/
│   │   ├── main.py     # endpoints
│   │   ├── pipeline.py # PyMuPDF + SBERT + TF-IDF + scoring híbrido
│   │   ├── db.py       # Mongo + MinIO clients + seed
│   │   ├── repos.py    # CRUD layer
│   │   └── schemas.py  # Pydantic models
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── requirements.txt
│
├── ui/                 # Angular 22 standalone + signals
│   ├── src/
│   │   └── app/
│   │       ├── core/   # api/, sse/, models, theme
│   │       ├── features/  # dashboard, papers, ranking, config, upload, reclassify, jobs, chat
│   │       └── shared/    # ui/, layout/, animations/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── nginx.conf      # proxy /api → examen-api con X-API-Key inyectada
│
└── infra/
    ├── nginx/          # 3 vhosts (ollama-api, examen-api, examen-ui)
    ├── ollama/         # docker-compose.yml del container Ollama
    ├── postman/        # 2 collections (api + ollama) listas para importar
    └── README.md       # detalle operativo
```

## Endpoints del API

| Método | Path | Descripción |
|---|---|---|
| GET | `/health` | Liveness + counts |
| GET | `/config` | Query/keywords/weights/thresholds activos |
| PUT | `/config?reclassify=bool` | Actualizar tema (parcial) |
| POST | `/papers?justify=none\|lazy\|auto` | Upload PDF (multipart) |
| GET | `/papers?limit&min_score` | Lista paginada |
| GET | `/papers/:id` | Detalle con breakdown |
| GET | `/ranking?top=N` | Top-N por weighted |
| POST | `/reclassify?reextract=bool&justify=none\|gold_only\|all` | Reprocesar todo |
| POST | `/justify/:paper_id` | Generar justificación (~15s) |
| POST | `/justify` (body: paper_ids \| top \| min_score) | Batch async |
| GET | `/jobs/:id` | Estado de un job |
| GET | `/stream?job_id=opt` | SSE con job.progress / job.completed |
| POST | `/chat` | Proxy a Ollama (model + messages) |

OpenAPI auto-generado en `https://$API_DOMAIN/docs` y `https://$API_DOMAIN/openapi.json`.

## Postman

Importá las dos collections de `infra/postman/`:
- `examen-api.postman_collection.json` — 18 requests organizados como flujo de demo
- `ollama-api.postman_collection.json` — 7 requests para Ollama directo

Las collections traen variables `{{baseUrl}}` y `{{apiKey}}` que tenés que setear en tu environment de Postman.

## Decisiones técnicas clave

- **Auth server-side**: el `X-API-Key` se inyecta en los nginx vhosts y en el nginx interno del container UI. El browser nunca lo ve. Cambiar a token-por-usuario es un cambio aislado a esos `.conf`.
- **SBERT (`all-MiniLM-L6-v2`) pre-descargado al build**: el primer startup del API no requiere internet. El modelo (~80 MB) queda en un volume cacheado.
- **Scoring híbrido configurable** sin redeploy: pesos (keyword/tfidf/sbert) y thresholds (gold_muy/gold_claro/revisar/no_prioritario) viven en Mongo y se editan desde `/config`.
- **Embeddings persistidos en el paper doc**: el reclassify NO recalcula embeddings, solo recompone scores. Reordenar 2000 papers tarda ~1 minuto.
- **Ollama opcional, asincrónico**: la justificación tiene 4 modos (`none`, `lazy`, `auto`, `gold_only`, `all`) para evitar bloquear con ~11h de generación sobre 2000 papers en CPU.
- **SSE para progreso**: jobs largos (reclassify, justify batch) emiten eventos `job.progress` parseables; la UI los muestra en vivo.

## Operaciones útiles

```bash
# Pull de otro modelo Ollama
ssh root@$VPS_HOST "docker exec ollama ollama pull llama3.2:3b"

# Backup de Mongo
ssh root@$VPS_HOST "docker exec mongodb mongodump --db examen_api --archive" > backup.archive

# Re-procesar todos los PDFs subidos cuando mejorás el extractor
curl -X POST -H "X-API-Key: $API_KEY" "https://$API_DOMAIN/reclassify?reextract=true"

# Ver logs en vivo del API
ssh root@$VPS_HOST "docker logs -f examen-api"
```

## Dev local (UI)

```bash
cd ui
npm install
npm run start  # http://localhost:4200
```

Para que la UI dev pegue al API de producción, agregá un `proxy.conf.json` que redirija `/api/*` a tu VPS con el header `X-API-Key`. NO commitear ese archivo.

## Licencia

MIT
