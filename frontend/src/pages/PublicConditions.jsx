import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import api, { formatApiError } from '@/lib/api';
import { Phone, Mail, Loader2, ArrowLeft, FileText, ShieldCheck } from 'lucide-react';

export default function PublicConditions() {
  const { slug } = useParams();
  const backend = process.env.REACT_APP_BACKEND_URL || '';
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try { const { data } = await api.get(`/public/company/${slug}/conditions`); setData(data); }
      catch (e) { setError(formatApiError(e)); }
    })();
  }, [slug]);

  if (error) return (
    <div className="min-h-screen flex items-center justify-center bg-cream p-6">
      <div className="text-center" data-testid="conditions-error">
        <p className="text-2xl font-display font-semibold text-ink-900">Condiciones no disponibles</p>
        <p className="text-ink-500 mt-2">{error}</p>
      </div>
    </div>
  );
  if (!data) return <div className="min-h-screen flex items-center justify-center bg-cream"><Loader2 className="w-8 h-8 animate-spin text-ink-300" /></div>;

  const { company, general_conditions, cancellation_policy } = data;
  const brand = company.primary_color || '#185FA5';
  const logo = company.logo_url ? (company.logo_url.startsWith('http') ? company.logo_url : `${backend}${company.logo_url}`) : null;
  const empty = !general_conditions && !cancellation_policy;

  return (
    <div className="min-h-screen bg-cream" data-testid="public-conditions-page">
      <header className="bg-white border-b border-ink-100">
        <div className="max-w-4xl mx-auto px-5 py-4 flex items-center justify-between">
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
        <div className="max-w-4xl mx-auto px-5 py-12 text-center">
          <Link to={`/c/${slug}`} className="inline-flex items-center gap-1 text-white/80 hover:text-white text-sm mb-4" data-testid="back-to-catalog">
            <ArrowLeft className="w-4 h-4" /> Volver al catálogo
          </Link>
          <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight">Condiciones generales y políticas de cancelación</h1>
        </div>
      </div>

      <main className="max-w-4xl mx-auto px-5 py-10 space-y-8">
        {empty && (
          <div className="text-center py-20 text-ink-400" data-testid="conditions-empty">
            <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>Esta empresa aún no ha publicado sus condiciones.</p>
          </div>
        )}
        {general_conditions && (
          <section className="bg-white rounded-2xl shadow-sm border border-ink-100 p-6 sm:p-8" data-testid="conditions-general">
            <h2 className="font-display text-2xl font-semibold text-ink-900 flex items-center gap-2 mb-4">
              <ShieldCheck className="w-6 h-6" style={{ color: brand }} /> Condiciones generales
            </h2>
            <div className="prose prose-sm max-w-none text-ink-700" dangerouslySetInnerHTML={{ __html: general_conditions }} />
          </section>
        )}
        {cancellation_policy && (
          <section className="bg-white rounded-2xl shadow-sm border border-ink-100 p-6 sm:p-8" data-testid="conditions-cancellation">
            <h2 className="font-display text-2xl font-semibold text-ink-900 flex items-center gap-2 mb-4">
              <FileText className="w-6 h-6" style={{ color: brand }} /> Políticas de cancelación
            </h2>
            <div className="prose prose-sm max-w-none text-ink-700" dangerouslySetInnerHTML={{ __html: cancellation_policy }} />
          </section>
        )}
      </main>

      <footer className="border-t border-ink-100 py-6 text-center text-xs text-ink-400">{company.name} · Catálogo con Routiq</footer>
    </div>
  );
}
