import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { useConfirm } from '@/components/ConfirmDialog';
import { useAuth } from '@/context/AuthContext';
import { Package as PackageIcon, MapPin, Calendar, Plus, Pencil, Trash2, Sun, FileSpreadsheet, Upload, X, CheckCircle2, AlertTriangle, Download, Share2, QrCode, Wand2, BookmarkPlus, Star, Globe } from 'lucide-react';
import { ShareCatalogModal } from '@/components/ShareCatalogModal';

export default function Packages() {
  const confirm = useConfirm();
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.role === 'company_admin';
  const [packages, setPackages] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [tab, setTab] = useState('paquetes');
  const [publishTpl, setPublishTpl] = useState(null);
  const [pubCode, setPubCode] = useState('');
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState('');
  const [importing, setImporting] = useState(false);
  const [report, setReport] = useState(null);
  const [slug, setSlug] = useState('');
  const [copiedCode, setCopiedCode] = useState('');
  const [shareCatalog, setShareCatalog] = useState(false);
  const fileRef = useRef(null);

  const load = async () => {
    try { const { data } = await api.get('/packages'); setPackages(data); }
    catch (_e) { /* noop */ }
  };
  const loadTemplates = async () => {
    try { const { data } = await api.get('/templates'); setTemplates(data); }
    catch (_e) { /* noop */ }
  };
  useEffect(() => { load(); loadTemplates(); }, []);
  useEffect(() => { api.get('/companies/me').then(({ data }) => setSlug(data.slug)).catch(() => {}); }, []);

  const sharePackage = async (p) => {
    if (!slug) return;
    const url = `${window.location.origin}/p/${slug}/${p.code}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopiedCode(p.code);
      setTimeout(() => setCopiedCode(''), 2000);
    } catch { window.prompt('Copia el enlace público del paquete:', url); }
  };

  const remove = async (p) => {
    if (!(await confirm({ title: 'Eliminar paquete', description: `¿Eliminar el paquete "${p.name}"? Esta acción no se puede deshacer.`, confirmText: 'Eliminar' }))) return;
    try { await api.delete(`/packages/${p.id}`); await load(); }
    catch (e) { setError(formatApiError(e)); }
  };

  const removeTemplate = async (t) => {
    if (!(await confirm({ title: 'Eliminar plantilla', description: `¿Eliminar la plantilla "${t.name}"? Esta acción no se puede deshacer.`, confirmText: 'Eliminar' }))) return;
    try { await api.delete(`/templates/${t.id}`); await loadTemplates(); }
    catch (e) { setError(formatApiError(e)); }
  };

  const toggleFeatured = async (t) => {
    try { await api.patch(`/templates/${t.id}`, { featured: !t.featured }); await loadTemplates(); }
    catch (e) { setError(formatApiError(e)); }
  };

  const suggestCode = (s) => (s || '').toUpperCase().normalize('NFD').replace(/[^A-Z0-9]/g, '').slice(0, 20);

  const openPublish = (t) => { setPublishTpl(t); setPubCode(suggestCode(t.custom_title || t.name)); };

  const publishAsPackage = async () => {
    setError(''); setPublishing(true);
    try {
      const { data } = await api.post(`/templates/${publishTpl.id}/publish-as-package`, { code: pubCode.trim() || null });
      navigate(`/app/packages/${data.id}/edit?from=template`);
    } catch (e) { setError(formatApiError(e)); setPublishing(false); }
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

  return (
    <AppShell>
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl md:text-4xl font-semibold text-ink-900 tracking-tight">Catálogo de paquetes</h1>
          <p className="text-ink-500 mt-1">Tus paquetes armados listos para cotizar.</p>
        </div>
        {isAdmin && (
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-ghost text-sm" onClick={() => setShareCatalog(true)} disabled={!slug} data-testid="share-catalog-btn">
              <QrCode className="w-4 h-4" /> Compartir catálogo
            </button>
            <button className="btn-ghost text-sm" onClick={downloadTemplate} data-testid="download-template-btn">
              <FileSpreadsheet className="w-4 h-4" /> Plantilla Excel
            </button>
            <button className="btn-ghost text-sm" onClick={exportCatalog} data-testid="export-catalog-btn">
              <Download className="w-4 h-4" /> Exportar Excel
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
        {!isAdmin && (
          <button className="btn-primary" onClick={() => setShareCatalog(true)} disabled={!slug} data-testid="share-catalog-btn">
            <QrCode className="w-4 h-4" /> Compartir catálogo
          </button>
        )}
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4">{error}</div>}

      <div className="flex items-center gap-2 mb-6 border-b border-ink-100">
        <button onClick={() => setTab('paquetes')} className={`px-4 py-2.5 text-sm font-semibold border-b-2 -mb-px transition-colors ${tab === 'paquetes' ? 'border-brand-500 text-brand-600' : 'border-transparent text-ink-400 hover:text-ink-700'}`} data-testid="tab-paquetes">
          <PackageIcon className="w-4 h-4 inline mr-1.5" /> Paquetes armados ({packages.length})
        </button>
        <button onClick={() => setTab('plantillas')} className={`px-4 py-2.5 text-sm font-semibold border-b-2 -mb-px transition-colors ${tab === 'plantillas' ? 'border-amber-500 text-amber-600' : 'border-transparent text-ink-400 hover:text-ink-700'}`} data-testid="tab-plantillas">
          <Wand2 className="w-4 h-4 inline mr-1.5" /> Plantillas de programa ({templates.length})
        </button>
      </div>

      {tab === 'paquetes' && (
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
                {(() => {
                  const min = Math.min(...((p.hotels || []).flatMap((h) => Object.values(h.prices_by_occupancy || {})).filter((n) => n > 0).concat([Infinity])));
                  return (
                    <p className="font-display text-xl font-bold text-brand-500">
                      {isFinite(min) ? `$${min.toLocaleString('es-MX')}` : '—'}
                      <span className="text-xs text-ink-400"> MXN/pax</span>
                    </p>
                  );
                })()}
              </div>
              <div className="flex items-center gap-1">
                {isAdmin && (
                  <>
                    <button className="p-2 rounded-lg text-ink-400 hover:bg-brand-50 hover:text-brand-500" onClick={() => navigate(`/app/packages/${p.id}/edit`)} data-testid={`edit-package-${p.code}`}><Pencil className="w-4 h-4" /></button>
                    <button className="p-2 rounded-lg text-ink-400 hover:bg-red-50 hover:text-red-600" onClick={() => remove(p)} data-testid={`delete-package-${p.code}`}><Trash2 className="w-4 h-4" /></button>
                  </>
                )}
                <button className={`p-2 rounded-lg ${copiedCode === p.code ? 'text-emerald-600 bg-mint-100' : 'text-ink-400 hover:bg-brand-50 hover:text-brand-500'}`} onClick={() => sharePackage(p)} title="Copiar enlace público" data-testid={`share-package-${p.code}`}>
                  {copiedCode === p.code ? <CheckCircle2 className="w-4 h-4" /> : <Share2 className="w-4 h-4" />}
                </button>
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
      )}

      {tab === 'plantillas' && (
        <div data-testid="templates-panel">
          <p className="text-sm text-ink-500 mb-5">Plantillas de programas personalizados guardadas por tu equipo. Úsalas para clonar una cotización a medida en segundos.</p>
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-5">
            {templates.map((t) => (
              <div key={t.id} className={`card-surface p-6 flex flex-col ${t.featured ? 'ring-2 ring-amber-300' : ''}`} data-testid={`template-card-${t.id}`}>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="pill bg-peach-100 text-amber-700 inline-flex items-center gap-1"><Wand2 className="w-3 h-3" /> Plantilla</span>
                    {t.featured && <span className="pill bg-amber-100 text-amber-700 inline-flex items-center gap-1" data-testid={`template-featured-badge-${t.id}`}><Star className="w-3 h-3 fill-amber-500 text-amber-500" /> Destacada</span>}
                  </div>
                  {isAdmin && (
                    <button onClick={() => toggleFeatured(t)} title={t.featured ? 'Quitar de destacadas' : 'Marcar como destacada'} className="p-1.5 rounded-lg hover:bg-amber-50" data-testid={`toggle-featured-${t.id}`}>
                      <Star className={`w-5 h-5 ${t.featured ? 'fill-amber-400 text-amber-400' : 'text-ink-300'}`} />
                    </button>
                  )}
                </div>
                <h3 className="font-display font-semibold text-lg text-ink-900 leading-tight">{t.name}</h3>
                {t.custom_title && t.custom_title !== t.name && <p className="text-sm text-ink-500 mt-1">{t.custom_title}</p>}
                <div className="mt-3 text-sm text-ink-600 space-y-1 flex-1">
                  {t.custom_nights > 0 && <div className="flex items-center gap-2"><Calendar className="w-4 h-4 text-amber-500" /> {t.custom_nights} noche(s)</div>}
                  {(t.custom_itinerary || []).length > 0 && <div className="flex items-center gap-2"><BookmarkPlus className="w-4 h-4 text-amber-500" /> {t.custom_itinerary.length} día(s) de itinerario</div>}
                  {t.created_by_name && <p className="text-xs text-ink-400 mt-1">Creada por {t.created_by_name}</p>}
                </div>
                <div className="mt-5 pt-4 border-t border-ink-100 flex items-center justify-between gap-2">
                  <button className="p-2 rounded-lg text-ink-400 hover:bg-red-50 hover:text-red-600" onClick={() => removeTemplate(t)} data-testid={`delete-template-${t.id}`}><Trash2 className="w-4 h-4" /></button>
                  <div className="flex items-center gap-2">
                    {isAdmin && (
                      <button className="btn-ghost text-sm border border-brand-200 text-brand-600" onClick={() => openPublish(t)} data-testid={`publish-template-${t.id}`}>
                        <Globe className="w-4 h-4" /> Paquete público
                      </button>
                    )}
                    <button className="btn-primary text-sm" onClick={() => navigate(`/app/quotations/new/custom?template=${t.id}`)} data-testid={`use-template-${t.id}`}>
                      <Plus className="w-4 h-4" /> Usar plantilla
                    </button>
                  </div>
                </div>
              </div>
            ))}
            {templates.length === 0 && (
              <div className="col-span-full text-center py-16 text-ink-400" data-testid="empty-templates">
                <Wand2 className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>Aún no tienes plantillas. Crea una cotización a medida y guárdala como plantilla.</p>
                <button className="btn-secondary text-sm mt-4" onClick={() => navigate('/app/quotations/new/custom')} data-testid="new-custom-from-templates">
                  <Wand2 className="w-4 h-4" /> Crear cotización a medida
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {publishTpl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => !publishing && setPublishTpl(null)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="publish-template-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900 flex items-center gap-2"><Globe className="w-5 h-5 text-brand-500" /> Convertir en paquete público</h3>
            <p className="text-sm text-ink-500 mt-2">Se creará un paquete en tu catálogo a partir de <b>{publishTpl.name}</b>. Quedará como <b>borrador (Inactivo)</b> y se abrirá el editor para que ajustes los precios por ocupación. Al cambiar el estado a <b>Activo</b> y guardar, aparecerá en tu catálogo público.</p>
            <label className="label-text mt-4">Código del paquete (para la URL pública)</label>
            <input className="input-field mt-1 uppercase" value={pubCode} placeholder="Ej. RIVIERAMAYA5N" onChange={(e) => setPubCode(e.target.value.toUpperCase())} data-testid="publish-code-input" />
            <div className="flex justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setPublishTpl(null)} data-testid="publish-cancel">Cancelar</button>
              <button className="btn-primary" disabled={publishing} onClick={publishAsPackage} data-testid="publish-confirm">
                <Globe className="w-4 h-4" /> {publishing ? 'Creando…' : 'Crear y abrir editor'}
              </button>
            </div>
          </div>
        </div>
      )}


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
                <p className="font-semibold" data-testid="import-total">{report.total_imported} registro(s) procesado(s)</p>
                <p className="text-sm" data-testid="import-breakdown">
                  {report.imported.paquetes_nuevos ?? 0} paquete(s) nuevo(s) · {report.imported.paquetes_actualizados ?? 0} actualizado(s) · {report.imported.hoteles ?? 0} hotel(es) · {report.imported.tours_nuevos ?? 0} tour(s) nuevo(s) · {report.imported.tours_actualizados ?? 0} actualizado(s) · {report.imported.traslados_nuevos ?? 0} traslado(s) nuevo(s) · {report.imported.traslados_actualizados ?? 0} actualizado(s)
                </p>
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

      <ShareCatalogModal open={shareCatalog} onClose={() => setShareCatalog(false)}
        url={slug ? `${window.location.origin}/c/${slug}` : ''} companyName={slug} />
    </AppShell>
  );
}
