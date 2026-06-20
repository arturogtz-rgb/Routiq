import { Bed, Car, Compass, Ticket, Sparkles, Plus, Trash2 } from 'lucide-react';

export const UNITS = [
  { v: 'per_person', label: 'Por persona' },
  { v: 'per_night', label: 'Por noche' },
  { v: 'per_room', label: 'Por habitación' },
  { v: 'per_group', label: 'Por grupo (precio único)' },
  { v: 'per_day', label: 'Por día' },
  { v: 'per_vehicle', label: 'Por vehículo' },
];
export const UNIT_ES = Object.fromEntries(UNITS.map((u) => [u.v, u.label]));

export const CATEGORIES = [
  { v: 'hospedaje', label: 'Hospedaje', icon: Bed },
  { v: 'traslado', label: 'Traslado', icon: Car },
  { v: 'tour', label: 'Tour', icon: Compass },
  { v: 'acceso', label: 'Acceso', icon: Ticket },
  { v: 'extra', label: 'Extra', icon: Sparkles },
];
export const CAT_ICON = Object.fromEntries(CATEGORIES.map((c) => [c.v, c.icon]));

export const EMPTY_CONTACTS = { agency: { name: '', contact: '', email: '', phone: '' }, traveler: { name: '', phone: '' } };

export function money(v, c = 'MXN') {
  return `$${Number(v || 0).toLocaleString('es-MX', { maximumFractionDigits: 2 })} ${c}`;
}

// Editable string list — module scope so it is NOT remounted on every parent
// render (that bug caused the input to lose focus after each keystroke).
export function StringList({ list, onChange, placeholder, testid }) {
  return (
    <div className="space-y-2" data-testid={testid}>
      {list.map((x, i) => (
        <div key={i} className="flex gap-2">
          <input className="input-field" value={x} placeholder={placeholder}
            onChange={(e) => onChange(list.map((v, j) => j === i ? e.target.value : v))} data-testid={`${testid}-input-${i}`} />
          <button type="button" className="text-red-600 hover:text-red-800 px-2" onClick={() => onChange(list.filter((_, j) => j !== i))} data-testid={`${testid}-remove-${i}`}><Trash2 className="w-4 h-4" /></button>
        </div>
      ))}
      <button type="button" className="btn-ghost text-xs" onClick={() => onChange([...list, ''])} data-testid={`${testid}-add`}><Plus className="w-4 h-4" /> Agregar</button>
    </div>
  );
}
