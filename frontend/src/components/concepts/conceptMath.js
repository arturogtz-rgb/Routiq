// Cálculo compartido de "Conceptos adicionales" (a la carta, personalizado y paquete).
// Espejo del backend: pricing._price_custom_item / _price_lodging_rows.
export const OCC_COUNT = { sencilla: 1, doble: 2, triple: 3, cuadruple: 4 };
export const OCC_LABEL = { sencilla: 'Sencilla', doble: 'Doble', triple: 'Triple', cuadruple: 'Cuádruple' };
export const LODGING_UNITS = [
  { v: 'per_night', label: 'Por noche' },
  { v: 'per_stay', label: 'Por estancia' },
];
export const CONCEPT_UNITS = [
  { v: 'per_person', label: 'Por persona' },
  { v: 'per_night', label: 'Por noche' },
  { v: 'per_room', label: 'Por habitación' },
  { v: 'per_group', label: 'Por grupo (precio único)' },
  { v: 'per_day', label: 'Por día' },
  { v: 'per_vehicle', label: 'Por vehículo' },
];
export const UNIT_WORD = {
  per_person: 'personas', per_night: 'noches', per_room: 'hab.', per_group: 'grupo',
  per_day: 'días', per_vehicle: 'vehículos', per_stay: 'estancia',
};

const r2 = (v) => Math.round((Number(v) || 0) * 100) / 100;

// Usa la tabla de ocupación (hospedaje en a la carta / personalizado).
export const usesOccupancyTable = (it, engine) => engine !== 'package' && it.category === 'hospedaje';

export const lodgingPersons = (it) => (it.occupancy_rows || [])
  .reduce((s, r) => s + (OCC_COUNT[r.ocupacion] || 0) * (Number(r.rooms) || 0), 0);

// Precio que ve el cliente por unidad (neto -> canal; público -> tal cual).
export function unitPrice(amount, priceType, pricing) {
  const amt = Number(amount) || 0;
  if ((priceType || 'neto') === 'publico') return r2(amt);
  const { margin, channel, commissions } = pricing;
  const pub = margin > 0 ? r2(amt / margin) : r2(amt);
  if (channel === 'operador') return r2(amt);
  if (channel === 'mayorista') return r2(pub * (1 - (Number(commissions?.mayorista) || 0)));
  return pub;
}

function defaultQty(unit, ctx) {
  if (unit === 'per_person') return Math.max(1, ctx.totalPax);
  if (unit === 'per_night' || unit === 'per_day') return Math.max(1, ctx.nights);
  if (unit === 'per_room') return Math.max(1, ctx.rooms);
  return 1;
}

// Multiplicador de conceptos que NO usan tabla de ocupación.
export function conceptQty(it, ctx) {
  const q = Number(it.qty) || 0;
  if (ctx.engine === 'custom') {
    if (it.unit === 'per_night') return Number(it.nights) || 0;
    if (it.unit === 'per_group') return 1;
  }
  return q > 0 ? q : defaultQty(it.unit, ctx);
}

// { subtotal, lines: [{text, amount}] } — las líneas son la fórmula visible en la captura.
export function conceptCalc(it, ctx, money) {
  const pt = it.price_type || 'neto';
  const priceTxt = (amt) => {
    const up = unitPrice(amt, pt, ctx.pricing);
    return pt === 'neto' && up !== r2(amt) ? `${money(up)} (neto ${money(amt)})` : money(up);
  };
  if (usesOccupancyTable(it, ctx.engine)) {
    const perNight = (it.unit || 'per_night') === 'per_night';
    const n = Number(it.nights) || 0;
    const lines = (it.occupancy_rows || []).filter((r) => Number(r.rooms) > 0).map((r) => {
      const persons = OCC_COUNT[r.ocupacion] * Number(r.rooms);
      const amount = r2(unitPrice(r.price, pt, ctx.pricing) * persons * (perNight ? n : 1));
      const text = `${OCC_LABEL[r.ocupacion]}: ${r.rooms} hab × ${OCC_COUNT[r.ocupacion]} pax = ${persons} pers × ${priceTxt(r.price)}${perNight ? ` × ${n} noches` : ' (estancia)'}`;
      return { text, amount };
    });
    return { subtotal: r2(lines.reduce((s, l) => s + l.amount, 0)), lines };
  }
  const qty = conceptQty(it, ctx);
  let amount = r2(unitPrice(it.net_price, pt, ctx.pricing) * qty);
  let text = it.unit === 'per_group' && ctx.engine === 'custom'
    ? `${priceTxt(it.net_price)} (precio único)`
    : `${priceTxt(it.net_price)} × ${qty} ${UNIT_WORD[it.unit] || ''}`;
  if (ctx.engine === 'package' && it.category === 'hospedaje' && Number(it.nights) > 0) {
    amount = r2(amount * Number(it.nights)); text += ` × ${it.nights} noches`;
  }
  return { subtotal: amount, lines: [{ text, amount }] };
}

export function conceptsTotals(items, ctx) {
  const money = (v) => v;
  let subtotal = 0; let publico = 0;
  (items || []).forEach((it) => {
    const s = conceptCalc(it, ctx, money).subtotal;
    subtotal += s;
    if ((it.price_type || 'neto') === 'publico') publico += s;
  });
  return { subtotal: r2(subtotal), publico: r2(publico) };
}

export const conceptIsValid = (it, engine) => (usesOccupancyTable(it, engine)
  ? (it.occupancy_rows || []).some((r) => Number(r.rooms) > 0 && Number(r.price) > 0)
  : Number(it.net_price) > 0);

// Normaliza conceptos guardados antes de la tabla de ocupación (hospedaje legacy).
export const normalizeConcepts = (items, engine) => (items || []).map((it) => {
  if (!usesOccupancyTable(it, engine) || (it.occupancy_rows || []).length) return { ...it };
  return {
    ...it, unit: it.unit === 'per_stay' ? 'per_stay' : 'per_night',
    occupancy_rows: [{ ocupacion: it.ocupacion || 'doble', rooms: 1, price: Number(it.net_price) || 0 }],
  };
});

// Payload limpio para el backend.
export const cleanConcept = (it, engine) => {
  const table = usesOccupancyTable(it, engine);
  return {
    category: it.category || 'extra', name: it.name || '', description: it.description || '',
    net_price: table ? 0 : Number(it.net_price) || 0, price_type: it.price_type || 'neto',
    unit: it.unit || 'per_group', qty: Number(it.qty) || 0,
    service_date: it.service_date || '', start_time: it.start_time || '', end_time: it.end_time || '',
    checkin: it.checkin || '', checkout: it.checkout || '', nights: Number(it.nights) || 0,
    ocupacion: it.category === 'hospedaje' ? (table ? null : (it.ocupacion || 'doble')) : null,
    occupancy_rows: table ? (it.occupancy_rows || []).map((r) => ({ ocupacion: r.ocupacion, rooms: Number(r.rooms) || 0, price: Number(r.price) || 0 })) : [],
  };
};
