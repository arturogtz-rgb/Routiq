import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api from '@/lib/api';
import { Plus, Search } from 'lucide-react';

const STATE_LABELS = {
  nueva_consulta: 'Nueva consulta', cotizando: 'Cotizando', enviada: 'Enviada',
  negociacion: 'En negociación', ganada: 'Ganada', perdida: 'Perdida',
};
const STATE_TONES = {
  nueva_consulta: 'bg-ink-100 text-ink-700', cotizando: 'bg-brand-50 text-brand-500',
  enviada: 'bg-blue-100 text-blue-700', negociacion: 'bg-peach-100 text-amber-800',
  ganada: 'bg-mint-100 text-emerald-700', perdida: 'bg-red-100 text-red-700',
};
function money(v, c = 'MXN') { return `$${Number(v || 0).toLocaleString('es-MX')} ${c}`; }

export default function QuotationsList() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState('');
  const [state, setState] = useState('');
  const [showArchived, setShowArchived] = useState(false);

  useEffect(() => {
    (async () => {
      const { data } = await api.get('/quotations', { params: showArchived ? { archived: true } : {} });
      setItems(data);
    })();
  }, [showArchived]);

  const filtered = items.filter((x) => {
    if (state && x.state !== state) return false;
    if (q) {
      const s = q.toLowerCase();
      return ((x.code || '') + (x.client_snapshot?.name || '') + (x.package_snapshot?.name || '')).toLowerCase().includes(s);
    }
    return true;
  });

  return (
    <AppShell>
      <div className="flex items-end justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight">Cotizaciones</h1>
          <p className="text-ink-500 mt-1">{items.length} {showArchived ? 'archivadas' : 'en total'}</p>
        </div>
        <Link to="/app/quotations/new" className="btn-primary" data-testid="new-quotation-btn"><Plus className="w-4 h-4" /> Nueva</Link>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} className="input-field pl-10" placeholder="Buscar por código, cliente o paquete" data-testid="quotations-search" />
        </div>
        <select value={state} onChange={(e) => setState(e.target.value)} className="input-field sm:w-56" data-testid="quotations-filter-state">
          <option value="">Todos los estados</option>
          {Object.entries(STATE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <button onClick={() => setShowArchived((v) => !v)} className={`pill whitespace-nowrap ${showArchived ? 'bg-brand-500 text-white' : 'bg-white border border-ink-200 text-ink-600'}`} data-testid="toggle-archived">
          {showArchived ? 'Ver activas' : 'Ver archivadas'}
        </button>
      </div>

      <div className="card-surface overflow-hidden" data-testid="quotations-table">
        <div className="hidden md:grid grid-cols-12 px-6 py-3 border-b border-ink-100 text-xs uppercase tracking-widest font-bold text-ink-400">
          <div className="col-span-2">Código</div><div className="col-span-3">Cliente</div>
          <div className="col-span-3">Paquete</div><div className="col-span-2">Estado</div>
          <div className="col-span-2 text-right">Total</div>
        </div>
        {filtered.map((x) => (
          <Link key={x.id} to={`/app/quotations/${x.id}`}
            data-testid={`row-${x.code}`}
            className="grid grid-cols-12 gap-2 px-6 py-4 border-b border-ink-100 last:border-0 hover:bg-brand-50/40 transition-colors">
            <div className="col-span-12 md:col-span-2 font-mono text-sm text-brand-500 font-semibold">{x.code}</div>
            <div className="col-span-6 md:col-span-3 text-sm text-ink-900 font-medium">{x.client_snapshot?.name}</div>
            <div className="col-span-6 md:col-span-3 text-sm text-ink-500 truncate">{x.package_snapshot?.name || 'Servicios a la carta'}</div>
            <div className="col-span-6 md:col-span-2"><span className={`pill ${STATE_TONES[x.state]}`}>{STATE_LABELS[x.state]}</span></div>
            <div className="col-span-6 md:col-span-2 md:text-right font-display font-semibold text-ink-900">{money(x.total, x.currency)}</div>
          </Link>
        ))}
        {filtered.length === 0 && (
          <div className="p-12 text-center" data-testid="empty-list">
            <Search className="w-9 h-9 mx-auto text-ink-300" />
            <p className="text-ink-700 font-semibold mt-3">{showArchived ? 'No hay cotizaciones archivadas' : 'Aún no tienes cotizaciones'}</p>
            <p className="text-ink-400 text-sm mt-1">{showArchived ? 'Las cotizaciones que archives aparecerán aquí.' : 'Crea tu primera cotización para empezar a vender.'}</p>
            {!showArchived && <Link to="/app/quotations/new" className="btn-secondary text-sm mt-4 inline-flex"><Plus className="w-4 h-4" /> Nueva cotización</Link>}
          </div>
        )}
      </div>
    </AppShell>
  );
}
