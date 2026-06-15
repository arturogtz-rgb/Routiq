import { useRef, useState } from 'react';
import { QRCodeCanvas } from 'qrcode.react';
import { Copy, Check, Download, X, MessageCircle, QrCode } from 'lucide-react';

export const ShareCatalogModal = ({ open, onClose, url, companyName }) => {
  const qrWrapRef = useRef(null);
  const [copied, setCopied] = useState(false);
  if (!open) return null;

  const copy = async () => {
    try { await navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { window.prompt('Copia el enlace del catálogo:', url); }
  };

  const downloadQr = () => {
    const canvas = qrWrapRef.current?.querySelector('canvas');
    if (!canvas) return;
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = `catalogo-${companyName || 'routiq'}.png`.replace(/\s+/g, '-').toLowerCase();
    document.body.appendChild(a); a.click(); a.remove();
  };

  const waText = encodeURIComponent(`¡Mira nuestro catálogo de viajes! 🌎\n${url}`);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={onClose}>
      <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="share-catalog-modal">
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-display text-xl font-semibold text-ink-900 flex items-center gap-2"><QrCode className="w-5 h-5 text-brand-500" /> Compartir catálogo</h3>
          <button onClick={onClose} className="text-ink-400 hover:text-ink-700" data-testid="share-catalog-close"><X className="w-5 h-5" /></button>
        </div>
        <p className="text-sm text-ink-500 mb-4">Difunde el catálogo completo de tu empresa. Tus clientes verán todos los paquetes activos y podrán solicitar cotización 24/7.</p>

        <div ref={qrWrapRef} className="flex justify-center bg-cream rounded-2xl py-6">
          <QRCodeCanvas value={url} size={180} level="M" includeMargin marginSize={2} fgColor="#0f2f52" data-testid="share-catalog-qr" />
        </div>

        <div className="flex gap-2 mt-4">
          <input readOnly className="input-field flex-1 text-xs" value={url} data-testid="share-catalog-url" />
          <button className="btn-secondary" onClick={copy} data-testid="share-catalog-copy">{copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}</button>
        </div>

        <div className="grid grid-cols-2 gap-2 mt-3">
          <button className="btn-ghost justify-center" onClick={downloadQr} data-testid="share-catalog-download"><Download className="w-4 h-4" /> Descargar QR</button>
          <a className="btn-primary justify-center" href={`https://wa.me/?text=${waText}`} target="_blank" rel="noreferrer" data-testid="share-catalog-whatsapp"><MessageCircle className="w-4 h-4" /> WhatsApp</a>
        </div>
      </div>
    </div>
  );
};
