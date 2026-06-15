import { useEffect, useRef, useState } from 'react';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { Save, UploadCloud, Eye, EyeOff, Rocket, RotateCcw, Globe, LogIn, Layers, Palette, Image as ImageIcon, Loader2, CheckCircle2, ChevronUp, ChevronDown, Plus, Trash2 } from 'lucide-react';
import { applyTheme, THEME_PRESETS } from '@/lib/theme';

const backend = process.env.REACT_APP_BACKEND_URL || '';

function Field({ label, value, onChange, type = 'text', rows, placeholder, testid }) {
  return (
    <div>
      <label className="label-text">{label}</label>
      {rows ? (
        <textarea rows={rows} className="input-field" value={value || ''} placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)} data-testid={testid} />
      ) : (
        <input type={type} className="input-field" value={value || ''} placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)} data-testid={testid} />
      )}
    </div>
  );
}

function ImageField({ label, value, onChange, onPersist, testid }) {
  const ref = useRef(null);
  const [up, setUp] = useState(false);
  const pick = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUp(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await api.post('/site-settings/upload-image', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      onChange(data.url);
      if (onPersist) await onPersist(data.url);
    } catch (_e) { /* noop */ }
    finally { setUp(false); }
  };
  return (
    <div>
      <label className="label-text">{label}</label>
      <div className="flex items-center gap-3">
        <div className="w-20 h-14 rounded-lg bg-ink-100 overflow-hidden flex items-center justify-center shrink-0">
          {value ? <img src={value.startsWith('http') ? value : `${backend}${value}`} alt="" className="w-full h-full object-cover" /> : <ImageIcon className="w-5 h-5 text-ink-400" />}
        </div>
        <button type="button" className="btn-secondary text-sm" onClick={() => ref.current?.click()} disabled={up} data-testid={testid}>
          {up ? <Loader2 className="w-4 h-4 animate-spin" /> : <UploadCloud className="w-4 h-4" />} Subir imagen
        </button>
        {value && <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => onChange('')}>Quitar</button>}
        <input ref={ref} type="file" accept="image/*" className="hidden" onChange={pick} />
      </div>
    </div>
  );
}

export default function MasterSite() {
  const [landing, setLanding] = useState(null);
  const [login, setLogin] = useState(null);
  const [theme, setTheme] = useState(null);
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState('landing');

  const load = async () => {
    try {
      const { data } = await api.get('/site-settings');
      setLanding(data.draft.landing);
      setLogin(data.draft.login);
      setTheme(data.draft.theme || { preset: 'corporate', primary: '#185FA5' });
    } catch (e) { setError(formatApiError(e)); }
  };
  useEffect(() => { load(); }, []);

  // Live-preview the theme inside the editor as the Master adjusts it.
  useEffect(() => { if (theme) applyTheme(theme); }, [theme]);

  const setL = (k, v) => setLanding((s) => ({ ...s, [k]: v }));
  const setLg = (k, v) => setLogin((s) => ({ ...s, [k]: v }));

  // --- Affiliate logos (carousel) ---
  const addAffiliateLogo = (url, name = '') => setLanding((s) => ({
    ...s, affiliate_logos: [...(s.affiliate_logos || []), { url, name }],
  }));
  const setAffiliateName = (idx, name) => setLanding((s) => ({
    ...s, affiliate_logos: (s.affiliate_logos || []).map((l, i) => (i === idx ? { ...l, name } : l)),
  }));
  const removeAffiliateLogo = (idx) => setLanding((s) => ({
    ...s, affiliate_logos: (s.affiliate_logos || []).filter((_, i) => i !== idx),
  }));
  const affRef = useRef(null);
  const uploadAffiliate = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData(); fd.append('file', file);
    try {
      const { data } = await api.post('/site-settings/upload-image', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      addAffiliateLogo(data.url, (file.name || '').replace(/\.[^.]+$/, ''));
    } catch (_e) { /* noop */ }
    e.target.value = '';
  };
  const setTh = (k, v) => setTheme((s) => ({ ...s, [k]: v }));

  // --- Section ordering / visibility ---
  const moveSection = (idx, dir) => setLanding((s) => {
    const arr = [...(s.sections || [])];
    const j = idx + dir;
    if (j < 0 || j >= arr.length) return s;
    [arr[idx], arr[j]] = [arr[j], arr[idx]];
    return { ...s, sections: arr };
  });
  const toggleSection = (idx) => setLanding((s) => ({
    ...s,
    sections: (s.sections || []).map((x, i) => (i === idx ? { ...x, visible: !x.visible } : x)),
  }));

  // --- Pricing tiers ---
  const setTier = (idx, key, val) => setLanding((s) => ({
    ...s,
    pricing_tiers: (s.pricing_tiers || []).map((t, i) => (i === idx ? { ...t, [key]: val } : t)),
  }));
  const addTier = () => setLanding((s) => ({
    ...s,
    pricing_tiers: [...(s.pricing_tiers || []), { name: 'Nuevo plan', price: '$0', period: '/mes', highlight: false, cta: 'Comenzar', perks: [] }],
  }));
  const removeTier = (idx) => setLanding((s) => ({
    ...s,
    pricing_tiers: (s.pricing_tiers || []).filter((_, i) => i !== idx),
  }));

  // Persist a single section immediately to the draft (used after image uploads
  // so a freshly uploaded image is never lost on navigation).
  const persistLanding = async (patch) => { await api.patch('/site-settings', { landing: { ...landing, ...patch } }); };
  const persistLogin = async (patch) => { await api.patch('/site-settings', { login: { ...login, ...patch } }); };

  const saveDraft = async () => {
    setSaving(true); setError(''); setOk('');
    try {
      await api.patch('/site-settings', { landing, login, theme });
      setOk('Borrador guardado'); setTimeout(() => setOk(''), 2500);
    } catch (e) { setError(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const publish = async () => {
    setSaving(true); setError(''); setOk('');
    try {
      await api.patch('/site-settings', { landing, login, theme });
      await api.post('/site-settings/publish');
      setOk('¡Publicado! Los cambios ya están en vivo.'); setTimeout(() => setOk(''), 3500);
    } catch (e) { setError(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const resetDraft = async () => {
    if (!window.confirm('¿Descartar cambios y volver a la versión publicada?')) return;
    await api.post('/site-settings/reset-draft');
    await load();
  };

  const preview = async (path) => {
    // persist current edits to draft, then open preview
    await api.patch('/site-settings', { landing, login, theme });
    window.open(`${path}?preview=1`, '_blank');
  };

  if (!landing || !login || !theme) {
    return <AppShell><div className="text-ink-400">Cargando…</div></AppShell>;
  }

  return (
    <AppShell>
      <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <p className="pill bg-brand-500 text-white mb-3">Panel Master</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold text-ink-900 tracking-tight">Editor del sitio</h1>
          <p className="text-ink-500 mt-1">Edita la landing y el login. Previsualiza y publica sin tocar código.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-ghost text-sm" onClick={resetDraft} data-testid="reset-draft-btn"><RotateCcw className="w-4 h-4" /> Descartar</button>
          <button className="btn-secondary text-sm" onClick={saveDraft} disabled={saving} data-testid="save-draft-btn"><Save className="w-4 h-4" /> Guardar borrador</button>
          <button className="btn-primary text-sm" onClick={publish} disabled={saving} data-testid="publish-btn"><Rocket className="w-4 h-4" /> Publicar</button>
        </div>
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="site-error">{error}</div>}
      {ok && <div className="rounded-xl border border-emerald-200 bg-mint-100 text-emerald-800 px-4 py-3 text-sm mb-4 flex items-center gap-2" data-testid="site-ok"><CheckCircle2 className="w-4 h-4" /> {ok}</div>}

      <div className="flex gap-2 mb-6">
        <button onClick={() => setTab('landing')} className={`pill ${tab === 'landing' ? 'bg-brand-500 text-white' : 'bg-white border border-ink-100 text-ink-700'}`} data-testid="tab-landing"><Globe className="w-3.5 h-3.5" /> Landing</button>
        <button onClick={() => setTab('sections')} className={`pill ${tab === 'sections' ? 'bg-brand-500 text-white' : 'bg-white border border-ink-100 text-ink-700'}`} data-testid="tab-sections"><Layers className="w-3.5 h-3.5" /> Secciones y precios</button>
        <button onClick={() => setTab('theme')} className={`pill ${tab === 'theme' ? 'bg-brand-500 text-white' : 'bg-white border border-ink-100 text-ink-700'}`} data-testid="tab-theme"><Palette className="w-3.5 h-3.5" /> Tema y color</button>
        <button onClick={() => setTab('login')} className={`pill ${tab === 'login' ? 'bg-brand-500 text-white' : 'bg-white border border-ink-100 text-ink-700'}`} data-testid="tab-login"><LogIn className="w-3.5 h-3.5" /> Login</button>
      </div>

      {tab === 'landing' && (
        <div className="grid lg:grid-cols-2 gap-6">
          <div className="card-surface p-6 space-y-4">
            <h3 className="font-display font-semibold text-ink-900">Sección principal (Hero)</h3>
            <Field label="Etiqueta superior (pill)" value={landing.hero_pill} onChange={(v) => setL('hero_pill', v)} testid="ld-hero-pill" />
            <Field label="Título principal" value={landing.hero_title} onChange={(v) => setL('hero_title', v)} testid="ld-hero-title" />
            <Field label="Título resaltado (color)" value={landing.hero_highlight} onChange={(v) => setL('hero_highlight', v)} testid="ld-hero-highlight" />
            <Field label="Subtítulo / descripción" value={landing.hero_subtitle} onChange={(v) => setL('hero_subtitle', v)} rows={3} testid="ld-hero-subtitle" />
            <div className="grid grid-cols-2 gap-3">
              <Field label="Botón principal (CTA)" value={landing.cta_primary} onChange={(v) => setL('cta_primary', v)} testid="ld-cta-primary" />
              <Field label="Botón secundario" value={landing.cta_secondary} onChange={(v) => setL('cta_secondary', v)} testid="ld-cta-secondary" />
            </div>
            <Field label="Texto de prueba social" value={landing.waitlist_text} onChange={(v) => setL('waitlist_text', v)} testid="ld-waitlist" />
            <ImageField label="Imagen de fondo del Hero" value={landing.hero_image_url} onChange={(v) => setL('hero_image_url', v)} onPersist={(url) => persistLanding({ hero_image_url: url })} testid="ld-hero-image" />
          </div>
          <div className="card-surface p-6 space-y-4">
            <h3 className="font-display font-semibold text-ink-900">Secciones</h3>
            <Field label="Título de características" value={landing.features_title} onChange={(v) => setL('features_title', v)} rows={2} testid="ld-features-title" />
            <Field label="Subtítulo de características" value={landing.features_subtitle} onChange={(v) => setL('features_subtitle', v)} rows={2} testid="ld-features-subtitle" />
            <ImageField label="Imagen 'Cómo funciona'" value={landing.feature_image_url} onChange={(v) => setL('feature_image_url', v)} onPersist={(url) => persistLanding({ feature_image_url: url })} testid="ld-feature-image" />
            <Field label="Título CTA final" value={landing.final_cta_title} onChange={(v) => setL('final_cta_title', v)} testid="ld-finalcta-title" />
            <Field label="Subtítulo CTA final" value={landing.final_cta_subtitle} onChange={(v) => setL('final_cta_subtitle', v)} rows={2} testid="ld-finalcta-subtitle" />
            <button className="btn-secondary text-sm w-full" onClick={() => preview('/')} data-testid="preview-landing-btn"><Eye className="w-4 h-4" /> Vista previa de la landing</button>
          </div>
        </div>
      )}

      {tab === 'sections' && (
        <div className="grid lg:grid-cols-2 gap-6">
          <div className="card-surface p-6 space-y-4">
            <div>
              <h3 className="font-display font-semibold text-ink-900">Orden y visibilidad de secciones</h3>
              <p className="text-ink-500 text-sm mt-1">Reordena con las flechas y muestra/oculta secciones de la landing. El Hero (arriba) y el pie de página son fijos.</p>
            </div>
            <div className="space-y-2" data-testid="sections-list">
              {(landing.sections || []).map((sec, idx) => (
                <div key={sec.key} className={`flex items-center gap-3 rounded-xl border p-3 ${sec.visible ? 'border-ink-100 bg-white' : 'border-dashed border-ink-200 bg-ink-50 opacity-70'}`} data-testid={`section-row-${sec.key}`}>
                  <div className="flex flex-col">
                    <button type="button" className="text-ink-400 hover:text-brand-500 disabled:opacity-30" onClick={() => moveSection(idx, -1)} disabled={idx === 0} data-testid={`section-up-${sec.key}`}><ChevronUp className="w-4 h-4" /></button>
                    <button type="button" className="text-ink-400 hover:text-brand-500 disabled:opacity-30" onClick={() => moveSection(idx, 1)} disabled={idx === (landing.sections.length - 1)} data-testid={`section-down-${sec.key}`}><ChevronDown className="w-4 h-4" /></button>
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-ink-900 text-sm">{sec.label}</p>
                    <p className="text-xs text-ink-400">{sec.visible ? 'Visible' : 'Oculta'}</p>
                  </div>
                  <button type="button" className={`pill text-xs ${sec.visible ? 'bg-mint-100 text-emerald-800' : 'bg-ink-100 text-ink-500'}`} onClick={() => toggleSection(idx)} data-testid={`section-toggle-${sec.key}`}>
                    {sec.visible ? <><Eye className="w-3.5 h-3.5" /> Mostrar</> : <><EyeOff className="w-3.5 h-3.5" /> Ocultar</>}
                  </button>
                </div>
              ))}
            </div>
            <button className="btn-secondary text-sm w-full" onClick={() => preview('/')} data-testid="preview-sections-btn"><Eye className="w-4 h-4" /> Vista previa de la landing</button>
          </div>

          <div className="card-surface p-6 space-y-4">
            <h3 className="font-display font-semibold text-ink-900">Sección de Precios / Planes</h3>
            <Field label="Etiqueta (pill)" value={landing.pricing_pill} onChange={(v) => setL('pricing_pill', v)} testid="pr-pill" />
            <Field label="Título" value={landing.pricing_title} onChange={(v) => setL('pricing_title', v)} testid="pr-title" />
            <Field label="Subtítulo" value={landing.pricing_subtitle} onChange={(v) => setL('pricing_subtitle', v)} rows={2} testid="pr-subtitle" />

            <div className="border-t border-ink-100 pt-3 space-y-4">
              {(landing.pricing_tiers || []).map((t, idx) => (
                <div key={idx} className="rounded-xl border border-ink-100 p-4 space-y-3 bg-ink-50/40" data-testid={`tier-card-${idx}`}>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-ink-400">Plan {idx + 1}</span>
                    <button type="button" className="text-red-600 hover:text-red-700" onClick={() => removeTier(idx)} data-testid={`tier-remove-${idx}`}><Trash2 className="w-4 h-4" /></button>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Nombre" value={t.name} onChange={(v) => setTier(idx, 'name', v)} testid={`tier-name-${idx}`} />
                    <Field label="Precio" value={t.price} onChange={(v) => setTier(idx, 'price', v)} testid={`tier-price-${idx}`} />
                    <Field label="Periodo" value={t.period} onChange={(v) => setTier(idx, 'period', v)} placeholder="/mes" testid={`tier-period-${idx}`} />
                    <Field label="Texto del botón" value={t.cta} onChange={(v) => setTier(idx, 'cta', v)} testid={`tier-cta-${idx}`} />
                  </div>
                  <div>
                    <label className="label-text">Beneficios (uno por línea)</label>
                    <textarea rows={4} className="input-field" value={(t.perks || []).join('\n')} onChange={(e) => setTier(idx, 'perks', e.target.value.split('\n'))} data-testid={`tier-perks-${idx}`} />
                  </div>
                  <label className="flex items-center gap-2 text-sm text-ink-700 cursor-pointer">
                    <input type="checkbox" checked={!!t.highlight} onChange={(e) => setTier(idx, 'highlight', e.target.checked)} data-testid={`tier-highlight-${idx}`} />
                    Destacar este plan (resaltado)
                  </label>
                </div>
              ))}
              <button className="btn-secondary text-sm w-full" onClick={addTier} data-testid="add-tier-btn"><Plus className="w-4 h-4" /> Agregar plan</button>
            </div>
          </div>

          <div className="card-surface p-6 space-y-4 lg:col-span-2" data-testid="affiliates-manager">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-display font-semibold text-ink-900">Logos de empresas afiliadas (carrusel)</h3>
                <p className="text-ink-500 text-sm mt-1">Sube los logos que rotarán en la landing. Actívalo/ocúltalo desde la lista de secciones de arriba.</p>
              </div>
              <button className="btn-primary text-sm" onClick={() => affRef.current?.click()} data-testid="add-affiliate-btn"><UploadCloud className="w-4 h-4" /> Subir logo</button>
              <input ref={affRef} type="file" accept="image/*" className="hidden" onChange={uploadAffiliate} />
            </div>
            <Field label="Título de la sección" value={landing.affiliates_title} onChange={(v) => setL('affiliates_title', v)} testid="affiliates-title" />
            <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-3">
              {(landing.affiliate_logos || []).map((l, idx) => (
                <div key={idx} className="rounded-xl border border-ink-100 p-3 flex items-center gap-3" data-testid={`affiliate-row-${idx}`}>
                  <div className="w-16 h-12 rounded bg-ink-50 flex items-center justify-center overflow-hidden shrink-0">
                    <img src={l.url?.startsWith('http') ? l.url : `${backend}${l.url}`} alt={l.name} className="max-w-full max-h-full object-contain" />
                  </div>
                  <input className="input-field text-sm" value={l.name || ''} placeholder="Nombre" onChange={(e) => setAffiliateName(idx, e.target.value)} data-testid={`affiliate-name-${idx}`} />
                  <button className="text-red-600 hover:text-red-700 shrink-0" onClick={() => removeAffiliateLogo(idx)} data-testid={`affiliate-remove-${idx}`}><Trash2 className="w-4 h-4" /></button>
                </div>
              ))}
              {(landing.affiliate_logos || []).length === 0 && <p className="text-ink-400 text-sm italic">Aún no hay logos. Sube el primero.</p>}
            </div>
          </div>
        </div>
      )}

      {tab === 'theme' && (
        <div className="grid lg:grid-cols-2 gap-6">
          <div className="card-surface p-6 space-y-5" data-testid="theme-panel">
            <div>
              <h3 className="font-display font-semibold text-ink-900">Tema de color</h3>
              <p className="text-ink-500 text-sm mt-1">Elige un preset y ajusta el color principal. Se aplica a la landing pública y al panel de la app para coherencia visual total.</p>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {Object.entries(THEME_PRESETS).map(([key, p]) => (
                <button key={key} type="button" onClick={() => setTheme({ preset: key, primary: p.primary })}
                  className={`rounded-xl border p-4 text-center transition-all ${theme.preset === key ? 'border-brand-500 ring-2 ring-brand-200' : 'border-ink-100 hover:border-brand-300'}`}
                  data-testid={`theme-preset-${key}`}>
                  <span className="block w-full h-10 rounded-lg mb-2" style={{ background: p.primary }} />
                  <span className="text-sm font-semibold text-ink-900">{p.label}</span>
                </button>
              ))}
            </div>
            <div>
              <label className="label-text">Color principal (personalizado)</label>
              <div className="flex items-center gap-3">
                <input type="color" value={theme.primary || '#185FA5'} onChange={(e) => setTh('primary', e.target.value)} className="w-12 h-10 rounded-lg border border-ink-200 cursor-pointer" data-testid="theme-color" />
                <input className="input-field" value={theme.primary || ''} onChange={(e) => setTh('primary', e.target.value)} data-testid="theme-color-hex" />
              </div>
            </div>
            <button className="btn-secondary text-sm w-full" onClick={() => preview('/')} data-testid="preview-theme-btn"><Eye className="w-4 h-4" /> Vista previa con el tema</button>
          </div>
          <div className="card-surface p-6 space-y-4">
            <h3 className="font-display font-semibold text-ink-900">Vista previa</h3>
            <p className="text-ink-500 text-sm">Así se verán los elementos con el color elegido:</p>
            <div className="flex flex-wrap gap-3 items-center">
              <button className="btn-primary" data-testid="theme-demo-btn">Botón primario</button>
              <span className="pill bg-brand-50 text-brand-500">Etiqueta</span>
              <span className="pill bg-brand-500 text-white">Activo</span>
            </div>
            <div className="rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white p-5">
              <p className="text-sm uppercase tracking-widest opacity-80">Total</p>
              <p className="font-display font-bold text-3xl">$12,500 MXN</p>
            </div>
            <div className="flex gap-2 text-sm">
              {[50, 100, 300, 500, 700, 900].map((sh) => (
                <span key={sh} className="flex-1 h-10 rounded" style={{ background: `rgb(var(--brand-${sh}))` }} />
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === 'login' && (
        <div className="grid lg:grid-cols-2 gap-6">
          <div className="card-surface p-6 space-y-4">
            <h3 className="font-display font-semibold text-ink-900">Marca del login</h3>
            <ImageField label="Logo" value={login.logo_url} onChange={(v) => setLg('logo_url', v)} onPersist={(url) => persistLogin({ logo_url: url })} testid="lg-logo" />
            <div>
              <label className="label-text">Color principal</label>
              <div className="flex items-center gap-3">
                <input type="color" value={login.primary_color || '#185FA5'} onChange={(e) => setLg('primary_color', e.target.value)} className="w-12 h-10 rounded-lg border border-ink-200 cursor-pointer" data-testid="lg-color" />
                <input className="input-field" value={login.primary_color || ''} onChange={(e) => setLg('primary_color', e.target.value)} data-testid="lg-color-hex" />
              </div>
            </div>
            <button className="btn-secondary text-sm w-full" onClick={() => preview('/login')} data-testid="preview-login-btn"><Eye className="w-4 h-4" /> Vista previa del login</button>
          </div>
          <div className="card-surface p-6 space-y-4">
            <h3 className="font-display font-semibold text-ink-900">Textos</h3>
            <Field label="Etiqueta lateral (badge)" value={login.side_badge} onChange={(v) => setLg('side_badge', v)} testid="lg-badge" />
            <Field label="Frase destacada" value={login.side_quote} onChange={(v) => setLg('side_quote', v)} rows={2} testid="lg-quote" />
            <Field label="Autor de la frase" value={login.side_author} onChange={(v) => setLg('side_author', v)} testid="lg-author" />
            <Field label="Título de bienvenida" value={login.welcome_title} onChange={(v) => setLg('welcome_title', v)} testid="lg-welcome-title" />
            <Field label="Subtítulo de bienvenida" value={login.welcome_subtitle} onChange={(v) => setLg('welcome_subtitle', v)} testid="lg-welcome-subtitle" />
          </div>
        </div>
      )}
    </AppShell>
  );
}
