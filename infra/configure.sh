#!/usr/bin/env bash
# infra/configure.sh
#
# Aplica las variables del .env a los archivos de despliegue
# (nginx vhosts + ui/nginx.conf + compose files).
#
# Uso:
#   set -a && source .env && set +a
#   bash infra/configure.sh
#
# Idempotente: ejecutarlo dos veces no hace daño si ya fue aplicado, pero
# tampoco vuelve atrás. Recomendado hacerlo sobre un repo recién clonado.

set -euo pipefail

cd "$(dirname "$0")/.."

# ---------------------------------------------------------------------------
# Validación de variables requeridas
# ---------------------------------------------------------------------------
required=(API_KEY VPS_DOMAIN DB_PASSWORD)
missing=()
for v in "${required[@]}"; do
  if [ -z "${!v:-}" ]; then
    missing+=("$v")
  fi
done

if [ ${#missing[@]} -ne 0 ]; then
  echo "ERROR: faltan variables en el .env: ${missing[*]}" >&2
  echo "       Asegúrate de hacer 'set -a && source .env && set +a' antes." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Archivos a parchar y reemplazos
# ---------------------------------------------------------------------------
files=(
  "infra/nginx/06-ollama-api.conf"
  "infra/nginx/09-examen-api.conf"
  "infra/nginx/10-examen-ui.conf"
  "ui/nginx.conf"
  "ui/docker-compose.yml"
  "infra/ollama/docker-compose.yml"
  "api/docker-compose.yml"
)

# Perl es portable entre macOS y Linux (no necesita el sufijo de sed -i).
for f in "${files[@]}"; do
  if [ ! -f "$f" ]; then
    echo "warn: $f no existe, salteado" >&2
    continue
  fi
  perl -i -pe "
    s/REPLACE_API_KEY/${API_KEY}/g;
    s/REPLACE_PASSWORD/${DB_PASSWORD}/g;
    s/your-vps\.example\.com/${VPS_DOMAIN}/g;
  " "$f"
  echo "  ✓ $f"
done

echo
echo "Configuración aplicada. Próximos pasos en el VPS:"
echo "  1. docker compose up -d --build  (en cada uno de: infra/ollama, api, ui)"
echo "  2. copiar infra/nginx/*.conf al nginx central del stack y reload"
