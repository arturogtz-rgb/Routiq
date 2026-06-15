import { useState } from 'react';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { Save, User as UserIcon, Lock, ShieldCheck, Crown } from 'lucide-react';

const ROLE_LABEL = { super_admin: 'Master (Dueño SaaS)', company_admin: 'Administrador de empresa', executive: 'Ejecutivo de ventas' };

export default function Profile() {
  const { user, refresh } = useAuth();
  const [name, setName] = useState(user?.name || '');
  const [email, setEmail] = useState(user?.email || '');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [saving, setSaving] = useState(false);

  const emailChanged = email.trim().toLowerCase() !== (user?.email || '').toLowerCase();
  const wantsPwd = !!newPassword;

  const save = async () => {
    setError(''); setOk('');
    if (wantsPwd && newPassword !== confirm) { setError('Las contraseñas nuevas no coinciden.'); return; }
    if ((wantsPwd || emailChanged) && !currentPassword) { setError('Ingresa tu contraseña actual para confirmar el cambio.'); return; }
    setSaving(true);
    try {
      const payload = { name: name.trim() };
      if (emailChanged) payload.email = email.trim();
      if (currentPassword) payload.current_password = currentPassword;
      if (wantsPwd) payload.new_password = newPassword;
      await api.patch('/auth/profile', payload);
      await refresh();
      setOk('Perfil actualizado correctamente.');
      setCurrentPassword(''); setNewPassword(''); setConfirm('');
      setTimeout(() => setOk(''), 3000);
    } catch (e) { setError(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const RoleIcon = user?.role === 'super_admin' ? Crown : user?.role === 'company_admin' ? ShieldCheck : UserIcon;

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight">Mi perfil</h1>
        <p className="text-ink-500 mt-1">Actualiza tus datos de acceso.</p>
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="profile-error">{error}</div>}
      {ok && <div className="rounded-xl border border-emerald-200 bg-mint-100 text-emerald-800 px-4 py-3 text-sm mb-4" data-testid="profile-ok">{ok}</div>}

      <div className="max-w-2xl space-y-6">
        <div className="card-surface p-6">
          <div className="flex items-center gap-3 mb-5">
            <div className="w-12 h-12 rounded-full bg-brand-500 text-white flex items-center justify-center font-display text-lg font-semibold">{(user?.name || 'U').slice(0, 1).toUpperCase()}</div>
            <div>
              <p className="font-semibold text-ink-900">{user?.name}</p>
              <span className="pill bg-brand-50 text-brand-500 text-xs mt-0.5"><RoleIcon className="w-3 h-3" /> {ROLE_LABEL[user?.role] || user?.role}</span>
            </div>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div><label className="label-text">Nombre</label><input className="input-field" value={name} onChange={(e) => setName(e.target.value)} data-testid="profile-name-input" /></div>
            <div><label className="label-text">Correo</label><input type="email" className="input-field" value={email} onChange={(e) => setEmail(e.target.value)} data-testid="profile-email-input" /></div>
          </div>
        </div>

        <div className="card-surface p-6">
          <h2 className="font-display font-semibold text-ink-900 flex items-center gap-2 mb-1"><Lock className="w-4 h-4 text-brand-500" /> Seguridad</h2>
          <p className="text-sm text-ink-500 mb-4">Para cambiar tu correo o contraseña, confirma con tu contraseña actual.</p>
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="sm:col-span-2"><label className="label-text">Contraseña actual</label><input type="password" className="input-field" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} data-testid="profile-current-password" /></div>
            <div><label className="label-text">Nueva contraseña</label><input type="password" className="input-field" value={newPassword} placeholder="Mín. 8 caracteres" onChange={(e) => setNewPassword(e.target.value)} data-testid="profile-new-password" /></div>
            <div><label className="label-text">Confirmar nueva contraseña</label><input type="password" className="input-field" value={confirm} onChange={(e) => setConfirm(e.target.value)} data-testid="profile-confirm-password" /></div>
          </div>
        </div>

        <div className="flex justify-end">
          <button className="btn-primary" onClick={save} disabled={saving} data-testid="profile-save-btn"><Save className="w-4 h-4" /> {saving ? 'Guardando…' : 'Guardar cambios'}</button>
        </div>
      </div>
    </AppShell>
  );
}
