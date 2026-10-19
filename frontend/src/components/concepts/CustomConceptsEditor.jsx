import { Plus } from 'lucide-react';
import { nightsBetween } from '@/lib/dates';
import { ConceptCard, CONCEPT_CATEGORIES } from './ConceptCard';
import { conceptsTotals, usesOccupancyTable } from './conceptMath';

const LODGING_UNIT_SET = ['per_night', 'per_stay'];

function newConcept(category, ctx) {
  const base = {
    category, name: '', description: '', net_price: 0, price_type: 'neto', unit: 'per_person', qty: 0,
    service_date: '', start_time: '', end_time: '', checkin: '', checkout: '', nights: 0, ocupacion: null, occupancy_rows: [],
  };
  if (category !== 'hospedaje') return base;
  if (ctx.engine === 'package') return { ...base, unit: 'per_night', ocupacion: 'doble' };
  const { start = '', end = '' } = ctx.defaultDates || {};
  return { ...base, unit: 'per_night', checkin: start, checkout: end, nights: start && end ? nightsBetween(start, end) : 0,
    occupancy_rows: [{ ocupacion: 'doble', rooms: 1, price: 0 }] };
}

// Aplica un cambio sin sobreescribir la unidad elegida (solo se corrige si deja de ser válida).
function applyPatch(it, patch, engine) {
  const next = { ...it, ...patch };
  if (patch.category && patch.category !== it.category) {
    const toTable = usesOccupancyTable(next, engine);
    if (toTable && !LODGING_UNIT_SET.includes(next.unit)) next.unit = 'per_night';
    if (!toTable && next.unit === 'per_stay') next.unit = 'per_group';
    if (toTable && !(next.occupancy_rows || []).length) next.occupancy_rows = [{ ocupacion: it.ocupacion || 'doble', rooms: 1, price: Number(it.net_price) || 0 }];
    if (patch.category === 'hospedaje') { next.start_time = ''; next.end_time = ''; if (engine === 'package' && !next.ocupacion) next.ocupacion = 'doble'; }
    else { next.ocupacion = null; next.checkin = ''; next.checkout = ''; }
  }
  if (next.category === 'hospedaje' && (patch.checkin !== undefined || patch.checkout !== undefined)) {
    next.nights = next.checkin && next.checkout ? Math.max(0, nightsBetween(next.checkin, next.checkout)) : 0;
  }
  return next;
}

export function CustomConceptsEditor({ items, setItems, ctx, money, onSyncPax, title = 'Conceptos adicionales', subtitle }) {
  const list = items || [];
  const add = (cat) => setItems((xs) => [...(xs || []), newConcept(cat, ctx)]);
  const update = (idx, patch) => setItems((xs) => xs.map((it, i) => (i === idx ? applyPatch(it, patch, ctx.engine) : it)));
  const remove = (idx) => setItems((xs) => xs.filter((_, i) => i !== idx));
  const { subtotal } = conceptsTotals(list, ctx);
  return (
    <div className="space-y-3" data-testid="custom-concepts-section">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-display text-lg font-semibold text-ink-900">{title}</h3>
        <div className="flex flex-wrap gap-2">
          {CONCEPT_CATEGORIES.map((c) => (
            <button key={c.v} type="button" className="btn-ghost text-xs border border-brand-200 text-brand-600" onClick={() => add(c.v)} data-testid={`add-concept-${c.v}`}>
              <Plus className="w-3.5 h-3.5" /> {c.label}
            </button>
          ))}
        </div>
      </div>
      {subtitle && <p className="text-ink-500 text-sm">{subtitle}</p>}
      {list.length === 0 && <p className="text-ink-400 text-sm italic" data-testid="concepts-empty">Sin conceptos. Agrega hospedaje, traslados, tours, accesos o extras con los botones de arriba.</p>}
      {list.map((it, idx) => (
        <ConceptCard key={idx} it={it} idx={idx} ctx={ctx} money={money} onSyncPax={onSyncPax}
          update={(patch) => update(idx, patch)} remove={() => remove(idx)} />
      ))}
      {subtotal > 0 && (
        <div className="rounded-xl bg-brand-50 text-brand-700 px-4 py-3 text-sm font-medium" data-testid="concepts-subtotal">
          {title}: {money(subtotal)}
        </div>
      )}
    </div>
  );
}
