import { Calculator, Percent, Save } from 'lucide-react';
import { HelpTip } from '@/components/HelpTip';

const CHANNELS = [
  { k: 'directo', label: 'Directo', tip: 'Cliente final. Ve el precio público (neto ÷ divisor). Normalmente 0%.' },
  { k: 'agencia', label: 'Agencia', tip: 'Las tarifas netas se muestran a precio público (no se comisionan). Los conceptos de precio público llevan este % de descuento.' },
  { k: 'mayorista', label: 'Mayorista internacional', tip: 'Precio público menos este %, tanto en tarifas netas como en conceptos de precio público. Precio neto no comisionable.' },
  { k: 'operador', label: 'Mayorista Preferencial', tip: 'Las tarifas netas se muestran sin divisor (neto original). Los conceptos de precio público llevan este % de descuento.' },
];

const FX_TIP = 'Lo captura el administrador y NO se actualiza solo. Solo afecta la presentación en USD de las cotizaciones del canal Mayorista internacional; el cobro siempre es en MXN. Cada cotización guarda el tipo de cambio con el que se creó.';
const fxError = (v) => {
  if (v === '' || v === null || v === undefined) return '';
  const n = Number(v);
  if (!(n > 0)) return 'Debe ser un número mayor que 0.';
  if (Math.round(n * 10000) / 10000 !== n) return 'Máximo 4 decimales.';
  return '';
};

const FxSettings = ({ pricing, setPricing }) => {
  const v = pricing.fx_mayorista_mxn_per_usd ?? '';
  const err = fxError(v);
  const upd = pricing.fx_mayorista_updated_at;
  return (
    <div data-testid="fx-settings">
      <h2 className="font-display font-semibold text-lg text-ink-900">Tipo de cambio para Mayorista internacional (MXN por 1 USD)<HelpTip text={FX_TIP} testid="help-fx-mayorista" /></h2>
      <div className="grid md:grid-cols-2 gap-4 mt-4">
        <div>
          <label className="label-text">MXN por 1 USD</label>
          <input type="number" step="0.0001" min="0" className="input-field" placeholder="Ej. 18.50" value={v}
            onChange={(e) => setPricing((p) => ({ ...p, fx_mayorista_mxn_per_usd: e.target.value === '' ? null : +e.target.value }))} data-testid="fx-mayorista-input" />
          {err && <p className="text-xs text-red-600 mt-1" data-testid="fx-mayorista-error">{err}</p>}
        </div>
        <div className="flex items-end">
          <p className="text-sm text-ink-500" data-testid="fx-mayorista-updated">
            {upd ? `Última actualización: ${new Date(upd).toLocaleString('es-MX', { dateStyle: 'medium', timeStyle: 'short' })}` : 'Sin capturar: las cotizaciones de este canal se muestran solo en MXN.'}
          </p>
        </div>
      </div>
    </div>
  );
};

export { fxError };

export const PricingSettings = ({ pricing, setPricing, save, marginPct }) => (
  <>
    <div>
      <h2 className="font-display font-semibold text-lg text-ink-900 flex items-center gap-2"><Calculator className="w-5 h-5 text-brand-500" /> Fórmula base<HelpTip text="El divisor convierte la tarifa neta en precio público: público = neto ÷ divisor. Ej. $700 ÷ 0.80 = $875 (margen 20%)." testid="help-margin-formula" /></h2>
      <p className="text-sm text-ink-500 mt-1">Costo total ÷ divisor = precio público. Ej: {pricing.margin_divisor} ⇒ margen del {marginPct}%.</p>
      <div className="grid md:grid-cols-2 gap-4 mt-4">
        <div>
          <label className="label-text">Divisor de margen<HelpTip text="Valor entre 0.1 y 1. Margen equivalente = 1 − divisor. 0.80 ⇒ 20% de margen." testid="help-margin-divisor" /></label>
          <input type="number" step="0.01" min="0.1" max="1" className="input-field" value={pricing.margin_divisor}
            onChange={(e) => setPricing((p) => ({ ...p, margin_divisor: +e.target.value }))} data-testid="margin-divisor-input" />
        </div>
        <div className="flex items-end">
          <div className="rounded-xl bg-brand-50 text-brand-500 px-5 py-4 w-full">
            <p className="text-xs uppercase tracking-widest font-bold">Margen equivalente</p>
            <p className="font-display text-3xl font-bold">{marginPct}%</p>
          </div>
        </div>
      </div>
    </div>

    <div>
      <h2 className="font-display font-semibold text-lg text-ink-900 flex items-center gap-2"><Percent className="w-5 h-5 text-brand-500" /> Comisiones por canal<HelpTip text="La comisión se aplica concepto por concepto antes de armar el precio por persona: las tarifas netas ya traen su precio de canal; los conceptos de precio público llevan el % del canal." testid="help-commissions" /></h2>
      <div className="grid md:grid-cols-2 gap-4 mt-4">
        {CHANNELS.map(({ k, label, tip }) => (
          <div key={k}>
            <label className="label-text">{label} (decimal, ej. 0.10 = 10%)<HelpTip text={tip} testid={`help-commission-${k}`} /></label>
            <input type="number" step="0.01" min="0" max="1" className="input-field"
              value={pricing.commissions[k]}
              onChange={(e) => setPricing((p) => ({ ...p, commissions: { ...p.commissions, [k]: +e.target.value } }))}
              data-testid={`commission-${k}`} />
          </div>
        ))}
      </div>
    </div>

    <FxSettings pricing={pricing} setPricing={setPricing} />

    <div>
      <h2 className="font-display font-semibold text-lg text-ink-900">Menores</h2>
      <div className="grid md:grid-cols-3 gap-4 mt-4">
        <div><label className="label-text">Edad mín.</label><input type="number" className="input-field" value={pricing.minor_age_min} onChange={(e) => setPricing((p) => ({ ...p, minor_age_min: +e.target.value }))} data-testid="minor-min" /></div>
        <div><label className="label-text">Edad máx.</label><input type="number" className="input-field" value={pricing.minor_age_max} onChange={(e) => setPricing((p) => ({ ...p, minor_age_max: +e.target.value }))} data-testid="minor-max" /></div>
        <div><label className="label-text">Descuento (decimal)</label><input type="number" step="0.01" className="input-field" value={pricing.minor_discount} onChange={(e) => setPricing((p) => ({ ...p, minor_discount: +e.target.value }))} data-testid="minor-discount" /></div>
      </div>
    </div>

    <div className="pt-4 border-t border-ink-100 flex justify-end">
      <button className="btn-primary" onClick={save} data-testid="save-pricing-btn"><Save className="w-4 h-4" /> Guardar</button>
    </div>
  </>
);

const fmt = (v) => `$${Math.round(v).toLocaleString('es-MX')}`;

export const PricingExample = ({ pricing }) => {
  const pub = 7600 / (pricing.margin_divisor || 1);
  return (
    <aside className="card-surface p-6">
      <h3 className="font-display font-semibold text-ink-900">Ejemplo</h3>
      <p className="text-sm text-ink-500 mt-1">Cómo se aplica a un costo de $7,600 MXN:</p>
      <div className="mt-4 space-y-2 text-sm">
        <div className="flex justify-between"><span>Costo base</span><span className="font-semibold">$7,600</span></div>
        <div className="flex justify-between"><span>÷ {pricing.margin_divisor}</span><span className="font-semibold" data-testid="pricing-example-public">{fmt(pub)}</span></div>
        <div className="rounded-lg bg-mint-100 text-emerald-800 p-3">
          <p className="text-xs font-bold uppercase tracking-widest">Precio público</p>
          <p className="font-display text-2xl font-bold">{fmt(pub)}</p>
        </div>
        <p className="text-xs text-ink-400">Comisión agencia {(pricing.commissions.agencia * 100).toFixed(0)}%: −{fmt(pub * pricing.commissions.agencia)}</p>
      </div>
    </aside>
  );
};
