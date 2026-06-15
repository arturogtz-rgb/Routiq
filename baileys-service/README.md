# Routiq — Microservicio WhatsApp (Baileys)

Microservicio Node.js que conecta números de WhatsApp por **QR**, persiste la
sesión en disco y reenvía los mensajes entrantes al backend de Routiq (FastAPI)
mediante un **webhook protegido con secreto compartido**.

El frontend nunca habla con este servicio directamente: solo el backend de
Routiq lo consume por la red interna de Docker. **No expongas su puerto a
internet.**

---

## 1. Variables de entorno

El microservicio usa:

| Variable                | Descripción                                                        |
|-------------------------|--------------------------------------------------------------------|
| `PORT`                  | Puerto interno (por defecto `3001`).                               |
| `BAILEYS_SHARED_SECRET` | Secreto compartido con el backend. **Debe ser idéntico** en ambos. |
| `WEBHOOK_URL`           | Base del backend FastAPI, ej. `http://backend:8001`.               |
| `AUTH_DIR`              | Carpeta de sesiones persistidas (por defecto `/data/auth`).        |

El backend FastAPI necesita (en `deploy/.env`):

```
BAILEYS_SHARED_SECRET=586784a4d615b6b2df4402ff599e063ef0438f3efc235d5b
```

> `BAILEYS_URL` ya está fijado en `deploy/docker-compose.yml` como
> `http://baileys:3001`; no necesitas declararlo en `.env`.
>
> Genera tu propio secreto en producción:
> `openssl rand -hex 24`
> y pon el **mismo valor** en `BAILEYS_SHARED_SECRET` del backend y del microservicio.

---

## 2. El contenedor ya está integrado en `docker-compose.yml`

El servicio `baileys` **ya viene incluido** en `deploy/docker-compose.yml`, en la
misma red interna (`routiq_net`), con un volumen `baileys_auth` para persistir
las sesiones y **sin puertos publicados** (privado). El backend recibe
automáticamente `BAILEYS_URL=http://baileys:3001` y `BAILEYS_SHARED_SECRET`.

Solo debes definir `BAILEYS_SHARED_SECRET` en tu `deploy/.env` (mismo valor que
usará el backend y el microservicio). El microservicio reenvía los mensajes al
backend en `http://backend:8000` (puerto interno del backend dentro de la red
Docker; el `8001` es solo el mapeo hacia el host).

Definición incluida (referencia):

```yaml
  baileys:
    build:
      context: ../baileys-service
      dockerfile: Dockerfile
    container_name: routiq-baileys
    restart: unless-stopped
    environment:
      PORT: "3001"
      BAILEYS_SHARED_SECRET: ${BAILEYS_SHARED_SECRET}
      WEBHOOK_URL: http://backend:8000
      AUTH_DIR: /data/auth
    volumes:
      - baileys_auth:/data/auth
    networks:
      - routiq_net
    # Sin "ports": accesible SOLO dentro de la red interna.
```

---

## 3. Desplegar (mismo flujo de siempre)

```bash
cd /opt/routiq
git pull
# Edita deploy/.env y agrega BAILEYS_URL y BAILEYS_SHARED_SECRET (ver arriba)
sudo /opt/routiq/deploy/scripts/05-update.sh
```

El script de update reconstruye y recrea los contenedores. El nuevo contenedor
`baileys` se levantará junto a los demás. MongoDB y backend no se ven afectados
(solo el backend recibe 2 variables nuevas).

Verifica que arrancó:

```bash
docker ps | grep baileys
docker logs routiq-baileys --tail 50
# health (desde el host, dentro de la red):
docker exec routiq-backend wget -qO- http://baileys:3001/health
```

---

## 4. Conectar un número (desde la app, sin SSH)

1. Entra como **admin de la empresa** → **WhatsApp Inbox**.
2. **Agregar número** (etiqueta: "Ventas GDL", etc.). Puedes tener varios.
3. Clic en el ícono **QR** del número → escanea con WhatsApp
   (WhatsApp → Dispositivos vinculados → Vincular un dispositivo).
4. Al vincularse, el estado cambia a **Conectado** y empezarás a recibir y
   enviar mensajes desde el inbox.

La sesión queda persistida en el volumen `baileys_auth`, así que sobrevive a
reinicios sin volver a escanear el QR. **Desconectar** borra la sesión.

---

## 5. Notas de seguridad

- El microservicio exige el header `x-baileys-secret` en todas las rutas
  (excepto `/health`). El backend lo envía automáticamente.
- El webhook entrante (`/api/whatsapp/webhook`) en FastAPI también valida el
  mismo secreto.
- **No publiques** el puerto `3001` hacia internet; debe vivir solo en la red
  interna de Docker.

---

## 6. Desarrollo local (opcional)

```bash
cd baileys-service
yarn install
BAILEYS_SHARED_SECRET=dev-secret WEBHOOK_URL=http://localhost:8001 AUTH_DIR=./data node server.js
```
