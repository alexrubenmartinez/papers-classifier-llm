# Infra del examen — VPS your-vps.example.com

Servicios extra que viven encima del stack principal del curso, sin tocarlo.

## Fase 0 — Ollama LLM API

Servidor Ollama (CPU-only) expuesto vía HTTPS con autenticación por API key.

### Endpoint público

- URL: `https://ollama-api.your-vps.example.com`
- Header obligatorio: `X-API-Key: REPLACE_API_KEY`
- Modelo por defecto: `qwen2.5:1.5b` (~1 GB, ~15–25 tokens/seg en CPU)

### Componentes en el VPS

| Pieza | Path | Notas |
|---|---|---|
| Compose del container Ollama | `/root/proyecto_papers/ollama/docker-compose.yml` | Red `stack_web`, vol `./models` |
| vhost de nginx | `/root/stack/data/nginx/conf.d/06-ollama-api.conf` | Cert wildcard, API key gate |
| Modelos pulleados | `/root/proyecto_papers/ollama/models/` | Persistente entre restarts |

### Quick test desde tu terminal

```bash
# 1. Health (root) — debe devolver "Ollama is running"
curl -H "X-API-Key: REPLACE_API_KEY" \
  https://ollama-api.your-vps.example.com/

# 2. Listar modelos descargados
curl -H "X-API-Key: REPLACE_API_KEY" \
  https://ollama-api.your-vps.example.com/api/tags

# 3. Chat real
curl -H "X-API-Key: REPLACE_API_KEY" \
     -H "Content-Type: application/json" \
     https://ollama-api.your-vps.example.com/api/chat \
     -d '{
       "model": "qwen2.5:1.5b",
       "stream": false,
       "messages": [{"role":"user","content":"Que es zero trust?"}]
     }'

# 4. Auth check — sin key debe devolver 401
curl -i https://ollama-api.your-vps.example.com/
```

### Postman

Importá `infra/postman/ollama-api.postman_collection.json`. Incluye:

- Health, list models
- Chat (sync + streaming)
- Generate (completion)
- Endpoint OpenAI-compatible (`/v1/chat/completions`)
- Auth-fail check (debe dar 401)

### Operación

Pull de un modelo nuevo:

```bash
ssh root@your.vps.ip.address "docker exec ollama ollama pull <model>:<tag>"
```

Modelos viables en CPU (RAM aproximada):

| Modelo | RAM | tokens/seg |
|---|---|---|
| `qwen2.5:0.5b` | 400 MB | 30–50 |
| `qwen2.5:1.5b` | 1.2 GB | 15–25 |
| `llama3.2:3b`  | 2.5 GB | 7–12 |

Logs y restart:

```bash
ssh root@your.vps.ip.address "docker logs --tail 50 ollama"
ssh root@your.vps.ip.address "cd /root/proyecto_papers/ollama && docker compose restart"
```

## Fase 1 — Examen API (FastAPI skeleton)

REST API que orquesta upload, clasificación, ranking y chat con el LLM.

### Endpoint público

- URL: `https://examen-api.your-vps.example.com`
- Header: `X-API-Key: REPLACE_API_KEY` (misma key que Ollama)
- OpenAPI: `GET /openapi.json` · Swagger UI: `GET /docs`

### Endpoints

| Método | Path | Descripción |
|---|---|---|
| `GET`  | `/health` | Liveness |
| `GET`  | `/` | Info del servicio |
| `POST` | `/papers` | Upload PDF (multipart `file`). Devuelve `job_id` + `paper_id` + `stream_url` |
| `GET`  | `/papers?limit&min_score` | Lista paginada |
| `GET`  | `/papers/:paper_id` | Detalle con `score_breakdown` |
| `GET`  | `/ranking?top` | Top-N por weighted score |
| `GET`  | `/jobs/:job_id` | Estado de un job |
| `GET`  | `/stream?job_id=opcional` | SSE — con `job_id` emite transiciones del job, sin él emite heartbeats |
| `POST` | `/chat` | Proxy a Ollama (red interna, no expone API key del LLM) |

### Componentes en el VPS

| Pieza | Path |
|---|---|
| Container FastAPI | `/root/proyecto_papers/examen-api/` |
| vhost nginx | `/root/stack/data/nginx/conf.d/09-examen-api.conf` |
| Red interna | `stack_web` (junto a `ollama`, `mongodb`, `minio`) |

### Postman collection

`infra/postman/examen-api.postman_collection.json` — 12 requests con flujo de demo:

1. Health + root + OpenAPI
2. List papers / Get by id / Ranking (mock data en Fase 1)
3. POST /papers con PDF adjunto → guardar `job_id`
4. Stream SSE con `job_id` → ver 5 eventos `job.progress` + 1 `job.completed`
5. Job status final
6. Chat (proxy a Ollama)
7. Auth-fail (401)

### Estado actual del API (Fase 2 — persistencia real)

- `POST /chat` y `GET /stream` son **funcionales** (proxy real + SSE con poll a Mongo).
- **Persistencia real**: Mongo (`examen_api.papers`, `examen_api.jobs`) + MinIO (`examen-parcial/examen-api/uploads/<paper_id>.pdf`).
- En startup el API:
  - Crea índices (`paper_id` unique, `score_final`, `score_breakdown.weighted` desc, `job_id` unique).
  - Asegura el bucket MinIO.
  - Hace seed de 3 papers reales del corpus **solo si la colección está vacía** (idempotente).
- `POST /papers`: guarda el PDF en MinIO con key `examen-api/uploads/<paper_id>.pdf`, inserta el job en Mongo, lanza la simulación de stages.
- `GET /papers`, `/papers/:id`, `/ranking`, `/jobs/:id`: leen de Mongo. `/stream` polea el job cada 1s y emite cada transición.
- Lo que **todavía es mock**: el paper resultante tras un upload tiene `score_final=3` fijo. Fase 3 reemplaza `_simulate_job_progress` por el pipeline real (PyMuPDF + SBERT + score híbrido). Fase 4 agrega Ollama justification post-scoring.

### Tabla de variables de entorno

| Variable | Default | Para qué |
|---|---|---|
| `OLLAMA_URL` | `http://ollama:11434` | Upstream de `/chat` (red interna) |
| `OLLAMA_DEFAULT_MODEL` | `qwen2.5:1.5b` | Modelo si el request no lo especifica |
| `MONGO_URI` | `mongodb://admin:REPLACE_PASSWORD@mongodb:27017/?authSource=admin` | Conexión Mongo |
| `MONGO_DB` | `examen_api` | DB para `papers` + `jobs` |
| `MINIO_ENDPOINT` | `minio:9000` | S3 endpoint interno |
| `MINIO_BUCKET` | `examen-parcial` | Bucket compartido con classifier-g3 |
| `MINIO_PREFIX` | `examen-api/uploads` | Prefijo del API dentro del bucket |

### Por qué la arquitectura es así

- **Cert wildcard `*.your-vps.example.com`** ya existe → no hay que tocar certbot para nuevos subdomains.
- **API key vía nginx `if ($http_x_api_key != ...)`** → auth en el reverse proxy, Ollama nunca ve requests sin autorizar.
- **Sin publicar puerto al host** → el container es accesible solo desde la red interna del stack y desde nginx; no se expone 11434 al internet.
- **`proxy_buffering off`** → necesario para que el streaming NDJSON / SSE de Ollama llegue en chunks reales al cliente.
- **`resolver 127.0.0.11`** → nginx re-resuelve la IP del container Ollama si se recrea, evita 502 stuck.
