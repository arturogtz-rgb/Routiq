import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { Package as PackageIcon, MapPin, Calendar, Plus, Pencil, Trash2, Sun, FileSpreadsheet, Upload, X, CheckCircle2, AlertTriangle } from 'lucide-react';

export default function Packages() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.role === 'company_admin';
  const [packages, setPackages] = useState([]);
  const [error, setError] = useState('');
  const [importing, setImporting] = useState(false);
  const [report, setReport] = useState(null);
  const fileRef = useRef(null);

  const load = async () => {
    try { const { data } = await api.get('/packages'); setPackages(data); }
    catch (_e) { /* noop */ }
  };
  useEffect(() => { load(); }, []);

  const remove = async (p) => {
    if (!window.confirm(`¿Eliminar el paquete "${p.name}"?`)) return;
    try { await api.delete(`/packages/${p.id}`); await load(); }
    catch (e) { setError(formatApiError(e)); }
  };

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

  return (
    <AppShell>
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl md:text-4xl font-semibold text-ink-900 tracking-tight">Catálogo de paquetes</h1>
          <p className="text-ink-500 mt-1">Tus paquetes armados listos para cotizar.</p>
        </div>
        {isAdmin && (
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-ghost text-sm" onClick={downloadTemplate} data-testid="download-template-btn">
              <FileSpreadsheet className="w-4 h-4" /> Plantilla Excel
            </button>
            <button className="btn-ghost text-sm" onClick={() => fileRef.current?.click()} disabled={importing} data-testid="import-excel-btn">
              <Upload className="w-4 h-4" /> {importing ? 'Importando…' : 'Importar Excel'}
            </button>
            <input ref={fileRef} type="file" accept=".xlsx" className="hidden" onChange={handleImport} data-testid="import-excel-input" />
            <button className="btn-primary" onClick={() => navigate('/app/packages/new')} data-testid="new-package-btn">
              <Plus className="w-4 h-4" /> Nuevo paquete
            </button>
          </div>
        )}
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4">{error}</div>}

      <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-5">
        {packages.map((p) => (
          <div key={p.id} className="card-surface p-6 flex flex-col" data-testid={`package-card-${p.code}`}>
            <div className="flex items-start justify-between mb-3">
              <span className="pill bg-brand-50 text-brand-500 font-mono">{p.code}</span>
              <div className="flex items-center gap-2">
                {(p.seasons?.length > 0) && <span className="pill bg-peach-100 text-amber-700 inline-flex items-center gap-1"><Sun className="w-3 h-3" /> {p.seasons.length} temp.</span>}
                <span className="pill bg-mint-100 text-emerald-700">{p.nights} noches</span>
              </div>
            </div>
            <h3 className="font-display font-semibold text-lg text-ink-900 leading-tight">{p.name}</h3>
            <p className="text-sm text-ink-500 mt-2 line-clamp-3 flex-1">{p.description}</p>
            <div className="mt-4 space-y-1.5 text-sm text-ink-700">
              <div className="flex items-center gap-2"><MapPin className="w-4 h-4 text-brand-500" /> {p.hotels?.length || 0} hoteles disponibles</div>
            </div>
            <div className="mt-5 pt-4 border-t border-ink-100 flex items-center justify-between">
              <div>
                <p className="text-xs text-ink-400">Desde</p>
                <p className="font-display text-xl font-bold text-brand-500">
                  ${Math.min(...((p.hotels || []).flatMap((h) => Object.values(h.prices_by_occupancy || {})).filter((n) => n > 0).concat([Infinity]))).toLocaleString('es-MX')}
                  <span className="text-xs text-ink-400"> MXN/pax</span>
                </p>
              </div>
              <div className="flex items-center gap-1">
                {isAdmin && (
                  <>
                    <button className="p-2 rounded-lg text-ink-400 hover:bg-brand-50 hover:text-brand-500" onClick={() => navigate(`/app/packages/${p.id}/edit`)} data-testid={`edit-package-${p.code}`}><Pencil className="w-4 h-4" /></button>
                    <button className="p-2 rounded-lg text-ink-400 hover:bg-red-50 hover:text-red-600" onClick={() => remove(p)} data-testid={`delete-package-${p.code}`}><Trash2 className="w-4 h-4" /></button>
                  </>
                )}
                <Link to={`/app/quotations/new?package=${p.id}`} className="btn-secondary text-sm" data-testid={`quote-from-${p.code}`}>Cotizar</Link>
              </div>
            </div>
          </div>
        ))}
        {packages.length === 0 && (
          <div className="col-span-full text-center py-16 text-ink-400" data-testid="empty-packages">
            <PackageIcon className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>Aún no tienes paquetes cargados.</p>
          </div>
        )}
      </div>

      {report && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog">
          <div className="absolute inset-0 bg-ink-900/40" onClick={() => setReport(null)} />
          <div className="relative card-surface p-6 w-full max-w-lg animate-fade-up" data-testid="import-report-modal">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-xl font-semibold text-ink-900">Resultado de la importación</h2>
              <button onClick={() => setReport(null)} className="p-2 rounded-lg hover:bg-brand-50" data-testid="import-report-close"><X className="w-5 h-5" /></button>
            </div>
            <div className="rounded-xl bg-mint-100 text-emerald-800 p-4 flex items-center gap-3 mb-4">
              <CheckCircle2 className="w-6 h-6 shrink-0" />
              <div>
                <p className="font-semibold" data-testid="import-total">{report.total_imported} registro(s) importado(s)</p>
                <p className="text-sm">Paquetes: {report.imported.paquetes} · Tours: {report.imported.tours} · Traslados: {report.imported.traslados}</p>
              </div>
            </div>
            {report.error_count > 0 ? (
              <div data-testid="import-errors">
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
              <p className="text-sm text-emerald-700" data-testid="import-no-errors">✓ Sin errores. Todo se importó correctamente.</p>
            )}
            <div className="flex justify-end mt-6">
              <button className="btn-primary" onClick={() => setReport(null)} data-testid="import-report-done">Listo</button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
