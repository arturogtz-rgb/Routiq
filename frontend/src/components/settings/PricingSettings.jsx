import { Calculator, Percent, Save } from 'lucide-react';

const CHANNELS = [
  { k: 'directo', label: 'Directo' },
  { k: 'agencia', label: 'Agencia' },
  { k: 'mayorista', label: 'Mayorista' },
  { k: 'operador', label: 'Mayorista Preferencial' },
];

export const PricingSettings = ({ pricing, setPricing, save, marginPct }) => (
  <>
    <div>
      <h2 className="font-display font-semibold text-lg text-ink-900 flex items-center gap-2"><Calculator className="w-5 h-5 text-brand-500" /> Fórmula base</h2>
      <p className="text-sm text-ink-500 mt-1">Costo total ÷ divisor = precio público. Ej: 0.76 ⇒ margen del 24%.</p>
      <div className="grid md:grid-cols-2 gap-4 mt-4">
        <div>
          <label className="label-text">Divisor de margen</label>
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
      <h2 className="font-display font-semibold text-lg text-ink-900 flex items-center gap-2"><Percent className="w-5 h-5 text-brand-500" /> Comisiones por canal</h2>
      <div className="grid md:grid-cols-2 gap-4 mt-4">
        {CHANNELS.map(({ k, label }) => (
          <div key={k}>
            <label className="label-text">{label} (decimal, ej. 0.10 = 10%)</label>
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
