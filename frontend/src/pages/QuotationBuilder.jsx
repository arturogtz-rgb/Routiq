import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { ArrowLeft, ArrowRight, Check, User, Package, CalendarDays, Calculator, FileText, Plus, Sparkles, AlertTriangle, Moon, Briefcase, Users, Wand2 } from 'lucide-react';
import { formatDateEs, nightsBetween, addDays, weekdayMon0, WEEKDAYS_ES } from '@/lib/dates';

const SERVICE_UNIT_ES = { per_person: 'por persona', per_group: 'por grupo', per_day: 'por día', per_access: 'por acceso' };
const OCC_COUNT = { sencilla: 1, doble: 2, triple: 3, cuadruple: 4 };

function money(v, c = 'MXN') { return `$${Number(v || 0).toLocaleString('es-MX')} ${c}`; }

const EMPTY_CONTACTS = { agency: { name: '', contact: '', email: '' }, traveler: { name: '', phone: '' } };

export default function QuotationBuilder() {
  const navigate = useNavigate();
  const { id } = useParams();
  const editing = !!id;
  const [search] = useSearchParams();
  const [step, setStep] = useState(0);
  const [clients, setClients] = useState([]);
  const [packages, setPackages] = useState([]);
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showClient, setShowClient] = useState(false);
  const [newClient, setNewClient] = useState({ name: '', phone: '', email: '', channel: 'directo' });
  const [aiPresLoading, setAiPresLoading] = useState(false);
  const [presTone, setPresTone] = useState('formal');
  const [company, setCompany] = useState(null);

  const [form, setForm] = useState({
    type: 'paquete',
    client_id: '',
    package_id: search.get('package') || '',
    hotel_name: '',
    dates: { start: '', end: '' },
    pax: { rooms: [{ ocupacion: 'doble', count: 1 }], menores: 0, adultos: 2 },
    services: [],
    extra_nights: { cost_per_night: 0, unit: 'per_reservation' },
    contacts: JSON.parse(JSON.stringify(EMPTY_CONTACTS)),
    notes: '',
    presentation_text: '',
  });

  useEffect(() => {
    (async () => {
      const [c, p, s, comp] = await Promise.all([api.get('/clients'), api.get('/packages'), api.get('/services'), api.get('/companies/me')]);
      setClients(c.data); setPackages(p.data); setServices(s.data); setCompany(comp.data);
      if (editing) {
        try {
          const { data: q } = await api.get(`/quotations/${id}`);
          setForm({
            type: q.type || 'paquete',
            client_id: q.client_id || '',
            package_id: q.package_id || '',
            hotel_name: q.hotel_selected || '',
            dates: q.dates || { start: '', end: '' },
            pax: { rooms: [], menores: 0, adultos: 2, ...(q.pax || {}) },
            services: q.services || [],
            extra_nights: q.extra_nights_cfg || { cost_per_night: 0, unit: 'per_reservation' },
            contacts: { ...JSON.parse(JSON.stringify(EMPTY_CONTACTS)), ...(q.contacts || {}) },
            notes: q.notes || '',
            presentation_text: q.presentation_text || '',
          });
        } catch (e) { setError(formatApiError(e)); }
        return;
      }
      if (form.package_id && !form.hotel_name) {
        const pack = p.data.find((x) => x.id === form.package_id);
        if (pack?.hotels?.[0]) setForm((f) => ({ ...f, hotel_name: pack.hotels[0].name }));
      }
    })();
  }, []); // eslint-disable-line

  const isServices = form.type === 'servicios';
  const pack = packages.find((p) => p.id === form.package_id);
  const hotel = pack?.hotels?.find((h) => h.name === form.hotel_name);
  const client = clients.find((c) => c.id === form.client_id);
  const isB2B = !!client && client.channel !== 'directo';

  const STEPS = isServices
    ? [
        { key: 'client', label: 'Cliente', icon: User },
        { key: 'servicios', label: 'Servicios', icon: Sparkles },
        { key: 'review', label: 'Revisión', icon: Calculator },
      ]
    : [
        { key: 'client', label: 'Cliente', icon: User },
        { key: 'package', label: 'Paquete', icon: Package },
        { key: 'dates', label: 'Fechas y pax', icon: CalendarDays },
        { key: 'services', label: 'Servicios', icon: Sparkles },
        { key: 'review', label: 'Revisión', icon: Calculator },
      ];
  const cur = STEPS[Math.min(step, STEPS.length - 1)].key;

  const margin = Number(company?.pricing_config?.margin_divisor) || 0.76;
  const commissions = company?.pricing_config?.commissions || {};
  const channel = client?.channel || 'directo';
  const commissionRate = client ? Number(commissions[channel] ?? 0) : 0;
  // Paquetes: catálogo guarda TARIFA NETA. Público = neto / divisor; el precio por
  // canal define lo que VE el cliente (directo/agencia=público, mayorista=público-comisión,
  // operador/Mayorista Preferencial=neto). No comisionable para mayorista/operador.
  const publicPrice = (net) => (margin > 0 ? (Number(net) || 0) / margin : (Number(net) || 0));
  const channelPrice = (net) => {
    const n = Number(net) || 0;
    if (n <= 0) return 0;
    const pub = publicPrice(n);
    if (channel === 'operador') return n;
    if (channel === 'mayorista') return pub * (1 - (Number(commissions.mayorista) || 0));
    return pub;
  };

  const rooms = form.pax.rooms || [];
  const roomsAdults = rooms.reduce((s, r) => s + OCC_COUNT[r.ocupacion] * (r.count || 0), 0);
  const totalAdults = isServices ? (Number(form.pax.adultos) || 0) : roomsAdults;
  const totalPax = totalAdults + (form.pax.menores || 0);
  const numRooms = rooms.reduce((s, r) => s + (r.count || 0), 0);

  const packNights = pack?.nights || 0;
  const tripNights = nightsBetween(form.dates.start, form.dates.end);
  const extraNights = isServices ? 0 : Math.max(0, tripNights - packNights);
  const extraCfg = form.extra_nights || { cost_per_night: 0, unit: 'per_reservation' };
  const extraMult = extraCfg.unit === 'per_person' ? totalPax : extraCfg.unit === 'per_room' ? numRooms : 1;
  const extraNightsSubtotal = extraNights > 0 ? channelPrice(Number(extraCfg.cost_per_night) || 0) * extraNights * extraMult : 0;

  const allowedDays = pack?.allowed_start_days || [];
  const specialDates = pack?.special_departure_dates || [];
  const hasDayRule = allowedDays.length > 0 || specialDates.length > 0;
  const startWeekday = form.dates.start ? weekdayMon0(form.dates.start) : null;
  const startInvalid = !isServices && !!form.dates.start && hasDayRule
    && !(allowedDays.includes(startWeekday) || specialDates.includes(form.dates.start));

  const serviceDefaultQty = (svc) => {
    const unit = svc.unit || (svc.per_person ? 'per_person' : 'per_group');
    if (unit === 'per_person' || unit === 'per_access') return Math.max(1, totalPax);
    if (unit === 'per_day') return Math.max(1, packNights || tripNights || 1);
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

  const effectiveSeason = (() => {
    if (!hotel) return { seasonId: null, seasonName: null };
    const ci = form.dates.start ? form.dates.start.slice(0, 10) : null;
    for (const s of (pack?.seasons || [])) {
      for (const r of (s.ranges || [])) {
        const st = (r.start || '').slice(0, 10); const en = (r.end || '').slice(0, 10);
        if (st && en && st <= ci && ci <= en) return { seasonId: s.id, seasonName: s.name };
      }
    }
    return { seasonId: null, seasonName: null };
  })();
  const priceFor = (occ) => {  // tarifa NETA del catálogo (con temporada si aplica)
    if (!hotel) return 0;
    const sp = effectiveSeason.seasonId ? (hotel.season_prices || {})[effectiveSeason.seasonId] : null;
    const v = sp ? sp[occ] : undefined;
    return (v !== undefined && v !== null && v !== '') ? Number(v) : Number(hotel.prices_by_occupancy?.[occ] || 0);
  };
  const minorNet = (() => {
    if (!hotel) return 0;
    const sp = effectiveSeason.seasonId ? (hotel.season_prices || {})[effectiveSeason.seasonId] : null;
    const v = sp ? sp.minor_price : undefined;
    return (v !== undefined && v !== null && v !== '') ? Number(v) : Number(hotel.minor_price || 0);
  })();

  const packageSubtotal = (() => {
    if (isServices || !hotel) return 0;
    let s = extraNightsSubtotal;
    for (const r of rooms) {
      const net = priceFor(r.ocupacion);
      if (net <= 0) continue;  // precio 0 = no disponible
      s += channelPrice(net) * OCC_COUNT[r.ocupacion] * (r.count || 0);
    }
    if (minorNet > 0) s += channelPrice(minorNet) * (form.pax.menores || 0);
    return s;
  })();
  const subtotal = isServices ? servicesSubtotal : (packageSubtotal + servicesSubtotal);
  const commission = Math.round(servicesSubtotal * commissionRate * 100) / 100;  // sólo servicios
  const total = subtotal - commission;
  const priceNote = (!isServices && hotel && (channel === 'mayorista' || channel === 'operador')) ? 'Precio neto no comisionable' : '';

  const isServiceSelected = (id) => (form.services || []).some((s) => s.service_id === id);
  const toggleService = (svc) => setForm((f) => {
    const exists = (f.services || []).some((s) => s.service_id === svc.id);
    if (exists) return { ...f, services: f.services.filter((s) => s.service_id !== svc.id) };
    return { ...f, services: [...(f.services || []), { service_id: svc.id, qty: serviceDefaultQty(svc) }] };
  });
  const setServiceQty = (id, qty) => setForm((f) => ({
    ...f, services: f.services.map((s) => s.service_id === id ? { ...s, qty: Math.max(1, qty) } : s),
  }));

  const setStart = (start) => setForm((f) => {
    const nights = packages.find((p) => p.id === f.package_id)?.nights || 0;
    const end = start && nights > 0 ? addDays(start, nights) : f.dates.end;
    return { ...f, dates: { start, end } };
  });
  const setEnd = (end) => setForm((f) => ({ ...f, dates: { ...f.dates, end } }));
  const setExtra = (patch) => setForm((f) => ({ ...f, extra_nights: { ...f.extra_nights, ...patch } }));

  const setType = (type) => { if (editing) return; setForm((f) => ({ ...f, type })); setStep(0); };

  const setContact = (group, key, val) => setForm((f) => ({
    ...f, contacts: { ...f.contacts, [group]: { ...f.contacts[group], [key]: val } },
  }));

  const selectClient = (c) => setForm((f) => {
    const next = { ...f, client_id: c.id };
    // Prefill agency block from the client record when it's a B2B channel and empty
    if (c.channel !== 'directo' && !f.contacts.agency.name) {
      next.contacts = { ...f.contacts, agency: { name: c.name || '', contact: c.phone || '', email: c.email || '' } };
    }
    return next;
  });

  const goToStep = (i) => setStep(i);

  const addRoom = (ocupacion) => setForm((f) => ({ ...f, pax: { ...f.pax, rooms: [...(f.pax.rooms || []), { ocupacion, count: 1 }] } }));
  const updateRoom = (idx, patch) => setForm((f) => ({ ...f, pax: { ...f.pax, rooms: f.pax.rooms.map((r, i) => i === idx ? { ...r, ...patch } : r) } }));
  const removeRoom = (idx) => setForm((f) => ({ ...f, pax: { ...f.pax, rooms: f.pax.rooms.filter((_, i) => i !== idx) } }));

  const canNext = () => {
    if (cur === 'client') return !!form.client_id;
    if (cur === 'package') return !!form.package_id && !!form.hotel_name;
    if (cur === 'dates') return form.dates.start && form.dates.end && rooms.length > 0 && totalAdults > 0;
    if (cur === 'servicios') return totalAdults > 0 && (form.services || []).length > 0;
    return true;
  };

  const handleCreateClient = async () => {
    setError('');
    try {
      const { data } = await api.post('/clients', newClient);
      setClients((cs) => [...cs, data]);
      selectClient(data);
      setShowClient(false);
      setNewClient({ name: '', phone: '', email: '', channel: 'directo' });
    } catch (e) { setError(formatApiError(e)); }
  };

  const genPresentation = async () => {
    setError(''); setAiPresLoading(true);
    try {
      const pkg = packages.find((p) => p.id === form.package_id);
      const title = isServices ? 'Servicios a la carta' : (pkg?.name || '');
      const { data } = await api.post('/ai/presentation', {
        client_name: client?.name || '', title,
        date_start: form.dates.start || '', date_end: form.dates.end || '',
        adultos: totalAdults || 0, menores: form.pax.menores || 0, tone: presTone,
      });
      if (data.text) setForm((f) => ({ ...f, presentation_text: data.text }));
    } catch (e) { setError(formatApiError(e)); }
    finally { setAiPresLoading(false); }
  };

  const submit = async () => {
    setError(''); setLoading(true);
    try {
      const contacts = isB2B ? form.contacts : null;
      if (editing) {
        const patch = {
          dates: form.dates,
          pax: isServices ? { adultos: totalAdults, menores: form.pax.menores || 0, rooms: [] } : form.pax,
          services: form.services,
          extra_nights: form.extra_nights,
          contacts,
          notes: form.notes,
          presentation_text: form.presentation_text || '',
        };
        if (!isServices) patch.hotel_name = form.hotel_name;
        await api.patch(`/quotations/${id}`, patch);
        navigate(`/app/quotations/${id}`);
        return;
      }
      const payload = {
        type: form.type,
        client_id: form.client_id,
        services: form.services,
        notes: form.notes,
        contacts,
        presentation_text: form.presentation_text || '',
        from_request: search.get('lead') || undefined,
      };
      if (isServices) {
        payload.pax = { adultos: totalAdults, menores: form.pax.menores || 0, rooms: [] };
        payload.dates = form.dates;
      } else {
        payload.package_id = form.package_id;
        payload.hotel_name = form.hotel_name;
        payload.pax = form.pax;
        payload.extra_nights = form.extra_nights;
        let dates = form.dates;
        if (dates.start && dates.end && dates.start > dates.end) dates = { start: dates.end, end: dates.start };
        payload.dates = dates;
      }
      const { data } = await api.post('/quotations', payload);
      navigate(`/app/quotations/${data.id}`);
    } catch (e) { setError(formatApiError(e)); }
    finally { setLoading(false); }
  };

  const renderServicesGrid = () => (
    services.length === 0 ? (
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
    )
  );

  return (
    <AppShell>
      <div className="mb-6 flex items-center justify-between">
        <Link to={editing ? `/app/quotations/${id}` : '/app/quotations'} className="btn-ghost text-sm" data-testid="back-to-quotations">
          <ArrowLeft className="w-4 h-4" /> Volver
        </Link>
      </div>
      <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight mb-2">
        {editing ? 'Editar cotización' : 'Nueva cotización'}
      </h1>
      <p className="text-ink-500 mb-6">
        {editing ? 'Modifica fechas, habitaciones, servicios y contactos. Los totales se recalculan automáticamente.' : 'Construye una cotización. Navega libremente entre los pasos.'}
      </p>

      {/* Type selector */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6 max-w-3xl">
        <button type="button" onClick={() => setType('paquete')} disabled={editing}
          className={`rounded-xl border p-4 text-left transition-all ${form.type === 'paquete' ? 'border-brand-500 bg-brand-50' : 'border-ink-100 hover:border-brand-300'} ${editing ? 'opacity-60 cursor-not-allowed' : ''}`}
          data-testid="type-paquete">
          <Package className="w-5 h-5 text-brand-500 mb-1" />
          <p className="font-semibold text-ink-900">Paquete armado</p>
          <p className="text-xs text-ink-500">Hospedaje + itinerario con motor de precios.</p>
        </button>
        <button type="button" onClick={() => setType('servicios')} disabled={editing}
          className={`rounded-xl border p-4 text-left transition-all ${form.type === 'servicios' ? 'border-brand-500 bg-brand-50' : 'border-ink-100 hover:border-brand-300'} ${editing ? 'opacity-60 cursor-not-allowed' : ''}`}
          data-testid="type-servicios">
          <Sparkles className="w-5 h-5 text-brand-500 mb-1" />
          <p className="font-semibold text-ink-900">Servicios a la carta</p>
          <p className="text-xs text-ink-500">Tours, traslados y extras sin paquete base.</p>
        </button>
        <button type="button" onClick={() => !editing && navigate('/app/quotations/new/custom')} disabled={editing}
          className={`rounded-xl border p-4 text-left transition-all border-ink-100 hover:border-amber-300 ${editing ? 'opacity-60 cursor-not-allowed' : ''}`}
          data-testid="type-personalizado">
          <Wand2 className="w-5 h-5 text-amber-600 mb-1" />
          <p className="font-semibold text-ink-900">Programa personalizado</p>
          <p className="text-xs text-ink-500">Cotización a medida desde cero, sin catálogo.</p>
        </button>
      </div>

      {/* Stepper */}
      <div className={`grid gap-2 mb-8`} style={{ gridTemplateColumns: `repeat(${STEPS.length}, minmax(0, 1fr))` }}>
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
        {cur === 'client' && (
          <div className="space-y-4" data-testid="step-client-panel">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-xl font-semibold text-ink-900">Selecciona cliente</h2>
              {!editing && (
                <button className="btn-secondary text-sm" onClick={() => setShowClient((v) => !v)} data-testid="toggle-new-client">
                  <Plus className="w-4 h-4" /> Nuevo cliente
                </button>
              )}
            </div>
            {showClient && !editing && (
              <div className="rounded-xl border border-ink-100 bg-cream p-4 space-y-3" data-testid="new-client-form">
                <div className="grid md:grid-cols-2 gap-3">
                  <div><label className="label-text">Nombre</label><input className="input-field" value={newClient.name} onChange={(e) => setNewClient((x) => ({ ...x, name: e.target.value }))} data-testid="newclient-name" /></div>
                  <div><label className="label-text">Canal</label>
                    <select className="input-field" value={newClient.channel} onChange={(e) => setNewClient((x) => ({ ...x, channel: e.target.value }))} data-testid="newclient-channel">
                      <option value="directo">Directo</option>
                      <option value="agencia">Agencia</option>
                      <option value="mayorista">Mayorista</option>
                      <option value="operador">Mayorista Preferencial</option>
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
                <button key={c.id} onClick={() => !editing && selectClient(c)} disabled={editing}
                  className={`text-left rounded-xl border p-4 transition-all ${form.client_id === c.id ? 'border-brand-500 bg-brand-50' : 'border-ink-100 hover:border-brand-300'} ${editing && form.client_id !== c.id ? 'hidden' : ''}`}
                  data-testid={`client-option-${c.id}`}>
                  <p className="font-semibold text-ink-900">{c.name}</p>
                  <p className="text-xs text-ink-500 mt-1">{c.email} · {c.phone}</p>
                  <span className="pill bg-brand-50 text-brand-500 mt-2">{c.channel}</span>
                </button>
              ))}
              {clients.length === 0 && <p className="text-ink-400 text-sm">No hay clientes. Crea uno.</p>}
            </div>

            {/* Agency + final traveler contacts for B2B */}
            {isB2B && (
              <div className="grid md:grid-cols-2 gap-4 pt-4 border-t border-ink-100" data-testid="contacts-block">
                <div className="rounded-xl border border-ink-100 p-4 space-y-3">
                  <p className="font-semibold text-ink-900 flex items-center gap-2"><Briefcase className="w-4 h-4 text-brand-500" /> Agencia / Vendedor</p>
                  <div><label className="label-text">Nombre de la agencia</label><input className="input-field" value={form.contacts.agency.name} onChange={(e) => setContact('agency', 'name', e.target.value)} data-testid="contact-agency-name" /></div>
                  <div><label className="label-text">Contacto / Vendedor</label><input className="input-field" value={form.contacts.agency.contact} onChange={(e) => setContact('agency', 'contact', e.target.value)} data-testid="contact-agency-contact" /></div>
                  <div><label className="label-text">Correo</label><input className="input-field" value={form.contacts.agency.email} onChange={(e) => setContact('agency', 'email', e.target.value)} data-testid="contact-agency-email" /></div>
                </div>
                <div className="rounded-xl border border-ink-100 p-4 space-y-3">
                  <p className="font-semibold text-ink-900 flex items-center gap-2"><Users className="w-4 h-4 text-brand-500" /> Cliente final / Turista</p>
                  <div><label className="label-text">Nombre completo</label><input className="input-field" value={form.contacts.traveler.name} onChange={(e) => setContact('traveler', 'name', e.target.value)} data-testid="contact-traveler-name" /></div>
                  <div><label className="label-text">Teléfono directo</label><input className="input-field" value={form.contacts.traveler.phone} onChange={(e) => setContact('traveler', 'phone', e.target.value)} data-testid="contact-traveler-phone" /></div>
                  <p className="text-xs text-ink-400">Puedes tener varias reservas de la misma agencia con turistas distintos.</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Step: Package */}
        {cur === 'package' && (
          <div className="space-y-4" data-testid="step-package-panel">
            <h2 className="font-display text-xl font-semibold text-ink-900">Selecciona paquete y hotel</h2>
            <div className="grid md:grid-cols-2 gap-3">
              {packages.map((p) => (
                <button key={p.id} onClick={() => !editing && setForm((f) => ({ ...f, package_id: p.id, hotel_name: p.hotels?.[0]?.name || '' }))} disabled={editing}
                  className={`text-left rounded-xl border p-4 transition-all ${form.package_id === p.id ? 'border-brand-500 bg-brand-50' : 'border-ink-100 hover:border-brand-300'} ${editing && form.package_id !== p.id ? 'hidden' : ''}`}
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
                          <div key={k}>
                            <span className="text-ink-400 text-xs uppercase tracking-wider">{k}</span>{' '}
                            <span className="font-semibold">${Number(v).toLocaleString('es-MX')}</span>
                            {Number(v) > 0 && <span className="text-[10px] text-emerald-600 ml-1">Púb ${Number(publicPrice(v)).toLocaleString('es-MX', { maximumFractionDigits: 0 })}</span>}
                          </div>
                        ))}
                      </div>
                      <p className="text-[10px] text-ink-400 mt-1.5">Tarifa neta · Público = neto / {margin}</p>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Step: Dates & Pax */}
        {cur === 'dates' && (
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
                {rooms.map((r, idx) => {
                  const net = priceFor(r.ocupacion);
                  const pub = publicPrice(net);
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
                      <div className="col-span-4 text-xs text-ink-500" data-testid={`room-price-${idx}`}>
                        {pax} pax
                        {net > 0
                          ? <> · <span className="text-ink-400">Neto</span> ${(net * pax).toLocaleString('es-MX')} · <span className="text-emerald-700 font-medium">Público</span> ${(pub * pax).toLocaleString('es-MX', { maximumFractionDigits: 0 })}</>
                          : <span className="text-amber-600"> · no disponible</span>}
                      </div>
                      <div className="col-span-1 text-right">
                        <button type="button" className="text-red-600 hover:text-red-800 text-xs"
                          onClick={() => removeRoom(idx)} data-testid={`room-remove-${idx}`}>✕</button>
                      </div>
                    </div>
                  );
                })}
                {rooms.length === 0 && (
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

        {/* Step: Services (paquete flow) */}
        {cur === 'services' && (
          <div className="space-y-4" data-testid="step-services-panel">
            <div>
              <h2 className="font-display text-xl font-semibold text-ink-900">Servicios a la carta</h2>
              <p className="text-ink-500 text-sm mt-1">Agrega tours, traslados, accesos o extras opcionales. Este paso es opcional.</p>
            </div>
            {renderServicesGrid()}
            {servicesSubtotal > 0 && (
              <div className="rounded-xl bg-mint-100 text-emerald-800 px-4 py-3 text-sm font-medium" data-testid="services-subtotal">
                Servicios seleccionados: {money(servicesSubtotal)}
              </div>
            )}
          </div>
        )}

        {/* Step: Servicios (servicios-only flow) */}
        {cur === 'servicios' && (
          <div className="space-y-5" data-testid="step-servicios-panel">
            <div>
              <h2 className="font-display text-xl font-semibold text-ink-900">Servicios y personas</h2>
              <p className="text-ink-500 text-sm mt-1">Cotiza tours, traslados y extras sin paquete base. Indica el número de personas.</p>
            </div>
            <div className="grid md:grid-cols-3 gap-4">
              <div><label className="label-text">Número de personas</label>
                <input type="number" min="1" className="input-field" value={form.pax.adultos || 0}
                  onChange={(e) => setForm((f) => ({ ...f, pax: { ...f.pax, adultos: +e.target.value || 0 } }))} data-testid="servicios-personas" /></div>
              <div><label className="label-text">Fecha inicio (opcional)</label>
                <input type="date" className="input-field" value={form.dates.start} onChange={(e) => setForm((f) => ({ ...f, dates: { ...f.dates, start: e.target.value } }))} data-testid="servicios-date-start" /></div>
              <div><label className="label-text">Fecha fin (opcional)</label>
                <input type="date" className="input-field" value={form.dates.end} onChange={(e) => setForm((f) => ({ ...f, dates: { ...f.dates, end: e.target.value } }))} data-testid="servicios-date-end" /></div>
            </div>
            {renderServicesGrid()}
            {servicesSubtotal > 0 && (
              <div className="rounded-xl bg-mint-100 text-emerald-800 px-4 py-3 text-sm font-medium" data-testid="services-subtotal">
                Servicios seleccionados: {money(servicesSubtotal)}
              </div>
            )}
            <div>
              <label className="label-text">Notas internas</label>
              <textarea rows="3" className="input-field" value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} data-testid="builder-notes-servicios" />
            </div>
          </div>
        )}

        {/* Step: Review */}
        {cur === 'review' && (
          <div className="space-y-4" data-testid="step-review-panel">
            <h2 className="font-display text-xl font-semibold text-ink-900">Revisión</h2>
            <div className="rounded-xl border border-brand-100 bg-brand-50/40 p-4" data-testid="presentation-block">
              <div className="flex items-center justify-between mb-2">
                <label className="label-text mb-0">Texto de presentación (aparece al inicio del PDF y del enlace)</label>
                <div className="flex items-center gap-2">
                  <select className="input-field text-xs w-auto py-1.5" value={presTone} onChange={(e) => setPresTone(e.target.value)} data-testid="tone-select">
                    <option value="formal">Tono: Formal</option>
                    <option value="cercano">Tono: Cercano</option>
                    <option value="premium">Tono: Premium</option>
                  </select>
                  <button type="button" className="btn-ghost text-xs border border-brand-200 text-brand-600" onClick={genPresentation} disabled={aiPresLoading} data-testid="ai-presentation-btn">
                    <Sparkles className="w-3.5 h-3.5" /> {aiPresLoading ? 'Generando…' : 'Generar con IA'}
                  </button>
                </div>
              </div>
              <textarea rows="4" className="input-field" value={form.presentation_text} placeholder="Estimada/o [nombre], a continuación le presento la cotización para su viaje…"
                onChange={(e) => setForm((f) => ({ ...f, presentation_text: e.target.value }))} data-testid="presentation-input" />
            </div>
            <div className="grid md:grid-cols-2 gap-4 text-sm">
              <div className="rounded-xl border border-ink-100 p-4">
                <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">Cliente</p>
                <p className="font-semibold text-ink-900">{client?.name}</p>
                <p className="text-ink-500">{client?.channel}</p>
              </div>
              <div className="rounded-xl border border-ink-100 p-4">
                <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">{isServices ? 'Tipo' : 'Paquete'}</p>
                <p className="font-semibold text-ink-900">{isServices ? 'Servicios a la carta' : pack?.name}</p>
                {!isServices && <p className="text-ink-500">{form.hotel_name}</p>}
              </div>
              {!isServices && (
                <>
                  <div className="rounded-xl border border-ink-100 p-4">
                    <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">Fechas</p>
                    <p className="font-semibold text-ink-900">{formatDateEs(form.dates.start)} → {formatDateEs(form.dates.end)}</p>
                    <p className="text-ink-500">{tripNights} noches{extraNights > 0 ? ` (${packNights} paquete + ${extraNights} extra)` : ''}</p>
                  </div>
                  <div className="rounded-xl border border-ink-100 p-4">
                    <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">Pasajeros</p>
                    <p className="font-semibold text-ink-900">{totalAdults} adultos · {form.pax.menores} menores</p>
                    <p className="text-ink-500 text-xs mt-1">{rooms.map((r) => `${r.count} ${r.ocupacion}`).join(' · ')}</p>
                  </div>
                </>
              )}
              {isServices && (
                <div className="rounded-xl border border-ink-100 p-4">
                  <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">Personas</p>
                  <p className="font-semibold text-ink-900">{totalAdults} persona(s)</p>
                  {(form.dates.start || form.dates.end) && <p className="text-ink-500 text-xs mt-1">{formatDateEs(form.dates.start)} → {formatDateEs(form.dates.end)}</p>}
                </div>
              )}
              {isB2B && (
                <div className="rounded-xl border border-ink-100 p-4 md:col-span-2" data-testid="review-contacts">
                  <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">Contactos</p>
                  <p className="text-ink-700"><b>Agencia:</b> {form.contacts.agency.name || '—'} · {form.contacts.agency.email}</p>
                  <p className="text-ink-700"><b>Turista:</b> {form.contacts.traveler.name || '—'} · {form.contacts.traveler.phone}</p>
                </div>
              )}
            </div>

            <div className="rounded-xl bg-gradient-to-br from-brand-500 to-accent text-white p-5" data-testid="builder-totals">
              {extraNightsSubtotal > 0 && (
                <div className="flex justify-between text-sm mb-1 opacity-90"><span>Noches extra ({extraNights})</span><span>{money(extraNightsSubtotal)}</span></div>
              )}
              {servicesSubtotal > 0 && (
                <div className="flex justify-between text-sm mb-1 opacity-90"><span>Servicios a la carta</span><span>{money(servicesSubtotal)}</span></div>
              )}
              <div className="flex justify-between text-sm"><span>Subtotal</span><span>{money(subtotal)}</span></div>
              {commission > 0 && <div className="flex justify-between text-sm mt-1"><span>Comisión canal servicios ({(commissionRate * 100).toFixed(0)}%)</span><span>- {money(commission)}</span></div>}
              <div className="border-t border-white/20 mt-3 pt-3 flex justify-between items-end">
                <span className="text-sm uppercase tracking-widest opacity-80">Total</span>
                <span className="font-display font-bold text-3xl">{money(total)}</span>
              </div>
              {priceNote && <p className="text-xs opacity-80 mt-2" data-testid="builder-price-note">{priceNote}</p>}
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
              {loading ? 'Guardando…' : <>{editing ? 'Guardar cambios' : 'Crear cotización'} <FileText className="w-4 h-4" /></>}
            </button>
          )}
        </div>
      </div>
    </AppShell>
  );
}
