import { useEffect, useRef, useState } from 'react';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { Save, UploadCloud, Eye, Rocket, RotateCcw, Globe, LogIn, Image as ImageIcon, Loader2, CheckCircle2 } from 'lucide-react';

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
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState('landing');

  const load = async () => {
    try {
      const { data } = await api.get('/site-settings');
      setLanding(data.draft.landing);
      setLogin(data.draft.login);
    } catch (e) { setError(formatApiError(e)); }
  };
  useEffect(() => { load(); }, []);

  const setL = (k, v) => setLanding((s) => ({ ...s, [k]: v }));
  const setLg = (k, v) => setLogin((s) => ({ ...s, [k]: v }));

  // Persist a single section immediately to the draft (used after image uploads
  // so a freshly uploaded image is never lost on navigation).
  const persistLanding = async (patch) => { await api.patch('/site-settings', { landing: { ...landing, ...patch } }); };
  const persistLogin = async (patch) => { await api.patch('/site-settings', { login: { ...login, ...patch } }); };

  const saveDraft = async () => {
    setSaving(true); setError(''); setOk('');
    try {
      await api.patch('/site-settings', { landing, login });
      setOk('Borrador guardado'); setTimeout(() => setOk(''), 2500);
    } catch (e) { setError(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const publish = async () => {
    setSaving(true); setError(''); setOk('');
    try {
      await api.patch('/site-settings', { landing, login });
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
    await api.patch('/site-settings', { landing, login });
    window.open(`${path}?preview=1`, '_blank');
  };

  if (!landing || !login) {
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
