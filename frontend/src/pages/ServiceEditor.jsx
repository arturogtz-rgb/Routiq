import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { ArrowLeft, Save, Plus, Trash2, Bus, Ticket, Map, Sparkles, Image as ImageIcon, Loader2 } from 'lucide-react';

const CATEGORIES = [
  { key: 'tour', label: 'Tour', icon: Map },
  { key: 'traslado', label: 'Traslado', icon: Bus },
  { key: 'acceso', label: 'Acceso', icon: Ticket },
  { key: 'extra', label: 'Extra', icon: Sparkles },
];
const UNITS = [
  { key: 'per_person', label: 'Por persona' }, { key: 'per_group', label: 'Por grupo' },
  { key: 'per_day', label: 'Por día' }, { key: 'per_access', label: 'Por acceso' },
];
const DUR_UNITS = [{ key: 'minutos', label: 'Minutos' }, { key: 'horas', label: 'Horas' }, { key: 'dias', label: 'Días' }];
const DAYS = [['Lun', 0], ['Mar', 1], ['Mié', 2], ['Jue', 3], ['Vie', 4], ['Sáb', 5], ['Dom', 6]];
const EMPTY = { name: '', category: 'tour', description: '', net_price: 0, public_price: 0, unit: 'per_group', image_url: '', duration_value: 0, duration_unit: 'horas', operating_days: [], includes: [], excludes: [], is_private: false, status: 'active' };
function money(v) { return `$${Number(v || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }

export default function ServiceEditor() {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = !!id;
  const [form, setForm] = useState(EMPTY);
  const [margin, setMargin] = useState(0.76);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const imgRef = useRef(null);
  const backend = process.env.REACT_APP_BACKEND_URL || '';
  const imgSrc = (u) => (u ? (u.startsWith('http') ? u : `${backend}${u}`) : '');

  useEffect(() => {
    (async () => {
      try {
        const { data: co } = await api.get('/companies/me');
        setMargin(co?.pricing_config?.margin_divisor || 0.76);
        if (isEdit) {
          const { data } = await api.get(`/services/${id}`);
          setForm({ ...EMPTY, ...data, operating_days: data.operating_days || [], includes: data.includes || [], excludes: data.excludes || [] });
        }
      } catch (e) { setError(formatApiError(e)); }
    })();
  }, [id, isEdit]);

  const suggestedPublic = (+form.net_price > 0 && margin > 0) ? Math.round((+form.net_price / margin) * 100) / 100 : 0;

  const uploadImage = async (e) => {
    const file = e.target.files?.[0];
    if (file) e.target.value = '';
    if (!file) return;
    setError(''); setUploading(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      const { data } = await api.post('/packages/upload-image', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setForm((f) => ({ ...f, image_url: data.url }));
    } catch (err) { setError(formatApiError(err)); }
    finally { setUploading(false); }
  };

  const allDays = form.operating_days.length === 0;
  const toggleDay = (d) => setForm((f) => {
    const has = f.operating_days.includes(d);
    return { ...f, operating_days: has ? f.operating_days.filter((x) => x !== d) : [...f.operating_days, d].sort((a, b) => a - b) };
  });
  const updList = (key, i, val) => setForm((f) => ({ ...f, [key]: f[key].map((x, j) => (j === i ? val : x)) }));
  const addList = (key) => setForm((f) => ({ ...f, [key]: [...f[key], ''] }));
  const delList = (key, i) => setForm((f) => ({ ...f, [key]: f[key].filter((_, j) => j !== i) }));

  const save = async () => {
    setError(''); setSaving(true);
    try {
      const payload = { ...form, net_price: +form.net_price || 0, public_price: +form.public_price || 0, duration_value: +form.duration_value || 0, includes: form.includes.filter((x) => (x || '').trim()), excludes: form.excludes.filter((x) => (x || '').trim()) };
      if (isEdit) await api.patch(`/services/${id}`, payload);
      else await api.post('/services', payload);
      navigate('/app/services');
    } catch (e) { setError(formatApiError(e)); }
    finally { setSaving(false); }
  };

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto" data-testid="service-editor-page">
        <button onClick={() => navigate('/app/services')} className="btn-ghost text-sm mb-4" data-testid="service-editor-back"><ArrowLeft className="w-4 h-4" /> Volver a servicios</button>
        <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight mb-6">{isEdit ? 'Editar servicio' : 'Nuevo servicio'}</h1>
        {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-2 text-sm mb-4">{error}</div>}
        <div className="card-surface p-6 space-y-4">
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

          <div><label className="label-text">Imagen de portada</label>
            <div className="flex items-center gap-3">
              <button type="button" className="btn-ghost text-sm" onClick={() => imgRef.current?.click()} disabled={uploading} data-testid="service-image-upload-btn">
                {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ImageIcon className="w-4 h-4" />} {uploading ? 'Subiendo…' : 'Subir imagen'}
              </button>
              {form.image_url && <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => setForm((f) => ({ ...f, image_url: '' }))} data-testid="service-image-remove">Quitar</button>}
              <input ref={imgRef} type="file" accept="image/*" className="hidden" onChange={uploadImage} data-testid="service-image-file" />
            </div>
            <input className="input-field mt-2" placeholder="o pega una URL https://..." value={form.image_url || ''} onChange={(e) => setForm((f) => ({ ...f, image_url: e.target.value }))} data-testid="service-image-input" />
            {form.image_url ? <img src={imgSrc(form.image_url)} alt="" className="mt-2 h-28 w-full object-cover rounded-lg border border-ink-100" onError={(e) => { e.currentTarget.style.display = 'none'; }} /> : null}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div><label className="label-text">Duración</label>
              <input type="number" min="0" step="0.5" className="input-field" value={form.duration_value} onChange={(e) => setForm((f) => ({ ...f, duration_value: e.target.value }))} data-testid="service-duration-value" /></div>
            <div><label className="label-text">Unidad de duración</label>
              <select className="input-field" value={form.duration_unit} onChange={(e) => setForm((f) => ({ ...f, duration_unit: e.target.value }))} data-testid="service-duration-unit">
                {DUR_UNITS.map((u) => <option key={u.key} value={u.key}>{u.label}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="label-text">Días de operación</label>
            <div className="flex flex-wrap gap-2" data-testid="service-operating-days">
              <button type="button" onClick={() => setForm((f) => ({ ...f, operating_days: [] }))} className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${allDays ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-ink-100 text-ink-500 hover:border-brand-300'}`} data-testid="service-day-all">Todos los días</button>
              {DAYS.map(([label, d]) => (
                <button type="button" key={d} onClick={() => toggleDay(d)} className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${form.operating_days.includes(d) ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-ink-100 text-ink-500 hover:border-brand-300'}`} data-testid={`service-day-${d}`}>{label}</button>
              ))}
            </div>
            <p className="text-[11px] text-ink-400 mt-1">Sin selección = disponible todos los días.</p>
          </div>

          <label className="flex items-center gap-3 rounded-xl border border-ink-100 p-3 cursor-pointer" data-testid="service-private-toggle">
            <input type="checkbox" className="w-4 h-4 accent-brand-500" checked={!!form.is_private} onChange={(e) => setForm((f) => ({ ...f, is_private: e.target.checked }))} data-testid="service-private-checkbox" />
            <span>
              <span className="block text-sm font-medium text-ink-900">Servicio privado</span>
              <span className="block text-[11px] text-ink-400">No aparece en el catálogo público; sí está disponible al cotizar internamente.</span>
            </span>
          </label>

          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="label-text">Incluye</label>
              <div className="space-y-2" data-testid="service-includes">
                {form.includes.map((x, i) => (
                  <div key={i} className="flex gap-2">
                    <input className="input-field" value={x} placeholder="Ej. Transporte" onChange={(e) => updList('includes', i, e.target.value)} data-testid={`service-includes-input-${i}`} />
                    <button type="button" className="text-red-600 hover:text-red-800 px-1" onClick={() => delList('includes', i)} data-testid={`service-includes-remove-${i}`}><Trash2 className="w-4 h-4" /></button>
                  </div>
                ))}
                <button type="button" className="btn-ghost text-xs" onClick={() => addList('includes')} data-testid="service-includes-add"><Plus className="w-4 h-4" /> Agregar</button>
              </div>
            </div>
            <div>
              <label className="label-text">No incluye</label>
              <div className="space-y-2" data-testid="service-excludes">
                {form.excludes.map((x, i) => (
                  <div key={i} className="flex gap-2">
                    <input className="input-field" value={x} placeholder="Ej. Propinas" onChange={(e) => updList('excludes', i, e.target.value)} data-testid={`service-excludes-input-${i}`} />
                    <button type="button" className="text-red-600 hover:text-red-800 px-1" onClick={() => delList('excludes', i)} data-testid={`service-excludes-remove-${i}`}><Trash2 className="w-4 h-4" /></button>
                  </div>
                ))}
                <button type="button" className="btn-ghost text-xs" onClick={() => addList('excludes')} data-testid="service-excludes-add"><Plus className="w-4 h-4" /> Agregar</button>
              </div>
            </div>
          </div>

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
        <div className="flex justify-end gap-2 mt-6">
          <button className="btn-ghost" onClick={() => navigate('/app/services')}>Cancelar</button>
          <button className="btn-primary" onClick={save} disabled={saving || !form.name} data-testid="save-service-btn">
            <Save className="w-4 h-4" /> {saving ? 'Guardando…' : 'Guardar'}
          </button>
        </div>
      </div>
    </AppShell>
  );
}
