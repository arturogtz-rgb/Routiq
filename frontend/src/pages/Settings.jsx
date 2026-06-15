import { useEffect, useState, useRef } from 'react';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { CreditCard, Save } from 'lucide-react';
import { LogoSettings } from '@/components/settings/LogoSettings';
import { PricingSettings, PricingExample } from '@/components/settings/PricingSettings';
import { PaymentSettings } from '@/components/settings/PaymentSettings';
import { EmailSettings } from '@/components/settings/EmailSettings';
import { BankingSettings } from '@/components/settings/BankingSettings';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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
    setInteg({ ...ig.data, stripe_secret_key: '', resend_api_key: '', smtp_password: '', gmail_client_secret: '' });
  };

  useEffect(() => { reload(); }, []);

  // Handle return from Gmail OAuth (?gmail=connected|error|norefresh)
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get('gmail');
    if (!p) return;
    if (p === 'connected') setOk('Gmail conectado correctamente.');
    else if (p === 'norefresh') setError('Google no devolvió token. Revoca el acceso en tu cuenta de Google y vuelve a conectar.');
    else setError('No se pudo conectar Gmail. Verifica el Client ID/Secret y la Redirect URI.');
    window.history.replaceState({}, '', window.location.pathname);
    setTimeout(() => { setOk(''); setError(''); }, 6000);
  }, []);

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
    if (integ.notify_email && !EMAIL_RE.test(integ.notify_email.trim())) {
      setError('El "Correo de avisos" debe ser una dirección de correo completa, ej: reservas@aventurateporjalisco.com');
      return;
    }
    try {
      const payload = { ...integ };
      // don't send masked placeholders or empty secrets
      if (!payload.stripe_secret_key) delete payload.stripe_secret_key;
      if (!payload.resend_api_key) delete payload.resend_api_key;
      if (!payload.smtp_password) delete payload.smtp_password;
      if (!payload.gmail_client_secret) delete payload.gmail_client_secret;
      const { data } = await api.patch('/companies/me/integrations', payload);
      setInteg({ ...data, stripe_secret_key: '', resend_api_key: '', smtp_password: '', gmail_client_secret: '' });
      setOk('Integraciones guardadas');
      setTimeout(() => setOk(''), 2500);
    } catch (e) { setError(formatApiError(e)); }
  };

  const connectGmail = async () => {
    setError(''); setOk('');
    try {
      const { data } = await api.get('/oauth/gmail/authorize');
      window.location.href = data.url;
    } catch (e) { setError(formatApiError(e)); }
  };

  const disconnectGmail = async () => {
    if (!window.confirm('¿Desconectar Gmail? Las cotizaciones dejarán de enviarse desde tu cuenta de Google.')) return;
    try {
      const { data } = await api.post('/oauth/gmail/disconnect');
      setInteg({ ...data, stripe_secret_key: '', resend_api_key: '', smtp_password: '', gmail_client_secret: '' });
      setOk('Gmail desconectado');
      setTimeout(() => setOk(''), 2500);
    } catch (e) { setError(formatApiError(e)); }
  };

  const clearStripeSecret = async () => {
    if (!window.confirm('¿Borrar la clave secreta de Stripe guardada? Se desactivarán los cobros con Stripe hasta que ingreses una nueva.')) return;
    setError(''); setOk('');
    try {
      const { data } = await api.delete('/companies/me/integrations/stripe-secret');
      setInteg({ ...data, stripe_secret_key: '', resend_api_key: '', smtp_password: '' });
      setOk('Clave secreta de Stripe eliminada');
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
          <LogoSettings company={company} uploading={uploading} fileInputRef={fileInputRef}
            uploadLogo={uploadLogo} removeLogo={removeLogo} backend={backend} />
          <hr className="border-ink-100" />
          <PricingSettings pricing={pricing} setPricing={setPricing} save={save} marginPct={marginPct} />
        </div>
        <PricingExample pricing={pricing} />
      </div>

      {integ && (
        <div className="card-surface p-6 mt-6" data-testid="integrations-card">
          <h2 className="font-display font-semibold text-lg text-ink-900 flex items-center gap-2"><CreditCard className="w-5 h-5 text-brand-500" /> Pagos e integraciones</h2>
          <p className="text-sm text-ink-500 mt-1">Conecta tu propia cuenta de Stripe y tu correo. Todo se configura aquí, sin tocar servidores.</p>

          <div className="grid lg:grid-cols-2 gap-8 mt-5">
            <PaymentSettings integ={integ} setInteg={setInteg} clearStripeSecret={clearStripeSecret} />
            <EmailSettings integ={integ} setInteg={setInteg} company={company} backend={backend}
              connectGmail={connectGmail} disconnectGmail={disconnectGmail}
              testSmtp={testSmtp} smtpTesting={smtpTesting} smtpTestEmail={smtpTestEmail} setSmtpTestEmail={setSmtpTestEmail} />
          </div>

          <BankingSettings integ={integ} setInteg={setInteg} />

          <div className="pt-4 mt-2 border-t border-ink-100 flex justify-end">
            <button className="btn-primary" onClick={saveInteg} data-testid="save-integrations-btn"><Save className="w-4 h-4" /> Guardar integraciones</button>
          </div>
        </div>
      )}
    </AppShell>
  );
}
