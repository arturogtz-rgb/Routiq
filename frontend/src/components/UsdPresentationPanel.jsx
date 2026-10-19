import { useState } from 'react';
import { DollarSign, AlertTriangle, RefreshCw } from 'lucide-react';
import api, { formatApiError } from '@/lib/api';

const usd = (v) => `US$${Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const mxn = (v) => `$${Number(v || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} MXN`;
const day = (iso) => (iso ? new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: '2-digit' }) : '—');

function RefreshFx({ p, quotationId, onDone }) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  if (!p.company_rate) return null;
  const go = async () => {
    setBusy(true); setErr('');
    try { await api.post(`/quotations/${quotationId}/fx/refresh`); setConfirm(false); onDone(); }
    catch (e) { setErr(formatApiError(e)); }
    finally { setBusy(false); }
  };
  const same = p.available && Number(p.rate) === Number(p.company_rate);
  if (!confirm) {
    return (
      <button type="button" className="btn-ghost text-xs border border-ink-200" onClick={() => setConfirm(true)} data-testid="fx-refresh-btn">
        <RefreshCw className="w-3.5 h-3.5" /> Actualizar al tipo de cambio actual{same ? '' : ` ($${p.company_rate})`}
      </button>
    );
  }
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-2 text-xs space-y-1.5" data-testid="fx-refresh-confirm">
      <p className="text-amber-800">Se recalculará la presentación en USD con ${p.company_rate} MXN por USD{p.available ? ` (antes $${p.rate_label})` : ''}. Los montos en MXN y el cobro no cambian.</p>
      {err && <p className="text-red-600">{err}</p>}
      <div className="flex gap-2">
        <button type="button" className="btn-primary text-xs" disabled={busy} onClick={go} data-testid="fx-refresh-yes">{busy ? 'Actualizando…' : 'Confirmar'}</button>
        <button type="button" className="btn-ghost text-xs" onClick={() => setConfirm(false)} data-testid="fx-refresh-no">Cancelar</button>
      </div>
    </div>
  );
}

// Iter 71: presentación USD (interna: USD y MXN a la par) del canal Mayorista internacional.
export function UsdPresentationPanel({ q, onRefreshed }) {
  const p = q.usd_presentation;
  if (!p) return null;
  return (
    <div className="mt-4 rounded-xl border border-brand-100 bg-brand-50/40 p-4 space-y-2 text-sm" data-testid="usd-presentation-panel">
      <p className="flex items-center gap-1.5 font-semibold text-ink-900"><DollarSign className="w-4 h-4 text-brand-500" /> Mayorista internacional · USD</p>
      {!p.available ? (
        <p className="text-amber-800 flex items-start gap-1.5" data-testid="usd-missing-warning"><AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          {p.company_rate ? 'Esta cotización no tiene tipo de cambio guardado: usa “Actualizar al tipo de cambio actual”.' : `${p.warning}.`} Mientras tanto el cliente la ve solo en MXN.</p>
      ) : (
        <>
          <p className="text-xs text-ink-500" data-testid="usd-rate">TC guardado: <b>${p.rate_label} MXN por USD</b> · {day(p.rate_date)}{p.company_rate && Number(p.company_rate) !== Number(p.rate) ? ` · Ajustes hoy: $${p.company_rate}` : ''}</p>
          {p.rows.map((r) => (
            <div key={r.key} className="grid grid-cols-[1fr_auto_auto] gap-3" data-testid={`usd-row-${r.key}`}>
              <span className="text-ink-600">{r.title || r.label} ({r.pax} pers.)</span>
              <span className="text-right"><b className="text-ink-900">{usd(r.price_per_person_usd)}</b> <span className="text-ink-400">· {mxn(r.price_per_person_mxn)}</span></span>
              <span className="text-right text-ink-700">{usd(r.subtotal_usd)}</span>
            </div>
          ))}
          <div className="flex justify-between border-t border-ink-100 pt-1.5">
            <span className="font-semibold text-ink-900">Total</span>
            <span className="text-right"><b className="text-brand-600" data-testid="usd-total">{usd(p.total_usd)}</b> <span className="text-ink-400">· {mxn(p.total_mxn)}</span></span>
          </div>
          {Math.abs(p.rounding_diff_usd || 0) >= 0.01 && (
            <p className="text-[11px] text-ink-500" data-testid="usd-rounding-diff">Suma por persona {usd(p.total_usd)} vs total MXN ÷ TC {usd(p.direct_total_usd)}: diferencia de {usd(Math.abs(p.rounding_diff_usd))} por redondeo. El monto real a cobrar es el total en MXN.</p>
          )}
          <p className="text-[11px] italic text-ink-500" data-testid="usd-note">{p.note}</p>
        </>
      )}
      <RefreshFx p={p} quotationId={q.id} onDone={onRefreshed} />
    </div>
  );
}
