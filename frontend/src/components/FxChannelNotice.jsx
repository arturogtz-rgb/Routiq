import { DollarSign, AlertTriangle } from 'lucide-react';

// Iter 71: aviso en la captura para el canal Mayorista internacional.
export function FxChannelNotice({ client, company }) {
  if (client?.channel !== 'mayorista') return null;
  const rate = company?.pricing_config?.fx_mayorista_mxn_per_usd;
  if (!rate) {
    return (
      <p className="rounded-xl border border-amber-300 bg-amber-50 text-amber-800 text-sm px-4 py-3 flex items-start gap-2" data-testid="fx-missing-warning">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" /> Captura el tipo de cambio en Ajustes para mostrar esta cotización en USD (Mayorista internacional). Mientras tanto se presenta solo en MXN.
      </p>
    );
  }
  return (
    <p className="rounded-xl border border-brand-100 bg-brand-50 text-brand-700 text-sm px-4 py-3 flex items-start gap-2" data-testid="fx-channel-notice">
      <DollarSign className="w-4 h-4 shrink-0 mt-0.5" /> Mayorista internacional: se presentará en USD primero al tipo de cambio fijo de ${rate} MXN por USD (se guarda con la cotización). El cobro sigue en MXN.
    </p>
  );
}
