import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { formatDateEs } from '@/lib/dates';
import { Inbox, Phone, Mail, Calendar, Users, MessageCircle, FileText, Check, Archive, RotateCcw, TrendingUp, Sparkles, Clock } from 'lucide-react';

const STATUS_LABEL = { new: 'Nueva', attended: 'Atendida', archived: 'Archivada' };
const STATUS_STYLE = {
  new: 'bg-peach-100 text-amber-700',
  attended: 'bg-mint-100 text-emerald-700',
  archived: 'bg-ink-100 text-ink-400',
};

export default function Leads() {
  const navigate = useNavigate();
  const [leads, setLeads] = useState([]);
  const [stats, setStats] = useState(null);
  const [filter, setFilter] = useState('active'); // active | all | archived
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const [l, s] = await Promise.all([api.get('/quote-requests'), api.get('/quote-requests/stats').catch(() => ({ data: null }))]);
      setLeads(l.data); setStats(s.data);
    }
    catch (e) { setError(formatApiError(e)); }
  };
  useEffect(() => { load(); }, []);

  const setStatus = async (id, status) => {
    try { await api.patch(`/quote-requests/${id}`, { status }); await load(); }
    catch (e) { setError(formatApiError(e)); }
  };

  const waLink = (l) => {
    const phone = (l.phone || '').replace(/[^\d]/g, '');
    const text = encodeURIComponent(`Hola ${l.name}, gracias por tu interés en "${l.package_name}". Te comparto tu cotización personalizada:`);
    return `https://wa.me/${phone}?text=${text}`;
  };

  const visible = leads.filter((l) =>
    filter === 'all' ? true : filter === 'archived' ? l.status === 'archived' : l.status !== 'archived');
  const newCount = leads.filter((l) => l.status === 'new').length;

  return (
    <AppShell>
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl md:text-4xl font-semibold text-ink-900 tracking-tight">Solicitudes de paquete</h1>
          <p className="text-ink-500 mt-1">Clientes que pidieron cotización desde la vista pública de un paquete.{newCount > 0 && <span className="ml-1 font-semibold text-amber-700">{newCount} nueva(s).</span>}</p>
        </div>
        <div className="flex gap-1 bg-white border border-ink-100 rounded-xl p-1" data-testid="leads-filter">
          {[['active', 'Activas'], ['archived', 'Archivadas'], ['all', 'Todas']].map(([k, lbl]) => (
            <button key={k} onClick={() => setFilter(k)} data-testid={`leads-filter-${k}`}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${filter === k ? 'bg-brand-50 text-brand-500' : 'text-ink-500 hover:text-ink-700'}`}>{lbl}</button>
          ))}
        </div>
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="leads-error">{error}</div>}

      {stats && stats.total > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-6" data-testid="leads-dashboard">
          {[
            { icon: Inbox, label: 'Total solicitudes', v: stats.total, tone: 'bg-brand-50 text-brand-500' },
            { icon: Sparkles, label: 'Nuevas', v: stats.new, tone: 'bg-peach-100 text-amber-700' },
            { icon: Clock, label: 'Últimos 7 días', v: stats.this_week, tone: 'bg-mint-100 text-emerald-700' },
            { icon: Check, label: 'Atendidas', v: stats.attended, tone: 'bg-brand-500 text-white' },
          ].map(({ icon: Icon, label, v, tone }) => (
            <div key={label} className="card-surface p-5" data-testid={`leads-stat-${label}`}>
              <div className={`w-9 h-9 rounded-xl ${tone} flex items-center justify-center`}><Icon className="w-4 h-4" /></div>
              <p className="text-xs uppercase tracking-widest text-ink-400 font-bold mt-3">{label}</p>
              <p className="font-display text-3xl font-bold text-ink-900 mt-1">{v}</p>
            </div>
          ))}
          {stats.top_packages?.length > 0 && (
            <div className="card-surface p-5 lg:col-span-4" data-testid="leads-top-packages">
              <p className="text-xs uppercase tracking-widest text-ink-400 font-bold flex items-center gap-1.5 mb-3"><TrendingUp className="w-4 h-4" /> Paquetes más solicitados</p>
              <div className="space-y-2">
                {stats.top_packages.map((p) => {
                  const pct = Math.round((p.count / stats.total) * 100);
                  return (
                    <div key={p.name} className="flex items-center gap-3">
                      <span className="text-sm text-ink-700 w-48 truncate">{p.name}</span>
                      <div className="flex-1 h-2.5 rounded-full bg-ink-100 overflow-hidden"><div className="h-full bg-brand-500 rounded-full" style={{ width: `${pct}%` }} /></div>
                      <span className="text-sm font-semibold text-ink-900 w-10 text-right">{p.count}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="space-y-3">
        {visible.map((l) => (
          <div key={l.id} className="card-surface p-5" data-testid={`lead-${l.id}`}>
            <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-semibold text-ink-900">{l.name}</h3>
                  <span className={`pill text-[10px] ${STATUS_STYLE[l.status] || ''}`} data-testid={`lead-status-${l.id}`}>{STATUS_LABEL[l.status] || l.status}</span>
                </div>
                <p className="text-sm text-ink-500 mt-1 flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className="flex items-center gap-1"><Mail className="w-3.5 h-3.5" /> {l.email}</span>
                  {l.phone && <span className="flex items-center gap-1"><Phone className="w-3.5 h-3.5" /> {l.phone}</span>}
                  {l.travel_date && <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> {formatDateEs(l.travel_date)}</span>}
                  {l.pax && <span className="flex items-center gap-1"><Users className="w-3.5 h-3.5" /> {l.pax}</span>}
                </p>
                <p className="text-sm text-ink-700 mt-2"><span className="pill bg-brand-50 text-brand-500 font-mono text-[10px] mr-2">{l.package_code}</span>{l.package_name}</p>
                {l.message && <p className="text-sm text-ink-500 mt-2 italic">“{l.message}”</p>}
                <p className="text-[11px] text-ink-300 mt-2">{(l.created_at || '').slice(0, 16).replace('T', ' ')}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2 shrink-0">
                <button onClick={() => navigate(`/app/quotations/new?package=${l.package_id}&lead=${l.id}`)} className="btn-primary text-sm" data-testid={`lead-quote-${l.id}`}>
                  <FileText className="w-4 h-4" /> Crear cotización
                </button>
                {l.phone && <a href={waLink(l)} target="_blank" rel="noreferrer" className="btn-secondary text-sm" data-testid={`lead-wa-${l.id}`}><MessageCircle className="w-4 h-4" /> WhatsApp</a>}
                {l.status !== 'attended' && <button onClick={() => setStatus(l.id, 'attended')} className="btn-ghost text-sm" data-testid={`lead-attend-${l.id}`}><Check className="w-4 h-4" /> Atendida</button>}
                {l.status !== 'archived'
                  ? <button onClick={() => setStatus(l.id, 'archived')} className="btn-ghost text-sm text-ink-400" data-testid={`lead-archive-${l.id}`}><Archive className="w-4 h-4" /></button>
                  : <button onClick={() => setStatus(l.id, 'new')} className="btn-ghost text-sm" data-testid={`lead-restore-${l.id}`}><RotateCcw className="w-4 h-4" /></button>}
              </div>
            </div>
          </div>
        ))}
        {visible.length === 0 && (
          <div className="text-center py-16 text-ink-400" data-testid="leads-empty">
            <Inbox className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>Sin solicitudes por ahora. Comparte la vista pública de un paquete para empezar a recibir leads.</p>
          </div>
        )}
      </div>
    </AppShell>
  );
}
