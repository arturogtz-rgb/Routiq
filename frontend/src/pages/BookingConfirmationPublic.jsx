import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api, { formatApiError } from '@/lib/api';
import { CalendarPlus, Download, Landmark, Copy, BedDouble, MapPin, Users } from 'lucide-react';
import { formatDateEs } from '@/lib/dates';

function money(v, c = 'MXN') { return `$${Number(v || 0).toLocaleString('es-MX')} ${c}`; }
const ymd = (iso) => (iso || '').slice(0, 10).replaceAll('-', '');
const addOneDay = (iso) => {
  try { const d = new Date(`${iso}T00:00:00`); d.setDate(d.getDate() + 1); return d.toISOString().slice(0, 10); }
  catch { return iso; }
};

export default function BookingConfirmationPublic() {
  const { token } = useParams();
  const backend = process.env.REACT_APP_BACKEND_URL || '';
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try { const { data } = await api.get(`/public/booking-confirmation/${token}`); setData(data); }
      catch (e) { setError(formatApiError(e)); }
    })();
  }, [token]);

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

  const { confirmation: c, company } = data;
  const primary = 'rgb(var(--brand-500))';
  const start = c.trip_start;
  const end = c.trip_end || c.trip_start;
  const hasDates = !!start;
  const title = `Viaje con ${company.name || 'tu agencia'} — ${c.code}`;
  const location = (c.lodging?.[0]?.hotel) || company.name || '';
  const details = `Confirmación de Reserva ${c.code}. Pasajero: ${c.passenger_name || c.agent_name || ''}. Personas: ${c.num_persons || ''}.`;

  const googleUrl = hasDates
    ? `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(title)}&dates=${ymd(start)}/${ymd(addOneDay(end))}&details=${encodeURIComponent(details)}&location=${encodeURIComponent(location)}`
    : '';

  const downloadIcs = () => {
    if (!hasDates) return;
    const stamp = new Date().toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
    const ics = [
      'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Routiq//ReservaTuristica//ES', 'CALSCALE:GREGORIAN',
      'BEGIN:VEVENT', `UID:${token}@routiq`, `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${ymd(start)}`, `DTEND;VALUE=DATE:${ymd(addOneDay(end))}`,
      `SUMMARY:${title}`, `DESCRIPTION:${details.replace(/\n/g, '\\n')}`, `LOCATION:${location}`,
      'END:VEVENT', 'END:VCALENDAR',
    ].join('\r\n');
    const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${c.code}.ics`; document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  };

  const bank = company.bank;
  const services = (c.services || []).filter((s) => s.service || s.details || s.date || s.persons || s.observations);
  const lodging = (c.lodging || []).filter((l) => l.hotel || l.checkin || l.checkout || l.room_type || l.confirmation_number || l.guest_name);

  return (
    <div className="min-h-screen bg-cream" data-testid="public-booking-page">
      <header className="bg-white border-b border-ink-100 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between gap-3">
          <span className="text-xs font-mono text-ink-500">{c.code}</span>
          <a href={`${backend}/api/public/booking-confirmation/${token}/pdf`} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-2 text-sm font-semibold px-3 py-2 rounded-xl border-2 transition-all hover:bg-cream"
            style={{ borderColor: primary, color: primary }} data-testid="booking-download-pdf-btn">
            <Download className="w-4 h-4" /> Descargar PDF
          </a>
        </div>
      </header>

      <section className="bg-gradient-to-br from-white to-brand-50/40">
        <div className="max-w-3xl mx-auto px-4 py-12 text-center">
          {company.logo_url ? (
            <img src={`${backend}${company.logo_url}`} alt={company.name}
              className="h-28 md:h-36 max-w-[280px] object-contain mx-auto mb-5 drop-shadow-sm" data-testid="booking-logo" />
          ) : (
            <div className="font-display font-bold text-3xl mb-3" style={{ color: primary }}>{company.name}</div>
          )}
          <p className="pill inline-block mb-3" style={{ background: `${primary}15`, color: primary }}>Confirmación de Reserva</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold text-ink-900">¡Tu reserva está confirmada! 🎉</h1>
          {c.passenger_name && <p className="text-ink-500 mt-2 text-lg">A nombre de {c.passenger_name}</p>}
        </div>
      </section>

      <main className="max-w-3xl mx-auto px-4 pb-20 space-y-6 pt-6">
        {/* Agregar al calendario */}
        {hasDates && (
          <div className="card-surface p-6" data-testid="add-to-calendar">
            <div className="flex items-start gap-3 mb-4">
              <CalendarPlus className="w-6 h-6 shrink-0" style={{ color: primary }} />
              <div>
                <h2 className="font-display text-lg font-semibold text-ink-900">Agrega tu viaje al calendario</h2>
                <p className="text-sm text-ink-500">{formatDateEs(start)} → {formatDateEs(end)}</p>
              </div>
            </div>
            <div className="grid sm:grid-cols-2 gap-3">
              <button onClick={downloadIcs} data-testid="ics-download-btn"
                className="w-full inline-flex items-center justify-center gap-2 font-display font-semibold py-3 rounded-xl text-white transition-all hover:scale-[1.01]"
                style={{ background: primary }}>
                <Download className="w-5 h-5" /> Descargar .ics (Apple/Outlook)
              </button>
              <a href={googleUrl} target="_blank" rel="noreferrer" data-testid="gcal-btn"
                className="w-full inline-flex items-center justify-center gap-2 font-display font-semibold py-3 rounded-xl border-2 transition-all hover:bg-brand-50"
                style={{ borderColor: primary, color: primary }}>
                <CalendarPlus className="w-5 h-5" /> Google Calendar
              </a>
            </div>
          </div>
        )}

        {/* Datos de la reserva */}
        <div className="card-surface p-6 grid sm:grid-cols-2 gap-4" data-testid="booking-summary">
          {c.agent_name && (
            <div className="flex items-start gap-3"><Users className="w-5 h-5 mt-0.5" style={{ color: primary }} />
              <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Agente / Cliente</p>
                <p className="font-semibold text-ink-900">{c.agent_name}</p>{c.agent_company && <p className="text-xs text-ink-400">{c.agent_company}</p>}</div></div>
          )}
          {c.passenger_name && (
            <div className="flex items-start gap-3"><Users className="w-5 h-5 mt-0.5" style={{ color: primary }} />
              <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Pasajero</p>
                <p className="font-semibold text-ink-900">{c.passenger_name}</p>{c.passenger_phone && <p className="text-xs text-ink-400">{c.passenger_phone}</p>}</div></div>
          )}
          {c.num_persons && (
            <div className="flex items-start gap-3"><Users className="w-5 h-5 mt-0.5" style={{ color: primary }} />
              <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Personas</p>
                <p className="font-semibold text-ink-900">{c.num_persons}</p></div></div>
          )}
          {c.reservation_date && (
            <div className="flex items-start gap-3"><CalendarPlus className="w-5 h-5 mt-0.5" style={{ color: primary }} />
              <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Fecha de reservación</p>
                <p className="font-semibold text-ink-900">{c.reservation_date}</p></div></div>
          )}
        </div>

        {/* Servicios */}
        {services.length > 0 && (
          <div className="card-surface p-6" data-testid="booking-services">
            <h2 className="font-display text-xl font-semibold text-ink-900 mb-4">Servicios confirmados</h2>
            <div className="space-y-3">
              {services.map((s, i) => (
                <div key={i} className="flex items-start gap-3 py-2 border-b border-ink-100 last:border-0">
                  <MapPin className="w-4 h-4 mt-1 shrink-0" style={{ color: primary }} />
                  <div>
                    <p className="font-medium text-ink-900">{s.service}{s.date ? ` · ${s.date}` : ''}</p>
                    {s.details && <p className="text-sm text-ink-500">{s.details}</p>}
                    {(s.persons || s.observations) && <p className="text-xs text-ink-400 mt-0.5">{[s.persons && `${s.persons} pers.`, s.observations].filter(Boolean).join(' · ')}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Hospedaje */}
        {lodging.length > 0 && (
          <div className="card-surface p-6" data-testid="booking-lodging">
            <h2 className="font-display text-xl font-semibold text-ink-900 mb-4">Hospedaje</h2>
            <div className="space-y-3">
              {lodging.map((l, i) => (
                <div key={i} className="flex items-start gap-3 py-2 border-b border-ink-100 last:border-0">
                  <BedDouble className="w-4 h-4 mt-1 shrink-0" style={{ color: primary }} />
                  <div>
                    <p className="font-medium text-ink-900">{l.hotel}{l.plan ? ` · ${l.plan}` : ''}</p>
                    <p className="text-sm text-ink-500">{[l.checkin && `Check-in ${l.checkin}`, l.checkout && `Check-out ${l.checkout}`, l.nights && `${l.nights} noches`].filter(Boolean).join(' · ')}</p>
                    {(l.room_type || l.confirmation_number || l.guest_name) && <p className="text-xs text-ink-400 mt-0.5">{[l.room_type, l.guest_name, l.confirmation_number && `N° ${l.confirmation_number}`].filter(Boolean).join(' · ')}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Observaciones */}
        {c.general_observations && (
          <div className="card-surface p-6" data-testid="booking-observations">
            <h2 className="font-display text-xl font-semibold text-ink-900 mb-3">Observaciones generales</h2>
            <p className="text-sm text-ink-600 whitespace-pre-line">{c.general_observations}</p>
          </div>
        )}

        {/* Precio */}
        {(c.total_amount > 0 || c.price_per_person > 0) && (
          <div className="card-surface p-6" data-testid="booking-price">
            {c.price_per_person > 0 && (
              <div className="flex items-center justify-between text-sm text-ink-600 mb-2">
                <span>Precio por persona</span><span className="font-medium">{money(c.price_per_person, c.currency)}</span>
              </div>
            )}
            <div className="flex items-center justify-between pt-2 border-t border-ink-100">
              <span className="font-semibold text-ink-900">Total a pagar</span>
              <span className="font-display text-2xl font-bold" style={{ color: primary }}>{money(c.total_amount, c.currency)}</span>
            </div>
          </div>
        )}

        {/* Datos bancarios */}
        {bank && (bank.name || bank.clabe || bank.account) && (
          <div className="card-surface p-6" data-testid="booking-bank">
            <p className="font-semibold text-ink-900 flex items-center gap-2 mb-3"><Landmark className="w-4 h-4" style={{ color: primary }} /> Datos para transferencia bancaria</p>
            <div className="space-y-1.5 text-sm">
              {[['Banco', bank.name], ['Beneficiario', bank.holder], ['CLABE', bank.clabe], ['Cuenta', bank.account],
                ['Cuenta USD', bank.usd_account], ['SWIFT/BIC', bank.swift], ['Sucursal', bank.branch], ['Referencia', bank.reference]]
                .filter(([, v]) => v).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between gap-3 py-1 border-b border-ink-100 last:border-0">
                    <span className="text-ink-400">{k}</span>
                    <span className="font-medium text-ink-900 text-right break-all">{v}
                      <button className="ml-2 text-ink-300 hover:text-ink-600 align-middle" onClick={() => navigator.clipboard.writeText(v)} title="Copiar"><Copy className="w-3 h-3 inline" /></button>
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}

        <footer className="text-center text-xs text-ink-400 pt-6">
          Confirmación generada por <b style={{ color: primary }}>{company.name}</b><br />
          {company.contact_email} · {company.contact_phone}
          {!company.white_label && <p className="mt-3 text-ink-300">Generado con Routiq · routiq.com.mx</p>}
        </footer>
      </main>
    </div>
  );
}
