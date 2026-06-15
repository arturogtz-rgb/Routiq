import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import api, { formatApiError } from '@/lib/api';
import Logo from '@/components/Logo';
import { ArrowRight, Eye, EyeOff, CheckCircle2, Building2, Bot, CreditCard, Landmark, BadgeCheck } from 'lucide-react';

const PLANS = {
  starter: { label: 'Starter', desc: 'Hasta 3 ejecutivos · Pago por transferencia', perks: ['Hasta 3 ejecutivos', 'Cotizaciones ilimitadas', 'PDF con tu marca', 'Pago por transferencia'] },
  pro: { label: 'Pro', desc: 'Hasta 15 ejecutivos · IA + Stripe', perks: ['Hasta 15 ejecutivos', 'IA operativa (Claude)', 'Cobros con Stripe', 'Kanban + alertas'] },
  enterprise: { label: 'Enterprise', desc: 'Ejecutivos ilimitados · Marca blanca', perks: ['Ejecutivos ilimitados', 'Marca blanca (sin Routiq)', 'IA + Stripe + transferencia', 'Onboarding dedicado'] },
};

export default function Signup() {
  const [params] = useSearchParams();
  const initialPlan = ['starter', 'pro', 'enterprise'].includes(params.get('plan')) ? params.get('plan') : 'pro';
  const [form, setForm] = useState({
    company_name: '', admin_name: '', admin_email: '', admin_phone: '',
    plan: initialPlan, admin_password: '',
  });
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError(''); setLoading(true);
    try {
      await api.post('/signup', { ...form, admin_email: form.admin_email.trim().toLowerCase() });
      setDone(true);
    } catch (err) { setError(formatApiError(err)); }
    finally { setLoading(false); }
  };

  const plan = PLANS[form.plan];

  if (done) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream p-6">
        <div className="w-full max-w-md card-surface p-8 text-center" data-testid="signup-success">
          <div className="w-16 h-16 rounded-full bg-mint-100 text-emerald-700 flex items-center justify-center mx-auto"><CheckCircle2 className="w-8 h-8" /></div>
          <h1 className="font-display text-2xl font-semibold text-ink-900 mt-5">¡Solicitud enviada!</h1>
          <p className="text-ink-500 mt-2">Recibimos tu solicitud para <span className="font-semibold text-ink-900">{form.company_name}</span>. Nuestro equipo la revisará y, al aprobarla, recibirás un correo de bienvenida en <span className="font-semibold text-ink-900">{form.admin_email}</span> con el acceso a tu cuenta.</p>
          <Link to="/" className="btn-primary w-full justify-center mt-6" data-testid="signup-back-home">Volver al inicio</Link>
          <p className="text-sm text-ink-500 mt-3"><Link to="/login" className="hover:text-brand-500">Ya tengo cuenta — Entrar</Link></p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-cream">
      {/* Brand / plan summary */}
      <div className="hidden lg:flex flex-col justify-between text-white p-10 relative overflow-hidden bg-brand-500" data-testid="signup-brand-panel">
        <div className="absolute inset-0 grain opacity-20" />
        <div className="relative"><Logo size={32} white /></div>
        <div className="relative space-y-5 max-w-md">
          <p className="pill bg-white/10 text-white">Plan {plan.label}</p>
          <h2 className="font-display text-4xl font-semibold leading-tight">Empieza a cotizar como un equipo profesional.</h2>
          <ul className="space-y-2 text-white/90">
            {plan.perks.map((p) => (
              <li key={p} className="flex items-start gap-2"><CheckCircle2 className="w-5 h-5 mt-0.5 text-mint-100" />{p}</li>
            ))}
          </ul>
        </div>
        <div className="relative text-sm text-white/70">© 2026 Routiq</div>
      </div>

      {/* Form */}
      <div className="flex items-center justify-center p-6 md:p-10">
        <div className="w-full max-w-md space-y-6" data-testid="signup-card">
          <div className="lg:hidden mb-2"><Logo size={30} /></div>
          <div>
            <h1 className="font-display text-3xl font-semibold text-ink-900">Crea tu cuenta de empresa</h1>
            <p className="text-ink-500 mt-2">Cuéntanos sobre tu operación y te damos acceso.</p>
          </div>

          {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm" data-testid="signup-error">{error}</div>}

          <form onSubmit={submit} className="space-y-4" data-testid="signup-form">
            <div>
              <label className="label-text">Plan</label>
              <div className="grid grid-cols-3 gap-2">
                {['starter', 'pro', 'enterprise'].map((p) => (
                  <button type="button" key={p} onClick={() => setForm((f) => ({ ...f, plan: p }))} data-testid={`signup-plan-${p}`}
                    className={`rounded-xl border-2 px-2 py-2.5 text-center transition-colors ${form.plan === p ? 'border-brand-500 bg-brand-50' : 'border-ink-100 hover:border-ink-200'}`}>
                    <p className="font-display font-semibold text-ink-900 text-sm">{PLANS[p].label}</p>
                  </button>
                ))}
              </div>
              <p className="text-xs text-ink-400 mt-1.5">{plan.desc}</p>
            </div>
            <div>
              <label className="label-text">Nombre de la empresa</label>
              <input required value={form.company_name} onChange={set('company_name')} className="input-field" placeholder="Aventúrate por Jalisco" data-testid="signup-company-input" />
            </div>
            <div>
              <label className="label-text">Tu nombre (administrador)</label>
              <input required value={form.admin_name} onChange={set('admin_name')} className="input-field" placeholder="Nombre y apellido" data-testid="signup-admin-name-input" />
            </div>
            <div className="grid sm:grid-cols-2 gap-3">
              <div>
                <label className="label-text">Correo</label>
                <input type="email" required value={form.admin_email} onChange={set('admin_email')} className="input-field" placeholder="tu@empresa.com" data-testid="signup-email-input" />
              </div>
              <div>
                <label className="label-text">Teléfono</label>
                <input value={form.admin_phone} onChange={set('admin_phone')} className="input-field" placeholder="+52 ..." data-testid="signup-phone-input" />
              </div>
            </div>
            <div>
              <label className="label-text">Contraseña (mín. 8)</label>
              <div className="relative">
                <input type={showPwd ? 'text' : 'password'} required minLength={8} value={form.admin_password} onChange={set('admin_password')}
                  className="input-field pr-11" placeholder="••••••••" data-testid="signup-password-input" />
                <button type="button" onClick={() => setShowPwd((v) => !v)} className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-ink-400 hover:text-brand-500" data-testid="signup-toggle-password">
                  {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <p className="text-xs text-ink-400 mt-1">Usarás este correo y contraseña para entrar una vez aprobada tu cuenta.</p>
            </div>
            <button type="submit" disabled={loading || form.admin_password.length < 8} className="btn-primary w-full justify-center" data-testid="signup-submit-btn">
              {loading ? 'Enviando…' : 'Solicitar acceso'} {!loading && <ArrowRight className="w-4 h-4" />}
            </button>
          </form>

          <p className="text-center text-sm text-ink-500">
            ¿Ya tienes cuenta? <Link to="/login" className="font-semibold hover:text-brand-500" data-testid="signup-login-link">Entrar</Link>
            <span className="mx-2">·</span>
            <Link to="/" className="hover:text-brand-500" data-testid="signup-back-to-landing">Volver al sitio</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
