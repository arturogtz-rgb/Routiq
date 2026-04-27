#!/usr/bin/env bash
# ============================================================
# Routiq — 03-deploy-routiq.sh
# Despliega Routiq en producción:
#   1) Build del frontend React con la URL de producción
#   2) Copia el build a /var/www/routiq
#   3) Levanta backend + MongoDB en Docker
#   4) Configura Nginx (sin SSL aún)
#   5) Verifica que el backend responda
#
# Idempotente: puedes correrlo de nuevo para re-desplegar.
# ============================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "❌ Este script debe correr como root.   Usa: sudo $0"
  exit 1
fi

REPO_DIR="${REPO_DIR:-/opt/routiq}"
DEPLOY_DIR="$REPO_DIR/deploy"
WEB_ROOT="/var/www/routiq"
ENV_FILE="$DEPLOY_DIR/.env"
NGINX_AVAILABLE="/etc/nginx/sites-available/routiq.com.mx.conf"
NGINX_ENABLED="/etc/nginx/sites-enabled/routiq.com.mx.conf"

# --- Validaciones ---
[[ -f "$ENV_FILE" ]] || { echo "❌ No existe $ENV_FILE — copia .env.example a .env y edítalo."; exit 1; }
[[ -d "$REPO_DIR/frontend" ]] || { echo "❌ No existe $REPO_DIR/frontend"; exit 1; }
[[ -d "$REPO_DIR/backend"  ]] || { echo "❌ No existe $REPO_DIR/backend";  exit 1; }

# Cargar variables
set -a; source "$ENV_FILE"; set +a

# Validar JWT_SECRET no es el placeholder
if [[ "$JWT_SECRET" == REEMPLAZA* ]]; then
  echo "❌ Tienes que cambiar JWT_SECRET en $ENV_FILE."
  echo "   Genera uno con:  openssl rand -hex 32"
  exit 1
fi

echo "▶ 1/5 Buildeando frontend React (esto tarda ~3-5 minutos)…"
cd "$REPO_DIR/frontend"

# Override de la env del frontend para producción
cat > .env <<EOF
REACT_APP_BACKEND_URL=$APP_PUBLIC_URL
WDS_SOCKET_PORT=443
ENABLE_HEALTH_CHECK=false
EOF

# Instala deps si no existen
if [[ ! -d node_modules ]]; then
  yarn install --frozen-lockfile
fi

NODE_OPTIONS="--max-old-space-size=2048" yarn build

echo "▶ 2/5 Copiando build a $WEB_ROOT…"
mkdir -p "$WEB_ROOT"
rm -rf "${WEB_ROOT:?}/"*
cp -R "$REPO_DIR/frontend/build/." "$WEB_ROOT/"
chown -R www-data:www-data "$WEB_ROOT"

echo "▶ 3/5 Levantando backend + MongoDB en Docker…"
cd "$DEPLOY_DIR"
docker compose --env-file "$ENV_FILE" up -d --build

echo "   Esperando que el backend esté saludable…"
for i in {1..30}; do
  if curl -fsS http://127.0.0.1:8001/api/ >/dev/null 2>&1; then
    echo "   ✅ Backend responde en 127.0.0.1:8001"
    break
  fi
  sleep 2
  if [[ $i -eq 30 ]]; then
    echo "   ❌ Backend no respondió en 60s. Logs:"
    docker compose --env-file "$ENV_FILE" logs backend --tail=50
    exit 1
  fi
done

echo "▶ 4/5 Configurando Nginx…"
cp "$DEPLOY_DIR/nginx/routiq.com.mx.conf" "$NGINX_AVAILABLE"
ln -sf "$NGINX_AVAILABLE" "$NGINX_ENABLED"

# Test config
nginx -t
systemctl reload nginx

echo "▶ 5/5 Verificación final…"
sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -L "http://routiq.com.mx" || echo "000")
echo "   GET http://routiq.com.mx → HTTP $HTTP_CODE"

echo
echo "✅ Despliegue HTTP completo."
echo "   Frontend:  http://routiq.com.mx (sirve desde $WEB_ROOT)"
echo "   API:       http://routiq.com.mx/api/  (proxy a Docker 127.0.0.1:8001)"
echo
echo "👉 SIGUIENTE PASO: ejecuta  sudo ./04-ssl-setup.sh  para activar HTTPS."
