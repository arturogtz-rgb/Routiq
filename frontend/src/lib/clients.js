// 4.1 — Orden de clientes: favoritos manuales primero, luego los más frecuentes
// (cotizaciones del ejecutivo logueado), luego el resto por nombre.
export function sortByFavorite(list) {
  return [...(list || [])].sort(
    (a, b) =>
      (b.is_favorite ? 1 : 0) - (a.is_favorite ? 1 : 0) ||
      (b.my_freq || 0) - (a.my_freq || 0) ||
      (a.name || '').localeCompare(b.name || '')
  );
}
