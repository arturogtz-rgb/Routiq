import { useState } from 'react';
import { Plus } from 'lucide-react';
import api from '@/lib/api';

const EMPTY = { name: '', phone: '', email: '' };

// Agrega un ejecutivo al cliente (client.executives) y lo devuelve para seleccionarlo en la cotización.
export function AddExecutiveControl({ client, onSaved }) {
  const [open, setOpen] = useState(false);
  const [ex, setEx] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setEx((n) => ({ ...n, [k]: e.target.value }));
  const close = () => { setOpen(false); setEx(EMPTY); setError(''); };
  const save = async () => {
    if (!client || !ex.name.trim()) return;
    setSaving(true); setError('');
    try {
      const created = { id: Math.random().toString(16).slice(2, 14), name: ex.name.trim(), phone: ex.phone.trim(), email: ex.email.trim() };
      const { data } = await api.patch(`/clients/${client.id}`, { executives: [...(client.executives || []), created] });
      onSaved(data, created);
      close();
    } catch (_e) { setError('No se pudo guardar el ejecutivo. Intenta de nuevo.'); }
    finally { setSaving(false); }
  };
  if (!client) return null;
  return (
    <div data-testid="add-executive-control">
      {!open ? (
        <button type="button" className="btn-ghost text-xs" onClick={() => setOpen(true)} data-testid="add-executive-toggle"><Plus className="w-4 h-4" /> Agregar ejecutivo</button>
      ) : (
        <div className="rounded-lg border border-brand-200 bg-brand-50/40 p-3 space-y-2">
          <input className="input-field text-sm" placeholder="Nombre del ejecutivo" value={ex.name} onChange={set('name')} data-testid="add-executive-name" />
          <div className="grid grid-cols-2 gap-2">
            <input className="input-field text-sm" placeholder="Teléfono" value={ex.phone} onChange={set('phone')} data-testid="add-executive-phone" />
            <input className="input-field text-sm" placeholder="Correo" value={ex.email} onChange={set('email')} data-testid="add-executive-email" />
          </div>
          {error && <p className="text-xs text-red-600" data-testid="add-executive-error">{error}</p>}
          <div className="flex gap-2">
            <button type="button" className="btn-primary text-xs" disabled={!ex.name.trim() || saving} onClick={save} data-testid="add-executive-save">{saving ? 'Guardando…' : 'Guardar'}</button>
            <button type="button" className="btn-ghost text-xs" onClick={close} data-testid="add-executive-cancel">Cancelar</button>
          </div>
        </div>
      )}
    </div>
  );
}
