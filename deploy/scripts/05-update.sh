#!/usr/bin/env bash
# ============================================================
# Routiq — 05-update.sh
# Actualiza Routiq tras cambios en el código.
# Si usas git: hace pull. Si subes archivos por SCP: solo rebuild.
# ============================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "❌ Ejecuta como root:  sudo $0"
  exit 1
fi

REPO_DIR="${REPO_DIR:-/opt/routiq}"
DEPLOY_DIR="$REPO_DIR/deploy"
ENV_FILE="$DEPLOY_DIR/.env"

cd "$REPO_DIR"

if [[ -d .git ]]; then
  echo "▶ Pull desde git…"
  git pull --ff-only
fi

echo "▶ Re-buildeando frontend…"
cd "$REPO_DIR/frontend"
yarn install --frozen-lockfile
NODE_OPTIONS="--max-old-space-size=2048" yarn build
mkdir -p /var/www/routiq
rm -rf /var/www/routiq/*
cp -R build/. /var/www/routiq/
chown -R www-data:www-data /var/www/routiq

echo "▶ Re-buildeando y reiniciando backend + microservicio WhatsApp (baileys)…"
cd "$DEPLOY_DIR"
docker compose --env-file "$ENV_FILE" up -d --build --force-recreate backend baileys

echo "▶ Recargando Nginx…"
nginx -t && systemctl reload nginx

echo
echo "✅ Routiq actualizado."
docker compose --env-file "$ENV_FILE" ps
