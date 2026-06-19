import { useEffect, useMemo, useState } from 'react';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { formatDateEs } from '@/lib/dates';
import { UserCog, Plus, Search, Pencil, Trash2, AlertTriangle, FileText, TrendingUp, ChevronLeft, ChevronRight, Users } from 'lucide-react';

const CHANNELS = [
  { v: 'directo', label: 'Directo' },
  { v: 'agencia', label: 'Agencia' },
  { v: 'mayorista', label: 'Mayorista' },
  { v: 'operador', label: 'Mayorista Preferencial' },
];
const CHANNEL_LABEL = Object.fromEntries(CHANNELS.map((c) => [c.v, c.label]));
const PAGE_SIZE = 10;
const uid = () => (crypto?.randomUUID ? crypto.randomUUID() : `id-${Date.now()}-${Math.random()}`);
const money = (v) => `$${Number(v || 0).toLocaleString('es-MX', { maximumFractionDigits: 0 })}`;
const emptyForm = { name: '', email: '', phone: '', channel: 'directo', notes: '', executives: [] };

export default function Clients() {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [q, setQ] = useState('');
  const [channel, setChannel] = useState('todos');
  const [sort, setSort] = useState('activity');
  const [page, setPage] = useState(1);
  const [editClient, setEditClient] = useState(null); // null | {} (new) | client
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [delClient, setDelClient] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const load = async () => {
    setLoading(true);
    try { const { data } = await api.get('/clients'); setClients(data); }
    catch (e) { setError(formatApiError(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    let list = [...clients];
    const term = q.trim().toLowerCase();
    if (term) list = list.filter((c) => `${c.name} ${c.email} ${c.notes || ''}`.toLowerCase().includes(term));
    if (channel !== 'todos') list = list.filter((c) => c.channel === channel);
    const sorters = {
      activity: (a, b) => (b.quotations_count || 0) - (a.quotations_count || 0),
      sales: (a, b) => (b.sales_total || 0) - (a.sales_total || 0),
      name: (a, b) => (a.name || '').localeCompare(b.name || ''),
      recent: (a, b) => String(b.last_activity_at || '').localeCompare(String(a.last_activity_at || '')),
    };
    list.sort(sorters[sort] || sorters.activity);
    return list;
  }, [clients, q, channel, sort]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const curPage = Math.min(page, totalPages);
  const pageItems = filtered.slice((curPage - 1) * PAGE_SIZE, curPage * PAGE_SIZE);
  useEffect(() => { setPage(1); }, [q, channel, sort]);

  const openNew = () => { setForm(emptyForm); setEditClient({}); setError(''); };
  const openEdit = (c) => { setForm({ name: c.name || '', email: c.email || '', phone: c.phone || '', channel: c.channel || 'directo', notes: c.notes || '', executives: (c.executives || []).map((e) => ({ ...e })) }); setEditClient(c); setError(''); };

  const addExec = () => setForm((f) => ({ ...f, executives: [...(f.executives || []), { id: uid(), name: '', phone: '', email: '' }] }));
  const updExec = (idx, patch) => setForm((f) => ({ ...f, executives: f.executives.map((e, i) => i === idx ? { ...e, ...patch } : e) }));
  const removeExec = (idx) => setForm((f) => ({ ...f, executives: f.executives.filter((_, i) => i !== idx) }));

  const save = async () => {
    setError(''); setSaving(true);
    try {
      if (editClient && editClient.id) await api.patch(`/clients/${editClient.id}`, form);
      else await api.post('/clients', form);
      setEditClient(null); await load();
    } catch (e) { setError(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const confirmDelete = async () => {
    setError(''); setDeleting(true);
    try { await api.delete(`/clients/${delClient.id}`); setDelClient(null); await load(); }
    catch (e) { setError(formatApiError(e)); }
    finally { setDeleting(false); }
  };

  return (
    <AppShell>
      <div className="flex items-end justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight">Clientes</h1>
          <p className="text-ink-500 mt-1">Gestiona tu cartera de clientes y agencias.</p>
        </div>
        <button className="btn-primary" onClick={openNew} data-testid="new-client-btn"><Plus className="w-4 h-4" /> Nuevo cliente</button>
      </div>

      {error && !editClient && !delClient && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4">{error}</div>}

      {/* Toolbar */}
      <div className="card-surface p-4 mb-5 flex flex-col md:flex-row md:items-center gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-ink-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input className="input-field pl-9" placeholder="Buscar por nombre, correo o empresa…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="clients-search" />
        </div>
        <select className="input-field md:w-44" value={channel} onChange={(e) => setChannel(e.target.value)} data-testid="clients-filter-channel">
          <option value="todos">Todos los tipos</option>
          {CHANNELS.map((c) => <option key={c.v} value={c.v}>{c.label}</option>)}
        </select>
        <select className="input-field md:w-52" value={sort} onChange={(e) => setSort(e.target.value)} data-testid="clients-sort">
          <option value="activity">Orden: más cotizaciones</option>
          <option value="sales">Orden: más ventas</option>
          <option value="name">Orden: nombre (A-Z)</option>
          <option value="recent">Orden: actividad reciente</option>
        </select>
      </div>

      {/* List */}
      {loading ? (
        <p className="text-ink-400 text-sm">Cargando…</p>
      ) : filtered.length === 0 ? (
        <div className="card-surface text-center py-16 text-ink-400" data-testid="clients-empty">
          <UserCog className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>{clients.length === 0 ? 'No tienes clientes aún — crea tu primer cliente.' : 'Ningún cliente coincide con tu búsqueda.'}</p>
          {clients.length === 0 && <button className="btn-secondary text-sm mt-4" onClick={openNew}><Plus className="w-4 h-4" /> Nuevo cliente</button>}
        </div>
      ) : (
        <>
          <div className="space-y-2" data-testid="clients-list">
            {pageItems.map((c) => (
              <div key={c.id} className="card-surface px-5 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3" data-testid={`client-row-${c.id}`}>
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-11 h-11 rounded-full bg-brand-50 text-brand-500 flex items-center justify-center font-display font-semibold shrink-0">{(c.name || '?').slice(0, 1).toUpperCase()}</div>
                  <div className="min-w-0">
                    <p className="font-semibold text-ink-900 truncate">{c.name}</p>
                    <p className="text-xs text-ink-500 truncate">{[c.email, c.phone].filter(Boolean).join(' · ') || '—'}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4 flex-wrap">
                  <span className="pill bg-ink-100 text-ink-700 capitalize">{CHANNEL_LABEL[c.channel] || c.channel}</span>
                  <div className="text-center" title="Ejecutivos vinculados"><p className="font-semibold text-ink-900 flex items-center gap-1 text-sm" data-testid={`client-execs-${c.id}`}><Users className="w-3.5 h-3.5 text-ink-400" /> {c.executives_count || 0}</p></div>
                  <div className="text-center" title="Cotizaciones"><p className="font-semibold text-ink-900 flex items-center gap-1 text-sm" data-testid={`client-quotes-${c.id}`}><FileText className="w-3.5 h-3.5 text-ink-400" /> {c.quotations_count || 0}</p></div>
                  <div className="text-center" title="Ventas ganadas"><p className="font-semibold text-emerald-700 flex items-center gap-1 text-sm" data-testid={`client-sales-${c.id}`}><TrendingUp className="w-3.5 h-3.5" /> {money(c.sales_total)}</p></div>
                  <div className="flex items-center gap-1">
                    <button className="btn-ghost text-xs" onClick={() => openEdit(c)} data-testid={`edit-client-${c.id}`}><Pencil className="w-3.5 h-3.5" /> Editar</button>
                    <button className="btn-ghost text-xs text-red-600 hover:bg-red-50" onClick={() => { setDelClient(c); setError(''); }} data-testid={`delete-client-${c.id}`}><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Paginator */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-5" data-testid="clients-paginator">
              <p className="text-xs text-ink-400">{filtered.length} cliente(s) · página {curPage} de {totalPages}</p>
              <div className="flex items-center gap-2">
                <button className="btn-ghost text-sm" disabled={curPage <= 1} onClick={() => setPage((p) => p - 1)} data-testid="clients-prev"><ChevronLeft className="w-4 h-4" /> Anterior</button>
                <button className="btn-ghost text-sm" disabled={curPage >= totalPages} onClick={() => setPage((p) => p + 1)} data-testid="clients-next">Siguiente <ChevronRight className="w-4 h-4" /></button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Create/Edit modal */}
      {editClient && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => !saving && setEditClient(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="client-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900 mb-1">{editClient.id ? 'Editar empresa / cliente' : 'Nueva empresa / cliente'}</h3>
            <p className="text-sm text-ink-500 mb-4">Nivel 1: datos de la empresa. Nivel 2: ejecutivos vinculados.</p>
            {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-3" data-testid="client-modal-error">{error}</div>}
            <div className="space-y-3">
              <div><label className="label-text">Nombre / Empresa</label><input className="input-field" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} data-testid="client-name" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="label-text">Correo general</label><input type="email" className="input-field" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} data-testid="client-email" /></div>
                <div><label className="label-text">Teléfono general</label><input className="input-field" value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} data-testid="client-phone" /></div>
              </div>
              <div><label className="label-text">Canal</label>
                <select className="input-field" value={form.channel} onChange={(e) => setForm((f) => ({ ...f, channel: e.target.value }))} data-testid="client-channel">
                  {CHANNELS.map((c) => <option key={c.v} value={c.v}>{c.label}</option>)}
                </select>
              </div>
              <div><label className="label-text">Dirección / Notas (opcional)</label><textarea rows="2" className="input-field" value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} data-testid="client-notes" /></div>

              {/* Nivel 2 — Ejecutivos */}
              <div className="pt-3 border-t border-ink-100" data-testid="client-executives-section">
                <div className="flex items-center justify-between mb-1">
                  <p className="label-text mb-0 flex items-center gap-1.5"><Users className="w-4 h-4 text-brand-500" /> Ejecutivos / Contactos</p>
                  <button type="button" className="text-xs text-brand-600 font-medium inline-flex items-center gap-1" onClick={addExec} data-testid="add-exec-btn"><Plus className="w-3.5 h-3.5" /> Agregar ejecutivo</button>
                </div>
                <p className="text-xs text-ink-400 mb-2">Personas de contacto dentro de esta empresa. Al cotizar elegirás el ejecutivo específico.</p>
                {(form.executives || []).length === 0 && <p className="text-xs text-ink-400 italic">Sin ejecutivos. Las cotizaciones usarán los datos generales de la empresa.</p>}
                <div className="space-y-2">
                  {(form.executives || []).map((ex, i) => (
                    <div key={ex.id || i} className="rounded-xl border border-ink-100 p-2.5 grid grid-cols-1 sm:grid-cols-[1fr_1fr_1fr_auto] gap-2 items-center" data-testid={`exec-row-${i}`}>
                      <input className="input-field text-sm" placeholder="Nombre completo" value={ex.name} onChange={(e) => updExec(i, { name: e.target.value })} data-testid={`exec-name-${i}`} />
                      <input className="input-field text-sm" placeholder="Teléfono directo" value={ex.phone} onChange={(e) => updExec(i, { phone: e.target.value })} data-testid={`exec-phone-${i}`} />
                      <input className="input-field text-sm" placeholder="Correo directo" value={ex.email} onChange={(e) => updExec(i, { email: e.target.value })} data-testid={`exec-email-${i}`} />
                      <button type="button" className="p-2 text-ink-300 hover:text-red-500 justify-self-end" onClick={() => removeExec(i)} data-testid={`exec-remove-${i}`}><Trash2 className="w-4 h-4" /></button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setEditClient(null)} data-testid="client-cancel">Cancelar</button>
              <button className="btn-primary" disabled={!form.name.trim() || saving} onClick={save} data-testid="client-save">{saving ? 'Guardando…' : 'Guardar'}</button>
            </div>
          </div>
        </div>
      )}

      {/* Delete modal */}
      {delClient && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => !deleting && setDelClient(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="delete-client-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900 mb-1 flex items-center gap-2"><Trash2 className="w-5 h-5 text-red-600" /> Eliminar cliente</h3>
            <p className="text-sm text-ink-600 mt-2">Vas a eliminar a <b>{delClient.name}</b>. Las cotizaciones existentes conservarán sus datos, pero el cliente dejará de aparecer en tu cartera.</p>
            {delClient.active_count > 0 && (
              <div className="rounded-xl border border-amber-200 bg-peach-100/60 text-amber-800 px-4 py-3 text-sm mt-3 flex items-start gap-2" data-testid="delete-client-warning">
                <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5 text-amber-600" />
                <span>Este cliente tiene <b>{delClient.active_count}</b> cotización(es) activa(s). ¿Seguro que deseas eliminarlo?</span>
              </div>
            )}
            {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mt-3">{error}</div>}
            <div className="flex justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setDelClient(null)} data-testid="delete-client-cancel">Cancelar</button>
              <button className="btn-primary bg-red-600 hover:bg-red-700" disabled={deleting} onClick={confirmDelete} data-testid="delete-client-confirm">{deleting ? 'Eliminando…' : 'Eliminar'}</button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
