import { Trash2, Sparkles, Bed, Car, Compass, Ticket } from 'lucide-react';
import { nextDay } from '@/lib/dates';
import { HelpTip } from '@/components/HelpTip';
import { LodgingOccupancyTable } from './LodgingOccupancyTable';
import { ConceptFormula } from './ConceptFormula';
import { CONCEPT_UNITS, LODGING_UNITS, usesOccupancyTable, conceptQty } from './conceptMath';

export const CONCEPT_CATEGORIES = [
  { v: 'hospedaje', label: 'Hospedaje', icon: Bed },
  { v: 'traslado', label: 'Traslado', icon: Car },
  { v: 'tour', label: 'Tour', icon: Compass },
  { v: 'acceso', label: 'Acceso', icon: Ticket },
  { v: 'extra', label: 'Extra', icon: Sparkles },
];
const ICON = Object.fromEntries(CONCEPT_CATEGORIES.map((c) => [c.v, c.icon]));

const TIP_PRICE_TYPE = 'Tarifa neta: costo confidencial; el precio al cliente se calcula con el divisor y el canal (no comisionable). Precio público: el monto ya es público y se le descuenta la comisión del canal.';
const TIP_UNIT = 'Define qué multiplica al precio: personas, noches, habitaciones, días, vehículos o un precio único por grupo.';
const TIP_QTY = 'Deja 0 para calcularla automáticamente según la unidad (ej. número de personas o noches de la cotización).';
const TIP_LODGING_UNIT = 'Por noche: precio por persona × noches. Por estancia: precio por persona por toda la estancia.';

function PriceTypeToggle({ it, idx, update }) {
  const pt = it.price_type || 'neto';
  const cls = (on, c) => `flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-colors ${on ? c : 'border-ink-100 text-ink-500 hover:border-brand-300'}`;
  return (
    <div>
      <label className="label-text text-xs">Tipo de precio<HelpTip text={TIP_PRICE_TYPE} testid={`concept-help-pricetype-${idx}`} /></label>
      <div className="flex gap-2">
        <button type="button" onClick={() => update({ price_type: 'neto' })} className={cls(pt === 'neto', 'border-brand-500 bg-brand-50 text-brand-700')} data-testid={`concept-type-neto-${idx}`}>Tarifa neta</button>
        <button type="button" onClick={() => update({ price_type: 'publico' })} className={cls(pt === 'publico', 'border-emerald-500 bg-mint-100 text-emerald-700')} data-testid={`concept-type-publico-${idx}`}>Precio público</button>
      </div>
    </div>
  );
}

function LodgingFields({ it, idx, update }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
      <div><label className="label-text text-xs">Unidad<HelpTip text={TIP_LODGING_UNIT} testid={`concept-help-unit-${idx}`} /></label>
        <select className="input-field" value={it.unit === 'per_stay' ? 'per_stay' : 'per_night'} onChange={(e) => update({ unit: e.target.value })} data-testid={`concept-unit-${idx}`}>
          {LODGING_UNITS.map((u) => <option key={u.v} value={u.v}>{u.label}</option>)}
        </select></div>
      <div><label className="label-text text-xs">Check-in</label><input type="date" className="input-field" value={it.checkin || ''} onChange={(e) => update({ checkin: e.target.value })} data-testid={`concept-checkin-${idx}`} /></div>
      <div><label className="label-text text-xs">Check-out</label><input type="date" className="input-field" min={nextDay(it.checkin) || undefined} value={it.checkout || ''} onChange={(e) => update({ checkout: e.target.value })} data-testid={`concept-checkout-${idx}`} /></div>
      <div><label className="label-text text-xs">Noches (auto)</label><input className="input-field bg-ink-50" value={it.nights || 0} readOnly disabled data-testid={`concept-nights-${idx}`} /></div>
    </div>
  );
}

function StandardFields({ it, idx, update, ctx, priceLabel }) {
  const custom = ctx.engine === 'custom';
  const nightsMode = custom && it.unit === 'per_night';
  const fixed = custom && it.unit === 'per_group';
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
      <div><label className="label-text text-xs">{priceLabel}</label>
        <input type="number" min="0" step="0.01" className="input-field" value={it.net_price} onChange={(e) => update({ net_price: +e.target.value || 0 })} data-testid={`concept-price-${idx}`} /></div>
      <div><label className="label-text text-xs">Unidad<HelpTip text={TIP_UNIT} testid={`concept-help-unit-${idx}`} /></label>
        <select className="input-field" value={it.unit} onChange={(e) => update({ unit: e.target.value })} data-testid={`concept-unit-${idx}`}>
          {CONCEPT_UNITS.map((u) => <option key={u.v} value={u.v}>{u.label}</option>)}
        </select></div>
      <div><label className="label-text text-xs">{nightsMode ? 'Noches' : 'Cantidad (0 = auto)'}{!nightsMode && <HelpTip text={TIP_QTY} testid={`concept-help-qty-${idx}`} />}</label>
        <input type="number" min="0" className="input-field disabled:bg-ink-50" disabled={fixed} value={fixed ? 1 : (nightsMode ? (it.nights || 0) : it.qty)}
          onChange={(e) => update(nightsMode ? { nights: Math.max(0, +e.target.value || 0) } : { qty: Math.max(0, +e.target.value || 0) })} data-testid={`concept-qty-${idx}`} />
        {!nightsMode && !fixed && !(Number(it.qty) > 0) && <p className="text-[11px] text-ink-400 mt-1" data-testid={`concept-qty-auto-${idx}`}>Auto: {conceptQty(it, ctx)}</p>}
      </div>
      {it.category === 'hospedaje' && (
        <div><label className="label-text text-xs">Ocupación</label>
          <select className="input-field" value={it.ocupacion || 'doble'} onChange={(e) => update({ ocupacion: e.target.value })} data-testid={`concept-ocupacion-${idx}`}>
            <option value="sencilla">Sencilla</option><option value="doble">Doble</option><option value="triple">Triple</option><option value="cuadruple">Cuádruple</option>
          </select></div>
      )}
    </div>
  );
}

function ScheduleFields({ it, idx, update }) {
  if (it.category === 'hospedaje') return null;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
      <div><label className="label-text text-xs">Fecha (opcional)</label><input type="date" className="input-field" value={it.service_date || ''} onChange={(e) => update({ service_date: e.target.value })} data-testid={`concept-date-${idx}`} /></div>
      {it.category !== 'acceso' && <div><label className="label-text text-xs">Hora inicio</label><input type="time" className="input-field" value={it.start_time || ''} onChange={(e) => update({ start_time: e.target.value })} data-testid={`concept-start-${idx}`} /></div>}
      {(it.category === 'traslado' || it.category === 'extra') && <div><label className="label-text text-xs">Hora fin</label><input type="time" className="input-field" value={it.end_time || ''} onChange={(e) => update({ end_time: e.target.value })} data-testid={`concept-end-${idx}`} /></div>}
    </div>
  );
}

export function ConceptCard({ it, idx, ctx, update, remove, money, onSyncPax }) {
  const Icon = ICON[it.category] || Sparkles;
  const table = usesOccupancyTable(it, ctx.engine);
  const priceLabel = (it.price_type || 'neto') === 'publico' ? 'Precio público' : 'Tarifa neta';
  return (
    <div className="rounded-xl border border-ink-100 bg-cream/60 p-4 space-y-3 transition-shadow hover:shadow-sm" data-testid={`concept-row-${idx}`}>
      <div className="flex items-center gap-2">
        <span className="pill bg-white text-brand-500 text-xs flex items-center gap-1 shrink-0"><Icon className="w-3.5 h-3.5" /></span>
        <div className="flex-1 min-w-0">
          <input className="input-field" placeholder={table ? 'Nombre del hotel' : 'Nombre del concepto (ej. Traslado aeropuerto)'} value={it.name} onChange={(e) => update({ name: e.target.value })} data-testid={`concept-name-${idx}`} />
        </div>
        <div className="w-40 shrink-0">
          <select className="input-field" value={it.category || 'extra'} onChange={(e) => update({ category: e.target.value })} data-testid={`concept-category-${idx}`}>
            {CONCEPT_CATEGORIES.map((c) => <option key={c.v} value={c.v}>{c.label}</option>)}
          </select>
        </div>
        <button type="button" className="text-ink-300 hover:text-red-500 p-2" onClick={remove} data-testid={`concept-remove-${idx}`}><Trash2 className="w-4 h-4" /></button>
      </div>
      <input className="input-field" placeholder="Detalle (opcional)" value={it.description || ''} onChange={(e) => update({ description: e.target.value })} data-testid={`concept-detail-${idx}`} />
      <PriceTypeToggle it={it} idx={idx} update={update} />
      {table ? (
        <>
          <LodgingFields it={it} idx={idx} update={update} />
          <LodgingOccupancyTable it={it} idx={idx} update={update} priceLabel={priceLabel} totalPax={ctx.totalPax} onSyncPax={onSyncPax} />
        </>
      ) : <StandardFields it={it} idx={idx} update={update} ctx={ctx} priceLabel={priceLabel} />}
      <ScheduleFields it={it} idx={idx} update={update} />
      <ConceptFormula it={it} idx={idx} ctx={ctx} money={money} />
    </div>
  );
}
