import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import Logo from '@/components/Logo';
import { ArrowRight, Eye, EyeOff } from 'lucide-react';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    const res = await login(email.trim(), password);
    setLoading(false);
    if (res.ok) {
      const target =
        res.user.role === 'super_admin' ? '/master'
        : (location.state?.from?.pathname?.startsWith('/app') ? location.state.from.pathname : '/app/dashboard');
      navigate(target, { replace: true });
    } else {
      setError(res.error || 'No pudimos iniciar sesión');
    }
  };

  const quickFill = (em, pw) => { setEmail(em); setPassword(pw); };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-cream">
      <div className="hidden lg:flex flex-col justify-between bg-brand-500 text-white p-10 relative overflow-hidden">
        <div className="absolute inset-0 grain opacity-20" />
        <div className="relative">
          <Logo size={32} white />
        </div>
        <div className="relative space-y-4 max-w-md">
          <p className="pill bg-white/10 text-white">Para tour operadores</p>
          <h2 className="font-display text-4xl font-semibold leading-tight">“Antes perdía cotizaciones en el chat. Ahora cierro 3x más rápido.”</h2>
          <p className="text-brand-50">— Piloto en producción: Aventúrate por Jalisco</p>
        </div>
        <div className="relative text-sm text-brand-50/80">© 2026 Routiq</div>
      </div>

      <div className="flex items-center justify-center p-6 md:p-10">
        <div className="w-full max-w-md space-y-6" data-testid="login-card">
          <div className="lg:hidden mb-4"><Logo size={30} /></div>
          <div>
            <h1 className="font-display text-3xl font-semibold text-ink-900">Bienvenido de vuelta</h1>
            <p className="text-ink-500 mt-2">Entra a tu panel de Routiq.</p>
          </div>

          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm" data-testid="login-error">
              {error}
            </div>
          )}

          <form onSubmit={onSubmit} className="space-y-4" data-testid="login-form">
            <div>
              <label className="label-text">Correo</label>
              <input
                type="email" autoComplete="email" required value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input-field" placeholder="tucorreo@empresa.com"
                data-testid="login-email-input"
              />
            </div>
            <div>
              <label className="label-text">Contraseña</label>
              <div className="relative">
                <input
                  type={showPwd ? 'text' : 'password'} autoComplete="current-password" required
                  value={password} onChange={(e) => setPassword(e.target.value)}
                  className="input-field pr-11" placeholder="••••••••"
                  data-testid="login-password-input"
                />
                <button type="button" onClick={() => setShowPwd((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-ink-400 hover:text-brand-500"
                  data-testid="toggle-password">
                  {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <button type="submit" disabled={loading}
              className="btn-primary w-full justify-center"
              data-testid="login-submit-btn">
              {loading ? 'Entrando…' : 'Entrar'} {!loading && <ArrowRight className="w-4 h-4" />}
            </button>
          </form>

          <div className="rounded-xl border border-dashed border-ink-200 bg-white p-4 text-sm">
            <p className="font-semibold text-ink-900 mb-2">Credenciales de demo</p>
            <div className="space-y-2">
              <button onClick={() => quickFill('admin@aventurate.mx', 'Demo2026!')}
                className="w-full text-left px-3 py-2 rounded-lg hover:bg-brand-50 transition-colors"
                data-testid="demo-company-admin">
                <span className="font-semibold text-brand-500">Admin empresa</span> — admin@aventurate.mx / Demo2026!
              </button>
              <button onClick={() => quickFill('ejecutivo@aventurate.mx', 'Demo2026!')}
                className="w-full text-left px-3 py-2 rounded-lg hover:bg-brand-50 transition-colors"
                data-testid="demo-executive">
                <span className="font-semibold text-brand-500">Ejecutivo</span> — ejecutivo@aventurate.mx / Demo2026!
              </button>
              <button onClick={() => quickFill('owner@routiq.mx', 'Routiq2026!')}
                className="w-full text-left px-3 py-2 rounded-lg hover:bg-brand-50 transition-colors"
                data-testid="demo-super-admin">
                <span className="font-semibold text-brand-500">Master (SaaS)</span> — owner@routiq.mx / Routiq2026!
              </button>
            </div>
          </div>

          <p className="text-center text-sm text-ink-500">
            <Link to="/" className="hover:text-brand-500" data-testid="back-to-landing">← Volver al sitio</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
