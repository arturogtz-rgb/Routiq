import { useEffect, useState } from 'react';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { UserPlus, ShieldCheck, User as UserIcon, ShieldOff } from 'lucide-react';

export default function Team() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'company_admin';
  const [users, setUsers] = useState([]);
  const [company, setCompany] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [error, setError] = useState('');

  const load = async () => {
    const [usersRes, companyRes] = await Promise.all([
      api.get('/users'),
      api.get('/companies/me').catch(() => ({ data: null })),
    ]);
    setUsers(usersRes.data);
    if (companyRes.data) setCompany(companyRes.data);
  };
  useEffect(() => { load(); }, []);

  const execCount = users.filter((u) => u.role === 'executive' && u.status !== 'suspended').length;
  const execLimit = company?.exec_limit ?? 0;
  const limitReached = execLimit > 0 && execCount >= execLimit;

  const invite = async () => {
    setError('');
    try {
      await api.post('/users/invite-executive', form);
      setOpen(false); setForm({ name: '', email: '', password: '' });
      load();
    } catch (e) { setError(formatApiError(e)); }
  };

  const toggle = async (u) => {
    const next = u.status === 'active' ? 'suspended' : 'active';
    await api.patch(`/users/${u.id}/status`, null, { params: { status: next } });
    load();
  };

  return (
    <AppShell>
      <div className="flex items-end justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight">Equipo</h1>
          <p className="text-ink-500 mt-1">Gestiona ejecutivos y accesos.</p>
        </div>
        {isAdmin && (
          <button className="btn-primary" onClick={() => setOpen(true)} disabled={limitReached} data-testid="invite-exec-btn">
            <UserPlus className="w-4 h-4" /> Invitar ejecutivo
          </button>
        )}
      </div>

      {isAdmin && (
        <div className="card-surface px-6 py-4 mb-4 flex items-center justify-between gap-4" data-testid="exec-usage-banner">
          <div>
            <p className="text-xs uppercase tracking-widest font-bold text-ink-400">Ejecutivos activos · Plan {(company?.plan || 'pro').toUpperCase()}</p>
            <p className="font-display text-2xl font-bold text-ink-900 mt-0.5" data-testid="exec-usage-count">
              {execCount}{execLimit > 0 ? ` de ${execLimit}` : ' · ilimitado'}
            </p>
          </div>
          {limitReached && (
            <div className="rounded-xl bg-peach-100 text-amber-800 px-4 py-2 text-sm max-w-md" data-testid="exec-limit-warning">
              Alcanzaste el límite de tu plan. Suspende un ejecutivo o solicita una actualización de plan al administrador de Routiq.
            </div>
          )}
        </div>
      )}

      <div className="card-surface overflow-hidden">
        {users.map((u) => (
          <div key={u.id} className="flex items-center justify-between px-6 py-4 border-b border-ink-100 last:border-0" data-testid={`team-row-${u.id}`}>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-brand-50 text-brand-500 flex items-center justify-center font-display font-semibold">{u.name.slice(0, 1).toUpperCase()}</div>
              <div>
                <p className="font-semibold text-ink-900">{u.name}</p>
                <p className="text-xs text-ink-500">{u.email}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className={`pill ${u.role === 'company_admin' ? 'bg-brand-50 text-brand-500' : 'bg-ink-100 text-ink-700'}`}>
                {u.role === 'company_admin' ? <ShieldCheck className="w-3 h-3" /> : <UserIcon className="w-3 h-3" />}
                {u.role === 'company_admin' ? 'Admin' : 'Ejecutivo'}
              </span>
              {u.status === 'suspended' && <span className="pill bg-red-100 text-red-700">Suspendido</span>}
              {isAdmin && u.role !== 'company_admin' && (
                <button className="btn-ghost text-xs" onClick={() => toggle(u)} data-testid={`toggle-user-${u.id}`}>
                  {u.status === 'active' ? <><ShieldOff className="w-3.5 h-3.5" /> Suspender</> : 'Reactivar'}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => setOpen(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="invite-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900 mb-4">Invitar ejecutivo</h3>
            {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-3">{error}</div>}
            <div className="space-y-3">
              <div><label className="label-text">Nombre</label><input className="input-field" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} data-testid="invite-name" /></div>
              <div><label className="label-text">Email</label><input type="email" className="input-field" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} data-testid="invite-email" /></div>
              <div><label className="label-text">Contraseña temporal (mín. 8)</label><input type="text" className="input-field" value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} data-testid="invite-password" /></div>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setOpen(false)} data-testid="invite-cancel">Cancelar</button>
              <button className="btn-primary" onClick={invite} disabled={!form.name || !form.email || form.password.length < 8} data-testid="invite-submit">Invitar</button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
