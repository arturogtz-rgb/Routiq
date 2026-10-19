import { useState } from 'react';
import { RefreshCw, AlertTriangle } from 'lucide-react';
import api, { formatApiError } from '@/lib/api';

const STATUS_ES = { paid: 'Pagada', pending: 'Pendiente', processing: 'En proceso', expired: 'Expirada', failed: 'Fallida' };
const fmt = (v, c) => `$${Number(v || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${c}`;

// Iter 69: el ejecutivo verifica con Stripe y reconcilia esta cotización (sin loops ni correos).
export function StripeVerifyPanel({ quotationId, currency, onDone }) {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState('');
  const run = async () => {
    setBusy(true); setErr('');
    try {
      const { data } = await api.post(`/quotations/${quotationId}/verify-stripe`);
      setRes(data);
      if (data.credited_now > 0) onDone?.();
    } catch (e) { setErr(formatApiError(e)); }
    finally { setBusy(false); }
  };
  return (
    <div className="mt-3" data-testid="stripe-verify-panel">
      <button type="button" onClick={run} disabled={busy} className="btn-ghost text-xs border border-ink-200" data-testid="stripe-verify-btn">
        <RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} /> Verificar pago con Stripe
      </button>
      {err && <p className="text-xs text-red-600 mt-2" data-testid="stripe-verify-error">{err}</p>}
      {res && (
        <div className="mt-2 rounded-lg border border-ink-100 bg-white p-2 text-xs space-y-1.5" data-testid="stripe-verify-result">
          <p className="text-ink-600" data-testid="stripe-verify-summary">
            {res.credited_now > 0 ? `Se acreditaron ${res.credited_now} pago(s). ` : 'Sin acreditaciones nuevas. '}
            Pagado: <b>{fmt(res.amount_paid, currency)}</b>{res.key_type ? ` · llave ${res.key_type}…` : ' · sin llave de Stripe'}
          </p>
          {res.transactions.length === 0 && <p className="text-ink-400 italic">Esta cotización no tiene transacciones con tarjeta.</p>}
          {res.transactions.map((t) => (
            <div key={t.session_id} className="border-t border-ink-100 pt-1.5" data-testid={`stripe-txn-${t.session_id}`}>
              <p className="font-mono text-[11px] text-ink-500 break-all">{t.session_id}</p>
              <p className="text-ink-700">
                Local: <b>{STATUS_ES[t.local_status] || t.local_status}</b> · Stripe: <b>{t.stripe_status || '—'}</b> · {fmt(t.amount, currency)}
                {t.card_fee_amount > 0 && <span className="text-ink-400"> (base {fmt(t.base_amount, currency)} + comisión {fmt(t.card_fee_amount, currency)})</span>}
                {t.applied !== null && <> · Aplicada: <b data-testid={`stripe-txn-applied-${t.session_id}`}>{t.applied ? 'sí' : 'no'}</b></>}
              </p>
              {t.error && <p className="text-red-600 flex items-start gap-1" data-testid={`stripe-txn-error-${t.session_id}`}><AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {t.error}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
