# Routiq — Despliegue en VPS Hostinger (routiq.com.mx)

> Guía 100 % verificada para Ubuntu 24.04 LTS + Hostinger.
> Stack producción: Docker (FastAPI + MongoDB) + Nginx + Let's Encrypt + frontend React buildeado.

---

## 🎯 Arquitectura final en producción

```
                  ┌────────────────────────────────────┐
   Internet ─────►│  Nginx (host) :80 :443 (SSL/TLS)   │
                  └────────────┬───────────────────────┘
                               │ reverse proxy
              ┌────────────────┼─────────────────────┐
              │                │                     │
              ▼                ▼                     ▼
     /  → /var/www/routiq   /api/  → 127.0.0.1:8001       (futuro: /wa/  → 127.0.0.1:3030)
        (build estático)        (Docker FastAPI)              (Docker Baileys, fase 2)
                                       │
                                       ▼
                              127.0.0.1:27017 (Docker MongoDB con volumen persistente)
```

> Beneficio: frontend y backend mismo origen `https://routiq.com.mx` → cookies seguras sin CORS.

---

## ✅ Pre-requisitos (ya confirmados por ti)
- VPS Hostinger Ubuntu 24.04 LTS, IP `177.7.36.75`
- DNS apuntado:
  - `routiq.com.mx` → A → `177.7.36.75`
  - `www.routiq.com.mx` → A → `177.7.36.75`
  - `api.routiq.com.mx` → A → `177.7.36.75`
  - `wa.routiq.com.mx` → A → `177.7.36.75` (para fase Baileys)
- Email SSL: `arturogtz@servicetourmexico.com`
- Acceso vía PowerShell de Windows con contraseña inicial

---

## 📦 Fase 0 — Generar tu llave SSH (Windows PowerShell)

Abre **PowerShell** en tu PC y ejecuta:

```powershell
# 1. Generar llave Ed25519 (más segura que RSA, más rápida)
ssh-keygen -t ed25519 -C "arturogtz@servicetourmexico.com"
# Cuando pregunte "Enter file" → presiona Enter (default ~\.ssh\id_ed25519)
# Cuando pregunte "passphrase" → MUY recomendado escribir una (mínimo 12 caracteres)

# 2. Copiar tu llave pública al VPS (te pedirá la contraseña UNA última vez)
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@177.7.36.75 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

# 3. Probar que entras SIN contraseña
ssh root@177.7.36.75
```

Si la prueba (#3) entra sin pedir contraseña, ¡perfecto! Sigue a la Fase 1.

> 💡 Si ya entras con la llave, recuerda: **conserva el archivo `id_ed25519`** (sin extensión). Si lo pierdes, perderás acceso al VPS.

---

## 🛠️ Fase 1 — Bootstrap del servidor (1 sola vez)

Una vez dentro del VPS por SSH:

```bash
# Sube los scripts de Routiq al servidor (ver Fase 2 más abajo PRIMERO)
# Luego, ya con los scripts en /opt/routiq:

cd /opt/routiq/deploy/scripts
chmod +x *.sh
sudo ./01-server-bootstrap.sh
```

El script `01-server-bootstrap.sh` hace, en orden:
1. Actualiza Ubuntu (`apt update && upgrade`)
2. Configura firewall (`ufw`) — solo permite **SSH(22), HTTP(80), HTTPS(443)**
3. Instala `fail2ban` (protege SSH contra fuerza bruta)
4. Crea **2 GB de swap** (recomendado en VPS pequeños)
5. Instala **Docker + docker-compose-plugin**
6. Instala **Nginx** + **Certbot** (Let's Encrypt)
7. Crea usuario `routiq` (sin sudo, dueño de la app)
8. Configura **timezone** America/Mexico_City

⏱️ Duración: ~3-5 minutos.

---

## 📤 Fase 2 — Subir el código de Routiq al VPS

Tienes 3 opciones, **en orden de preferencia**:

### Opción A — GitHub (recomendada, permite updates fáciles después)
1. En tu chat de Emergent, usa el botón **"Save to GitHub"**.
2. En el VPS (como `root`):
   ```bash
   apt install -y git
   cd /opt
   git clone https://github.com/TU_USUARIO/TU_REPO.git routiq
   cd routiq
   ```

### Opción B — SCP (sin GitHub)
Desde tu PC PowerShell, en la carpeta donde tengas el código:
```powershell
# Comprime localmente (necesitarás haber descargado el .zip de Emergent primero)
# Luego sube:
scp routiq.zip root@177.7.36.75:/opt/
ssh root@177.7.36.75
cd /opt && apt install -y unzip && unzip routiq.zip -d routiq && cd routiq
```

### Opción C — Rsync (continuo, ideal para iterar)
```powershell
rsync -av --exclude node_modules --exclude __pycache__ ./ root@177.7.36.75:/opt/routiq/
```

---

## 🚀 Fase 3 — Despliegue automatizado

Una vez con los archivos en `/opt/routiq` y bootstrap hecho:

```bash
cd /opt/routiq/deploy/scripts
chmod +x *.sh

# 1) Configura variables de producción
cp /opt/routiq/deploy/.env.example /opt/routiq/deploy/.env
nano /opt/routiq/deploy/.env
# Cambia: JWT_SECRET (genera uno nuevo), passwords, etc. Guía dentro del archivo.

# 2) Despliega
sudo ./03-deploy-routiq.sh
```

El script `03-deploy-routiq.sh`:
1. Buildea el frontend React con `REACT_APP_BACKEND_URL=https://routiq.com.mx`
2. Lo copia a `/var/www/routiq/`
3. Levanta Docker Compose (backend FastAPI + MongoDB con volumen persistente)
4. Configura Nginx (sin SSL todavía, solo HTTP)
5. Verifica que el backend responde en `127.0.0.1:8001/api/`

⏱️ Duración: ~5-8 minutos (yarn build tarda).

---

## 🔒 Fase 4 — Habilitar SSL con Let's Encrypt

```bash
sudo ./04-ssl-setup.sh
```

Ejecuta automáticamente:
```
certbot --nginx -d routiq.com.mx -d www.routiq.com.mx -d api.routiq.com.mx \
        --email arturogtz@servicetourmexico.com --agree-tos --redirect --non-interactive
```

Resultado: tu sitio sirve en **HTTPS** con renovación automática (cron de certbot).

✅ Visita `https://routiq.com.mx` y deberías ver la landing.
✅ Login con `admin@aventurate.mx` / `Demo2026!` debe funcionar.

---

## 🔐 Fase 5 — Endurecer SSH (DESPUÉS de confirmar que entras con llave)

> ⚠️ **NO ejecutes esto antes de la Fase 0** — quedarías fuera del VPS si tu llave SSH no funciona.

```bash
sudo ./02-harden-ssh.sh
```

Este script:
- Deshabilita login con contraseña (solo llave SSH)
- Deshabilita login directo de root (te creará un usuario `arturo` con sudo, opcional)
- Cambia el puerto SSH al **22022** (opcional pero muy recomendado contra bots)
- Reinicia el servicio sshd

Después de ejecutarlo, conéctate con:
```powershell
ssh -p 22022 root@177.7.36.75
```

---

## 🧰 Mantenimiento — Comandos útiles

```bash
# Ver logs del backend en tiempo real
docker compose -f /opt/routiq/deploy/docker-compose.yml logs -f backend

# Ver logs de Nginx
tail -f /var/log/nginx/routiq.error.log

# Reiniciar backend
docker compose -f /opt/routiq/deploy/docker-compose.yml restart backend

# Backup manual de MongoDB
sudo /opt/routiq/deploy/scripts/05-backup-mongo.sh

# Actualizar Routiq tras cambios (git pull o subir archivos nuevos)
sudo /opt/routiq/deploy/scripts/04-update.sh
```

---

## 🆘 Troubleshooting rápido

| Síntoma | Causa probable | Fix |
|---|---|---|
| 502 Bad Gateway | Backend cayó | `docker compose logs backend` para ver error |
| Login no guarda sesión | Cookies bloqueadas | Verifica que estás en HTTPS (no HTTP) |
| `Certbot fallo` | DNS aún no propagado | Espera 10-30 min y re-ejecuta. `dig routiq.com.mx` debe devolver `177.7.36.75` |
| Frontend muestra "Network Error" | `REACT_APP_BACKEND_URL` mal | Re-ejecuta `03-deploy-routiq.sh` |
| Mongo no persiste | Volumen mal montado | Verifica `docker volume ls | grep routiq_mongo` |

---

## 📞 Soporte

Si algo falla en el despliegue, comparte conmigo:
1. La salida del comando que falló (copia-pega completo).
2. `docker compose -f /opt/routiq/deploy/docker-compose.yml ps` (para ver estado de contenedores).
3. `tail -n 50 /var/log/nginx/error.log`

Y te ayudo a diagnosticar.
