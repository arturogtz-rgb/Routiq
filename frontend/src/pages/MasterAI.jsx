import { useEffect, useState } from 'react';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { Sparkles, Save, Plug, CheckCircle2, AlertTriangle, KeyRound } from 'lucide-react';

const PROVIDERS = [
  { id: 'anthropic', label: 'Anthropic (Claude)', hint: 'Recomendado para resúmenes en español', keyUrl: 'https://console.anthropic.com/settings/keys', keyPrefix: 'sk-ant-...' },
  { id: 'openai', label: 'OpenAI (GPT)', hint: 'GPT-4o', keyUrl: 'https://platform.openai.com/api-keys', keyPrefix: 'sk-...' },
  { id: 'google', label: 'Google (Gemini)', hint: 'Gemini 1.5/2.0', keyUrl: 'https://aistudio.google.com/app/apikey', keyPrefix: 'AIza...' },
];

export default function MasterAI() {
  const [settings, setSettings] = useState(null);
  const [provider, setProvider] = useState('anthropic');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [defaults, setDefaults] = useState({});
  const [error, setError] = useState('');
  const [ok, setOk] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get('/master/ai-settings');
      setSettings(data); setProvider(data.provider); setModel(data.model); setDefaults(data.default_models || {});
    } catch (e) { setError(formatApiError(e)); }
  };
  useEffect(() => { load(); }, []);

  const changeProvider = (p) => {
    setProvider(p);
    // suggest default model for the provider unless user already typed one matching prev provider default
    setModel(defaults[p] || '');
    setTestResult(null);
  };

  const save = async () => {
    setError(''); setOk(''); setSaving(true);
    try {
      const payload = { provider, model };
      if (apiKey) payload.api_key = apiKey;
      const { data } = await api.patch('/master/ai-settings', payload);
      setSettings((s) => ({ ...s, ...data })); setApiKey('');
      setOk('Configuración de IA guardada. Aplica a todas las empresas.');
      setTimeout(() => setOk(''), 3500);
    } catch (e) { setError(formatApiError(e)); }
    finally { setSaving(false); }
  };

  const test = async () => {
    setError(''); setOk(''); setTestResult(null); setTesting(true);
    try {
      const payload = { provider, model };
      if (apiKey) payload.api_key = apiKey;
      const { data } = await api.post('/master/ai-settings/test', payload);
      setTestResult({ ok: true, text: data.reply });
    } catch (e) { setTestResult({ ok: false, text: formatApiError(e) }); }
    finally { setTesting(false); }
  };

  const current = PROVIDERS.find((p) => p.id === provider) || PROVIDERS[0];

  return (
    <AppShell>
      <div className="mb-8">
        <p className="pill bg-brand-500 text-white mb-3">Panel Master</p>
        <h1 className="font-display text-3xl md:text-4xl font-semibold text-ink-900 tracking-tight flex items-center gap-2">
          <Sparkles className="w-7 h-7 text-brand-500" /> Inteligencia Artificial
        </h1>
        <p className="text-ink-500 mt-1">Configura el proveedor de IA con tu propia API key. Aplica a <b>todas las empresas</b> del sistema (resúmenes de chat, siguiente paso, mensajes sugeridos).</p>
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="ai-error">{error}</div>}
      {ok && <div className="rounded-xl border border-emerald-200 bg-mint-100 text-emerald-800 px-4 py-3 text-sm mb-4" data-testid="ai-ok">{ok}</div>}

      <div className="max-w-2xl card-surface p-6 space-y-5">
        {settings && (
          <div className="flex items-center gap-2 text-sm" data-testid="ai-status">
            {settings.api_key_set
              ? <><CheckCircle2 className="w-4 h-4 text-emerald-600" /> <span className="text-emerald-700">IA activa · key {settings.api_key_masked}</span></>
              : <><AlertTriangle className="w-4 h-4 text-amber-600" /> <span className="text-amber-700">Aún no hay API key configurada. La IA no funcionará hasta que guardes una.</span></>}
          </div>
        )}

        <div>
          <label className="label-text">Proveedor de IA</label>
          <div className="grid sm:grid-cols-3 gap-2 mt-1">
            {PROVIDERS.map((p) => (
              <button key={p.id} onClick={() => changeProvider(p.id)} data-testid={`ai-provider-${p.id}`}
                className={`rounded-xl border-2 px-3 py-3 text-left transition-colors ${provider === p.id ? 'border-brand-500 bg-brand-50' : 'border-ink-100 hover:border-ink-200'}`}>
                <p className="font-semibold text-ink-900 text-sm">{p.label}</p>
                <p className="text-[11px] text-ink-500 mt-0.5">{p.hint}</p>
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="label-text">Modelo</label>
          <input className="input-field" value={model} onChange={(e) => setModel(e.target.value)} placeholder={defaults[provider] || ''} data-testid="ai-model-input" />
          <p className="text-xs text-ink-400 mt-1">Sugerido: <button type="button" className="text-brand-500 underline" onClick={() => setModel(defaults[provider] || '')}>{defaults[provider]}</button>. Puedes escribir cualquier modelo válido del proveedor.</p>
        </div>

        <div>
          <label className="label-text flex items-center gap-1"><KeyRound className="w-3.5 h-3.5" /> API key de {current.label}</label>
          <input type="password" className="input-field" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
            placeholder={settings?.api_key_set ? `Guardada ${settings.api_key_masked} — deja vacío para conservar` : current.keyPrefix} data-testid="ai-key-input" />
          <p className="text-xs text-ink-400 mt-1">Obtén tu key en <a href={current.keyUrl} target="_blank" rel="noreferrer" className="text-brand-500 underline">{current.keyUrl.replace('https://', '')}</a>. Se guarda en el servidor y nunca se muestra completa.</p>
        </div>

        {testResult && (
          <div className={`rounded-xl border px-4 py-3 text-sm ${testResult.ok ? 'border-emerald-200 bg-mint-100 text-emerald-800' : 'border-red-200 bg-red-50 text-red-700'}`} data-testid="ai-test-result">
            {testResult.ok ? <><CheckCircle2 className="w-4 h-4 inline mr-1" /> Conexión exitosa: “{testResult.text}”</> : <><AlertTriangle className="w-4 h-4 inline mr-1" /> {testResult.text}</>}
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-2 border-t border-ink-100">
          <button className="btn-secondary" onClick={test} disabled={testing || (!apiKey && !settings?.api_key_set)} data-testid="ai-test-btn">
            <Plug className="w-4 h-4" /> {testing ? 'Probando…' : 'Probar conexión'}
          </button>
          <button className="btn-primary" onClick={save} disabled={saving} data-testid="ai-save-btn">
            <Save className="w-4 h-4" /> {saving ? 'Guardando…' : 'Guardar configuración'}
          </button>
        </div>
      </div>
    </AppShell>
  );
}
