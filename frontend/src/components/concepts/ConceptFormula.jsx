import { Calculator } from 'lucide-react';
import { conceptCalc } from './conceptMath';

// Fórmula visible del subtotal estimado (solo captura interna).
export function ConceptFormula({ it, idx, ctx, money }) {
  const { subtotal, lines } = conceptCalc(it, ctx, money);
  const rate = Number(ctx.pricing.commissionRate) || 0;
  const commissionable = (it.price_type || 'neto') === 'publico' && rate > 0 && subtotal > 0;
  const net = Math.round(subtotal * (1 - rate) * 100) / 100;
  return (
    <div className="rounded-lg bg-white border border-dashed border-ink-200 px-3 py-2 text-xs text-ink-500 space-y-0.5" data-testid={`concept-formula-${idx}`}>
      <p className="flex items-center gap-1 text-[10px] uppercase tracking-widest font-bold text-ink-400"><Calculator className="w-3 h-3" /> Cálculo</p>
      {lines.map((l, i) => (
        <p key={i} className="flex justify-between gap-3 font-mono" data-testid={`concept-formula-line-${idx}-${i}`}>
          <span>{l.text}</span><span className="text-ink-700">= {money(l.amount)}</span>
        </p>
      ))}
      {lines.length === 0 && <p className="italic">Agrega habitaciones y precio para calcular.</p>}
      <p className="flex justify-between gap-3 pt-1 border-t border-ink-100 text-sm">
        <span className="text-ink-600">Subtotal estimado</span>
        <b className="text-brand-600" data-testid={`concept-subtotal-${idx}`}>{money(subtotal)}</b>
      </p>
      {commissionable && (
        <p className="flex justify-between gap-3 font-mono text-emerald-700" data-testid={`concept-commission-${idx}`}>
          <span>{money(subtotal)} − {(rate * 100).toFixed(0)}% comisión del canal</span><span>= {money(net)}</span>
        </p>
      )}
    </div>
  );
}
