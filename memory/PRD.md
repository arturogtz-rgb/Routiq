# Routiq — PRD (Product Requirements Document)

## Contexto
Plataforma SaaS PWA multi-tenant para **cotización y seguimiento turístico** para tour operadores receptivos / DMCs en Latinoamérica.
- Empresa piloto: **Aventúrate por Jalisco**
- Marca: **Routiq**
- **Producción: https://routiq.com.mx** ✅ (VPS Hostinger 177.7.36.75, Docker + Nginx + Let's Encrypt)
- Iteración actual: **v1.4** (fixes UI + mejoras del constructor: noches extra, unidades de servicio, fechas ES, días de salida)

## Arquitectura
- **Frontend:** React 19 + Tailwind + dnd-kit + PWA
- **Backend:** FastAPI + MongoDB (motor) + bcrypt + PyJWT + reportlab + emergentintegrations
- **IA:** Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) via Emergent Universal LLM Key
- **Auth:** JWT custom (cookies httpOnly secure samesite=none)
- **Multi-tenant:** aislamiento por `tenant_id`

## Roles
- `super_admin`: dueño SaaS, panel Master, gestiona tenants
- `company_admin`: admin empresa, pricing, equipo, catálogos, logo
- `executive`: ventas, cotizaciones, kanban

## Implementado en v1.0 (Producción, abr-2026)
- Landing vertical, Auth multi-tenant, Panel Master, Dashboard empresa
- Catálogo paquetes, Motor de precios configurable, Constructor cotización wizard
- Kanban 6 estados drag-drop, Lista cotizaciones, Gestión equipo
- PDF profesional, WhatsApp Inbox mock, PWA completo

## Implementado en v1.1 (jun-2026) — listo para deploy
- ✅ **Logo por empresa**: upload PNG/JPG/SVG/WEBP (max 2MB) desde Ajustes, visible en sidebar, PDF de cotización y página pública del cliente. Servido via `/api/uploads/logos/{tenant_id}.{ext}` (StaticFiles montado bajo /api para pasar el ingress).
- ✅ **Habitaciones múltiples**: rooms[] con combinación libre (ej: 2 dobles + 1 triple = 7 adultos). Pricing engine recalcula correctamente. PDF muestra desglose por habitación. Back-compat con cotizaciones legacy (formato `pax.adultos/ocupacion`).
- ✅ **IA operativa (Claude Sonnet 4.5)**:
  - `POST /api/ai/quotations/{id}/next-step` — sugiere próximo paso al ejecutivo
  - `POST /api/ai/quotations/{id}/missing-fields` — detecta campos faltantes (JSON array)
  - `POST /api/ai/quotations/{id}/client-message` — redacta mensaje WhatsApp en español
  - `POST /api/ai/chat-summary` — resumen de chat (wireado al botón del WhatsApp Inbox)
- ✅ **Enlace público de cotización**: `POST /api/quotations/{id}/public-link` genera token (válido 7 días). Página `/q/:token` sin auth muestra cotización con branding de la empresa, itinerario, total y botón "Confirmar y reservar" que mueve el estado a `ganada` automáticamente. Revocable.

## Testing v1.1
- Backend: 18/19 ✅ (resuelto el único fallo: ingress no enrutaba `/uploads/` → movido a `/api/uploads/`)
- Frontend: 100% smoke ✅ tras el fix
- Reporte: `/app/test_reports/iteration_2.json`

## Backlog priorizado para v1.2 (próxima iteración tras feedback)
### P1 — backlog priorizado
- [x] **Backup MongoDB cron + descarga desde Master** ✅ (jun-2026): script `deploy/scripts/06-backup-mongo.sh` (mongodump gzip diario, retención 7 días en volumen `mongo_backups` y en host `/var/backups/routiq`). El volumen se monta **read-only** en el backend (`/backups`) y el Super Admin descarga el último respaldo sin SSH desde `/master/companies` (`GET /api/backups`, `GET /api/backups/latest/download`, con guardas anti path-traversal y rol super_admin). Cron a activar por el usuario: `0 3 * * * /opt/routiq/deploy/scripts/06-backup-mongo.sh >> /var/log/routiq-backup.log 2>&1`.
- [x] **Deploy de Baileys integrado** ✅ (jun-2026): servicio `baileys` añadido a `deploy/docker-compose.yml` (red `routiq_net`, volumen `baileys_auth`, sin puertos públicos, `WEBHOOK_URL=http://backend:8000`); backend recibe `BAILEYS_URL`, `BAILEYS_SHARED_SECRET`, `TURNSTILE_SECRET_KEY`, `PUBLIC_LOGIN_URL`; `05-update.sh` recrea `backend baileys`; `.env.example` documentado.
- [ ] **Carga masiva de catálogo vía Excel** (P1 #4): template descargable (paquetes/tours/traslados) + import.
- [ ] **Limpiar clave secreta de Stripe (centinela)** (P1 #5) desde Ajustes.

### P2 — futuro
- Gmail OAuth **por empresa** (Client ID/Secret en Ajustes→Correo, flujo OAuth por tenant).
- Multi-moneda USD completa por empresa.

### P0 — siguientes
- [x] **KPI de conversión del funnel (Master)** ✅ (jun-2026, iter_16): tira de 4 tarjetas en `/master/companies` (Solicitudes del mes → Aprobadas → Empresas activas → % Conversión). `GET /api/tenant-requests/metrics`.
- [x] **WhatsApp real (Baileys)** ✅ (jun-2026, iter_16): microservicio Node.js en `/app/baileys-service` (Docker, multi-sesión por número, QR, persistencia en volumen, envío/recepción) + router `routes/whatsapp.py` en FastAPI que actúa de **proxy seguro** (connect/qr/status/logout/send) y **webhook** entrante protegido por `BAILEYS_SHARED_SECRET`. Inbox `/app/whatsapp` reescrito: barra multi-número con estado, conexión por QR (modal), lista de chats, conversación en tiempo real (polling), envío real y resumen IA. Mensajes en `whatsapp_messages` (idempotentes por message_id, índices + aislamiento por tenant). **El microservicio se despliega en el VPS** (instrucciones en `/app/baileys-service/README.md`); en preview `BAILEYS_URL` está vacío → connect/send devuelven 503/502 (degradación controlada). Falta: el usuario despliega el contenedor en su VPS.
- [x] **Seguridad del funnel + historial de solicitudes (Master)** ✅ (jun-2026, iter_15): `POST /api/signup` con rate-limit por IP (5/h, 20/día, `signup_attempts` TTL 24h), honeypot y **Cloudflare Turnstile ENCHUFADO** (llaves reales del usuario en `.env`; widget bound a `routiq.com.mx` → en preview no valida, en producción sí). Historial con filtro en `/master/companies`.
- [x] **Funnel de registro autoservicio (nuevos tenants)** ✅ (jun-2026, iter_14): CTA "Comenzar" en cada plan de la landing → `/signup?plan=` con el plan preseleccionado. Página pública `/signup` (empresa, admin, correo, teléfono, plan, contraseña propia). `POST /api/signup` crea una solicitud `pending`. El Master ve "Solicitudes de registro" en `/master/companies` y puede **Aprobar** (slug auto-generado editable, crea empresa+admin con el plan y sus PLAN_DEFAULTS, devuelve credenciales en modal + correo de bienvenida best-effort) o **Rechazar** (motivo interno). El nuevo admin entra con el correo/contraseña que eligió. `login_url` configurable via `PUBLIC_LOGIN_URL`; el `password_hash` de la solicitud se borra al decidir. Endpoints: `POST /signup`, `GET /tenant-requests`, `GET /tenant-requests/count`, `POST /tenant-requests/{id}/approve|reject`.
- [x] **Control de planes por empresa (Master)** ✅ (jun-2026, iter_13): el Super Admin asigna plan (Starter/Pro/Enterprise) por tenant desde `/master/companies` → botón "Plan" → modal con presets que aplican límite de ejecutivos + toggles (IA, Stripe, Transferencia, White-label). `PATCH /api/companies/{id}/plan` (PLAN_DEFAULTS en deps.py). El Tenant respeta el límite: banner de uso "X de Y ejecutivos" en `/app/team`, botón "Invitar" deshabilitado y aviso de upgrade al alcanzarlo; backend devuelve 403 al exceder (`POST /users/invite-executive`).
- [x] **Email SMTP por empresa** ✅ (jun-2026, iter_13): selector de proveedor (Resend/SMTP) en Ajustes → sección SMTP (host, puerto, TLS, usuario, contraseña/app-password, remitente) + botón "Probar" (`POST /api/companies/me/test-smtp`). `send_email` usa SMTP via aiosmtplib cuando el proveedor del tenant es 'smtp'. Gmail OAuth queda pendiente (esperando credenciales del usuario).
- [x] **Servicios a la carta** ✅ (jun-2026): catálogo (tour/traslado/acceso/extra) con precio neto y público; el motor de precios autocalcula público = neto/divisor; seleccionables en el constructor (paso "Servicios"), visibles en PDF, detalle y enlace público. CRUD admin-only en `/app/services`. Tests: iteration_3 (13/13 backend + 3/3 frontend).
- [x] **Stripe** ✅ (jun-2026): cobro total o anticipo (% configurable) desde el enlace público; descuento (%/fijo) por cotización desde el detalle; al pagar la cotización pasa a `ganada` y `payment_status`=paid/partial. Llaves Stripe POR EMPRESA (cada tenant conecta su cuenta) configurables desde Ajustes → "Pagos e integraciones"; fallback a llave de prueba de plataforma. Webhook `/api/webhook/stripe` + polling resiliente (con fallback al registro local). Tests: iteration_4/5 (15/15). **Limitación de entorno preview**: el proxy `sk_test_emergent` no entrega webhooks de vuelta → la confirmación automática solo ocurre con la llave propia del cliente (con ella el polling confirma directo). Botón manual "Ya pagué, verificar pago" como respaldo.
- [x] **Integraciones por empresa (cero SSH)** ✅: Ajustes → moneda base (MXN/USD), % anticipo, llaves Stripe (pk/sk), API key Resend + remitente, correo de avisos. Endpoint `GET/PATCH /api/companies/me/integrations` con secretos enmascarados.
- [x] **Tipo de cambio automático** ✅: `GET /api/exchange-rate` (open.er-api.com, caché 6h). El enlace público muestra el equivalente en USD cuando la moneda base es MXN.
- [x] **Notificaciones** ✅ (parcial): email automático al ejecutivo/admin al aceptar o pagar (vía Resend, dispara cuando hay API key configurada) + centro de notificaciones in-app (campana con badge en el AppShell, `/api/notifications`). **Falta**: Web Push (VAPID + service worker) — ver P1.

### P0 — pendientes (solicitados por el usuario, arquitectura "todo desde panel")
- [x] **Panel Master — Editor del Index/landing** ✅ (jun-2026): textos (hero, características, CTA final), imágenes (hero + "cómo funciona") y vista previa antes de publicar. Borrador vs publicado. `/master/site`. Endpoints `/api/site-settings*`. Tests: iteration_6 (15/15 backend).
- [x] **Panel Master — Editor de la página de login** ✅: logo, color principal, frase, autor, badge y textos de bienvenida; vista previa + publicar.
- [x] **Web Push (VAPID)** ✅: claves VAPID autogeneradas, suscripción por usuario, envío al aceptar/pagar; toggle en la campana de notificaciones; service worker con handlers push/notificationclick. (En navegadores reales con permiso concedido; el entorno headless bloquea el permiso de notificaciones.)
- [x] **WhatsApp "Enviar con un clic"** ✅: en el detalle de cotización, botón "Enviar cotización por WhatsApp" y "Enviar enlace de pago por WhatsApp" — mensaje prellenado con folio, nombre del cliente y monto, vía wa.me.

### P1
- [x] **v1.8 — Fase D (refactor + marketing + automatización)** ✅ (jun-2026, tests iteration_12, backend 22/22 + UI 100%, suite total 131 verde): (1) **Refactor de `server.py`** (1559→~685 líneas) en routers modulares `routes/{quotations,public_payments,audit,integrations}.py` + `deps.py` compartido, sin cambios de comportamiento; (2) **Carrusel de logos de empresas afiliadas** en la landing, administrable desde el Panel Master (subir/nombrar logos, mostrar/ocultar y reordenar); (3) **Selector de temas** en el Panel Master: 3 presets (Corporativo/Cálido/Oscuro) + color picker, aplicado a la landing pública **y** al panel de la app vía variables CSS (`--brand-50..900`, `.btn-primary` incluido) para coherencia visual total; (4) botón **"Pagar ahora"** incrustado en correos + **recordatorio automático a 48h** para cotizaciones aceptadas sin pagar (loop en background + endpoint manual `/internal/run-reminders`, solo super_admin). Validación de color hex y guardas de subida de imagen (5MB/mime).
- [x] **v1.7 — Fase C Enlace público y cobro** ✅ (jun-2026, tests iteration_11, backend 9/9 + UI 100%): (8) flujo post-aceptación (aceptar por enlace → estado ganada + notificación push/email al ejecutivo + auditoría "won"); (9) **dos opciones de pago** en el enlace público: A) **Stripe** (tarjeta, total/anticipo), B) **Transferencia bancaria** mostrando datos de la empresa (Banco, Titular, CLABE, Nº cuenta, Cuenta USD, SWIFT/BIC, ABA/Routing, domicilio del banco) configurables en Ajustes→Pagos; el cliente puede recibir los datos por correo y el ejecutivo marca el pago recibido manualmente (`/mark-paid`, con guarda anti-sobrepago); (10) botón **"Enviar a cobrar"** por WhatsApp o correo (`/send-payment`, genera enlace si falta). **Mini-dashboard de Auditoría**: ganadas del mes, monto recuperado, ejecutivo top (`/metrics/audit`).
- [x] **v1.6 — Fase B Cotización** ✅ (jun-2026, tests iteration_10, backend 6/6 + UI 100%): (4) tipo "Servicios a la carta" sin paquete base (tours/traslados/extras, motor de precios solo-servicios); (5) bloques de contacto Agencia/Vendedor + Cliente final/Turista para clientes B2B (no directo), visibles en constructor, detalle y PDF; (6) editar cotización existente (ruta `/app/quotations/:id/edit`, cliente y paquete bloqueados, recálculo automático) + **historial de cambios** por cotización (quién, cuándo, qué); (7) **archivar/eliminar** (soft-delete) con filtro "Ver archivadas" + **página de Auditoría** (`/app/audit`, solo admin) con registro de ganadas/archivadas/restauradas/eliminadas. Auditoría "won" también al aceptar/pagar por enlace público.
- [x] **v1.4 — Fixes + constructor avanzado** ✅ (jun-2026, tests iteration_7, 0 incidencias): campana reubicada a header superior; equivalente USD visible en `/q/:token`; navegación libre entre pasos sin perder datos; fecha **DD MMM YYYY** (ES) en constructor/PDF/público/Kanban/detalle; check-out automático + noches extra (costo por persona/habitación/reservación, desglosado en PDF/público); días de salida permitidos por paquete con advertencia; unidades de cobro en servicios (persona/grupo/día/acceso) con cantidad automática.
- [ ] **CRUD UI completo de paquetes** (próxima iteración): crear/editar/eliminar desde el panel — noches, días de inicio permitidos, hoteles, precios por ocupación y temporadas (hoy solo lectura desde seed). El campo `allowed_start_days` ya existe en el modelo; falta la UI de edición.
- [ ] **Editor del sitio Master — avanzado**: ~~reordenar y mostrar/ocultar secciones de la landing + editor de la sección de precios~~ ✅ (jun-2026, tests iteration_9, backend 9/9 + UI 11/11): pestaña "Secciones y precios" en `/master/site` → reordenar secciones (flechas ↑/↓), mostrar/ocultar (features/how/pricing/final_cta), y editor completo de la sección Precios/Planes (pill, título, subtítulo, planes con nombre/precio/periodo/CTA/beneficios/destacado, agregar/eliminar planes). La landing pública renderiza secciones dinámicamente y oculta enlaces del nav de secciones ocultas. `useSiteContent` con reintentos para evitar caer a defaults por un fetch fallido.
- [ ] **Integración Baileys real** (microservicio Node.js en VPS): conexión QR, persistencia, envío real desde el inbox
- [ ] Carga masiva de catálogos vía Excel
- [ ] Multi-moneda completa por empresa cuando opere en USD como base (arquitectura ya preparada: base_currency + conversión)
- [ ] Subdominios reales por empresa (empresa1.routiq.com.mx)
- [ ] Cron de cotizaciones estancadas + backup MongoDB diario (`06-backup-mongo.sh` ya creado, falta activar)
- [ ] Permitir limpiar la clave secreta de Stripe guardada (sentinela)

### P2
- [ ] Meta API oficial como alternativa a Baileys
- [ ] Calendario post-venta (v2.0)
- [ ] Reportes avanzados por ejecutivo
- [ ] Email transaccional al aceptar enlace público (notifica al admin)

## Decisiones técnicas clave
1. **MongoDB-only** (no Postgres) — multi-tenant via `tenant_id`.
2. **Cookies httpOnly secure samesite=none** — protección XSS.
3. **Same-origin en prod** — frontend y backend en `routiq.com.mx`, sin CORS.
4. **StaticFiles bajo `/api/uploads`** para pasar el ingress K8s y el Nginx de producción que solo enruta `/api/*` al backend.
5. **`emergentintegrations` se instala con `--extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/`** tanto en preview como en VPS (ya en Dockerfile).
6. **EMERGENT_LLM_KEY** universal para Claude — sin gestión de billing Anthropic para el usuario.
7. **Migración automática de logo URLs viejas** (`/uploads/...` → `/api/uploads/...`) en cada startup via `ensure_indexes`.

## Credenciales
Ver `/app/memory/test_credentials.md`. Seed automático en cada startup.

## Despliegue de esta iteración
1. Usuario hace **"Save to GitHub"** en chat de Emergent.
2. En VPS: `cd /opt/routiq && git pull`
3. Editar `/opt/routiq/deploy/.env` y agregar `EMERGENT_LLM_KEY=sk-emergent-fF2A3A42eB149Cc812` al final.
4. `sudo /opt/routiq/deploy/scripts/05-update.sh` (el script ya hace `--force-recreate` que recarga env vars).
