import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { ArrowLeft, ArrowRight, Check, User, Package, CalendarDays, Calculator, FileText, Plus, Sparkles, AlertTriangle, Moon } from 'lucide-react';
import { formatDateEs, nightsBetween, addDays, weekdayMon0, WEEKDAYS_ES } from '@/lib/dates';

const STEPS = [
  { key: 'client', label: 'Cliente', icon: User },
  { key: 'package', label: 'Paquete', icon: Package },
  { key: 'dates', label: 'Fechas y pax', icon: CalendarDays },
  { key: 'services', label: 'Servicios', icon: Sparkles },
  { key: 'review', label: 'Revisión', icon: Calculator },
];

const SERVICE_UNIT_ES = { per_person: 'por persona', per_group: 'por grupo', per_day: 'por día', per_access: 'por acceso' };

function money(v, c = 'MXN') { return `$${Number(v || 0).toLocaleString('es-MX')} ${c}`; }

export default function QuotationBuilder() {
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const [step, setStep] = useState(0);
  const [clients, setClients] = useState([]);
  const [packages, setPackages] = useState([]);
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showClient, setShowClient] = useState(false);
  const [newClient, setNewClient] = useState({ name: '', phone: '', email: '', channel: 'directo' });

  const [form, setForm] = useState({
    client_id: '',
    package_id: search.get('package') || '',
    hotel_name: '',
    dates: { start: '', end: '' },
    pax: { rooms: [{ ocupacion: 'doble', count: 1 }], menores: 0 },
    services: [],
    extra_nights: { cost_per_night: 0, unit: 'per_reservation' },
    notes: '',
  });

  useEffect(() => {
    (async () => {
      const [c, p, s] = await Promise.all([api.get('/clients'), api.get('/packages'), api.get('/services')]);
      setClients(c.data); setPackages(p.data); setServices(s.data);
      if (form.package_id && !form.hotel_name) {
        const pack = p.data.find((x) => x.id === form.package_id);
        if (pack?.hotels?.[0]) setForm((f) => ({ ...f, hotel_name: pack.hotels[0].name }));
      }
    })();
  }, []); // eslint-disable-line

  const pack = packages.find((p) => p.id === form.package_id);
  const hotel = pack?.hotels?.find((h) => h.name === form.hotel_name);
  const client = clients.find((c) => c.id === form.client_id);

  const commissionRate = (() => {
    if (!client) return 0;
    const rates = { directo: 0, agencia: 0.10, mayorista: 0.15, operador: 0.20 };
    return rates[client.channel] ?? 0;
  })();

  const OCC_COUNT = { sencilla: 1, doble: 2, triple: 3, cuadruple: 4 };

  const totalAdults = (form.pax.rooms || []).reduce((s, r) => s + OCC_COUNT[r.ocupacion] * (r.count || 0), 0);
  const totalPax = totalAdults + (form.pax.menores || 0);
  const numRooms = (form.pax.rooms || []).reduce((s, r) => s + (r.count || 0), 0);

  const packNights = pack?.nights || 0;
  const tripNights = nightsBetween(form.dates.start, form.dates.end);
  const extraNights = Math.max(0, tripNights - packNights);
  const extraCfg = form.extra_nights || { cost_per_night: 0, unit: 'per_reservation' };
  const extraMult = extraCfg.unit === 'per_person' ? totalPax : extraCfg.unit === 'per_room' ? numRooms : 1;
  const extraNightsSubtotal = extraNights > 0 ? (Number(extraCfg.cost_per_night) || 0) * extraNights * extraMult : 0;

  // Allowed departure days warning
  const allowedDays = pack?.allowed_start_days || [];
  const specialDates = pack?.special_departure_dates || [];
  const hasDayRule = allowedDays.length > 0 || specialDates.length > 0;
  const startWeekday = form.dates.start ? weekdayMon0(form.dates.start) : null;
  const startInvalid = !!form.dates.start && hasDayRule
    && !(allowedDays.includes(startWeekday) || specialDates.includes(form.dates.start));

  const serviceDefaultQty = (svc) => {
    const unit = svc.unit || (svc.per_person ? 'per_person' : 'per_group');
    if (unit === 'per_person' || unit === 'per_access') return Math.max(1, totalPax);
    if (unit === 'per_day') return Math.max(1, packNights);
    return 1;
  };

  const servicesSubtotal = (() => {
    let s = 0;
    for (const sel of (form.services || [])) {
      const svc = services.find((x) => x.id === sel.service_id);
      if (!svc) continue;
      s += Number(svc.public_price || 0) * (sel.qty || 1);
    }
    return s;
  })();

  const subtotal = (() => {
    let s = servicesSubtotal + extraNightsSubtotal;
    if (!hotel) return s;
    for (const r of (form.pax.rooms || [])) {
      const price = Number(hotel.prices_by_occupancy?.[r.ocupacion] || 0);
      s += price * OCC_COUNT[r.ocupacion] * (r.count || 0);
    }
    s += Number(hotel.minor_price || 0) * (form.pax.menores || 0);
    return s;
  })();
  const commission = Math.round(subtotal * commissionRate * 100) / 100;
  const total = subtotal - commission;

  const isServiceSelected = (id) => (form.services || []).some((s) => s.service_id === id);
  const toggleService = (svc) => setForm((f) => {
    const exists = (f.services || []).some((s) => s.service_id === svc.id);
    if (exists) return { ...f, services: f.services.filter((s) => s.service_id !== svc.id) };
    return { ...f, services: [...(f.services || []), { service_id: svc.id, qty: serviceDefaultQty(svc) }] };
  });
  const setServiceQty = (id, qty) => setForm((f) => ({
    ...f, services: f.services.map((s) => s.service_id === id ? { ...s, qty: Math.max(1, qty) } : s),
  }));

  // Setting check-in auto-suggests check-out based on package nights.
  const setStart = (start) => setForm((f) => {
    const nights = packages.find((p) => p.id === f.package_id)?.nights || 0;
    const end = start && nights > 0 ? addDays(start, nights) : f.dates.end;
    return { ...f, dates: { start, end } };
  });
  const setEnd = (end) => setForm((f) => ({ ...f, dates: { ...f.dates, end } }));
  const setExtra = (patch) => setForm((f) => ({ ...f, extra_nights: { ...f.extra_nights, ...patch } }));

  const canNext = () =>
    (step === 0 && !!form.client_id) ||
    (step === 1 && !!form.package_id && !!form.hotel_name) ||
    (step === 2 && form.dates.start && form.dates.end && (form.pax.rooms?.length > 0) && totalAdults > 0) ||
    (step === 3);

  // Free navigation: allow jumping to any step without losing data.
  const goToStep = (i) => setStep(i);

  const addRoom = (ocupacion) => setForm((f) => ({ ...f, pax: { ...f.pax, rooms: [...(f.pax.rooms || []), { ocupacion, count: 1 }] } }));
  const updateRoom = (idx, patch) => setForm((f) => ({ ...f, pax: { ...f.pax, rooms: f.pax.rooms.map((r, i) => i === idx ? { ...r, ...patch } : r) } }));
  const removeRoom = (idx) => setForm((f) => ({ ...f, pax: { ...f.pax, rooms: f.pax.rooms.filter((_, i) => i !== idx) } }));

  const handleCreateClient = async () => {
    setError('');
    try {
      const { data } = await api.post('/clients', newClient);
      setClients((cs) => [...cs, data]);
      setForm((f) => ({ ...f, client_id: data.id }));
      setShowClient(false);
      setNewClient({ name: '', phone: '', email: '', channel: 'directo' });
    } catch (e) { setError(formatApiError(e)); }
  };

  const submit = async () => {
    setError(''); setLoading(true);
    try {
      // Defensive: ensure start <= end
      const payload = { ...form };
      if (payload.dates.start && payload.dates.end && payload.dates.start > payload.dates.end) {
        payload.dates = { start: payload.dates.end, end: payload.dates.start };
      }
      const { data } = await api.post('/quotations', payload);
      navigate(`/app/quotations/${data.id}`);
    } catch (e) { setError(formatApiError(e)); }
    finally { setLoading(false); }
  };

  return (
    <AppShell>
      <div className="mb-6 flex items-center justify-between">
        <Link to="/app/quotations" className="btn-ghost text-sm" data-testid="back-to-quotations">
          <ArrowLeft className="w-4 h-4" /> Volver
        </Link>
      </div>
      <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight mb-2">Nueva cotización</h1>
      <p className="text-ink-500 mb-8">Construye una cotización de paquete armado. Navega libremente entre los pasos.</p>

      {/* Stepper — free navigation */}
      <div className="grid grid-cols-5 gap-2 mb-8">
        {STEPS.map((s, i) => (
          <button key={s.key} type="button" onClick={() => goToStep(i)}
            className={`rounded-xl p-3 border text-xs font-semibold uppercase tracking-wider text-center transition-all cursor-pointer hover:shadow-sm
              ${i === step ? 'bg-brand-500 text-white border-brand-500'
                : i < step ? 'bg-mint-100 text-emerald-700 border-mint-200' : 'bg-white text-ink-400 border-ink-100 hover:border-brand-300'}`}
              data-testid={`step-${s.key}`}>
            <div className="flex items-center justify-center gap-2">
              {i < step ? <Check className="w-4 h-4" /> : <s.icon className="w-4 h-4" />}
              <span className="hidden sm:inline">{s.label}</span>
            </div>
          </button>
        ))}
      </div>

      {error && <div className="mb-4 rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm" data-testid="builder-error">{error}</div>}

      <div className="card-surface p-6 md:p-8">
        {/* Step: Client */}
        {step === 0 && (
          <div className="space-y-4" data-testid="step-client-panel">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-xl font-semibold text-ink-900">Selecciona cliente</h2>
              <button className="btn-secondary text-sm" onClick={() => setShowClient((v) => !v)} data-testid="toggle-new-client">
                <Plus className="w-4 h-4" /> Nuevo cliente
              </button>
            </div>
            {showClient && (
              <div className="rounded-xl border border-ink-100 bg-cream p-4 space-y-3" data-testid="new-client-form">
                <div className="grid md:grid-cols-2 gap-3">
                  <div><label className="label-text">Nombre</label><input className="input-field" value={newClient.name} onChange={(e) => setNewClient((x) => ({ ...x, name: e.target.value }))} data-testid="newclient-name" /></div>
                  <div><label className="label-text">Canal</label>
                    <select className="input-field" value={newClient.channel} onChange={(e) => setNewClient((x) => ({ ...x, channel: e.target.value }))} data-testid="newclient-channel">
                      <option value="directo">Directo</option>
                      <option value="agencia">Agencia (10%)</option>
                      <option value="mayorista">Mayorista (15%)</option>
                      <option value="operador">Operador (20%)</option>
                    </select>
                  </div>
                  <div><label className="label-text">Teléfono</label><input className="input-field" value={newClient.phone} onChange={(e) => setNewClient((x) => ({ ...x, phone: e.target.value }))} data-testid="newclient-phone" /></div>
                  <div><label className="label-text">Email</label><input className="input-field" value={newClient.email} onChange={(e) => setNewClient((x) => ({ ...x, email: e.target.value }))} data-testid="newclient-email" /></div>
                </div>
                <button className="btn-primary" onClick={handleCreateClient} disabled={!newClient.name} data-testid="save-new-client">Guardar cliente</button>
              </div>
            )}
            <div className="grid md:grid-cols-2 gap-3">
              {clients.map((c) => (
                <button key={c.id} onClick={() => setForm((f) => ({ ...f, client_id: c.id }))}
                  className={`text-left rounded-xl border p-4 transition-all ${form.client_id === c.id ? 'border-brand-500 bg-brand-50' : 'border-ink-100 hover:border-brand-300'}`}
                  data-testid={`client-option-${c.id}`}>
                  <p className="font-semibold text-ink-900">{c.name}</p>
                  <p className="text-xs text-ink-500 mt-1">{c.email} · {c.phone}</p>
                  <span className="pill bg-brand-50 text-brand-500 mt-2">{c.channel}</span>
                </button>
              ))}
              {clients.length === 0 && <p className="text-ink-400 text-sm">No hay clientes. Crea uno.</p>}
            </div>
          </div>
        )}

        {/* Step: Package */}
        {step === 1 && (
          <div className="space-y-4" data-testid="step-package-panel">
            <h2 className="font-display text-xl font-semibold text-ink-900">Selecciona paquete y hotel</h2>
            <div className="grid md:grid-cols-2 gap-3">
              {packages.map((p) => (
                <button key={p.id} onClick={() => setForm((f) => ({ ...f, package_id: p.id, hotel_name: p.hotels?.[0]?.name || '' }))}
                  className={`text-left rounded-xl border p-4 transition-all ${form.package_id === p.id ? 'border-brand-500 bg-brand-50' : 'border-ink-100 hover:border-brand-300'}`}
                  data-testid={`package-option-${p.code}`}>
                  <p className="font-mono text-xs text-brand-500">{p.code}</p>
                  <p className="font-semibold text-ink-900 mt-1">{p.name}</p>
                  <p className="text-xs text-ink-500 mt-1">{p.nights} noches</p>
                </button>
              ))}
            </div>
            {pack && (
              <div>
                <label className="label-text">Hotel</label>
                <div className="grid md:grid-cols-2 gap-3">
                  {pack.hotels.map((h) => (
                    <button key={h.name} onClick={() => setForm((f) => ({ ...f, hotel_name: h.name }))}
                      className={`text-left rounded-xl border p-4 transition-all ${form.hotel_name === h.name ? 'border-brand-500 bg-brand-50' : 'border-ink-100 hover:border-brand-300'}`}
                      data-testid={`hotel-option-${h.name}`}>
                      <p className="font-semibold text-ink-900">{h.name}</p>
                      <p className="text-xs text-ink-400 mt-0.5">{h.category}</p>
                      <div className="grid grid-cols-2 gap-x-2 gap-y-1 mt-3 text-sm">
                        {Object.entries(h.prices_by_occupancy).map(([k, v]) => (
                          <div key={k}><span className="text-ink-400 text-xs uppercase tracking-wider">{k}</span> <span className="font-semibold">${v.toLocaleString('es-MX')}</span></div>
                        ))}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Step: Dates & Pax */}
        {step === 2 && (
          <div className="space-y-5" data-testid="step-dates-panel">
            <h2 className="font-display text-xl font-semibold text-ink-900">Fechas y habitaciones</h2>
            {packNights > 0 && (
              <p className="text-sm text-ink-500">El paquete incluye <b className="text-ink-900">{packNights} noches</b>. Al elegir el check-in se sugiere el check-out automáticamente.</p>
            )}
            <div className="grid md:grid-cols-2 gap-4">
              <div><label className="label-text">Check-in</label>
                <input type="date" className="input-field" value={form.dates.start} onChange={(e) => setStart(e.target.value)} data-testid="date-start" />
                {form.dates.start && <p className="text-xs text-ink-400 mt-1">{WEEKDAYS_ES[startWeekday]} · {formatDateEs(form.dates.start)}</p>}
              </div>
              <div><label className="label-text">Check-out</label>
                <input type="date" className="input-field" value={form.dates.end} onChange={(e) => setEnd(e.target.value)} data-testid="date-end" />
                {form.dates.end && <p className="text-xs text-ink-400 mt-1">{formatDateEs(form.dates.end)} · {tripNights} noche(s)</p>}
              </div>
            </div>

            {startInvalid && (
              <div className="rounded-xl border border-amber-300 bg-peach-100 text-amber-800 px-4 py-3 text-sm flex items-start gap-2" data-testid="start-day-warning">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                <div>
                  <b>Día de salida no habitual para este paquete.</b>{' '}
                  {allowedDays.length > 0 && <>Salidas válidas: {allowedDays.map((d) => WEEKDAYS_ES[d]).join(', ')}. </>}
                  {specialDates.length > 0 && <>Fechas especiales: {specialDates.map((d) => formatDateEs(d)).join(', ')}. </>}
                  Puedes continuar de todos modos.
                </div>
              </div>
            )}

            {extraNights > 0 && (
              <div className="rounded-xl border border-brand-200 bg-brand-50 p-4 space-y-3" data-testid="extra-nights-box">
                <p className="text-sm text-ink-700 flex items-center gap-2"><Moon className="w-4 h-4 text-brand-500" /> Se agregan <b className="text-brand-600">{extraNights} noche(s) extra</b> sobre las {packNights} del paquete.</p>
                <div className="grid sm:grid-cols-2 gap-3">
                  <div>
                    <label className="label-text">Costo por noche extra ({extraCfg.unit === 'per_person' ? 'por persona' : extraCfg.unit === 'per_room' ? 'por habitación' : 'por reservación'})</label>
                    <input type="number" min="0" step="0.01" className="input-field" value={extraCfg.cost_per_night}
                      onChange={(e) => setExtra({ cost_per_night: +e.target.value || 0 })} data-testid="extra-night-cost" />
                  </div>
                  <div>
                    <label className="label-text">Unidad de cobro</label>
                    <select className="input-field" value={extraCfg.unit} onChange={(e) => setExtra({ unit: e.target.value })} data-testid="extra-night-unit">
                      <option value="per_person">Por persona</option>
                      <option value="per_room">Por habitación</option>
                      <option value="per_reservation">Por reservación completa</option>
                    </select>
                  </div>
                </div>
                {extraNightsSubtotal > 0 && (
                  <p className="text-sm font-medium text-emerald-800" data-testid="extra-nights-subtotal">
                    Noches extra: {extraNights} × {money(extraCfg.cost_per_night)} × {extraMult} = <b>{money(extraNightsSubtotal)}</b>
                  </p>
                )}
              </div>
            )}

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="label-text mb-0">Habitaciones del grupo</label>
                <div className="flex gap-2">
                  {['sencilla', 'doble', 'triple', 'cuadruple'].map((o) => (
                    <button key={o} type="button" onClick={() => addRoom(o)} className="btn-ghost text-xs"
                      data-testid={`add-room-${o}`}>+ {o}</button>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                {(form.pax.rooms || []).map((r, idx) => {
                  const price = hotel ? Number(hotel.prices_by_occupancy?.[r.ocupacion] || 0) : 0;
                  const pax = OCC_COUNT[r.ocupacion] * (r.count || 0);
                  return (
                    <div key={idx} className="grid grid-cols-12 gap-2 items-center rounded-xl border border-ink-100 p-3 bg-cream"
                      data-testid={`room-row-${idx}`}>
                      <div className="col-span-4">
                        <select className="input-field" value={r.ocupacion}
                          onChange={(e) => updateRoom(idx, { ocupacion: e.target.value })} data-testid={`room-occ-${idx}`}>
                          <option value="sencilla">Sencilla (1 pax)</option>
                          <option value="doble">Doble (2 pax)</option>
                          <option value="triple">Triple (3 pax)</option>
                          <option value="cuadruple">Cuádruple (4 pax)</option>
                        </select>
                      </div>
                      <div className="col-span-3">
                        <div className="flex items-center gap-2">
                          <button type="button" className="w-8 h-8 rounded-full bg-white border border-ink-200 hover:bg-brand-50"
                            onClick={() => updateRoom(idx, { count: Math.max(1, (r.count || 1) - 1) })} data-testid={`room-dec-${idx}`}>−</button>
                          <span className="font-display font-semibold text-lg w-8 text-center" data-testid={`room-count-${idx}`}>{r.count}</span>
                          <button type="button" className="w-8 h-8 rounded-full bg-white border border-ink-200 hover:bg-brand-50"
                            onClick={() => updateRoom(idx, { count: (r.count || 1) + 1 })} data-testid={`room-inc-${idx}`}>+</button>
                        </div>
                      </div>
                      <div className="col-span-4 text-xs text-ink-500">
                        {pax} pax · {price > 0 ? `$${(price * pax).toLocaleString('es-MX')} MXN` : ''}
                      </div>
                      <div className="col-span-1 text-right">
                        <button type="button" className="text-red-600 hover:text-red-800 text-xs"
                          onClick={() => removeRoom(idx)} data-testid={`room-remove-${idx}`}>✕</button>
                      </div>
                    </div>
                  );
                })}
                {(!form.pax.rooms || form.pax.rooms.length === 0) && (
                  <p className="text-ink-400 text-sm italic">Agrega al menos una habitación con los botones de arriba.</p>
                )}
              </div>
              {totalAdults > 0 && (
                <p className="text-xs text-ink-500 mt-2" data-testid="rooms-total">Total adultos: <b className="text-ink-900">{totalAdults}</b></p>
              )}
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div><label className="label-text">Menores (3-11 años)</label>
                <input type="number" min="0" className="input-field" value={form.pax.menores}
                  onChange={(e) => setForm((f) => ({ ...f, pax: { ...f.pax, menores: +e.target.value || 0 } }))} data-testid="pax-menores" /></div>
            </div>

            <div>
              <label className="label-text">Notas internas</label>
              <textarea rows="3" className="input-field" value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} data-testid="builder-notes" />
            </div>
          </div>
        )}

        {/* Step: Services (a la carte) */}
        {step === 3 && (
          <div className="space-y-4" data-testid="step-services-panel">
            <div>
              <h2 className="font-display text-xl font-semibold text-ink-900">Servicios a la carta</h2>
              <p className="text-ink-500 text-sm mt-1">Agrega tours, traslados, accesos o extras opcionales. Este paso es opcional.</p>
            </div>
            {services.length === 0 ? (
              <p className="text-ink-400 text-sm italic">No hay servicios en el catálogo. Pídele a un admin que los cree en la sección Servicios.</p>
            ) : (
              <div className="grid md:grid-cols-2 gap-3">
                {services.map((svc) => {
                  const selected = isServiceSelected(svc.id);
                  const sel = (form.services || []).find((s) => s.service_id === svc.id);
                  return (
                    <div key={svc.id}
                      className={`rounded-xl border p-4 transition-all ${selected ? 'border-brand-500 bg-brand-50' : 'border-ink-100 hover:border-brand-300'}`}
                      data-testid={`service-pick-${svc.id}`}>
                      <button type="button" className="w-full text-left" onClick={() => toggleService(svc)} data-testid={`service-toggle-${svc.id}`}>
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <span className="pill bg-white text-brand-500 text-xs capitalize">{svc.category}</span>
                            <p className="font-semibold text-ink-900 mt-1.5">{svc.name}</p>
                            {svc.description && <p className="text-xs text-ink-500 mt-0.5">{svc.description}</p>}
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 shrink-0 flex items-center justify-center ${selected ? 'bg-brand-500 border-brand-500' : 'border-ink-200'}`}>
                            {selected && <Check className="w-3 h-3 text-white" />}
                          </div>
                        </div>
                        <p className="font-display font-bold text-brand-500 mt-2">${Number(svc.public_price).toLocaleString('es-MX')} <span className="text-xs font-medium text-ink-400">{SERVICE_UNIT_ES[svc.unit || (svc.per_person ? 'per_person' : 'per_group')]}</span></p>
                      </button>
                      {selected && (
                        <div className="flex items-center gap-2 mt-3 pt-3 border-t border-brand-200">
                          <span className="text-xs text-ink-500">Cantidad</span>
                          <button type="button" className="w-7 h-7 rounded-full bg-white border border-ink-200 hover:bg-brand-50"
                            onClick={() => setServiceQty(svc.id, (sel?.qty || 1) - 1)} data-testid={`service-dec-${svc.id}`}>−</button>
                          <span className="font-semibold w-8 text-center" data-testid={`service-qty-${svc.id}`}>{sel?.qty || 1}</span>
                          <button type="button" className="w-7 h-7 rounded-full bg-white border border-ink-200 hover:bg-brand-50"
                            onClick={() => setServiceQty(svc.id, (sel?.qty || 1) + 1)} data-testid={`service-inc-${svc.id}`}>+</button>
                          <span className="text-xs text-ink-400 ml-auto">{money(Number(svc.public_price) * (sel?.qty || 1))}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {servicesSubtotal > 0 && (
              <div className="rounded-xl bg-mint-100 text-emerald-800 px-4 py-3 text-sm font-medium" data-testid="services-subtotal">
                Servicios seleccionados: {money(servicesSubtotal)}
              </div>
            )}
          </div>
        )}

        {/* Step: Review */}
        {step === 4 && (
          <div className="space-y-4" data-testid="step-review-panel">
            <h2 className="font-display text-xl font-semibold text-ink-900">Revisión</h2>
            <div className="grid md:grid-cols-2 gap-4 text-sm">
              <div className="rounded-xl border border-ink-100 p-4">
                <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">Cliente</p>
                <p className="font-semibold text-ink-900">{client?.name}</p>
                <p className="text-ink-500">{client?.channel}</p>
              </div>
              <div className="rounded-xl border border-ink-100 p-4">
                <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">Paquete</p>
                <p className="font-semibold text-ink-900">{pack?.name}</p>
                <p className="text-ink-500">{form.hotel_name}</p>
              </div>
              <div className="rounded-xl border border-ink-100 p-4">
                <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">Fechas</p>
                <p className="font-semibold text-ink-900">{formatDateEs(form.dates.start)} → {formatDateEs(form.dates.end)}</p>
                <p className="text-ink-500">{tripNights} noches{extraNights > 0 ? ` (${packNights} paquete + ${extraNights} extra)` : ''}</p>
              </div>
              <div className="rounded-xl border border-ink-100 p-4">
                <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">Pasajeros</p>
                <p className="font-semibold text-ink-900">{totalAdults} adultos · {form.pax.menores} menores</p>
                <p className="text-ink-500 text-xs mt-1">{(form.pax.rooms || []).map((r) => `${r.count} ${r.ocupacion}`).join(' · ')}</p>
              </div>
            </div>

            <div className="rounded-xl bg-gradient-to-br from-brand-500 to-accent text-white p-5" data-testid="builder-totals">
              {extraNightsSubtotal > 0 && (
                <div className="flex justify-between text-sm mb-1 opacity-90"><span>Noches extra ({extraNights})</span><span>{money(extraNightsSubtotal)}</span></div>
              )}
              {servicesSubtotal > 0 && (
                <div className="flex justify-between text-sm mb-1 opacity-90"><span>Servicios a la carta</span><span>{money(servicesSubtotal)}</span></div>
              )}
              <div className="flex justify-between text-sm"><span>Subtotal</span><span>{money(subtotal)}</span></div>
              {commissionRate > 0 && <div className="flex justify-between text-sm mt-1"><span>Comisión canal ({(commissionRate * 100).toFixed(0)}%)</span><span>- {money(commission)}</span></div>}
              <div className="border-t border-white/20 mt-3 pt-3 flex justify-between items-end">
                <span className="text-sm uppercase tracking-widest opacity-80">Total</span>
                <span className="font-display font-bold text-3xl">{money(total)}</span>
              </div>
            </div>
          </div>
        )}

        {/* Footer navigation */}
        <div className="flex items-center justify-between mt-8 pt-6 border-t border-ink-100">
          <button onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0} className="btn-ghost" data-testid="builder-back">
            <ArrowLeft className="w-4 h-4" /> Atrás
          </button>
          {step < STEPS.length - 1 ? (
            <button disabled={!canNext()} onClick={() => setStep((s) => s + 1)} className="btn-primary" data-testid="builder-next">
              Siguiente <ArrowRight className="w-4 h-4" />
            </button>
          ) : (
            <button disabled={loading} onClick={submit} className="btn-primary" data-testid="builder-submit">
              {loading ? 'Creando…' : <>Crear cotización <FileText className="w-4 h-4" /></>}
            </button>
          )}
        </div>
      </div>
    </AppShell>
  );
}
