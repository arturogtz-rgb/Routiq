import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { useConfirm } from '@/components/ConfirmDialog';
import { useAuth } from '@/context/AuthContext';
import { Plus, Pencil, Trash2, X, Sparkles, Bus, Ticket, Map, FileSpreadsheet, Upload, Download, CheckCircle2, AlertTriangle } from 'lucide-react';

const CATEGORIES = [
  { key: 'tour', label: 'Tour', icon: Map },
  { key: 'traslado', label: 'Traslado', icon: Bus },
  { key: 'acceso', label: 'Acceso', icon: Ticket },
  { key: 'extra', label: 'Extra', icon: Sparkles },
];

const UNIT_ES = { per_person: 'por persona', per_group: 'por grupo', per_day: 'por día', per_access: 'por acceso' };

function money(v) { return `$${Number(v || 0).toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }

export default function Services() {
  const confirm = useConfirm();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'company_admin';
  const [services, setServices] = useState([]);
  const [error, setError] = useState('');
  const [importing, setImporting] = useState(false);
  const [report, setReport] = useState(null);
  const fileRef = useRef(null);

  const backend = process.env.REACT_APP_BACKEND_URL || '';
  const imgSrc = (u) => (u ? (u.startsWith('http') ? u : `${backend}${u}`) : '');

  const downloadTemplate = async () => {
    try {
      const res = await api.get('/catalog/template', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url; a.download = 'routiq-catalogo-template.xlsx';
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) { setError(formatApiError(e)); }
  };

  const exportCatalog = async () => {
    try {
      const res = await api.get('/catalog/export', { responseType: 'blob' });
      const cd = res.headers['content-disposition'] || '';
      const m = cd.match(/filename="?([^"]+)"?/);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url; a.download = m ? m[1] : 'routiq-catalogo.xlsx';
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) { setError(formatApiError(e)); }
  };

  const handleImport = async (e) => {
    const file = e.target.files?.[0];
    if (file) e.target.value = '';
    if (!file) return;
    setError(''); setImporting(true); setReport(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await api.post('/catalog/import', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setReport(data);
      await load();
    } catch (err) { setError(formatApiError(err)); }
    finally { setImporting(false); }
  };

  const load = async () => {
    try {
      const { data } = await api.get('/services');
      setServices(data);
    } catch (e) { setError(formatApiError(e)); }
  };
  useEffect(() => { load(); }, []);

  const remove = async (svc) => {
    if (!(await confirm({ title: 'Eliminar servicio', description: `¿Eliminar el servicio "${svc.name}"? Esta acción no se puede deshacer.`, confirmText: 'Eliminar' }))) return;
    try { await api.delete(`/services/${svc.id}`); await load(); }
    catch (e) { setError(formatApiError(e)); }
  };

  return (
    <AppShell>
      <div className="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight">Servicios a la carta</h1>
          <p className="text-ink-500 mt-1">Tours, traslados, accesos y extras opcionales agregables a cualquier cotización.</p>
        </div>
        {isAdmin && (
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-ghost text-sm" onClick={downloadTemplate} data-testid="svc-download-template-btn">
              <FileSpreadsheet className="w-4 h-4" /> Plantilla Excel
            </button>
            <button className="btn-ghost text-sm" onClick={exportCatalog} data-testid="svc-export-btn">
              <Download className="w-4 h-4" /> Exportar Excel
            </button>
            <button className="btn-ghost text-sm" onClick={() => fileRef.current?.click()} disabled={importing} data-testid="svc-import-btn">
              <Upload className="w-4 h-4" /> {importing ? 'Importando…' : 'Importar Excel'}
            </button>
            <input ref={fileRef} type="file" accept=".xlsx" className="hidden" onChange={handleImport} data-testid="svc-import-input" />
            <button className="btn-primary text-sm" onClick={() => navigate('/app/services/new')} data-testid="new-service-btn">
              <Plus className="w-4 h-4" /> Nuevo servicio
            </button>
          </div>
        )}
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="services-error">{error}</div>}

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="services-grid">
        {services.map((svc) => {
          const cat = CATEGORIES.find((c) => c.key === svc.category) || CATEGORIES[3];
          const Icon = cat.icon;
          return (
            <div key={svc.id} className="card-surface p-5 flex flex-col" data-testid={`service-card-${svc.id}`}>
              {svc.image_url ? <img src={imgSrc(svc.image_url)} alt={svc.name} className="h-32 w-full object-cover rounded-lg mb-3 border border-ink-100" onError={(e) => { e.currentTarget.style.display = 'none'; }} /> : null}
              <div className="flex items-start justify-between">
                <span className="pill bg-brand-50 text-brand-500 inline-flex items-center gap-1.5"><Icon className="w-3.5 h-3.5" /> {cat.label}</span>
                {isAdmin && (
                  <div className="flex gap-1">
                    <button className="p-1.5 rounded-lg text-ink-400 hover:bg-brand-50 hover:text-brand-500" onClick={() => navigate(`/app/services/${svc.id}/edit`)} data-testid={`edit-service-${svc.id}`}><Pencil className="w-4 h-4" /></button>
                    <button className="p-1.5 rounded-lg text-ink-400 hover:bg-red-50 hover:text-red-600" onClick={() => remove(svc)} data-testid={`delete-service-${svc.id}`}><Trash2 className="w-4 h-4" /></button>
                  </div>
                )}
              </div>
              <h3 className="font-display font-semibold text-ink-900 mt-3">{svc.name}
                {svc.is_private && <span className="ml-2 pill bg-ink-100 text-ink-600 text-[10px] align-middle" data-testid={`service-private-badge-${svc.id}`}>Privado</span>}
              </h3>
              {svc.description && <p className="text-sm text-ink-500 mt-1 flex-1">{svc.description}</p>}
              <div className="mt-4 pt-3 border-t border-ink-100 flex items-end justify-between">
                <div>
                  <p className="text-xs text-ink-400">Neto: {money(svc.net_price)}</p>
                  <p className="font-display text-xl font-bold text-brand-500">{money(svc.public_price)}</p>
                </div>
                {svc.unit && <span className="text-xs text-ink-400">{UNIT_ES[svc.unit] || ''}</span>}
              </div>
            </div>
          );
        })}
        {services.length === 0 && (
          <div className="col-span-full text-center py-16 text-ink-400">
            <Map className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p>Aún no hay servicios. {isAdmin ? 'Crea el primero.' : ''}</p>
          </div>
        )}
      </div>

      {report && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog">
          <div className="absolute inset-0 bg-ink-900/40" onClick={() => setReport(null)} />
          <div className="relative card-surface p-6 w-full max-w-lg animate-fade-up" data-testid="svc-import-report-modal">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-xl font-semibold text-ink-900">Resultado de la importación</h2>
              <button onClick={() => setReport(null)} className="p-2 rounded-lg hover:bg-brand-50" data-testid="svc-import-report-close"><X className="w-5 h-5" /></button>
            </div>
            <div className="rounded-xl bg-mint-100 text-emerald-800 p-4 flex items-center gap-3 mb-4">
              <CheckCircle2 className="w-6 h-6 shrink-0" />
              <div>
                <p className="font-semibold" data-testid="svc-import-total">{report.total_imported} registro(s) procesado(s)</p>
                <p className="text-sm">
                  {report.imported.tours_nuevos ?? 0} tour(s) nuevo(s) / {report.imported.tours_actualizados ?? 0} act. · {report.imported.traslados_nuevos ?? 0} traslado(s) / {report.imported.traslados_actualizados ?? 0} act. · {report.imported.accesos_nuevos ?? 0} acceso(s) / {report.imported.accesos_actualizados ?? 0} act. · {report.imported.extras_nuevos ?? 0} extra(s) / {report.imported.extras_actualizados ?? 0} act.
                </p>
              </div>
            </div>
            {report.error_count > 0 ? (
              <div data-testid="svc-import-errors">
                <p className="text-sm font-semibold text-red-700 flex items-center gap-1.5 mb-2"><AlertTriangle className="w-4 h-4" /> {report.error_count} fila(s) con error</p>
                <div className="max-h-60 overflow-y-auto rounded-xl border border-ink-100 divide-y divide-ink-100">
                  {report.errors.map((er, i) => (
                    <div key={i} className="px-3 py-2 text-sm flex gap-3">
                      <span className="pill bg-red-100 text-red-700 text-xs shrink-0">{er.sheet} · fila {er.row}</span>
                      <span className="text-ink-700">{er.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-emerald-700">✓ Sin errores. Todo se importó correctamente.</p>
            )}
            <div className="flex justify-end mt-6">
              <button className="btn-primary" onClick={() => setReport(null)} data-testid="svc-import-report-done">Listo</button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
