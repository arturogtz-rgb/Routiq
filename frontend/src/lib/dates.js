// Spanish date helpers — format DD MMM YYYY (e.g. "26 JUN 2026").
const MESES = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC'];

export function formatDateEs(iso) {
  if (!iso) return '';
  const s = String(iso).slice(0, 10);
  const parts = s.split('-').map(Number);
  const [y, m, d] = parts;
  if (!y || !m || !d) return String(iso);
  return `${String(d).padStart(2, '0')} ${MESES[m - 1]} ${y}`;
}

export function nightsBetween(start, end) {
  if (!start || !end) return 0;
  const a = new Date(`${String(start).slice(0, 10)}T00:00:00`);
  const b = new Date(`${String(end).slice(0, 10)}T00:00:00`);
  const n = Math.round((b - a) / 86400000);
  return Number.isFinite(n) ? Math.max(0, n) : 0;
}

export function addDays(iso, days) {
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

// 0 = Monday … 6 = Sunday
export function weekdayMon0(iso) {
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
  return (d.getDay() + 6) % 7;
}

export const WEEKDAYS_ES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

// Día siguiente (YYYY-MM-DD) en hora local; '' si no hay fecha. Guía el `min` del campo de salida.
export function nextDay(iso) {
  if (!iso) return '';
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return '';
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
