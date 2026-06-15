import { useEffect, useState } from 'react';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { Plus, Pencil, Trash2, X, Save, Sparkles, Bus, Ticket, Map } from 'lucide-react';

const CATEGORIES = [
  { key: 'tour', label: 'Tour', icon: Map },
  { key: 'traslado', label: 'Traslado', icon: Bus },
  { key: 'acceso', label: 'Acceso', icon: Ticket },
  { key: 'extra', label: 'Extra', icon: Sparkles },
];

const UNITS = [
  { key: 'per_person', label: 'Por persona' },
  { key: 'per_group', label: 'Por grupo' },
  { key: 'per_day', label: 'Por día' },
  { key: 'per_access', label: 'Por acceso' },
];
const UNIT_ES = { per_person: 'por persona', per_group: 'por grupo', per_day: 'por día', per_access: 'por acceso' };

const EMPTY = { name: '', category: 'tour', description: '', net_price: 0, public_price: 0, unit: 'per_group', status: 'active' };

function money(v) { return `$${Number(v || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }

export default function Services() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'company_admin';
  const [services, setServices] = useState([]);
  const [margin, setMargin] = useState(0.76);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const [s, c] = await Promise.all([api.get('/services'), api.get('/companies/me')]);
      setServices(s.data);
      setMargin(c.data?.pricing_config?.margin_divisor || 0.76);
    } catch (e) { setError(formatApiError(e)); }
  };
  useEffect(() => { load(); }, []);

  const openNew = () => { setEditing(null); setForm(EMPTY); setShowForm(true); setError(''); };
  const openEdit = (svc) => { setEditing(svc.id); setForm({ ...EMPTY, ...svc }); setShowForm(true); setError(''); };

  const suggestedPublic = form.net_price > 0 ? Math.round((form.net_price / (margin || 0.76)) * 100) / 100 : 0;

  const save = async () => {
    setError(''); setSaving(true);
    try {
      const payload = { ...form, net_price: +form.net_price || 0, public_price: +form.public_price || 0 };
      if (editing) await api.patch(`/services/${editing}`, payload);
      else await api.post('/services', payload);
      setShowForm(false);
      await load();
    } catch (e) { setError(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const remove = async (svc) => {
    if (!window.confirm(`¿Eliminar el servicio "${svc.name}"?`)) return;
    try { await api.delete(`/services/${svc.id}`); await load(); }
    catch (e) { setError(formatApiError(e)); }
  };

  return (
    <AppShell>
      <div className="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight">Servicios a la carta</h1>
          <p className="text-ink-500 mt-1">Tours, traslados, accesos y extras opcionales agregables a cualquier cotización.</p>
        </div>
        {isAdmin && (
          <button className="btn-primary text-sm" onClick={openNew} data-testid="new-service-btn">
            <Plus className="w-4 h-4" /> Nuevo servicio
          </button>
        )}
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="services-error">{error}</div>}

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="services-grid">
        {services.map((svc) => {
          const cat = CATEGORIES.find((c) => c.key === svc.category) || CATEGORIES[3];
          const Icon = cat.icon;
          return (
            <div key={svc.id} className="card-surface p-5 flex flex-col" data-testid={`service-card-${svc.id}`}>
              <div className="flex items-start justify-between">
                <span className="pill bg-brand-50 text-brand-500 inline-flex items-center gap-1.5"><Icon className="w-3.5 h-3.5" /> {cat.label}</span>
                {isAdmin && (
                  <div className="flex gap-1">
                    <button className="p-1.5 rounded-lg text-ink-400 hover:bg-brand-50 hover:text-brand-500" onClick={() => openEdit(svc)} data-testid={`edit-service-${svc.id}`}><Pencil className="w-4 h-4" /></button>
                    <button className="p-1.5 rounded-lg text-ink-400 hover:bg-red-50 hover:text-red-600" onClick={() => remove(svc)} data-testid={`delete-service-${svc.id}`}><Trash2 className="w-4 h-4" /></button>
                  </div>
                )}
              </div>
              <h3 className="font-display font-semibold text-ink-900 mt-3">{svc.name}</h3>
              {svc.description && <p className="text-sm text-ink-500 mt-1 flex-1">{svc.description}</p>}
              <div className="mt-4 pt-3 border-t border-ink-100 flex items-end justify-between">
                <div>
                  <p className="text-xs text-ink-400">Neto: {money(svc.net_price)}</p>
                  <p className="font-display text-xl font-bold text-brand-500">{money(svc.public_price)}</p>
                </div>
                {svc.unit && <span className="text-xs text-ink-400">{UNIT_ES[svc.unit] || ''}</span>}
              </div>
            </div>
          );
        })}
        {services.length === 0 && (
          <div className="col-span-full text-center py-16 text-ink-400">
            <Map className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p>Aún no hay servicios. {isAdmin ? 'Crea el primero.' : ''}</p>
          </div>
        )}
      </div>

      {/* Form modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog">
          <div className="absolute inset-0 bg-ink-900/40" onClick={() => setShowForm(false)} />
          <div className="relative card-surface p-6 w-full max-w-lg animate-fade-up" data-testid="service-form-modal">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-xl font-semibold text-ink-900">{editing ? 'Editar servicio' : 'Nuevo servicio'}</h2>
              <button onClick={() => setShowForm(false)} className="p-2 rounded-lg hover:bg-brand-50"><X className="w-5 h-5" /></button>
            </div>
            {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-2 text-sm mb-3">{error}</div>}
            <div className="space-y-4">
              <div><label className="label-text">Nombre</label>
                <input className="input-field" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} data-testid="service-name-input" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="label-text">Categoría</label>
                  <select className="input-field" value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))} data-testid="service-category-input">
                    {CATEGORIES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                  </select>
                </div>
                <div><label className="label-text">Unidad de cobro</label>
                  <select className="input-field" value={form.unit || 'per_group'} onChange={(e) => setForm((f) => ({ ...f, unit: e.target.value }))} data-testid="service-unit-input">
                    {UNITS.map((u) => <option key={u.key} value={u.key}>{u.label}</option>)}
                  </select>
                </div>
              </div>
              <div><label className="label-text">Descripción</label>
                <textarea rows="2" className="input-field" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} data-testid="service-desc-input" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="label-text">Precio neto (costo)</label>
                  <input type="number" step="0.01" className="input-field" value={form.net_price} onChange={(e) => setForm((f) => ({ ...f, net_price: e.target.value }))} data-testid="service-net-input" /></div>
                <div><label className="label-text">Precio público</label>
                  <input type="number" step="0.01" className="input-field" value={form.public_price} placeholder={suggestedPublic ? String(suggestedPublic) : ''}
                    onChange={(e) => setForm((f) => ({ ...f, public_price: e.target.value }))} data-testid="service-public-input" /></div>
              </div>
              {suggestedPublic > 0 && (
                <p className="text-xs text-ink-500">Sugerido con margen {Math.round((1 - margin) * 100)}%: <b className="text-brand-500">{money(suggestedPublic)}</b>. Déjalo en 0 para autocalcular.</p>
              )}
            </div>
            <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-ink-100">
              <button className="btn-ghost" onClick={() => setShowForm(false)}>Cancelar</button>
              <button className="btn-primary" onClick={save} disabled={saving || !form.name} data-testid="save-service-btn">
                <Save className="w-4 h-4" /> {saving ? 'Guardando…' : 'Guardar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
