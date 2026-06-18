import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { ArrowLeft, Plus, Trash2, Save, Download, Mail, MessageCircle, Loader2, CheckCircle2 } from 'lucide-react';

const EMPTY_SVC = { date: '', service: '', details: '', persons: '', observations: '' };
const EMPTY_LODGING = { hotel: '', plan: '', checkin: '', checkout: '', nights: '', room_type: '', confirmation_number: '', guest_name: '' };

export default function BookingConfirmation() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [q, setQ] = useState(null);
  const [conf, setConf] = useState(null);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [form, setForm] = useState({
    agent_name: '', agent_phone: '', agent_company: '', reservation_date: '',
    passenger_name: '', passenger_phone: '', num_persons: '',
    services: [{ ...EMPTY_SVC }], lodging: [{ ...EMPTY_LODGING }],
    general_observations: '', price_per_person: 0, total_amount: 0,
  });

  useEffect(() => {
    (async () => {
      try {
        const [qr, cr] = await Promise.all([
          api.get(`/quotations/${id}`),
          api.get(`/quotations/${id}/booking-confirmation`),
        ]);
        setQ(qr.data);
        const existing = cr.data && cr.data.id ? cr.data : null;
        if (existing) {
          setConf(existing);
          setForm({
            agent_name: existing.agent_name || '', agent_phone: existing.agent_phone || '',
            agent_company: existing.agent_company || '', reservation_date: existing.reservation_date || '',
            passenger_name: existing.passenger_name || '', passenger_phone: existing.passenger_phone || '',
            num_persons: existing.num_persons || '',
            services: existing.services?.length ? existing.services : [{ ...EMPTY_SVC }],
            lodging: existing.lodging?.length ? existing.lodging : [{ ...EMPTY_LODGING }],
            general_observations: existing.general_observations || '',
            price_per_person: existing.price_per_person || 0, total_amount: existing.total_amount || 0,
          });
        } else {
          const total = qr.data.final_total != null ? qr.data.final_total : qr.data.total;
          const pax = (qr.data.pax?.adultos || 0) + (qr.data.pax?.menores || 0);
          setForm((f) => ({
            ...f, agent_name: qr.data.client_snapshot?.name || '',
            num_persons: pax ? String(pax) : '', total_amount: total || 0,
            price_per_person: pax ? Math.round((total / pax) * 100) / 100 : 0,
          }));
        }
      } catch (e) { setError(formatApiError(e)); }
    })();
  }, [id]);

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const updRow = (key, i, patch) => setForm((f) => ({ ...f, [key]: f[key].map((r, idx) => idx === i ? { ...r, ...patch } : r) }));
  const addRow = (key, empty) => setForm((f) => ({ ...f, [key]: [...f[key], { ...empty }] }));
  const delRow = (key, i) => setForm((f) => ({ ...f, [key]: f[key].filter((_, idx) => idx !== i) }));

  const save = async () => {
    setError(''); setOk(''); setSaving(true);
    try {
      const { data } = await api.post(`/quotations/${id}/booking-confirmation`, {
        ...form,
        price_per_person: Number(form.price_per_person) || 0,
        total_amount: Number(form.total_amount) || 0,
      });
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
            {conf && <button onClick={() => send('email')} disabled={sending} className="btn-ghost text-sm border border-ink-100" data-testid="send-email-btn"><Mail className="w-4 h-4" /> Correo</button>}
            {conf && <button onClick={() => send('whatsapp')} disabled={sending} className="btn-ghost text-sm border border-emerald-300 text-emerald-700" data-testid="send-whatsapp-btn"><MessageCircle className="w-4 h-4" /> WhatsApp</button>}
          </div>
        </div>

        {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="confirmation-error">{error}</div>}
        {ok && <div className="rounded-xl border border-emerald-200 bg-mint-100 text-emerald-800 px-4 py-3 text-sm mb-4 flex items-center gap-2" data-testid="confirmation-ok"><CheckCircle2 className="w-4 h-4" /> {ok}</div>}

        {/* Encabezado */}
        <div className="card-surface p-6 mb-5">
          <h2 className="font-display font-semibold text-lg text-ink-900 mb-4">Datos generales</h2>
          <div className="grid md:grid-cols-3 gap-4">
            {[['agent_name', 'Agente / Cliente'], ['agent_phone', 'Teléfono'], ['agent_company', 'Empresa'],
              ['reservation_date', 'Fecha de reservación'], ['passenger_name', 'Pasajero final'], ['passenger_phone', 'Teléfono del pasajero'],
              ['num_persons', 'Número de personas']].map(([k, label]) => (
              <div key={k}>
                <label className="label-text">{label}</label>
                <input className="input-field" value={form[k]} onChange={(e) => setField(k, e.target.value)} data-testid={`conf-${k}`} />
              </div>
            ))}
          </div>
        </div>

        {/* Servicios confirmados */}
        <div className="card-surface p-6 mb-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-semibold text-lg text-ink-900">Servicios confirmados</h2>
            <button onClick={() => addRow('services', EMPTY_SVC)} className="btn-ghost text-sm" data-testid="add-service-row"><Plus className="w-4 h-4" /> Fila</button>
          </div>
          <div className="space-y-3">
            {form.services.map((r, i) => (
              <div key={i} className="grid md:grid-cols-12 gap-2 items-start" data-testid={`service-row-${i}`}>
                <input className="input-field md:col-span-2" placeholder="Fecha" value={r.date} onChange={(e) => updRow('services', i, { date: e.target.value })} data-testid={`svc-date-${i}`} />
                <input className="input-field md:col-span-3" placeholder="Servicio" value={r.service} onChange={(e) => updRow('services', i, { service: e.target.value })} data-testid={`svc-name-${i}`} />
                <input className="input-field md:col-span-3" placeholder="Detalles" value={r.details} onChange={(e) => updRow('services', i, { details: e.target.value })} data-testid={`svc-details-${i}`} />
                <input className="input-field md:col-span-1" placeholder="Pers." value={r.persons} onChange={(e) => updRow('services', i, { persons: e.target.value })} data-testid={`svc-persons-${i}`} />
                <input className="input-field md:col-span-2" placeholder="Observaciones" value={r.observations} onChange={(e) => updRow('services', i, { observations: e.target.value })} data-testid={`svc-obs-${i}`} />
                <button onClick={() => delRow('services', i)} className="md:col-span-1 p-2 text-ink-400 hover:text-red-600 justify-self-start" data-testid={`del-service-${i}`}><Trash2 className="w-4 h-4" /></button>
              </div>
            ))}
          </div>
        </div>

        {/* Hospedaje */}
        <div className="card-surface p-6 mb-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-semibold text-lg text-ink-900">Hospedaje</h2>
            <button onClick={() => addRow('lodging', EMPTY_LODGING)} className="btn-ghost text-sm" data-testid="add-lodging-row"><Plus className="w-4 h-4" /> Fila</button>
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
