import { useEffect, useState, useRef } from 'react';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { Save, Calculator, Percent, Upload, Image as ImageIcon, X } from 'lucide-react';

export default function Settings() {
  const [company, setCompany] = useState(null);
  const [pricing, setPricing] = useState(null);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);
  const backend = process.env.REACT_APP_BACKEND_URL || '';

  const reload = async () => {
    const { data } = await api.get('/companies/me');
    setCompany(data);
    setPricing(data.pricing_config);
  };

  useEffect(() => { reload(); }, []);

  const save = async () => {
    setError(''); setOk('');
    try {
      const { data } = await api.patch('/companies/me/pricing', pricing);
      setCompany(data); setOk('Configuración guardada');
      setTimeout(() => setOk(''), 2500);
    } catch (e) { setError(formatApiError(e)); }
  };

  const uploadLogo = async (file) => {
    if (!file) return;
    setError(''); setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await api.post('/companies/me/logo', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setCompany(data);
      setOk('Logo actualizado');
      setTimeout(() => setOk(''), 2500);
    } catch (e) { setError(formatApiError(e)); }
    finally { setUploading(false); }
  };

  const removeLogo = async () => {
    if (!window.confirm('¿Eliminar el logo actual?')) return;
    try {
      const { data } = await api.delete('/companies/me/logo');
      setCompany(data);
    } catch (e) { setError(formatApiError(e)); }
  };

  if (!pricing) return <AppShell><div className="p-8 text-ink-400">Cargando…</div></AppShell>;

  const marginPct = Math.round((1 - pricing.margin_divisor) * 100);

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight">Ajustes de empresa</h1>
        <p className="text-ink-500 mt-1">Motor de precios de <span className="font-semibold text-ink-900">{company?.name}</span>.</p>
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="settings-error">{error}</div>}
      {ok && <div className="rounded-xl border border-emerald-200 bg-mint-100 text-emerald-800 px-4 py-3 text-sm mb-4" data-testid="settings-ok">{ok}</div>}

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 card-surface p-6 space-y-6">
          {/* Logo upload */}
          <div>
            <h2 className="font-display font-semibold text-lg text-ink-900 flex items-center gap-2"><ImageIcon className="w-5 h-5 text-brand-500" /> Logo de empresa</h2>
            <p className="text-sm text-ink-500 mt-1">Aparece en el sidebar, los PDF y el enlace público del cliente. Recomendado: PNG/SVG transparente, máx 2 MB.</p>
            <div className="mt-4 flex items-center gap-5">
              <div className="w-28 h-28 rounded-2xl border-2 border-dashed border-ink-200 bg-cream flex items-center justify-center overflow-hidden" data-testid="logo-preview">
                {company?.logo_url
                  ? <img src={`${backend}${company.logo_url}`} alt="Logo" className="max-w-full max-h-full object-contain" />
                  : <ImageIcon className="w-10 h-10 text-ink-300" />}
              </div>
              <div className="flex-1">
                <input ref={fileInputRef} type="file" accept="image/*" className="hidden"
                  onChange={(e) => uploadLogo(e.target.files?.[0])} data-testid="logo-file-input" />
                <button className="btn-primary text-sm" disabled={uploading}
                  onClick={() => fileInputRef.current?.click()} data-testid="upload-logo-btn">
                  <Upload className="w-4 h-4" /> {uploading ? 'Subiendo…' : (company?.logo_url ? 'Cambiar logo' : 'Subir logo')}
                </button>
                {company?.logo_url && (
                  <button className="btn-ghost text-sm ml-2 text-red-600" onClick={removeLogo} data-testid="remove-logo-btn">
                    <X className="w-4 h-4" /> Quitar
                  </button>
                )}
              </div>
            </div>
          </div>

          <hr className="border-ink-100" />

          <div>
            <h2 className="font-display font-semibold text-lg text-ink-900 flex items-center gap-2"><Calculator className="w-5 h-5 text-brand-500" /> Fórmula base</h2>
            <p className="text-sm text-ink-500 mt-1">Costo total ÷ divisor = precio público. Ej: 0.76 ⇒ margen del 24%.</p>
            <div className="grid md:grid-cols-2 gap-4 mt-4">
              <div>
                <label className="label-text">Divisor de margen</label>
                <input type="number" step="0.01" min="0.1" max="1" className="input-field" value={pricing.margin_divisor}
                  onChange={(e) => setPricing((p) => ({ ...p, margin_divisor: +e.target.value }))} data-testid="margin-divisor-input" />
              </div>
              <div className="flex items-end">
                <div className="rounded-xl bg-brand-50 text-brand-500 px-5 py-4 w-full">
                  <p className="text-xs uppercase tracking-widest font-bold">Margen equivalente</p>
                  <p className="font-display text-3xl font-bold">{marginPct}%</p>
                </div>
              </div>
            </div>
          </div>

          <div>
            <h2 className="font-display font-semibold text-lg text-ink-900 flex items-center gap-2"><Percent className="w-5 h-5 text-brand-500" /> Comisiones por canal</h2>
            <div className="grid md:grid-cols-2 gap-4 mt-4">
              {[
                { k: 'directo', label: 'Directo' },
                { k: 'agencia', label: 'Agencia' },
                { k: 'mayorista', label: 'Mayorista' },
                { k: 'operador', label: 'Operador' },
              ].map(({ k, label }) => (
                <div key={k}>
                  <label className="label-text">{label} (decimal, ej. 0.10 = 10%)</label>
                  <input type="number" step="0.01" min="0" max="1" className="input-field"
                    value={pricing.commissions[k]}
                    onChange={(e) => setPricing((p) => ({ ...p, commissions: { ...p.commissions, [k]: +e.target.value } }))}
                    data-testid={`commission-${k}`} />
                </div>
              ))}
            </div>
          </div>

          <div>
            <h2 className="font-display font-semibold text-lg text-ink-900">Menores</h2>
            <div className="grid md:grid-cols-3 gap-4 mt-4">
              <div><label className="label-text">Edad mín.</label><input type="number" className="input-field" value={pricing.minor_age_min} onChange={(e) => setPricing((p) => ({ ...p, minor_age_min: +e.target.value }))} data-testid="minor-min" /></div>
              <div><label className="label-text">Edad máx.</label><input type="number" className="input-field" value={pricing.minor_age_max} onChange={(e) => setPricing((p) => ({ ...p, minor_age_max: +e.target.value }))} data-testid="minor-max" /></div>
              <div><label className="label-text">Descuento (decimal)</label><input type="number" step="0.01" className="input-field" value={pricing.minor_discount} onChange={(e) => setPricing((p) => ({ ...p, minor_discount: +e.target.value }))} data-testid="minor-discount" /></div>
            </div>
          </div>

          <div className="pt-4 border-t border-ink-100 flex justify-end">
            <button className="btn-primary" onClick={save} data-testid="save-pricing-btn"><Save className="w-4 h-4" /> Guardar</button>
          </div>
        </div>

        <aside className="card-surface p-6">
          <h3 className="font-display font-semibold text-ink-900">Ejemplo</h3>
          <p className="text-sm text-ink-500 mt-1">Cómo se aplica a un costo de $7,600 MXN:</p>
          <div className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between"><span>Costo base</span><span className="font-semibold">$7,600</span></div>
            <div className="flex justify-between"><span>÷ {pricing.margin_divisor}</span><span className="font-semibold">$ {(7600 / pricing.margin_divisor).toFixed(0)}</span></div>
            <div className="rounded-lg bg-mint-100 text-emerald-800 p-3">
              <p className="text-xs font-bold uppercase tracking-widest">Precio público</p>
              <p className="font-display text-2xl font-bold">${(7600 / pricing.margin_divisor).toFixed(0)}</p>
            </div>
            <p className="text-xs text-ink-400">Comisión agencia {(pricing.commissions.agencia * 100).toFixed(0)}%: -${((7600 / pricing.margin_divisor) * pricing.commissions.agencia).toFixed(0)}</p>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}
