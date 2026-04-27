#!/usr/bin/env bash
# ============================================================
# Routiq — 01-server-bootstrap.sh
# Prepara un VPS Ubuntu 24.04 limpio para correr Routiq.
# Idempotente: puedes correrlo de nuevo sin romper nada.
# ============================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "❌ Este script debe correr como root.   Usa: sudo $0"
  exit 1
fi

echo "▶ 1/9 Actualizando paquetes del sistema…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y curl wget gnupg lsb-release ca-certificates software-properties-common \
                   ufw fail2ban htop tmux unzip git nano jq

echo "▶ 2/9 Configurando timezone America/Mexico_City…"
timedatectl set-timezone America/Mexico_City || true

echo "▶ 3/9 Configurando firewall (ufw)…"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable

echo "▶ 4/9 Configurando fail2ban (protección SSH)…"
cat >/etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled = true
port = 22,22022
filter = sshd
logpath = /var/log/auth.log
maxretry = 5
findtime = 600
bantime = 3600
EOF
systemctl enable --now fail2ban
systemctl restart fail2ban

echo "▶ 5/9 Creando swap de 2GB (recomendado en VPS pequeños)…"
if ! swapon --show | grep -q '/swapfile'; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "vm.swappiness=10" >> /etc/sysctl.conf
  sysctl vm.swappiness=10
fi

echo "▶ 6/9 Instalando Docker + docker compose…"
if ! command -v docker &> /dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi
docker --version
docker compose version

echo "▶ 7/9 Instalando Nginx + Certbot…"
apt-get install -y nginx certbot python3-certbot-nginx
systemctl enable --now nginx

# Quitar el sitio default (libera puerto 80 para Routiq)
rm -f /etc/nginx/sites-enabled/default

echo "▶ 8/9 Instalando Node.js LTS (necesario para buildear el frontend)…"
if ! command -v node &> /dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
  npm install -g yarn
fi
node --version
yarn --version

echo "▶ 9/9 Creando usuario 'routiq' (sin sudo, dueño de la app)…"
if ! id -u routiq &>/dev/null; then
  useradd -m -s /bin/bash routiq
  usermod -aG docker routiq
fi

mkdir -p /var/www/routiq
chown -R routiq:routiq /var/www/routiq
mkdir -p /opt/routiq
chown -R routiq:routiq /opt/routiq

echo
echo "✅ Bootstrap completo."
echo "   - Firewall: SSH(22) + HTTP(80) + HTTPS(443) abiertos"
echo "   - Docker, Nginx, Certbot, Node 20 + Yarn instalados"
echo "   - Usuario 'routiq' creado con acceso a Docker"
echo "   - 2GB de swap activos"
echo
echo "Siguiente paso: subir el código de Routiq a /opt/routiq y ejecutar 03-deploy-routiq.sh"
