import { useEffect, useState } from 'react';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Area, AreaChart,
} from 'recharts';
import {
  DollarSign, Wallet, TrendingUp, XCircle, Users, UserCog, Package, Sparkles, Download, BarChart3,
} from 'lucide-react';

const PERIODS = [['week', 'Semana'], ['month', 'Mes'], ['quarter', 'Trimestre'], ['year', 'Año']];

export default function SalesStats() {
  const [data, setData] = useState(null);
  const [period, setPeriod] = useState('month');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState(false);

  const ccy = data?.currency || 'MXN';
  const money = (v) => `$${Number(v || 0).toLocaleString('es-MX', { maximumFractionDigits: 0 })} ${ccy}`;

  const load = async (p) => {
    setLoading(true); setError('');
    try { const { data } = await api.get('/stats/sales', { params: { period: p } }); setData(data); }
    catch (e) { setError(formatApiError(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(period); }, [period]);

  const exportXlsx = async () => {
    setExporting(true);
    try {
      const res = await api.get('/stats/sales/export', { params: { period }, responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url; a.download = `routiq-ventas-${period}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) { setError(formatApiError(e)); }
    finally { setExporting(false); }
  };

  const conv = data?.conversion || {};
  const kpis = [
    { icon: DollarSign, label: 'Ingresos (ganadas)', v: money(data?.revenue_total), tone: 'bg-brand-500 text-white' },
    { icon: Wallet, label: 'Cobrado', v: money(data?.collected_total), tone: 'bg-mint-100 text-emerald-700' },
    { icon: TrendingUp, label: 'Conversión', v: `${conv.rate ?? 0}%`, sub: `${conv.won ?? 0}/${conv.total ?? 0} ganadas`, tone: 'bg-brand-50 text-brand-500' },
    { icon: XCircle, label: 'Perdidas', v: conv.lost ?? 0, tone: 'bg-red-100 text-red-600' },
  ];

  return (
    <AppShell>
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl md:text-4xl font-semibold text-ink-900 tracking-tight">Ventas y estadísticas</h1>
          <p className="text-ink-500 mt-1">Ingresos, conversión y rendimiento de tu equipo y catálogo.</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-1 bg-white border border-ink-100 rounded-xl p-1" data-testid="stats-period">
            {PERIODS.map(([k, lbl]) => (
              <button key={k} onClick={() => setPeriod(k)} data-testid={`stats-period-${k}`}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${period === k ? 'bg-brand-50 text-brand-500' : 'text-ink-500 hover:text-ink-700'}`}>{lbl}</button>
            ))}
          </div>
          <button onClick={exportXlsx} disabled={exporting} className="btn-secondary text-sm whitespace-nowrap" data-testid="stats-export-btn">
            <Download className="w-4 h-4" /> {exporting ? 'Generando…' : 'Exportar Excel'}
          </button>
        </div>
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="stats-error">{error}</div>}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6" data-testid="stats-kpis">
        {kpis.map(({ icon: Icon, label, v, sub, tone }) => (
          <div key={label} className="card-surface p-5" data-testid={`stats-kpi-${label}`}>
            <div className={`w-9 h-9 rounded-xl ${tone} flex items-center justify-center`}><Icon className="w-4 h-4" /></div>
            <p className="text-xs uppercase tracking-widest text-ink-400 font-bold mt-3">{label}</p>
            <p className="font-display text-2xl font-bold text-ink-900 mt-1 truncate">{v}</p>
            {sub && <p className="text-xs text-ink-400 mt-0.5">{sub}</p>}
          </div>
        ))}
      </div>

      <div className="card-surface p-5 mb-6" data-testid="stats-trend">
        <p className="text-xs uppercase tracking-widest text-ink-400 font-bold flex items-center gap-1.5 mb-4"><TrendingUp className="w-4 h-4" /> Tendencia de ingresos</p>
        <div style={{ width: '100%', height: 240 }}>
          <ResponsiveContainer>
            <AreaChart data={data?.trend || []} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#185FA5" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#185FA5" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef1f5" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#94a3b8' }} interval="preserveStartEnd" minTickGap={24} />
              <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} width={56} tickFormatter={(v) => v >= 1000 ? `${Math.round(v / 1000)}k` : v} />
              <Tooltip formatter={(v) => money(v)} labelStyle={{ color: '#0f172a' }} contentStyle={{ borderRadius: 12, border: '1px solid #e2e8f0', fontSize: 12 }} />
              <Area type="monotone" dataKey="revenue" stroke="#185FA5" strokeWidth={2.5} fill="url(#revFill)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6 mb-6">
        <RankTable testid="stats-executives" icon={UserCog} title="Ranking de ejecutivos"
          headers={['Ejecutivo', 'Creadas', 'Cerradas', 'Vendido']}
          rows={(data?.executives || []).map((e) => [e.name, e.created, e.won, money(e.revenue)])}
          empty="Aún no hay actividad de ejecutivos en este período." />
        <RankTable testid="stats-clients" icon={Users} title="Ranking de clientes"
          headers={['Cliente', 'Cotiz.', 'Compra']}
          rows={(data?.clients || []).map((c) => [c.name, c.count, money(c.revenue)])}
          empty="Aún no hay clientes con actividad en este período." />
        <RankTable testid="stats-packages" icon={Package} title="Paquetes más vendidos"
          headers={['Paquete', 'Vendidos', 'Ingresos']}
          rows={(data?.packages || []).map((p) => [p.name, p.count, money(p.revenue)])}
          empty="Aún no hay paquetes ganados en este período." />
        <RankTable testid="stats-services" icon={Sparkles} title="Servicios más vendidos"
          headers={['Servicio', 'Vendidos', 'Ingresos']}
          rows={(data?.services || []).map((s) => [s.name, s.count, money(s.revenue)])}
          empty="Aún no hay servicios vendidos en este período." />
      </div>

      <div className="card-surface overflow-hidden" data-testid="stats-lost">
        <div className="px-6 py-4 border-b border-ink-100 flex items-center gap-2">
          <XCircle className="w-5 h-5 text-red-500" />
          <h2 className="font-display font-semibold text-ink-900">Cotizaciones perdidas</h2>
        </div>
        {(data?.lost || []).length === 0 ? (
          <p className="p-8 text-center text-ink-400 text-sm">Sin cotizaciones perdidas en este período. 🎉</p>
        ) : (
          <>
            <div className="hidden md:grid grid-cols-12 px-6 py-3 border-b border-ink-100 text-xs uppercase tracking-widest text-ink-400 font-bold">
              <div className="col-span-2">Folio</div><div className="col-span-3">Cliente</div>
              <div className="col-span-2 text-right">Monto</div><div className="col-span-4">Motivo</div><div className="col-span-1 text-right">Fecha</div>
            </div>
            {(data?.lost || []).map((l, i) => (
              <div key={i} className="grid grid-cols-2 md:grid-cols-12 gap-2 px-6 py-3 border-b border-ink-100 last:border-0 text-sm items-center" data-testid={`stats-lost-row-${l.code}`}>
                <div className="md:col-span-2 font-mono text-brand-500 font-semibold">{l.code}</div>
                <div className="md:col-span-3 text-ink-900">{l.client}</div>
                <div className="md:col-span-2 md:text-right text-ink-700">{money(l.amount)}</div>
                <div className="md:col-span-4 text-ink-500 italic">{l.reason || '—'}</div>
                <div className="md:col-span-1 md:text-right text-ink-400 text-xs">{l.date}</div>
              </div>
            ))}
          </>
        )}
      </div>

      {loading && <div className="text-center text-ink-400 text-sm mt-6">Cargando estadísticas…</div>}
      {!loading && data && conv.total === 0 && (
        <div className="card-surface text-center py-12 mt-6" data-testid="stats-empty">
          <BarChart3 className="w-10 h-10 mx-auto text-ink-300" />
          <p className="text-ink-700 font-semibold mt-3">Aún no hay datos de ventas en este período</p>
          <p className="text-ink-400 text-sm mt-1">Cuando crees y cierres cotizaciones, verás aquí tu rendimiento.</p>
        </div>
      )}
    </AppShell>
  );
}

const RankTable = ({ testid, icon: Icon, title, headers, rows, empty }) => (
  <div className="card-surface overflow-hidden" data-testid={testid}>
    <div className="px-6 py-4 border-b border-ink-100 flex items-center gap-2">
      <Icon className="w-5 h-5 text-brand-500" />
      <h2 className="font-display font-semibold text-ink-900">{title}</h2>
    </div>
    {rows.length === 0 ? (
      <p className="p-8 text-center text-ink-400 text-sm">{empty}</p>
    ) : (
      <div className="divide-y divide-ink-100">
        <div className="hidden md:flex items-center gap-3 px-6 py-2 text-[10px] uppercase tracking-widest text-ink-400 font-bold">
          <div className="flex-1">{headers[0]}</div>
          {headers.slice(1).map((h, j) => (
            <div key={j} className={`text-right ${j === headers.length - 2 ? 'w-28' : 'w-16'}`}>{h}</div>
          ))}
        </div>
        {rows.map((r, i) => (
          <div key={i} className="flex items-center gap-3 px-6 py-3 text-sm">
            <div className="flex-1 flex items-center gap-2 min-w-0">
              <span className={`w-6 h-6 rounded-lg flex items-center justify-center text-xs font-bold shrink-0 ${i === 0 ? 'bg-brand-500 text-white' : 'bg-ink-100 text-ink-500'}`}>{i + 1}</span>
              <span className="text-ink-900 font-medium truncate">{r[0]}</span>
            </div>
            {r.slice(1).map((c, j) => (
              <div key={j} className={`text-right ${j === r.length - 2 ? 'w-28 font-display font-semibold text-ink-900' : 'w-16 text-ink-500'}`}>{c}</div>
            ))}
          </div>
        ))}
      </div>
    )}
  </div>
);
