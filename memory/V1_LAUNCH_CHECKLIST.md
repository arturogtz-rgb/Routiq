# Routiq — Checklist de lanzamiento v1.0
_Última actualización: jun-2026 (iteración 22)_

Documento de referencia para el lanzamiento con los primeros clientes reales.
Cubre: (A) lo implementado, (B) configuración pendiente en producción, (C) backlog P2.

---

## A) ✅ Implementado y probado

### Núcleo / multi-tenant
- [x] Autenticación JWT (cookies httpOnly), roles **Master / Admin / Ejecutivo**.
- [x] Multi-tenant con aislamiento por `tenant_id` en todas las consultas.
- [x] Planes por empresa (Starter / Pro / Enterprise): límites de ejecutivos, IA, white-label, métodos de pago.
- [x] Panel Master: empresas, métricas globales, KPIs de conversión, historial de solicitudes.

### Catálogos y cotizaciones
- [x] CRUD completo de **Paquetes** (nombre, descripción, noches, días de salida, hoteles con precios por ocupación y por temporada, incluye/no incluye, itinerario día a día, imagen).
- [x] Servicios (tours, traslados) y motor de precios dinámicos (margen, comisiones por canal, menores).
- [x] Importación / exportación masiva de catálogos vía **Excel** (openpyxl).
- [x] Generación de cotizaciones, **PDF** (ReportLab), Kanban / pipeline.
- [x] Enlace público de cotización `/q/:token` con pago.

### Crecimiento / prospección
- [x] Funnel de auto-registro de tenants (`/signup`) protegido (Cloudflare Turnstile, honeypot, rate-limit).
- [x] **Vista pública de paquete** `/p/:slug/:code` con branding + lead "Quiero este paquete".
- [x] **Catálogo público por empresa** `/c/:slug` (grilla de paquetes activos).
- [x] **Botón "Compartir catálogo" con QR** (copiar enlace, descargar QR, compartir por WhatsApp).
- [x] Página de **Solicitudes / leads** (`/app/leads`) con aviso in-app + correo y "Crear cotización".

### Comunicación
- [x] Microservicio **WhatsApp (Baileys)** multi-número: conexión por QR, bandeja de entrada, envío/recepción, eliminar número.
- [x] Vinculación de chats de WhatsApp ↔ cotización; envío y cobro por WhatsApp.
- [x] **Resumen IA de chat** (Claude Sonnet vía Emergent LLM Key) — funciona en preview.
- [x] Correo por empresa: SMTP propio / Resend / **Gmail OAuth** por tenant.

### Cuentas y seguridad
- [x] **Recuperación de contraseña por correo** (todos los roles): token de un solo uso, 1h, `/reset-password`.
- [x] **Perfil self-service** (`/profile`): cambiar nombre, correo y contraseña.
- [x] Gestión de equipo: invitar/editar/suspender ejecutivos + enlace de recuperación.
- [x] Master: editar correo/contacto de empresa + reset de contraseña del admin.
- [x] Diferenciación visual Administrador / Ejecutivo + bienvenida por rol.
- [x] **Backups automatizados** de MongoDB (retención 7 días) + descarga desde Master + aviso de respaldo > 24h.

---

## B) ⚙️ Configuración pendiente en PRODUCCIÓN (no código — variables/infra)

> Editar `/opt/routiq/deploy/.env` (o el `.env` del backend) y redeplegar con `05-update.sh`.

| Variable | Estado | Acción |
|---|---|---|
| `EMERGENT_LLM_KEY` | ⚠️ Pendiente | Agregar la llave para activar el **resumen IA**. Si da `FREE_USER_EXTERNAL_ACCESS_DENIED` → recargar saldo en **Profile → Universal Key → Add Balance**. |
| `PLATFORM_RESEND_API_KEY` | ⏳ Cuando tengas la llave | Activa correos de plataforma (reset de contraseña del **Master** + aviso de backup por correo). Mientras tanto: reset del Master por enlace en panel + aviso de backup in-app. |
| `PLATFORM_FROM_EMAIL` | ⏳ | Poner `no-reply@routiq.com.mx` (remitente de plataforma). |
| `SHOW_DEMO_CREDENTIALS` | �е Antes del lanzamiento | Poner `false` para **ocultar las credenciales demo** del login. |
| `BAILEYS_SHARED_SECRET` | ✅ | Ya configurada (no cambiar). Baileys fijado a `6.7.22` por CVE — **no actualizar**. |
| Cron de backup (`06-backup-mongo.sh`) | ⚠️ Verificar | Confirmar que el cron diario corre en el VPS (en preview no corre → el aviso de backup aparece como esperado). |

### Verificación post-deploy (recomendada)
- [ ] Login de los 3 roles funciona en producción.
- [ ] **Resumen IA** genera texto (no `FREE_USER_EXTERNAL_ACCESS_DENIED`).
- [ ] Conexión de un número de WhatsApp por QR.
- [ ] Envío de un correo de prueba (SMTP/Resend/Gmail) desde Ajustes.
- [ ] Recuperación de contraseña (admin/ejecutivo) llega por correo.
- [ ] Vista pública `/p/:slug/:code` y catálogo `/c/:slug` cargan con branding.
- [ ] Verificar HTTPS, dominio y backup descargable desde el Master.

---

## C) 📋 Backlog P2 (post-v1.0)
- [ ] **Multi-moneda USD completa por empresa** (operar con USD como base, no solo equivalencia de tipo de cambio).
- [ ] (Opcional) Refactor de páginas grandes (`Master.jsx`) en subcomponentes.
- [ ] (Opcional) Notificaciones in-app para el Master (bandeja propia) además del correo.

---

## Credenciales demo (ocultar en prod con `SHOW_DEMO_CREDENTIALS=false`)
- Master: `owner@routiq.mx` / `Routiq2026!`
- Admin: `admin@aventurate.mx` / `Demo2026!`
- Ejecutivo: `ejecutivo@aventurate.mx` / `Demo2026!`
