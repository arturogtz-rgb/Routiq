import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { Eye, Inbox, FileText, TrendingUp, BarChart3, Share2 } from 'lucide-react';

export default function CatalogAnalytics() {
  const [data, setData] = useState(null);
  const [period, setPeriod] = useState('month'); // week | month
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async (p) => {
    setLoading(true); setError('');
    try {
      const { data } = await api.get('/catalog/analytics', { params: { period: p } });
      setData(data);
    } catch (e) { setError(formatApiError(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(period); }, [period]);

  const t = data?.totals || {};
  const rows = data?.packages || [];
  const hasViews = rows.some((r) => r.views > 0);

  return (
    <AppShell>
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl md:text-4xl font-semibold text-ink-900 tracking-tight">Analítica de catálogo</h1>
          <p className="text-ink-500 mt-1">Vistas, solicitudes y conversión de cada paquete publicado. Las cotizaciones cuentan las creadas desde una solicitud del catálogo.</p>
        </div>
        <div className="flex gap-1 bg-white border border-ink-100 rounded-xl p-1" data-testid="analytics-period">
          {[['week', 'Última semana'], ['month', 'Último mes']].map(([k, lbl]) => (
            <button key={k} onClick={() => setPeriod(k)} data-testid={`analytics-period-${k}`}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${period === k ? 'bg-brand-50 text-brand-500' : 'text-ink-500 hover:text-ink-700'}`}>{lbl}</button>
          ))}
        </div>
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="analytics-error">{error}</div>}

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6" data-testid="analytics-totals">
        {[
          { icon: Eye, label: 'Vistas', v: t.views ?? 0, tone: 'bg-brand-50 text-brand-500' },
          { icon: Inbox, label: 'Solicitudes', v: t.leads ?? 0, tone: 'bg-peach-100 text-amber-700' },
          { icon: FileText, label: 'Cotizaciones', v: t.quotations ?? 0, tone: 'bg-mint-100 text-emerald-700' },
          { icon: TrendingUp, label: 'Vista → Solicitud', v: `${t.view_to_lead ?? 0}%`, tone: 'bg-brand-500 text-white' },
          { icon: TrendingUp, label: 'Solicitud → Cotización', v: `${t.lead_to_quote ?? 0}%`, tone: 'bg-ink-900 text-white' },
        ].map(({ icon: Icon, label, v, tone }) => (
          <div key={label} className="card-surface p-5" data-testid={`analytics-stat-${label}`}>
            <div className={`w-9 h-9 rounded-xl ${tone} flex items-center justify-center`}><Icon className="w-4 h-4" /></div>
            <p className="text-xs uppercase tracking-widest text-ink-400 font-bold mt-3">{label}</p>
            <p className="font-display text-2xl md:text-3xl font-bold text-ink-900 mt-1">{v}</p>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="card-surface p-12 text-center text-ink-400">Cargando analítica…</div>
      ) : rows.length === 0 ? (
        <div className="card-surface text-center py-16" data-testid="analytics-empty">
          <BarChart3 className="w-10 h-10 mx-auto text-ink-300" />
          <p className="text-ink-700 font-semibold mt-3">Aún no tienes paquetes publicados</p>
          <p className="text-ink-400 text-sm mt-1">Publica paquetes en tu catálogo para empezar a medir su rendimiento.</p>
          <Link to="/app/packages" className="btn-secondary text-sm mt-4 inline-flex"><FileText className="w-4 h-4" /> Ir a Paquetes</Link>
        </div>
      ) : (
        <div className="card-surface overflow-hidden" data-testid="analytics-table">
          <div className="hidden md:grid grid-cols-12 px-6 py-3 border-b border-ink-100 text-xs uppercase tracking-widest text-ink-400 font-bold">
            <div className="col-span-5">Paquete</div>
            <div className="col-span-2 text-right">Vistas</div>
            <div className="col-span-2 text-right">Solicitudes</div>
            <div className="col-span-1 text-right">Cotiz.</div>
            <div className="col-span-2 text-right">Conversión</div>
          </div>
          {rows.map((r) => (
            <div key={r.package_id} className="grid grid-cols-2 md:grid-cols-12 gap-2 px-6 py-4 border-b border-ink-100 last:border-0 items-center" data-testid={`analytics-row-${r.code}`}>
              <div className="col-span-2 md:col-span-5">
                <p className="font-semibold text-ink-900 truncate">{r.name}</p>
                <p className="text-xs text-ink-400 font-mono">{r.code}</p>
              </div>
              <div className="md:col-span-2 text-right"><span className="md:hidden text-ink-400 text-xs mr-1">Vistas</span><span className="font-semibold text-ink-900 inline-flex items-center gap-1 justify-end"><Eye className="w-3.5 h-3.5 text-ink-300" />{r.views}</span></div>
              <div className="md:col-span-2 text-right"><span className="md:hidden text-ink-400 text-xs mr-1">Solic.</span><span className="font-semibold text-ink-900">{r.leads}</span></div>
              <div className="md:col-span-1 text-right"><span className="md:hidden text-ink-400 text-xs mr-1">Cotiz.</span><span className="font-semibold text-ink-900">{r.quotations}</span></div>
              <div className="col-span-2 md:col-span-2 text-right">
                <span className={`pill ${r.view_to_quote > 0 ? 'bg-mint-100 text-emerald-700' : 'bg-ink-100 text-ink-400'}`} title="Vista → Cotización">{r.view_to_quote}%</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && rows.length > 0 && !hasViews && (
        <p className="text-xs text-ink-400 mt-4 flex items-center gap-1.5" data-testid="analytics-hint">
          <Share2 className="w-3.5 h-3.5" /> Comparte tu catálogo público (botón "Compartir catálogo" en Paquetes) para empezar a registrar vistas.
        </p>
      )}
    </AppShell>
  );
}
