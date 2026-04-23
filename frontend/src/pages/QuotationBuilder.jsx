import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { ArrowLeft, ArrowRight, Check, User, Package, CalendarDays, Calculator, FileText, Plus } from 'lucide-react';

const STEPS = [
  { key: 'client', label: 'Cliente', icon: User },
  { key: 'package', label: 'Paquete', icon: Package },
  { key: 'dates', label: 'Fechas y pax', icon: CalendarDays },
  { key: 'review', label: 'Revisión', icon: Calculator },
];

function money(v, c = 'MXN') { return `$${Number(v || 0).toLocaleString('es-MX')} ${c}`; }

export default function QuotationBuilder() {
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const [step, setStep] = useState(0);
  const [clients, setClients] = useState([]);
  const [packages, setPackages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showClient, setShowClient] = useState(false);
  const [newClient, setNewClient] = useState({ name: '', phone: '', email: '', channel: 'directo' });

  const [form, setForm] = useState({
    client_id: '',
    package_id: search.get('package') || '',
    hotel_name: '',
    dates: { start: '', end: '' },
    pax: { adultos: 2, menores: 0, ocupacion: 'doble' },
    notes: '',
  });

  useEffect(() => {
    (async () => {
      const [c, p] = await Promise.all([api.get('/clients'), api.get('/packages')]);
      setClients(c.data); setPackages(p.data);
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

  const subtotal = (() => {
    if (!hotel) return 0;
    const adult = Number(hotel.prices_by_occupancy?.[form.pax.ocupacion] || 0) * form.pax.adultos;
    const minor = Number(hotel.minor_price || 0) * form.pax.menores;
    return adult + minor;
  })();
  const commission = Math.round(subtotal * commissionRate * 100) / 100;
  const total = subtotal - commission;

  const canNext = () =>
    (step === 0 && !!form.client_id) ||
    (step === 1 && !!form.package_id && !!form.hotel_name) ||
    (step === 2 && form.dates.start && form.dates.end && form.pax.adultos >= 0);

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
      const { data } = await api.post('/quotations', form);
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
      <p className="text-ink-500 mb-8">Construye una cotización de paquete armado en 4 pasos.</p>

      {/* Stepper */}
      <div className="grid grid-cols-4 gap-2 mb-8">
        {STEPS.map((s, i) => (
          <div key={s.key} className={`rounded-xl p-3 border text-xs font-semibold uppercase tracking-wider text-center transition-all
              ${i === step ? 'bg-brand-500 text-white border-brand-500'
                : i < step ? 'bg-mint-100 text-emerald-700 border-mint-200' : 'bg-white text-ink-400 border-ink-100'}`}
              data-testid={`step-${s.key}`}>
            <div className="flex items-center justify-center gap-2">
              {i < step ? <Check className="w-4 h-4" /> : <s.icon className="w-4 h-4" />}
              <span className="hidden sm:inline">{s.label}</span>
            </div>
          </div>
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
          <div className="space-y-4" data-testid="step-dates-panel">
            <h2 className="font-display text-xl font-semibold text-ink-900">Fechas y pasajeros</h2>
            <div className="grid md:grid-cols-2 gap-4">
              <div><label className="label-text">Check-in</label>
                <input type="date" className="input-field" value={form.dates.start} onChange={(e) => setForm((f) => ({ ...f, dates: { ...f.dates, start: e.target.value } }))} data-testid="date-start" />
              </div>
              <div><label className="label-text">Check-out</label>
                <input type="date" className="input-field" value={form.dates.end} onChange={(e) => setForm((f) => ({ ...f, dates: { ...f.dates, end: e.target.value } }))} data-testid="date-end" />
              </div>
              <div><label className="label-text">Ocupación</label>
                <select className="input-field" value={form.pax.ocupacion} onChange={(e) => setForm((f) => ({ ...f, pax: { ...f.pax, ocupacion: e.target.value } }))} data-testid="pax-ocupacion">
                  <option value="sencilla">Sencilla</option><option value="doble">Doble</option>
                  <option value="triple">Triple</option><option value="cuadruple">Cuádruple</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="label-text">Adultos</label>
                  <input type="number" min="1" className="input-field" value={form.pax.adultos} onChange={(e) => setForm((f) => ({ ...f, pax: { ...f.pax, adultos: +e.target.value } }))} data-testid="pax-adultos" /></div>
                <div><label className="label-text">Menores</label>
                  <input type="number" min="0" className="input-field" value={form.pax.menores} onChange={(e) => setForm((f) => ({ ...f, pax: { ...f.pax, menores: +e.target.value } }))} data-testid="pax-menores" /></div>
              </div>
            </div>
            <div>
              <label className="label-text">Notas internas</label>
              <textarea rows="3" className="input-field" value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} data-testid="builder-notes" />
            </div>
          </div>
        )}

        {/* Step: Review */}
        {step === 3 && (
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
                <p className="font-semibold text-ink-900">{form.dates.start} → {form.dates.end}</p>
                <p className="text-ink-500">{pack?.nights} noches</p>
              </div>
              <div className="rounded-xl border border-ink-100 p-4">
                <p className="text-xs uppercase tracking-widest font-bold text-ink-400 mb-1">Pasajeros</p>
                <p className="font-semibold text-ink-900">{form.pax.adultos} adultos · {form.pax.menores} menores</p>
                <p className="text-ink-500 capitalize">{form.pax.ocupacion}</p>
              </div>
            </div>

            <div className="rounded-xl bg-gradient-to-br from-brand-500 to-accent text-white p-5" data-testid="builder-totals">
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
