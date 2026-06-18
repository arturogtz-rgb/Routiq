import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import api, { formatApiError } from '@/lib/api';
import { Phone, Mail, Loader2, ArrowLeft, Map, Bus, Ticket, Sparkles } from 'lucide-react';

const UNIT_ES = { per_person: 'por persona', per_group: 'por grupo', per_day: 'por día', per_access: 'por acceso' };
const CAT_ICON = { tour: Map, traslado: Bus, acceso: Ticket, extra: Sparkles };

function money(v, c = 'MXN') { return v == null ? '' : `$${Number(v).toLocaleString('es-MX')} ${c}`; }

export default function PublicServices() {
  const { slug } = useParams();
  const backend = process.env.REACT_APP_BACKEND_URL || '';
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try { const { data } = await api.get(`/public/company/${slug}/services`); setData(data); }
      catch (e) { setError(formatApiError(e)); }
    })();
  }, [slug]);

  if (error) return (
    <div className="min-h-screen flex items-center justify-center bg-cream p-6">
      <div className="text-center" data-testid="services-error">
        <p className="text-2xl font-display font-semibold text-ink-900">Servicios no disponibles</p>
        <p className="text-ink-500 mt-2">{error}</p>
      </div>
    </div>
  );
  if (!data) return <div className="min-h-screen flex items-center justify-center bg-cream"><Loader2 className="w-8 h-8 animate-spin text-ink-300" /></div>;

  const { company, groups } = data;
  const brand = company.primary_color || '#185FA5';
  const logo = company.logo_url ? (company.logo_url.startsWith('http') ? company.logo_url : `${backend}${company.logo_url}`) : null;

  return (
    <div className="min-h-screen bg-cream" data-testid="public-services-page">
      <header className="bg-white border-b border-ink-100">
        <div className="max-w-6xl mx-auto px-5 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {logo ? <img src={logo} alt={company.name} className="h-12 max-w-[220px] object-contain" />
              : <span className="font-display font-bold text-xl text-ink-900">{company.name}</span>}
          </div>
          <div className="hidden sm:flex items-center gap-4 text-sm text-ink-500">
            {company.contact_phone && <span className="flex items-center gap-1"><Phone className="w-3.5 h-3.5" /> {company.contact_phone}</span>}
            {company.contact_email && <span className="flex items-center gap-1"><Mail className="w-3.5 h-3.5" /> {company.contact_email}</span>}
          </div>
        </div>
      </header>

      <div className="text-white" style={{ background: `linear-gradient(135deg, ${brand}, #0f2f52)` }}>
        <div className="max-w-6xl mx-auto px-5 py-14 text-center">
          <Link to={`/c/${slug}`} className="inline-flex items-center gap-1 text-white/80 hover:text-white text-sm mb-4" data-testid="back-to-catalog">
            <ArrowLeft className="w-4 h-4" /> Volver al catálogo
          </Link>
          <h1 className="font-display text-4xl sm:text-5xl font-bold tracking-tight">Servicios</h1>
          <p className="text-white/85 mt-3 max-w-2xl mx-auto">Tours, traslados, accesos y extras disponibles.</p>
        </div>
      </div>

      <main className="max-w-6xl mx-auto px-5 py-10 space-y-12">
        {groups.length === 0 ? (
          <div className="text-center py-20 text-ink-400" data-testid="services-empty">
            <Map className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>Pronto publicaremos nuestros servicios aquí.</p>
          </div>
        ) : groups.map((g) => {
          const Icon = CAT_ICON[g.key] || Sparkles;
          return (
            <section key={g.key} data-testid={`services-group-${g.key}`}>
              <h2 className="font-display text-2xl font-semibold text-ink-900 flex items-center gap-2 mb-5">
                <Icon className="w-6 h-6" style={{ color: brand }} /> {g.label}
              </h2>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
                {g.items.map((s, i) => {
                  const img = s.image_url ? (s.image_url.startsWith('http') ? s.image_url : `${backend}${s.image_url}`) : null;
                  return (
                    <div key={i} className="bg-white rounded-2xl shadow-sm border border-ink-100 overflow-hidden" data-testid={`service-pub-card-${g.key}-${i}`}>
                      {img && <div className="h-40 bg-ink-200 overflow-hidden"><img src={img} alt={s.name} className="w-full h-full object-cover" onError={(e) => { e.currentTarget.parentElement.style.display = 'none'; }} /></div>}
                      <div className="p-5">
                        <h3 className="font-display font-semibold text-lg text-ink-900 leading-tight">{s.name}</h3>
                        {s.description && <p className="text-sm text-ink-500 mt-2 line-clamp-3">{s.description}</p>}
                        <div className="mt-4 flex items-end justify-between">
                          <span className="font-display text-xl font-bold" style={{ color: brand }}>{money(s.public_price, s.currency)}</span>
                          <span className="text-xs text-ink-400">{UNIT_ES[s.unit] || ''}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}
      </main>

      <footer className="border-t border-ink-100 py-6 text-center text-xs text-ink-400">
        {company.name} · <Link to={`/c/${slug}/condiciones`} className="hover:underline" data-testid="footer-conditions-link">Condiciones generales</Link> · Catálogo con Routiq
      </footer>
    </div>
  );
}
