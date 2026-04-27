#!/usr/bin/env bash
# ============================================================
# Routiq — 02-harden-ssh.sh
# Endurece la configuración SSH:
#   - Deshabilita login con contraseña (solo llave SSH)
#   - Deshabilita login directo de root (opcional)
#   - Cambia puerto a 22022 (opcional pero recomendado)
#
# ⚠️ IMPORTANTE: Solo ejecutar DESPUÉS de confirmar que entras
# al VPS con tu llave SSH sin pedir contraseña.
# ============================================================
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "❌ Este script debe correr como root.   Usa: sudo $0"
  exit 1
fi

read -p "¿Confirmas que ya pruebas a entrar con llave SSH SIN contraseña? (yes/no): " ok
if [[ "$ok" != "yes" ]]; then
  echo "Aborta. Primero asegúrate de que 'ssh root@IP' funciona sin contraseña."
  exit 1
fi

read -p "¿Quieres cambiar el puerto SSH al 22022 (recomendado)? (y/N): " change_port
read -p "¿Quieres deshabilitar login directo como root? (y/N): " disable_root

# Backup
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak.$(date +%s)

# Deshabilitar password auth (siempre)
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?KbdInteractiveAuthentication.*/KbdInteractiveAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?UsePAM.*/UsePAM yes/' /etc/ssh/sshd_config

# Pubkey
sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config

# Cambiar puerto
NEW_PORT=22
if [[ "${change_port,,}" == "y" ]]; then
  NEW_PORT=22022
  sed -i 's/^#\?Port .*/Port 22022/' /etc/ssh/sshd_config
  ufw allow 22022/tcp comment 'SSH custom'
fi

# Deshabilitar root login
if [[ "${disable_root,,}" == "y" ]]; then
  read -p "Nombre del usuario sudoer que usarás (ej: arturo): " new_user
  if ! id -u "$new_user" &>/dev/null; then
    adduser --gecos "" "$new_user"
    usermod -aG sudo "$new_user"
    mkdir -p /home/"$new_user"/.ssh
    cp /root/.ssh/authorized_keys /home/"$new_user"/.ssh/authorized_keys
    chown -R "$new_user":"$new_user" /home/"$new_user"/.ssh
    chmod 700 /home/"$new_user"/.ssh
    chmod 600 /home/"$new_user"/.ssh/authorized_keys
    echo "✅ Usuario $new_user creado con tu misma llave SSH y permisos sudo."
  fi
  sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
  echo "ℹ️  A partir de ahora entra con: ssh -p $NEW_PORT $new_user@177.7.36.75"
fi

# Validar config
sshd -t

systemctl restart ssh || systemctl restart sshd
echo
echo "✅ SSH endurecido."
echo "   Puerto: $NEW_PORT"
[[ "${change_port,,}" == "y" ]] && echo "   ⚠️  En tu PC: ssh -p 22022 root@177.7.36.75"
echo "   Password auth: DESHABILITADO"
echo "   Backup del config previo: /etc/ssh/sshd_config.bak.*"
