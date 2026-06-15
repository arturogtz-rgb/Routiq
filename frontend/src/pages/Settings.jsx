import { useEffect, useState, useRef } from 'react';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { Save, Calculator, Percent, Upload, Image as ImageIcon, X, CreditCard, Mail, Coins, Landmark, Server, Send } from 'lucide-react';

export default function Settings() {
  const [company, setCompany] = useState(null);
  const [pricing, setPricing] = useState(null);
  const [integ, setInteg] = useState(null);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [uploading, setUploading] = useState(false);
  const [smtpTesting, setSmtpTesting] = useState(false);
  const [smtpTestEmail, setSmtpTestEmail] = useState('');
  const fileInputRef = useRef(null);
  const backend = process.env.REACT_APP_BACKEND_URL || '';

  const reload = async () => {
    const [{ data }, ig] = await Promise.all([api.get('/companies/me'), api.get('/companies/me/integrations')]);
    setCompany(data);
    setPricing(data.pricing_config);
    setInteg({ ...ig.data, stripe_secret_key: '', resend_api_key: '', smtp_password: '' });
  };

  useEffect(() => { reload(); }, []);

  const save = async () => {
    setError(''); setOk('');
    try {
      const { data } = await api.patch('/companies/me/pricing', pricing);
      setCompany(data); setOk('Configuración guardada');
      setTimeout(() => setOk(''), 2500);
    } catch (e) { setError(formatApiError(e)); }
  };

  const saveInteg = async () => {
    setError(''); setOk('');
    try {
      const payload = { ...integ };
      // don't send masked placeholders or empty secrets
      if (!payload.stripe_secret_key) delete payload.stripe_secret_key;
      if (!payload.resend_api_key) delete payload.resend_api_key;
      if (!payload.smtp_password) delete payload.smtp_password;
      const { data } = await api.patch('/companies/me/integrations', payload);
      setInteg({ ...data, stripe_secret_key: '', resend_api_key: '', smtp_password: '' });
      setOk('Integraciones guardadas');
      setTimeout(() => setOk(''), 2500);
    } catch (e) { setError(formatApiError(e)); }
  };

  const testSmtp = async () => {
    setError(''); setOk(''); setSmtpTesting(true);
    try {
      const { data } = await api.post('/companies/me/test-smtp', {
        smtp_host: integ.smtp_host,
        smtp_port: Number(integ.smtp_port) || 587,
        smtp_username: integ.smtp_username,
        smtp_password: integ.smtp_password || '',
        smtp_use_tls: integ.smtp_use_tls !== false,
        smtp_from_email: integ.smtp_from_email,
        smtp_from_name: integ.smtp_from_name || '',
        to_email: smtpTestEmail || undefined,
      });
      setOk(`Correo de prueba enviado a ${data.to}. Revisa la bandeja de entrada.`);
      setTimeout(() => setOk(''), 5000);
    } catch (e) { setError(formatApiError(e)); }
    finally { setSmtpTesting(false); }
  };

  const uploadLogo = async (file) => {
    if (!file) return;
    setError(''); setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await api.post('/companies/me/logo', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setCompany(data);
      setOk('Logo actualizado');
      setTimeout(() => setOk(''), 2500);
    } catch (e) { setError(formatApiError(e)); }
    finally { setUploading(false); }
  };

  const removeLogo = async () => {
    if (!window.confirm('¿Eliminar el logo actual?')) return;
    try {
      const { data } = await api.delete('/companies/me/logo');
      setCompany(data);
    } catch (e) { setError(formatApiError(e)); }
  };

  if (!pricing) return <AppShell><div className="p-8 text-ink-400">Cargando…</div></AppShell>;

  const marginPct = Math.round((1 - pricing.margin_divisor) * 100);

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight">Ajustes de empresa</h1>
        <p className="text-ink-500 mt-1">Motor de precios de <span className="font-semibold text-ink-900">{company?.name}</span>.</p>
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="settings-error">{error}</div>}
      {ok && <div className="rounded-xl border border-emerald-200 bg-mint-100 text-emerald-800 px-4 py-3 text-sm mb-4" data-testid="settings-ok">{ok}</div>}

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 card-surface p-6 space-y-6">
          {/* Logo upload */}
          <div>
            <h2 className="font-display font-semibold text-lg text-ink-900 flex items-center gap-2"><ImageIcon className="w-5 h-5 text-brand-500" /> Logo de empresa</h2>
            <p className="text-sm text-ink-500 mt-1">Aparece en el sidebar, los PDF y el enlace público del cliente. Recomendado: PNG/SVG transparente, máx 2 MB.</p>
            <div className="mt-4 flex items-center gap-5">
              <div className="w-28 h-28 rounded-2xl border-2 border-dashed border-ink-200 bg-cream flex items-center justify-center overflow-hidden" data-testid="logo-preview">
                {company?.logo_url
                  ? <img src={`${backend}${company.logo_url}`} alt="Logo" className="max-w-full max-h-full object-contain" />
                  : <ImageIcon className="w-10 h-10 text-ink-300" />}
              </div>
              <div className="flex-1">
                <input ref={fileInputRef} type="file" accept="image/*" className="hidden"
                  onChange={(e) => uploadLogo(e.target.files?.[0])} data-testid="logo-file-input" />
                <button className="btn-primary text-sm" disabled={uploading}
                  onClick={() => fileInputRef.current?.click()} data-testid="upload-logo-btn">
                  <Upload className="w-4 h-4" /> {uploading ? 'Subiendo…' : (company?.logo_url ? 'Cambiar logo' : 'Subir logo')}
                </button>
                {company?.logo_url && (
                  <button className="btn-ghost text-sm ml-2 text-red-600" onClick={removeLogo} data-testid="remove-logo-btn">
                    <X className="w-4 h-4" /> Quitar
                  </button>
                )}
              </div>
            </div>
          </div>

          <hr className="border-ink-100" />

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
              {[
                { k: 'directo', label: 'Directo' },
                { k: 'agencia', label: 'Agencia' },
                { k: 'mayorista', label: 'Mayorista' },
                { k: 'operador', label: 'Operador' },
              ].map(({ k, label }) => (
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
        </div>

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
      </div>

      {/* Pagos e integraciones */}
      {integ && (
        <div className="card-surface p-6 mt-6" data-testid="integrations-card">
          <h2 className="font-display font-semibold text-lg text-ink-900 flex items-center gap-2"><CreditCard className="w-5 h-5 text-brand-500" /> Pagos e integraciones</h2>
          <p className="text-sm text-ink-500 mt-1">Conecta tu propia cuenta de Stripe y tu correo. Todo se configura aquí, sin tocar servidores.</p>

          <div className="grid lg:grid-cols-2 gap-8 mt-5">
            {/* Stripe */}
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
                <p className="text-xs text-ink-400 mt-1">Déjala vacía para conservar la actual. Nunca se muestra completa.</p>
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

            {/* Email (Resend o SMTP propio) */}
            <div className="space-y-4">
              <h3 className="font-semibold text-ink-900 flex items-center gap-2"><Mail className="w-4 h-4 text-brand-500" /> Correo saliente</h3>
              <div>
                <label className="label-text">Proveedor de envío</label>
                <select className="input-field" value={integ.email_provider || 'resend'}
                  onChange={(e) => setInteg((s) => ({ ...s, email_provider: e.target.value }))} data-testid="email-provider-select">
                  <option value="resend">Resend (API)</option>
                  <option value="smtp">SMTP propio (correo corporativo)</option>
                </select>
                <p className="text-xs text-ink-400 mt-1">Las cotizaciones y cobros se enviarán con el proveedor seleccionado.</p>
              </div>

              {(integ.email_provider || 'resend') === 'resend' ? (
                <>
                  <div>
                    <label className="label-text">API key de Resend</label>
                    <input type="password" className="input-field" placeholder={integ.resend_api_key_set ? `Guardada ${integ.resend_api_key_masked}` : 're_...'}
                      value={integ.resend_api_key || ''} onChange={(e) => setInteg((s) => ({ ...s, resend_api_key: e.target.value }))} data-testid="resend-key-input" />
                  </div>
                  <div>
                    <label className="label-text">Correo remitente (verificado en Resend)</label>
                    <input className="input-field" value={integ.resend_from_email || ''} placeholder="no-reply@tudominio.com"
                      onChange={(e) => setInteg((s) => ({ ...s, resend_from_email: e.target.value }))} data-testid="resend-from-input" />
                  </div>
                  <div>
                    <label className="label-text">Nombre remitente</label>
                    <input className="input-field" value={integ.resend_from_name || ''} placeholder={company?.name || 'Tu empresa'}
                      onChange={(e) => setInteg((s) => ({ ...s, resend_from_name: e.target.value }))} data-testid="resend-name-input" />
                  </div>
                </>
              ) : (
                <div className="rounded-xl border border-ink-100 bg-cream/50 p-4 space-y-3" data-testid="smtp-section">
                  <p className="text-xs text-ink-500 flex items-center gap-1.5"><Server className="w-3.5 h-3.5" /> Datos de tu servidor de correo (Gmail, Outlook, cPanel, etc.).</p>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="col-span-2"><label className="label-text">Servidor SMTP (host)</label><input className="input-field" placeholder="smtp.gmail.com" value={integ.smtp_host || ''} onChange={(e) => setInteg((s) => ({ ...s, smtp_host: e.target.value }))} data-testid="smtp-host-input" /></div>
                    <div><label className="label-text">Puerto</label><input type="number" className="input-field" placeholder="587" value={integ.smtp_port || 587} onChange={(e) => setInteg((s) => ({ ...s, smtp_port: e.target.value }))} data-testid="smtp-port-input" /></div>
                    <div className="flex items-end pb-2">
                      <label className="flex items-center gap-2 cursor-pointer text-sm text-ink-700">
                        <input type="checkbox" checked={integ.smtp_use_tls !== false} onChange={(e) => setInteg((s) => ({ ...s, smtp_use_tls: e.target.checked }))} data-testid="smtp-tls-input" />
                        Usar TLS/STARTTLS
                      </label>
                    </div>
                    <div className="col-span-2"><label className="label-text">Usuario</label><input className="input-field" placeholder="tucorreo@tudominio.com" value={integ.smtp_username || ''} onChange={(e) => setInteg((s) => ({ ...s, smtp_username: e.target.value }))} data-testid="smtp-username-input" /></div>
                    <div className="col-span-2">
                      <label className="label-text">Contraseña / App Password</label>
                      <input type="password" className="input-field" placeholder={integ.smtp_password_set ? 'Guardada ••••' : 'Contraseña del correo'}
                        value={integ.smtp_password || ''} onChange={(e) => setInteg((s) => ({ ...s, smtp_password: e.target.value }))} data-testid="smtp-password-input" />
                      <p className="text-xs text-ink-400 mt-1">Déjala vacía para conservar la actual. En Gmail usa una "Contraseña de aplicación".</p>
                    </div>
                    <div className="col-span-2"><label className="label-text">Correo remitente (From)</label><input className="input-field" placeholder="ventas@tudominio.com" value={integ.smtp_from_email || ''} onChange={(e) => setInteg((s) => ({ ...s, smtp_from_email: e.target.value }))} data-testid="smtp-from-input" /></div>
                    <div className="col-span-2"><label className="label-text">Nombre remitente</label><input className="input-field" placeholder={company?.name || 'Tu empresa'} value={integ.smtp_from_name || ''} onChange={(e) => setInteg((s) => ({ ...s, smtp_from_name: e.target.value }))} data-testid="smtp-from-name-input" /></div>
                  </div>
                  <div className="pt-2 border-t border-ink-100">
                    <label className="label-text">Enviar prueba a (opcional)</label>
                    <div className="flex gap-2">
                      <input className="input-field flex-1" placeholder={integ.smtp_from_email || 'correo@destino.com'} value={smtpTestEmail} onChange={(e) => setSmtpTestEmail(e.target.value)} data-testid="smtp-test-email-input" />
                      <button className="btn-ghost whitespace-nowrap" onClick={testSmtp} disabled={smtpTesting || !integ.smtp_host || !integ.smtp_username} data-testid="smtp-test-btn">
                        <Send className="w-4 h-4" /> {smtpTesting ? 'Enviando…' : 'Probar'}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              <div>
                <label className="label-text">Correo de avisos (ventas / ejecutivo)</label>
                <input className="input-field" value={integ.notify_email || ''} placeholder="ventas@tudominio.com"
                  onChange={(e) => setInteg((s) => ({ ...s, notify_email: e.target.value }))} data-testid="notify-email-input" />
                <p className="text-xs text-ink-400 mt-1">Recibe avisos cuando un cliente acepta o paga una cotización.</p>
              </div>
            </div>
          </div>

          {/* Bank transfer (Opción B) */}
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

          <div className="pt-4 mt-2 border-t border-ink-100 flex justify-end">
            <button className="btn-primary" onClick={saveInteg} data-testid="save-integrations-btn"><Save className="w-4 h-4" /> Guardar integraciones</button>
          </div>
        </div>
      )}
    </AppShell>
  );
}
