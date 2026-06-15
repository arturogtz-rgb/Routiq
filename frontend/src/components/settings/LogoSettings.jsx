import { Image as ImageIcon, Upload, X } from 'lucide-react';

export const LogoSettings = ({ company, uploading, fileInputRef, uploadLogo, removeLogo, backend }) => (
  <div>
    <h2 className="font-display font-semibold text-lg text-ink-900 flex items-center gap-2"><ImageIcon className="w-5 h-5 text-brand-500" /> Logo de empresa</h2>
    <p className="text-sm text-ink-500 mt-1">Aparece en el sidebar, los PDF y el enlace público del cliente. Recomendado: PNG/SVG transparente, máx 2 MB.</p>
    <div className="mt-4 flex items-center gap-5">
      <div className="w-28 h-28 rounded-2xl border-2 border-dashed border-ink-200 bg-cream flex items-center justify-center overflow-hidden" data-testid="logo-preview">
        {company?.logo_url
          ? <img src={`${backend}${company.logo_url}`} alt="Logo" className="max-w-full max-h-full object-contain" />
          : <ImageIcon className="w-10 h-10 text-ink-300" />}
      </div>
      <div className="flex-1">
        <input ref={fileInputRef} type="file" accept="image/*" className="hidden"
          onChange={(e) => uploadLogo(e.target.files?.[0])} data-testid="logo-file-input" />
        <button className="btn-primary text-sm" disabled={uploading}
          onClick={() => fileInputRef.current?.click()} data-testid="upload-logo-btn">
          <Upload className="w-4 h-4" /> {uploading ? 'Subiendo…' : (company?.logo_url ? 'Cambiar logo' : 'Subir logo')}
        </button>
        {company?.logo_url && (
          <button className="btn-ghost text-sm ml-2 text-red-600" onClick={removeLogo} data-testid="remove-logo-btn">
            <X className="w-4 h-4" /> Quitar
          </button>
        )}
      </div>
    </div>
  </div>
);
