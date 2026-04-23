# Routiq — PRD (Product Requirements Document)

## Contexto
Plataforma SaaS PWA multi-tenant para **cotización y seguimiento turístico** dirigida a tour operadores receptivos / DMCs en Latinoamérica. Empresa piloto: **Aventúrate por Jalisco**. Nombre comercial: **Routiq** (dominio provisional; final: routiq.mx).

Problema que resuelve: digitalizar el flujo **previo a la venta** (primer contacto → cotización → seguimiento → cierre), complementario a Fareharbor/Bokun que resuelven post-venta. WhatsApp sigue siendo el canal #1 pero sin memoria operativa ni pipeline visual.

## Arquitectura
- **Frontend:** React 19 + React Router 7 + Tailwind + shadcn/ui + dnd-kit + PWA (manifest + service-worker.js).
- **Backend:** FastAPI + MongoDB (motor async) + bcrypt + PyJWT + reportlab + slugify.
- **Auth:** JWT custom (access 12h + refresh 30d) en cookies httpOnly `secure` `samesite=none`.
- **Multi-tenant:** aislamiento por `tenant_id` a nivel de query. `super_admin` tiene `tenant_id=None`.

## Roles
| Rol | Alcance |
|---|---|
| `super_admin` | Dueño del SaaS. Panel Master. Gestiona tenants. Sin acceso a datos confidenciales. |
| `company_admin` | Admin de la empresa. Configura pricing, gestiona equipo y catálogos. |
| `executive` | Ejecutivo de ventas. Cotiza, da seguimiento, usa Kanban. |

## Credenciales sembradas (seed idempotente en startup)
| Rol | Email | Password |
|---|---|---|
| super_admin | owner@routiq.mx | Routiq2026! |
| company_admin (Aventúrate) | admin@aventurate.mx | Demo2026! |
| executive (Aventúrate) | ejecutivo@aventurate.mx | Demo2026! |

## Implementado en MVP v1.0 (23-abr-2026)
- ✅ Landing page vertical (hero + features + how-it-works + pricing + final CTA + footer). Paleta Routiq, fuentes Outfit/Manrope, mobile-first.
- ✅ Auth JWT multi-tenant (login/me/logout/refresh) con cookies httpOnly.
- ✅ Panel Master Admin: métricas globales + gestión de empresas (crear tenant + admin en un paso, suspender/reactivar).
- ✅ Dashboard empresa con 4 métricas (activas, conversión, ingresos, proyección) + tabla de cotizaciones recientes.
- ✅ Catálogo de paquetes (2 seeds: GDL-Tequila 4 días y PV Lujo 6 días).
- ✅ Motor de precios configurable por empresa (margin_divisor, comisiones por canal directo/agencia/mayorista/operador, descuento menor). Panel Ajustes para editarlo.
- ✅ Constructor de cotización (wizard 4 pasos: Cliente → Paquete+Hotel → Fechas/Pax → Revisión con total calculado).
- ✅ Detalle de cotización con itinerario + desglose + cambio de estado + descarga de PDF.
- ✅ PDF profesional (reportlab) con branding, itinerario, desglose, comisión, incluye/no incluye, condiciones.
- ✅ Kanban pipeline con 6 estados (Nueva → Cotizando → Enviada → Negociación → Ganada/Perdida) con drag-drop (dnd-kit) y badge "días sin movimiento" ≥3d.
- ✅ Lista de cotizaciones con búsqueda y filtro por estado.
- ✅ Gestión de equipo: invitar ejecutivos, suspender/reactivar.
- ✅ WhatsApp Inbox **UI-only MOCKED** (chats, sub-hilos por cotización, resumen IA placeholder, input deshabilitado hasta fase Baileys).
- ✅ PWA completo: `manifest.json`, iconos 192/512, `service-worker.js` (cache shell + network-first en navegación), theme color #185FA5, mobile-first.
- ✅ Seed automático idempotente en cada arranque (super admin + tenant demo + 2 paquetes + 2 clientes + 6 cotizaciones en distintos estados).

## Testing
- **Backend:** 25/25 ✅ (auth, aislamiento de rol/tenant, CRUD, cálculo de precios verificado numéricamente, PDF válido, métricas).
- **Frontend:** 100% smoke ✅ (landing, login 3 roles, dashboard, kanban, wizard, PDF download, master panel, mobile drawer).
- Reporte: `/app/test_reports/iteration_1.json`.

## Personas objetivo
1. **Carlos, ejecutivo de ventas** — cotiza 20+ veces al día, necesita velocidad y no perder seguimientos.
2. **María, admin de operación** — necesita visibilidad del pipeline y controlar márgenes/comisiones por canal.
3. **Dueño de DMC** — necesita KPIs de conversión y proyección para planear.

## Backlog / Siguientes fases
### P0 — próxima iteración (post-feedback)
- [ ] Integración **Baileys real** (microservicio Node.js en VPS Hostinger del usuario): conexión QR, persistencia de sesión, webhooks a FastAPI, envío real de mensajes y PDFs desde el chat.
- [ ] **IA operativa** con Claude Sonnet 4.5 (Emergent LLM key): resumen automático de chat, detección de oportunidades, campos faltantes.

### P1
- [ ] Tipos adicionales de cotización: Day tours, traslados, cotización a medida.
- [ ] Carga masiva de catálogos vía Excel.
- [ ] Notificaciones push web (VAPID) — scaffolding ya listo en service-worker.
- [ ] Subdominio real por empresa (empresa1.routiq.mx) — hoy usamos login para identificar tenant.
- [ ] Push de cotizaciones estancadas (job programado + notificación).
- [ ] CRUD UI completo para paquetes (ahora solo lectura/seed; creación vía API).

### P2
- [ ] Meta API oficial como alternativa a Baileys para empresas grandes.
- [ ] Calendario de reservas post-venta (v2.0 — fuera de MVP según prompt).
- [ ] Reportes avanzados por ejecutivo.
- [ ] Integración API con aventurateporjalisco.com.

## Decisiones clave
1. **MongoDB solo** (no PostgreSQL como pedía el prompt original). Justificación: entorno Emergent nativo + multi-tenant vía `tenant_id` + índices compuestos. Sin pérdida funcional para el alcance actual.
2. **WhatsApp mockeado en UI** en este MVP. Baileys real va en fase dedicada cuando el VPS del usuario esté listo.
3. **IA diferida a fase 5** para validar primero la UX del flujo de cotización sin complicar.
4. **Cookies httpOnly** (no localStorage) por seguridad contra XSS.
