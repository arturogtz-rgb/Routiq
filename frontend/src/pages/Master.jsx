import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { Building2, Plus, Power, PowerOff, Users as UsersIcon, FileText, TrendingUp, SlidersHorizontal, Bot, CreditCard, Landmark, BadgeCheck, ImageIcon, Crown, X, Inbox, Check, Clock, Copy } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

export default function MasterAdmin() {
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try { const { data } = await api.get('/metrics/master'); setMetrics(data); }
      catch (e) { setError(formatApiError(e)); }
    })();
  }, []);

  return (
    <AppShell>
      <div className="mb-8">
        <p className="pill bg-brand-500 text-white mb-3">Panel Master</p>
        <h1 className="font-display text-3xl md:text-4xl font-semibold text-ink-900 tracking-tight">Routiq SaaS</h1>
        <p className="text-ink-500 mt-1">Gestión de empresas y métricas globales.</p>
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4">{error}</div>}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[
          { icon: Building2, label: 'Empresas', v: metrics?.companies_total ?? '—', tone: 'bg-brand-50 text-brand-500' },
          { icon: Power, label: 'Activas', v: metrics?.companies_active ?? '—', tone: 'bg-mint-100 text-emerald-700' },
          { icon: UsersIcon, label: 'Usuarios', v: metrics?.users_total ?? '—', tone: 'bg-peach-100 text-amber-800' },
          { icon: FileText, label: 'Cotizaciones', v: metrics?.quotations_total ?? '—', tone: 'bg-brand-500 text-white' },
        ].map(({ icon: Icon, label, v, tone }) => (
          <div key={label} className="card-surface p-5" data-testid={`master-metric-${label}`}>
            <div className={`w-10 h-10 rounded-xl ${tone} flex items-center justify-center`}><Icon className="w-5 h-5" /></div>
            <p className="text-xs uppercase tracking-widest text-ink-400 font-bold mt-4">{label}</p>
            <p className="font-display text-3xl font-bold text-ink-900 mt-1">{v}</p>
          </div>
        ))}
      </div>

      <h2 className="font-display text-xl font-semibold text-ink-900 mb-4 flex items-center gap-2"><TrendingUp className="w-5 h-5 text-brand-500" /> Desempeño por empresa</h2>
      <div className="card-surface overflow-hidden">
        <div className="hidden md:grid grid-cols-12 px-6 py-3 border-b border-ink-100 text-xs uppercase tracking-widest font-bold text-ink-400">
          <div className="col-span-4">Empresa</div>
          <div className="col-span-3">Slug</div>
          <div className="col-span-2">Estado</div>
          <div className="col-span-3 text-right">Cotizaciones (total / ganadas)</div>
        </div>
        {(metrics?.per_company || []).map((c) => (
          <div key={c.id} className="grid grid-cols-12 px-6 py-4 border-b border-ink-100 last:border-0" data-testid={`master-company-row-${c.slug}`}>
            <div className="col-span-6 md:col-span-4 font-semibold text-ink-900">{c.name}</div>
            <div className="col-span-6 md:col-span-3 font-mono text-sm text-ink-500">{c.slug}</div>
            <div className="col-span-6 md:col-span-2"><span className={`pill ${c.status === 'active' ? 'bg-mint-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>{c.status}</span></div>
            <div className="col-span-6 md:col-span-3 md:text-right text-sm text-ink-700">
              <span className="font-semibold">{c.quotations_total}</span> · <span className="text-emerald-700 font-semibold">{c.quotations_won}</span> ganadas
            </div>
          </div>
        ))}
      </div>
    </AppShell>
  );
}

export function MasterCompanies() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [companies, setCompanies] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    name: '', slug: '', contact_email: '', contact_phone: '', address: '',
    admin_name: '', admin_email: '', admin_password: '',
  });
  const [error, setError] = useState('');
  const [planTarget, setPlanTarget] = useState(null);  // company being edited
  const [planForm, setPlanForm] = useState(null);
  const [planSaving, setPlanSaving] = useState(false);
  const [planError, setPlanError] = useState('');
  // Tenant signup requests
  const [requests, setRequests] = useState([]);
  const [approveTarget, setApproveTarget] = useState(null);
  const [approveSlug, setApproveSlug] = useState('');
  const [approveResult, setApproveResult] = useState(null);
  const [rejectTarget, setRejectTarget] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [reqBusy, setReqBusy] = useState(false);
  const [reqError, setReqError] = useState('');

  const load = async () => {
    const [comp, reqs] = await Promise.all([
      api.get('/companies'),
      api.get('/tenant-requests', { params: { status: 'pending' } }).catch(() => ({ data: [] })),
    ]);
    setCompanies(comp.data);
    setRequests(reqs.data || []);
  };
  useEffect(() => { load(); }, []);

  const openApprove = (r) => { setReqError(''); setApproveResult(null); setApproveTarget(r); setApproveSlug(r.slug || ''); };

  const confirmApprove = async () => {
    setReqBusy(true); setReqError('');
    try {
      const { data } = await api.post(`/tenant-requests/${approveTarget.id}/approve`, { slug: approveSlug || undefined });
      setApproveResult(data);
      load();
    } catch (e) { setReqError(formatApiError(e)); }
    finally { setReqBusy(false); }
  };

  const confirmReject = async () => {
    setReqBusy(true); setReqError('');
    try {
      await api.post(`/tenant-requests/${rejectTarget.id}/reject`, { reason: rejectReason });
      setRejectTarget(null); setRejectReason('');
      load();
    } catch (e) { setReqError(formatApiError(e)); }
    finally { setReqBusy(false); }
  };

  const toggle = async (c) => {
    const next = c.status === 'active' ? 'suspended' : 'active';
    await api.patch(`/companies/${c.id}/status`, null, { params: { status: next } });
    load();
  };

  const create = async () => {
    setError('');
    try {
      await api.post('/companies', form);
      setOpen(false);
      setForm({ name: '', slug: '', contact_email: '', contact_phone: '', address: '', admin_name: '', admin_email: '', admin_password: '' });
      load();
    } catch (e) { setError(formatApiError(e)); }
  };

  const openPlan = (c) => {
    setPlanError('');
    setPlanTarget(c);
    setPlanForm({
      plan: c.plan || 'pro',
      exec_limit: c.exec_limit ?? 0,
      ai_enabled: c.ai_enabled !== false,
      white_label: !!c.white_label,
      stripe_allowed: c.stripe_allowed !== false,
      transfer_allowed: c.transfer_allowed !== false,
    });
  };

  const applyPreset = (plan) => {
    const presets = PLAN_PRESETS[plan] || {};
    setPlanForm((f) => ({ ...f, plan, ...presets }));
  };

  const savePlan = async () => {
    setPlanSaving(true); setPlanError('');
    try {
      await api.patch(`/companies/${planTarget.id}/plan`, planForm);
      setPlanTarget(null); setPlanForm(null);
      load();
    } catch (e) { setPlanError(formatApiError(e)); }
    finally { setPlanSaving(false); }
  };

  return (
    <AppShell>
      <div className="flex items-end justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight">Empresas</h1>
          <p className="text-ink-500 mt-1">{companies.length} tenants en la plataforma</p>
        </div>
        <button className="btn-primary" onClick={() => setOpen(true)} data-testid="new-company-btn"><Plus className="w-4 h-4" /> Nueva empresa</button>
      </div>

      {requests.length > 0 && (
        <div className="card-surface overflow-hidden mb-6 border-2 border-peach-100" data-testid="signup-requests-card">
          <div className="px-6 py-4 bg-peach-100/60 flex items-center gap-2">
            <Inbox className="w-5 h-5 text-amber-800" />
            <h2 className="font-display font-semibold text-ink-900">Solicitudes de registro</h2>
            <span className="pill bg-amber-800 text-white text-xs" data-testid="signup-requests-count">{requests.length} pendiente{requests.length !== 1 ? 's' : ''}</span>
          </div>
          {requests.map((r) => (
            <div key={r.id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-ink-100 last:border-0" data-testid={`signup-request-${r.id}`}>
              <div className="flex items-center gap-4">
                <div className="w-11 h-11 rounded-xl bg-peach-100 text-amber-800 flex items-center justify-center"><Clock className="w-5 h-5" /></div>
                <div>
                  <p className="font-semibold text-ink-900 flex items-center gap-2">
                    {r.company_name}
                    <span className={`pill text-xs ${PLAN_TONE[r.plan] || 'bg-ink-100 text-ink-700'}`}><Crown className="w-3 h-3" /> {(r.plan || 'pro').toUpperCase()}</span>
                  </p>
                  <p className="text-xs text-ink-500">{r.admin_name} · {r.admin_email}{r.admin_phone ? ` · ${r.admin_phone}` : ''}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => openApprove(r)} className="btn-primary text-xs" data-testid={`approve-request-${r.id}`}><Check className="w-4 h-4" /> Aprobar</button>
                <button onClick={() => { setReqError(''); setRejectTarget(r); setRejectReason(''); }} className="btn-ghost text-xs text-red-600" data-testid={`reject-request-${r.id}`}><X className="w-4 h-4" /> Rechazar</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="card-surface overflow-hidden">
        {companies.map((c) => (
          <div key={c.id} className="flex items-center justify-between px-6 py-4 border-b border-ink-100 last:border-0" data-testid={`company-row-${c.slug}`}>
            <div className="flex items-center gap-4">
              <div className="w-11 h-11 rounded-xl bg-brand-50 text-brand-500 flex items-center justify-center"><Building2 className="w-5 h-5" /></div>
              <div>
                <p className="font-semibold text-ink-900 flex items-center gap-2">
                  {c.name}
                  <span className={`pill text-xs ${PLAN_TONE[c.plan] || 'bg-ink-100 text-ink-700'}`} data-testid={`company-plan-badge-${c.slug}`}>
                    <Crown className="w-3 h-3" /> {(c.plan || 'pro').toUpperCase()}
                  </span>
                </p>
                <p className="text-xs text-ink-500">{c.slug} · {c.contact_email}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className={`pill ${c.status === 'active' ? 'bg-mint-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>{c.status}</span>
              <button onClick={() => openPlan(c)} className="btn-ghost text-xs" data-testid={`manage-plan-${c.slug}`}>
                <SlidersHorizontal className="w-4 h-4" /> Plan
              </button>
              <button onClick={() => toggle(c)} className="btn-ghost text-xs" data-testid={`toggle-company-${c.slug}`}>
                {c.status === 'active' ? <><PowerOff className="w-4 h-4" /> Suspender</> : <><Power className="w-4 h-4" /> Reactivar</>}
              </button>
            </div>
          </div>
        ))}
      </div>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => setOpen(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-xl" onClick={(e) => e.stopPropagation()} data-testid="create-company-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900 mb-4">Nueva empresa (tenant)</h3>
            {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-3">{error}</div>}
            <div className="grid md:grid-cols-2 gap-3">
              <div><label className="label-text">Nombre comercial</label><input className="input-field" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} data-testid="company-name" /></div>
              <div><label className="label-text">Slug (subdominio)</label><input className="input-field" value={form.slug} onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '') }))} data-testid="company-slug" /></div>
              <div><label className="label-text">Email contacto</label><input type="email" className="input-field" value={form.contact_email} onChange={(e) => setForm((f) => ({ ...f, contact_email: e.target.value }))} data-testid="company-email" /></div>
              <div><label className="label-text">Teléfono</label><input className="input-field" value={form.contact_phone} onChange={(e) => setForm((f) => ({ ...f, contact_phone: e.target.value }))} data-testid="company-phone" /></div>
              <div className="md:col-span-2"><label className="label-text">Dirección</label><input className="input-field" value={form.address} onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))} data-testid="company-address" /></div>
              <div className="md:col-span-2"><hr className="my-2" /><p className="text-sm font-semibold text-ink-900">Admin inicial de la empresa</p></div>
              <div><label className="label-text">Nombre</label><input className="input-field" value={form.admin_name} onChange={(e) => setForm((f) => ({ ...f, admin_name: e.target.value }))} data-testid="admin-name" /></div>
              <div><label className="label-text">Email</label><input type="email" className="input-field" value={form.admin_email} onChange={(e) => setForm((f) => ({ ...f, admin_email: e.target.value }))} data-testid="admin-email" /></div>
              <div className="md:col-span-2"><label className="label-text">Contraseña (mín. 8)</label><input type="text" className="input-field" value={form.admin_password} onChange={(e) => setForm((f) => ({ ...f, admin_password: e.target.value }))} data-testid="admin-password" /></div>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setOpen(false)} data-testid="company-cancel">Cancelar</button>
              <button className="btn-primary" onClick={create} data-testid="company-submit">Crear empresa</button>
            </div>
          </div>
        </div>
      )}

      {planTarget && planForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => setPlanTarget(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-lg" onClick={(e) => e.stopPropagation()} data-testid="plan-modal">
            <div className="flex items-start justify-between mb-1">
              <h3 className="font-display text-xl font-semibold text-ink-900 flex items-center gap-2"><Crown className="w-5 h-5 text-brand-500" /> Plan de {planTarget.name}</h3>
              <button className="text-ink-400 hover:text-ink-700" onClick={() => setPlanTarget(null)} data-testid="plan-close"><X className="w-5 h-5" /></button>
            </div>
            <p className="text-sm text-ink-500 mb-4">Elige un plan (aplica valores recomendados) y ajusta límites a la medida.</p>
            {planError && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-3">{planError}</div>}

            <div className="grid grid-cols-3 gap-2 mb-5">
              {['starter', 'pro', 'enterprise'].map((p) => (
                <button key={p} onClick={() => applyPreset(p)} data-testid={`plan-option-${p}`}
                  className={`rounded-xl border-2 px-3 py-3 text-center transition-colors ${planForm.plan === p ? 'border-brand-500 bg-brand-50' : 'border-ink-100 hover:border-ink-200'}`}>
                  <p className="font-display font-semibold text-ink-900 capitalize text-sm">{p}</p>
                  <p className="text-[11px] text-ink-500 mt-0.5">{PLAN_LABELS[p]}</p>
                </button>
              ))}
            </div>

            <div className="space-y-4">
              <div>
                <label className="label-text">Límite de ejecutivos (0 = ilimitado)</label>
                <input type="number" min="0" className="input-field" value={planForm.exec_limit}
                  onChange={(e) => setPlanForm((f) => ({ ...f, exec_limit: Math.max(0, parseInt(e.target.value || '0', 10)) }))} data-testid="plan-exec-limit" />
              </div>
              <div className="grid sm:grid-cols-2 gap-3">
                {[
                  { k: 'ai_enabled', label: 'IA operativa (Claude)', icon: Bot },
                  { k: 'stripe_allowed', label: 'Cobros con Stripe', icon: CreditCard },
                  { k: 'transfer_allowed', label: 'Pago por transferencia', icon: Landmark },
                  { k: 'white_label', label: 'Marca blanca (sin Routiq)', icon: BadgeCheck },
                ].map(({ k, label, icon: Icon }) => (
                  <label key={k} className={`flex items-center gap-3 rounded-xl border px-3 py-3 cursor-pointer ${planForm[k] ? 'border-brand-200 bg-brand-50/50' : 'border-ink-100'}`} data-testid={`plan-toggle-${k}`}>
                    <input type="checkbox" checked={!!planForm[k]} onChange={(e) => setPlanForm((f) => ({ ...f, [k]: e.target.checked }))} />
                    <Icon className="w-4 h-4 text-brand-500" />
                    <span className="text-sm text-ink-700">{label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button className="btn-ghost" onClick={() => setPlanTarget(null)} data-testid="plan-cancel">Cancelar</button>
              <button className="btn-primary" onClick={savePlan} disabled={planSaving} data-testid="plan-save">{planSaving ? 'Guardando…' : 'Guardar plan'}</button>
            </div>
          </div>
        </div>
      )}

      {approveTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => !reqBusy && setApproveTarget(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="approve-modal">
            {!approveResult ? (
              <>
                <h3 className="font-display text-xl font-semibold text-ink-900 flex items-center gap-2"><Building2 className="w-5 h-5 text-brand-500" /> Aprobar empresa</h3>
                <p className="text-sm text-ink-500 mt-1">Se creará el tenant <span className="font-semibold">{approveTarget.company_name}</span> con plan <span className="font-semibold capitalize">{approveTarget.plan}</span> y se activará la cuenta de <span className="font-semibold">{approveTarget.admin_email}</span>.</p>
                {reqError && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mt-3">{reqError}</div>}
                <div className="mt-4">
                  <label className="label-text">Slug / subdominio</label>
                  <input className="input-field" value={approveSlug} onChange={(e) => setApproveSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))} data-testid="approve-slug-input" />
                  <p className="text-xs text-ink-400 mt-1">Editable. Si ya existe, se añadirá un sufijo automáticamente.</p>
                </div>
                <div className="flex justify-end gap-2 mt-6">
                  <button className="btn-ghost" onClick={() => setApproveTarget(null)} disabled={reqBusy} data-testid="approve-cancel">Cancelar</button>
                  <button className="btn-primary" onClick={confirmApprove} disabled={reqBusy} data-testid="approve-confirm">{reqBusy ? 'Creando…' : 'Aprobar y crear'}</button>
                </div>
              </>
            ) : (
              <div data-testid="approve-result">
                <div className="w-14 h-14 rounded-full bg-mint-100 text-emerald-700 flex items-center justify-center"><Check className="w-7 h-7" /></div>
                <h3 className="font-display text-xl font-semibold text-ink-900 mt-4">¡Empresa creada!</h3>
                <p className="text-sm text-ink-500 mt-1">Comparte estos accesos con el administrador. La contraseña es la que el solicitante eligió al registrarse.</p>
                <div className="rounded-xl bg-cream border border-ink-100 p-4 mt-4 text-sm space-y-1.5">
                  <div className="flex justify-between"><span className="text-ink-500">Empresa</span><span className="font-semibold text-ink-900">{approveResult.company.name}</span></div>
                  <div className="flex justify-between"><span className="text-ink-500">Slug</span><span className="font-mono text-ink-900">{approveResult.company.slug}</span></div>
                  <div className="flex justify-between"><span className="text-ink-500">Plan</span><span className="font-semibold capitalize text-ink-900">{approveResult.company.plan}</span></div>
                  <div className="flex justify-between items-center"><span className="text-ink-500">Acceso</span>
                    <span className="font-semibold text-ink-900 flex items-center gap-2">{approveResult.credentials.email}
                      <button onClick={() => navigator.clipboard?.writeText(approveResult.credentials.email)} className="text-brand-500 hover:text-brand-700" title="Copiar"><Copy className="w-3.5 h-3.5" /></button>
                    </span>
                  </div>
                  <div className="flex justify-between"><span className="text-ink-500">URL</span><span className="font-mono text-xs text-ink-900">{approveResult.credentials.login_url}</span></div>
                </div>
                <p className={`text-xs mt-3 ${approveResult.email_sent ? 'text-emerald-700' : 'text-amber-700'}`}>
                  {approveResult.email_sent ? '✓ Correo de bienvenida enviado al administrador.' : 'ⓘ No hay proveedor de correo de plataforma configurado: comparte los accesos manualmente.'}
                </p>
                <div className="flex justify-end mt-6">
                  <button className="btn-primary" onClick={() => { setApproveTarget(null); setApproveResult(null); }} data-testid="approve-done">Listo</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {rejectTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => !reqBusy && setRejectTarget(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="reject-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900">Rechazar solicitud</h3>
            <p className="text-sm text-ink-500 mt-1">Rechazar la solicitud de <span className="font-semibold">{rejectTarget.company_name}</span>. El motivo es interno (no se notifica al solicitante).</p>
            {reqError && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mt-3">{reqError}</div>}
            <div className="mt-4">
              <label className="label-text">Motivo (opcional)</label>
              <textarea className="input-field" rows={3} value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} data-testid="reject-reason-input" />
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button className="btn-ghost" onClick={() => setRejectTarget(null)} disabled={reqBusy} data-testid="reject-cancel">Cancelar</button>
              <button className="btn-primary !bg-red-600 hover:!bg-red-700" onClick={confirmReject} disabled={reqBusy} data-testid="reject-confirm">{reqBusy ? 'Rechazando…' : 'Rechazar'}</button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}

const PLAN_PRESETS = {
  starter: { exec_limit: 3, ai_enabled: false, white_label: false, stripe_allowed: false, transfer_allowed: true },
  pro: { exec_limit: 15, ai_enabled: true, white_label: false, stripe_allowed: true, transfer_allowed: true },
  enterprise: { exec_limit: 0, ai_enabled: true, white_label: true, stripe_allowed: true, transfer_allowed: true },
};

const PLAN_LABELS = {
  starter: '3 ejec · transferencia',
  pro: '15 ejec · IA + Stripe',
  enterprise: 'Ilimitado · marca blanca',
};

const PLAN_TONE = {
  starter: 'bg-ink-100 text-ink-700',
  pro: 'bg-brand-50 text-brand-500',
  enterprise: 'bg-peach-100 text-amber-800',
};
