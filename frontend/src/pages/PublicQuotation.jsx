import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import api, { formatApiError } from '@/lib/api';
import { CheckCircle2, Calendar, MapPin, Users, FileText, Sparkles, CreditCard, Loader2, Moon, Landmark, Copy, Download, Briefcase } from 'lucide-react';
import { formatDateEs } from '@/lib/dates';

function money(v, c = 'MXN') { return `$${Number(v || 0).toLocaleString('es-MX')} ${c}`; }
function conceptWhen(it) {
  if (it.category === 'hospedaje' && (it.checkin || it.checkout)) {
    const rango = [it.checkin ? formatDateEs(it.checkin) : '', it.checkout ? formatDateEs(it.checkout) : ''].filter(Boolean).join(' → ');
    const n = Number(it.nights) || 0;
    return rango + (n ? ` (${n} ${n === 1 ? 'noche' : 'noches'})` : '');
  }
  const time = (it.start_time && it.end_time) ? `${it.start_time}–${it.end_time}` : (it.start_time || '');
  return [it.service_date ? formatDateEs(it.service_date) : '', time].filter(Boolean).join(' · ');
}

const OCC = { sencilla: 1, doble: 2, triple: 3, cuadruple: 4, menor: 1 };

export default function PublicQuotation() {
  const { token } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const backend = process.env.REACT_APP_BACKEND_URL || '';
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [accepting, setAccepting] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [paying, setPaying] = useState(false);
  const [payMsg, setPayMsg] = useState(null); // { type, text }
  const [lastSession, setLastSession] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [showTransfer, setShowTransfer] = useState(false);
  const [transferMsg, setTransferMsg] = useState('');
  const [selectedOcc, setSelectedOcc] = useState(null);

  const load = async () => {
    try {
      const { data } = await api.get(`/public/quotations/${token}`);
      setData(data);
      if (data.quotation?.accepted_at) setAccepted(true);
    } catch (e) { setError(formatApiError(e)); }
  };
  useEffect(() => { load(); }, [token]); // eslint-disable-line

  const pollOnce = async (sessionId) => {
    const { data: st } = await api.get(`/public/quotations/${token}/payment-status/${sessionId}`);
    return st;
  };

  // Detect return from Stripe and poll status
  useEffect(() => {
    const sessionId = searchParams.get('session_id');
    if (!sessionId) return;
    setLastSession(sessionId);
    let attempts = 0;
    setPayMsg({ type: 'pending', text: 'Verificando tu pago…' });
    const poll = async () => {
      try {
        const st = await pollOnce(sessionId);
        if (st.payment_status === 'paid') {
          setPayMsg({ type: 'success', text: '¡Pago confirmado! Gracias por tu reserva.' });
          await load();
          return;
        }
        if (st.status === 'expired') {
          setPayMsg({ type: 'error', text: 'La sesión de pago expiró. Intenta de nuevo.' });
          return;
        }
        if (attempts++ < 15) { setTimeout(poll, 2000); }
        else setPayMsg({ type: 'pending', text: 'Aún no confirmamos tu pago. Si ya pagaste, pulsa "Verificar pago".' });
      } catch (_e) {
        if (attempts++ < 15) setTimeout(poll, 2000);
        else setPayMsg({ type: 'error', text: 'Error verificando el pago.' });
      }
    };
    poll();
    // clear the session_id from URL so refresh doesn't re-poll endlessly
    const sp = new URLSearchParams(searchParams); sp.delete('session_id'); setSearchParams(sp, { replace: true });
  }, [token]); // eslint-disable-line

  const verifyPayment = async () => {
    if (!lastSession) return;
    setVerifying(true);
    try {
      const st = await pollOnce(lastSession);
      if (st.payment_status === 'paid') {
        setPayMsg({ type: 'success', text: '¡Pago confirmado! Gracias por tu reserva.' });
        await load();
      } else {
        setPayMsg({ type: 'pending', text: 'Tu pago sigue pendiente de confirmación. Intenta de nuevo en unos minutos.' });
      }
    } catch (_e) {
      setPayMsg({ type: 'error', text: 'No pudimos verificar el pago.' });
    } finally { setVerifying(false); }
  };

  const accept = async () => {
    setAccepting(true);
    try {
      await api.post(`/public/quotations/${token}/accept`);
      setAccepted(true);
      await load();
    } catch (e) { setError(formatApiError(e)); }
    finally { setAccepting(false); }
  };

  const pay = async (payType) => {
    setPaying(true); setPayMsg(null);
    try {
      const { data: res } = await api.post(`/public/quotations/${token}/checkout`, {
        origin_url: window.location.origin, pay_type: payType,
      });
      window.location.href = res.url;
    } catch (e) { setPayMsg({ type: 'error', text: formatApiError(e) }); setPaying(false); }
  };

  const requestTransfer = async () => {
    setShowTransfer(true); setTransferMsg('');
    try {
      const { data: res } = await api.post(`/public/quotations/${token}/request-transfer`);
      if (res.email_sent) setTransferMsg(`Te enviamos los datos a ${res.to}. Revisa tu correo.`);
    } catch (_e) { /* still show on-screen data */ }
  };

  if (error) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center p-6">
        <div className="text-center max-w-md">
          <h1 className="font-display text-2xl font-semibold text-ink-900 mb-2">Enlace no válido</h1>
          <p className="text-ink-500">{error}</p>
        </div>
      </div>
    );
  }
  if (!data) return <div className="min-h-screen flex items-center justify-center text-ink-400">Cargando…</div>;

  const { quotation: q, company, itinerary, includes, excludes, payment } = data;
  // Inherit the brand theme configured in the Master panel (applied globally via
  // CSS variables by ThemeApplier) for end-to-end brand consistency.
  const primary = 'rgb(var(--brand-500))';
  const finalTotal = q.final_total != null ? q.final_total : q.total;
  const amountDue = q.amount_due != null ? q.amount_due : finalTotal;
  const isPaid = q.payment_status === 'paid';

  const paxDesc = (() => {
    const p = q.pax || {};
    if (p.rooms?.length) {
      const rooms = p.rooms.map((r) => `${r.count} ${r.ocupacion}`).join(' · ');
      const adults = p.rooms.reduce((s, r) => s + (OCC[r.ocupacion] || 0) * r.count, 0);
      return `${rooms} (${adults} adultos${p.menores > 0 ? ` + ${p.menores} menores` : ''})`;
    }
    return `${p.adultos || 0} adultos · ${p.menores || 0} menores`;
  })();

  return (
    <div className="min-h-screen bg-cream" data-testid="public-quotation-page">
      {/* Header */}
      <header className="bg-white border-b border-ink-100 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between gap-3">
          <span className="text-xs font-mono text-ink-500">{q.code}</span>
          <a href={`${backend}/api/public/quotations/${token}/pdf`} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-2 text-sm font-semibold px-3 py-2 rounded-xl border-2 transition-all hover:bg-cream"
            style={{ borderColor: primary, color: primary }} data-testid="download-pdf-btn">
            <Download className="w-4 h-4" /> Descargar PDF
          </a>
        </div>
      </header>

      {/* Hero with big centered logo */}
      <section className="bg-gradient-to-br from-white to-brand-50/40">
        <div className="max-w-3xl mx-auto px-4 py-12 md:py-16 text-center">
          {company.logo_url ? (
            <div className="flex justify-center mb-6">
              <img src={`${backend}${company.logo_url}`} alt={company.name}
                className="h-40 md:h-52 max-w-[320px] md:max-w-[420px] object-contain drop-shadow-sm"
                data-testid="public-logo" />
            </div>
          ) : (
            <div className="font-display font-bold text-3xl mb-4" style={{ color: primary }}>{company.name}</div>
          )}
          <p className="pill inline-block mb-3" style={{ background: `${primary}15`, color: primary }}>Cotización personalizada</p>
          <h1 className="font-display text-3xl md:text-5xl font-semibold text-ink-900 tracking-tight">
            ¡Hola{q.client_name ? `, ${q.client_name.split(' ')[0]}` : ''}!<br />
            Tu viaje está casi listo. ✨
          </h1>
          <p className="text-ink-500 mt-3 text-lg">{q.package_snapshot?.name || (q.type === 'servicios' ? 'Servicios a la carta' : '')}</p>
        </div>
        {data.package_image_url && (
          <div className="max-w-3xl mx-auto px-4 pb-2">
            <img src={data.package_image_url.startsWith('http') ? data.package_image_url : `${backend}${data.package_image_url}`}
              alt={q.package_snapshot?.name} className="w-full h-48 md:h-64 object-cover rounded-2xl shadow-sm" data-testid="public-package-image" />
          </div>
        )}
      </section>

      <main className="max-w-3xl mx-auto px-4 pb-20 space-y-6">
        {/* Presentation (carta al cliente) */}
        {q.presentation_text && (
          <div className="card-surface p-6" data-testid="public-presentation">
            <p className="text-ink-700 leading-relaxed whitespace-pre-line">{q.presentation_text}</p>
          </div>
        )}

        {/* Datos del cliente — Agencia/Vendedor + Turista (réplica del PDF) */}
        {q.contacts && (q.contacts.agency?.name || q.contacts.traveler?.name) && (
          <div className="card-surface p-6 grid sm:grid-cols-2 gap-4" data-testid="public-client-data">
            {q.contacts.agency?.name && (
              <div className="flex items-start gap-3">
                <Briefcase className="w-5 h-5 mt-0.5" style={{ color: primary }} />
                <div>
                  <p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Agencia / Vendedor</p>
                  <p className="font-semibold text-ink-900">{q.contacts.agency.name}</p>
                  <p className="text-xs text-ink-500">{[q.contacts.agency.contact, q.contacts.agency.phone, q.contacts.agency.email].filter(Boolean).join(' · ')}</p>
                </div>
              </div>
            )}
            {q.contacts.traveler?.name && (
              <div className="flex items-start gap-3">
                <Users className="w-5 h-5 mt-0.5" style={{ color: primary }} />
                <div>
                  <p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Cliente final / Turista</p>
                  <p className="font-semibold text-ink-900">{q.contacts.traveler.name}</p>
                  {q.contacts.traveler.phone && <p className="text-xs text-ink-500">Tel: {q.contacts.traveler.phone}</p>}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Summary */}
        <div className="card-surface p-6 grid sm:grid-cols-2 gap-4">
          {q.hotel_selected && (
            <div className="flex items-start gap-3">
              <MapPin className="w-5 h-5 mt-0.5" style={{ color: primary }} />
              <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Hotel</p>
                <p className="font-semibold text-ink-900">{q.hotel_selected}</p></div>
            </div>
          )}
          {(q.dates?.start || q.dates?.end) && (
            <div className="flex items-start gap-3">
              <Calendar className="w-5 h-5 mt-0.5" style={{ color: primary }} />
              <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Fechas</p>
                <p className="font-semibold text-ink-900">{formatDateEs(q.dates?.start)} → {formatDateEs(q.dates?.end)}</p>
                {q.nights_total ? <p className="text-xs text-ink-400">{q.nights_total} noches{q.extra_nights > 0 ? ` (${q.package_nights} paquete + ${q.extra_nights} extra)` : ''}</p> : null}
              </div>
            </div>
          )}
          <div className="flex items-start gap-3 sm:col-span-2">
            <Users className="w-5 h-5 mt-0.5" style={{ color: primary }} />
            <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">{q.type === 'servicios' ? 'Personas' : 'Habitaciones / Pax'}</p>
              <p className="font-semibold text-ink-900">{paxDesc}</p></div>
          </div>
        </div>

        {/* Opciones de ocupación interactivas — solo cuando el ejecutivo activa "Mostrar todas las opciones" */}
        {q.occupancy_prices?.length > 0 && (
          <div className="card-surface p-6" data-testid="public-occupancy-table">
            <h2 className="font-display text-xl font-semibold text-ink-900 mb-1">Opciones de ocupación{q.hotel_selected ? ` — ${q.hotel_selected}` : ''}</h2>
            <p className="text-sm text-ink-500 mb-4">Elige tu tipo de ocupación para ver el precio estimado.</p>
            <div className="space-y-2">
              {q.occupancy_prices.map((o) => {
                const count = OCC[o.occ] || 1;
                const active = selectedOcc?.key === o.key;
                return (
                  <button key={o.key} type="button" onClick={() => setSelectedOcc(o)}
                    data-testid={`occ-option-${o.occ || o.key}`}
                    className={`w-full flex items-center justify-between gap-3 rounded-xl border-2 px-4 py-3 text-left transition-all ${active ? 'shadow-sm' : 'border-ink-100 hover:border-ink-200'}`}
                    style={active ? { borderColor: primary, background: `${primary}0D` } : {}}>
                    <span className="flex items-center gap-3">
                      <span className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${active ? '' : 'border-ink-300'}`} style={active ? { borderColor: primary } : {}}>
                        {active && <span className="w-2 h-2 rounded-full" style={{ background: primary }} />}
                      </span>
                      <span className="font-medium text-ink-900">{o.label}</span>
                    </span>
                    <span className="text-right">
                      <span className="block font-semibold text-ink-900">{money(o.price, q.currency)}</span>
                      <span className="block text-xs text-ink-400">por persona</span>
                    </span>
                  </button>
                );
              })}
            </div>
            {selectedOcc && (
              <div className="mt-4 rounded-xl px-4 py-3 flex items-center justify-between" style={{ background: `${primary}12` }} data-testid="occ-estimated-total">
                <div>
                  <p className="text-xs uppercase tracking-widest font-bold" style={{ color: primary }}>Total estimado — {selectedOcc.label}</p>
                  <p className="text-xs text-ink-500">{money(selectedOcc.price, q.currency)} × {OCC[selectedOcc.occ] || 1} persona(s)</p>
                </div>
                <p className="font-display text-2xl font-bold" style={{ color: primary }}>{money(selectedOcc.price * (OCC[selectedOcc.occ] || 1), q.currency)}</p>
              </div>
            )}
            <p className="text-xs text-ink-400 italic mt-3">Precio referencial por habitación. El monto a pagar es el indicado en el total de la cotización.</p>
          </div>
        )}

        {/* Desglose de precios — todas las líneas juntas (réplica del PDF) */}
        {(q.items || []).length > 0 && (
          <div className="card-surface p-6" data-testid="public-price-breakdown">
            <h2 className="font-display text-xl font-semibold text-ink-900 mb-4">{q.show_price_breakdown === false ? 'Conceptos incluidos' : 'Desglose de precios'}</h2>
            {q.show_price_breakdown === false ? (
              <ul className="space-y-1.5 mb-2" data-testid="public-concepts-list">
                {(q.items || []).map((it, i) => (
                  <li key={i} className="flex items-center gap-2 text-ink-800" data-testid={`public-concept-${i}`}>
                    <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: primary }} />{it.label}
                  </li>
                ))}
              </ul>
            ) : (
            <div className="space-y-1">
              {(q.items || []).map((it, i) => {
                const dt = conceptWhen(it);
                const Icon = it.kind === 'noche_extra' ? Moon : Sparkles;
                return (
                  <div key={i} className="flex items-start justify-between gap-3 py-2.5 border-b border-ink-100 last:border-0" data-testid={`public-line-item-${i}`}>
                    <div className="flex items-start gap-3">
                      <Icon className="w-4 h-4 mt-1 shrink-0" style={{ color: primary }} />
                      <div>
                        <p className="font-medium text-ink-900">{it.label}</p>
                        {it.description && <p className="text-xs text-ink-500 mt-0.5">{it.description}</p>}
                        {dt && <p className="text-xs text-ink-400 mt-0.5">{dt}</p>}
                        <p className="text-xs text-ink-400 mt-0.5">{it.category === 'hospedaje' && Number(it.nights) > 0
                          ? `${money(it.unit_price, q.currency)}/noche × ${it.qty} hab × ${it.nights} ${Number(it.nights) === 1 ? 'noche' : 'noches'}`
                          : `${money(it.unit_price, q.currency)} × ${it.qty}`}</p>
                      </div>
                    </div>
                    <p className="font-semibold text-ink-900 whitespace-nowrap pl-3">{money(it.subtotal, q.currency)}</p>
                  </div>
                );
              })}
            </div>
            )}
            <div className="mt-3 pt-3 space-y-1.5">
              {q.show_price_breakdown !== false && (
                <>
                  <div className="flex items-center justify-between text-sm text-ink-600">
                    <span>Subtotal</span><span className="font-medium">{money(q.subtotal, q.currency)}</span>
                  </div>
                  {q.commission > 0 && (
                    <div className="flex items-center justify-between text-sm text-ink-600">
                      <span>Comisión canal</span><span className="font-medium">- {money(q.commission, q.currency)}</span>
                    </div>
                  )}
                </>
              )}
              <div className="flex items-center justify-between pt-1.5 border-t border-ink-100">
                <span className="font-semibold text-ink-900">Total</span>
                <span className="font-display text-lg font-bold" style={{ color: primary }}>{money(finalTotal, q.currency)}</span>
              </div>
            </div>
            {q.price_note && (
              <p className="text-xs text-ink-500 italic mt-3" data-testid="public-breakdown-note">{q.price_note}</p>
            )}
          </div>
        )}

        {/* Información importante + condiciones (réplica del PDF) */}
        {q.important_info && (
          <div className="card-surface p-6" data-testid="public-important-info">
            <h2 className="font-display text-xl font-semibold text-ink-900 mb-3">Información importante</h2>
            <p className="text-sm text-ink-600 whitespace-pre-line">{q.important_info}</p>
          </div>
        )}
        <div className="text-center text-xs text-ink-400 italic px-4">
          Todos los precios están sujetos a cambio y disponibilidad sin previo aviso.
          {company.slug && (
            <> · <a href={`/c/${company.slug}/condiciones`} target="_blank" rel="noreferrer" className="not-italic underline" style={{ color: primary }} data-testid="public-conditions-link">Consultar condiciones generales y políticas de cancelación</a></>
          )}
        </div>

        {/* Total + Accept */}
        <div className="card-surface p-6 sticky bottom-4" data-testid="public-total-card">
          <div className="flex items-center justify-between mb-2">
            <p className="text-ink-500 text-sm">Total final</p>
            <p className="font-display text-3xl md:text-4xl font-bold" style={{ color: primary }}>{money(finalTotal, q.currency)}</p>
          </div>
          {payment?.equivalent_amount && payment?.equivalent_currency && (
            <p className="text-right text-xs text-ink-400 mb-4" data-testid="usd-equivalent">≈ ${Number(payment.equivalent_amount).toLocaleString(payment.equivalent_currency === 'USD' ? 'en-US' : 'es-MX')} {payment.equivalent_currency} (TC {payment.rate_mxn_per_usd})</p>
          )}
          {q.amount_paid > 0 && !isPaid && (
            <p className="text-right text-xs text-emerald-700 mb-3">Pagado: {money(q.amount_paid, q.currency)} · Resta: {money(amountDue, q.currency)}</p>
          )}

          {payMsg && (
            <div className={`rounded-xl px-4 py-3 mb-4 text-sm flex items-center gap-2 ${payMsg.type === 'success' ? 'bg-mint-100 text-emerald-800' : payMsg.type === 'error' ? 'bg-red-50 text-red-700' : 'bg-peach-100 text-amber-800'}`} data-testid="payment-message">
              {payMsg.type === 'pending' && <Loader2 className="w-4 h-4 animate-spin" />}
              {payMsg.type === 'success' && <CheckCircle2 className="w-4 h-4" />}
              {payMsg.text}
            </div>
          )}
          {lastSession && payMsg && payMsg.type !== 'success' && !isPaid && (
            <button onClick={verifyPayment} disabled={verifying}
              className="w-full mb-3 text-sm font-semibold py-2.5 rounded-xl border border-ink-200 text-ink-700 hover:bg-cream disabled:opacity-60 flex items-center justify-center gap-2"
              data-testid="verify-payment-btn">
              {verifying ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} Ya pagué, verificar pago
            </button>
          )}

          {isPaid ? (
            <div className="rounded-xl bg-mint-100 text-emerald-800 px-5 py-4 flex items-center gap-3" data-testid="public-paid-banner">
              <CheckCircle2 className="w-6 h-6 shrink-0" />
              <div>
                <p className="font-semibold">¡Pago completado!</p>
                <p className="text-sm">{company.name} confirmará tu reserva en breve.</p>
              </div>
            </div>
          ) : (
            <>
              {payment?.enabled && (
                <div className="space-y-2 mb-3" data-testid="payment-buttons">
                  <button onClick={() => pay('total')} disabled={paying}
                    className="w-full text-white font-display font-semibold py-4 rounded-2xl text-lg transition-all hover:scale-[1.01] disabled:opacity-60 flex items-center justify-center gap-2"
                    style={{ background: primary }} data-testid="pay-total-btn">
                    {paying ? <Loader2 className="w-5 h-5 animate-spin" /> : <CreditCard className="w-5 h-5" />}
                    Pagar {money(amountDue, q.currency)}
                  </button>
                  <button onClick={() => pay('deposit')} disabled={paying}
                    className="w-full font-display font-semibold py-3 rounded-2xl border-2 transition-all hover:bg-brand-50 disabled:opacity-60"
                    style={{ borderColor: primary, color: primary }} data-testid="pay-deposit-btn">
                    Pagar anticipo ({payment.deposit_percent}%)
                  </button>
                </div>
              )}
              {payment?.transfer_enabled && payment?.bank && (
                <div className="mb-3 rounded-2xl border-2 border-ink-100 p-4" data-testid="transfer-section">
                  {!showTransfer ? (
                    <button onClick={requestTransfer}
                      className="w-full font-display font-semibold py-3 rounded-xl border-2 transition-all hover:bg-cream flex items-center justify-center gap-2"
                      style={{ borderColor: primary, color: primary }} data-testid="transfer-toggle-btn">
                      <Landmark className="w-5 h-5" /> Pagar por transferencia bancaria
                    </button>
                  ) : (
                    <div data-testid="transfer-details">
                      <p className="font-semibold text-ink-900 flex items-center gap-2 mb-3"><Landmark className="w-4 h-4" style={{ color: primary }} /> Datos para tu transferencia</p>
                      <div className="space-y-1.5 text-sm">
                        {[
                          ['Banco', payment.bank.name], ['Titular', payment.bank.holder],
                          ['CLABE', payment.bank.clabe], ['Cuenta', payment.bank.account],
                          ['Cuenta USD', payment.bank.usd_account], ['SWIFT/BIC', payment.bank.swift],
                          ['ABA/Routing', payment.bank.aba], ['Domicilio del banco', payment.bank.address],
                        ].filter(([, v]) => v).map(([k, v]) => (
                          <div key={k} className="flex items-center justify-between gap-3 py-1 border-b border-ink-100 last:border-0">
                            <span className="text-ink-400">{k}</span>
                            <span className="font-medium text-ink-900 text-right break-all">{v}
                              <button className="ml-2 text-ink-300 hover:text-ink-600 align-middle" onClick={() => navigator.clipboard.writeText(v)} title="Copiar"><Copy className="w-3 h-3 inline" /></button>
                            </span>
                          </div>
                        ))}
                      </div>
                      <p className="text-xs text-ink-500 mt-3">Importe: <b>{money(amountDue, q.currency)}</b>. Envía tu comprobante a {company.contact_email || company.name} para confirmar.</p>
                      {transferMsg && <p className="text-xs text-emerald-700 bg-mint-100 rounded p-2 mt-2" data-testid="transfer-msg">{transferMsg}</p>}
                    </div>
                  )}
                </div>
              )}
              {accepted ? (
                <div className="rounded-xl bg-mint-100 text-emerald-800 px-5 py-4 flex items-center gap-3" data-testid="public-accepted-banner">
                  <CheckCircle2 className="w-6 h-6 shrink-0" />
                  <div>
                    <p className="font-semibold">¡Cotización aceptada!</p>
                    <p className="text-sm">{company.name} se pondrá en contacto contigo en breve.</p>
                  </div>
                </div>
              ) : (
                <button onClick={accept} disabled={accepting}
                  className={`w-full font-display font-semibold py-3 rounded-2xl text-base transition-all hover:scale-[1.01] disabled:opacity-60 ${payment?.enabled ? 'border-2 text-ink-700 border-ink-200 hover:bg-cream' : 'text-white'}`}
                  style={payment?.enabled ? {} : { background: primary }} data-testid="accept-quotation-btn">
                  {accepting ? 'Confirmando…' : <span className="flex items-center justify-center gap-2"><Sparkles className="w-5 h-5" /> {payment?.enabled ? 'Confirmar sin pagar ahora' : 'Confirmar y reservar'}</span>}
                </button>
              )}
            </>
          )}
          <p className="text-xs text-ink-400 mt-3 text-center">
            <FileText className="w-3 h-3 inline mr-1" /> Pago seguro procesado por Stripe. Al confirmar, {company.name} procederá con la reserva.
          </p>
        </div>

        {/* Página 2: Descripción + Itinerario día a día + Incluye/No incluye (réplica del PDF) */}
        {(q.package_snapshot?.description || itinerary?.length > 0 || includes?.length > 0 || excludes?.length > 0) && (
          <div className="card-surface p-6" data-testid="public-itinerary">
            <h2 className="font-display text-xl font-semibold text-ink-900 mb-4">{q.package_snapshot?.name || 'Tu programa'}</h2>
            {q.package_snapshot?.description && (
              <p className="text-sm text-ink-600 whitespace-pre-line mb-5">{q.package_snapshot.description}</p>
            )}
            {itinerary?.length > 0 && (
              <>
                <h3 className="font-display text-lg font-semibold text-ink-900 mb-4">Itinerario día a día</h3>
                <div className="space-y-4">
                  {itinerary.map((d) => (
                    <div key={d.day} className="flex gap-4">
                      <div className="shrink-0 w-10 h-10 rounded-xl text-white font-display font-bold flex items-center justify-center"
                        style={{ background: primary }}>{d.day}</div>
                      <div>
                        <p className="font-semibold text-ink-900">{d.title}</p>
                        <p className="text-sm text-ink-500 mt-0.5">{d.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
            {(includes?.length > 0 || excludes?.length > 0) && (
              <div className="grid sm:grid-cols-2 gap-4 mt-6 pt-6 border-t border-ink-100" data-testid="public-includes-excludes">
                {includes?.length > 0 && (
                  <div>
                    <h3 className="font-display font-semibold text-ink-900 mb-3">Incluye</h3>
                    <ul className="space-y-1.5 text-sm">
                      {includes.map((x, i) => <li key={i} className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 mt-0.5 text-emerald-600 shrink-0" />{x}</li>)}
                    </ul>
                  </div>
                )}
                {excludes?.length > 0 && (
                  <div>
                    <h3 className="font-display font-semibold text-ink-900 mb-3">No incluye</h3>
                    <ul className="space-y-1.5 text-sm">
                      {excludes.map((x, i) => <li key={i} className="flex items-start gap-2 text-ink-500">• {x}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <footer className="text-center text-xs text-ink-400 pt-6">
          {q.exec_name && <p className="mb-2 text-ink-600">Tu ejecutivo: <b>{q.exec_name}</b></p>}
          Cotización generada por <b style={{ color: primary }}>{company.name}</b><br />
          {company.contact_email} · {company.contact_phone}
        </footer>
      </main>
    </div>
  );
}
