import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api from '@/lib/api';
import { ArrowLeft, Download, MessageCircle, Mail, FileText } from 'lucide-react';

const STATES = [
  { id: 'nueva_consulta', label: 'Nueva' },
  { id: 'cotizando', label: 'Cotizando' },
  { id: 'enviada', label: 'Enviada' },
  { id: 'negociacion', label: 'En negociación' },
  { id: 'ganada', label: 'Ganada' },
  { id: 'perdida', label: 'Perdida' },
];

function money(v, c = 'MXN') { return `$${Number(v || 0).toLocaleString('es-MX')} ${c}`; }

export default function QuotationDetail() {
  const { id } = useParams();
  const [q, setQ] = useState(null);
  const [pack, setPack] = useState(null);

  const load = async () => {
    const { data } = await api.get(`/quotations/${id}`);
    setQ(data);
    try {
      const p = await api.get(`/packages/${data.package_id}`);
      setPack(p.data);
    } catch (_e) { /* noop */ }
  };
  useEffect(() => { load(); }, [id]); // eslint-disable-line

  const changeState = async (state) => {
    await api.patch(`/quotations/${id}/state`, { state });
    await load();
  };

  const downloadPdf = async () => {
    const response = await api.get(`/quotations/${id}/pdf`, { responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
    const a = document.createElement('a');
    a.href = url; a.download = `${q.code}.pdf`; a.click();
    window.URL.revokeObjectURL(url);
  };

  if (!q) return <AppShell><div className="p-8 text-ink-400">Cargando…</div></AppShell>;

  return (
    <AppShell>
      <Link to="/app/quotations" className="btn-ghost text-sm mb-6" data-testid="qdetail-back">
        <ArrowLeft className="w-4 h-4" /> Cotizaciones
      </Link>

      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4 mb-6">
        <div>
          <p className="font-mono text-sm text-brand-500 font-semibold">{q.code}</p>
          <h1 className="font-display text-3xl font-semibold text-ink-900 mt-1">{q.package_snapshot?.name}</h1>
          <p className="text-ink-500 mt-1">Cliente: <span className="text-ink-900 font-medium">{q.client_snapshot?.name}</span></p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={downloadPdf} className="btn-primary text-sm" data-testid="download-pdf-btn">
            <Download className="w-4 h-4" /> Descargar PDF
          </button>
          <button className="btn-secondary text-sm opacity-60 cursor-not-allowed" disabled title="Disponible con WhatsApp conectado" data-testid="send-whatsapp-btn">
            <MessageCircle className="w-4 h-4" /> Enviar por WhatsApp
          </button>
          <button className="btn-ghost text-sm opacity-60 cursor-not-allowed" disabled data-testid="send-email-btn">
            <Mail className="w-4 h-4" /> Enviar por email
          </button>
        </div>
      </div>

      {/* State selector */}
      <div className="flex flex-wrap gap-2 mb-8" data-testid="state-selector">
        {STATES.map((s) => (
          <button key={s.id} onClick={() => changeState(s.id)}
            className={`pill transition-all ${q.state === s.id ? 'bg-brand-500 text-white' : 'bg-white border border-ink-100 text-ink-700 hover:bg-brand-50'}`}
            data-testid={`state-btn-${s.id}`}>
            {s.label}
          </button>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="card-surface p-6">
            <h3 className="font-display font-semibold text-ink-900 mb-4">Detalles</h3>
            <div className="grid md:grid-cols-2 gap-4 text-sm">
              <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Hotel</p><p className="text-ink-900 font-medium mt-1">{q.hotel_selected}</p></div>
              <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Fechas</p><p className="text-ink-900 font-medium mt-1">{q.dates?.start} → {q.dates?.end}</p></div>
              <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Pasajeros</p><p className="text-ink-900 font-medium mt-1">{q.pax?.adultos} adultos · {q.pax?.menores} menores</p></div>
              <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Ocupación</p><p className="text-ink-900 font-medium mt-1 capitalize">{q.pax?.ocupacion}</p></div>
            </div>
            {q.notes && <><p className="text-xs uppercase tracking-widest text-ink-400 font-bold mt-6">Notas</p><p className="text-ink-700 mt-1 text-sm">{q.notes}</p></>}
          </div>

          <div className="card-surface p-6">
            <h3 className="font-display font-semibold text-ink-900 mb-4">Itinerario</h3>
            {pack?.itinerary?.map((d) => (
              <div key={d.day} className="flex gap-4 mb-4 last:mb-0">
                <div className="shrink-0 w-10 h-10 rounded-xl bg-brand-50 text-brand-500 font-display font-bold flex items-center justify-center">{d.day}</div>
                <div>
                  <p className="font-semibold text-ink-900">{d.title}</p>
                  <p className="text-sm text-ink-500 mt-0.5">{d.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <div className="card-surface p-6">
            <h3 className="font-display font-semibold text-ink-900 mb-4 flex items-center gap-2"><FileText className="w-4 h-4 text-brand-500" /> Desglose</h3>
            {q.items?.map((it, i) => (
              <div key={i} className="flex justify-between text-sm py-2 border-b border-ink-100 last:border-0">
                <div><p className="text-ink-700">{it.label}</p><p className="text-ink-400 text-xs">{money(it.unit_price, q.currency)} × {it.qty}</p></div>
                <p className="font-semibold text-ink-900">{money(it.subtotal, q.currency)}</p>
              </div>
            ))}
            <div className="mt-4 pt-4 border-t border-ink-100 space-y-1 text-sm">
              <div className="flex justify-between"><span className="text-ink-500">Subtotal</span><span className="text-ink-900 font-medium">{money(q.subtotal, q.currency)}</span></div>
              {q.commission > 0 && <div className="flex justify-between"><span className="text-ink-500">Comisión</span><span className="text-red-600 font-medium">- {money(q.commission, q.currency)}</span></div>}
              <div className="flex justify-between pt-2 border-t border-ink-100 mt-2"><span className="font-display text-lg font-semibold text-ink-900">Total</span><span className="font-display text-lg font-bold text-brand-500">{money(q.total, q.currency)}</span></div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
