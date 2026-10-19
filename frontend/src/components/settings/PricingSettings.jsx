import { Calculator, Percent, Save } from 'lucide-react';
import { HelpTip } from '@/components/HelpTip';

const CHANNELS = [
  { k: 'directo', label: 'Directo', tip: 'Cliente final. Ve el precio público (neto ÷ divisor). Normalmente 0%.' },
  { k: 'agencia', label: 'Agencia', tip: 'Las tarifas netas se muestran a precio público (no se comisionan). Los conceptos de precio público llevan este % de descuento.' },
  { k: 'mayorista', label: 'Mayorista', tip: 'Precio público menos este %, tanto en tarifas netas como en conceptos de precio público. Precio neto no comisionable.' },
  { k: 'operador', label: 'Mayorista Preferencial', tip: 'Las tarifas netas se muestran sin divisor (neto original). Los conceptos de precio público llevan este % de descuento.' },
];

export const PricingSettings = ({ pricing, setPricing, save, marginPct }) => (
  <>
    <div>
      <h2 className="font-display font-semibold text-lg text-ink-900 flex items-center gap-2"><Calculator className="w-5 h-5 text-brand-500" /> Fórmula base<HelpTip text="El divisor convierte la tarifa neta en precio público: público = neto ÷ divisor. Ej. $700 ÷ 0.80 = $875 (margen 20%)." testid="help-margin-formula" /></h2>
      <p className="text-sm text-ink-500 mt-1">Costo total ÷ divisor = precio público. Ej: 0.76 ⇒ margen del 24%.</p>
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

export const PricingExample = ({ pricing }) => (
  <aside className="card-surface p-6">
    <h3 className="font-display font-semibold text-ink-900">Ejemplo</h3>
    <p className="text-sm text-ink-500 mt-1">Cómo se aplica a un costo de $7,600 MXN:</p>
    <div className="mt-4 space-y-2 text-sm">
      <div className="flex justify-between"><span>Costo base</span><span className="font-semibold">$7,600</span></div>
      <div className="flex justify-between"><span>÷ {pricing.margin_divisor}</span><span className="font-semibold">$ {(7600 / pricing.margin_divisor).toFixed(0)}</span></div>
      <div className="rounded-lg bg-mint-100 text-emerald-800 p-3">
        <p className="text-xs font-bold uppercase tracking-widest">Precio público</p>
        <p className="font-display text-2xl font-bold">${(7600 / pricing.margin_divisor).toFixed(0)}</p>
      </div>
      <p className="text-xs text-ink-400">Comisión agencia {(pricing.commissions.agencia * 100).toFixed(0)}%: -${((7600 / pricing.margin_divisor) * pricing.commissions.agencia).toFixed(0)}</p>
    </div>
  </aside>
);
