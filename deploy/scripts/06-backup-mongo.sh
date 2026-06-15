#!/usr/bin/env bash
# ============================================================
# Routiq — 06-backup-mongo.sh
# Backup diario de MongoDB con rotación (últimos 7 días).
# Usar con cron:
#   0 3 * * * /opt/routiq/deploy/scripts/06-backup-mongo.sh >> /var/log/routiq-backup.log 2>&1
# ============================================================
set -euo pipefail

DEPLOY_DIR="/opt/routiq/deploy"
ENV_FILE="$DEPLOY_DIR/.env"
set -a; source "$ENV_FILE"; set +a

DATE=$(date +%Y-%m-%d_%H%M)
BACKUP_DIR_LOCAL="/var/backups/routiq"
BACKUP_DIR_CONTAINER="/backups"

mkdir -p "$BACKUP_DIR_LOCAL"

echo "[$(date)] Iniciando backup de MongoDB…"
docker exec routiq-mongo mongodump \
  --db "$DB_NAME" \
  --gzip \
  --archive="$BACKUP_DIR_CONTAINER/routiq-$DATE.gz"

# Copia el archivo del volumen al filesystem del host
docker cp "routiq-mongo:$BACKUP_DIR_CONTAINER/routiq-$DATE.gz" "$BACKUP_DIR_LOCAL/"

# Mantener últimos 7 días tanto en el contenedor (volumen mongo_backups, que el
# Panel Master usa para la descarga sin SSH) como en el host.
docker exec routiq-mongo find "$BACKUP_DIR_CONTAINER" -name 'routiq-*.gz' -mtime +7 -delete

# Mantener últimos 7 días en el host
find "$BACKUP_DIR_LOCAL" -name 'routiq-*.gz' -mtime +7 -delete

echo "[$(date)] ✅ Backup OK → $BACKUP_DIR_LOCAL/routiq-$DATE.gz"
ls -lh "$BACKUP_DIR_LOCAL/routiq-$DATE.gz"
