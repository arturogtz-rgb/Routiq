import { CreditCard, Coins, Trash2 } from 'lucide-react';

export const PaymentSettings = ({ integ, setInteg, clearStripeSecret }) => (
  <div className="space-y-4">
    <h3 className="font-semibold text-ink-900 flex items-center gap-2"><CreditCard className="w-4 h-4 text-brand-500" /> Stripe (cobros)</h3>
    <div>
      <label className="label-text">Clave publicable (pk_live / pk_test)</label>
      <input className="input-field" value={integ.stripe_publishable_key || ''}
        onChange={(e) => setInteg((s) => ({ ...s, stripe_publishable_key: e.target.value }))} data-testid="stripe-pk-input" />
    </div>
    <div>
      <label className="label-text">Clave secreta (sk_live / sk_test)</label>
      <input type="password" className="input-field" placeholder={integ.stripe_secret_set ? `Guardada ${integ.stripe_secret_key_masked}` : 'sk_...'}
        value={integ.stripe_secret_key || ''} onChange={(e) => setInteg((s) => ({ ...s, stripe_secret_key: e.target.value }))} data-testid="stripe-sk-input" />
      <div className="flex items-center justify-between mt-1">
        <p className="text-xs text-ink-400">Déjala vacía para conservar la actual. Nunca se muestra completa.</p>
        {integ.stripe_secret_set && (
          <button type="button" onClick={clearStripeSecret} className="text-xs text-red-600 hover:text-red-700 inline-flex items-center gap-1" data-testid="clear-stripe-secret-btn">
            <Trash2 className="w-3.5 h-3.5" /> Borrar clave guardada
          </button>
        )}
      </div>
    </div>
    <label className="flex items-center gap-2 cursor-pointer">
      <input type="checkbox" checked={!!integ.stripe_enabled} onChange={(e) => setInteg((s) => ({ ...s, stripe_enabled: e.target.checked }))} data-testid="stripe-enabled-input" />
      <span className="text-sm text-ink-700">Habilitar cobros con Stripe en el enlace público</span>
    </label>
    <p className="text-xs text-ink-400 -mt-1">Con tu propia clave secreta, la confirmación del pago es automática. Sin clave propia se usa el modo de prueba.</p>
    <div className="grid grid-cols-2 gap-3">
      <div>
        <label className="label-text flex items-center gap-1"><Coins className="w-3.5 h-3.5" /> Moneda base</label>
        <select className="input-field" value={integ.base_currency || 'MXN'} onChange={(e) => setInteg((s) => ({ ...s, base_currency: e.target.value }))} data-testid="base-currency-input">
          <option value="MXN">MXN — Peso mexicano</option>
          <option value="USD">USD — Dólar</option>
        </select>
      </div>
      <div>
        <label className="label-text">Anticipo / depósito (%)</label>
        <input type="number" min="1" max="100" className="input-field" value={integ.deposit_percent || 50}
          onChange={(e) => setInteg((s) => ({ ...s, deposit_percent: +e.target.value }))} data-testid="deposit-percent-input" />
      </div>
    </div>
  </div>
);
