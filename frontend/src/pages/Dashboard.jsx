import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { TrendingUp, FileText, Target, Wallet, Plus, ArrowUpRight } from 'lucide-react';

const STATE_LABELS = {
  nueva_consulta: 'Nueva consulta',
  cotizando: 'Cotizando',
  enviada: 'Enviada',
  negociacion: 'En negociación',
  ganada: 'Ganada',
  perdida: 'Perdida',
};
const STATE_TONES = {
  nueva_consulta: 'bg-ink-100 text-ink-700',
  cotizando: 'bg-brand-50 text-brand-500',
  enviada: 'bg-blue-100 text-blue-700',
  negociacion: 'bg-peach-100 text-amber-800',
  ganada: 'bg-mint-100 text-emerald-700',
  perdida: 'bg-red-100 text-red-700',
};

function Money({ value, currency = 'MXN' }) {
  const n = Number(value || 0);
  return <>${n.toLocaleString('es-MX', { minimumFractionDigits: 0, maximumFractionDigits: 0 })} <span className="text-ink-400 text-sm">{currency}</span></>;
}

function MetricCard({ icon: Icon, label, value, tone = 'bg-brand-50 text-brand-500', trend, testid }) {
  return (
    <div className="card-surface p-5" data-testid={testid}>
      <div className="flex items-start justify-between">
        <div className={`w-10 h-10 rounded-xl ${tone} flex items-center justify-center`}>
          <Icon className="w-5 h-5" />
        </div>
        {trend && <span className="pill bg-mint-100 text-emerald-700">{trend}</span>}
      </div>
      <p className="text-xs uppercase tracking-widest text-ink-400 font-bold mt-4">{label}</p>
      <p className="font-display text-3xl font-bold text-ink-900 mt-1">{value}</p>
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const [metrics, setMetrics] = useState(null);
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const [m, q] = await Promise.all([
          api.get('/metrics/dashboard'),
          api.get('/quotations'),
        ]);
        setMetrics(m.data);
        setRecent(q.data.slice(0, 6));
      } catch (_e) { /* noop */ }
    })();
  }, []);

  return (
    <AppShell>
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
        <div>
          <p className="pill bg-brand-50 text-brand-500 mb-3" data-testid="welcome-pill">Buen día, {user?.name?.split(' ')[0]} 👋</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold text-ink-900 tracking-tight">Dashboard</h1>
          <p className="text-ink-500 mt-1">Tu operación en una sola vista.</p>
        </div>
        <Link to="/app/quotations/new" className="btn-primary" data-testid="new-quotation-cta">
          <Plus className="w-4 h-4" /> Nueva cotización
        </Link>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard icon={FileText} label="Cotizaciones activas" value={metrics?.quotations_active ?? '—'} testid="metric-active" />
        <MetricCard icon={Target} label="Tasa de conversión" value={metrics ? `${metrics.conversion_rate}%` : '—'} tone="bg-mint-100 text-emerald-700" testid="metric-conversion" />
        <MetricCard icon={Wallet} label="Ingresos ganados" value={metrics ? <Money value={metrics.revenue_won} /> : '—'} tone="bg-peach-100 text-amber-800" testid="metric-revenue" />
        <MetricCard icon={TrendingUp} label="Proyección" value={metrics ? <Money value={metrics.projected_revenue} /> : '—'} tone="bg-brand-500 text-white" testid="metric-projected" />
      </div>

      <div className="mt-10">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display text-xl font-semibold text-ink-900">Cotizaciones recientes</h2>
          <Link to="/app/quotations" className="btn-ghost text-sm" data-testid="see-all-quotations">Ver todas <ArrowUpRight className="w-4 h-4" /></Link>
        </div>
        <div className="card-surface overflow-hidden">
          <div className="hidden md:grid grid-cols-12 px-6 py-3 border-b border-ink-100 text-xs uppercase tracking-widest font-bold text-ink-400">
            <div className="col-span-2">Código</div>
            <div className="col-span-3">Cliente</div>
            <div className="col-span-3">Paquete</div>
            <div className="col-span-2">Estado</div>
            <div className="col-span-2 text-right">Total</div>
          </div>
          {recent.length === 0 && (
            <div className="p-8 text-center text-ink-400" data-testid="empty-quotations">Aún no hay cotizaciones. Crea la primera.</div>
          )}
          {recent.map((q) => (
            <Link key={q.id} to={`/app/quotations/${q.id}`}
              data-testid={`recent-quotation-${q.code}`}
              className="grid grid-cols-12 gap-2 px-6 py-4 border-b border-ink-100 last:border-0 hover:bg-brand-50/40 transition-colors">
              <div className="col-span-12 md:col-span-2 font-mono text-sm text-brand-500 font-semibold">{q.code}</div>
              <div className="col-span-6 md:col-span-3 text-sm text-ink-900 font-medium">{q.client_snapshot?.name}</div>
              <div className="col-span-6 md:col-span-3 text-sm text-ink-500 truncate">{q.package_snapshot?.name}</div>
              <div className="col-span-6 md:col-span-2"><span className={`pill ${STATE_TONES[q.state]}`}>{STATE_LABELS[q.state]}</span></div>
              <div className="col-span-6 md:col-span-2 md:text-right font-display font-semibold text-ink-900"><Money value={q.total} currency={q.currency || 'MXN'} /></div>
            </Link>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
