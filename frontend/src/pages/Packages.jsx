import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api from '@/lib/api';
import { Package as PackageIcon, MapPin, Calendar, Plus } from 'lucide-react';

export default function Packages() {
  const [packages, setPackages] = useState([]);
  useEffect(() => { (async () => {
    try { const { data } = await api.get('/packages'); setPackages(data); }
    catch (_e) { /* noop */ }
  })(); }, []);

  return (
    <AppShell>
      <div className="flex items-end justify-between gap-4 mb-8">
        <div>
          <h1 className="font-display text-3xl md:text-4xl font-semibold text-ink-900 tracking-tight">Catálogo de paquetes</h1>
          <p className="text-ink-500 mt-1">Tus paquetes armados listos para cotizar.</p>
        </div>
        <button disabled className="btn-primary opacity-60 cursor-not-allowed" data-testid="new-package-btn" title="Disponible próximamente">
          <Plus className="w-4 h-4" /> Nuevo paquete
        </button>
      </div>

      <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-5">
        {packages.map((p) => (
          <div key={p.id} className="card-surface p-6 flex flex-col" data-testid={`package-card-${p.code}`}>
            <div className="flex items-start justify-between mb-3">
              <span className="pill bg-brand-50 text-brand-500 font-mono">{p.code}</span>
              <span className="pill bg-mint-100 text-emerald-700">{p.nights} noches</span>
            </div>
            <h3 className="font-display font-semibold text-lg text-ink-900 leading-tight">{p.name}</h3>
            <p className="text-sm text-ink-500 mt-2 line-clamp-3 flex-1">{p.description}</p>
            <div className="mt-4 space-y-1.5 text-sm text-ink-700">
              <div className="flex items-center gap-2"><MapPin className="w-4 h-4 text-brand-500" /> {p.hotels?.length || 0} hoteles disponibles</div>
              <div className="flex items-center gap-2"><Calendar className="w-4 h-4 text-brand-500" /> {p.season_start} → {p.season_end}</div>
            </div>
            <div className="mt-5 pt-4 border-t border-ink-100 flex items-center justify-between">
              <div>
                <p className="text-xs text-ink-400">Desde</p>
                <p className="font-display text-xl font-bold text-brand-500">
                  ${Math.min(...(p.hotels || []).flatMap((h) => Object.values(h.prices_by_occupancy || {}))).toLocaleString('es-MX')}
                  <span className="text-xs text-ink-400"> MXN/pax</span>
                </p>
              </div>
              <Link to={`/app/quotations/new?package=${p.id}`} className="btn-secondary text-sm" data-testid={`quote-from-${p.code}`}>
                Cotizar
              </Link>
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
    </AppShell>
  );
}
