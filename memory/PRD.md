# Routiq — PRD (Product Requirements Document)

## Contexto
Plataforma SaaS PWA multi-tenant para **cotización y seguimiento turístico** para tour operadores receptivos / DMCs en Latinoamérica.
- Empresa piloto: **Aventúrate por Jalisco**
- Marca: **Routiq**
- **Producción: https://routiq.com.mx** ✅ (VPS Hostinger 177.7.36.75, Docker + Nginx + Let's Encrypt)
- Iteración actual: **v1.1** (logo + multi-room + IA + público)

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
### P0 — siguientes
- [ ] **Servicios a la carta**: tours sueltos, traslados, accesos a recintos, extras opcionales agregables a cualquier cotización (nuevos catálogos + UI de "Agregar servicio" en quotation builder + detalle)
- [ ] **Stripe**: cobro total o parcial, modificación de precio y descuentos directos desde la cotización, enlace de pago enviable por WhatsApp o correo

### P1
- [ ] **Integración Baileys real** (microservicio Node.js en VPS): conexión QR, persistencia, envío real desde el inbox
- [ ] CRUD UI completo para paquetes (hoy solo lectura desde seed)
- [ ] Carga masiva de catálogos vía Excel
- [ ] Notificaciones push web (VAPID, scaffolding ya listo)
- [ ] Subdominios reales por empresa (empresa1.routiq.com.mx)
- [ ] Cron de cotizaciones estancadas

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
