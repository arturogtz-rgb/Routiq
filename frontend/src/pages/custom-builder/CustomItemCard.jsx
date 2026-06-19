import { Trash2, Sparkles } from 'lucide-react';
import { UNITS, UNIT_ES, CATEGORIES, CAT_ICON, money } from './constants';

export function CustomItemCard({ it, idx, currency, updateItem, removeItem, unitPriceFor, itemSubtotal, publicPrice }) {
  const Icon = CAT_ICON[it.category] || Sparkles;
  const priceType = it.price_type || 'neto';
  return (
    <div className="rounded-xl border border-ink-100 p-4 bg-cream" data-testid={`custom-item-${idx}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="pill bg-white text-brand-500 text-xs capitalize flex items-center gap-1"><Icon className="w-3.5 h-3.5" /> {it.category}</span>
        <button type="button" className="text-red-600 hover:text-red-800" onClick={() => removeItem(idx)} data-testid={`custom-item-remove-${idx}`}><Trash2 className="w-4 h-4" /></button>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <div><label className="label-text">Concepto</label><input className="input-field" value={it.name} placeholder="Ej. Hotel Xcaret 3 noches" onChange={(e) => updateItem(idx, { name: e.target.value })} data-testid={`custom-item-name-${idx}`} /></div>
        <div><label className="label-text">Categoría</label>
          <select className="input-field" value={it.category} onChange={(e) => updateItem(idx, { category: e.target.value })} data-testid={`custom-item-cat-${idx}`}>
            {CATEGORIES.map((c) => <option key={c.v} value={c.v}>{c.label}</option>)}
          </select>
        </div>
      </div>
      <div className="mt-3"><label className="label-text">Descripción (opcional)</label><input className="input-field" value={it.description} onChange={(e) => updateItem(idx, { description: e.target.value })} data-testid={`custom-item-desc-${idx}`} /></div>
      <div className="mt-3">
        <label className="label-text">Tipo de precio</label>
        <div className="flex gap-2" data-testid={`custom-item-pricetype-${idx}`}>
          <button type="button" onClick={() => updateItem(idx, { price_type: 'neto' })}
            className={`flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-colors ${priceType === 'neto' ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-ink-100 text-ink-500 hover:border-brand-300'}`}
            data-testid={`custom-item-pricetype-neto-${idx}`}>🔒 Tarifa neta</button>
          <button type="button" onClick={() => updateItem(idx, { price_type: 'publico' })}
            className={`flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-colors ${priceType === 'publico' ? 'border-emerald-500 bg-mint-100 text-emerald-700' : 'border-ink-100 text-ink-500 hover:border-emerald-300'}`}
            data-testid={`custom-item-pricetype-publico-${idx}`}>💰 Precio público</button>
        </div>
        <p className="text-[11px] text-ink-400 mt-1">{priceType === 'publico' ? 'El monto ya es público; se le descuenta la comisión del canal.' : 'Tarifa neta confidencial; el público se calcula (neto / divisor) y luego según el canal.'}</p>
      </div>
      <div className="grid md:grid-cols-3 gap-3 mt-3">
        <div><label className="label-text">{priceType === 'publico' ? 'Precio público' : 'Tarifa neta'}</label><input type="number" min="0" step="0.01" className="input-field" value={it.net_price} onChange={(e) => updateItem(idx, { net_price: +e.target.value || 0 })} data-testid={`custom-item-net-${idx}`} /></div>
        <div><label className="label-text">Unidad de cobro</label>
          <select className="input-field" value={it.unit} onChange={(e) => updateItem(idx, { unit: e.target.value })} data-testid={`custom-item-unit-${idx}`}>
            {UNITS.map((u) => <option key={u.v} value={u.v}>{u.label}</option>)}
          </select>
        </div>
        <div><label className="label-text">Cantidad{it.category === 'hospedaje' ? ' (hab./pax)' : ''}</label>
          <input type="number" min="1" className="input-field" value={it.qty} onChange={(e) => updateItem(idx, { qty: Math.max(1, +e.target.value || 1) })} data-testid={`custom-item-qty-${idx}`} />
        </div>
      </div>
      {it.category === 'hospedaje' ? (
        <div className="grid md:grid-cols-3 gap-3 mt-3" data-testid={`custom-item-lodging-${idx}`}>
          <div><label className="label-text">Check-in</label><input type="date" className="input-field" value={it.checkin || ''} onChange={(e) => updateItem(idx, { checkin: e.target.value })} data-testid={`custom-item-checkin-${idx}`} /></div>
          <div><label className="label-text">Check-out</label><input type="date" className="input-field" value={it.checkout || ''} onChange={(e) => updateItem(idx, { checkout: e.target.value })} data-testid={`custom-item-checkout-${idx}`} /></div>
          <div><label className="label-text">Noches (auto)</label><input className="input-field bg-ink-50" value={it.nights || 0} readOnly disabled data-testid={`custom-item-nights-${idx}`} /></div>
        </div>
      ) : it.category === 'acceso' ? (
        <div className="grid md:grid-cols-3 gap-3 mt-3">
          <div><label className="label-text">Fecha del acceso</label><input type="date" className="input-field" value={it.service_date || ''} onChange={(e) => updateItem(idx, { service_date: e.target.value })} data-testid={`custom-item-date-${idx}`} /></div>
        </div>
      ) : it.category === 'tour' ? (
        <div className="grid md:grid-cols-3 gap-3 mt-3">
          <div><label className="label-text">Fecha del servicio</label><input type="date" className="input-field" value={it.service_date || ''} onChange={(e) => updateItem(idx, { service_date: e.target.value })} data-testid={`custom-item-date-${idx}`} /></div>
          <div><label className="label-text">Hora inicio</label><input type="time" className="input-field" value={it.start_time || ''} onChange={(e) => updateItem(idx, { start_time: e.target.value })} data-testid={`custom-item-start-${idx}`} /></div>
        </div>
      ) : (
        <div className="grid md:grid-cols-3 gap-3 mt-3">
          <div><label className="label-text">Fecha del servicio</label><input type="date" className="input-field" value={it.service_date || ''} onChange={(e) => updateItem(idx, { service_date: e.target.value })} data-testid={`custom-item-date-${idx}`} /></div>
          <div><label className="label-text">Hora inicio</label><input type="time" className="input-field" value={it.start_time || ''} onChange={(e) => updateItem(idx, { start_time: e.target.value })} data-testid={`custom-item-start-${idx}`} /></div>
          <div><label className="label-text">Hora fin</label><input type="time" className="input-field" value={it.end_time || ''} onChange={(e) => updateItem(idx, { end_time: e.target.value })} data-testid={`custom-item-end-${idx}`} /></div>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-1 mt-3 text-sm">
        <span className="text-ink-400">{priceType === 'publico'
          ? <>Público: <b className="text-ink-700">{money(Number(it.net_price) || 0, currency)}</b></>
          : <>Neto <b className="text-ink-700">{money(Number(it.net_price) || 0, currency)}</b> · Público <b className="text-ink-700">{money(publicPrice(it.net_price), currency)}</b></>} / {UNIT_ES[it.unit]}</span>
        <span className="font-semibold text-brand-600" data-testid={`custom-item-subtotal-${idx}`}>Subtotal: {money(itemSubtotal(it), currency)}</span>
      </div>
    </div>
  );
}
