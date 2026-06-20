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
2. **Stack Docker base** corriendo en una network externa `stack_web` con estos containers ya activos:
   - `mongodb` (puerto 27017 interno, autenticado con `admin`)
   - `minio` (puerto 9000 interno)
   - `nginx` (proxy reverso central) montando configs desde `/root/stack/data/nginx/conf.d/`
3. **Certificado TLS wildcard** (`*.VPS_DOMAIN`) presente en `/etc/letsencrypt/live/VPS_DOMAIN/`. Si no existe: `certbot certonly --dns-* ...`.
4. **DNS con wildcard** apuntando al VPS (ej. DuckDNS `*.tuvps.duckdns.org → IP`).
5. **23+ GB RAM libres** (Ollama qwen2.5:1.5b usa ~1.2 GB, SBERT ~500 MB, etc.).

## Pasos para replicar

### 1. Clonar y configurar

```bash
git clone https://github.com/alexrubenmartinez/papers-classifier-llm.git
cd papers-classifier-llm
cp .env.example .env
$EDITOR .env   # completar VPS_DOMAIN, API_KEY, DB_PASSWORD

# Aplicar las variables a los nginx vhosts y compose files
set -a && source .env && set +a
bash infra/configure.sh
```

El script `infra/configure.sh` reemplaza los placeholders (`REPLACE_API_KEY`, `REPLACE_PASSWORD`, `your-vps.example.com`) en todos los archivos relevantes usando `perl -i -pe` (portable entre macOS y Linux).

### 2. Desplegar en el VPS

```bash
# Subir todo al VPS
rsync -avz --exclude='node_modules' --exclude='dist' --exclude='.angular' \
      ./ root@$VPS_HOST:/root/papers/

# En el VPS
ssh root@$VPS_HOST
cd /root/papers
```

#### 2a. Ollama (~5 min)

```bash
cd infra/ollama
docker compose up -d
docker exec ollama ollama pull qwen2.5:1.5b
```

#### 2b. API (~8 min, incluye descarga de torch CPU + SBERT)

```bash
cd /root/papers/api
docker compose up -d --build
docker logs -f examen-api    # esperar "[startup] SBERT model loaded"
```

#### 2c. UI (~3 min)

```bash
cd /root/papers/ui
docker compose up -d --build
```

#### 2d. nginx vhosts del stack central

```bash
cp /root/papers/infra/nginx/*.conf /root/stack/data/nginx/conf.d/
docker exec nginx nginx -t && docker exec nginx nginx -s reload
```

### 3. Verificar

```bash
# Desde tu máquina local
curl -H "X-API-Key: $API_KEY" https://ollama-api.$VPS_DOMAIN/
# → "Ollama is running"

curl -H "X-API-Key: $API_KEY" https://examen-api.$VPS_DOMAIN/health
# → {"status":"ok","papers":3,"sbert_loaded":true,...}

# UI
open https://examen-ui.$VPS_DOMAIN/
```

## Verificación end-to-end en la UI

1. **Dashboard** carga con tarjetas Bronze/Silver/Gold + donut chart.
2. **Subir un PDF** en `/upload` con `justify=auto` → redirige a `/jobs/:id` con SSE en vivo.
3. **Cambiar tema** en `/config` + "Guardar + Reclasificar" → modal de costo → ranking se reordena.
4. **`/reclassify` con `justify=all`** → modal **danger con doble confirmación** (~11 horas en 2000 papers).
5. **`/chat`** → respuesta de Ollama en ~5–20s (warm).
6. **DevTools → Network**: ninguna request expone `X-API-Key`.

## Estructura del repo

```
.
├── README.md                  # este archivo
├── .env.example               # template — copia a .env y completa
├── api/                       # FastAPI con pipeline SBERT + Mongo + MinIO + Ollama
│   ├── app/
│   │   ├── main.py            # endpoints REST + SSE
│   │   ├── pipeline.py        # PyMuPDF + SBERT + TF-IDF + scoring
│   │   ├── db.py              # Mongo + MinIO clients + seed
│   │   ├── repos.py           # CRUD layer
│   │   └── schemas.py         # Pydantic models
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── requirements.txt
├── ui/                        # Angular 22 standalone + signals
│   ├── src/
│   │   └── app/
│   │       ├── core/          # api/, sse/, toast/, models, theme
│   │       ├── features/      # dashboard, papers, ranking, config, upload, reclassify, jobs, chat
│   │       └── shared/        # ui/, layout/, animations/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── nginx.conf             # proxy /api → examen-api con X-API-Key inyectada
└── infra/
    ├── configure.sh           # aplica .env a los archivos de despliegue
    ├── nginx/                 # 3 vhosts (ollama-api, examen-api, examen-ui)
    ├── ollama/                # docker-compose.yml del container Ollama
    └── postman/               # 2 collections (api + ollama)
```

## Endpoints del API

| Método | Path | Descripción |
|---|---|---|
| GET | `/health` | Liveness + counts |
| GET | `/config` | Query / keywords / weights / thresholds activos |
| PUT | `/config?reclassify=bool` | Actualizar tema (parcial) |
| POST | `/papers?justify=none\|lazy\|auto` | Upload PDF (multipart) |
| GET | `/papers?limit&min_score` | Lista paginada (limit hasta 5000) |
| GET | `/papers/:id` | Detalle con breakdown |
| GET | `/ranking?top=N` | Top-N por weighted |
| POST | `/reclassify?reextract=bool&justify=none\|gold_only\|all` | Reprocesar todo |
| POST | `/justify/:paper_id` | Generar justificación (~15s) |
| POST | `/justify` (body: paper_ids \| top \| min_score) | Batch async |
| GET | `/jobs/:id` | Estado de un job |
| GET | `/stream?job_id=opt` | SSE con job.progress / job.completed |
| POST | `/chat` | Proxy a Ollama (model + messages) |

OpenAPI auto-generado en `https://examen-api.$VPS_DOMAIN/docs` y `/openapi.json`.

## Postman

Importa las dos collections de `infra/postman/`:

- `examen-api.postman_collection.json` — 18 requests organizados como flujo de demo.
- `ollama-api.postman_collection.json` — 7 requests para Ollama directo.

Las collections traen variables `{{baseUrl}}` y `{{apiKey}}` que tienes que configurar en tu environment de Postman.

## Decisiones técnicas clave

- **Auth server-side**: el `X-API-Key` se inyecta en los nginx vhosts y en el nginx interno del container UI. El browser nunca lo ve. Cambiar a token-por-usuario es un cambio aislado a esos `.conf`.
- **SBERT (`all-MiniLM-L6-v2`) pre-descargado al build**: el primer startup del API no requiere internet. El modelo (~80 MB) queda en un volume cacheado.
- **Scoring híbrido configurable sin redeploy**: pesos (keyword/tfidf/sbert) y thresholds (gold_muy/gold_claro/revisar/no_prioritario) viven en Mongo y se editan desde `/config`.
- **Embeddings persistidos en el paper doc**: el reclassify NO recalcula embeddings, solo recompone scores. Reordenar 2000 papers tarda ~1 minuto.
- **Counter atómico** en `examen_api.counters` para `paper_id` — race-safe entre uploads paralelos (Mongo `findOneAndUpdate` con `$inc`).
- **Title extraction multi-línea**: el extractor concatena líneas consecutivas hasta encontrar `abstract`, una línea vacía o un marcador de cierre. Maneja papers cuyo título viene partido en varias líneas.
- **Ollama opcional, asincrónico**: la justificación tiene modos (`none`, `lazy`, `auto`, `gold_only`, `all`) para evitar bloquear con ~11h de generación sobre 2000 papers en CPU.
- **SSE para progreso**: jobs largos (reclassify, justify batch) emiten eventos `job.progress` parseables; la UI los muestra en vivo.

## Operaciones útiles

```bash
# Pull de otro modelo Ollama
ssh root@$VPS_HOST "docker exec ollama ollama pull llama3.2:3b"

# Backup de Mongo
ssh root@$VPS_HOST "docker exec mongodb mongodump --db examen_api --archive" > backup.archive

# Re-procesar todos los PDFs subidos cuando mejoras el extractor
curl -X POST -H "X-API-Key: $API_KEY" "https://examen-api.$VPS_DOMAIN/reclassify?reextract=true"

# Ver logs en vivo del API
ssh root@$VPS_HOST "docker logs -f examen-api"
```

## Dev local de la UI

```bash
cd ui
npm install
npm run start    # http://localhost:4200
```

Para que la UI dev pegue al API de producción, agrega un `proxy.conf.json` que redirija `/api/*` a tu VPS con el header `X-API-Key`. NO commitear ese archivo.

## Troubleshooting

### El build del API tarda mucho

Normal: el primer build descarga torch CPU + sentence-transformers + pre-baja el modelo SBERT. Son ~8 min. Builds subsecuentes son rápidos porque las capas quedan cacheadas.

### El container UI da 500 en `/api/*`

Verifica que el `nginx.conf` del container UI tenga el `X-API-Key` real (no `REPLACE_API_KEY`). El `infra/configure.sh` debería haberlo aplicado.

```bash
docker exec examen-ui grep "X-API-Key" /etc/nginx/conf.d/default.conf
```

### Ollama responde 502

El modelo no está descargado o el container se reinició. Verifica:

```bash
docker exec ollama ollama list
docker logs --tail 20 ollama
```

### El reclassify tarda demasiado con `justify=all`

Es esperado: ~15s por paper en CPU × N papers. La UI muestra el modal danger con tiempo estimado. Para 2000 papers son ~11 horas. Usa `justify=gold_only` (~2.8h) o `justify=lazy`.

### El SBERT no carga al startup

Revisa el volume `hf_cache`:

```bash
docker exec examen-api ls /root/.cache/huggingface
```

Si está vacío, el container va a re-descargar el modelo al arrancar (~30s extra una vez).

### `infra/configure.sh: command not found: perl`

Perl está pre-instalado en macOS y casi todas las distros Linux. Si no lo tienes, instálalo (`brew install perl` o `apt install perl`) o edita los archivos a mano reemplazando los placeholders `REPLACE_API_KEY`, `REPLACE_PASSWORD` y `your-vps.example.com`.

## Licencia

MIT
