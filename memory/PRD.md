# Routiq — PRD (Product Requirements Document)

## Contexto
Plataforma SaaS PWA multi-tenant para **cotización y seguimiento turístico** para tour operadores receptivos / DMCs en Latinoamérica.
- Empresa piloto: **Aventúrate por Jalisco**
- Marca: **Routiq**
- **Producción: https://routiq.com.mx** ✅ (VPS Hostinger 177.7.36.75, Docker + Nginx + Let's Encrypt)
- Iteración actual: **v2.4** (iter_24: registro de uso/costo de IA en Master + generar respaldo on-demand + revisión de seguridad pre-lanzamiento)

## Iteración 36 (jun-2026) — Correcciones PDF / enlace / catálogo público
1. **Precios por canal (PDF + enlace `/q/:token`):** nunca se muestran todas las ocupaciones por defecto; solo las **seleccionadas** con precio por persona **y total**. Notas por canal: directo (sin nota), agencia ("Precio comisionable"), mayorista/operador ("Precio neto no comisionable"). Checkbox en paso Revisión "Mostrar todas las opciones de ocupación disponibles" (`show_all_occupancies`, off por defecto) → muestra la tabla completa (cotización abierta, precio por persona). Helpers compartidos `occupancy_rows_selected/all` en `pricing.py`.
2. **Hero `/p/:slug/:code`:** la imagen ahora cubre el 100% del área (altura fija + `object-cover absolute inset-0`); se eliminó la franja gris.
3. **Botón "Imprimir" en `/p/:slug/:code`:** `@media print` (Tailwind `print:`) — imprime logo+datos empresa, nombre, descripción, itinerario, Incluye/No incluye; oculta precios, CTA "Quiero este paquete", header de navegación, hoteles y modales.
- Verificado por curl (seleccionadas/todas, notas, PDF 200) y screenshots (hero, botón imprimir, tabla en enlace).

## Iteración 35 (jun-2026) — Fases 2-5 + PDF profesional + Confirmación de Reserva
**Fase 2 (constructor):** al elegir paquete se ocultan los demás (+ "Cambiar paquete"); ocupaciones con precio neto 0 = "no disponible" (ocultas en selects/tarjetas/PDF/enlace); fix selector de Tono.
**Fase 3 (Excel):** plantilla/import/export con itinerario día a día (`dia_1..dia_10`), hojas de servicios por categoría (Tours/Traslados/Accesos/Extras) con `image_url`; importación upsert idempotente e independiente por categoría. Servicios con imagen + import/export desde `/app/services`.
**Fase 4 (público):** catálogo público de servicios `/c/:slug/servicios` por categorías (endpoint `/api/public/company/{slug}/services`); página de condiciones `/c/:slug/condiciones`.
**Fase 5 (textos):** subtítulo del catálogo editable en Ajustes (`catalog_subtitle`).
**Item 9:** Programa Personalizado con toggle por concepto 🔒 Tarifa neta (canal, no comisionable) / 💰 Precio público (comisionable). Mezcla en la misma cotización.
**Item 10/11 (PDF + enlace + condiciones):** PDF rediseñado para los 3 tipos — logo grande, ciudad/fecha de emisión, dirigido a, saludo, itinerario, **tabla de precios por ocupación** (paquetes), Incluye/No incluye, **"Información importante"** (campo libre por cotización), texto fijo de precios, **enlace clickeable a `/c/:slug/condiciones`**, nombre del ejecutivo. TODO replicado en el enlace `/q/:token` (tabla ocupación, información importante, enlace condiciones, ejecutivo). Condiciones separadas en 2 campos (`general_conditions` + `cancellation_policy`) editables en Ajustes.
**Item 12 (Confirmación de Reserva):** documento nuevo desde cotización "Ganada" (`routes/booking.py`): formulario (encabezado, servicios confirmados, hospedaje con N° de confirmación, observaciones, precio/total), PDF dedicado con datos bancarios (banco/beneficiario/cuenta/sucursal/CLABE/SWIFT/referencia), nota Stripe y condiciones completas; envío por correo (PDF adjunto) y WhatsApp (link público por token). Bancarios `sucursal`+`referencia` añadidos en Ajustes→Pagos.
- Tests: `/app/test_reports/iteration_35.json` (backend 17/17 PASS) + `backend/tests/test_iteration35_phases.py`. Regla "PDF == enlace cliente" verificada.
- ⏳ Backlog: % de comisión por cliente; modo vista previa (dry-run) en importación Excel.

## Iteración 34 (jun-2026) — FASE 1: Reescritura del Motor de Precios (PAQUETES = tarifas netas)
- ✅ **Catálogo de PAQUETES guarda TARIFAS NETAS**. `pricing.py`: nuevas `public_from_net(net, divisor)` y `channel_price(net, channel, divisor, commissions)`. Precio Público = neto / `margin_divisor`. `compute_quotation` ahora aplica precio por canal SOLO a items de paquete (hospedaje, noche_extra):
  - **directo / agencia** → Precio Público (sin comisión sobre el paquete).
  - **mayorista** → Público × (1 − `commissions.mayorista`) (configurable). Leyenda "Precio neto no comisionable".
  - **operador (UI: "Mayorista Preferencial")** → Tarifa Neta original. Leyenda "Precio neto no comisionable".
- ✅ **Comisión por canal SOLO sobre servicios a la carta** (lógica de servicios intacta: precio catálogo ya público − comisión por canal). Los paquetes ya traen el precio canalizado y son no comisionables. `subtotal = paquete(canal) + servicios(público)`, `commission = servicios × rate`, `total = subtotal − commission`.
- ✅ **Menores suman al total** (Issue 2): `minor_price` del hotel es neto; mismo cálculo que adultos (público=neto/divisor, luego canal). Habitación con neto 0 = "no disponible" → se omite (Issue 1 parcial — "precio 0 = no disponible").
- ✅ **Catálogo público muestra PRECIO PÚBLICO** (Issue 1): `routes/public_package._base_price` = min(neto)/`margin_divisor` (antes exponía el neto crudo). Aplica a `/c/:slug` y `/p/:slug/:code`.
- ✅ **Builder muestra Neto + Público** (Issue 3): `QuotationBuilder.jsx` fetchea `/companies/me` (divisor+comisiones), `channelPrice`/`publicPrice`; filas de habitación muestran "Neto $X · Público $Y", tarjetas de hotel muestran neto + "Púb $...", totales reflejan lógica por canal + leyenda `builder-price-note`. `price_note` propagado a PDF (`pdf_generator`), detalle (`QuotationDetail` `detail-price-note`) y enlace público (`PublicQuotation` `public-price-note`).
- ✅ **Rename UI "Operador" → "Mayorista Preferencial"** (valor interno `operador` sin migración) en QuotationBuilder, CustomQuotationBuilder, Clients y Ajustes→Precios. **Fix UI selector de Tono** (clases `h-8 py-0` → `text-xs py-1.5`, ya no se recorta) en ambos constructores (Issue 4).
- ⚠️ **Alcance**: el cambio aplica SOLO a paquetes. `compute_custom_quotation` (programa personalizado) y servicios NO se modificaron (siguen público − comisión por canal).
- 🔧 Dato demo: se restauró `margin_divisor` del tenant demo a 0.76 (estaba en 1.25, inválido para el nuevo modelo neto→público).
- Tests: `/app/test_reports/iteration_34.json` (backend 17/17 PASS, frontend labels+leyendas+Revisión verificados) + `backend/tests/test_iteration34_pricing_paquetes.py`.
- ⏳ **Pendiente (próximas fases / P0)**: ocultar paquetes no seleccionados en el constructor; itinerario día a día en plantilla Excel de importación; ¿aplicar la lógica por canal también a "programa personalizado"? (a confirmar con usuario).

## Iteración 33 (jun-2026) — Comparativa vs período anterior + Zona horaria configurable + Limpieza/auditoría
- ✅ **(1) Comparativa vs período anterior** — `routes/stats._compute` ahora consulta 2× el período y devuelve bloques `previous` (revenue/collected/conversion) y `deltas` (% cambio en revenue, collected, created, won, rate; `null`='nuevo' cuando el período previo fue 0, `0.0` cuando ambos 0). En **/app/stats** cada KPI muestra un badge ▲verde/▼rojo con el % (o "nuevo"/"0%"), subtítulo "vs. período anterior". En el **correo automático** cada KPI incluye el mismo indicador (`reports._kpi_html`/`_delta_badge`).
- ✅ **(2) Zona horaria configurable por empresa** — `report_timezone` (default `America/Mexico_City`) en config de Ajustes→Correo (`report-timezone-input`, 10 zonas LatAm/US/ES). `routes/integrations` valida con `ZoneInfo` (ignora inválidas) y persiste `sales_report.timezone`; `reports.run_sales_reports` evalúa cada empresa en su propia zona horaria. Expuesto en `_integrations_view`.
- ✅ **(3) Revisión/limpieza general** — Auditoría de nav y rutas: sin rutas huérfanas (todas las entradas de nav tienen ruta y viceversa), role-gating correcto (ejecutivo no ve Analítica/Ventas/Equipo/Auditoría/Ajustes y es redirigido por `ProtectedRoute`). Renombrado "Pipeline" → **"Embudo"** para consistencia en español. Orden de nav admin verificado: Dashboard→Embudo→Cotizaciones→Clientes→Solicitudes→Analítica→Ventas→Paquetes→Servicios→WhatsApp→Equipo→Auditoría→Ajustes. Flujo de ejecutivo (login→dashboard→crear cotizaciones/embudo/clientes/solicitudes/WhatsApp) intuitivo.
- Tests: `/app/test_reports/iteration_33.json` (backend 12/12, frontend 100%, 0 incidencias) + `backend/tests/test_iteration33_stats_tz.py`.
- ⏳ **Backlog opcional**: BackgroundTask para envío manual del reporte en tenants muy grandes; agregación Mongo `$facet` si crece el volumen.


- ✅ **(1) Resumen automático de ventas por correo** — cada empresa configura desde Ajustes→Correo (`report-section`): activar/desactivar, frecuencia (semanal/mensual), día (semana 0–6 / mes 1–28, con clamp según frecuencia) y hora (0–23, zona América/México_City). Loop de fondo horario (`reports.run_sales_reports`, registrado en `server.py` `_sales_report_loop`) detecta empresas "due" (con de-dupe de 23h vía `sales_report_last_sent_at`) y envía un correo con KPIs (ingresos, cotizaciones creadas, conversión, ejecutivo top) + **Excel adjunto** (reporte completo). Usa el proveedor de correo de la empresa (Resend/SMTP/Gmail) con fallback de plataforma. Botón **"Enviar ahora (prueba)"** → `POST /api/stats/sales/send-report?period=` (devuelve 200 con `{ok, detail}`; mensaje claro en español si el proveedor rechaza). `notifications.send_email` + `_resend_post`/`_send_smtp`/`_send_gmail` ahora soportan **attachments**. `routes/stats.build_workbook(data)` extraído para reuso entre export y reporte. Config expuesta en `_integrations_view` y persistida en `routes/integrations.py` (`sales_report.*`).
- ✅ **(2) Multi-moneda USD completa** — empresa elige moneda base (MXN/USD) en Ajustes→Pagos (`base-currency-input`); pricing/cotizaciones/Stripe ya usan `base_currency`. El enlace público ahora muestra el **equivalente genérico en la otra moneda** (`equivalent_amount`/`equivalent_currency`): base MXN→muestra USD, base USD→muestra MXN, con tipo de cambio en vivo (`currency.get_rates`, open.er-api). Verificado en ambos sentidos vía curl.
- Tests: `/app/test_reports/iteration_32.json` (backend 9/9 API + 5/5 unit, frontend 100%, 0 incidencias) + `backend/tests/test_iteration32_reports.py` y `test_iteration32_api.py`.
- ⏳ **Backlog**: todo lo solicitado por el usuario está implementado. Posibles mejoras futuras: timezone configurable por empresa para el reporte, BackgroundTask para el envío manual en tenants muy grandes.


- ✅ **(1) Insights accionables en Analítica** (`/app/analytics`): dos tarjetas destacadas calculadas en cliente desde los datos del período — **"Tu mejor vendedor"** (paquete con mayor `view_to_quote` con vistas+cotizaciones) y **"Oportunidad de mejora"** (paquete con más vistas y 0 cotizaciones), con recomendación accionable. data-testid `analytics-insights`/`insight-best`/`insight-opportunity`.
- ✅ **(2) Módulo de Ventas y estadísticas** — nueva página `/app/stats` (nav "Ventas", solo company_admin). Backend `GET /api/stats/sales?period=week|month|quarter|year` (`routes/stats.py`, require company_admin) devuelve: ingresos totales (ganadas) + cobrado, **tendencia de ingresos** (buckets: semana=7d, mes=30d, trimestre=13 semanas, año=12 meses) graficada con **recharts** (AreaChart), **conversión global** (ganadas/total + perdidas), **ranking de ejecutivos** (creadas/cerradas/monto vendido), **ranking de clientes** (cotizaciones/compra), **paquetes más vendidos**, **servicios más vendidos** (line items de ganadas), y **cotizaciones perdidas con motivo**. Query Mongo acotada por `created_at`/`last_activity_at >= cutoff` para rendimiento.
- ✅ **Exportable a Excel** — `GET /api/stats/sales/export?period=` (company_admin) genera XLSX (openpyxl) con hojas Resumen/Ejecutivos/Clientes/Paquetes/Servicios/Perdidas; botón "Exportar Excel" en la página (descarga vía blob). RBAC: ejecutivo 403.
- ✅ **Motivo de cotización perdida** — `QuotationStateUpdate.reason` (max 500); `update_quotation_state` guarda `lost_reason` al pasar a `perdida` (y lo limpia al salir de perdida). UI: modal en `QuotationDetail` (`lost-reason-modal`) al hacer clic en "Perdida" que pide el motivo opcional; el resto de estados cambian directo sin modal. El motivo aparece en el reporte de Ventas y en el Excel.
- Tests: `/app/test_reports/iteration_31.json` (backend 10/10, frontend 100%, 0 incidencias) + `backend/tests/test_iteration31_sales_stats.py`.
- ⏳ **Pendiente (Backlog P2)**: Multi-moneda USD completa por empresa.


- ✅ **(1) Analítica de catálogo público** — nueva página `/app/analytics` (nav "Analítica", solo company_admin) con tablero por paquete activo: vistas, solicitudes, cotizaciones y tasas de conversión (vista→solicitud, solicitud→cotización, vista→cotización), filtrable por semana/mes. Backend: `GET /api/catalog/analytics?period=week|month` (require_tenant). **Tracking de vistas**: `GET /api/public/package/{slug}/{code}` registra un evento en `catalog_views` (best-effort try/except). Las **cotizaciones del embudo** sólo cuentan las creadas desde una solicitud del catálogo (campo `from_request`), evitando inflar la conversión con cotizaciones manuales.
- ✅ **(2) WhatsApp share con Open Graph** — `GET /api/share/q/{token}` (HTMLResponse) sirve meta `og:title/og:description/og:image` con datos del tenant (nombre, código, logo absoluto del tenant) y redirige (meta refresh + JS) a la SPA `/q/{token}`. Token inválido degrada a HTML 200 genérico (no 500). `QuotationDetail.sendWhatsApp` ahora comparte la URL `/api/share/q/{token}` para que el preview de WhatsApp muestre los datos de la empresa, no los de Routiq.
- ✅ **(3) Multi-hotel al convertir plantilla** — `templates._build_package_from_custom` ahora crea **un hotel por cada concepto 'hospedaje'** de la plantilla/cotización (antes sólo el primero), con `prices_by_occupancy` = neto/margin_divisor. Aplica a `save-as-package` y `publish-as-package`.
- ✅ **(4) Revisión UX** — componente reutilizable `ConfirmDialog` (`ConfirmProvider`/`useConfirm`) que reemplaza TODOS los `window.confirm` (13 en Services, Packages, QuotationDetail, Settings, WhatsAppInbox, MasterSite) por un modal estilizado (data-testid `confirm-dialog`/`confirm-accept`/`confirm-cancel`). Empty state informativo con CTA en lista de Cotizaciones (`empty-list`); empty states ya existentes en Clientes/Solicitudes/Analítica.
- ✅ **(5) Prueba automática de Resend al guardar** — `Settings.saveInteg`: tras guardar una configuración de Resend (provider=resend + key + remitente) dispara automáticamente `POST /api/companies/me/test-resend` y muestra el resultado (✓ verificado / advertencia de dominio no verificado) — red de seguridad de un clic.
- Linkage embudo: `QuotationCreate.from_request` (modelo) + persistido en `quotations` doc; `Leads.jsx` "Crear cotización" pasa `&lead={id}`, `QuotationBuilder` lo envía en el payload.
- Tests: `/app/test_reports/iteration_30.json` (backend 9/9, frontend 100%, 0 incidencias) + `backend/tests/test_iteration30_fase_c.py`.
- ⏳ **Pendiente (Backlog P2)**: Módulo de ventas y estadísticas completas; Multi-moneda USD completa por empresa.


- ✅ **Botón "Probar" para Resend** en Ajustes→Correo (proveedor Resend): `POST /api/companies/me/test-resend` (company_admin) usa la API key de la empresa (payload o la guardada en DB) y el remitente verificado para enviar un correo de prueba real; si Resend rechaza (dominio no verificado / key inválida) devuelve 400 con el mensaje de Resend. `ResendTestInput` + `notifications.send_test_resend` (reusa `_resend_post`). UI: `resend-test-email-input` + `resend-test-btn` en `EmailSettings.jsx`, handler `testResend` en `Settings.jsx`.
- ✅ **Eliminar empresa (hard delete) desde Panel Master** — `DELETE /api/master/companies/{id}?confirm_name=` (super_admin) exige que `confirm_name` coincida exactamente con el nombre de la empresa; borra la empresa y TODOS sus datos por `tenant_id` (users, packages, services, tours, transfers, clients, quotations, quotation_templates, quote_requests, payment_transactions, notifications, push_subscriptions, audit_log, ai_usage, whatsapp_links, whatsapp_messages). Modal de doble confirmación en `Master.jsx` (botón rojo `delete-company-{slug}`, input `delete-company-confirm-input`, botón `delete-company-confirm` deshabilitado hasta escribir el nombre exacto).
- Verificado vía curl E2E: 404 empresa inexistente, 400 nombre incorrecto, 403 RBAC (admin), 200 + cascade delete (crear empresa throwaway → eliminar → confirmada ausente). Modal verificado por screenshot.
- ⏳ **Pendiente**: Fase C (analítica catálogo público, multi-hotel al convertir plantilla, revisión UX, WhatsApp Open Graph).


- ✅ **(8) CRUD completo de clientes** — nueva página `/app/clients` (nav "Clientes"): editar (nombre/correo/teléfono/tipo/notas), eliminar con confirmación (advierte si tiene cotizaciones activas), filtro por tipo, buscador (nombre/correo/notas), paginador (10/pág), orden por actividad/ventas/nombre/reciente. `GET /api/clients` enriquecido con `quotations_count`, `active_count`, `sales_total`, `last_activity_at` (agregación). Nuevos: `PATCH/DELETE /api/clients/{id}`, `ClientUpdate`.
- ✅ **(9) Eliminar ejecutivos** en `/app/team` (además de suspender): `DELETE /api/users/{id}` (admin) reasigna las cotizaciones del ejecutivo al admin; `GET /api/users/{id}/workload` para la advertencia. Guardas: 400 self-delete, 403 admin/executive. Modal con advertencia de cotizaciones activas.
- ✅ **(10) Selector de tono IA** (Formal/Cercano/Premium) junto a "Generar con IA" en el paso Revisión de ambos constructores; `PresentationInput.tone` + `generate_presentation(tone)`.
- Tests: `/app/test_reports/iteration_29.json` (frontend 100%, backend 12/12 tras corregir orden de checks self-delete→400) + `backend/tests/test_iteration29_fase_b.py`.
- ⏳ **Pendiente iteración 28**: Fase C (4 analítica catálogo público, 5 multi-hotel al convertir plantilla, 6 revisión general UX).

## Iteración 28 — Fase A (jun-2026) — Bugs críticos + presentación IA + fecha/hora por concepto
- 🐞 **Bug correos (raíz)**: `notifications.send_email` ahora hace **fallback a `PLATFORM_RESEND_API_KEY`/`PLATFORM_FROM_EMAIL`** cuando la empresa no tiene proveedor propio (antes el reset de contraseña fallaba en silencio). Requiere dominio `routiq.com.mx` verificado en Resend (pasos entregados al usuario).
- 🐞 **Bug captcha**: `_verify_turnstile` ahora loguea `error-codes`/`hostname` de Cloudflare para diagnosticar (`invalid-input-secret` / `hostname-mismatch` / `timeout-or-duplicate`).
- 🐞 **Bug cursor (Incluye/No incluye)**: `StringList` se movió a nivel de módulo en `CustomQuotationBuilder.jsx` (estaba inline → React lo remontaba en cada tecla y perdía el foco). VERIFICADO (27 chars sin perder foco).
- ✅ **(10) Fecha/hora por concepto** en cotización a medida: `CustomItem.service_date/start_time/end_time` (opcionales); aparecen en PDF y enlace público.
- ✅ **(11) Texto de presentación con IA** en el paso Revisión de AMBOS constructores: textarea editable + botón "Generar con IA" (`POST /api/ai/presentation`, BYOK Master vía `ai_service.generate_presentation`; usa nombre cliente, destino/título, fechas). 503 en preview por BYOK no configurado (manejado con error claro en español).
- ✅ **(12) PDF mejorado**: presentación al inicio, conceptos con descripción+fecha+hora, condiciones con "Todos los precios están sujetos a cambio…", salto de página automático (presentación+itinerario pág.1, precios pág.2) cuando hay presentación+itinerario.
- ✅ **(13) Enlace público detallado**: presentación al inicio, bloque "Conceptos del programa" con descripción/fecha/hora, itinerario y políticas de cancelación.
- Tests: `/app/test_reports/iteration_28.json` (backend 6/6, frontend 6/6, bug cursor verificado, 0 incidencias) + `backend/tests/test_iteration28_presentation_custom_dt.py`.
- ⏳ **Pendiente iteración 28**: Fase B (8 CRUD clientes, 9 eliminar ejecutivos) y Fase C (4 analítica catálogo, 5 multi-hotel al convertir plantilla, 6 revisión UX).

## Iteración 27 (jun-2026) — Plantillas destacadas + paquete público + mejoras QA
- ✅ **Plantillas destacadas**: campo `featured` en plantillas; toggle estrella ⭐ **solo admin** (`PATCH /api/templates/{id}`, require company_admin); las destacadas se ordenan primero (badge + ring en la pestaña Plantillas).
- ✅ **Convertir en paquete público** (solo admin, `POST /api/templates/{id}/publish-as-package`): crea un paquete como **borrador (`status="inactive"`, NO visible en `/c/:slug`)** con contenido descriptivo + hotel prellenado (público=neto/margen), y abre el editor con `?from=template`. El admin ajusta precios por ocupación y cambia Estado→Activo para publicar (decisión del usuario: control antes de publicar). `from_template` registrado.
- ✅ **Mejoras menores QA**: modal "Guardar como paquete" (detalle de cotización) ahora con **código editable** y modal estilizado (reemplaza `window.confirm`); redirige a `/app/packages/{id}/edit?from=custom`. **Aviso (`prefill-notice`)** en `PackageEditor` cuando viene `?from=custom|template` recordando ajustar precios por ocupación. (data-testid del enlace público ya existía: `create-public-link`; `margin_divisor` ya expuesto en `/companies/me`.) Refactor DRY: `_build_package_from_custom` compartido.
- Tests: `/app/test_reports/iteration_27.json` (backend 8/8, frontend 7/7, RBAC verificado, borrador NO público, regresión OK) + `backend/tests/test_iteration27_publish.py`.

## Iteración 26 (jun-2026) — Plantillas de programa personalizado + Guardar como paquete
- ✅ **Plantillas de programa personalizado** (colección `quotation_templates` por empresa): guardar una cotización a medida como plantilla reutilizable con nombre (ej. "Riviera Maya 5 días") y clonarla en segundos. Nueva pestaña **"Plantillas"** dentro del catálogo `/app/packages` (`tab-paquetes`/`tab-plantillas`) con "Usar plantilla" → abre `/app/quotations/new/custom?template={id}` precargando conceptos, itinerario, incluye/no incluye y pax (sin cliente). Se guarda como plantilla desde **el paso Revisión del builder** Y desde **el detalle** de la cotización. Endpoints: `GET/POST/DELETE /api/templates`, `POST /api/quotations/{id}/save-as-template` (require_tenant). Selector "Cargar plantilla" también en el paso Programa.
- ✅ **Guardar como paquete** (`POST /api/quotations/{id}/save-as-package`, solo company_admin): crea un paquete en el catálogo copiando contenido descriptivo (nombre, noches, itinerario, incluye/no incluye) + un **hotel prellenado** con el precio público del concepto de hospedaje (público=neto/margin_divisor) en las 4 ocupaciones; code único auto-generado; redirige a `/app/packages/{id}/edit` para que el admin ajuste precios por ocupación. El catálogo crece orgánicamente con lo vendido. (RBAC: ejecutivo 403; no ve el botón.)
- Tests: `/app/test_reports/iteration_26.json` (backend 9/9, frontend 6/6 flujos, RBAC verificado, regresión paquetes OK, 0 incidencias) + `backend/tests/test_iteration26_templates.py`.

## Iteración 25 (jun-2026) — Cotización a medida + Políticas de cancelación + fix demo creds
- ✅ **Cotización a medida / Programa personalizado** (3er tipo, `type='personalizado'`): builder libre `CustomQuotationBuilder.jsx` (ruta `/app/quotations/new/custom` y edición `/app/quotations/custom/:id/edit`). El ejecutivo arma todo desde cero sin catálogo: conceptos libres de **Hospedaje/Traslado/Tour/Extra** con **unidad de cobro** (por persona, por noche, por habitación, por grupo, por día, **por vehículo**) + itinerario día a día de texto libre + incluye/no incluye. Matemática: precio público = **neto / margin_divisor** de la empresa, cantidad auto-derivada por unidad, comisión por canal aplicada (mismo modelo que servicios/paquetes). Backend: `compute_custom_quotation` (pricing.py), rama `is_custom` en `create/update_quotation`, y `download_quotation_pdf` sintetiza un "pack" para que el **PDF y enlace público sean idénticos** a los de un paquete. 3ra tarjeta `type-personalizado` en `QuotationBuilder.jsx`.
- ✅ **Políticas de cancelación y cambios por empresa**: editor de texto enriquecido (`RichTextEditor.jsx`, contentEditable: negrita/cursiva/subrayado/listas) en Ajustes (`policy-card`). `GET/PATCH /api/companies/me/policy` (admin) con **sanitización** server-side (`sanitize_richtext` en deps.py: elimina `<script>/<style>`/handlers `on*`/`javascript:`). Se inyecta automáticamente en el **PDF** (`_richtext_flowables` HTML→ReportLab) y en el **enlace público** (`PublicQuotation.jsx`, sección `public-policy`). Campo `companies.cancellation_policy`.
- ✅ **Fix credenciales demo**: `/api/public-config` ahora default `false` + strip de comillas; `backend/.env` `SHOW_DEMO_CREDENTIALS="false"`. Las credenciales demo ya NO se muestran en `/login`. (Nota prod: el contenedor backend debe recrearse con `--force-recreate` para recargar la env var; `deploy/docker-compose.yml` ya la pasa con default `false`.)
- Tests: `/app/test_reports/iteration_25.json` (backend 13/13, frontend 6/6 flujos, 0 incidencias) + `backend/tests/test_iteration25_custom_policy.py`. Validado: creación/edición/recalculo personalizado, PDF válido, policy sanitizada e inyectada, regresión paquete/servicios OK.

## Iteración 24 (jun-2026) — uso de IA, backup on-demand, revisión de seguridad
- ✅ **Registro de uso/costo de IA** en `/master/ai`: cada llamada de IA se registra en `ai_usage` (tenant, proveedor, modelo, tokens, costo estimado USD según tabla de tarifas). `GET /master/ai-usage` agrega por mes y por empresa; UI con totales y tablas.
- ✅ **Generar respaldo ahora** (sin SSH): botón en la tarjeta de backups del Master → `POST /backups/run` (mongodump async a `BACKUP_DIR`). ⚠️ En producción el volumen de backups debe estar **montado con escritura** para el backend (si es solo lectura, devuelve error claro).
- ✅ **Revisión de seguridad pre-lanzamiento**: auditados todos los endpoints públicos (todos intencionales y protegidos donde corresponde — webhooks por secreto/firma, catálogo/paquete público read-only, cotización por token). Uploads/import requieren admin. Signup con rate-limit (hora+día) + honeypot + Turnstile. API key de IA enmascarada. `deployment_agent`: PASS sin bloqueadores. (Nota: `CORS_ORIGINS="*"` — aceptable para API pública; se puede restringir al dominio en prod si se desea).
- Tests: `/app/test_reports/iteration_24.json` (frontend 3/3) + curl backend + deployment_agent PASS.

## Iteración 23 (jun-2026) — IA BYOK (independiente de Emergent) + 4 fixes
- ✅ **IA independiente (BYOK)**: se eliminó la dependencia de `EMERGENT_LLM_KEY`. El Master configura proveedor (**Anthropic / OpenAI / Google**), modelo y su **propia API key** en `/master/ai` (aplica a todas las empresas). SDKs oficiales: `anthropic`, `openai`, `google-genai`. Endpoints `GET/PATCH /master/ai-settings` y `POST /master/ai-settings/test` (probar conexión). Mensajes de error amistosos en español (key inválida, sin saldo, no configurada). `ai_service.py` reescrito (BYOK) leyendo `platform_settings(id='ai')`.
- ✅ **Logo más grande y centrado** en catálogo `/c/:slug` (hero con logo destacado).
- ✅ **Proporciones de imagen** consistentes en `/p/:slug/:code` (contenedor con aspect-ratio).
- ✅ **Mini-dashboard de leads** en `/app/leads` (`GET /quote-requests/stats`): total, nuevas, últimos 7 días, atendidas + ranking de paquetes más solicitados.
- ✅ **Limpiar datos de prueba por empresa** (`POST /companies/me/clear-data`, admin): borra cotizaciones, clientes, leads, pagos, WhatsApp y notificaciones; conserva catálogo/config. Zona de peligro en Ajustes con confirmación "LIMPIAR".
- Tests: `/app/test_reports/iteration_23.json` (frontend 100%) + curl backend. ⚠️ El camino exitoso de IA requiere una API key real del proveedor (no validable en preview).

## Iteración 22 (jun-2026) — Compartir catálogo con QR + checklist v1.0
- ✅ **Botón "Compartir catálogo" con QR** en /app/packages (admin y ejecutivo): modal con código QR (`qrcode.react`), copiar enlace `/c/:slug`, descargar QR (PNG) y compartir por WhatsApp. Herramienta de prospección 24/7.
- ✅ **IA verificada en preview** (resumen de chat OK). En producción depende de `EMERGENT_LLM_KEY` + saldo.
- ✅ **Checklist de lanzamiento v1.0** creado en `/app/memory/V1_LAUNCH_CHECKLIST.md` (implementado / config producción / backlog P2).
- Verificación: smoke screenshot del modal QR + curl IA preview.

## Iteración 21 (jun-2026) — usuarios/perfiles, password reset, catálogo por empresa
- ✅ **Recuperación de contraseña por correo** (todos los roles): token de un solo uso (sha256, TTL 1h) en `password_reset_tokens`; páginas públicas `/forgot-password` y `/reset-password?token=`. `POST /auth/forgot-password` (sin enumeración) y `POST /auth/reset-password`. Tenant usa correo de su empresa; Master usa correo de plataforma (Resend `PLATFORM_RESEND_API_KEY`/`PLATFORM_FROM_EMAIL`, aún sin llave → enlace generado en panel).
- ✅ **Perfil self-service** `/profile` (admin/ejecutivo/master): cambiar nombre, correo y contraseña (correo/contraseña requieren contraseña actual). `PATCH /auth/profile`. Enlace "Mi perfil" en sidebar.
- ✅ **Gestión en /app/team**: editar nombre/correo de ejecutivos (`PATCH /users/{id}`) y generar enlace de recuperación (`POST /users/{id}/reset-link`). Diferenciación visual clara Administrador (corona, borde brand) vs Ejecutivo.
- ✅ **Panel Master**: editar correo/nombre/teléfono de cada empresa (`PATCH /master/companies/{id}/contact`), generar reset del admin (`POST /master/users/{id}/reset-link`, `GET /master/company-admins`). Master cambia su propio correo/contraseña desde `/profile`.
- ✅ **Bienvenida por rol** en dashboard: "Bienvenido, [nombre] · Administrador/Ejecutivo".
- ✅ **Toggle credenciales demo** en /login vía env `SHOW_DEMO_CREDENTIALS` (`GET /public-config`).
- ✅ **Catálogo público por empresa** `/c/:slug` (`PublicCatalog.jsx`, `GET /public/company/{slug}`): branding + grilla de paquetes activos enlazando a `/p/:slug/:code`.
- ✅ **Aviso de backup**: `GET /backups/status` (freshness >24h) + banner rojo en Master; loop en background cada 6h envía correo de plataforma cuando haya `PLATFORM_RESEND_API_KEY`.
- Tests: `/app/test_reports/iteration_21.json` (frontend 100%) + curl backend.

### Pendiente de despliegue / acción del usuario
- Agregar `PLATFORM_RESEND_API_KEY` y `PLATFORM_FROM_EMAIL` (no-reply@routiq.com.mx) al `.env` de producción para activar correos de plataforma (reset Master + aviso backup).
- Agregar `EMERGENT_LLM_KEY` al `.env` de producción (resumen IA). Si persiste `FREE_USER_EXTERNAL_ACCESS_DENIED`: recargar saldo en Profile → Universal Key → Add Balance.
- `SHOW_DEMO_CREDENTIALS=false` en producción para ocultar credenciales demo del login.

## Iteración 20 (jun-2026) — refactor + vista pública de paquete + leads
- ✅ **Refactor Settings.jsx** (427→~160 líneas): dividido en `components/settings/{LogoSettings, PricingSettings, PaymentSettings, EmailSettings, BankingSettings}.jsx`. Sin cambios de comportamiento (todos los data-testid preservados; no-regresión validada).
- ✅ **Vista previa pública de paquete** `/p/:slug/:code` (`PublicPackage.jsx`): página con branding de la empresa (logo, color), hero, descripción, itinerario día a día, precio base "Desde", incluye/no incluye y hoteles. Botón **"Quiero este paquete"** → formulario (nombre, correo, tel, fecha, pax, mensaje) con honeypot anti-bot. `GET /api/public/package/{slug}/{code}` y `POST .../request`.
- ✅ **Solicitudes (leads)** `/app/leads` (`Leads.jsx`, admin+ejecutivo): lista de solicitudes con filtros (activas/archivadas/todas), notificación in-app + correo al recibir un lead, botones "Crear cotización" (→ builder con paquete preseleccionado), WhatsApp directo y marcar atendida/archivar. `GET/PATCH /api/quote-requests`.
- ✅ **Compartir paquete**: botón en cada card de `/app/packages` que copia el enlace público `/p/{slug}/{code}`.
- Tests: `/app/test_reports/iteration_20.json` (frontend 18/18) + curl backend.

## Iteración 19 (jun-2026) — fixes post-validación + CRUD paquetes
- ✅ **Fix IA resumen WhatsApp**: el inbox ahora muestra el error real del backend en vez de "No se pudo generar el resumen". El motor IA funciona (probado en preview). ⚠️ En producción verificar que `EMERGENT_LLM_KEY` esté en `/opt/routiq/deploy/.env`.
- ✅ **Fix eliminar número WhatsApp**: botón 🗑️ con confirmación en la barra de números (`DELETE /whatsapp/numbers/{id}`, admin-only, cierra sesión Baileys).
- ✅ **Fix validación "Correo de avisos"**: front + back (`EMAIL_RE`) rechazan correos sin dominio (400) y exigen formato completo.
- ✅ **CRUD UI completo de paquetes** (ver P1 abajo).
- ✅ Guarda `isFinite()` en card de paquete (evita "Desde $Infinity" si no hay precios).
- Tests: `/app/test_reports/iteration_19.json` (frontend 5/5) + curl backend (CRUD, validación, IA).

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
- [x] **Carga masiva de catálogo vía Excel** ✅ (jun-2026, iter_17): plantilla descargable (`GET /api/catalog/template`, hojas Paquetes/Tours/Traslados + Instrucciones) e importación (`POST /api/catalog/import`) con validación **fila por fila** y reporte de importados vs fallidos (hoja·fila·mensaje). UI en `/app/packages` (botones Plantilla Excel / Importar Excel + modal de reporte). Admin-only. `openpyxl` en requirements.
- [x] **Limpiar/reemplazar clave secreta de Stripe** ✅ (jun-2026, iter_17): `DELETE /api/companies/me/integrations/stripe-secret` (borra clave + desactiva Stripe) con botón "Borrar clave guardada" en Ajustes→Pagos. Reemplazar = escribir nueva clave y guardar. Sin SSH, admin-only.
- [ ] **Aviso por correo si el backup diario falla / no se generó en >24h** (backlog): pendiente de tener correo de plataforma configurado.

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
- [x] **CRUD UI completo de paquetes** ✅ (jun-2026, iter_19): editor completo en `/app/packages/new` y `/app/packages/:id/edit` (`PackageEditor.jsx`) — código, nombre, noches, estado, descripción, imagen (upload), días de salida permitidos, temporadas con rangos de fechas, hoteles con precios por ocupación (sencilla/doble/triple/cuádruple + menor) y precios por temporada, incluye/no incluye e itinerario día a día. Backend `POST/PATCH/DELETE /packages` (admin-only, código único, season-ids auto). Validado E2E (crear/editar/eliminar) en iteration_19.
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
