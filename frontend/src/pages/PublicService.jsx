import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import api, { formatApiError } from '@/lib/api';
import {
  Check, X, Calendar, Sparkles, Loader2, Clock, CalendarDays,
  CheckCircle2, Phone, Mail, Send, Printer, Share2, ArrowLeft,
} from 'lucide-react';

function money(v, c = 'MXN') { return v == null ? '' : `$${Number(v).toLocaleString('es-MX')} ${c}`; }
const UNIT_ES = { per_person: 'por persona', per_group: 'por grupo', per_day: 'por día', per_access: 'por acceso' };
const DUR_ES = { minutos: 'minutos', horas: 'horas', dias: 'días' };
const DAYS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

export default function PublicService() {
  const { slug, id } = useParams();
  const backend = process.env.REACT_APP_BACKEND_URL || '';
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', phone: '', travel_date: '', pax: '', message: '', company_website: '' });
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    (async () => {
      try { const { data } = await api.get(`/public/company/${slug}/service/${id}`); setData(data); }
      catch (e) { setError(formatApiError(e)); }
    })();
  }, [slug, id]);

  const submit = async () => {
    setFormError('');
    if (!form.name.trim()) { setFormError('Escribe tu nombre.'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) { setFormError('Escribe un correo válido.'); return; }
    setSending(true);
    try {
      await api.post(`/public/company/${slug}/service/${id}/request`, form);
      setSent(true);
    } catch (e) { setFormError(formatApiError(e)); }
    finally { setSending(false); }
  };

  const share = async () => {
    try { await navigator.clipboard.writeText(window.location.href); setCopied(true); setTimeout(() => setCopied(false), 2500); }
    catch { /* clipboard bloqueado */ }
  };

  if (error) return (
    <div className="min-h-screen flex items-center justify-center bg-cream p-6">
      <div className="text-center" data-testid="svc-public-error">
        <p className="text-2xl font-display font-semibold text-ink-900">Servicio no disponible</p>
        <p className="text-ink-500 mt-2">{error}</p>
      </div>
    </div>
  );
  if (!data) return <div className="min-h-screen flex items-center justify-center bg-cream"><Loader2 className="w-8 h-8 animate-spin text-ink-300" /></div>;

  const { service: s, company } = data;
  const brand = company.primary_color || '#185FA5';
  const logo = company.logo_url ? (company.logo_url.startsWith('http') ? company.logo_url : `${backend}${company.logo_url}`) : null;
  const heroImg = s.image_url ? (s.image_url.startsWith('http') ? s.image_url : `${backend}${s.image_url}`) : null;
  const days = (s.operating_days && s.operating_days.length > 0)
    ? s.operating_days.slice().sort((a, b) => a - b).map((d) => DAYS[d]).filter(Boolean)
    : null;

  return (
    <div className="min-h-screen bg-cream print:bg-white" data-testid="public-service-page">
      {/* Encabezado solo para impresión */}
      <div className="hidden print:block px-2 pt-2 mb-4">
        {logo && <img src={logo} alt={company.name} className="h-16 object-contain mb-2" />}
        <p className="font-bold text-lg text-ink-900">{company.name}</p>
        <p className="text-sm text-ink-600">{[company.contact_phone, company.contact_email].filter(Boolean).join(' · ')}</p>
        {company.address && <p className="text-sm text-ink-600">{company.address}</p>}
        <h1 className="text-2xl font-bold text-ink-900 mt-3">{s.name}</h1>
      </div>

      {/* Header */}
      <header className="bg-white border-b border-ink-100 sticky top-0 z-30 print:hidden">
        <div className="max-w-5xl mx-auto px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {logo ? <img src={logo} alt={company.name} className="h-9 max-w-[160px] object-contain" />
              : <span className="font-display font-bold text-lg text-ink-900">{company.name}</span>}
          </div>
          <div className="hidden sm:flex items-center gap-4 text-sm text-ink-500">
            {company.contact_phone && <span className="flex items-center gap-1"><Phone className="w-3.5 h-3.5" /> {company.contact_phone}</span>}
            {company.contact_email && <span className="flex items-center gap-1"><Mail className="w-3.5 h-3.5" /> {company.contact_email}</span>}
          </div>
        </div>
      </header>

      {/* Hero */}
      <div className="relative print:hidden">
        <div className="relative h-[300px] sm:h-[420px] w-full overflow-hidden bg-ink-200">
          {heroImg ? <img src={heroImg} alt={s.name} className="absolute inset-0 w-full h-full object-cover object-center" data-testid="svc-hero-image" />
            : <div className="absolute inset-0" style={{ background: `linear-gradient(135deg, ${brand}, #0f2f52)` }} />}
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
        </div>
        <div className="max-w-5xl mx-auto px-5">
          <div className="-mt-20 relative bg-white rounded-2xl shadow-xl p-6 sm:p-8">
            <Link to={`/c/${slug}/servicios`} className="inline-flex items-center gap-1 text-sm text-ink-400 hover:text-ink-700 mb-2" data-testid="svc-back-to-services"><ArrowLeft className="w-4 h-4" /> Volver a servicios</Link>
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
              <div>
                <h1 className="font-display text-3xl sm:text-4xl font-bold text-ink-900 tracking-tight" data-testid="svc-title">{s.name}</h1>
                <div className="flex flex-wrap items-center gap-4 mt-2 text-sm text-ink-500">
                  {s.duration_value > 0 && <span className="flex items-center gap-1" data-testid="svc-duration"><Clock className="w-4 h-4" /> {s.duration_value} {DUR_ES[s.duration_unit] || s.duration_unit}</span>}
                  <span className="flex items-center gap-1" data-testid="svc-days"><CalendarDays className="w-4 h-4" /> {days ? days.join(' · ') : 'Todos los días'}</span>
                </div>
              </div>
              <div className="text-left sm:text-right">
                <div className="print:hidden">
                  {s.public_price != null && (
                    <>
                      <p className="text-xs text-ink-400">Precio público</p>
                      <p className="font-display text-3xl font-bold" style={{ color: brand }} data-testid="svc-price">{money(s.public_price, s.currency)}<span className="text-sm text-ink-400"> {UNIT_ES[s.unit] || ''}</span></p>
                    </>
                  )}
                </div>
                <div className="mt-3 flex flex-wrap gap-2 sm:justify-end print:hidden">
                  <button onClick={share} className="inline-flex items-center gap-2 rounded-full px-4 py-3 font-semibold border border-ink-200 text-ink-700 hover:bg-ink-50 transition" data-testid="share-service-btn">
                    <Share2 className="w-4 h-4" /> {copied ? '¡Enlace copiado!' : 'Compartir'}
                  </button>
                  <button onClick={() => window.print()} className="inline-flex items-center gap-2 rounded-full px-4 py-3 font-semibold border border-ink-200 text-ink-700 hover:bg-ink-50 transition" data-testid="print-service-btn">
                    <Printer className="w-4 h-4" /> Imprimir
                  </button>
                  <button onClick={() => { setShowForm(true); setSent(false); }} className="inline-flex items-center gap-2 rounded-full px-6 py-3 text-white font-semibold shadow-lg hover:brightness-110 transition" style={{ background: brand }} data-testid="want-service-btn">
                    <Sparkles className="w-4 h-4" /> Quiero este servicio
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <main className="max-w-5xl mx-auto px-5 py-10 grid lg:grid-cols-3 gap-8 print:block print:py-0 print:px-2">
        <div className="lg:col-span-2 space-y-8">
          {s.description && (
            <section data-testid="svc-description">
              <h2 className="font-display text-xl font-semibold text-ink-900 mb-2">Sobre este servicio</h2>
              <p className="text-ink-600 leading-relaxed whitespace-pre-wrap">{s.description}</p>
            </section>
          )}

          <section className="grid sm:grid-cols-2 gap-6" data-testid="svc-meta">
            {s.duration_value > 0 && (
              <div>
                <h2 className="font-display text-lg font-semibold text-ink-900 mb-2 flex items-center gap-2"><Clock className="w-4 h-4" style={{ color: brand }} /> Duración</h2>
                <p className="text-sm text-ink-600">{s.duration_value} {DUR_ES[s.duration_unit] || s.duration_unit}</p>
              </div>
            )}
            <div>
              <h2 className="font-display text-lg font-semibold text-ink-900 mb-2 flex items-center gap-2"><CalendarDays className="w-4 h-4" style={{ color: brand }} /> Días de operación</h2>
              <p className="text-sm text-ink-600">{days ? days.join(' · ') : 'Todos los días'}</p>
            </div>
          </section>

          {(s.includes?.length > 0 || s.excludes?.length > 0) && (
            <section className="grid sm:grid-cols-2 gap-6">
              {s.includes?.length > 0 && (
                <div data-testid="svc-includes">
                  <h2 className="font-display text-lg font-semibold text-ink-900 mb-3">Incluye</h2>
                  <ul className="space-y-2">
                    {s.includes.map((x, i) => <li key={i} className="flex gap-2 text-sm text-ink-600"><Check className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" /> {x}</li>)}
                  </ul>
                </div>
              )}
              {s.excludes?.length > 0 && (
                <div data-testid="svc-excludes">
                  <h2 className="font-display text-lg font-semibold text-ink-900 mb-3">No incluye</h2>
                  <ul className="space-y-2">
                    {s.excludes.map((x, i) => <li key={i} className="flex gap-2 text-sm text-ink-400"><X className="w-4 h-4 text-ink-300 shrink-0 mt-0.5" /> {x}</li>)}
                  </ul>
                </div>
              )}
            </section>
          )}
        </div>

        {/* Side CTA */}
        <aside className="lg:sticky lg:top-20 h-fit print:hidden">
          <div className="bg-white rounded-2xl shadow-sm border border-ink-100 p-6">
            {s.public_price != null && (
              <>
                <p className="text-xs text-ink-400">Precio público</p>
                <p className="font-display text-2xl font-bold mb-3" style={{ color: brand }}>{money(s.public_price, s.currency)} <span className="text-sm text-ink-400">{UNIT_ES[s.unit] || ''}</span></p>
                <hr className="border-ink-100 mb-4" />
              </>
            )}
            <p className="text-sm text-ink-500">¿Te interesa? Cuéntanos tus fechas y te armamos una cotización personalizada.</p>
            <button onClick={() => { setShowForm(true); setSent(false); }} className="mt-4 w-full inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-white font-semibold shadow hover:brightness-110 transition" style={{ background: brand }} data-testid="want-service-btn-side">
              <Sparkles className="w-4 h-4" /> Quiero este servicio
            </button>
          </div>
        </aside>
      </main>

      <footer className="border-t border-ink-100 py-6 text-center text-xs text-ink-400 print:hidden">
        {company.name} · Catálogo con Routiq
      </footer>

      {/* Request form modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50 print:hidden" onClick={() => !sending && setShowForm(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="service-request-modal">
            {sent ? (
              <div className="text-center py-6" data-testid="svc-request-success">
                <CheckCircle2 className="w-14 h-14 mx-auto text-emerald-500 mb-3" />
                <h3 className="font-display text-xl font-semibold text-ink-900">¡Solicitud enviada!</h3>
                <p className="text-ink-500 mt-2">Un asesor de {company.name} te contactará muy pronto con tu cotización personalizada.</p>
                <button className="btn-primary mt-5" onClick={() => setShowForm(false)} data-testid="svc-request-success-close">Cerrar</button>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between mb-1">
                  <h3 className="font-display text-xl font-semibold text-ink-900">Solicitar cotización</h3>
                  <button onClick={() => setShowForm(false)} className="text-ink-400 hover:text-ink-700"><X className="w-5 h-5" /></button>
                </div>
                <p className="text-sm text-ink-500 mb-4">{s.name}</p>
                {formError && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-3 py-2 text-sm mb-3" data-testid="svc-request-error">{formError}</div>}
                <div className="space-y-3">
                  <input className="hidden" tabIndex="-1" autoComplete="off" value={form.company_website} onChange={(e) => setForm((f) => ({ ...f, company_website: e.target.value }))} />
                  <div><label className="label-text">Nombre completo *</label><input className="input-field" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} data-testid="svc-request-name" /></div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><label className="label-text">Correo *</label><input type="email" className="input-field" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} data-testid="svc-request-email" /></div>
                    <div><label className="label-text">WhatsApp / Tel.</label><input className="input-field" value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} data-testid="svc-request-phone" /></div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><label className="label-text flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> Fecha tentativa</label><input type="date" className="input-field" value={form.travel_date} onChange={(e) => setForm((f) => ({ ...f, travel_date: e.target.value }))} data-testid="svc-request-date" /></div>
                    <div><label className="label-text">N° de personas</label><input className="input-field" placeholder="ej. 2 adultos" value={form.pax} onChange={(e) => setForm((f) => ({ ...f, pax: e.target.value }))} data-testid="svc-request-pax" /></div>
                  </div>
                  <div><label className="label-text">Mensaje (opcional)</label><textarea rows="2" className="input-field" value={form.message} onChange={(e) => setForm((f) => ({ ...f, message: e.target.value }))} data-testid="svc-request-message" /></div>
                </div>
                <button className="btn-primary w-full mt-5 justify-center" onClick={submit} disabled={sending} data-testid="svc-request-submit">
                  {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Enviar solicitud
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
