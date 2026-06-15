import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { Building2, Plus, Power, PowerOff, Users as UsersIcon, FileText, TrendingUp, SlidersHorizontal, Bot, CreditCard, Landmark, BadgeCheck, ImageIcon, Crown, X, Inbox, Check, Clock, Copy, Database, Download, KeyRound, AlertTriangle } from 'lucide-react';
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
  // Request history (approved / rejected)
  const [history, setHistory] = useState([]);
  const [historyFilter, setHistoryFilter] = useState('all');
  const [funnel, setFunnel] = useState(null);
  const [backups, setBackups] = useState(null);
  const [backupStatus, setBackupStatus] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [admins, setAdmins] = useState([]);
  const [editCompany, setEditCompany] = useState(null);
  const [editCompanyForm, setEditCompanyForm] = useState({ name: '', contact_email: '', contact_phone: '' });
  const [resetInfo, setResetInfo] = useState(null);
  const [copied, setCopied] = useState(false);

  const adminFor = (tenantId) => admins.find((a) => a.tenant_id === tenantId);

  const openEditCompany = (c) => { setEditCompany(c); setEditCompanyForm({ name: c.name || '', contact_email: c.contact_email || '', contact_phone: c.contact_phone || '' }); setError(''); };

  const saveCompanyContact = async () => {
    setError('');
    try {
      await api.patch(`/master/companies/${editCompany.id}/contact`, editCompanyForm);
      setEditCompany(null); load();
    } catch (e) { setError(formatApiError(e)); }
  };

  const resetAdmin = async (c) => {
    setError('');
    const a = adminFor(c.id);
    if (!a) { setError('No se encontró el administrador de esta empresa.'); return; }
    try {
      const { data } = await api.post(`/master/users/${a.id}/reset-link`);
      setResetInfo({ email: data.email, link: data.link, company: c.name }); setCopied(false);
    } catch (e) { setError(formatApiError(e)); }
  };

  const copyReset = async () => {
    try { await navigator.clipboard.writeText(resetInfo.link); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { window.prompt('Copia el enlace:', resetInfo.link); }
  };

  const loadHistory = async (filter = historyFilter) => {
    try {
      if (filter === 'all') {
        const { data } = await api.get('/tenant-requests');
        setHistory((data || []).filter((r) => r.status !== 'pending'));
      } else {
        const { data } = await api.get('/tenant-requests', { params: { status: filter } });
        setHistory(data || []);
      }
    } catch { setHistory([]); }
  };

  const load = async () => {
    const [comp, reqs] = await Promise.all([
      api.get('/companies'),
      api.get('/tenant-requests', { params: { status: 'pending' } }).catch(() => ({ data: [] })),
    ]);
    setCompanies(comp.data);
    setRequests(reqs.data || []);
    loadHistory();
    api.get('/tenant-requests/metrics').then(({ data }) => setFunnel(data)).catch(() => {});
    api.get('/backups').then(({ data }) => setBackups(data)).catch(() => {});
    api.get('/backups/status').then(({ data }) => setBackupStatus(data)).catch(() => {});
    api.get('/master/company-admins').then(({ data }) => setAdmins(data || [])).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  const downloadBackup = async () => {
    setDownloading(true);
    try {
      const res = await api.get('/backups/latest/download', { responseType: 'blob' });
      const cd = res.headers['content-disposition'] || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      const name = m ? m[1] : 'routiq-backup.gz';
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url; a.download = name; document.body.appendChild(a); a.click();
      a.remove(); window.URL.revokeObjectURL(url);
    } catch (e) {
      alert(formatApiError(e));
    } finally { setDownloading(false); }
  };

  const generateBackup = async () => {
    setError(''); setGenerating(true);
    try {
      await api.post('/backups/run');
      const [b, s] = await Promise.all([api.get('/backups'), api.get('/backups/status').catch(() => ({ data: null }))]);
      setBackups(b.data); if (s.data) setBackupStatus(s.data);
    } catch (e) { setError(formatApiError(e)); }
    finally { setGenerating(false); }
  };

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

      {funnel && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6" data-testid="funnel-kpi">
          {[
            { label: 'Solicitudes (mes)', v: funnel.received, tone: 'bg-brand-50 text-brand-500', tip: 'Recibidas este mes' },
            { label: 'Aprobadas (mes)', v: funnel.approved, tone: 'bg-mint-100 text-emerald-700', tip: 'Aprobadas este mes' },
            { label: 'Empresas activas (mes)', v: funnel.active, tone: 'bg-peach-100 text-amber-800', tip: 'Tenants activos creados este mes' },
            { label: 'Conversión', v: `${funnel.conversion_pct}%`, tone: 'bg-brand-500 text-white', tip: 'Aprobadas ÷ recibidas' },
          ].map(({ label, v, tone, tip }) => (
            <div key={label} className="card-surface p-5" data-testid={`funnel-${label}`} title={tip}>
              <p className="text-xs uppercase tracking-widest text-ink-400 font-bold">{label}</p>
              <p className={`font-display text-3xl font-bold mt-1 inline-flex px-2 rounded-lg ${tone}`}>{v}</p>
            </div>
          ))}
        </div>
      )}

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
              <button onClick={() => openEditCompany(c)} className="btn-ghost text-xs" data-testid={`edit-company-${c.slug}`}>
                <Building2 className="w-4 h-4" /> Editar
              </button>
              <button onClick={() => resetAdmin(c)} className="btn-ghost text-xs" data-testid={`reset-admin-${c.slug}`}>
                <KeyRound className="w-4 h-4" /> Reset admin
              </button>
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

      <div className="card-surface overflow-hidden mt-6" data-testid="requests-history-card">
        <div className="px-6 py-4 border-b border-ink-100 flex items-center justify-between gap-3">
          <h2 className="font-display font-semibold text-ink-900 flex items-center gap-2"><Clock className="w-5 h-5 text-brand-500" /> Historial de solicitudes</h2>
          <select className="input-field !w-auto !py-1.5 text-sm" value={historyFilter}
            onChange={(e) => { setHistoryFilter(e.target.value); loadHistory(e.target.value); }} data-testid="history-filter">
            <option value="all">Todas</option>
            <option value="approved">Aprobadas</option>
            <option value="rejected">Rechazadas</option>
          </select>
        </div>
        {history.length === 0 ? (
          <p className="px-6 py-6 text-sm text-ink-400" data-testid="history-empty">Aún no hay solicitudes procesadas.</p>
        ) : history.map((r) => (
          <div key={r.id} className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-b border-ink-100 last:border-0" data-testid={`history-row-${r.id}`}>
            <div>
              <p className="font-semibold text-ink-900 flex items-center gap-2">
                {r.company_name}
                <span className={`pill text-xs ${PLAN_TONE[r.plan] || 'bg-ink-100 text-ink-700'}`}><Crown className="w-3 h-3" /> {(r.plan || 'pro').toUpperCase()}</span>
              </p>
              <p className="text-xs text-ink-500">{r.admin_name} · {r.admin_email}</p>
              {r.status === 'rejected' && r.reason && <p className="text-xs text-red-600 mt-0.5">Motivo: {r.reason}</p>}
            </div>
            <div className="text-right">
              <span className={`pill text-xs ${r.status === 'approved' ? 'bg-mint-100 text-emerald-700' : 'bg-red-100 text-red-700'}`} data-testid={`history-status-${r.id}`}>
                {r.status === 'approved' ? 'Aprobada' : 'Rechazada'}
              </span>
              <p className="text-xs text-ink-400 mt-1">{r.decided_at ? new Date(r.decided_at).toLocaleString('es-MX', { dateStyle: 'medium', timeStyle: 'short' }) : ''}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="card-surface p-6 mt-6" data-testid="backups-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-brand-50 text-brand-500 flex items-center justify-center"><Database className="w-5 h-5" /></div>
            <div>
              <h2 className="font-display font-semibold text-ink-900">Respaldo de base de datos</h2>
              <p className="text-xs text-ink-500">
                {backups && backups.available > 0
                  ? `${backups.available} respaldo(s) · último: ${new Date(backups.backups[0].modified_at).toLocaleString('es-MX', { dateStyle: 'medium', timeStyle: 'short' })} (${backups.backups[0].size_mb} MB)`
                  : 'Aún no hay respaldos. Activa el cron diario en el VPS (06-backup-mongo.sh).'}
              </p>
            </div>
          </div>
          <button className="btn-primary" onClick={downloadBackup} disabled={downloading || !backups || backups.available === 0} data-testid="download-backup-btn">
            <Download className="w-4 h-4" /> {downloading ? 'Descargando…' : 'Descargar último respaldo'}
          </button>
          <button className="btn-secondary" onClick={generateBackup} disabled={generating} data-testid="generate-backup-btn">
            <Database className="w-4 h-4" /> {generating ? 'Generando…' : 'Generar respaldo ahora'}
          </button>
        </div>
        {backupStatus && backupStatus.stale && (
          <div className="mt-4 rounded-xl bg-red-50 border border-red-200 text-red-700 px-4 py-3 text-sm flex items-start gap-2" data-testid="backup-stale-warning">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{backupStatus.message}{backupStatus.hours_since != null ? ` (hace ${backupStatus.hours_since} h)` : ''} Se enviará un aviso por correo al Master cuando el correo de plataforma esté configurado.</span>
          </div>
        )}
      </div>

      {editCompany && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => setEditCompany(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="edit-company-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900 mb-4">Editar {editCompany.name}</h3>
            {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-3" data-testid="edit-company-error">{error}</div>}
            <div className="space-y-3">
              <div><label className="label-text">Nombre comercial</label><input className="input-field" value={editCompanyForm.name} onChange={(e) => setEditCompanyForm((f) => ({ ...f, name: e.target.value }))} data-testid="edit-company-name" /></div>
              <div><label className="label-text">Correo principal de contacto</label><input type="email" className="input-field" value={editCompanyForm.contact_email} onChange={(e) => setEditCompanyForm((f) => ({ ...f, contact_email: e.target.value }))} data-testid="edit-company-email" /></div>
              <div><label className="label-text">Teléfono</label><input className="input-field" value={editCompanyForm.contact_phone} onChange={(e) => setEditCompanyForm((f) => ({ ...f, contact_phone: e.target.value }))} data-testid="edit-company-phone" /></div>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setEditCompany(null)} data-testid="edit-company-cancel">Cancelar</button>
              <button className="btn-primary" onClick={saveCompanyContact} data-testid="edit-company-save">Guardar</button>
            </div>
          </div>
        </div>
      )}

      {resetInfo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => setResetInfo(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-lg" onClick={(e) => e.stopPropagation()} data-testid="master-reset-link-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900 mb-1">Restablecer contraseña — {resetInfo.company}</h3>
            <p className="text-sm text-ink-500 mb-4">Comparte este enlace con <b>{resetInfo.email}</b>. Válido 1 hora. También se intentó enviar por correo.</p>
            <div className="flex gap-2">
              <input readOnly className="input-field flex-1 text-xs" value={resetInfo.link} data-testid="master-reset-link-value" />
              <button className="btn-secondary" onClick={copyReset} data-testid="master-reset-link-copy">{copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}</button>
            </div>
            <div className="flex justify-end mt-5"><button className="btn-primary" onClick={() => setResetInfo(null)} data-testid="master-reset-link-close">Listo</button></div>
          </div>
        </div>
      )}

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
