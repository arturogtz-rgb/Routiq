import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { ArrowLeft, ArrowRight, Check, User, Wand2, ListChecks, CalendarRange, Calculator, Plus, Trash2, Briefcase, Users, FileText, Sparkles, Save, BookmarkPlus } from 'lucide-react';
import { formatDateEs, nightsBetween } from '@/lib/dates';
import { UNIT_ES, CATEGORIES, EMPTY_CONTACTS, money, StringList } from './custom-builder/constants';
import { CustomItemCard } from './custom-builder/CustomItemCard';

export default function CustomQuotationBuilder() {
  const navigate = useNavigate();
  const { id } = useParams();
  const editing = !!id;
  const [search] = useSearchParams();
  const [step, setStep] = useState(0);
  const [clients, setClients] = useState([]);
  const [company, setCompany] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showClient, setShowClient] = useState(false);
  const [newClient, setNewClient] = useState({ name: '', phone: '', email: '', channel: 'directo' });
  const [saveTplOpen, setSaveTplOpen] = useState(false);
  const [tplName, setTplName] = useState('');
  const [savingTpl, setSavingTpl] = useState(false);
  const [tplMsg, setTplMsg] = useState('');
  const [aiPresLoading, setAiPresLoading] = useState(false);
  const [presTone, setPresTone] = useState('formal');

  const [form, setForm] = useState({
    client_id: '',
    executive_id: '',
    custom_title: '',
    dates: { start: '', end: '' },
    pax: { adultos: 2, menores: 0 },
    custom_nights: 0,
    custom_rooms: 1,
    custom_items: [],
    custom_itinerary: [],
    custom_includes: [],
    custom_excludes: [],
    presentation_text: '',
    important_info: '',
    show_price_breakdown: true,
    contacts: JSON.parse(JSON.stringify(EMPTY_CONTACTS)),
    notes: '',
  });

  useEffect(() => {
    (async () => {
      const [c, comp, t] = await Promise.all([api.get('/clients'), api.get('/companies/me'), api.get('/templates')]);
      setClients(c.data); setCompany(comp.data); setTemplates(t.data || []);
      if (editing) {
        try {
          const { data: q } = await api.get(`/quotations/${id}`);
          setForm({
            client_id: q.client_id || '',
            executive_id: q.executive_id || '',
            custom_title: q.custom_title || '',
            dates: q.dates || { start: '', end: '' },
            pax: { adultos: q.pax?.adultos || 0, menores: q.pax?.menores || 0 },
            custom_nights: q.custom_nights || 0,
            custom_rooms: q.custom_rooms || 1,
            custom_items: (q.custom_items || []).map((it) => ({ ...it })),
            custom_itinerary: (q.custom_itinerary || []).map((d) => ({ ...d })),
            custom_includes: q.custom_includes || [],
            custom_excludes: q.custom_excludes || [],
            presentation_text: q.presentation_text || '',
            important_info: q.important_info || '',
            show_price_breakdown: q.show_price_breakdown !== false,
            contacts: { ...JSON.parse(JSON.stringify(EMPTY_CONTACTS)), ...(q.contacts || {}) },
            notes: q.notes || '',
          });
        } catch (e) { setError(formatApiError(e)); }
        return;
      }
      const tplId = search.get('template');
      if (tplId) {
        const tpl = (t.data || []).find((x) => x.id === tplId);
        if (tpl) applyTemplate(tpl);
      }
    })();
  }, []); // eslint-disable-line

  const applyTemplate = (tpl) => setForm((f) => ({
    ...f,
    custom_title: tpl.custom_title || tpl.name || f.custom_title,
    pax: { adultos: tpl.pax_default?.adultos || f.pax.adultos, menores: tpl.pax_default?.menores || 0 },
    custom_nights: tpl.custom_nights || 0,
    custom_rooms: tpl.custom_rooms || 1,
    custom_items: (tpl.custom_items || []).map((it) => ({ ...it })),
    custom_itinerary: (tpl.custom_itinerary || []).map((d) => ({ ...d })),
    custom_includes: tpl.custom_includes || [],
    custom_excludes: tpl.custom_excludes || [],
  }));

  const saveAsTemplate = async () => {
    setError(''); setTplMsg(''); setSavingTpl(true);
    try {
      await api.post('/templates', {
        name: tplName.trim(),
        custom_title: form.custom_title.trim(),
        custom_items: form.custom_items.map((it) => ({ category: it.category, name: it.name, description: it.description || '', net_price: Number(it.net_price) || 0, price_type: it.price_type || 'neto', unit: it.unit, qty: Number(it.qty) || 0 })),
        custom_itinerary: form.custom_itinerary.map((d, i) => ({ day: i + 1, title: d.title || '', description: d.description || '' })),
        custom_includes: form.custom_includes.filter((x) => (x || '').trim()),
        custom_excludes: form.custom_excludes.filter((x) => (x || '').trim()),
        custom_nights: Number(form.custom_nights) || 0,
        custom_rooms: Number(form.custom_rooms) || 0,
        pax_default: { adultos: Number(form.pax.adultos) || 0, menores: Number(form.pax.menores) || 0 },
      });
      const t = await api.get('/templates'); setTemplates(t.data || []);
      setSaveTplOpen(false); setTplName('');
      setTplMsg('✓ Plantilla guardada. Podrás reutilizarla desde el catálogo.');
      setTimeout(() => setTplMsg(''), 4000);
    } catch (e) { setError(formatApiError(e)); }
    finally { setSavingTpl(false); }
  };

  const client = clients.find((c) => c.id === form.client_id);
  const isB2B = !!client && client.channel !== 'directo';
  const margin = Number(company?.pricing_config?.margin_divisor) || 0.76;
  const currency = company?.pricing_config?.currency || 'MXN';
  const commissionRate = (() => {
    if (!client) return 0;
    return Number(company?.pricing_config?.commissions?.[client.channel] ?? 0);
  })();

  const totalPax = (Number(form.pax.adultos) || 0) + (Number(form.pax.menores) || 0);
  const nights = nightsBetween(form.dates.start, form.dates.end) || Number(form.custom_nights) || 0;
  const rooms = Number(form.custom_rooms) || 0;

  const defaultQty = (unit) => {
    if (unit === 'per_person') return Math.max(1, totalPax);
    if (unit === 'per_night' || unit === 'per_day') return Math.max(1, nights);
    if (unit === 'per_room') return Math.max(1, rooms);
    return 1;
  };
  const channel = client?.channel || 'directo';
  const commissions = company?.pricing_config?.commissions || {};
  const publicPrice = (net) => (margin > 0 ? Math.round((Number(net) || 0) / margin * 100) / 100 : Number(net) || 0);
  // Precio que paga el cliente por unidad según el tipo de precio del concepto:
  //  - 'publico': el monto ingresado YA es público (lógica de servicios, comisionable).
  //  - 'neto': monto neto -> público=neto/divisor -> precio por canal (no comisionable).
  const unitPriceFor = (it) => {
    const amt = Number(it.net_price) || 0;
    if ((it.price_type || 'neto') === 'publico') return Math.round(amt * 100) / 100;
    const pub = publicPrice(amt);
    if (channel === 'operador') return Math.round(amt * 100) / 100;
    if (channel === 'mayorista') return Math.round(pub * (1 - (Number(commissions.mayorista) || 0)) * 100) / 100;
    return pub;
  };
  const itemSubtotal = (it) => {
    const base = unitPriceFor(it) * (Number(it.qty) || 0);
    const n = Number(it.nights) || 0;
    if (it.category === 'hospedaje' && n > 0) return base * n;
    return base;
  };

  const publicoSubtotal = form.custom_items.filter((it) => (it.price_type || 'neto') === 'publico').reduce((s, it) => s + itemSubtotal(it), 0);
  const subtotal = form.custom_items.reduce((s, it) => s + itemSubtotal(it), 0);
  const commission = Math.round(publicoSubtotal * commissionRate * 100) / 100;  // sólo conceptos de precio público
  const total = subtotal - commission;
  const hasNeto = form.custom_items.some((it) => (it.price_type || 'neto') !== 'publico');
  const priceNote = (hasNeto && (channel === 'mayorista' || channel === 'operador')) ? 'Precio neto no comisionable' : '';

  const STEPS = [
    { key: 'client', label: 'Cliente', icon: User },
    { key: 'program', label: 'Programa', icon: CalendarRange },
    { key: 'items', label: 'Conceptos', icon: Wand2 },
    { key: 'itinerary', label: 'Itinerario', icon: ListChecks },
    { key: 'review', label: 'Revisión', icon: Calculator },
  ];
  const cur = STEPS[Math.min(step, STEPS.length - 1)].key;

  // --- mutators ---
  const setContact = (group, key, val) => setForm((f) => ({ ...f, contacts: { ...f.contacts, [group]: { ...f.contacts[group], [key]: val } } }));
  const selectClient = (c) => setForm((f) => {
    const next = { ...f, client_id: c.id, executive_id: '' };
    const execs = c.executives || [];
    if (execs.length > 0) {
      // Empresa con ejecutivos: la agencia se llena al elegir el ejecutivo.
      next.contacts = { ...f.contacts, agency: { name: c.name || '', contact: '', email: '', phone: '' } };
    } else if (c.channel !== 'directo' && !f.contacts.agency.name) {
      // Empresa sin ejecutivos (legacy): prellenar agencia con datos generales.
      next.contacts = { ...f.contacts, agency: { name: c.name || '', contact: c.phone || '', email: c.email || '', phone: c.phone || '' } };
    }
    return next;
  });
  const selectExecutive = (ex) => setForm((f) => ({
    ...f, executive_id: ex.id,
    contacts: { ...f.contacts, agency: { name: (clients.find((c) => c.id === f.client_id) || {}).name || '', contact: ex.name || '', email: ex.email || '', phone: ex.phone || '' } },
  }));
  const handleCreateClient = async () => {
    setError('');
    try {
      const { data } = await api.post('/clients', newClient);
      setClients((cs) => [...cs, data]); selectClient(data);
      setShowClient(false); setNewClient({ name: '', phone: '', email: '', channel: 'directo' });
    } catch (e) { setError(formatApiError(e)); }
  };

  const addItem = (category) => setForm((f) => ({
    ...f, custom_items: [...f.custom_items, {
      category, name: '', description: '', net_price: 0, price_type: 'neto',
      unit: category === 'hospedaje' ? 'per_night' : 'per_person',
      qty: category === 'hospedaje' ? 1 : defaultQty('per_person'),
      service_date: '', start_time: '', end_time: '', checkin: '', checkout: '', nights: 0,
    }],
  }));
  const updateItem = (idx, patch) => setForm((f) => ({
    ...f, custom_items: f.custom_items.map((it, i) => {
      if (i !== idx) return it;
      let next = { ...it, ...patch };
      // Cambio de categoría: ajustar unidad por defecto y limpiar campos no aplicables.
      if (patch.category && patch.category !== it.category) {
        if (patch.category === 'hospedaje') { next.unit = 'per_night'; next.start_time = ''; next.end_time = ''; }
        else { next.checkin = ''; next.checkout = ''; next.nights = 0; if (it.unit === 'per_night') next.unit = 'per_person'; }
        if (patch.category === 'tour' || patch.category === 'acceso') next.end_time = '';
        if (patch.category === 'acceso') next.start_time = '';
      }
      // Hospedaje: las noches se autocalculan por check-in/out; la cantidad (habitaciones/personas) es independiente y editable.
      if (next.category === 'hospedaje' && (patch.checkin !== undefined || patch.checkout !== undefined)) {
        next.nights = (next.checkin && next.checkout) ? Math.max(0, nightsBetween(next.checkin, next.checkout)) : 0;
      }
      if (patch.unit && patch.qty === undefined && next.category !== 'hospedaje') next.qty = defaultQty(patch.unit);
      return next;
    }),
  }));
  const removeItem = (idx) => setForm((f) => ({ ...f, custom_items: f.custom_items.filter((_, i) => i !== idx) }));

  const addDay = () => setForm((f) => ({ ...f, custom_itinerary: [...f.custom_itinerary, { day: f.custom_itinerary.length + 1, title: '', description: '' }] }));
  const updateDay = (idx, patch) => setForm((f) => ({ ...f, custom_itinerary: f.custom_itinerary.map((d, i) => i === idx ? { ...d, ...patch } : d) }));
  const removeDay = (idx) => setForm((f) => ({ ...f, custom_itinerary: f.custom_itinerary.filter((_, i) => i !== idx).map((d, i) => ({ ...d, day: i + 1 })) }));

  const setList = (key, arr) => setForm((f) => ({ ...f, [key]: arr }));

  const genPresentation = async () => {
    setError(''); setAiPresLoading(true);
    try {
      const { data } = await api.post('/ai/presentation', {
        client_name: client?.name || '', title: form.custom_title || '',
        date_start: form.dates.start || '', date_end: form.dates.end || '',
        adultos: Number(form.pax.adultos) || 0, menores: Number(form.pax.menores) || 0, tone: presTone,
      });
      if (data.text) setForm((f) => ({ ...f, presentation_text: data.text }));
    } catch (e) { setError(formatApiError(e)); }
    finally { setAiPresLoading(false); }
  };

  const canNext = () => {
    if (cur === 'client') {
      if (!form.client_id) return false;
      if (client && (client.executives || []).length > 0 && !form.executive_id) return false;
      return true;
    }
    if (cur === 'program') return !!form.custom_title.trim() && totalPax > 0;
    if (cur === 'items') return form.custom_items.length > 0 && form.custom_items.every((it) => (it.name || '').trim() && Number(it.net_price) > 0);
    return true;
  };

  const submit = async () => {
    setError(''); setLoading(true);
    try {
      const payload = {
        type: 'personalizado',
        client_id: form.client_id,
        custom_title: form.custom_title.trim(),
        dates: form.dates,
        pax: { adultos: Number(form.pax.adultos) || 0, menores: Number(form.pax.menores) || 0, rooms: [] },
        custom_nights: Number(form.custom_nights) || 0,
        custom_rooms: Number(form.custom_rooms) || 0,
        custom_items: form.custom_items.map((it) => ({
          category: it.category, name: it.name, description: it.description || '',
          net_price: Number(it.net_price) || 0, price_type: it.price_type || 'neto', unit: it.unit, qty: Number(it.qty) || 0,
          service_date: it.service_date || '', start_time: it.start_time || '', end_time: it.end_time || '',
          checkin: it.checkin || '', checkout: it.checkout || '', nights: Number(it.nights) || 0,
        })),
        custom_itinerary: form.custom_itinerary.map((d, i) => ({ day: i + 1, title: d.title || '', description: d.description || '' })),
        custom_includes: form.custom_includes.filter((x) => (x || '').trim()),
        custom_excludes: form.custom_excludes.filter((x) => (x || '').trim()),
        contacts: (isB2B || ((client?.executives || []).length > 0)) ? form.contacts : null,
        executive_id: form.executive_id || null,
        notes: form.notes,
        presentation_text: form.presentation_text || '',
        important_info: form.important_info || '',
        show_price_breakdown: !!form.show_price_breakdown,
      };
      if (editing) {
        await api.patch(`/quotations/${id}`, payload);
        navigate(`/app/quotations/${id}`);
      } else {
        const { data } = await api.post('/quotations', payload);
        navigate(`/app/quotations/${data.id}`);
      }
    } catch (e) { setError(formatApiError(e)); setLoading(false); }
  };

  // --- editable string-list helper ---

  return (
    <AppShell>
      <div className="mb-6">
        <Link to={editing ? `/app/quotations/${id}` : '/app/quotations'} className="btn-ghost text-sm" data-testid="custom-back"><ArrowLeft className="w-4 h-4" /> Volver</Link>
      </div>
      <div className="flex items-center gap-2 mb-2">
        <span className="pill bg-peach-100 text-amber-700"><Wand2 className="w-3.5 h-3.5 inline mr-1" /> Programa personalizado</span>
      </div>
      <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight mb-2">{editing ? 'Editar cotización a medida' : 'Cotización a medida'}</h1>
      <p className="text-ink-500 mb-6">Arma una cotización desde cero: define hospedajes, traslados, tours y extras con su unidad de cobro. El precio público y la comisión se calculan automáticamente.</p>

      {/* Stepper */}
      <div className="grid gap-2 mb-8" style={{ gridTemplateColumns: `repeat(${STEPS.length}, minmax(0, 1fr))` }}>
        {STEPS.map((s, i) => (
          <button key={s.key} type="button" onClick={() => setStep(i)}
            className={`rounded-xl p-3 border text-xs font-semibold uppercase tracking-wider text-center transition-all cursor-pointer hover:shadow-sm
              ${i === step ? 'bg-brand-500 text-white border-brand-500' : i < step ? 'bg-mint-100 text-emerald-700 border-mint-200' : 'bg-white text-ink-400 border-ink-100 hover:border-brand-300'}`}
            data-testid={`custom-step-${s.key}`}>
            <div className="flex items-center justify-center gap-2">{i < step ? <Check className="w-4 h-4" /> : <s.icon className="w-4 h-4" />}<span className="hidden sm:inline">{s.label}</span></div>
          </button>
        ))}
      </div>

      {error && <div className="mb-4 rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm" data-testid="custom-error">{error}</div>}
      {tplMsg && <div className="mb-4 rounded-xl border border-emerald-200 bg-mint-100 text-emerald-800 px-4 py-3 text-sm" data-testid="custom-tpl-msg">{tplMsg}</div>}

      <div className="card-surface p-6 md:p-8">
        {/* Step: Client */}
        {cur === 'client' && (
          <div className="space-y-4" data-testid="custom-step-client-panel">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-xl font-semibold text-ink-900">Selecciona cliente</h2>
              {!editing && <button className="btn-secondary text-sm" onClick={() => setShowClient((v) => !v)} data-testid="custom-toggle-new-client"><Plus className="w-4 h-4" /> Nuevo cliente</button>}
            </div>
            {showClient && !editing && (
              <div className="rounded-xl border border-ink-100 bg-cream p-4 space-y-3" data-testid="custom-new-client-form">
                <div className="grid md:grid-cols-2 gap-3">
                  <div><label className="label-text">Nombre</label><input className="input-field" value={newClient.name} onChange={(e) => setNewClient((x) => ({ ...x, name: e.target.value }))} data-testid="custom-newclient-name" /></div>
                  <div><label className="label-text">Canal</label>
                    <select className="input-field" value={newClient.channel} onChange={(e) => setNewClient((x) => ({ ...x, channel: e.target.value }))} data-testid="custom-newclient-channel">
                      <option value="directo">Directo</option><option value="agencia">Agencia</option><option value="mayorista">Mayorista</option><option value="operador">Mayorista Preferencial</option>
                    </select>
                  </div>
                  <div><label className="label-text">Teléfono</label><input className="input-field" value={newClient.phone} onChange={(e) => setNewClient((x) => ({ ...x, phone: e.target.value }))} data-testid="custom-newclient-phone" /></div>
                  <div><label className="label-text">Email</label><input className="input-field" value={newClient.email} onChange={(e) => setNewClient((x) => ({ ...x, email: e.target.value }))} data-testid="custom-newclient-email" /></div>
                </div>
                <button className="btn-primary" onClick={handleCreateClient} disabled={!newClient.name} data-testid="custom-save-new-client">Guardar cliente</button>
              </div>
            )}
            <div className="grid md:grid-cols-2 gap-3">
              {clients.map((c) => (
                <button key={c.id} onClick={() => !editing && selectClient(c)} disabled={editing}
                  className={`text-left rounded-xl border p-4 transition-all ${form.client_id === c.id ? 'border-brand-500 bg-brand-50' : 'border-ink-100 hover:border-brand-300'} ${editing && form.client_id !== c.id ? 'hidden' : ''}`}
                  data-testid={`custom-client-option-${c.id}`}>
                  <p className="font-semibold text-ink-900">{c.name}</p>
                  <p className="text-xs text-ink-500 mt-1">{c.email} · {c.phone}</p>
                  <span className="pill bg-brand-50 text-brand-500 mt-2">{c.channel}</span>
                </button>
              ))}
              {clients.length === 0 && <p className="text-ink-400 text-sm">No hay clientes. Crea uno.</p>}
            </div>
            {/* Empresa con ejecutivos (nivel 2): elegir ejecutivo + turista */}
            {client && (client.executives || []).length > 0 && (
              <div className="grid md:grid-cols-2 gap-4 pt-4 border-t border-ink-100" data-testid="custom-executive-block">
                <div className="rounded-xl border border-ink-100 p-4 space-y-3">
                  <p className="font-semibold text-ink-900 flex items-center gap-2"><Briefcase className="w-4 h-4 text-brand-500" /> Ejecutivo de {client.name}</p>
                  <div className="space-y-2" data-testid="custom-executive-options">
                    {client.executives.map((ex) => (
                      <button key={ex.id} type="button" onClick={() => selectExecutive(ex)} data-testid={`custom-executive-option-${ex.id}`}
                        className={`w-full text-left rounded-xl border p-3 transition-all ${form.executive_id === ex.id ? 'border-brand-500 bg-brand-50' : 'border-ink-100 hover:border-brand-300'}`}>
                        <p className="font-medium text-ink-900">{ex.name || 'Sin nombre'}</p>
                        <p className="text-xs text-ink-500">{[ex.phone, ex.email].filter(Boolean).join(' · ') || '—'}</p>
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-ink-400">En el PDF y el enlace: <b>{client.name}</b> + el ejecutivo seleccionado (teléfono y correo).</p>
                </div>
                <div className="rounded-xl border border-ink-100 p-4 space-y-3">
                  <p className="font-semibold text-ink-900 flex items-center gap-2"><Users className="w-4 h-4 text-brand-500" /> Cliente final / Turista</p>
                  <div><label className="label-text">Nombre completo</label><input className="input-field" value={form.contacts.traveler.name} onChange={(e) => setContact('traveler', 'name', e.target.value)} data-testid="custom-contact-traveler-name" /></div>
                  <div><label className="label-text">Teléfono directo</label><input className="input-field" value={form.contacts.traveler.phone} onChange={(e) => setContact('traveler', 'phone', e.target.value)} data-testid="custom-contact-traveler-phone" /></div>
                </div>
              </div>
            )}

            {/* Agencia + turista para B2B (empresas sin ejecutivos / legacy) */}
            {isB2B && !(client && (client.executives || []).length > 0) && (
              <div className="grid md:grid-cols-2 gap-4 pt-4 border-t border-ink-100" data-testid="custom-contacts-block">
                <div className="rounded-xl border border-ink-100 p-4 space-y-3">
                  <p className="font-semibold text-ink-900 flex items-center gap-2"><Briefcase className="w-4 h-4 text-brand-500" /> Agencia / Vendedor</p>
                  <div><label className="label-text">Nombre de la agencia</label><input className="input-field" value={form.contacts.agency.name} onChange={(e) => setContact('agency', 'name', e.target.value)} data-testid="custom-contact-agency-name" /></div>
                  <div><label className="label-text">Contacto / Vendedor</label><input className="input-field" value={form.contacts.agency.contact} onChange={(e) => setContact('agency', 'contact', e.target.value)} data-testid="custom-contact-agency-contact" /></div>
                  <div className="grid grid-cols-2 gap-2">
                    <div><label className="label-text">Teléfono</label><input className="input-field" value={form.contacts.agency.phone} onChange={(e) => setContact('agency', 'phone', e.target.value)} data-testid="custom-contact-agency-phone" /></div>
                    <div><label className="label-text">Correo</label><input className="input-field" value={form.contacts.agency.email} onChange={(e) => setContact('agency', 'email', e.target.value)} data-testid="custom-contact-agency-email" /></div>
                  </div>
                </div>
                <div className="rounded-xl border border-ink-100 p-4 space-y-3">
                  <p className="font-semibold text-ink-900 flex items-center gap-2"><Users className="w-4 h-4 text-brand-500" /> Cliente final / Turista</p>
                  <div><label className="label-text">Nombre completo</label><input className="input-field" value={form.contacts.traveler.name} onChange={(e) => setContact('traveler', 'name', e.target.value)} data-testid="custom-contact-traveler-name" /></div>
                  <div><label className="label-text">Teléfono directo</label><input className="input-field" value={form.contacts.traveler.phone} onChange={(e) => setContact('traveler', 'phone', e.target.value)} data-testid="custom-contact-traveler-phone" /></div>
                  <p className="text-xs text-ink-400">Puedes tener varias reservas de la misma agencia con turistas distintos.</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Step: Program */}
        {cur === 'program' && (
          <div className="space-y-5" data-testid="custom-step-program-panel">
            <h2 className="font-display text-xl font-semibold text-ink-900">Datos del programa</h2>
            {!editing && templates.length > 0 && (
              <div className="rounded-xl border border-amber-200 bg-peach-100/50 p-4" data-testid="custom-template-loader">
                <label className="label-text flex items-center gap-2"><BookmarkPlus className="w-4 h-4 text-amber-600" /> Cargar desde una plantilla guardada</label>
                <select className="input-field mt-1" defaultValue="" onChange={(e) => { const t = templates.find((x) => x.id === e.target.value); if (t) applyTemplate(t); }} data-testid="custom-template-select">
                  <option value="">— Elegir plantilla —</option>
                  {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                <p className="text-xs text-ink-500 mt-1">Carga conceptos, itinerario e incluye/no incluye. Luego ajusta fechas, grupo y precios.</p>
              </div>
            )}
            <div>
              <label className="label-text">Nombre del programa / título de la cotización</label>
              <input className="input-field" value={form.custom_title} placeholder="Ej. Aventura personalizada en la Riviera Maya, 5 días"
                onChange={(e) => setForm((f) => ({ ...f, custom_title: e.target.value }))} data-testid="custom-title" />
            </div>
            <div className="grid md:grid-cols-3 gap-4">
              <div><label className="label-text">Personas (adultos)</label><input type="number" min="0" className="input-field" value={form.pax.adultos} onChange={(e) => setForm((f) => ({ ...f, pax: { ...f.pax, adultos: +e.target.value || 0 } }))} data-testid="custom-adultos" /></div>
              <div><label className="label-text">Menores</label><input type="number" min="0" className="input-field" value={form.pax.menores} onChange={(e) => setForm((f) => ({ ...f, pax: { ...f.pax, menores: +e.target.value || 0 } }))} data-testid="custom-menores" /></div>
              <div><label className="label-text">Habitaciones</label><input type="number" min="0" className="input-field" value={form.custom_rooms} onChange={(e) => setForm((f) => ({ ...f, custom_rooms: +e.target.value || 0 }))} data-testid="custom-rooms" /></div>
            </div>
            <div className="grid md:grid-cols-3 gap-4">
              <div><label className="label-text">Check-in (opcional)</label><input type="date" className="input-field" value={form.dates.start} onChange={(e) => setForm((f) => ({ ...f, dates: { ...f.dates, start: e.target.value } }))} data-testid="custom-date-start" /></div>
              <div><label className="label-text">Check-out (opcional)</label><input type="date" className="input-field" value={form.dates.end} onChange={(e) => setForm((f) => ({ ...f, dates: { ...f.dates, end: e.target.value } }))} data-testid="custom-date-end" /></div>
              <div><label className="label-text">Noches {nightsBetween(form.dates.start, form.dates.end) > 0 ? '(auto)' : ''}</label><input type="number" min="0" className="input-field" value={nightsBetween(form.dates.start, form.dates.end) || form.custom_nights} disabled={nightsBetween(form.dates.start, form.dates.end) > 0} onChange={(e) => setForm((f) => ({ ...f, custom_nights: +e.target.value || 0 }))} data-testid="custom-nights" /></div>
            </div>
            <p className="text-xs text-ink-400">Las noches y personas se usan para calcular automáticamente la cantidad según la unidad de cobro de cada concepto.</p>
            <div><label className="label-text">Notas internas</label><textarea rows="3" className="input-field" value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} data-testid="custom-notes" /></div>
          </div>
        )}

        {/* Step: Items */}
        {cur === 'items' && (
          <div className="space-y-5" data-testid="custom-step-items-panel">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-display text-xl font-semibold text-ink-900">Conceptos del programa</h2>
              <div className="flex flex-wrap gap-2">
                {CATEGORIES.map((cat) => (
                  <button key={cat.v} type="button" className="btn-ghost text-xs" onClick={() => addItem(cat.v)} data-testid={`custom-add-${cat.v}`}>
                    <cat.icon className="w-4 h-4" /> + {cat.label}
                  </button>
                ))}
              </div>
            </div>
            {form.custom_items.length === 0 && <p className="text-ink-400 text-sm italic">Agrega hospedajes, traslados, tours o extras con los botones de arriba.</p>}
            <div className="space-y-3">
              {form.custom_items.map((it, idx) => (
                <CustomItemCard key={idx} it={it} idx={idx} currency={currency}
                  updateItem={updateItem} removeItem={removeItem}
                  unitPriceFor={unitPriceFor} itemSubtotal={itemSubtotal} publicPrice={publicPrice} />
              ))}
            </div>
            {subtotal > 0 && (
              <div className="rounded-xl bg-mint-100 text-emerald-800 px-4 py-3 text-sm font-medium" data-testid="custom-items-subtotal">Subtotal de conceptos: {money(subtotal, currency)}</div>
            )}
          </div>
        )}

        {/* Step: Itinerary + includes */}
        {cur === 'itinerary' && (
          <div className="space-y-6" data-testid="custom-step-itinerary-panel">
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-display text-xl font-semibold text-ink-900">Itinerario día a día</h2>
                <button type="button" className="btn-secondary text-sm" onClick={addDay} data-testid="custom-add-day"><Plus className="w-4 h-4" /> Agregar día</button>
              </div>
              <p className="text-ink-500 text-sm mb-3">Texto libre. Cada día con un título y una descripción. Es opcional pero recomendado.</p>
              <div className="space-y-3">
                {form.custom_itinerary.map((d, idx) => (
                  <div key={idx} className="rounded-xl border border-ink-100 p-4" data-testid={`custom-day-${idx}`}>
                    <div className="flex items-center gap-3 mb-2">
                      <div className="shrink-0 w-9 h-9 rounded-xl bg-brand-50 text-brand-500 font-display font-bold flex items-center justify-center">{idx + 1}</div>
                      <input className="input-field" value={d.title} placeholder={`Día ${idx + 1}: título`} onChange={(e) => updateDay(idx, { title: e.target.value })} data-testid={`custom-day-title-${idx}`} />
                      <button type="button" className="text-red-600 hover:text-red-800 px-1" onClick={() => removeDay(idx)} data-testid={`custom-day-remove-${idx}`}><Trash2 className="w-4 h-4" /></button>
                    </div>
                    <textarea rows="2" className="input-field" value={d.description} placeholder="Descripción del día" onChange={(e) => updateDay(idx, { description: e.target.value })} data-testid={`custom-day-desc-${idx}`} />
                  </div>
                ))}
                {form.custom_itinerary.length === 0 && <p className="text-ink-400 text-sm italic">Sin días aún. Agrega el primero.</p>}
              </div>
            </div>
            <div className="grid md:grid-cols-2 gap-6 pt-2 border-t border-ink-100">
              <div>
                <p className="font-semibold text-ink-900 mb-2">Incluye</p>
                <StringList list={form.custom_includes} onChange={(arr) => setList('custom_includes', arr)} placeholder="Ej. Desayunos diarios" testid="custom-includes" />
              </div>
              <div>
                <p className="font-semibold text-ink-900 mb-2">No incluye</p>
                <StringList list={form.custom_excludes} onChange={(arr) => setList('custom_excludes', arr)} placeholder="Ej. Vuelos" testid="custom-excludes" />
              </div>
            </div>
          </div>
        )}

        {/* Step: Review */}
        {cur === 'review' && (
          <div className="space-y-4" data-testid="custom-step-review-panel">
            <h2 className="font-display text-xl font-semibold text-ink-900">Revisión</h2>
            <div className="rounded-xl border border-brand-100 bg-brand-50/40 p-4" data-testid="custom-presentation-block">
              <div className="flex items-center justify-between mb-2">
                <label className="label-text mb-0">Texto de presentación (aparece al inicio del PDF y del enlace)</label>
                <div className="flex items-center gap-2">
                  <select className="input-field text-xs w-auto py-1.5" value={presTone} onChange={(e) => setPresTone(e.target.value)} data-testid="custom-tone-select">
                    <option value="formal">Tono: Formal</option>
                    <option value="cercano">Tono: Cercano</option>
                    <option value="premium">Tono: Premium</option>
                  </select>
                  <button type="button" className="btn-ghost text-xs border border-brand-200 text-brand-600" onClick={genPresentation} disabled={aiPresLoading} data-testid="custom-ai-presentation-btn">
                    <Sparkles className="w-3.5 h-3.5" /> {aiPresLoading ? 'Generando…' : 'Generar con IA'}
                  </button>
                </div>
              </div>
              <textarea rows="4" className="input-field" value={form.presentation_text} placeholder="Estimada/o [nombre], a continuación le presento la cotización para su viaje…"
                onChange={(e) => setForm((f) => ({ ...f, presentation_text: e.target.value }))} data-testid="custom-presentation-input" />
            </div>
            <div className="card-surface p-5">
              <label className="label-text">Información importante (opcional)</label>
              <p className="text-xs text-ink-400 mb-2">Condiciones específicas de esta cotización. Aparece en el PDF y en el enlace del cliente.</p>
              <textarea rows="3" className="input-field" value={form.important_info || ''} placeholder="Ej. Tarifas vigentes solo para las fechas indicadas. Anticipo del 50% para confirmar…"
                onChange={(e) => setForm((f) => ({ ...f, important_info: e.target.value }))} data-testid="custom-important-info-input" />
            </div>
            <label className="card-surface p-4 flex items-start gap-3 cursor-pointer" data-testid="custom-show-price-breakdown-label">
              <input type="checkbox" className="mt-1 h-4 w-4 accent-brand-500" checked={form.show_price_breakdown !== false}
                onChange={(e) => setForm((f) => ({ ...f, show_price_breakdown: e.target.checked }))} data-testid="custom-show-price-breakdown-checkbox" />
              <span>
                <span className="font-medium text-ink-900">Mostrar desglose detallado de precios</span>
                <span className="block text-xs text-ink-400 mt-0.5">Activado: tabla con Fecha · Servicio · Detalle · Cant. · $ unitario · Subtotal. Desactivado: el cliente ve solo los conceptos incluidos y el Total final.</span>
              </span>
            </label>
            <div className="grid md:grid-cols-2 gap-4 text-sm">
              <div className="rounded-xl border border-ink-100 p-4">
                <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">Cliente</p>
                <p className="font-semibold text-ink-900">{client?.name}</p><p className="text-ink-500">{client?.channel}</p>
              </div>
              <div className="rounded-xl border border-ink-100 p-4">
                <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">Programa</p>
                <p className="font-semibold text-ink-900">{form.custom_title || 'Programa personalizado'}</p>
                <p className="text-ink-500">{totalPax} persona(s){nights > 0 ? ` · ${nights} noche(s)` : ''}</p>
              </div>
            </div>
            {(isB2B || ((client?.executives || []).length > 0)) && (
              <div className="rounded-xl border border-ink-100 p-4 text-sm" data-testid="custom-review-contacts">
                <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">Contactos</p>
                <p className="text-ink-700"><b>Agencia / Vendedor:</b> {form.contacts.agency.name || '—'}{form.contacts.agency.contact ? ` · ${form.contacts.agency.contact}` : ''}{form.contacts.agency.phone ? ` · ${form.contacts.agency.phone}` : ''}{form.contacts.agency.email ? ` · ${form.contacts.agency.email}` : ''}</p>
                <p className="text-ink-700"><b>Turista:</b> {form.contacts.traveler.name || '—'}{form.contacts.traveler.phone ? ` · ${form.contacts.traveler.phone}` : ''}</p>
              </div>
            )}
            <div className="rounded-xl border border-ink-100 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-cream text-ink-500"><tr><th className="text-left p-3">Concepto</th><th className="text-right p-3">Precio</th><th className="text-center p-3">Cant.</th><th className="text-right p-3">Subtotal</th></tr></thead>
                <tbody>
                  {form.custom_items.map((it, i) => (
                    <tr key={i} className="border-t border-ink-100" data-testid={`custom-review-item-${i}`}>
                      <td className="p-3"><span className="font-medium text-ink-900">{it.name || '—'}</span> <span className="text-ink-400 text-xs">· {UNIT_ES[it.unit]}{(it.price_type || 'neto') === 'neto' ? ' · neto' : ''}</span></td>
                      <td className="p-3 text-right">{money(unitPriceFor(it), currency)}</td>
                      <td className="p-3 text-center">{it.category === 'hospedaje' ? `${it.qty} × ${it.nights || 0}n` : it.qty}</td>
                      <td className="p-3 text-right font-semibold">{money(itemSubtotal(it), currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="rounded-xl bg-gradient-to-br from-brand-500 to-accent text-white p-5" data-testid="custom-totals">
              <div className="flex justify-between text-sm"><span>Subtotal</span><span>{money(subtotal, currency)}</span></div>
              {commission > 0 && <div className="flex justify-between text-sm mt-1"><span>Comisión canal servicios ({(commissionRate * 100).toFixed(0)}%)</span><span>- {money(commission, currency)}</span></div>}
              <div className="border-t border-white/20 mt-3 pt-3 flex justify-between items-end">
                <span className="text-sm uppercase tracking-widest opacity-80">Total</span>
                <span className="font-display font-bold text-3xl" data-testid="custom-total-amount">{money(total, currency)}</span>
              </div>
              {priceNote && <p className="text-xs opacity-80 mt-2" data-testid="custom-price-note">{priceNote}</p>}
            </div>
            <div className="flex justify-end">
              <button type="button" className="btn-ghost text-sm border border-amber-200 text-amber-700" onClick={() => { setTplName(form.custom_title || ''); setSaveTplOpen(true); }} disabled={form.custom_items.length === 0} data-testid="custom-save-template-btn">
                <BookmarkPlus className="w-4 h-4" /> Guardar como plantilla
              </button>
            </div>
          </div>
        )}

        {/* Footer nav */}
        <div className="flex items-center justify-between mt-8 pt-6 border-t border-ink-100">
          <button onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0} className="btn-ghost" data-testid="custom-prev"><ArrowLeft className="w-4 h-4" /> Atrás</button>
          {step < STEPS.length - 1 ? (
            <button disabled={!canNext()} onClick={() => setStep((s) => s + 1)} className="btn-primary" data-testid="custom-next">Siguiente <ArrowRight className="w-4 h-4" /></button>
          ) : (
            <button disabled={loading || form.custom_items.length === 0} onClick={submit} className="btn-primary" data-testid="custom-submit">{loading ? 'Guardando…' : <>{editing ? 'Guardar cambios' : 'Crear cotización'} <FileText className="w-4 h-4" /></>}</button>
          )}
        </div>
      </div>

      {saveTplOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => !savingTpl && setSaveTplOpen(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="custom-save-template-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900 flex items-center gap-2"><BookmarkPlus className="w-5 h-5 text-amber-600" /> Guardar como plantilla</h3>
            <p className="text-sm text-ink-500 mt-2">Reutiliza este programa en segundos para futuras cotizaciones. Se guardan los conceptos, itinerario e incluye/no incluye (sin el cliente).</p>
            <label className="label-text mt-4">Nombre de la plantilla</label>
            <input className="input-field mt-1" value={tplName} placeholder="Ej. Riviera Maya 5 días" onChange={(e) => setTplName(e.target.value)} data-testid="custom-template-name-input" />
            <div className="flex justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setSaveTplOpen(false)} data-testid="custom-template-cancel">Cancelar</button>
              <button className="btn-primary" disabled={tplName.trim().length < 2 || savingTpl} onClick={saveAsTemplate} data-testid="custom-template-save">
                <Save className="w-4 h-4" /> {savingTpl ? 'Guardando…' : 'Guardar plantilla'}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
