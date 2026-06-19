import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { formatDateEs } from '@/lib/dates';
import {
  ArrowLeft, Save, Plus, Trash2, UploadCloud, Image as ImageIcon, Loader2,
  Hotel, CalendarRange, ListChecks, MapPinned, Sun, Info,
} from 'lucide-react';

const backend = process.env.REACT_APP_BACKEND_URL || '';
const OCC = ['sencilla', 'doble', 'triple', 'cuadruple'];
const DAYS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
const uid = () => (crypto?.randomUUID ? crypto.randomUUID() : `id-${Date.now()}-${Math.random()}`);

const EMPTY_PKG = {
  code: '', name: '', nights: 3, description: '', image_url: '', status: 'active',
  allowed_start_days: [], includes: [], excludes: [], itinerary: [], seasons: [], hotels: [],
  inclusions: { arrival_transfer: false, departure_transfer: false, lodging: false, tours: false, venue_access: false, extras: '' },
};

const INCLUSION_OPTS = [
  ['arrival_transfer', 'Traslado de llegada'],
  ['departure_transfer', 'Traslado de salida'],
  ['lodging', 'Hospedaje'],
  ['tours', 'Tours'],
  ['venue_access', 'Accesos a recintos'],
];

function Section({ icon: Icon, title, desc, children }) {
  return (
    <div className="card-surface p-6 space-y-4">
      <div>
        <h3 className="font-display font-semibold text-ink-900 flex items-center gap-2"><Icon className="w-4 h-4 text-brand-500" /> {title}</h3>
        {desc && <p className="text-xs text-ink-500 mt-1">{desc}</p>}
      </div>
      {children}
    </div>
  );
}

function StringList({ items, onChange, placeholder, testid }) {
  return (
    <div className="space-y-2" data-testid={testid}>
      {(items || []).map((v, i) => (
        <div key={i} className="flex gap-2">
          <input className="input-field text-sm" value={v} placeholder={placeholder}
            onChange={(e) => onChange(items.map((x, j) => (j === i ? e.target.value : x)))} />
          <button type="button" className="p-2 text-ink-400 hover:text-red-600" onClick={() => onChange(items.filter((_, j) => j !== i))}><Trash2 className="w-4 h-4" /></button>
        </div>
      ))}
      <button type="button" className="text-sm text-brand-500 font-medium inline-flex items-center gap-1" onClick={() => onChange([...(items || []), ''])}><Plus className="w-4 h-4" /> Agregar</button>
    </div>
  );
}

export default function PackageEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const fromCustom = search.get('from'); // 'custom' | 'template'
  const editing = !!id;
  const [pkg, setPkg] = useState(EMPTY_PKG);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    if (!editing) return;
    (async () => {
      try {
        const { data } = await api.get(`/packages/${id}`);
        setPkg({ ...EMPTY_PKG, ...data });
      } catch (e) { setError(formatApiError(e)); }
    })();
  }, [id]); // eslint-disable-line

  const set = (k, v) => setPkg((p) => ({ ...p, [k]: v }));

  const toggleDay = (d) => set('allowed_start_days',
    pkg.allowed_start_days.includes(d) ? pkg.allowed_start_days.filter((x) => x !== d) : [...pkg.allowed_start_days, d].sort());

  // Hotels
  const addHotel = () => set('hotels', [...pkg.hotels, { name: '', category: '', prices_by_occupancy: { sencilla: 0, doble: 0, triple: 0, cuadruple: 0 }, minor_price: 0, season_prices: {} }]);
  const updHotel = (i, patch) => set('hotels', pkg.hotels.map((h, j) => (j === i ? { ...h, ...patch } : h)));
  const updHotelPrice = (i, occ, val) => updHotel(i, { prices_by_occupancy: { ...pkg.hotels[i].prices_by_occupancy, [occ]: +val || 0 } });
  const updHotelSeasonPrice = (i, sid, occ, val) => {
    const sp = { ...(pkg.hotels[i].season_prices || {}) };
    sp[sid] = { ...(sp[sid] || {}), [occ]: +val || 0 };
    updHotel(i, { season_prices: sp });
  };

  // Seasons
  const addSeason = () => set('seasons', [...pkg.seasons, { id: uid(), name: '', ranges: [{ start: '', end: '' }] }]);
  const updSeason = (i, patch) => set('seasons', pkg.seasons.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const removeSeason = (i) => {
    const sid = pkg.seasons[i].id;
    set('seasons', pkg.seasons.filter((_, j) => j !== i));
    // also strip its prices from hotels
    set('hotels', pkg.hotels.map((h) => { const sp = { ...(h.season_prices || {}) }; delete sp[sid]; return { ...h, season_prices: sp }; }));
  };
  const addRange = (i) => updSeason(i, { ranges: [...pkg.seasons[i].ranges, { start: '', end: '' }] });
  const updRange = (i, j, patch) => updSeason(i, { ranges: pkg.seasons[i].ranges.map((r, k) => (k === j ? { ...r, ...patch } : r)) });

  // Itinerary
  const addDay = () => set('itinerary', [...pkg.itinerary, { day: pkg.itinerary.length + 1, title: '', description: '' }]);
  const updDay = (i, patch) => set('itinerary', pkg.itinerary.map((d, j) => (j === i ? { ...d, ...patch } : d)));

  const uploadImage = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      const { data } = await api.post('/packages/upload-image', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      set('image_url', data.url);
    } catch (er) { setError(formatApiError(er)); }
    finally { setUploading(false); }
  };

  const save = async () => {
    setError(''); setSaving(true);
    try {
      const payload = { ...pkg, nights: +pkg.nights || 0 };
      if (editing) await api.patch(`/packages/${id}`, payload);
      else await api.post('/packages', payload);
      navigate('/app/packages');
    } catch (e) { setError(formatApiError(e)); setSaving(false); }
  };

  return (
    <AppShell>
      <button onClick={() => navigate('/app/packages')} className="btn-ghost text-sm mb-4" data-testid="back-to-packages"><ArrowLeft className="w-4 h-4" /> Paquetes</button>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight">{editing ? 'Editar paquete' : 'Nuevo paquete'}</h1>
        <button className="btn-primary" onClick={save} disabled={saving || !pkg.name || !pkg.code} data-testid="save-package-btn">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Guardar paquete
        </button>
      </div>
      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="package-error">{error}</div>}

      {fromCustom && (
        <div className="rounded-xl border border-amber-200 bg-peach-100/60 text-amber-800 px-4 py-3 text-sm mb-4 flex items-start gap-3" data-testid="prefill-notice">
          <Info className="w-5 h-5 shrink-0 mt-0.5 text-amber-600" />
          <div>
            <p className="font-semibold">Paquete creado desde {fromCustom === 'template' ? 'una plantilla' : 'una cotización a medida'}.</p>
            <p className="mt-0.5">Revisa y <b>ajusta los precios por ocupación</b> del hotel prellenado (sencilla/doble/triple/cuádruple) antes de publicar.{fromCustom === 'template' ? ' Cambia el Estado a "Activo" y guarda para que aparezca en tu catálogo público.' : ''}</p>
          </div>
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-6">
        {/* General */}
        <Section icon={ListChecks} title="Datos generales">
          <div className="grid grid-cols-3 gap-3">
            <div><label className="label-text">Código</label><input className="input-field" value={pkg.code} onChange={(e) => set('code', e.target.value)} data-testid="pkg-code" /></div>
            <div className="col-span-2"><label className="label-text">Nombre</label><input className="input-field" value={pkg.name} onChange={(e) => set('name', e.target.value)} data-testid="pkg-name" /></div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div><label className="label-text">Noches</label><input type="number" min="1" className="input-field" value={pkg.nights} onChange={(e) => set('nights', e.target.value)} data-testid="pkg-nights" /></div>
            <div className="col-span-2"><label className="label-text">Estado</label>
              <select className="input-field" value={pkg.status} onChange={(e) => set('status', e.target.value)}><option value="active">Activo</option><option value="inactive">Inactivo</option></select>
            </div>
          </div>
          <div><label className="label-text">Descripción</label><textarea rows="3" className="input-field" value={pkg.description} onChange={(e) => set('description', e.target.value)} data-testid="pkg-desc" /></div>
          <div>
            <label className="label-text">Imagen del paquete (enlace público)</label>
            <div className="flex items-center gap-3">
              <div className="w-24 h-16 rounded-lg bg-ink-100 overflow-hidden flex items-center justify-center shrink-0">
                {pkg.image_url ? <img src={pkg.image_url.startsWith('http') ? pkg.image_url : `${backend}${pkg.image_url}`} alt="" className="w-full h-full object-cover" /> : <ImageIcon className="w-5 h-5 text-ink-400" />}
              </div>
              <button type="button" className="btn-secondary text-sm" onClick={() => fileRef.current?.click()} disabled={uploading} data-testid="pkg-image-btn">
                {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <UploadCloud className="w-4 h-4" />} Subir
              </button>
              {pkg.image_url && <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => set('image_url', '')}>Quitar</button>}
              <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={uploadImage} />
            </div>
          </div>
          <div>
            <label className="label-text">Días de salida permitidos (opcional)</label>
            <div className="flex flex-wrap gap-2" data-testid="pkg-days">
              {DAYS.map((d, i) => (
                <button key={d} type="button" onClick={() => toggleDay(i)}
                  className={`pill ${pkg.allowed_start_days.includes(i) ? 'bg-brand-500 text-white' : 'bg-white border border-ink-200 text-ink-600'}`}>{d}</button>
              ))}
            </div>
            <p className="text-xs text-ink-400 mt-1">Vacío = cualquier día. Si eliges algunos, el constructor advierte cuando el check-in no coincide.</p>
          </div>
        </Section>

        {/* Seasons */}
        <Section icon={CalendarRange} title="Temporadas" desc="Define rangos de fechas (ej. Alta/Baja). El motor aplica el precio correcto según el check-in.">
          {pkg.seasons.map((s, i) => (
            <div key={s.id} className="rounded-xl border border-ink-100 p-3 space-y-2" data-testid={`season-${i}`}>
              <div className="flex gap-2">
                <input className="input-field text-sm" placeholder="Nombre (ej. Alta)" value={s.name} onChange={(e) => updSeason(i, { name: e.target.value })} data-testid={`season-name-${i}`} />
                <button type="button" className="p-2 text-ink-400 hover:text-red-600" onClick={() => removeSeason(i)}><Trash2 className="w-4 h-4" /></button>
              </div>
              {s.ranges.map((r, j) => (
                <div key={j} className="flex items-center gap-2 text-sm">
                  <input type="date" className="input-field text-sm" value={r.start} onChange={(e) => updRange(i, j, { start: e.target.value })} data-testid={`season-${i}-start-${j}`} />
                  <span className="text-ink-400">→</span>
                  <input type="date" className="input-field text-sm" value={r.end} onChange={(e) => updRange(i, j, { end: e.target.value })} data-testid={`season-${i}-end-${j}`} />
                </div>
              ))}
              <button type="button" className="text-xs text-brand-500" onClick={() => addRange(i)}>+ rango de fechas</button>
            </div>
          ))}
          <button type="button" className="btn-secondary text-sm" onClick={addSeason} data-testid="add-season-btn"><Plus className="w-4 h-4" /> Agregar temporada</button>
        </Section>

        {/* Hotels */}
        <Section icon={Hotel} title="Hoteles y precios" desc="Precio base por ocupación. Si hay temporadas, puedes definir precios específicos por temporada.">
          {pkg.hotels.map((h, i) => (
            <div key={i} className="rounded-xl border border-ink-100 p-3 space-y-3" data-testid={`hotel-${i}`}>
              <div className="flex gap-2">
                <input className="input-field text-sm" placeholder="Nombre del hotel" value={h.name} onChange={(e) => updHotel(i, { name: e.target.value })} data-testid={`hotel-name-${i}`} />
                <button type="button" className="p-2 text-ink-400 hover:text-red-600" onClick={() => set('hotels', pkg.hotels.filter((_, j) => j !== i))}><Trash2 className="w-4 h-4" /></button>
              </div>
              <p className="text-xs uppercase font-bold tracking-wide text-ink-400">Precio base por ocupación (MXN)</p>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                {OCC.map((occ) => (
                  <div key={occ}><label className="text-[11px] text-ink-500 capitalize">{occ}</label>
                    <input type="number" className="input-field text-sm" value={h.prices_by_occupancy?.[occ] ?? 0} onChange={(e) => updHotelPrice(i, occ, e.target.value)} data-testid={`hotel-${i}-${occ}`} /></div>
                ))}
                <div><label className="text-[11px] text-ink-500">Menor</label>
                  <input type="number" className="input-field text-sm" value={h.minor_price ?? 0} onChange={(e) => updHotel(i, { minor_price: +e.target.value || 0 })} /></div>
              </div>
              {pkg.seasons.filter((s) => s.name).map((s) => (
                <div key={s.id} className="rounded-lg bg-brand-50/50 p-2">
                  <p className="text-[11px] uppercase font-bold tracking-wide text-brand-500 mb-1 flex items-center gap-1"><Sun className="w-3 h-3" /> Temporada {s.name}</p>
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                    {OCC.map((occ) => (
                      <div key={occ}><label className="text-[11px] text-ink-500 capitalize">{occ}</label>
                        <input type="number" className="input-field text-sm" placeholder={String(h.prices_by_occupancy?.[occ] ?? 0)}
                          value={h.season_prices?.[s.id]?.[occ] ?? ''} onChange={(e) => updHotelSeasonPrice(i, s.id, occ, e.target.value)} data-testid={`hotel-${i}-${s.id}-${occ}`} /></div>
                    ))}
                    <div><label className="text-[11px] text-ink-500">Menor</label>
                      <input type="number" className="input-field text-sm" placeholder={String(h.minor_price ?? 0)}
                        value={h.season_prices?.[s.id]?.minor_price ?? ''} onChange={(e) => updHotelSeasonPrice(i, s.id, 'minor_price', e.target.value)} /></div>
                  </div>
                </div>
              ))}
            </div>
          ))}
          <button type="button" className="btn-secondary text-sm" onClick={addHotel} data-testid="add-hotel-btn"><Plus className="w-4 h-4" /> Agregar hotel</button>
        </Section>

        {/* Includes / Excludes */}
        <Section icon={ListChecks} title="Incluye / No incluye">
          <div><p className="label-text">Incluye</p><StringList items={pkg.includes} onChange={(v) => set('includes', v)} placeholder="Ej. Hospedaje 3 noches" testid="includes-list" /></div>
          <div className="pt-3 border-t border-ink-100"><p className="label-text">No incluye</p><StringList items={pkg.excludes} onChange={(v) => set('excludes', v)} placeholder="Ej. Vuelos" testid="excludes-list" /></div>
        </Section>

        {/* ¿Qué incluye este paquete? (checkboxes para IA + prellenado de Confirmación) */}
        <Section icon={ListChecks} title="¿Qué incluye este paquete?" desc="Da contexto a la IA para el saludo y prellena los servicios de la Confirmación de Reserva.">
          <div className="grid sm:grid-cols-2 gap-2" data-testid="inclusions-checkboxes">
            {INCLUSION_OPTS.map(([key, label]) => (
              <label key={key} className="flex items-center gap-2 rounded-lg border border-ink-100 px-3 py-2 cursor-pointer hover:border-brand-300">
                <input type="checkbox" className="h-4 w-4 accent-brand-500" checked={!!pkg.inclusions?.[key]}
                  onChange={(e) => set('inclusions', { ...pkg.inclusions, [key]: e.target.checked })} data-testid={`inclusion-${key}`} />
                <span className="text-sm text-ink-800">{label}</span>
              </label>
            ))}
          </div>
          <div className="pt-2">
            <label className="label-text">Servicios extras (texto libre)</label>
            <input className="input-field text-sm" placeholder="Ej. Cena romántica, guía privado…" value={pkg.inclusions?.extras || ''}
              onChange={(e) => set('inclusions', { ...pkg.inclusions, extras: e.target.value })} data-testid="inclusion-extras" />
          </div>
        </Section>

        {/* Itinerary */}
        <Section icon={MapPinned} title="Itinerario día a día">
          {pkg.itinerary.map((d, i) => (
            <div key={i} className="rounded-xl border border-ink-100 p-3 space-y-2" data-testid={`day-${i}`}>
              <div className="flex gap-2 items-center">
                <span className="pill bg-brand-50 text-brand-500 shrink-0">Día {d.day || i + 1}</span>
                <input className="input-field text-sm" placeholder="Título" value={d.title} onChange={(e) => updDay(i, { title: e.target.value })} data-testid={`day-title-${i}`} />
                <button type="button" className="p-2 text-ink-400 hover:text-red-600" onClick={() => set('itinerary', pkg.itinerary.filter((_, j) => j !== i))}><Trash2 className="w-4 h-4" /></button>
              </div>
              <textarea rows="2" className="input-field text-sm" placeholder="Descripción" value={d.description} onChange={(e) => updDay(i, { description: e.target.value })} />
            </div>
          ))}
          <button type="button" className="btn-secondary text-sm" onClick={addDay} data-testid="add-day-btn"><Plus className="w-4 h-4" /> Agregar día</button>
        </Section>
      </div>
    </AppShell>
  );
}
