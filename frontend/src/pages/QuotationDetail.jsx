import { useEffect, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { useConfirm } from '@/components/ConfirmDialog';
import { ArrowLeft, Download, MessageCircle, Mail, FileText, Sparkles, Link2, Copy, CheckCircle2, X, Tag, CreditCard, Pencil, Archive, Trash2, History, Briefcase, Users, Smartphone, BookmarkPlus, Search, Package as PackageIcon } from 'lucide-react';
import { formatDateEs } from '@/lib/dates';
import { useAuth } from '@/context/AuthContext';

const STATES = [
  { id: 'nueva_consulta', label: 'Nueva' },
  { id: 'cotizando', label: 'Cotizando' },
  { id: 'enviada', label: 'Enviada' },
  { id: 'negociacion', label: 'En negociación' },
  { id: 'ganada', label: 'Aceptada' },
  { id: 'perdida', label: 'Perdida' },
];

function money(v, c = 'MXN') { return `$${Number(v || 0).toLocaleString('es-MX')} ${c}`; }

export default function QuotationDetail() {
  const confirm = useConfirm();
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
  const [aiLoading, setAiLoading] = useState({ prepay: false, postsale: false, message: false, payment: false });
  const [aiError, setAiError] = useState('');
  const [aiDraft, setAiDraft] = useState(null); // { kind, context, text }
  const [aiSendMsg, setAiSending] = useState('');
  const [publicToken, setPublicToken] = useState('');
  const [copiedPublic, setCopiedPublic] = useState(false);
  const [lostModal, setLostModal] = useState(false);
  const [lostReason, setLostReason] = useState('');
  const [discount, setDiscount] = useState({ discount_type: 'none', discount_value: 0 });
  const [clientPhone, setClientPhone] = useState('');
  const [companyName, setCompanyName] = useState('Routiq');
  const [payAmount, setPayAmount] = useState('');
  const [payMethod, setPayMethod] = useState('transfer');
  const [payDate, setPayDate] = useState(new Date().toISOString().slice(0, 10));
  const [payMsg, setPayMsg] = useState('');
  const [payCfg, setPayCfg] = useState({ payment_enabled: false, allowed_pay_type: 'full', card_fee_enabled: false, card_fee_percent: 4.5 });
  const [payCfgMsg, setPayCfgMsg] = useState('');
  const [notesDraft, setNotesDraft] = useState('');
  const [notesSaving, setNotesSaving] = useState(false);
  const [notesMsg, setNotesMsg] = useState('');
  const [sendingEmail, setSendingEmail] = useState(false);
  // WhatsApp link
  const [waLink, setWaLink] = useState(null);
  const [waModal, setWaModal] = useState(false);
  const [waNumbers, setWaNumbers] = useState([]);
  const [waSelNumber, setWaSelNumber] = useState('');
  const [waChats, setWaChats] = useState([]);
  const [waSearch, setWaSearch] = useState('');
  const [waShowAll, setWaShowAll] = useState(false);
  const [waSendMsg, setWaSendMsg] = useState('');
  const [waSending, setWaSending] = useState('');

  const load = async () => {
    const { data } = await api.get(`/quotations/${id}`);
    setQ(data);
    setNotesDraft(data.notes || '');
    setPublicToken(data?.public_link?.token || '');
    setPayCfg({
      payment_enabled: !!data.payment_enabled,
      allowed_pay_type: data.allowed_pay_type || 'full',
      card_fee_enabled: !!data.card_fee_enabled,
      card_fee_percent: data.card_fee_percent ?? 4.5,
    });
    if (data?.discount) setDiscount({ discount_type: data.discount.type, discount_value: data.discount.value });
    api.get(`/whatsapp/links/by-quotation/${id}`).then(({ data: l }) => setWaLink(l && l.chat_id ? l : null)).catch(() => {});
    api.get('/whatsapp/numbers').then(({ data }) => setWaNumbers(data || [])).catch(() => {});
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
    setWaModal(true); setWaSearch(''); setWaShowAll(false);
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
    if (!(await confirm({ title: 'Desvincular conversación', description: '¿Desvincular esta conversación de WhatsApp?', confirmText: 'Desvincular' }))) return;
    await api.delete(`/whatsapp/link/${id}`);
    setWaLink(null);
  };

  const archive = async () => {
    if (!(await confirm(q.archived
      ? { title: 'Restaurar cotización', description: '¿Restaurar esta cotización a la lista principal?', confirmText: 'Restaurar', danger: false }
      : { title: 'Archivar cotización', description: 'Se ocultará de la lista principal. Podrás restaurarla después.', confirmText: 'Archivar', danger: false }))) return;
    await api.patch(`/quotations/${id}/archive`, { archived: !q.archived });
    await load();
  };

  const remove = async () => {
    if (!(await confirm({ title: 'Eliminar cotización', description: 'Quedará registrada en la auditoría. Esta acción no se puede deshacer.', confirmText: 'Eliminar' }))) return;
    await api.delete(`/quotations/${id}`);
    navigate('/app/quotations');
  };

  const applyDiscount = async () => {
    await api.patch(`/quotations/${id}/pricing-adjust`, discount);
    await load();
  };

  const changeState = async (state, reason) => {
    await api.patch(`/quotations/${id}/state`, { state, reason: reason || undefined });
    await load();
  };

  const onStateClick = (state) => {
    if (state === 'perdida' && q.state !== 'perdida') {
      setLostReason(''); setLostModal(true);
    } else {
      changeState(state);
    }
  };

  const confirmLost = async () => {
    setLostModal(false);
    await changeState('perdida', lostReason.trim());
  };

  const downloadPdf = async () => {
    const response = await api.get(`/quotations/${id}/pdf`, { responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
    const a = document.createElement('a');
    a.href = url; a.download = `${q.code}.pdf`; a.click();
    window.URL.revokeObjectURL(url);
  };

  const runAIDraft = async (kind, endpoint) => {
    setAiError(''); setAiSending('');
    setAiLoading((s) => ({ ...s, [kind]: true }));
    try {
      const { data } = await api.post(`/ai/quotations/${id}/${endpoint}`);
      setAiDraft({ kind, context: data.context || '', text: data.message || '' });
    } catch (e) { setAiError(formatApiError(e)); }
    finally { setAiLoading((s) => ({ ...s, [kind]: false })); }
  };

  const sendDraftWhatsApp = async () => {
    if (!aiDraft?.text?.trim()) return;
    setAiSending('Enviando…');
    setAiSending(await deliverWhatsApp(aiDraft.text, aiDraft.kind));
  };

  const sendDraftEmail = async () => {
    if (!aiDraft?.text?.trim()) return;
    setAiSending('Enviando correo…');
    try {
      const { data } = await api.post(`/quotations/${id}/send-message`, { text: aiDraft.text });
      setAiSending(data.email_sent ? `✓ Correo enviado a ${data.to}` : 'No se pudo enviar el correo (configura Resend en Ajustes).');
    } catch (e) { setAiSending(formatApiError(e)); }
  };

  const createPublicLink = async () => {
    const { data } = await api.post(`/quotations/${id}/public-link`);
    setPublicToken(data.token);
    await load();
  };

  const revokePublicLink = async () => {
    if (!(await confirm({ title: 'Revocar enlace público', description: 'El cliente ya no podrá acceder a esta cotización con el enlace.', confirmText: 'Revocar' }))) return;
    await api.delete(`/quotations/${id}/public-link`);
    setPublicToken('');
    await load();
  };

  const copyPublicUrl = () => {
    // F6: la ruta /api/share entrega la vista previa (tarjeta) con nombre de empresa.
    const url = `${window.location.origin}/api/share/q/${publicToken}`;
    navigator.clipboard.writeText(url);
    setCopiedPublic(true);
    setTimeout(() => setCopiedPublic(false), 2000);
  };

  const buildWaMessage = (kind) => {
    const url = `${window.location.origin}/api/share/q/${publicToken}`;
    const name = q?.client_snapshot?.name || 'Hola';
    const code = q?.code || '';
    const pkg = q?.package_snapshot?.name || '';
    const amount = money(q?.final_total != null ? q.final_total : q?.total, q?.currency);
    if (kind === 'pay') {
      return `Hola ${name} 👋\nTu cotización *${code}* está lista. Total: *${amount}*.\nPuedes confirmar y *pagar de forma segura* (tarjeta o transferencia) aquí:\n${url}\n\n— ${companyName}`;
    }
    return `Hola ${name} 👋\nTe comparto tu cotización *${code}* de ${companyName}.\n${pkg ? `Paquete: ${pkg}\n` : ''}Total: *${amount}*\nMírala y confírmala aquí:\n${url}`;
  };

  const logSend = async (kind, channel) => {
    try { await api.post(`/quotations/${id}/log-send`, { kind, channel }); await load(); } catch (_e) { /* noop */ }
  };

  const deliverWhatsApp = async (msg, kind) => {
    const openFallback = () => {
      const phone = (clientPhone || '').replace(/[^0-9]/g, '');
      const base = phone ? `https://wa.me/${phone}` : 'https://wa.me/';
      window.open(`${base}?text=${encodeURIComponent(msg)}`, '_blank');
      return 'Abriendo WhatsApp… (envío manual)';
    };
    let status;
    // 1) Chat vinculado → envío directo por el WhatsApp conectado de la empresa.
    if (waLink?.chat_id && waLink?.number_id) {
      try {
        await api.post('/whatsapp/send', { number_id: waLink.number_id, to: waLink.chat_id, text: msg });
        status = `✓ Enviado por WhatsApp a ${waLink.phone}. Quedó registrado en el Inbox.`;
      } catch (e) { openFallback(); status = `No se pudo enviar directo (${formatApiError(e)}). Abriendo WhatsApp…`; }
      await logSend(kind, 'whatsapp');
      return status;
    }
    // 2) Sin chat vinculado, hay número conectado + teléfono del cliente → envío directo (crea el chat).
    const connected = waNumbers.find((n) => n.status === 'connected');
    const phone = (clientPhone || '').replace(/[^0-9]/g, '');
    if (connected && phone) {
      try {
        await api.post('/whatsapp/send', { number_id: connected.id, to: phone, text: msg });
        status = `✓ Enviado por "${connected.label}" al ${clientPhone}. Quedó registrado en el Inbox.`;
      } catch (e) { openFallback(); status = `No se pudo enviar directo (${formatApiError(e)}). Abriendo WhatsApp…`; }
      await logSend(kind, 'whatsapp');
      return status;
    }
    // 3) Sin número conectado → fallback a wa.me (nunca bloquear).
    status = openFallback();
    await logSend(kind, 'whatsapp');
    return status;
  };

  const sendWhatsApp = async (kind) => {
    if (!publicToken) return;
    setWaSendMsg(''); setWaSending(kind);
    const status = await deliverWhatsApp(buildWaMessage(kind), kind);
    setWaSendMsg(status); setWaSending('');
  };

  const markPaid = async () => {
    const amt = parseFloat(payAmount);
    if (!amt || amt <= 0) return;
    setPayMsg('');
    try {
      await api.patch(`/quotations/${id}/mark-paid`, { amount: amt, method: payMethod, date: payDate, note: 'Registrado manualmente' });
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

  const savePayCfg = async (patch) => {
    const next = { ...payCfg, ...patch };
    setPayCfg(next); setPayCfgMsg('');
    try {
      await api.patch(`/quotations/${id}/payment-config`, next);
      await load();
      setPayCfgMsg('✓ Configuración de pago guardada');
      setTimeout(() => setPayCfgMsg(''), 2500);
    } catch (e) { setPayCfgMsg(formatApiError(e)); }
  };

  const saveNotes = async () => {
    setNotesSaving(true); setNotesMsg('');
    try {
      await api.patch(`/quotations/${id}/notes`, { notes: notesDraft });
      setQ((prev) => (prev ? { ...prev, notes: notesDraft.trim() } : prev));
      setNotesMsg('✓ Notas guardadas');
      setTimeout(() => setNotesMsg(''), 2500);
    } catch (e) { setNotesMsg(formatApiError(e)); }
    finally { setNotesSaving(false); }
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
          <p className="text-ink-500 mt-0.5 text-sm" data-testid="quotation-agent-date">Ejecutivo: <span className="text-ink-900 font-medium">{q.agent_name || '—'}</span> · Elaborada el {formatDateEs(q.created_at)}</p>
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
          {q.state === 'ganada' && (
            <button onClick={() => navigate(`/app/quotations/${id}/confirmacion`)} className="btn-ghost text-sm border border-emerald-300 text-emerald-700 bg-mint-100" data-testid="booking-confirmation-btn">
              <FileText className="w-4 h-4" /> Generar confirmación de reserva
            </button>
          )}
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
          <button key={s.id} onClick={() => onStateClick(s.id)}
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
            {q.type === 'personalizado' && q.custom_items?.length > 0 && (
              <div className="mt-6 pt-4 border-t border-ink-100" data-testid="detail-custom-items">
                <p className="text-xs uppercase tracking-widest text-ink-400 font-bold mb-2">Conceptos del programa</p>
                <ul className="space-y-1.5">
                  {q.custom_items.map((it, i) => (
                    <li key={i} className="text-sm text-ink-700 flex items-start justify-between gap-3">
                      <span><span className="font-medium text-ink-900">{it.name || 'Concepto'}</span>{it.category ? <span className="text-ink-400 capitalize"> · {it.category}</span> : ''}{it.service_date ? <span className="text-ink-400"> · {formatDateEs(it.service_date)}</span> : ''}</span>
                      {it.qty > 0 && <span className="text-ink-400 shrink-0">×{it.qty}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {q.type === 'servicios' && q.items?.length > 0 && (
              <div className="mt-6 pt-4 border-t border-ink-100" data-testid="detail-service-items">
                <p className="text-xs uppercase tracking-widest text-ink-400 font-bold mb-2">Servicios contratados</p>
                <ul className="space-y-1.5">
                  {q.items.map((it, i) => (
                    <li key={i} className="text-sm text-ink-700 flex items-start justify-between gap-3">
                      <span className="font-medium text-ink-900">{it.label}</span>
                      <span className="text-ink-400 shrink-0">×{it.qty}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
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
            <div className="mt-6" data-testid="internal-notes-section">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-widest text-ink-400 font-bold">Notas internas</p>
                {notesMsg && <span className="text-xs text-emerald-700" data-testid="notes-msg">{notesMsg}</span>}
              </div>
              <textarea rows="3" className="input-field mt-1 text-sm" placeholder="Notas internas (solo visibles para tu equipo)…"
                value={notesDraft} onChange={(e) => setNotesDraft(e.target.value)} data-testid="internal-notes-input" />
              <button className="btn-secondary text-xs mt-2" onClick={saveNotes}
                disabled={notesSaving || notesDraft === (q.notes || '')} data-testid="save-notes-btn">
                {notesSaving ? 'Guardando…' : 'Guardar notas'}
              </button>
            </div>
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
          {/* AI Panel — seguimiento de venta (G1/G2/G3) */}
          <div className="card-surface p-6" data-testid="ai-panel">
            <h3 className="font-display font-semibold text-ink-900 mb-1 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-brand-500" /> Asistente de seguimiento
            </h3>
            <p className="text-xs text-ink-500 mb-3">La IA redacta; tú revisas, editas y envías. Nada se envía solo.</p>
            {aiError && <div className="text-xs text-red-700 bg-red-50 rounded-lg p-2 mb-3" data-testid="ai-error">{aiError}</div>}
            <div className="space-y-2">
              <button className="btn-secondary w-full text-xs justify-center" disabled={aiLoading.prepay}
                onClick={() => runAIDraft('prepay', 'follow-up-prepay')} data-testid="ai-followup-prepay-btn">
                {aiLoading.prepay ? 'Redactando…' : 'Seguimiento pre-pago'}
              </button>
              {q.state === 'ganada' && q.payment_status !== 'paid' && (
                <button className="btn-secondary w-full text-xs justify-center" disabled={aiLoading.payment}
                  onClick={() => runAIDraft('payment', 'follow-up-payment')} data-testid="ai-followup-payment-btn">
                  {aiLoading.payment ? 'Redactando…' : 'Recordatorio de pago'}
                </button>
              )}
              {(q.state === 'ganada' || q.payment_status === 'paid') && (
                <button className="btn-secondary w-full text-xs justify-center" disabled={aiLoading.postsale}
                  onClick={() => runAIDraft('postsale', 'follow-up-postsale')} data-testid="ai-followup-postsale-btn">
                  {aiLoading.postsale ? 'Redactando…' : 'Seguimiento post-venta'}
                </button>
              )}
              <button className="btn-secondary w-full text-xs justify-center" disabled={aiLoading.message}
                onClick={() => runAIDraft('message', 'client-message')} data-testid="ai-message-btn">
                {aiLoading.message ? 'Redactando…' : 'Redactar mensaje'}
              </button>

              {aiDraft && (
                <div className="rounded-lg bg-brand-50 p-3 space-y-2" data-testid="ai-draft">
                  {aiDraft.context && <p className="text-[11px] text-ink-500 italic" data-testid="ai-draft-context">{aiDraft.context}</p>}
                  <textarea rows="5" className="input-field text-sm" value={aiDraft.text}
                    onChange={(e) => setAiDraft((d) => ({ ...d, text: e.target.value }))} data-testid="ai-draft-text" />
                  <div className="flex gap-2">
                    <button onClick={sendDraftWhatsApp} className="flex-1 text-xs font-semibold justify-center inline-flex items-center gap-1.5 py-2 rounded-lg bg-[#25D366] text-white hover:brightness-95 transition" data-testid="ai-draft-send-whatsapp">
                      <MessageCircle className="w-3.5 h-3.5" /> WhatsApp
                    </button>
                    <button onClick={sendDraftEmail} className="flex-1 text-xs font-semibold justify-center inline-flex items-center gap-1.5 py-2 rounded-lg bg-brand-500 text-white hover:brightness-95 transition" data-testid="ai-draft-send-email">
                      <Mail className="w-3.5 h-3.5" /> Correo
                    </button>
                  </div>
                  {aiSendMsg && <p className="text-xs text-ink-700 bg-white rounded p-2 break-words" data-testid="ai-draft-send-msg">{aiSendMsg}</p>}
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
                <button className="w-full text-xs font-semibold justify-center inline-flex items-center gap-1.5 py-2.5 rounded-xl bg-[#25D366] text-white hover:brightness-95 transition disabled:opacity-60" onClick={() => sendWhatsApp('quote')} disabled={!!waSending} data-testid="send-quote-whatsapp-btn">
                  <MessageCircle className="w-3.5 h-3.5" /> {waSending === 'quote' ? 'Enviando…' : (waLink ? 'Enviar cotización por WhatsApp ✓' : 'Enviar cotización por WhatsApp')}
                </button>
                <button className="w-full text-xs font-semibold justify-center inline-flex items-center gap-1.5 py-2.5 rounded-xl border-2 border-[#25D366] text-[#128C7E] hover:bg-[#25D366]/10 transition disabled:opacity-60" onClick={() => sendWhatsApp('pay')} disabled={!!waSending} data-testid="send-pay-whatsapp-btn">
                  <MessageCircle className="w-3.5 h-3.5" /> {waSending === 'pay' ? 'Enviando…' : 'Enviar a cobrar por WhatsApp'}
                </button>
                {waSendMsg && <p className="text-xs text-emerald-700 bg-mint-100 rounded p-2 break-words" data-testid="wa-send-msg">{waSendMsg}</p>}
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
              {q.price_note && <p className="text-xs text-ink-400 italic" data-testid="detail-price-note">{q.price_note}</p>}
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
                <span className={`pill ${q.payment_status === 'paid' ? 'bg-amber-400 text-amber-950 ring-1 ring-amber-500 font-bold' : q.payment_status === 'partial' ? 'bg-peach-100 text-amber-700' : 'bg-ink-100 text-ink-500'}`} data-testid="payment-badge">
                  {q.payment_status === 'paid' ? 'Pagada' : q.payment_status === 'partial' ? 'Pago parcial' : 'Sin pagar'}
                </span>
                <span className="text-ink-700">Pagado: <b>{money(q.amount_paid || 0, q.currency)}</b></span>
              </div>

              {/* Gating de pago por etapas (Iter 4 punto 1 y 2) */}
              <div className="mt-3 rounded-xl border border-ink-100 bg-cream p-3" data-testid="payment-gating">
                {!(q.public_link?.accepted_at || q.state === 'ganada') ? (
                  <p className="text-xs text-ink-500">El cliente debe <b>aceptar</b> la cotización desde el enlace antes de habilitar el pago.</p>
                ) : (
                  <>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input type="checkbox" checked={payCfg.payment_enabled} onChange={(e) => savePayCfg({ payment_enabled: e.target.checked })} data-testid="payment-enabled-toggle" />
                      <span className="text-sm font-medium text-ink-800">Habilitar pago en el enlace del cliente</span>
                    </label>
                    {payCfg.payment_enabled && (
                      <div className="mt-3 space-y-3" data-testid="payment-options">
                        <div>
                          <p className="text-xs uppercase tracking-widest text-ink-400 font-bold mb-1.5">Tipo de pago permitido</p>
                          <div className="flex gap-2">
                            <button type="button" onClick={() => savePayCfg({ allowed_pay_type: 'full' })}
                              className={`pill flex-1 justify-center ${payCfg.allowed_pay_type === 'full' ? 'bg-brand-500 text-white' : 'bg-white border border-ink-100 text-ink-700'}`} data-testid="pay-type-full">Total</button>
                            <button type="button" onClick={() => savePayCfg({ allowed_pay_type: 'deposit' })}
                              className={`pill flex-1 justify-center ${payCfg.allowed_pay_type === 'deposit' ? 'bg-brand-500 text-white' : 'bg-white border border-ink-100 text-ink-700'}`} data-testid="pay-type-deposit">Anticipo</button>
                          </div>
                        </div>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input type="checkbox" checked={payCfg.card_fee_enabled} onChange={(e) => savePayCfg({ card_fee_enabled: e.target.checked })} data-testid="card-fee-toggle" />
                          <span className="text-sm text-ink-700">Agregar comisión bancaria (solo tarjeta)</span>
                        </label>
                        {payCfg.card_fee_enabled && (
                          <div className="flex items-center gap-2">
                            <label className="text-xs text-ink-500">Comisión %</label>
                            <input type="number" min="0" max="20" step="0.1" className="input-field text-sm w-24"
                              value={payCfg.card_fee_percent}
                              onChange={(e) => setPayCfg((c) => ({ ...c, card_fee_percent: +e.target.value }))}
                              onBlur={() => savePayCfg({})} data-testid="card-fee-percent-reservation" />
                            <span className="text-xs text-ink-400">No aplica en transferencia.</span>
                          </div>
                        )}
                      </div>
                    )}
                    {payCfgMsg && <p className="text-xs text-emerald-700 mt-2" data-testid="pay-cfg-msg">{payCfgMsg}</p>}
                  </>
                )}
              </div>

              {q.payment_status !== 'paid' && (
                <div className="mt-3" data-testid="mark-paid-control">
                  <p className="text-xs text-ink-500 mb-1.5">Registrar pago recibido:</p>
                  <div className="grid grid-cols-2 gap-2 mb-2">
                    <select className="input-field text-sm" value={payMethod} onChange={(e) => setPayMethod(e.target.value)} data-testid="mark-paid-method">
                      <option value="transfer">Transferencia</option>
                      <option value="cash">Efectivo</option>
                      <option value="card">Tarjeta</option>
                      <option value="other">Otro</option>
                    </select>
                    <input type="date" className="input-field text-sm" value={payDate} onChange={(e) => setPayDate(e.target.value)} data-testid="mark-paid-date" />
                  </div>
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
                <div className="relative mb-2">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-400" />
                  <input className="input-field pl-10" placeholder="Buscar por nombre o teléfono" value={waSearch} onChange={(e) => setWaSearch(e.target.value)} data-testid="wa-link-search" />
                </div>
                <label className="flex items-center gap-2 text-xs text-ink-500 mb-2 cursor-pointer">
                  <input type="checkbox" checked={waShowAll} onChange={(e) => setWaShowAll(e.target.checked)} data-testid="wa-link-show-all" />
                  Mostrar todos (incluye grupos y ocultos)
                </label>
                {(() => {
                  const norm = (p) => (p || '').replace(/[^0-9]/g, '').slice(-10);
                  const targets = [clientPhone, q?.contacts?.traveler?.phone, q?.contacts?.agency?.phone].map(norm).filter(Boolean);
                  const s = waSearch.toLowerCase();
                  const visible = waChats.filter((c) => {
                    if (!waShowAll) { if (c.hidden) return false; if (c.is_group) return false; }
                    return (c.contact_name || '').toLowerCase().includes(s) || (c.phone || '').includes(waSearch);
                  });
                  const suggested = visible.filter((c) => targets.includes(norm(c.phone)));
                  const others = visible.filter((c) => !targets.includes(norm(c.phone)));
                  const Row = (c) => (
                    <button key={c.chat_id} onClick={() => linkChat(c)} className="w-full text-left px-3 py-2.5 hover:bg-brand-50 transition-colors" data-testid={`wa-link-chat-${c.chat_id}`}>
                      <p className="font-semibold text-ink-900 text-sm flex items-center justify-between gap-2">
                        <span className="flex items-center gap-1.5 truncate">{c.is_group && <Users className="w-3.5 h-3.5 text-ink-400 shrink-0" />}{c.contact_name}</span>
                        {c.quotation_code && <span className="pill bg-peach-100 text-amber-700 text-[10px]">{c.quotation_code}</span>}
                      </p>
                      <p className="text-xs text-ink-400">{c.phone}</p>
                    </button>
                  );
                  return (
                    <div className="max-h-64 overflow-y-auto rounded-xl border border-ink-100 divide-y divide-ink-100">
                      {visible.length === 0 && <p className="p-4 text-sm text-ink-400" data-testid="wa-link-no-chats">No hay conversaciones que coincidan.</p>}
                      {suggested.length > 0 && (
                        <div className="bg-mint-100/50" data-testid="wa-link-suggested">
                          <p className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-widest font-bold text-emerald-700">Sugerido para esta cotización</p>
                          {suggested.map(Row)}
                        </div>
                      )}
                      {others.map(Row)}
                    </div>
                  );
                })()}
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

      {lostModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => setLostModal(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="lost-reason-modal">
            <h3 className="font-display text-xl font-semibold text-ink-900">Marcar como perdida</h3>
            <p className="text-sm text-ink-500 mt-1">Registra el motivo (opcional) para entender por qué se pierden ventas. Aparecerá en tu reporte de Ventas.</p>
            <div className="mt-4">
              <label className="label-text">Motivo</label>
              <textarea className="input-field" rows={3} value={lostReason} onChange={(e) => setLostReason(e.target.value)}
                placeholder="Ej: precio fuera de presupuesto, eligió otra agencia, cambió de fechas…" data-testid="lost-reason-input" />
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button className="btn-ghost" onClick={() => setLostModal(false)} data-testid="lost-reason-cancel">Cancelar</button>
              <button className="btn-primary !bg-red-600 hover:!bg-red-700" onClick={confirmLost} data-testid="lost-reason-confirm">Marcar perdida</button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
