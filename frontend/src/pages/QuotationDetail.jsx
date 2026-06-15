import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { ArrowLeft, Download, MessageCircle, Mail, FileText, Sparkles, Link2, Copy, CheckCircle2, X, Tag, CreditCard } from 'lucide-react';

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
  const [ai, setAi] = useState({ next: '', missing: [], message: '' });
  const [aiLoading, setAiLoading] = useState({ next: false, missing: false, message: false });
  const [aiError, setAiError] = useState('');
  const [publicToken, setPublicToken] = useState('');
  const [copiedPublic, setCopiedPublic] = useState(false);
  const [discount, setDiscount] = useState({ discount_type: 'none', discount_value: 0 });

  const load = async () => {
    const { data } = await api.get(`/quotations/${id}`);
    setQ(data);
    setPublicToken(data?.public_link?.token || '');
    if (data?.discount) setDiscount({ discount_type: data.discount.type, discount_value: data.discount.value });
    try {
      const p = await api.get(`/packages/${data.package_id}`);
      setPack(p.data);
    } catch (_e) { /* noop */ }
  };
  useEffect(() => { load(); }, [id]); // eslint-disable-line

  const applyDiscount = async () => {
    await api.patch(`/quotations/${id}/pricing-adjust`, discount);
    await load();
  };

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

  const runAI = async (kind) => {
    setAiError('');
    setAiLoading((s) => ({ ...s, [kind]: true }));
    try {
      const { data } = await api.post(`/ai/quotations/${id}/${kind === 'next' ? 'next-step' : kind === 'missing' ? 'missing-fields' : 'client-message'}`);
      setAi((a) => ({ ...a, [kind]: kind === 'missing' ? (data.fields || []) : (data.suggestion || data.message || '') }));
    } catch (e) { setAiError(formatApiError(e)); }
    finally { setAiLoading((s) => ({ ...s, [kind]: false })); }
  };

  const createPublicLink = async () => {
    const { data } = await api.post(`/quotations/${id}/public-link`);
    setPublicToken(data.token);
    await load();
  };

  const revokePublicLink = async () => {
    if (!window.confirm('¿Revocar el enlace público? El cliente ya no podrá acceder.')) return;
    await api.delete(`/quotations/${id}/public-link`);
    setPublicToken('');
    await load();
  };

  const copyPublicUrl = () => {
    const url = `${window.location.origin}/q/${publicToken}`;
    navigator.clipboard.writeText(url);
    setCopiedPublic(true);
    setTimeout(() => setCopiedPublic(false), 2000);
  };

  if (!q) return <AppShell><div className="p-8 text-ink-400">Cargando…</div></AppShell>;

  const paxDesc = (() => {
    const p = q.pax || {};
    if (p.rooms?.length) {
      const rooms = p.rooms.map((r) => `${r.count} ${r.ocupacion}`).join(' · ');
      const adults = p.rooms.reduce((s, r) => s + ({ sencilla: 1, doble: 2, triple: 3, cuadruple: 4 }[r.ocupacion] || 0) * r.count, 0);
      return `${rooms} (${adults} adultos${p.menores > 0 ? ` + ${p.menores} menores` : ''})`;
    }
    return `${p.adultos || 0} adultos · ${p.menores || 0} menores (${p.ocupacion || ''})`;
  })();

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
              <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Habitaciones / Pax</p><p className="text-ink-900 font-medium mt-1">{paxDesc}</p></div>
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
          {/* AI Panel */}
          <div className="card-surface p-6" data-testid="ai-panel">
            <h3 className="font-display font-semibold text-ink-900 mb-3 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-brand-500" /> Asistente IA
            </h3>
            {aiError && <div className="text-xs text-red-700 bg-red-50 rounded-lg p-2 mb-3" data-testid="ai-error">{aiError}</div>}
            <div className="space-y-2">
              <button className="btn-secondary w-full text-xs justify-center" disabled={aiLoading.next}
                onClick={() => runAI('next')} data-testid="ai-next-step-btn">
                {aiLoading.next ? 'Analizando…' : 'Sugerir próximo paso'}
              </button>
              {ai.next && <p className="text-sm text-ink-700 bg-mint-100 rounded-lg p-3" data-testid="ai-next-result">{ai.next}</p>}

              <button className="btn-secondary w-full text-xs justify-center" disabled={aiLoading.missing}
                onClick={() => runAI('missing')} data-testid="ai-missing-btn">
                {aiLoading.missing ? 'Analizando…' : 'Detectar campos faltantes'}
              </button>
              {ai.missing.length > 0 && (
                <ul className="text-sm text-ink-700 bg-peach-100 rounded-lg p-3 space-y-1" data-testid="ai-missing-result">
                  {ai.missing.map((f, i) => <li key={i}>• {f}</li>)}
                </ul>
              )}

              <button className="btn-secondary w-full text-xs justify-center" disabled={aiLoading.message}
                onClick={() => runAI('message')} data-testid="ai-message-btn">
                {aiLoading.message ? 'Redactando…' : 'Redactar mensaje WhatsApp'}
              </button>
              {ai.message && (
                <div className="text-sm text-ink-700 bg-brand-50 rounded-lg p-3 whitespace-pre-wrap" data-testid="ai-message-result">
                  {ai.message}
                  <button className="mt-2 btn-ghost text-xs"
                    onClick={() => navigator.clipboard.writeText(ai.message)} data-testid="ai-message-copy">
                    <Copy className="w-3 h-3" /> Copiar
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Public Link Panel */}
          <div className="card-surface p-6" data-testid="public-link-panel">
            <h3 className="font-display font-semibold text-ink-900 mb-2 flex items-center gap-2">
              <Link2 className="w-4 h-4 text-brand-500" /> Enlace para cliente
            </h3>
            <p className="text-xs text-ink-500 mb-3">El cliente puede ver y aceptar la cotización con un click. Válido 7 días.</p>
            {!publicToken ? (
              <button className="btn-primary w-full text-sm justify-center" onClick={createPublicLink} data-testid="create-public-link">
                Generar enlace
              </button>
            ) : (
              <div className="space-y-2">
                <div className="rounded-lg bg-cream border border-ink-100 p-2 text-xs font-mono break-all text-ink-700">
                  {window.location.origin}/q/{publicToken}
                </div>
                <div className="flex gap-2">
                  <button className="btn-primary text-xs flex-1 justify-center" onClick={copyPublicUrl} data-testid="copy-public-link">
                    {copiedPublic ? <><CheckCircle2 className="w-3 h-3" /> Copiado</> : <><Copy className="w-3 h-3" /> Copiar</>}
                  </button>
                  <button className="btn-ghost text-xs text-red-600" onClick={revokePublicLink} data-testid="revoke-public-link">
                    <X className="w-3 h-3" /> Revocar
                  </button>
                </div>
                {q.public_link?.accepted_at && (
                  <p className="text-xs text-emerald-700 bg-mint-100 rounded p-2" data-testid="public-accepted">
                    ✓ Aceptada por el cliente el {q.public_link.accepted_at.slice(0, 10)}
                  </p>
                )}
              </div>
            )}
          </div>

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
              <div className="flex justify-between pt-2 border-t border-ink-100 mt-2"><span className="text-ink-700">Total</span><span className="text-ink-900 font-semibold">{money(q.total, q.currency)}</span></div>
              {q.discount && q.discount.amount > 0 && (
                <div className="flex justify-between"><span className="text-ink-500">Descuento ({q.discount.type === 'percent' ? `${q.discount.value}%` : 'fijo'})</span><span className="text-red-600 font-medium">- {money(q.discount.amount, q.currency)}</span></div>
              )}
              <div className="flex justify-between pt-2 border-t border-ink-100 mt-2"><span className="font-display text-lg font-semibold text-ink-900">Total final</span><span className="font-display text-lg font-bold text-brand-500">{money(q.final_total != null ? q.final_total : q.total, q.currency)}</span></div>
            </div>

            {/* Discount control */}
            <div className="mt-4 pt-4 border-t border-ink-100" data-testid="discount-control">
              <p className="text-xs uppercase tracking-widest text-ink-400 font-bold mb-2 flex items-center gap-1.5"><Tag className="w-3.5 h-3.5" /> Descuento</p>
              <div className="flex gap-2">
                <select className="input-field text-sm" value={discount.discount_type}
                  onChange={(e) => setDiscount((d) => ({ ...d, discount_type: e.target.value }))} data-testid="discount-type-select">
                  <option value="none">Sin descuento</option>
                  <option value="percent">Porcentaje %</option>
                  <option value="fixed">Monto fijo</option>
                </select>
                <input type="number" min="0" className="input-field text-sm w-28" disabled={discount.discount_type === 'none'}
                  value={discount.discount_value} onChange={(e) => setDiscount((d) => ({ ...d, discount_value: +e.target.value || 0 }))} data-testid="discount-value-input" />
                <button className="btn-primary text-sm" onClick={applyDiscount} data-testid="apply-discount-btn">Aplicar</button>
              </div>
            </div>

            {/* Payment status */}
            <div className="mt-4 pt-4 border-t border-ink-100" data-testid="payment-status">
              <p className="text-xs uppercase tracking-widest text-ink-400 font-bold mb-2 flex items-center gap-1.5"><CreditCard className="w-3.5 h-3.5" /> Pago</p>
              <div className="flex items-center justify-between text-sm">
                <span className={`pill ${q.payment_status === 'paid' ? 'bg-mint-100 text-emerald-700' : q.payment_status === 'partial' ? 'bg-peach-100 text-amber-700' : 'bg-ink-100 text-ink-500'}`} data-testid="payment-badge">
                  {q.payment_status === 'paid' ? 'Pagado' : q.payment_status === 'partial' ? 'Pago parcial' : 'Sin pagar'}
                </span>
                <span className="text-ink-700">Pagado: <b>{money(q.amount_paid || 0, q.currency)}</b></span>
              </div>
              <p className="text-xs text-ink-400 mt-2">El cliente paga desde el enlace público. Comparte el enlace por WhatsApp o correo.</p>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
