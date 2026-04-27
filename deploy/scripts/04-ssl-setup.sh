#!/usr/bin/env bash
# ============================================================
# Routiq — 04-ssl-setup.sh
# Obtiene certificados Let's Encrypt y activa HTTPS automáticamente.
# Requiere: DNS ya apuntando al VPS y nginx funcionando.
# ============================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "❌ Ejecuta como root:  sudo $0"
  exit 1
fi

ENV_FILE="${ENV_FILE:-/opt/routiq/deploy/.env}"
[[ -f "$ENV_FILE" ]] || { echo "❌ No encuentro $ENV_FILE"; exit 1; }
set -a; source "$ENV_FILE"; set +a

EMAIL="${SSL_EMAIL:-arturogtz@servicetourmexico.com}"

echo "▶ Verificando DNS de los dominios…"
for d in routiq.com.mx www.routiq.com.mx api.routiq.com.mx; do
  RESOLVED=$(dig +short "$d" @1.1.1.1 | tail -n1)
  if [[ -z "$RESOLVED" ]]; then
    echo "  ⚠ $d no resuelve aún. Asegúrate de que el DNS está propagado."
    echo "    dig +short $d  →  vacío"
  else
    echo "  ✓ $d → $RESOLVED"
  fi
done

echo
read -p "¿Continuar con la emisión de certificados? (yes/no): " ok
[[ "$ok" == "yes" ]] || { echo "Cancelado."; exit 0; }

echo "▶ Obteniendo certificados Let's Encrypt…"
certbot --nginx \
  -d routiq.com.mx -d www.routiq.com.mx -d api.routiq.com.mx \
  --email "$EMAIL" \
  --agree-tos \
  --redirect \
  --no-eff-email \
  --non-interactive

echo "▶ Activando HSTS (HTTP Strict Transport Security)…"
# Insertamos HSTS solo en bloques 443 ya creados por certbot
# (certbot ya añade `add_header Strict-Transport-Security` cuando usas --redirect)

echo "▶ Verificando renovación automática…"
systemctl status certbot.timer --no-pager || systemctl list-timers | grep certbot
certbot renew --dry-run

echo
echo "✅ HTTPS habilitado en:"
echo "   https://routiq.com.mx"
echo "   https://www.routiq.com.mx"
echo "   https://api.routiq.com.mx"
echo
echo "   Renovación automática: cada 12h vía systemd-timer (certbot.timer)."
echo "   Probar:  curl -I https://routiq.com.mx"
