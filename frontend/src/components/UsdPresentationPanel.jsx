import { useEffect, useState } from 'react';
import { DollarSign, AlertTriangle, RefreshCw, Lock, Save } from 'lucide-react';
import api, { formatApiError } from '@/lib/api';
import { HelpTip } from '@/components/HelpTip';
import { fxError } from '@/components/settings/PricingSettings';
import { FX_HELP, usdFmt as usd, toUsd } from '@/components/FxRateField';

const mxn = (v) => `$${Number(v || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} MXN`;
const day = (iso) => (iso ? new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: '2-digit' }) : '—');
const when = (iso) => (iso ? new Date(iso).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' }) : '');

// Mismas reglas que el backend (fx_presentation.build): pp USD redondeado a 2, total = Σ pp USD × personas.
function compute(q, rate) {
  const totalMxn = Number(q.final_total ?? q.total ?? 0);
  const base = q.per_person_breakdown?.rows || [];
  const rows = base.map((r) => {
    const pp = toUsd(r.price_per_person, rate);
    return { key: r.key, label: r.label, pax: r.pax, pp, sub: Math.round(pp * r.pax * 100) / 100, ppMxn: r.price_per_person, subMxn: r.subtotal };
  });
  const direct = toUsd(totalMxn, rate);
  const total = rows.length ? Math.round(rows.reduce((s, r) => s + r.sub, 0) * 100) / 100 : direct;
  return { rows, total, direct, totalMxn };
}

function History({ items }) {
  if (!items?.length) return null;
  return (
    <details className="text-[11px] text-ink-500" data-testid="fx-history">
      <summary className="cursor-pointer">Historial del tipo de cambio ({items.length})</summary>
      <ul className="mt-1 space-y-0.5">
        {[...items].reverse().map((e, i) => (
          <li key={i} data-testid={`fx-history-${i}`}>{when(e.at)} · {e.user_name || '—'}: {e.old ?? '—'} → {e.new}{e.source === 'refresh' ? ' (Ajustes)' : ''}{e.unlocked ? ' · desbloqueo admin' : ''}{e.reason ? ` · ${e.reason}` : ''}</li>
        ))}
      </ul>
    </details>
  );
}

function RateEditor({ q, p, draft, setDraft, onDone }) {
  const lock = q.fx_lock || {};
  const editable = !lock.locked || lock.can_unlock;
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const changed = draft !== '' && Number(draft) !== Number(p.rate || 0);
  const needReason = lock.locked && !reason.trim();
  const run = async (fn) => {
    setBusy(true); setErr('');
    try { await fn(); setReason(''); onDone(); } catch (e) { setErr(formatApiError(e)); } finally { setBusy(false); }
  };
  const save = () => run(() => api.put(`/quotations/${q.id}/fx`, { rate: Number(draft), reason }));
  const refresh = () => run(() => api.post(`/quotations/${q.id}/fx/refresh`, { reason }));
  const vErr = fxError(draft);
  return (
    <div className="space-y-1.5 border-t border-ink-100 pt-2" data-testid="fx-editor">
      <label className="label-text"><span className="inline-flex items-center gap-1">Tipo de cambio (MXN por 1 USD)<HelpTip text={FX_HELP} testid="fx-detail-help" /></span></label>
      <div className="flex flex-wrap items-center gap-2">
        <input type="number" step="0.0001" min="0" className="input-field w-36 py-1.5 text-sm" value={draft} disabled={!editable}
          onChange={(e) => setDraft(e.target.value)} data-testid="fx-detail-input" />
        {editable && changed && !vErr && (
          <button type="button" className="btn-primary text-xs py-1.5" disabled={busy || needReason} onClick={save} data-testid="fx-detail-save"><Save className="w-3.5 h-3.5" /> {busy ? 'Guardando…' : 'Guardar'}</button>
        )}
        {editable && p.company_rate && Number(p.company_rate) !== Number(p.rate || 0) && (
          <button type="button" className="btn-ghost text-xs border border-ink-200" disabled={busy || needReason} onClick={refresh} data-testid="fx-refresh-btn">
            <RefreshCw className="w-3.5 h-3.5" /> Actualizar al tipo de cambio actual (${p.company_rate_label})
          </button>
        )}
      </div>
      {vErr && <p className="text-xs text-red-600" data-testid="fx-detail-error">{vErr}</p>}
      {lock.locked && (
        <p className="text-xs text-amber-800 flex items-start gap-1.5" data-testid="fx-locked-notice"><Lock className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          Tipo de cambio bloqueado: la cotización {lock.reason}, para que el USD de documentos entregados no cambie. {lock.can_unlock ? 'Como admin puedes cambiarlo con motivo obligatorio.' : 'Solo un admin puede desbloquearlo.'}</p>
      )}
      {editable && (
        <input className="input-field text-sm py-1.5" maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)}
          placeholder={lock.locked ? 'Motivo del desbloqueo (obligatorio)' : 'Motivo del cambio (opcional)'} data-testid="fx-detail-reason" />
      )}
      {err && <p className="text-xs text-red-600" data-testid="fx-detail-save-error">{err}</p>}
    </div>
  );
}

// Iter 71/72: presentación USD (interna) del canal Mayorista internacional, con TC editable por cotización.
export function UsdPresentationPanel({ q, onRefreshed }) {
  const p = q.usd_presentation;
  const [draft, setDraft] = useState(p?.rate ?? '');
  useEffect(() => { setDraft(p?.rate ?? ''); }, [p?.rate]);
  if (!p) return null;
  const draftOk = draft !== '' && !fxError(draft);
  const shownRate = draftOk ? draft : (p.available ? p.rate : null);
  const live = shownRate ? compute(q, shownRate) : null;
  return (
    <div className="mt-4 rounded-xl border border-brand-100 bg-brand-50/40 p-4 space-y-2 text-sm" data-testid="usd-presentation-panel">
      <p className="flex items-center gap-1.5 font-semibold text-ink-900"><DollarSign className="w-4 h-4 text-brand-500" /> Mayorista internacional · USD</p>
      {!live ? (
        <p className="text-amber-800 flex items-start gap-1.5" data-testid="usd-missing-warning"><AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          {p.company_rate ? 'Esta cotización no tiene tipo de cambio guardado: captúralo o usa “Actualizar al tipo de cambio actual”.' : `${p.warning || 'Sin tipo de cambio'}.`} Mientras tanto el cliente la ve solo en MXN.</p>
      ) : (
        <>
          <p className="text-xs text-ink-500" data-testid="usd-rate">TC guardado: <b>{p.available ? `$${p.rate_label} MXN por USD` : '—'}</b>{p.available ? ` · ${day(p.rate_date)}` : ''}{p.company_rate && Number(p.company_rate) !== Number(p.rate) ? ` · Sugerido en Ajustes: $${p.company_rate_label}` : ''}
            {draftOk && Number(draft) !== Number(p.rate || 0) && <span className="text-brand-600 font-semibold" data-testid="usd-draft-flag"> · Vista previa con ${draft} (sin guardar)</span>}</p>
          {live.rows.map((r) => (
            <div key={r.key} className="flex justify-between gap-3" data-testid={`usd-row-${r.key}`}>
              <span className="text-ink-600 whitespace-nowrap">{r.label} · {r.pax} pers.</span>
              <span className="text-right"><b className="text-ink-900">{usd(r.pp)}</b> c/u · {usd(r.sub)}
                <span className="block text-xs text-ink-400">{mxn(r.ppMxn)} c/u · {mxn(r.subMxn)}</span></span>
            </div>
          ))}
          <div className="flex justify-between border-t border-ink-100 pt-1.5">
            <span className="font-semibold text-ink-900">Total</span>
            <span className="text-right"><b className="text-brand-600" data-testid="usd-total">{usd(live.total)}</b><span className="block text-xs text-ink-400">{mxn(live.totalMxn)}</span></span>
          </div>
          {Math.abs(live.total - live.direct) >= 0.01 && (
            <p className="text-[11px] text-ink-500" data-testid="usd-rounding-diff">Suma por persona {usd(live.total)} vs total MXN ÷ TC {usd(live.direct)}: diferencia de {usd(Math.abs(live.total - live.direct))} por redondeo. El monto real a cobrar es el total en MXN.</p>
          )}
          {p.available && <p className="text-[11px] italic text-ink-500" data-testid="usd-note">{p.note}</p>}
        </>
      )}
      <RateEditor q={q} p={p} draft={draft} setDraft={setDraft} onDone={onRefreshed} />
      <History items={q.fx_history} />
    </div>
  );
}
