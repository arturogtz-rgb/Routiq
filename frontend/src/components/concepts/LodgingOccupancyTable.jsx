import { Plus, Trash2, Users } from 'lucide-react';
import { OCC_COUNT, OCC_LABEL, lodgingPersons } from './conceptMath';
import { HelpTip } from '@/components/HelpTip';

// Tabla interna de ocupación de un hospedaje: precio SIEMPRE por persona.
export function LodgingOccupancyTable({ it, idx, update, priceLabel, totalPax, onSyncPax }) {
  const rows = it.occupancy_rows || [];
  const setRows = (next) => update({ occupancy_rows: next });
  const setRow = (r, patch) => setRows(rows.map((x, i) => (i === r ? { ...x, ...patch } : x)));
  const used = new Set(rows.map((r) => r.ocupacion));
  const nextOcc = Object.keys(OCC_COUNT).find((o) => !used.has(o));
  const persons = lodgingPersons(it);
  return (
    <div className="rounded-lg border border-brand-100 bg-white" data-testid={`concept-occ-table-${idx}`}>
      <div className="grid grid-cols-[1.3fr_0.8fr_1.2fr_0.8fr_auto] gap-2 px-3 py-2 text-[11px] uppercase tracking-wider text-ink-400 font-semibold border-b border-ink-100">
        <span>Ocupación</span><span>Habitaciones</span>
        <span>{priceLabel} por persona<HelpTip text="Captura el precio POR PERSONA de esa ocupación (igual que en Paquete armado). Las personas se calculan: habitaciones × ocupación." testid={`concept-occ-help-${idx}`} /></span>
        <span className="text-right">Personas</span><span />
      </div>
      {rows.map((r, ri) => (
        <div key={ri} className="grid grid-cols-[1.3fr_0.8fr_1.2fr_0.8fr_auto] gap-2 px-3 py-2 items-center" data-testid={`concept-occ-row-${idx}-${ri}`}>
          <select className="input-field py-1.5" value={r.ocupacion} onChange={(e) => setRow(ri, { ocupacion: e.target.value })} data-testid={`concept-occ-occ-${idx}-${ri}`}>
            {Object.keys(OCC_COUNT).map((o) => <option key={o} value={o} disabled={o !== r.ocupacion && used.has(o)}>{OCC_LABEL[o]}</option>)}
          </select>
          <input type="number" min="0" className="input-field py-1.5" value={r.rooms} onChange={(e) => setRow(ri, { rooms: Math.max(0, +e.target.value || 0) })} data-testid={`concept-occ-rooms-${idx}-${ri}`} />
          <input type="number" min="0" step="0.01" className="input-field py-1.5" value={r.price} onChange={(e) => setRow(ri, { price: +e.target.value || 0 })} data-testid={`concept-occ-price-${idx}-${ri}`} />
          <span className="text-right text-sm font-medium text-ink-700" data-testid={`concept-occ-persons-${idx}-${ri}`}>{OCC_COUNT[r.ocupacion] * (Number(r.rooms) || 0)}</span>
          <button type="button" className="text-ink-300 hover:text-red-500 p-1 disabled:opacity-30" disabled={rows.length <= 1} onClick={() => setRows(rows.filter((_, i) => i !== ri))} data-testid={`concept-occ-remove-${idx}-${ri}`}><Trash2 className="w-4 h-4" /></button>
        </div>
      ))}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-t border-ink-100 text-xs">
        <button type="button" className="btn-ghost text-xs text-brand-600 disabled:opacity-40" disabled={!nextOcc} onClick={() => setRows([...rows, { ocupacion: nextOcc, rooms: 1, price: 0 }])} data-testid={`concept-occ-add-${idx}`}>
          <Plus className="w-3.5 h-3.5" /> Agregar ocupación
        </button>
        <span className="flex items-center gap-2 text-ink-500" data-testid={`concept-occ-total-persons-${idx}`}>
          <Users className="w-3.5 h-3.5" /> Total: <b className="text-ink-900">{persons} personas</b>
          {onSyncPax && persons > 0 && persons !== totalPax && (
            <button type="button" className="rounded-full bg-amber-50 border border-amber-200 text-amber-700 px-2 py-0.5 hover:bg-amber-100 transition-colors" onClick={() => onSyncPax(persons)} data-testid={`concept-pax-sync-${idx}`}>
              La cotización tiene {totalPax}; usar {persons}
            </button>
          )}
        </span>
      </div>
    </div>
  );
}
