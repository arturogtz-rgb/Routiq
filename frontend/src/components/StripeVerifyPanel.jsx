import { useState } from 'react';
import { RefreshCw, AlertTriangle } from 'lucide-react';
import api, { formatApiError } from '@/lib/api';
import { formatDateEs } from '@/lib/dates';

const STATUS_ES = { paid: 'Pagada', pending: 'Pendiente', processing: 'En proceso', expired: 'Expirada', failed: 'Fallida', reconciled: 'Conciliada' };
const fmt = (v, c) => `$${Number(v || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${c}`;
const when = (iso) => (iso ? `${formatDateEs(iso.slice(0, 10))} ${iso.slice(11, 16)}` : '—');

function ReconcileAction({ t, quotationId, isAdmin, onDone }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  if (t.applied) return null;
  if (!isAdmin) return <p className="text-ink-400 italic" data-testid={`stripe-txn-ask-admin-${t.session_id}`}>Pide a un administrador que concilie este pago.</p>;
  const confirm = async () => {
    setBusy(true); setErr('');
    try {
      await api.post(`/quotations/${quotationId}/transactions/${t.session_id}/reconcile-manual`, { reason });
      setOpen(false); onDone();
    } catch (e) { setErr(formatApiError(e)); }
    finally { setBusy(false); }
  };
  if (!open) {
    return <button type="button" className="btn-ghost text-[11px] border border-ink-200 mt-1" onClick={() => setOpen(true)} data-testid={`stripe-txn-reconcile-${t.session_id}`}>Marcar como conciliada manualmente</button>;
  }
  return (
    <div className="mt-1 rounded-md border border-amber-300 bg-amber-50 p-2 space-y-1.5" data-testid={`stripe-txn-reconcile-confirm-${t.session_id}`}>
      <p className="text-amber-800">Se cerrará esta transacción <b>sin sumar</b> {fmt(t.base_amount, '')} al pagado. Úsalo solo si ese pago ya se registró a mano.</p>
      <input className="input-field text-xs py-1" placeholder="Motivo (opcional)" value={reason} onChange={(e) => setReason(e.target.value)} data-testid={`stripe-txn-reconcile-reason-${t.session_id}`} />
      {err && <p className="text-red-600">{err}</p>}
      <div className="flex gap-2">
        <button type="button" className="btn-primary text-[11px]" disabled={busy} onClick={confirm} data-testid={`stripe-txn-reconcile-yes-${t.session_id}`}>{busy ? 'Guardando…' : 'Confirmar conciliación'}</button>
        <button type="button" className="btn-ghost text-[11px]" onClick={() => setOpen(false)} data-testid={`stripe-txn-reconcile-no-${t.session_id}`}>Cancelar</button>
      </div>
    </div>
  );
}

function TxnRow({ t, currency, quotationId, isAdmin, onReconciled }) {
  return (
    <div className="border-t border-ink-100 pt-1.5" data-testid={`stripe-txn-${t.session_id}`}>
      <p className="font-mono text-[11px] text-ink-500 break-all">{t.session_id}</p>
      <p className="text-ink-700">
        Local: <b>{STATUS_ES[t.local_status] || t.local_status}</b> · Stripe: <b>{t.stripe_status || '—'}</b> · {fmt(t.amount, currency)}
        {t.card_fee_amount > 0 && <span className="text-ink-400"> (base {fmt(t.base_amount, currency)} + comisión {fmt(t.card_fee_amount, currency)})</span>}
        {t.applied !== null && <> · Aplicada: <b data-testid={`stripe-txn-applied-${t.session_id}`}>{t.applied ? 'sí' : 'no'}</b></>}
      </p>
      <p className="text-ink-400">Creada {when(t.created_at)}{t.paid_at ? ` · pagada ${when(t.paid_at)}` : ''}</p>
      {t.review_state === 'needs_review' && !t.applied && (
        <p className="text-amber-800 bg-amber-50 rounded px-2 py-1 mt-1" data-testid={`stripe-txn-review-${t.session_id}`}>
          <b>En revisión</b> ({when(t.review_at)}): posible pago duplicado o ya registrado manualmente. No se sumó {fmt(t.base_amount, currency)}.
        </p>
      )}
      {t.reconciled_manually && (
        <p className="text-emerald-700" data-testid={`stripe-txn-manual-${t.session_id}`}>Conciliada manualmente por {t.reconciled_manually.by_name} · {when(t.reconciled_manually.at)}{t.reconciled_manually.reason ? ` · ${t.reconciled_manually.reason}` : ''}</p>
      )}
      {t.duplicate_warning && <p className="text-red-700 font-semibold flex items-start gap-1" data-testid={`stripe-txn-duplicate-${t.session_id}`}><AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {t.duplicate_warning}</p>}
      {t.error && <p className="text-red-600 flex items-start gap-1" data-testid={`stripe-txn-error-${t.session_id}`}><AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {t.error}</p>}
      <ReconcileAction t={t} quotationId={quotationId} isAdmin={isAdmin} onDone={onReconciled} />
    </div>
  );
}

// Iter 69/70: el ejecutivo verifica con Stripe y reconcilia esta cotización (sin loops ni correos).
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
  const afterReconcile = async () => { await run(); onDone?.(); };
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
            <TxnRow key={t.session_id} t={t} currency={currency} quotationId={quotationId} isAdmin={res.is_admin} onReconciled={afterReconcile} />
          ))}
        </div>
      )}
    </div>
  );
}
