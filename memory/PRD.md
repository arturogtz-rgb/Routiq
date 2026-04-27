# Routiq — PRD (Product Requirements Document)

## Contexto
Plataforma SaaS PWA multi-tenant para **cotización y seguimiento turístico** dirigida a tour operadores receptivos / DMCs en Latinoamérica.
- Empresa piloto: **Aventúrate por Jalisco**
- Marca: **Routiq**
- **Dominio en producción: https://routiq.com.mx** ✅
- VPS: Hostinger Ubuntu 24.04 LTS, IP `177.7.36.75`

Problema que resuelve: digitalizar el flujo **previo a la venta** (primer contacto → cotización → seguimiento → cierre), complementario a Fareharbor/Bokun que resuelven post-venta.

## Arquitectura en producción
```
Internet → Nginx (host, SSL Let's Encrypt) → /api/  → Docker FastAPI :8001
                                            → /     → /var/www/routiq (build React estático)
Docker MongoDB :27017 (volumen persistente, no expuesta al exterior)
```
- SSL automático con renovación cada 12h via certbot.timer
- Firewall UFW: solo SSH(22) + HTTP(80) + HTTPS(443)
- fail2ban activo, swap 2GB, timezone America/Mexico_City
- SSH solo con llave Ed25519 (passwordauth deshabilitado tras hardening)

## Stack
- **Frontend:** React 19 + React Router 7 + Tailwind + dnd-kit + PWA (manifest + service worker)
- **Backend:** FastAPI + MongoDB (motor) + bcrypt + PyJWT + reportlab
- **Auth:** JWT custom (access 12h + refresh 30d) en cookies httpOnly secure samesite=none
- **Multi-tenant:** aislamiento por `tenant_id` en cada query

## Roles
| Rol | Alcance |
|---|---|
| `super_admin` | Dueño del SaaS. Panel Master. Gestiona tenants. Sin acceso a datos confidenciales. |
| `company_admin` | Admin de la empresa. Configura pricing, gestiona equipo y catálogos. |
| `executive` | Ejecutivo de ventas. Cotiza, da seguimiento, usa Kanban. |

## Implementado en MVP v1.0 ✅ (en producción)
- Landing page vertical (hero + features + how-it-works + pricing + final CTA + footer)
- Auth JWT multi-tenant (login/me/logout/refresh) con cookies httpOnly
- Panel Master Admin: métricas globales + gestión de empresas (crear/suspender)
- Dashboard empresa (4 métricas + cotizaciones recientes)
- Catálogo de paquetes (seed: GDL-Tequila 4 días + PV Lujo 6 días)
- Motor de precios configurable por empresa (margin_divisor, comisiones por canal, descuento menor)
- Constructor de cotización wizard 4 pasos con cálculo automático
- Detalle de cotización + cambio de estado + descarga PDF profesional
- Kanban pipeline 6 estados con drag-drop + alertas días sin movimiento
- Lista de cotizaciones con búsqueda y filtros
- Gestión de equipo (invitar ejecutivos, suspender/reactivar)
- WhatsApp Inbox **UI MOCKED** (mensaje de envío deshabilitado)
- PWA completo: manifest, iconos 192/512, service worker offline
- Seed automático idempotente en cada startup del backend

## Despliegue (completado abr-2026)
- ✅ VPS configurado: Docker, Nginx, Certbot, Node 20, swap, UFW, fail2ban
- ✅ SSH endurecido (solo llave Ed25519, password auth deshabilitado)
- ✅ Repo en GitHub privado (arturogtz-rgb/Routiq)
- ✅ Docker Compose orquesta backend + MongoDB
- ✅ Nginx reverse proxy con SSL Let's Encrypt
- ✅ Auto-renovación SSL via certbot.timer
- ✅ Scripts de mantenimiento: 05-update.sh (deploy futuros), 06-backup-mongo.sh (backup diario)

## Pendiente para próxima iteración (cuando regrese arturogtz con observaciones)
- ✅ **Eliminar badge "Made with Emergent"** del index.html (HECHO en /app/, falta git pull en VPS)
- 📝 Aplicar observaciones que reporte el usuario tras testing
- 📝 Workflow de deploy de cambios documentado:
  1. Cambios en /app/ (Emergent)
  2. Save to GitHub
  3. En VPS: `cd /opt/routiq && git pull && sudo /opt/routiq/deploy/scripts/05-update.sh`

## Backlog priorizado
### P0 — Próximas fases
- [ ] **IA operativa con Claude Sonnet 4.5** (Emergent LLM key): resumen automático de chat, detección de oportunidades, campos faltantes
- [ ] **Integración Baileys real** (microservicio Node.js, fase dedicada): conexión QR, persistencia sesión, webhooks → FastAPI

### P1
- [ ] CRUD UI completo para paquetes (hoy solo lectura/seed)
- [ ] Tipos adicionales de cotización: tours sueltos, traslados, cotización a medida
- [ ] Carga masiva de catálogos vía Excel
- [ ] Notificaciones push web (VAPID)
- [ ] Subdominios reales por empresa (empresa1.routiq.com.mx)
- [ ] Job programado de detección de cotizaciones estancadas

### P2
- [ ] Meta API oficial como alternativa a Baileys
- [ ] Calendario de reservas post-venta (v2.0 — fuera de MVP según prompt)
- [ ] Reportes avanzados por ejecutivo
- [ ] Modo cliente del PDF: enlace público temporal + aceptación con click

## Decisiones técnicas clave
1. **MongoDB-only** (no PostgreSQL como pedía el prompt original) — entorno Emergent nativo + multi-tenant vía `tenant_id`. Sin pérdida funcional.
2. **WhatsApp mockeado en MVP** — Baileys real va en fase dedicada cuando el VPS estuviera listo.
3. **Cookies httpOnly secure samesite=none** — protección XSS y soporte cross-subdomain.
4. **Same-origin en producción** — frontend y backend en `routiq.com.mx`, sin CORS (ruta `/api/` proxy a Docker).
5. **`emergentintegrations` removido del requirements.txt** — paquete interno de Emergent no disponible en PyPI público; no se usa en producción ya que la IA aún no está integrada.

## Credenciales
Ver `/app/memory/test_credentials.md` para credenciales de demo (sembradas en producción mediante seed automático).
