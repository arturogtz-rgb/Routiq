import { useEffect, useState } from 'react';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { UserPlus, ShieldCheck, User as UserIcon, ShieldOff, Crown, Pencil, KeyRound, Copy, Check } from 'lucide-react';

export default function Team() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'company_admin';
  const [users, setUsers] = useState([]);
  const [company, setCompany] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [error, setError] = useState('');
  const [editUser, setEditUser] = useState(null);
  const [editForm, setEditForm] = useState({ name: '', email: '' });
  const [resetInfo, setResetInfo] = useState(null); // {email, link}
  const [copied, setCopied] = useState(false);

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

  const openEdit = (u) => { setEditUser(u); setEditForm({ name: u.name, email: u.email }); setError(''); };

  const saveEdit = async () => {
    setError('');
    try {
      await api.patch(`/users/${editUser.id}`, { name: editForm.name, email: editForm.email });
      setEditUser(null); load();
    } catch (e) { setError(formatApiError(e)); }
  };

  const genResetLink = async (u) => {
    setError('');
    try {
      const { data } = await api.post(`/users/${u.id}/reset-link`);
      setResetInfo({ email: data.email, link: data.link }); setCopied(false);
    } catch (e) { setError(formatApiError(e)); }
  };

  const copyLink = async () => {
    try { await navigator.clipboard.writeText(resetInfo.link); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { window.prompt('Copia el enlace de recuperación:', resetInfo.link); }
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

      <div className="space-y-3">
        {users.map((u) => {
          const admin = u.role === 'company_admin';
          return (
            <div key={u.id}
              className={`card-surface px-5 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-l-4 ${admin ? 'border-l-brand-500 bg-brand-50/30' : 'border-l-ink-200'}`}
              data-testid={`team-row-${u.id}`}>
              <div className="flex items-center gap-3">
                <div className={`w-11 h-11 rounded-full flex items-center justify-center font-display font-semibold ${admin ? 'bg-brand-500 text-white ring-2 ring-brand-200' : 'bg-ink-100 text-ink-500'}`}>
                  {admin ? <Crown className="w-5 h-5" /> : u.name.slice(0, 1).toUpperCase()}
                </div>
                <div>
                  <p className="font-semibold text-ink-900 flex items-center gap-2">{u.name}
                    {u.id === user?.id && <span className="text-[10px] text-ink-400">(tú)</span>}
                  </p>
                  <p className="text-xs text-ink-500">{u.email}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`pill ${admin ? 'bg-brand-500 text-white' : 'bg-ink-100 text-ink-700'}`} data-testid={`role-badge-${u.id}`}>
                  {admin ? <ShieldCheck className="w-3 h-3" /> : <UserIcon className="w-3 h-3" />}
                  {admin ? 'Administrador' : 'Ejecutivo'}
                </span>
                {u.status === 'suspended' && <span className="pill bg-red-100 text-red-700">Suspendido</span>}
                {isAdmin && !admin && (
                  <>
                    <button className="btn-ghost text-xs" onClick={() => openEdit(u)} data-testid={`edit-user-${u.id}`}><Pencil className="w-3.5 h-3.5" /> Editar</button>
                    <button className="btn-ghost text-xs" onClick={() => genResetLink(u)} data-testid={`reset-user-${u.id}`}><KeyRound className="w-3.5 h-3.5" /> Recuperar contraseña</button>
                    <button className="btn-ghost text-xs" onClick={() => toggle(u)} data-testid={`toggle-user-${u.id}`}>
                      {u.status === 'active' ? <><ShieldOff className="w-3.5 h-3.5" /> Suspender</> : 'Reactivar'}
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Invite modal */}
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

      {/* Edit user modal */}
      {editUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => setEditUser(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="edit-user-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900 mb-4">Editar ejecutivo</h3>
            {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-3" data-testid="edit-user-error">{error}</div>}
            <div className="space-y-3">
              <div><label className="label-text">Nombre</label><input className="input-field" value={editForm.name} onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} data-testid="edit-user-name" /></div>
              <div><label className="label-text">Email</label><input type="email" className="input-field" value={editForm.email} onChange={(e) => setEditForm((f) => ({ ...f, email: e.target.value }))} data-testid="edit-user-email" /></div>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setEditUser(null)} data-testid="edit-user-cancel">Cancelar</button>
              <button className="btn-primary" onClick={saveEdit} disabled={!editForm.name || !editForm.email} data-testid="edit-user-save">Guardar</button>
            </div>
          </div>
        </div>
      )}

      {/* Reset link modal */}
      {resetInfo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => setResetInfo(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-lg" onClick={(e) => e.stopPropagation()} data-testid="reset-link-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900 mb-1">Enlace de recuperación</h3>
            <p className="text-sm text-ink-500 mb-4">Comparte este enlace con <b>{resetInfo.email}</b> para que cree una nueva contraseña. Válido 1 hora. {company ? 'También se intentó enviar por el correo configurado.' : ''}</p>
            <div className="flex gap-2">
              <input readOnly className="input-field flex-1 text-xs" value={resetInfo.link} data-testid="reset-link-value" />
              <button className="btn-secondary" onClick={copyLink} data-testid="reset-link-copy">{copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}</button>
            </div>
            <div className="flex justify-end mt-5">
              <button className="btn-primary" onClick={() => setResetInfo(null)} data-testid="reset-link-close">Listo</button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
