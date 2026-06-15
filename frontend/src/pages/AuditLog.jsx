import { useEffect, useState } from 'react';
import AppShell from '@/components/AppShell';
import api from '@/lib/api';
import { formatDateEs } from '@/lib/dates';
import { ShieldCheck, Trophy, Archive, Trash2, RotateCcw, Filter, TrendingUp, Wallet, Crown } from 'lucide-react';

const ACTION_META = {
  won: { label: 'Ganada', icon: Trophy, tone: 'bg-mint-100 text-emerald-700' },
  archived: { label: 'Archivada', icon: Archive, tone: 'bg-ink-100 text-ink-600' },
  restored: { label: 'Restaurada', icon: RotateCcw, tone: 'bg-brand-50 text-brand-500' },
  deleted: { label: 'Eliminada', icon: Trash2, tone: 'bg-red-100 text-red-700' },
};

function money(v, c = 'MXN') { return `$${Number(v || 0).toLocaleString('es-MX')} ${c}`; }

export default function AuditLog() {
  const [items, setItems] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [action, setAction] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [a, m] = await Promise.all([
        api.get('/audit-log', { params: action ? { action } : {} }),
        api.get('/metrics/audit'),
      ]);
      setItems(a.data);
      setMetrics(m.data);
    } catch (_e) { /* noop */ }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [action]); // eslint-disable-line

  return (
    <AppShell>
      <div className="mb-6">
        <p className="pill bg-brand-50 text-brand-500 mb-3"><ShieldCheck className="w-3.5 h-3.5" /> Panel Admin</p>
        <h1 className="font-display text-3xl md:text-4xl font-semibold text-ink-900 tracking-tight">Auditoría</h1>
        <p className="text-ink-500 mt-1">Registro de cotizaciones ganadas, archivadas, restauradas y eliminadas. Quién y cuándo.</p>
      </div>

      {/* Mini-dashboard */}
      {metrics && (
        <div className="grid sm:grid-cols-3 gap-4 mb-6" data-testid="audit-metrics">
          <div className="card-surface p-5" data-testid="metric-won-month">
            <div className="flex items-center gap-2 text-ink-400 text-xs uppercase tracking-widest font-bold"><TrendingUp className="w-4 h-4" /> Ganadas del mes</div>
            <p className="font-display text-4xl font-bold text-ink-900 mt-2">{metrics.won_this_month}</p>
            <p className="text-xs text-ink-400 mt-1">{metrics.won_total} ganadas en total</p>
          </div>
          <div className="card-surface p-5" data-testid="metric-recovered">
            <div className="flex items-center gap-2 text-ink-400 text-xs uppercase tracking-widest font-bold"><Wallet className="w-4 h-4" /> Monto recuperado</div>
            <p className="font-display text-3xl font-bold text-emerald-700 mt-2">{money(metrics.amount_recovered, metrics.currency)}</p>
            <p className="text-xs text-ink-400 mt-1">Pagos registrados (Stripe + transferencia)</p>
          </div>
          <div className="card-surface p-5" data-testid="metric-top-exec">
            <div className="flex items-center gap-2 text-ink-400 text-xs uppercase tracking-widest font-bold"><Crown className="w-4 h-4" /> Ejecutivo top</div>
            {metrics.top_executive ? (
              <>
                <p className="font-display text-2xl font-bold text-ink-900 mt-2">{metrics.top_executive.name}</p>
                <p className="text-xs text-ink-400 mt-1">{metrics.top_executive.won} cotizaciones ganadas</p>
              </>
            ) : <p className="text-ink-400 mt-2 text-sm">Sin datos aún</p>}
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 mb-5">
        <Filter className="w-4 h-4 text-ink-400" />
        <select value={action} onChange={(e) => setAction(e.target.value)} className="input-field sm:w-56" data-testid="audit-filter">
          <option value="">Todas las acciones</option>
          <option value="won">Ganadas</option>
          <option value="archived">Archivadas</option>
          <option value="restored">Restauradas</option>
          <option value="deleted">Eliminadas</option>
        </select>
      </div>

      <div className="card-surface overflow-hidden" data-testid="audit-table">
        <div className="hidden md:grid grid-cols-12 px-6 py-3 border-b border-ink-100 text-xs uppercase tracking-widest font-bold text-ink-400">
          <div className="col-span-2">Acción</div><div className="col-span-2">Folio</div>
          <div className="col-span-3">Cliente</div><div className="col-span-2">Ejecutivo</div>
          <div className="col-span-1 text-right">Total</div><div className="col-span-2 text-right">Fecha</div>
        </div>
        {items.map((a) => {
          const meta = ACTION_META[a.action] || { label: a.action, icon: ShieldCheck, tone: 'bg-ink-100 text-ink-600' };
          const Icon = meta.icon;
          return (
            <div key={a.id} className="grid grid-cols-12 gap-2 px-6 py-4 border-b border-ink-100 last:border-0" data-testid={`audit-row-${a.quotation_code}`}>
              <div className="col-span-6 md:col-span-2"><span className={`pill ${meta.tone}`}><Icon className="w-3.5 h-3.5" /> {meta.label}</span></div>
              <div className="col-span-6 md:col-span-2 font-mono text-sm text-brand-500 font-semibold">{a.quotation_code}</div>
              <div className="col-span-6 md:col-span-3 text-sm text-ink-900">{a.client_name || '—'}</div>
              <div className="col-span-6 md:col-span-2 text-sm text-ink-500">{a.executive_name || 'Sistema'}</div>
              <div className="col-span-6 md:col-span-1 md:text-right text-sm font-semibold text-ink-900">{money(a.total, a.currency)}</div>
              <div className="col-span-6 md:col-span-2 md:text-right text-xs text-ink-400">{formatDateEs(a.at)}</div>
            </div>
          );
        })}
        {!loading && items.length === 0 && <p className="p-8 text-center text-ink-400" data-testid="audit-empty">Sin registros de auditoría todavía.</p>}
        {loading && <p className="p-8 text-center text-ink-400">Cargando…</p>}
      </div>
    </AppShell>
  );
}
