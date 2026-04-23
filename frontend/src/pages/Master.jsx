import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { Building2, Plus, Power, PowerOff, Users as UsersIcon, FileText, TrendingUp } from 'lucide-react';
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

  const load = async () => { const { data } = await api.get('/companies'); setCompanies(data); };
  useEffect(() => { load(); }, []);

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

  return (
    <AppShell>
      <div className="flex items-end justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight">Empresas</h1>
          <p className="text-ink-500 mt-1">{companies.length} tenants en la plataforma</p>
        </div>
        <button className="btn-primary" onClick={() => setOpen(true)} data-testid="new-company-btn"><Plus className="w-4 h-4" /> Nueva empresa</button>
      </div>

      <div className="card-surface overflow-hidden">
        {companies.map((c) => (
          <div key={c.id} className="flex items-center justify-between px-6 py-4 border-b border-ink-100 last:border-0" data-testid={`company-row-${c.slug}`}>
            <div className="flex items-center gap-4">
              <div className="w-11 h-11 rounded-xl bg-brand-50 text-brand-500 flex items-center justify-center"><Building2 className="w-5 h-5" /></div>
              <div>
                <p className="font-semibold text-ink-900">{c.name}</p>
                <p className="text-xs text-ink-500">{c.slug} · {c.contact_email}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className={`pill ${c.status === 'active' ? 'bg-mint-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>{c.status}</span>
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
    </AppShell>
  );
}
