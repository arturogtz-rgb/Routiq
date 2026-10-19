# Webhook de Stripe — análisis (Iteración 69)

## Estado anterior
- `/api/webhook/stripe` creaba `StripeCheckout(api_key=STRIPE_API_KEY del entorno)` sin `webhook_secret`.
  Con `webhook_secret=None`, `emergentintegrations` hace `json.loads(payload)` y **no valida la firma**:
  cualquiera que conociera un `session_id` pendiente podía enviar un aviso falso `checkout.session.completed`
  con `payment_status: "paid"` y acreditar la cotización.
- Usaba la llave del entorno aunque la empresa tuviera `company.stripe.secret_key`.
- Los errores se tragaban con `log.warning` y se respondía 200.

## Cambio aplicado en Iter 69 (aprobado por el usuario)
- El aviso nunca es prueba de pago: solo se leen `session_id` y `metadata.tenant_id` para saber qué consultar.
- Si el `session_id` no existe en `payment_transactions`: WARNING y 200 sin hacer nada.
- Se consulta la sesión a Stripe con la llave de la empresa dueña de **nuestra** transacción
  (`txn.tenant_id`; si `metadata.tenant_id` no coincide se registra WARNING).
- Se acredita solo si Stripe responde `payment_status == "paid"`, con `base_amount` de nuestra transacción.
- Si la consulta falla: no acredita, la transacción queda para el reconciliador. Siempre 200.

## Qué haría falta para validar la firma real (NO implementado)
1. Guardar por empresa el secreto del endpoint (`whsec_…`) en `company.stripe.webhook_secret`
   (campo nuevo en Ajustes > Integraciones, enmascarado como la secret key).
2. Registrar en el Dashboard de Stripe de cada empresa el endpoint
   `https://<dominio>/api/webhook/stripe` con eventos `checkout.session.completed`,
   `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `checkout.session.expired`.
3. En el webhook: leer `metadata.tenant_id` del payload sin confiar en él, cargar esa empresa y llamar
   `StripeCheckout(api_key=company_key, webhook_secret=company.stripe.webhook_secret).handle_webhook(body, sig)`
   (el SDK ya soporta `webhook_secret` → `stripe.Webhook.construct_event`; **no requiere cambiar dependencias**).
   Si la firma falla → 400 (Stripe reintenta) y WARNING.
4. Opcional: un endpoint por empresa (`/api/webhook/stripe/{tenant_id}`) evita depender de metadata.
5. Nota: `StripeCheckout.__init__` fija `stripe.api_key` global del SDK; con varias empresas concurrentes conviene
   migrar a `stripe.StripeClient(api_key)` por llamada (cambio de uso, no de dependencia).
