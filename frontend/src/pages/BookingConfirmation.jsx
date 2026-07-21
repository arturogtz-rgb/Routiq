import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { formatDateEs } from '@/lib/dates';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import {
  DndContext, PointerSensor, KeyboardSensor, useSensor, useSensors, closestCenter,
} from '@dnd-kit/core';
import {
  SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy, useSortable, arrayMove,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { ArrowLeft, Plus, Trash2, Save, Download, Mail, MessageCircle, Loader2, CheckCircle2, Link2, GripVertical, CalendarDays, AlertTriangle, RefreshCw } from 'lucide-react';

let RID = 0;
const rid = () => `r${Date.now().toString(36)}${(RID++).toString(36)}`;
const newSvc = () => ({ _rid: rid(), date: '', service: '', details: '', persons: '', observations: '' });
const withRid = (arr) => (arr || []).map((r) => ({ _rid: r._rid || rid(), ...r }));
const EMPTY_LODGING = { hotel: '', plan: '', checkin: '', checkout: '', nights: '', room_type: '', confirmation_number: '', guest_name: '' };

function DateField({ value, onChange, testid }) {
  const [open, setOpen] = useState(false);
  const selected = value ? new Date(`${String(value).slice(0, 10)}T00:00:00`) : undefined;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className="input-field flex items-center gap-2 text-left w-full" data-testid={testid}>
          <CalendarDays className="w-4 h-4 text-ink-400 shrink-0" />
          <span className={value ? 'text-ink-900' : 'text-ink-400'}>{value ? formatDateEs(value) : 'Fecha'}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={selected}
          onSelect={(d) => {
            if (d) {
              const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
              onChange(iso);
            } else {
              onChange('');
            }
            setOpen(false);
          }}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  );
}

function SortableServiceRow({ row, i, updRow, delRow }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: row._rid });
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1, zIndex: isDragging ? 20 : undefined };
  return (
    <div ref={setNodeRef} style={style} className="grid md:grid-cols-12 gap-2 items-start bg-white" data-testid={`service-row-${i}`}>
      <button
        type="button" {...attributes} {...listeners}
        className="md:col-span-1 flex items-center justify-center py-2.5 text-ink-300 hover:text-ink-600 cursor-grab active:cursor-grabbing touch-none"
        data-testid={`svc-drag-${i}`} aria-label="Reordenar fila"
      >
        <GripVertical className="w-4 h-4" />
      </button>
      <div className="md:col-span-2">
        <DateField value={row.date} onChange={(v) => updRow(i, { date: v })} testid={`svc-date-${i}`} />
      </div>
      <input className="input-field md:col-span-3" placeholder="Servicio" value={row.service} onChange={(e) => updRow(i, { service: e.target.value })} data-testid={`svc-name-${i}`} />
      <input className="input-field md:col-span-2" placeholder="Detalles" value={row.details} onChange={(e) => updRow(i, { details: e.target.value })} data-testid={`svc-details-${i}`} />
      <input className="input-field md:col-span-1" placeholder="Pers." value={row.persons} onChange={(e) => updRow(i, { persons: e.target.value })} data-testid={`svc-persons-${i}`} />
      <input className="input-field md:col-span-2" placeholder="Observaciones" value={row.observations} onChange={(e) => updRow(i, { observations: e.target.value })} data-testid={`svc-obs-${i}`} />
      <button onClick={() => delRow(i)} className="md:col-span-1 p-2 text-ink-400 hover:text-red-600 justify-self-start" data-testid={`del-service-${i}`}><Trash2 className="w-4 h-4" /></button>
    </div>
  );
}

export default function BookingConfirmation() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [q, setQ] = useState(null);
  const [conf, setConf] = useState(null);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [expected, setExpected] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [form, setForm] = useState({
    agent_name: '', agent_phone: '', agent_company: '', agent_email: '', reservation_date: '',
    passenger_name: '', passenger_phone: '', num_persons: '',
    services: [newSvc()], lodging: [{ ...EMPTY_LODGING }], itinerary: [],
    general_observations: '', price_per_person: 0, total_amount: 0,
  });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const load = async () => {
    try {
      const [qr, cr] = await Promise.all([
        api.get(`/quotations/${id}`),
        api.get(`/quotations/${id}/booking-confirmation`),
      ]);
      setQ(qr.data);
      const OCC = { sencilla: 1, doble: 2, triple: 3, cuadruple: 4 };
      const px = qr.data.pax || {};
      const paxTotal = (px.rooms?.length
        ? px.rooms.reduce((s, r) => s + (OCC[r.ocupacion] || 1) * (r.count || 1), 0)
        : (px.adultos || 0)) + (px.menores || 0);
      const paxStr = paxTotal ? String(paxTotal) : '';
      const existing = cr.data && cr.data.id ? cr.data : null;
      if (existing) {
        setConf(existing);
        setExpected(existing._expected || null);
        setForm({
          agent_name: existing.agent_name || '', agent_phone: existing.agent_phone || '',
          agent_company: existing.agent_company || '', agent_email: existing.agent_email || '', reservation_date: existing.reservation_date || '',
          passenger_name: existing.passenger_name || '', passenger_phone: existing.passenger_phone || '',
          num_persons: existing.num_persons || paxStr,
          services: existing.services?.length ? withRid(existing.services) : [newSvc()],
          lodging: existing.lodging?.length ? existing.lodging : [{ ...EMPTY_LODGING }],
          itinerary: existing.itinerary || [],
          general_observations: existing.general_observations || '',
          price_per_person: existing.price_per_person || 0, total_amount: existing.total_amount || 0,
        });
      } else if (cr.data && cr.data._prefill) {
        const p = cr.data;
        setForm({
          agent_name: p.agent_name || '', agent_phone: p.agent_phone || '',
          agent_company: p.agent_company || '', agent_email: p.agent_email || '', reservation_date: p.reservation_date || '',
          passenger_name: p.passenger_name || '', passenger_phone: p.passenger_phone || '',
          num_persons: p.num_persons || paxStr,
          services: p.services?.length ? withRid(p.services) : [newSvc()],
          lodging: p.lodging?.length ? p.lodging : [{ ...EMPTY_LODGING }],
          itinerary: p.itinerary || [],
          general_observations: p.general_observations || '',
          price_per_person: p.price_per_person || 0, total_amount: p.total_amount || 0,
        });
      }
    } catch (e) { setError(formatApiError(e)); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const refreshAmounts = async () => {
    setRefreshing(true); setError(''); setOk('');
    try {
      await api.post(`/quotations/${id}/booking-confirmation/refresh-amounts`);
      await load();
      setOk('Montos actualizados desde la cotización.');
      setTimeout(() => setOk(''), 3000);
    } catch (e) { setError(formatApiError(e)); }
    finally { setRefreshing(false); }
  };

  // Detección de desfase: compara la confirmación GUARDADA vs. el estado ACTUAL de la
  // cotización (expected). Los campos exclusivos de la confirmación (N° de confirmación,
  // huésped, plan) NO se comparan ni sincronizan: son datos que el ejecutivo captura a
  // propósito en la reserva y no viven en la cotización.
  const numEq = (a, b) => Math.abs((Number(a) || 0) - (Number(b) || 0)) < 0.01;
  const strEq = (a, b) => String(a ?? '').trim() === String(b ?? '').trim();
  const fmtMoney = (n) => `$${(Number(n) || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const mismatches = (() => {
    if (!conf || !expected) return [];
    const out = [];
    if (!numEq(conf.total_amount, expected.total_amount))
      out.push({ label: 'Total a pagar', from: fmtMoney(conf.total_amount), to: fmtMoney(expected.total_amount) });
    if (!numEq(conf.price_per_person, expected.price_per_person))
      out.push({ label: 'Precio por persona', from: fmtMoney(conf.price_per_person), to: fmtMoney(expected.price_per_person) });
    if (!strEq(conf.num_persons, expected.num_persons))
      out.push({ label: 'Número de personas', from: conf.num_persons || '—', to: expected.num_persons || '—' });
    const lod = (conf.lodging || [])[0];
    if (lod) {
      if (!strEq(lod.hotel, expected.hotel)) out.push({ label: 'Hotel', from: lod.hotel || '—', to: expected.hotel || '—' });
      if (!strEq(lod.checkin, expected.checkin)) out.push({ label: 'Check-in', from: lod.checkin ? formatDateEs(lod.checkin) : '—', to: expected.checkin ? formatDateEs(expected.checkin) : '—' });
      if (!strEq(lod.checkout, expected.checkout)) out.push({ label: 'Check-out', from: lod.checkout ? formatDateEs(lod.checkout) : '—', to: expected.checkout ? formatDateEs(expected.checkout) : '—' });
      if (!strEq(lod.nights, expected.nights)) out.push({ label: 'Noches', from: lod.nights || '—', to: expected.nights || '—' });
      if (!strEq(lod.room_type, expected.room_type)) out.push({ label: 'Tipo de habitación', from: lod.room_type || '—', to: expected.room_type || '—' });
    }
    return out;
  })();

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const updRow = (key, i, patch) => setForm((f) => ({ ...f, [key]: f[key].map((r, idx) => idx === i ? { ...r, ...patch } : r) }));
  const addRow = (key, empty) => setForm((f) => ({ ...f, [key]: [...f[key], empty] }));
  const delRow = (key, i) => setForm((f) => ({ ...f, [key]: f[key].filter((_, idx) => idx !== i) }));

  const onServicesDragEnd = (event) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setForm((f) => {
      const oldIdx = f.services.findIndex((r) => r._rid === active.id);
      const newIdx = f.services.findIndex((r) => r._rid === over.id);
      if (oldIdx < 0 || newIdx < 0) return f;
      return { ...f, services: arrayMove(f.services, oldIdx, newIdx) };
    });
  };

  const save = async () => {
    setError(''); setOk(''); setSaving(true);
    try {
      const payload = {
        ...form,
        services: form.services.map(({ _rid, ...rest }) => rest),
        itinerary: (form.itinerary || []).filter((e) => (e.title || '').trim() || (e.description || '').trim()),
        price_per_person: Number(form.price_per_person) || 0,
        total_amount: Number(form.total_amount) || 0,
      };
      const { data } = await api.post(`/quotations/${id}/booking-confirmation`, payload);
      setConf(data); setOk('Confirmación de reserva guardada');
      setTimeout(() => setOk(''), 2500);
    } catch (e) { setError(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const downloadPdf = async () => {
    if (!conf) return;
    try {
      const res = await api.get(`/booking-confirmations/${conf.id}/pdf`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url; a.download = `${conf.code}.pdf`; a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) { setError(formatApiError(e)); }
  };

  const send = async (channel) => {
    if (!conf) return;
    setError(''); setOk(''); setSending(true);
    try {
      const to = channel === 'email'
        ? (window.prompt('Correo del destinatario:', q?.contacts?.email || '') || '')
        : (form.passenger_phone || form.agent_phone || '');
      if (channel === 'email' && !to) { setSending(false); return; }
      const { data } = await api.post(`/booking-confirmations/${conf.id}/send`, { channel, to });
      if (channel === 'whatsapp' && data.wa_link) {
        window.open(data.wa_link, '_blank');
        setOk('Abriendo WhatsApp…');
      } else {
        setOk(data.email_sent ? `Confirmación enviada a ${data.to}` : 'No se pudo enviar el correo (revisa la configuración de email).');
      }
      setTimeout(() => setOk(''), 3500);
    } catch (e) { setError(formatApiError(e)); }
    finally { setSending(false); }
  };

  if (!q) return <AppShell><div className="flex items-center justify-center h-64"><Loader2 className="w-7 h-7 animate-spin text-ink-300" /></div></AppShell>;

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto" data-testid="booking-confirmation-page">
        <button onClick={() => navigate(`/app/quotations/${id}`)} className="btn-ghost text-sm mb-4" data-testid="back-to-quotation"><ArrowLeft className="w-4 h-4" /> Volver a la cotización</button>
        <div className="flex items-start justify-between flex-wrap gap-3 mb-6">
          <div>
            <h1 className="font-display text-3xl font-bold text-ink-900">Confirmación de Reserva</h1>
            <p className="text-ink-500 mt-1">Cotización {q.code} · {q.client_snapshot?.name}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={save} disabled={saving} className="btn-primary text-sm" data-testid="save-confirmation-btn">
              <Save className="w-4 h-4" /> {saving ? 'Guardando…' : 'Guardar'}
            </button>
            {conf && <button onClick={downloadPdf} className="btn-secondary text-sm" data-testid="download-confirmation-pdf-btn"><Download className="w-4 h-4" /> PDF</button>}
            {conf?.token && <button onClick={() => { navigator.clipboard.writeText(`${window.location.origin}/r/${conf.token}`); setOk('Enlace web copiado'); setTimeout(() => setOk(''), 2500); }} className="btn-ghost text-sm border border-ink-100" data-testid="copy-booking-link-btn"><Link2 className="w-4 h-4" /> Copiar enlace</button>}
            {conf && <button onClick={() => send('email')} disabled={sending} className="btn-ghost text-sm border border-ink-100" data-testid="send-email-btn"><Mail className="w-4 h-4" /> Correo</button>}
            {conf && <button onClick={() => send('whatsapp')} disabled={sending} className="btn-ghost text-sm border border-emerald-300 text-emerald-700" data-testid="send-whatsapp-btn"><MessageCircle className="w-4 h-4" /> WhatsApp</button>}
          </div>
        </div>

        {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="confirmation-error">{error}</div>}
        {ok && <div className="rounded-xl border border-emerald-200 bg-mint-100 text-emerald-800 px-4 py-3 text-sm mb-4 flex items-center gap-2" data-testid="confirmation-ok"><CheckCircle2 className="w-4 h-4" /> {ok}</div>}

        {/* Alerta de desfase vs. cotización + actualización manual (nunca automática) */}
        {mismatches.length > 0 && (
          <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-4 mb-5" data-testid="price-mismatch-banner">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="font-semibold text-amber-900 text-sm">La cotización cambió después de crear esta confirmación</h3>
                <p className="text-sm text-amber-800 mt-1">Los siguientes datos no coinciden con el estado actual de la cotización. Actualízalos manualmente para reflejar los valores vigentes; esto sobrescribe montos y datos de viaje, pero conserva el N° de confirmación, el huésped y el plan que hayas capturado.</p>
                <ul className="mt-3 space-y-1.5" data-testid="price-mismatch-list">
                  {mismatches.map((m, i) => (
                    <li key={i} className="text-sm text-amber-900 flex flex-wrap items-center gap-x-2" data-testid={`mismatch-${i}`}>
                      <span className="font-medium">{m.label}:</span>
                      <span className="line-through text-amber-600" data-testid={`mismatch-from-${i}`}>{m.from}</span>
                      <span aria-hidden>→</span>
                      <span className="font-semibold" data-testid={`mismatch-to-${i}`}>{m.to}</span>
                    </li>
                  ))}
                </ul>
                <button onClick={refreshAmounts} disabled={refreshing} className="btn-primary text-sm mt-4" data-testid="refresh-amounts-btn">
                  <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} /> {refreshing ? 'Actualizando…' : 'Actualizar montos desde la cotización'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Encabezado */}
        <div className="card-surface p-6 mb-5">
          <h2 className="font-display font-semibold text-lg text-ink-900 mb-4">Datos generales</h2>
          <div className="grid md:grid-cols-3 gap-4">
            {[['agent_name', 'Ejecutivo'], ['agent_email', 'Correo del ejecutivo'], ['agent_company', 'Empresa'], ['agent_phone', 'Teléfono'],
              ['passenger_name', 'Pasajero final'], ['passenger_phone', 'Teléfono del pasajero'],
              ['num_persons', 'Número de personas']].map(([k, label]) => (
              <div key={k}>
                <label className="label-text">{label}</label>
                <input className="input-field" value={form[k]} onChange={(e) => setField(k, e.target.value)} data-testid={`conf-${k}`} />
              </div>
            ))}
            <div>
              <label className="label-text">Fecha de reservación</label>
              <DateField value={form.reservation_date} onChange={(v) => setField('reservation_date', v)} testid="conf-reservation_date" />
            </div>
          </div>
        </div>

        {/* Servicios confirmados */}
        <div className="card-surface p-6 mb-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-semibold text-lg text-ink-900">Servicios confirmados</h2>
            <button onClick={() => addRow('services', newSvc())} className="btn-ghost text-sm" data-testid="add-service-row"><Plus className="w-4 h-4" /> Fila</button>
          </div>
          <p className="text-xs text-ink-400 mb-3">Arrastra <GripVertical className="w-3 h-3 inline align-middle" /> para reordenar. El orden visual define el orden impreso en el PDF.</p>
          <div className="space-y-3">
            {form.services.length > 0 && (
              <div className="hidden md:grid grid-cols-12 gap-2 px-1 text-xs uppercase tracking-widest font-bold text-ink-400" data-testid="service-row-headers">
                <div className="col-span-1"></div>
                <div className="col-span-2">Fecha</div>
                <div className="col-span-3">Servicio</div>
                <div className="col-span-2">Detalles</div>
                <div className="col-span-1">Pers.</div>
                <div className="col-span-2">Observaciones</div>
                <div className="col-span-1"></div>
              </div>
            )}
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onServicesDragEnd}>
              <SortableContext items={form.services.map((r) => r._rid)} strategy={verticalListSortingStrategy}>
                <div className="space-y-3">
                  {form.services.map((r, i) => (
                    <SortableServiceRow key={r._rid} row={r} i={i} updRow={(idx, patch) => updRow('services', idx, patch)} delRow={(idx) => delRow('services', idx)} />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          </div>
        </div>

        {/* Hospedaje */}
        <div className="card-surface p-6 mb-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-semibold text-lg text-ink-900">Hospedaje</h2>
            <button onClick={() => addRow('lodging', { ...EMPTY_LODGING })} className="btn-ghost text-sm" data-testid="add-lodging-row"><Plus className="w-4 h-4" /> Fila</button>
          </div>
          <div className="space-y-4">
            {form.lodging.map((r, i) => (
              <div key={i} className="rounded-xl border border-ink-100 p-3 relative" data-testid={`lodging-row-${i}`}>
                <button onClick={() => delRow('lodging', i)} className="absolute top-2 right-2 p-1.5 text-ink-400 hover:text-red-600" data-testid={`del-lodging-${i}`}><Trash2 className="w-4 h-4" /></button>
                <div className="grid md:grid-cols-4 gap-2">
                  {[['hotel', 'Hotel'], ['plan', 'Plan'], ['checkin', 'Check-in'], ['checkout', 'Check-out'],
                    ['nights', 'Noches'], ['room_type', 'Tipo de habitación'], ['confirmation_number', 'N° de confirmación'], ['guest_name', 'Nombre del huésped']].map(([k, label]) => (
                    <div key={k}>
                      <label className="label-text">{label}</label>
                      <input className="input-field" value={r[k]} onChange={(e) => updRow('lodging', i, { [k]: e.target.value })} data-testid={`lodging-${k}-${i}`} />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Itinerario / descripción según tipo (10.5) */}
        <div className="card-surface p-6 mb-5" data-testid="itinerary-section">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-display font-semibold text-lg text-ink-900">
              {q.type === 'servicios' ? 'Descripción de servicios' : q.type === 'personalizado' ? 'Programa detallado' : 'Itinerario día a día'}
            </h2>
            <button onClick={() => addRow('itinerary', { title: '', description: '' })} className="btn-ghost text-sm" data-testid="add-itinerary-row"><Plus className="w-4 h-4" /> Bloque</button>
          </div>
          <p className="text-xs text-ink-400 mb-3">Prellenado desde la cotización. Edítalo libremente; se imprime en el PDF de confirmación.</p>
          <div className="space-y-3">
            {(form.itinerary || []).length === 0 && (
              <p className="text-sm text-ink-400 italic" data-testid="itinerary-empty">Sin contenido. Agrega un bloque o guarda sin itinerario.</p>
            )}
            {(form.itinerary || []).map((e, i) => (
              <div key={i} className="rounded-xl border border-ink-100 p-3 relative" data-testid={`itinerary-row-${i}`}>
                <button onClick={() => delRow('itinerary', i)} className="absolute top-2 right-2 p-1.5 text-ink-400 hover:text-red-600" data-testid={`del-itinerary-${i}`}><Trash2 className="w-4 h-4" /></button>
                <input className="input-field font-medium mb-2 pr-8" placeholder="Título (ej. Día 1: Llegada)" value={e.title} onChange={(ev) => updRow('itinerary', i, { title: ev.target.value })} data-testid={`itinerary-title-${i}`} />
                <textarea rows="2" className="input-field" placeholder="Descripción" value={e.description} onChange={(ev) => updRow('itinerary', i, { description: ev.target.value })} data-testid={`itinerary-desc-${i}`} />
              </div>
            ))}
          </div>
        </div>

        {/* Observaciones + precios */}
        <div className="card-surface p-6 mb-5">
          <label className="label-text">Observaciones generales</label>
          <textarea rows="3" className="input-field" value={form.general_observations} onChange={(e) => setField('general_observations', e.target.value)} data-testid="conf-observations" />
          <div className="grid md:grid-cols-2 gap-4 mt-4">
            <div>
              <label className="label-text">Precio por persona</label>
              <input type="number" min="0" step="0.01" className="input-field" value={form.price_per_person} onChange={(e) => setField('price_per_person', e.target.value)} data-testid="conf-price-per-person" />
            </div>
            <div>
              <label className="label-text">Total a pagar</label>
              <input type="number" min="0" step="0.01" className="input-field" value={form.total_amount} onChange={(e) => setField('total_amount', e.target.value)} data-testid="conf-total" />
            </div>
          </div>
          <p className="text-xs text-ink-400 mt-3">Los datos bancarios y las condiciones generales/cancelación se toman automáticamente de Ajustes y se incluyen en el PDF.</p>
        </div>
      </div>
    </AppShell>
  );
}
