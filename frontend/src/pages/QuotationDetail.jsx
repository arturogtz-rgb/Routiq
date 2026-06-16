import { useEffect, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { ArrowLeft, Download, MessageCircle, Mail, FileText, Sparkles, Link2, Copy, CheckCircle2, X, Tag, CreditCard, Pencil, Archive, Trash2, History, Briefcase, Users, Smartphone, BookmarkPlus, Package as PackageIcon } from 'lucide-react';
import { formatDateEs } from '@/lib/dates';
import { useAuth } from '@/context/AuthContext';

const STATES = [
  { id: 'nueva_consulta', label: 'Nueva' },
  { id: 'cotizando', label: 'Cotizando' },
  { id: 'enviada', label: 'Enviada' },
  { id: 'negociacion', label: 'En negociación' },
  { id: 'ganada', label: 'Ganada' },
  { id: 'perdida', label: 'Perdida' },
];

function money(v, c = 'MXN') { return `$${Number(v || 0).toLocaleString('es-MX')} ${c}`; }

export default function QuotationDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'company_admin';
  const [q, setQ] = useState(null);
  const [pack, setPack] = useState(null);
  const [saveTplOpen, setSaveTplOpen] = useState(false);
  const [tplName, setTplName] = useState('');
  const [savingTpl, setSavingTpl] = useState(false);
  const [savingPkg, setSavingPkg] = useState(false);
  const [pkgModalOpen, setPkgModalOpen] = useState(false);
  const [pkgCode, setPkgCode] = useState('');
  const [saveAsMsg, setSaveAsMsg] = useState('');
  const [ai, setAi] = useState({ next: '', missing: [], message: '' });
  const [aiLoading, setAiLoading] = useState({ next: false, missing: false, message: false });
  const [aiError, setAiError] = useState('');
  const [publicToken, setPublicToken] = useState('');
  const [copiedPublic, setCopiedPublic] = useState(false);
  const [discount, setDiscount] = useState({ discount_type: 'none', discount_value: 0 });
  const [clientPhone, setClientPhone] = useState('');
  const [companyName, setCompanyName] = useState('Routiq');
  const [payAmount, setPayAmount] = useState('');
  const [payMsg, setPayMsg] = useState('');
  const [sendingEmail, setSendingEmail] = useState(false);
  // WhatsApp link
  const [waLink, setWaLink] = useState(null);
  const [waModal, setWaModal] = useState(false);
  const [waNumbers, setWaNumbers] = useState([]);
  const [waSelNumber, setWaSelNumber] = useState('');
  const [waChats, setWaChats] = useState([]);

  const load = async () => {
    const { data } = await api.get(`/quotations/${id}`);
    setQ(data);
    setPublicToken(data?.public_link?.token || '');
    if (data?.discount) setDiscount({ discount_type: data.discount.type, discount_value: data.discount.value });
    api.get(`/whatsapp/links/by-quotation/${id}`).then(({ data: l }) => setWaLink(l && l.chat_id ? l : null)).catch(() => {});
    try {
      const reqs = [api.get('/clients'), api.get('/companies/me')];
      if (data.package_id) reqs.push(api.get(`/packages/${data.package_id}`));
      const [clients, company, p] = await Promise.all(reqs);
      setPack(p?.data || null);
      const cl = (clients.data || []).find((c) => c.id === data.client_id);
      setClientPhone(cl?.phone || '');
      setCompanyName(company.data?.name || 'Routiq');
    } catch (_e) { /* noop */ }
  };
  useEffect(() => { load(); }, [id]); // eslint-disable-line

  const openWaModal = async () => {
    setWaModal(true);
    try {
      const { data } = await api.get('/whatsapp/numbers');
      setWaNumbers(data);
      if (data.length) { setWaSelNumber(data[0].id); loadWaChats(data[0].id); }
    } catch (_e) { /* noop */ }
  };

  const loadWaChats = async (numId) => {
    try { const { data } = await api.get('/whatsapp/chats', { params: { number_id: numId } }); setWaChats(data); }
    catch { setWaChats([]); }
  };

  const linkChat = async (chat) => {
    try {
      await api.post('/whatsapp/link', { quotation_id: id, number_id: waSelNumber, chat_id: chat.chat_id });
      setWaLink({ chat_id: chat.chat_id, phone: chat.phone, number_id: waSelNumber, quotation_code: q.code });
      setWaModal(false);
    } catch (e) { setAiError(formatApiError(e)); }
  };

  const unlinkChat = async () => {
    if (!window.confirm('¿Desvincular esta conversación de WhatsApp?')) return;
    await api.delete(`/whatsapp/link/${id}`);
    setWaLink(null);
  };

  const archive = async () => {
    if (!window.confirm(q.archived ? '¿Restaurar esta cotización?' : '¿Archivar esta cotización? Se ocultará de la lista principal.')) return;
    await api.patch(`/quotations/${id}/archive`, { archived: !q.archived });
    await load();
  };

  const remove = async () => {
    if (!window.confirm('¿Eliminar esta cotización? Quedará registrada en la auditoría.')) return;
    await api.delete(`/quotations/${id}`);
    navigate('/app/quotations');
  };

  const applyDiscount = async () => {
    await api.patch(`/quotations/${id}/pricing-adjust`, discount);
    await load();
  };

  const changeState = async (state) => {
    await api.patch(`/quotations/${id}/state`, { state });
    await load();
  };

  const downloadPdf = async () => {
    const response = await api.get(`/quotations/${id}/pdf`, { responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
    const a = document.createElement('a');
    a.href = url; a.download = `${q.code}.pdf`; a.click();
    window.URL.revokeObjectURL(url);
  };

  const runAI = async (kind) => {
    setAiError('');
    setAiLoading((s) => ({ ...s, [kind]: true }));
    try {
      const { data } = await api.post(`/ai/quotations/${id}/${kind === 'next' ? 'next-step' : kind === 'missing' ? 'missing-fields' : 'client-message'}`);
      setAi((a) => ({ ...a, [kind]: kind === 'missing' ? (data.fields || []) : (data.suggestion || data.message || '') }));
    } catch (e) { setAiError(formatApiError(e)); }
    finally { setAiLoading((s) => ({ ...s, [kind]: false })); }
  };

  const createPublicLink = async () => {
    const { data } = await api.post(`/quotations/${id}/public-link`);
    setPublicToken(data.token);
    await load();
  };

  const revokePublicLink = async () => {
    if (!window.confirm('¿Revocar el enlace público? El cliente ya no podrá acceder.')) return;
    await api.delete(`/quotations/${id}/public-link`);
    setPublicToken('');
    await load();
  };

  const copyPublicUrl = () => {
    const url = `${window.location.origin}/q/${publicToken}`;
    navigator.clipboard.writeText(url);
    setCopiedPublic(true);
    setTimeout(() => setCopiedPublic(false), 2000);
  };

  const sendWhatsApp = (kind) => {
    if (!publicToken) return;
    const url = `${window.location.origin}/q/${publicToken}`;
    const name = q?.client_snapshot?.name || 'Hola';
    const code = q?.code || '';
    const pkg = q?.package_snapshot?.name || '';
    const amount = money(q?.final_total != null ? q.final_total : q?.total, q?.currency);
    let msg;
    if (kind === 'pay') {
      msg = `Hola ${name} 👋\nTu cotización *${code}* está lista. Total: *${amount}*.\nPuedes confirmar y *pagar de forma segura* (tarjeta o transferencia) aquí:\n${url}\n\n— ${companyName}`;
    } else {
      msg = `Hola ${name} 👋\nTe comparto tu cotización *${code}* de ${companyName}.\n${pkg ? `Paquete: ${pkg}\n` : ''}Total: *${amount}*\nMírala y confírmala aquí:\n${url}`;
    }
    const phone = (clientPhone || '').replace(/[^0-9]/g, '');
    const base = phone ? `https://wa.me/${phone}` : 'https://wa.me/';
    window.open(`${base}?text=${encodeURIComponent(msg)}`, '_blank');
  };

  const markPaid = async () => {
    const amt = parseFloat(payAmount);
    if (!amt || amt <= 0) return;
    setPayMsg('');
    try {
      await api.patch(`/quotations/${id}/mark-paid`, { amount: amt, method: 'transfer', note: 'Registrado manualmente' });
      setPayAmount('');
      await load();
    } catch (e) { setPayMsg(formatApiError(e)); }
  };

  const sendPaymentEmail = async () => {
    setSendingEmail(true); setPayMsg('');
    try {
      const { data } = await api.post(`/quotations/${id}/send-payment`, { channel: 'email', public_url: window.location.origin });
      setPayMsg(data.email_sent ? `✓ Correo de cobro enviado a ${data.to}` : `Configura Resend en Ajustes para enviar correos. Enlace listo: ${data.link}`);
      await load();
    } catch (e) { setPayMsg(formatApiError(e)); }
    finally { setSendingEmail(false); }
  };

  if (!q) return <AppShell><div className="p-8 text-ink-400">Cargando…</div></AppShell>;

  const saveAsTemplate = async () => {
    setSaveAsMsg(''); setSavingTpl(true);
    try {
      await api.post(`/quotations/${id}/save-as-template`, { name: tplName.trim() });
      setSaveTplOpen(false); setTplName('');
      setSaveAsMsg('✓ Plantilla guardada. Reutilízala desde Catálogo → Plantillas.');
      setTimeout(() => setSaveAsMsg(''), 5000);
    } catch (e) { setSaveAsMsg(formatApiError(e)); }
    finally { setSavingTpl(false); }
  };

  const saveAsPackage = async () => {
    setSaveAsMsg(''); setSavingPkg(true);
    try {
      const { data } = await api.post(`/quotations/${id}/save-as-package`, { code: pkgCode.trim() || null });
      navigate(`/app/packages/${data.id}/edit?from=custom`);
    } catch (e) { setSaveAsMsg(formatApiError(e)); setSavingPkg(false); setPkgModalOpen(false); }
  };

  const paxDesc = (() => {
    const p = q.pax || {};
    if (q.type === 'servicios') return `${p.adultos || 0} persona(s)`;
    if (p.rooms?.length) {
      const rooms = p.rooms.map((r) => `${r.count} ${r.ocupacion}`).join(' · ');
      const adults = p.rooms.reduce((s, r) => s + ({ sencilla: 1, doble: 2, triple: 3, cuadruple: 4 }[r.ocupacion] || 0) * r.count, 0);
      return `${rooms} (${adults} adultos${p.menores > 0 ? ` + ${p.menores} menores` : ''})`;
    }
    return `${p.adultos || 0} adultos · ${p.menores || 0} menores (${p.ocupacion || ''})`;
  })();

  return (
    <AppShell>
      <Link to="/app/quotations" className="btn-ghost text-sm mb-6" data-testid="qdetail-back">
        <ArrowLeft className="w-4 h-4" /> Cotizaciones
      </Link>

      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4 mb-6">
        <div>
          <p className="font-mono text-sm text-brand-500 font-semibold">{q.code}
            {q.type === 'servicios' && <span className="pill bg-peach-100 text-amber-700 ml-2">Servicios a la carta</span>}
            {q.type === 'personalizado' && <span className="pill bg-peach-100 text-amber-700 ml-2">Programa personalizado</span>}
            {q.archived && <span className="pill bg-ink-100 text-ink-500 ml-2">Archivada</span>}
          </p>
          <h1 className="font-display text-3xl font-semibold text-ink-900 mt-1">{q.package_snapshot?.name || 'Servicios a la carta'}</h1>
          <p className="text-ink-500 mt-1">Cliente: <span className="text-ink-900 font-medium">{q.client_snapshot?.name}</span></p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => navigate(q.type === 'personalizado' ? `/app/quotations/custom/${id}/edit` : `/app/quotations/${id}/edit`)} className="btn-secondary text-sm" data-testid="edit-quotation-btn">
            <Pencil className="w-4 h-4" /> Editar
          </button>
          {q.type === 'personalizado' && (
            <button onClick={() => { setTplName(q.custom_title || q.package_snapshot?.name || ''); setSaveTplOpen(true); }} className="btn-ghost text-sm border border-amber-200 text-amber-700" data-testid="save-as-template-btn">
              <BookmarkPlus className="w-4 h-4" /> Guardar como plantilla
            </button>
          )}
          {q.type === 'personalizado' && isAdmin && (
            <button onClick={() => { setPkgCode((q.custom_title || q.package_snapshot?.name || '').toUpperCase().normalize('NFD').replace(/[^A-Z0-9]/g, '').slice(0, 20)); setPkgModalOpen(true); }} disabled={savingPkg} className="btn-ghost text-sm border border-brand-200 text-brand-600" data-testid="save-as-package-btn">
              <PackageIcon className="w-4 h-4" /> {savingPkg ? 'Creando…' : 'Guardar como paquete'}
            </button>
          )}
          <button onClick={downloadPdf} className="btn-primary text-sm" data-testid="download-pdf-btn">
            <Download className="w-4 h-4" /> Descargar PDF
          </button>
          <button onClick={archive} className="btn-ghost text-sm" data-testid="archive-quotation-btn">
            <Archive className="w-4 h-4" /> {q.archived ? 'Restaurar' : 'Archivar'}
          </button>
          <button onClick={remove} className="btn-ghost text-sm text-red-600 hover:bg-red-50" data-testid="delete-quotation-btn">
            <Trash2 className="w-4 h-4" /> Eliminar
          </button>
        </div>
      </div>

      {saveAsMsg && <div className="rounded-xl border border-emerald-200 bg-mint-100 text-emerald-800 px-4 py-3 text-sm mb-6" data-testid="save-as-msg">{saveAsMsg}</div>}

      {/* State selector */}
      <div className="flex flex-wrap gap-2 mb-8" data-testid="state-selector">
        {STATES.map((s) => (
          <button key={s.id} onClick={() => changeState(s.id)}
            className={`pill transition-all ${q.state === s.id ? 'bg-brand-500 text-white' : 'bg-white border border-ink-100 text-ink-700 hover:bg-brand-50'}`}
            data-testid={`state-btn-${s.id}`}>
            {s.label}
          </button>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="card-surface p-6">
            <h3 className="font-display font-semibold text-ink-900 mb-4">Detalles</h3>
            <div className="grid md:grid-cols-2 gap-4 text-sm">
              {q.hotel_selected && <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Hotel</p><p className="text-ink-900 font-medium mt-1">{q.hotel_selected}</p></div>}
              {(q.dates?.start || q.dates?.end) && <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Fechas</p><p className="text-ink-900 font-medium mt-1">{formatDateEs(q.dates?.start)} → {formatDateEs(q.dates?.end)}</p></div>}
              <div><p className="text-xs uppercase tracking-widest text-ink-400 font-bold">{q.type === 'servicios' ? 'Personas' : 'Habitaciones / Pax'}</p><p className="text-ink-900 font-medium mt-1">{paxDesc}</p></div>
            </div>
            {(q.contacts?.agency?.name || q.contacts?.traveler?.name) && (
              <div className="grid md:grid-cols-2 gap-4 mt-6 pt-4 border-t border-ink-100" data-testid="detail-contacts">
                {q.contacts?.agency?.name && (
                  <div>
                    <p className="text-xs uppercase tracking-widest text-ink-400 font-bold flex items-center gap-1.5"><Briefcase className="w-3.5 h-3.5" /> Agencia / Vendedor</p>
                    <p className="text-ink-900 font-medium mt-1">{q.contacts.agency.name}</p>
                    <p className="text-ink-500 text-xs">{q.contacts.agency.contact} · {q.contacts.agency.email}</p>
                  </div>
                )}
                {q.contacts?.traveler?.name && (
                  <div>
                    <p className="text-xs uppercase tracking-widest text-ink-400 font-bold flex items-center gap-1.5"><Users className="w-3.5 h-3.5" /> Cliente final / Turista</p>
                    <p className="text-ink-900 font-medium mt-1">{q.contacts.traveler.name}</p>
                    <p className="text-ink-500 text-xs">Tel: {q.contacts.traveler.phone}</p>
                  </div>
                )}
              </div>
            )}
            {q.notes && <><p className="text-xs uppercase tracking-widest text-ink-400 font-bold mt-6">Notas</p><p className="text-ink-700 mt-1 text-sm">{q.notes}</p></>}
          </div>

          {(pack?.itinerary?.length > 0 || q.custom_itinerary?.length > 0) && (
            <div className="card-surface p-6">
              <h3 className="font-display font-semibold text-ink-900 mb-4">Itinerario</h3>
              {(pack?.itinerary || q.custom_itinerary).map((d) => (
                <div key={d.day} className="flex gap-4 mb-4 last:mb-0">
                  <div className="shrink-0 w-10 h-10 rounded-xl bg-brand-50 text-brand-500 font-display font-bold flex items-center justify-center">{d.day}</div>
                  <div>
                    <p className="font-semibold text-ink-900">{d.title}</p>
                    <p className="text-sm text-ink-500 mt-0.5">{d.description}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* History */}
          {q.history?.length > 0 && (
            <div className="card-surface p-6" data-testid="history-panel">
              <h3 className="font-display font-semibold text-ink-900 mb-4 flex items-center gap-2"><History className="w-4 h-4 text-brand-500" /> Historial de cambios</h3>
              <ol className="space-y-3">
                {[...q.history].reverse().map((h, i) => (
                  <li key={i} className="flex gap-3 text-sm" data-testid={`history-item-${i}`}>
                    <div className="shrink-0 w-2 h-2 rounded-full bg-brand-400 mt-1.5" />
                    <div>
                      <p className="text-ink-800">{h.detail || h.action}</p>
                      <p className="text-xs text-ink-400">{h.user_name || 'Sistema'} · {formatDateEs(h.at)}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>

        <div className="space-y-6">
          {/* AI Panel */}
          <div className="card-surface p-6" data-testid="ai-panel">
            <h3 className="font-display font-semibold text-ink-900 mb-3 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-brand-500" /> Asistente IA
            </h3>
            {aiError && <div className="text-xs text-red-700 bg-red-50 rounded-lg p-2 mb-3" data-testid="ai-error">{aiError}</div>}
            <div className="space-y-2">
              <button className="btn-secondary w-full text-xs justify-center" disabled={aiLoading.next}
                onClick={() => runAI('next')} data-testid="ai-next-step-btn">
                {aiLoading.next ? 'Analizando…' : 'Sugerir próximo paso'}
              </button>
              {ai.next && <p className="text-sm text-ink-700 bg-mint-100 rounded-lg p-3" data-testid="ai-next-result">{ai.next}</p>}

              <button className="btn-secondary w-full text-xs justify-center" disabled={aiLoading.missing}
                onClick={() => runAI('missing')} data-testid="ai-missing-btn">
                {aiLoading.missing ? 'Analizando…' : 'Detectar campos faltantes'}
              </button>
              {ai.missing.length > 0 && (
                <ul className="text-sm text-ink-700 bg-peach-100 rounded-lg p-3 space-y-1" data-testid="ai-missing-result">
                  {ai.missing.map((f, i) => <li key={i}>• {f}</li>)}
                </ul>
              )}

              <button className="btn-secondary w-full text-xs justify-center" disabled={aiLoading.message}
                onClick={() => runAI('message')} data-testid="ai-message-btn">
                {aiLoading.message ? 'Redactando…' : 'Redactar mensaje WhatsApp'}
              </button>
              {ai.message && (
                <div className="text-sm text-ink-700 bg-brand-50 rounded-lg p-3 whitespace-pre-wrap" data-testid="ai-message-result">
                  {ai.message}
                  <button className="mt-2 btn-ghost text-xs"
                    onClick={() => navigator.clipboard.writeText(ai.message)} data-testid="ai-message-copy">
                    <Copy className="w-3 h-3" /> Copiar
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Public Link Panel */}
          <div className="card-surface p-6" data-testid="public-link-panel">
            <h3 className="font-display font-semibold text-ink-900 mb-2 flex items-center gap-2">
              <Link2 className="w-4 h-4 text-brand-500" /> Enlace para cliente
            </h3>
            <p className="text-xs text-ink-500 mb-3">El cliente puede ver y aceptar la cotización con un click. Válido 7 días.</p>
            {!publicToken ? (
              <button className="btn-primary w-full text-sm justify-center" onClick={createPublicLink} data-testid="create-public-link">
                Generar enlace
              </button>
            ) : (
              <div className="space-y-2">
                <div className="rounded-lg bg-cream border border-ink-100 p-2 text-xs font-mono break-all text-ink-700">
                  {window.location.origin}/q/{publicToken}
                </div>
                <div className="flex gap-2">
                  <button className="btn-primary text-xs flex-1 justify-center" onClick={copyPublicUrl} data-testid="copy-public-link">
                    {copiedPublic ? <><CheckCircle2 className="w-3 h-3" /> Copiado</> : <><Copy className="w-3 h-3" /> Copiar</>}
                  </button>
                  <button className="btn-ghost text-xs text-red-600" onClick={revokePublicLink} data-testid="revoke-public-link">
                    <X className="w-3 h-3" /> Revocar
                  </button>
                </div>
                <button className="w-full text-xs font-semibold justify-center inline-flex items-center gap-1.5 py-2.5 rounded-xl bg-[#25D366] text-white hover:brightness-95 transition" onClick={() => sendWhatsApp('quote')} data-testid="send-quote-whatsapp-btn">
                  <MessageCircle className="w-3.5 h-3.5" /> Enviar cotización por WhatsApp
                </button>
                <button className="w-full text-xs font-semibold justify-center inline-flex items-center gap-1.5 py-2.5 rounded-xl border-2 border-[#25D366] text-[#128C7E] hover:bg-[#25D366]/10 transition" onClick={() => sendWhatsApp('pay')} data-testid="send-pay-whatsapp-btn">
                  <MessageCircle className="w-3.5 h-3.5" /> Enviar a cobrar por WhatsApp
                </button>
                <button className="w-full text-xs font-semibold justify-center inline-flex items-center gap-1.5 py-2.5 rounded-xl bg-brand-500 text-white hover:brightness-95 transition disabled:opacity-60" onClick={sendPaymentEmail} disabled={sendingEmail} data-testid="send-pay-email-btn">
                  <Mail className="w-3.5 h-3.5" /> {sendingEmail ? 'Enviando…' : 'Enviar a cobrar por correo'}
                </button>
                {payMsg && <p className="text-xs text-ink-600 bg-cream rounded p-2 break-words" data-testid="send-pay-msg">{payMsg}</p>}
                {q.public_link?.accepted_at && (
                  <p className="text-xs text-emerald-700 bg-mint-100 rounded p-2" data-testid="public-accepted">
                    ✓ Aceptada por el cliente el {formatDateEs(q.public_link.accepted_at)}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* WhatsApp link Panel */}
          <div className="card-surface p-6" data-testid="wa-link-panel">
            <h3 className="font-display font-semibold text-ink-900 mb-2 flex items-center gap-2">
              <Smartphone className="w-4 h-4 text-[#25D366]" /> Conversación WhatsApp
            </h3>
            {waLink ? (
              <div className="space-y-2" data-testid="wa-linked">
                <div className="rounded-lg bg-mint-100 border border-emerald-200 p-3 text-sm">
                  <p className="text-emerald-800 font-semibold flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" /> Vinculada</p>
                  <p className="text-ink-700 mt-1">Chat: <b>{waLink.phone}</b></p>
                </div>
                <div className="flex gap-2">
                  <button className="btn-secondary text-xs flex-1 justify-center" onClick={() => navigate(`/app/whatsapp?number=${waLink.number_id}&chat=${encodeURIComponent(waLink.chat_id)}`)} data-testid="wa-open-inbox">
                    <MessageCircle className="w-3.5 h-3.5" /> Abrir en el inbox
                  </button>
                  <button className="btn-ghost text-xs text-red-600" onClick={unlinkChat} data-testid="wa-unlink-btn">
                    <X className="w-3.5 h-3.5" /> Desvincular
                  </button>
                </div>
              </div>
            ) : (
              <>
                <p className="text-xs text-ink-500 mb-3">Vincula esta cotización a una conversación de WhatsApp para tener el chat y el folio juntos.</p>
                <button className="btn-primary w-full text-sm justify-center" onClick={openWaModal} data-testid="wa-link-btn">
                  <Link2 className="w-4 h-4" /> Vincular WhatsApp
                </button>
              </>
            )}
          </div>

          <div className="card-surface p-6">
            <h3 className="font-display font-semibold text-ink-900 mb-4 flex items-center gap-2"><FileText className="w-4 h-4 text-brand-500" /> Desglose</h3>
            {q.items?.map((it, i) => (
              <div key={i} className="flex justify-between text-sm py-2 border-b border-ink-100 last:border-0">
                <div><p className="text-ink-700">{it.label}</p><p className="text-ink-400 text-xs">{money(it.unit_price, q.currency)} × {it.qty}</p></div>
                <p className="font-semibold text-ink-900">{money(it.subtotal, q.currency)}</p>
              </div>
            ))}
            <div className="mt-4 pt-4 border-t border-ink-100 space-y-1 text-sm">
              <div className="flex justify-between"><span className="text-ink-500">Subtotal</span><span className="text-ink-900 font-medium">{money(q.subtotal, q.currency)}</span></div>
              {q.commission > 0 && <div className="flex justify-between"><span className="text-ink-500">Comisión</span><span className="text-red-600 font-medium">- {money(q.commission, q.currency)}</span></div>}
              <div className="flex justify-between pt-2 border-t border-ink-100 mt-2"><span className="text-ink-700">Total</span><span className="text-ink-900 font-semibold">{money(q.total, q.currency)}</span></div>
              {q.discount && q.discount.amount > 0 && (
                <div className="flex justify-between"><span className="text-ink-500">Descuento ({q.discount.type === 'percent' ? `${q.discount.value}%` : 'fijo'})</span><span className="text-red-600 font-medium">- {money(q.discount.amount, q.currency)}</span></div>
              )}
              <div className="flex justify-between pt-2 border-t border-ink-100 mt-2"><span className="font-display text-lg font-semibold text-ink-900">Total final</span><span className="font-display text-lg font-bold text-brand-500">{money(q.final_total != null ? q.final_total : q.total, q.currency)}</span></div>
            </div>

            {/* Discount control */}
            <div className="mt-4 pt-4 border-t border-ink-100" data-testid="discount-control">
              <p className="text-xs uppercase tracking-widest text-ink-400 font-bold mb-2 flex items-center gap-1.5"><Tag className="w-3.5 h-3.5" /> Descuento</p>
              <div className="flex gap-2">
                <select className="input-field text-sm" value={discount.discount_type}
                  onChange={(e) => setDiscount((d) => ({ ...d, discount_type: e.target.value }))} data-testid="discount-type-select">
                  <option value="none">Sin descuento</option>
                  <option value="percent">Porcentaje %</option>
                  <option value="fixed">Monto fijo</option>
                </select>
                <input type="number" min="0" className="input-field text-sm w-28" disabled={discount.discount_type === 'none'}
                  value={discount.discount_value} onChange={(e) => setDiscount((d) => ({ ...d, discount_value: +e.target.value || 0 }))} data-testid="discount-value-input" />
                <button className="btn-primary text-sm" onClick={applyDiscount} data-testid="apply-discount-btn">Aplicar</button>
              </div>
            </div>

            {/* Payment status */}
            <div className="mt-4 pt-4 border-t border-ink-100" data-testid="payment-status">
              <p className="text-xs uppercase tracking-widest text-ink-400 font-bold mb-2 flex items-center gap-1.5"><CreditCard className="w-3.5 h-3.5" /> Pago</p>
              <div className="flex items-center justify-between text-sm">
                <span className={`pill ${q.payment_status === 'paid' ? 'bg-mint-100 text-emerald-700' : q.payment_status === 'partial' ? 'bg-peach-100 text-amber-700' : 'bg-ink-100 text-ink-500'}`} data-testid="payment-badge">
                  {q.payment_status === 'paid' ? 'Pagado' : q.payment_status === 'partial' ? 'Pago parcial' : 'Sin pagar'}
                </span>
                <span className="text-ink-700">Pagado: <b>{money(q.amount_paid || 0, q.currency)}</b></span>
              </div>
              {q.payment_status !== 'paid' && (
                <div className="mt-3" data-testid="mark-paid-control">
                  <p className="text-xs text-ink-500 mb-1.5">Registrar pago recibido (transferencia/efectivo):</p>
                  <div className="flex gap-2">
                    <input type="number" min="0" step="0.01" className="input-field text-sm flex-1" placeholder="Monto" value={payAmount}
                      onChange={(e) => setPayAmount(e.target.value)} data-testid="mark-paid-amount" />
                    <button className="btn-primary text-sm whitespace-nowrap" onClick={markPaid} data-testid="mark-paid-btn">
                      <CheckCircle2 className="w-4 h-4" /> Marcar
                    </button>
                  </div>
                </div>
              )}
              <p className="text-xs text-ink-400 mt-2">El cliente paga con tarjeta o transferencia desde el enlace público. También puedes registrar pagos manualmente aquí.</p>
            </div>
          </div>
        </div>
      </div>

      {waModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => setWaModal(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="wa-link-modal">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-display text-lg font-semibold text-ink-900">Vincular conversación</h3>
              <button onClick={() => setWaModal(false)} className="text-ink-400 hover:text-ink-700"><X className="w-5 h-5" /></button>
            </div>
            {waNumbers.length === 0 ? (
              <p className="text-sm text-ink-500" data-testid="wa-link-no-numbers">No hay números de WhatsApp. Agrégalos en el inbox de WhatsApp.</p>
            ) : (
              <>
                <label className="label-text">Número</label>
                <select className="input-field mb-3" value={waSelNumber}
                  onChange={(e) => { setWaSelNumber(e.target.value); loadWaChats(e.target.value); }} data-testid="wa-link-number-select">
                  {waNumbers.map((n) => <option key={n.id} value={n.id}>{n.label} {n.status === 'connected' ? '· conectado' : ''}</option>)}
                </select>
                <label className="label-text">Conversación</label>
                <div className="max-h-64 overflow-y-auto rounded-xl border border-ink-100 divide-y divide-ink-100">
                  {waChats.length === 0 && <p className="p-4 text-sm text-ink-400" data-testid="wa-link-no-chats">No hay conversaciones en este número todavía.</p>}
                  {waChats.map((c) => (
                    <button key={c.chat_id} onClick={() => linkChat(c)} className="w-full text-left px-3 py-2.5 hover:bg-brand-50 transition-colors" data-testid={`wa-link-chat-${c.chat_id}`}>
                      <p className="font-semibold text-ink-900 text-sm flex items-center justify-between">
                        {c.contact_name}
                        {c.quotation_code && <span className="pill bg-peach-100 text-amber-700 text-[10px]">{c.quotation_code}</span>}
                      </p>
                      <p className="text-xs text-ink-400">{c.phone}</p>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}
      {saveTplOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => !savingTpl && setSaveTplOpen(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="save-template-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900 flex items-center gap-2"><BookmarkPlus className="w-5 h-5 text-amber-600" /> Guardar como plantilla</h3>
            <p className="text-sm text-ink-500 mt-2">Reutiliza este programa para futuras cotizaciones. Se guardan conceptos, itinerario e incluye/no incluye (sin el cliente).</p>
            <label className="label-text mt-4">Nombre de la plantilla</label>
            <input className="input-field mt-1" value={tplName} placeholder="Ej. Riviera Maya 5 días" onChange={(e) => setTplName(e.target.value)} data-testid="template-name-input" />
            <div className="flex justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setSaveTplOpen(false)} data-testid="template-cancel">Cancelar</button>
              <button className="btn-primary" disabled={tplName.trim().length < 2 || savingTpl} onClick={saveAsTemplate} data-testid="template-save">
                <BookmarkPlus className="w-4 h-4" /> {savingTpl ? 'Guardando…' : 'Guardar plantilla'}
              </button>
            </div>
          </div>
        </div>
      )}
      {pkgModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => !savingPkg && setPkgModalOpen(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="save-package-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900 flex items-center gap-2"><PackageIcon className="w-5 h-5 text-brand-500" /> Guardar como paquete</h3>
            <p className="text-sm text-ink-500 mt-2">Se creará un paquete en tu catálogo con el itinerario, incluye/no incluye y un hotel prellenado con el precio del hospedaje. Al guardar se abrirá el editor para que <b>ajustes los precios por ocupación</b>.</p>
            <label className="label-text mt-4">Código del paquete</label>
            <input className="input-field mt-1 uppercase" value={pkgCode} placeholder="Ej. RIVIERAMAYA5N" onChange={(e) => setPkgCode(e.target.value.toUpperCase())} data-testid="save-package-code-input" />
            <div className="flex justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setPkgModalOpen(false)} data-testid="save-package-cancel">Cancelar</button>
              <button className="btn-primary" disabled={savingPkg} onClick={saveAsPackage} data-testid="save-package-confirm">
                <PackageIcon className="w-4 h-4" /> {savingPkg ? 'Creando…' : 'Crear y abrir editor'}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
