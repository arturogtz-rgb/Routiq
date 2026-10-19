// Etiquetas visibles de canal. La clave interna no cambia (Iter 71: mayorista -> "Mayorista internacional").
export const CHANNEL_OPTIONS = [
  { v: 'directo', label: 'Directo' },
  { v: 'agencia', label: 'Agencia' },
  { v: 'mayorista', label: 'Mayorista internacional' },
  { v: 'operador', label: 'Mayorista Preferencial' },
];
export const CHANNEL_LABEL = Object.fromEntries(CHANNEL_OPTIONS.map((c) => [c.v, c.label]));
export const channelLabel = (k) => CHANNEL_LABEL[k] || k || '';
