import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import api, { formatApiError } from '@/lib/api';
import Logo from '@/components/Logo';
import { CheckCircle2, Eye, EyeOff, ArrowRight } from 'lucide-react';

export default function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get('token') || '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (password.length < 8) { setError('La contraseña debe tener al menos 8 caracteres.'); return; }
    if (password !== confirm) { setError('Las contraseñas no coinciden.'); return; }
    setLoading(true);
    try {
      await api.post('/auth/reset-password', { token, password });
      setDone(true);
      setTimeout(() => navigate('/login', { replace: true }), 2500);
    } catch (e) { setError(formatApiError(e)); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-cream p-6">
      <div className="w-full max-w-md space-y-6" data-testid="reset-password-card">
        <Logo size={32} />
        {!token ? (
          <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm" data-testid="reset-no-token">
            Enlace inválido. Solicita uno nuevo desde "¿Olvidaste tu contraseña?".
          </div>
        ) : done ? (
          <div className="text-center" data-testid="reset-success">
            <CheckCircle2 className="w-14 h-14 mx-auto text-emerald-500 mb-3" />
            <h1 className="font-display text-2xl font-semibold text-ink-900">¡Contraseña actualizada!</h1>
            <p className="text-ink-500 mt-2">Te llevamos al inicio de sesión…</p>
          </div>
        ) : (
          <>
            <div>
              <h1 className="font-display text-3xl font-semibold text-ink-900">Crea tu nueva contraseña</h1>
              <p className="text-ink-500 mt-2">Elige una contraseña segura (mínimo 8 caracteres).</p>
            </div>
            {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm" data-testid="reset-error">{error}</div>}
            <form onSubmit={submit} className="space-y-4" data-testid="reset-form">
              <div>
                <label className="label-text">Nueva contraseña</label>
                <div className="relative">
                  <input type={show ? 'text' : 'password'} className="input-field pr-11" value={password}
                    onChange={(e) => setPassword(e.target.value)} data-testid="reset-password-input" />
                  <button type="button" onClick={() => setShow((v) => !v)} className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-ink-400 hover:text-brand-500">
                    {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <div>
                <label className="label-text">Confirmar contraseña</label>
                <input type={show ? 'text' : 'password'} className="input-field" value={confirm}
                  onChange={(e) => setConfirm(e.target.value)} data-testid="reset-confirm-input" />
              </div>
              <button type="submit" disabled={loading} className="btn-primary w-full justify-center" data-testid="reset-submit-btn">
                {loading ? 'Guardando…' : 'Guardar contraseña'} {!loading && <ArrowRight className="w-4 h-4" />}
              </button>
            </form>
          </>
        )}
        <p className="text-center text-sm text-ink-500"><Link to="/login" className="hover:text-brand-500">← Volver al inicio de sesión</Link></p>
      </div>
    </div>
  );
}
