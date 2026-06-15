import { Landmark } from 'lucide-react';

export const BankingSettings = ({ integ, setInteg }) => (
  <div className="mt-8 pt-6 border-t border-ink-100" data-testid="bank-section">
    <h3 className="font-semibold text-ink-900 flex items-center gap-2"><Landmark className="w-4 h-4 text-brand-500" /> Transferencia bancaria (Opción B de pago)</h3>
    <p className="text-sm text-ink-500 mt-1">Datos que verá el cliente en el enlace público para pagar por transferencia. El ejecutivo marca el pago como recibido desde el detalle de la cotización.</p>
    <label className="flex items-center gap-2 cursor-pointer mt-3">
      <input type="checkbox" checked={!!integ.bank_enabled} onChange={(e) => setInteg((s) => ({ ...s, bank_enabled: e.target.checked }))} data-testid="bank-enabled-input" />
      <span className="text-sm text-ink-700">Habilitar pago por transferencia en el enlace público</span>
    </label>
    <div className="grid md:grid-cols-2 gap-4 mt-4">
      <div><label className="label-text">Banco</label><input className="input-field" value={integ.bank_name || ''} onChange={(e) => setInteg((s) => ({ ...s, bank_name: e.target.value }))} data-testid="bank-name-input" /></div>
      <div><label className="label-text">Titular de la cuenta</label><input className="input-field" value={integ.bank_holder || ''} onChange={(e) => setInteg((s) => ({ ...s, bank_holder: e.target.value }))} data-testid="bank-holder-input" /></div>
      <div><label className="label-text">CLABE (nacional)</label><input className="input-field" value={integ.bank_clabe || ''} onChange={(e) => setInteg((s) => ({ ...s, bank_clabe: e.target.value }))} data-testid="bank-clabe-input" /></div>
      <div><label className="label-text">Número de cuenta</label><input className="input-field" value={integ.bank_account || ''} onChange={(e) => setInteg((s) => ({ ...s, bank_account: e.target.value }))} data-testid="bank-account-input" /></div>
      <div><label className="label-text">Cuenta USD (internacional)</label><input className="input-field" value={integ.bank_usd_account || ''} onChange={(e) => setInteg((s) => ({ ...s, bank_usd_account: e.target.value }))} data-testid="bank-usd-input" /></div>
      <div><label className="label-text">SWIFT / BIC</label><input className="input-field" value={integ.bank_swift || ''} onChange={(e) => setInteg((s) => ({ ...s, bank_swift: e.target.value }))} data-testid="bank-swift-input" /></div>
      <div><label className="label-text">ABA / Routing</label><input className="input-field" value={integ.bank_aba || ''} onChange={(e) => setInteg((s) => ({ ...s, bank_aba: e.target.value }))} data-testid="bank-aba-input" /></div>
      <div><label className="label-text">Domicilio del banco</label><input className="input-field" value={integ.bank_address || ''} onChange={(e) => setInteg((s) => ({ ...s, bank_address: e.target.value }))} data-testid="bank-address-input" /></div>
    </div>
  </div>
);
