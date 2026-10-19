import { DollarSign, Lock, AlertTriangle } from 'lucide-react';
import { HelpTip } from '@/components/HelpTip';
import { fxError } from '@/components/settings/PricingSettings';

export const FX_HELP = 'El dólar es solo informativo. El cobro es en pesos y el tipo de cambio puede variar según el banco del cliente.';
export const usdFmt = (v) => `US$${Number(v || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export const toUsd = (mxn, rate) => Math.round((Number(mxn || 0) / Number(rate)) * 100) / 100;

export const emptyFx = () => ({ rate: null, orig: null, reason: '', lock: null });
export const fxFromQuotation = (q) => ({ rate: q.fx_rate_mxn_per_usd ?? '', orig: q.fx_rate_mxn_per_usd ?? null, reason: '', lock: q.fx_lock || null });
const suggestedOf = (company) => company?.pricing_config?.fx_mayorista_mxn_per_usd ?? '';
export const fxValue = (fx, company) => (fx.rate ?? suggestedOf(company));

// Campos a enviar al guardar (solo canal Mayorista internacional y si cambió en edición).
export function fxPayload(fx, company, client, editing) {
  if (client?.channel !== 'mayorista') return {};
  const v = fxValue(fx, company);
  if (v === '' || v === null || fxError(v)) return {};
  if (editing && fx.orig !== null && Number(v) === Number(fx.orig)) return {};
  return { fx_rate_mxn_per_usd: Number(v), fx_reason: fx.reason || '' };
}

const Preview = ({ rate, totalMxn, pax }) => (
  <p className="text-sm text-ink-700" data-testid="fx-live-preview">
    Total: <b className="text-brand-600" data-testid="fx-live-total">{usdFmt(toUsd(totalMxn, rate))}</b>
    {pax > 0 && <> · Por persona (promedio): <b data-testid="fx-live-pp">{usdFmt(toUsd(Number(totalMxn) / pax, rate))}</b></>}
  </p>
);

// Iter 72: tipo de cambio editable por cotización (Mayorista internacional). Solo presentación USD.
export function FxRateField({ client, company, fx, setFx, totalMxn, pax }) {
  if (client?.channel !== 'mayorista') return null;
  const v = fxValue(fx, company);
  const err = fxError(v);
  const locked = !!fx.lock?.locked;
  const canUnlock = locked && fx.lock?.can_unlock;
  const changed = fx.orig === null ? v !== '' : Number(v) !== Number(fx.orig);
  return (
    <div className="rounded-xl border border-brand-100 bg-brand-50/50 p-4 space-y-2" data-testid="fx-rate-field">
      <label className="label-text flex items-center gap-1"><DollarSign className="w-3.5 h-3.5" /> Tipo de cambio (MXN por 1 USD)<HelpTip text={FX_HELP} testid="fx-rate-help" /></label>
      <input type="number" step="0.0001" min="0" className="input-field md:w-52" placeholder="Ej. 18.50" value={v ?? ''}
        disabled={locked && !canUnlock}
        onChange={(e) => setFx((f) => ({ ...f, rate: e.target.value }))} data-testid="fx-rate-input" />
      {err && <p className="text-xs text-red-600" data-testid="fx-rate-error">{err}</p>}
      {locked && (
        <p className="text-xs text-amber-800 flex items-start gap-1.5" data-testid="fx-locked-notice"><Lock className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          Bloqueado: la cotización {fx.lock.reason}. {canUnlock ? 'Como admin puedes cambiarlo indicando el motivo (obligatorio).' : 'Solo un admin puede cambiarlo.'}</p>
      )}
      {changed && (!locked || canUnlock) && (
        <input className="input-field text-sm" maxLength={300} placeholder={locked ? 'Motivo del desbloqueo (obligatorio)' : 'Motivo del cambio (opcional)'}
          value={fx.reason} onChange={(e) => setFx((f) => ({ ...f, reason: e.target.value }))} data-testid="fx-reason-input" />
      )}
      {v !== '' && !err ? <Preview rate={v} totalMxn={totalMxn} pax={pax} /> : (
        <p className="text-xs text-amber-800 flex items-start gap-1.5" data-testid="fx-missing-warning"><AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          Sin tipo de cambio: el cliente verá esta cotización solo en MXN.</p>
      )}
      <p className="text-[11px] text-ink-500">El cobro siempre es en MXN; el USD es solo de referencia y se guarda con esta cotización.</p>
    </div>
  );
}
