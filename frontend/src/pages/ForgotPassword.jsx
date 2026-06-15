import { useState } from 'react';
import { Link } from 'react-router-dom';
import api, { formatApiError } from '@/lib/api';
import Logo from '@/components/Logo';
import { MailCheck, ArrowRight } from 'lucide-react';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(''); setLoading(true);
    try {
      await api.post('/auth/forgot-password', { email: email.trim(), base_url: window.location.origin });
      setSent(true);
    } catch (e) { setError(formatApiError(e)); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-cream p-6">
      <div className="w-full max-w-md space-y-6" data-testid="forgot-card">
        <Logo size={32} />
        {sent ? (
          <div className="text-center" data-testid="forgot-success">
            <MailCheck className="w-14 h-14 mx-auto text-emerald-500 mb-3" />
            <h1 className="font-display text-2xl font-semibold text-ink-900">Revisa tu correo</h1>
            <p className="text-ink-500 mt-2">Si <b>{email}</b> tiene una cuenta, te enviamos un enlace para restablecer tu contraseña. El enlace expira en 1 hora.</p>
          </div>
        ) : (
          <>
            <div>
              <h1 className="font-display text-3xl font-semibold text-ink-900">¿Olvidaste tu contraseña?</h1>
              <p className="text-ink-500 mt-2">Escribe tu correo y te enviaremos un enlace para crear una nueva.</p>
            </div>
            {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm" data-testid="forgot-error">{error}</div>}
            <form onSubmit={submit} className="space-y-4" data-testid="forgot-form">
              <div>
                <label className="label-text">Correo</label>
                <input type="email" required className="input-field" value={email} placeholder="tucorreo@empresa.com"
                  onChange={(e) => setEmail(e.target.value)} data-testid="forgot-email-input" />
              </div>
              <button type="submit" disabled={loading} className="btn-primary w-full justify-center" data-testid="forgot-submit-btn">
                {loading ? 'Enviando…' : 'Enviar enlace'} {!loading && <ArrowRight className="w-4 h-4" />}
              </button>
            </form>
          </>
        )}
        <p className="text-center text-sm text-ink-500"><Link to="/login" className="hover:text-brand-500">← Volver al inicio de sesión</Link></p>
      </div>
    </div>
  );
}
