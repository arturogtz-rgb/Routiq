import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import api, { formatApiError } from '@/lib/api';
import { Moon, MapPin, Phone, Mail, Loader2, ArrowRight, Package as PackageIcon } from 'lucide-react';

function money(v, c = 'MXN') { return v == null ? '' : `$${Number(v).toLocaleString('es-MX')} ${c}`; }

export default function PublicCatalog() {
  const { slug } = useParams();
  const backend = process.env.REACT_APP_BACKEND_URL || '';
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try { const { data } = await api.get(`/public/company/${slug}`); setData(data); }
      catch (e) { setError(formatApiError(e)); }
    })();
  }, [slug]);

  if (error) return (
    <div className="min-h-screen flex items-center justify-center bg-cream p-6">
      <div className="text-center" data-testid="catalog-error">
        <p className="text-2xl font-display font-semibold text-ink-900">Catálogo no disponible</p>
        <p className="text-ink-500 mt-2">{error}</p>
      </div>
    </div>
  );
  if (!data) return <div className="min-h-screen flex items-center justify-center bg-cream"><Loader2 className="w-8 h-8 animate-spin text-ink-300" /></div>;

  const { company, packages } = data;
  const brand = company.primary_color || '#185FA5';
  const logo = company.logo_url ? (company.logo_url.startsWith('http') ? company.logo_url : `${backend}${company.logo_url}`) : null;

  return (
    <div className="min-h-screen bg-cream" data-testid="public-catalog-page">
      <header className="bg-white border-b border-ink-100">
        <div className="max-w-6xl mx-auto px-5 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {logo ? <img src={logo} alt={company.name} className="h-10 max-w-[180px] object-contain" />
              : <span className="font-display font-bold text-lg text-ink-900">{company.name}</span>}
          </div>
          <div className="hidden sm:flex items-center gap-4 text-sm text-ink-500">
            {company.contact_phone && <span className="flex items-center gap-1"><Phone className="w-3.5 h-3.5" /> {company.contact_phone}</span>}
            {company.contact_email && <span className="flex items-center gap-1"><Mail className="w-3.5 h-3.5" /> {company.contact_email}</span>}
          </div>
        </div>
      </header>

      <div className="text-white" style={{ background: `linear-gradient(135deg, ${brand}, #0f2f52)` }}>
        <div className="max-w-6xl mx-auto px-5 py-14">
          <h1 className="font-display text-4xl sm:text-5xl font-bold tracking-tight">{company.name}</h1>
          <p className="text-white/85 mt-3 max-w-2xl">Explora nuestros paquetes y solicita tu cotización personalizada en segundos.</p>
        </div>
      </div>

      <main className="max-w-6xl mx-auto px-5 py-10">
        {packages.length === 0 ? (
          <div className="text-center py-20 text-ink-400" data-testid="catalog-empty">
            <PackageIcon className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>Pronto publicaremos nuestros paquetes aquí.</p>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {packages.map((p) => {
              const img = p.image_url ? (p.image_url.startsWith('http') ? p.image_url : `${backend}${p.image_url}`) : null;
              return (
                <Link key={p.code} to={`/p/${slug}/${p.code}`} className="group bg-white rounded-2xl shadow-sm border border-ink-100 overflow-hidden hover:shadow-lg transition-shadow" data-testid={`catalog-card-${p.code}`}>
                  <div className="h-44 bg-ink-200 overflow-hidden">
                    {img ? <img src={img} alt={p.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                      : <div className="w-full h-full" style={{ background: `linear-gradient(135deg, ${brand}, #0f2f52)` }} />}
                  </div>
                  <div className="p-5">
                    <h3 className="font-display font-semibold text-lg text-ink-900 leading-tight">{p.name}</h3>
                    <div className="flex items-center gap-3 mt-2 text-sm text-ink-500">
                      {p.nights ? <span className="flex items-center gap-1"><Moon className="w-4 h-4" /> {p.nights} noches</span> : null}
                      {p.hotels_count ? <span className="flex items-center gap-1"><MapPin className="w-4 h-4" /> {p.hotels_count} hotel(es)</span> : null}
                    </div>
                    <p className="text-sm text-ink-500 mt-2 line-clamp-2">{p.description}</p>
                    <div className="mt-4 flex items-center justify-between">
                      <div>
                        {p.base_price != null && <><span className="text-xs text-ink-400">Desde </span><span className="font-display text-xl font-bold" style={{ color: brand }}>{money(p.base_price, p.currency)}</span></>}
                      </div>
                      <span className="inline-flex items-center gap-1 text-sm font-semibold" style={{ color: brand }}>Ver <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" /></span>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </main>

      <footer className="border-t border-ink-100 py-6 text-center text-xs text-ink-400">{company.name} · Catálogo con Routiq</footer>
    </div>
  );
}
