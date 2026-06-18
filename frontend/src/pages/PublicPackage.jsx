import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api, { formatApiError } from '@/lib/api';
import { formatDateEs } from '@/lib/dates';
import {
  Moon, MapPin, Check, X, Hotel, Calendar, Sparkles, Loader2,
  CheckCircle2, Phone, Mail, Send, Printer,
} from 'lucide-react';

function money(v, c = 'MXN') { return v == null ? '' : `$${Number(v).toLocaleString('es-MX')} ${c}`; }

export default function PublicPackage() {
  const { slug, code } = useParams();
  const backend = process.env.REACT_APP_BACKEND_URL || '';
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', phone: '', travel_date: '', pax: '', message: '', company_website: '' });
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => {
    (async () => {
      try { const { data } = await api.get(`/public/package/${slug}/${code}`); setData(data); }
      catch (e) { setError(formatApiError(e)); }
    })();
  }, [slug, code]);

  const submit = async () => {
    setFormError('');
    if (!form.name.trim()) { setFormError('Escribe tu nombre.'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) { setFormError('Escribe un correo válido.'); return; }
    setSending(true);
    try {
      await api.post(`/public/package/${slug}/${code}/request`, form);
      setSent(true);
    } catch (e) { setFormError(formatApiError(e)); }
    finally { setSending(false); }
  };

  if (error) return (
    <div className="min-h-screen flex items-center justify-center bg-cream p-6">
      <div className="text-center" data-testid="pkg-public-error">
        <p className="text-2xl font-display font-semibold text-ink-900">Paquete no disponible</p>
        <p className="text-ink-500 mt-2">{error}</p>
      </div>
    </div>
  );
  if (!data) return <div className="min-h-screen flex items-center justify-center bg-cream"><Loader2 className="w-8 h-8 animate-spin text-ink-300" /></div>;

  const { package: p, company } = data;
  const brand = company.primary_color || '#185FA5';
  const logo = company.logo_url ? (company.logo_url.startsWith('http') ? company.logo_url : `${backend}${company.logo_url}`) : null;
  const heroImg = p.image_url ? (p.image_url.startsWith('http') ? p.image_url : `${backend}${p.image_url}`) : null;

  return (
    <div className="min-h-screen bg-cream print:bg-white" data-testid="public-package-page">
      {/* Encabezado solo para impresión */}
      <div className="hidden print:block px-2 pt-2 mb-4">
        {logo && <img src={logo} alt={company.name} className="h-16 object-contain mb-2" />}
        <p className="font-bold text-lg text-ink-900">{company.name}</p>
        <p className="text-sm text-ink-600">{[company.contact_phone, company.contact_email].filter(Boolean).join(' · ')}</p>
        {company.address && <p className="text-sm text-ink-600">{company.address}</p>}
        <h1 className="text-2xl font-bold text-ink-900 mt-3">{p.name}</h1>
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
          {heroImg ? <img src={heroImg} alt={p.name} className="absolute inset-0 w-full h-full object-cover object-center" data-testid="pkg-hero-image" />
            : <div className="absolute inset-0" style={{ background: `linear-gradient(135deg, ${brand}, #0f2f52)` }} />}
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
        </div>
        <div className="max-w-5xl mx-auto px-5">
          <div className="-mt-20 relative bg-white rounded-2xl shadow-xl p-6 sm:p-8">
            <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
              <div>
                <span className="pill text-xs font-mono" style={{ background: `${brand}1a`, color: brand }}>{p.code}</span>
                <h1 className="font-display text-3xl sm:text-4xl font-bold text-ink-900 mt-2 tracking-tight" data-testid="pkg-title">{p.name}</h1>
                <div className="flex items-center gap-4 mt-2 text-sm text-ink-500">
                  {p.nights ? <span className="flex items-center gap-1"><Moon className="w-4 h-4" /> {p.nights} noches</span> : null}
                  {p.hotels?.length ? <span className="flex items-center gap-1"><Hotel className="w-4 h-4" /> {p.hotels.length} hotel(es)</span> : null}
                </div>
              </div>
              <div className="text-left sm:text-right print:hidden">
                {p.base_price != null && (
                  <>
                    <p className="text-xs text-ink-400">Desde</p>
                    <p className="font-display text-3xl font-bold" style={{ color: brand }} data-testid="pkg-price">{money(p.base_price, p.currency)}<span className="text-sm text-ink-400"> / pax</span></p>
                  </>
                )}
                <div className="mt-3 flex flex-wrap gap-2 sm:justify-end">
                  <button onClick={() => window.print()} className="inline-flex items-center gap-2 rounded-full px-5 py-3 font-semibold border border-ink-200 text-ink-700 hover:bg-ink-50 transition" data-testid="print-package-btn">
                    <Printer className="w-4 h-4" /> Imprimir
                  </button>
                  <button onClick={() => { setShowForm(true); setSent(false); }} className="inline-flex items-center gap-2 rounded-full px-6 py-3 text-white font-semibold shadow-lg hover:brightness-110 transition" style={{ background: brand }} data-testid="want-package-btn">
                    <Sparkles className="w-4 h-4" /> Quiero este paquete
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <main className="max-w-5xl mx-auto px-5 py-10 grid lg:grid-cols-3 gap-8 print:block print:py-0 print:px-2">
        <div className="lg:col-span-2 space-y-8">
          {p.description && (
            <section data-testid="pkg-description">
              <h2 className="font-display text-xl font-semibold text-ink-900 mb-2">Sobre este viaje</h2>
              <p className="text-ink-600 leading-relaxed whitespace-pre-wrap">{p.description}</p>
            </section>
          )}

          {p.itinerary?.length > 0 && (
            <section data-testid="pkg-itinerary">
              <h2 className="font-display text-xl font-semibold text-ink-900 mb-4 flex items-center gap-2"><MapPin className="w-5 h-5" style={{ color: brand }} /> Itinerario</h2>
              <ol className="relative border-l-2 border-ink-100 ml-2 space-y-6">
                {p.itinerary.map((d, i) => (
                  <li key={i} className="ml-6">
                    <span className="absolute -left-[11px] flex items-center justify-center w-5 h-5 rounded-full text-white text-[10px] font-bold" style={{ background: brand }}>{d.day || i + 1}</span>
                    <h3 className="font-semibold text-ink-900">{d.title || `Día ${d.day || i + 1}`}</h3>
                    {d.description && <p className="text-sm text-ink-500 mt-1 whitespace-pre-wrap">{d.description}</p>}
                  </li>
                ))}
              </ol>
            </section>
          )}

          {(p.includes?.length > 0 || p.excludes?.length > 0) && (
            <section className="grid sm:grid-cols-2 gap-6">
              {p.includes?.length > 0 && (
                <div data-testid="pkg-includes">
                  <h2 className="font-display text-lg font-semibold text-ink-900 mb-3">Incluye</h2>
                  <ul className="space-y-2">
                    {p.includes.map((x, i) => <li key={i} className="flex gap-2 text-sm text-ink-600"><Check className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" /> {x}</li>)}
                  </ul>
                </div>
              )}
              {p.excludes?.length > 0 && (
                <div data-testid="pkg-excludes">
                  <h2 className="font-display text-lg font-semibold text-ink-900 mb-3">No incluye</h2>
                  <ul className="space-y-2">
                    {p.excludes.map((x, i) => <li key={i} className="flex gap-2 text-sm text-ink-400"><X className="w-4 h-4 text-ink-300 shrink-0 mt-0.5" /> {x}</li>)}
                  </ul>
                </div>
              )}
            </section>
          )}
        </div>

        {/* Side CTA */}
        <aside className="lg:sticky lg:top-20 h-fit print:hidden">
          <div className="bg-white rounded-2xl shadow-sm border border-ink-100 p-6">
            {p.hotels?.length > 0 && (
              <>
                <h3 className="font-semibold text-ink-900 mb-2 flex items-center gap-2"><Hotel className="w-4 h-4" style={{ color: brand }} /> Hoteles</h3>
                <ul className="space-y-1 mb-4">
                  {p.hotels.map((h, i) => <li key={i} className="text-sm text-ink-600">{h.name}{h.category ? <span className="text-ink-400"> · {h.category}</span> : ''}</li>)}
                </ul>
                <hr className="border-ink-100 mb-4" />
              </>
            )}
            <p className="text-sm text-ink-500">¿Te interesa? Cuéntanos tus fechas y te armamos una cotización personalizada.</p>
            <button onClick={() => { setShowForm(true); setSent(false); }} className="mt-4 w-full inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-white font-semibold shadow hover:brightness-110 transition" style={{ background: brand }} data-testid="want-package-btn-side">
              <Sparkles className="w-4 h-4" /> Quiero este paquete
            </button>
          </div>
        </aside>
      </main>

      <footer className="border-t border-ink-100 py-6 text-center text-xs text-ink-400 print:hidden">
        {company.name} · Cotización generada con Routiq
      </footer>

      {/* Request form modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50 print:hidden" onClick={() => !sending && setShowForm(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="package-request-modal">
            {sent ? (
              <div className="text-center py-6" data-testid="request-success">
                <CheckCircle2 className="w-14 h-14 mx-auto text-emerald-500 mb-3" />
                <h3 className="font-display text-xl font-semibold text-ink-900">¡Solicitud enviada!</h3>
                <p className="text-ink-500 mt-2">Un asesor de {company.name} te contactará muy pronto con tu cotización personalizada.</p>
                <button className="btn-primary mt-5" onClick={() => setShowForm(false)} data-testid="request-success-close">Cerrar</button>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between mb-1">
                  <h3 className="font-display text-xl font-semibold text-ink-900">Solicitar cotización</h3>
                  <button onClick={() => setShowForm(false)} className="text-ink-400 hover:text-ink-700"><X className="w-5 h-5" /></button>
                </div>
                <p className="text-sm text-ink-500 mb-4">{p.name}</p>
                {formError && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-3 py-2 text-sm mb-3" data-testid="request-error">{formError}</div>}
                <div className="space-y-3">
                  <input className="hidden" tabIndex="-1" autoComplete="off" value={form.company_website} onChange={(e) => setForm((f) => ({ ...f, company_website: e.target.value }))} />
                  <div><label className="label-text">Nombre completo *</label><input className="input-field" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} data-testid="request-name" /></div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><label className="label-text">Correo *</label><input type="email" className="input-field" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} data-testid="request-email" /></div>
                    <div><label className="label-text">WhatsApp / Tel.</label><input className="input-field" value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} data-testid="request-phone" /></div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><label className="label-text flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> Fecha tentativa</label><input type="date" className="input-field" value={form.travel_date} onChange={(e) => setForm((f) => ({ ...f, travel_date: e.target.value }))} data-testid="request-date" /></div>
                    <div><label className="label-text">N° de personas</label><input className="input-field" placeholder="ej. 2 adultos" value={form.pax} onChange={(e) => setForm((f) => ({ ...f, pax: e.target.value }))} data-testid="request-pax" /></div>
                  </div>
                  <div><label className="label-text">Mensaje (opcional)</label><textarea rows="2" className="input-field" value={form.message} onChange={(e) => setForm((f) => ({ ...f, message: e.target.value }))} data-testid="request-message" /></div>
                </div>
                <button className="btn-primary w-full mt-5 justify-center" onClick={submit} disabled={sending} data-testid="request-submit">
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
