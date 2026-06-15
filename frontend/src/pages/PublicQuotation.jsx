import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import api, { formatApiError } from '@/lib/api';
import { CheckCircle2, Calendar, MapPin, Users, FileText, Sparkles, CreditCard, Loader2 } from 'lucide-react';

function money(v, c = 'MXN') { return `$${Number(v || 0).toLocaleString('es-MX')} ${c}`; }

const OCC = { sencilla: 1, doble: 2, triple: 3, cuadruple: 4 };

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

  const load = async () => {
    try {
      const { data } = await api.get(`/public/quotations/${token}`);
      setData(data);
      if (data.quotation?.accepted_at) setAccepted(true);
    } catch (e) { setError(formatApiError(e)); }
  };
  useEffect(() => { load(); }, [token]); // eslint-disable-line

  // Detect return from Stripe and poll status
  useEffect(() => {
    const sessionId = searchParams.get('session_id');
    if (!sessionId) return;
    let attempts = 0;
    setPayMsg({ type: 'pending', text: 'Verificando tu pago…' });
    const poll = async () => {
      try {
        const { data: st } = await api.get(`/public/quotations/${token}/payment-status/${sessionId}`);
        if (st.payment_status === 'paid') {
          setPayMsg({ type: 'success', text: '¡Pago confirmado! Gracias por tu reserva.' });
          await load();
          return;
        }
        if (st.status === 'expired') {
          setPayMsg({ type: 'error', text: 'La sesión de pago expiró. Intenta de nuevo.' });
          return;
        }
        if (attempts++ < 6) { setTimeout(poll, 2000); }
        else setPayMsg({ type: 'error', text: 'No pudimos confirmar el pago aún. Revisa más tarde.' });
      } catch (_e) {
        if (attempts++ < 6) setTimeout(poll, 2000);
        else setPayMsg({ type: 'error', text: 'Error verificando el pago.' });
      }
    };
    poll();
    // clear the session_id from URL so refresh doesn't re-poll endlessly
    const sp = new URLSearchParams(searchParams); sp.delete('session_id'); setSearchParams(sp, { replace: true });
  }, [token]); // eslint-disable-line

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
  const primary = company.primary_color || '#185FA5';
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
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-end">
          <span className="text-xs font-mono text-ink-500">{q.code}</span>
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
          <p className="text-ink-500 mt-3 text-lg">{q.package_snapshot?.name}</p>
        </div>
      </section>

      <main className="max-w-3xl mx-auto px-4 pb-20 space-y-6">
        {/* Summary */}
        <div className="card-surface p-6 grid sm:grid-cols-2 gap-4">
          <div className="flex items-start gap-3">
            <MapPin className="w-5 h-5 mt-0.5" style={{ color: primary }} />
            <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Hotel</p>
              <p className="font-semibold text-ink-900">{q.hotel_selected}</p></div>
          </div>
          <div className="flex items-start gap-3">
            <Calendar className="w-5 h-5 mt-0.5" style={{ color: primary }} />
            <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Fechas</p>
              <p className="font-semibold text-ink-900">{q.dates?.start} → {q.dates?.end}</p></div>
          </div>
          <div className="flex items-start gap-3 sm:col-span-2">
            <Users className="w-5 h-5 mt-0.5" style={{ color: primary }} />
            <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Habitaciones / Pax</p>
              <p className="font-semibold text-ink-900">{paxDesc}</p></div>
          </div>
        </div>

        {/* Itinerary */}
        {itinerary?.length > 0 && (
          <div className="card-surface p-6">
            <h2 className="font-display text-xl font-semibold text-ink-900 mb-4">Itinerario día a día</h2>
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
          </div>
        )}

        {/* Includes / Excludes */}
        {(includes?.length > 0 || excludes?.length > 0) && (
          <div className="grid sm:grid-cols-2 gap-4">
            {includes?.length > 0 && (
              <div className="card-surface p-5">
                <h3 className="font-display font-semibold text-ink-900 mb-3">Incluye</h3>
                <ul className="space-y-1.5 text-sm">
                  {includes.map((x, i) => <li key={i} className="flex items-start gap-2"><CheckCircle2 className="w-4 h-4 mt-0.5 text-emerald-600" />{x}</li>)}
                </ul>
              </div>
            )}
            {excludes?.length > 0 && (
              <div className="card-surface p-5">
                <h3 className="font-display font-semibold text-ink-900 mb-3">No incluye</h3>
                <ul className="space-y-1.5 text-sm">
                  {excludes.map((x, i) => <li key={i} className="flex items-start gap-2 text-ink-500">• {x}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Servicios a la carta */}
        {(q.items || []).some((it) => it.kind === 'servicio') && (
          <div className="card-surface p-6" data-testid="public-services">
            <h2 className="font-display text-xl font-semibold text-ink-900 mb-4">Servicios adicionales incluidos</h2>
            <div className="space-y-2">
              {(q.items || []).filter((it) => it.kind === 'servicio').map((it, i) => (
                <div key={i} className="flex items-center justify-between py-2 border-b border-ink-100 last:border-0">
                  <div className="flex items-center gap-3">
                    <Sparkles className="w-4 h-4" style={{ color: primary }} />
                    <div>
                      <p className="font-medium text-ink-900">{it.label}</p>
                      <p className="text-xs text-ink-400">{money(it.unit_price, q.currency)} × {it.qty}</p>
                    </div>
                  </div>
                  <p className="font-semibold text-ink-900">{money(it.subtotal, q.currency)}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Total + Accept */}
        <div className="card-surface p-6 sticky bottom-4" data-testid="public-total-card">
          <div className="flex items-center justify-between mb-2">
            <p className="text-ink-500 text-sm">Total final</p>
            <p className="font-display text-3xl md:text-4xl font-bold" style={{ color: primary }}>{money(finalTotal, q.currency)}</p>
          </div>
          {payment?.total_usd_equivalent && payment?.base_currency === 'MXN' && (
            <p className="text-right text-xs text-ink-400 mb-4" data-testid="usd-equivalent">≈ ${Number(payment.total_usd_equivalent).toLocaleString('en-US')} USD (TC {payment.rate_mxn_per_usd})</p>
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

        <footer className="text-center text-xs text-ink-400 pt-6">
          Cotización generada por <b style={{ color: primary }}>{company.name}</b><br />
          {company.contact_email} · {company.contact_phone}
        </footer>
      </main>
    </div>
  );
}
