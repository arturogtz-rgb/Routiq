import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import api, { formatApiError } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { MessageCircle, Sparkles, Smartphone, Send, Search, Plus, QrCode, Power, X, RefreshCw, Phone, FileText, Trash2 } from 'lucide-react';

export default function WhatsAppInbox() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const wantNumber = params.get('number');
  const wantChat = params.get('chat');
  const appliedChat = useRef(false);
  const isAdmin = user?.role === 'company_admin';
  const [numbers, setNumbers] = useState([]);
  const [activeNumber, setActiveNumber] = useState(null);
  const [chats, setChats] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const [search, setSearch] = useState('');
  // QR connect modal
  const [qrModal, setQrModal] = useState(false);
  const [qr, setQr] = useState(null);
  const [connStatus, setConnStatus] = useState('idle');
  // add number
  const [addOpen, setAddOpen] = useState(false);
  const [addForm, setAddForm] = useState({ label: '', number: '' });
  // ai
  const [aiSummary, setAiSummary] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const qrTimer = useRef(null);
  const msgTimer = useRef(null);

  const activeNum = useMemo(() => numbers.find((n) => n.id === activeNumber), [numbers, activeNumber]);

  const loadNumbers = async () => {
    try {
      const { data } = await api.get('/whatsapp/numbers');
      setNumbers(data);
      if (data.length && !activeNumber) {
        const pick = (wantNumber && data.find((n) => n.id === wantNumber)) ? wantNumber : data[0].id;
        setActiveNumber(pick);
      }
    } catch (e) { setError(formatApiError(e)); }
  };

  const loadChats = async (numId) => {
    if (!numId) return;
    try { const { data } = await api.get('/whatsapp/chats', { params: { number_id: numId } }); setChats(data); }
    catch { /* empty */ }
  };

  const loadMessages = async (numId, chatId) => {
    if (!numId || !chatId) return;
    try { const { data } = await api.get('/whatsapp/messages', { params: { number_id: numId, chat_id: chatId } }); setMessages(data); }
    catch { /* empty */ }
  };

  useEffect(() => { loadNumbers(); }, []);
  useEffect(() => { if (activeNumber) { loadChats(activeNumber); setActiveChat(null); setMessages([]); } }, [activeNumber]);
  useEffect(() => { setAiSummary(''); if (activeChat) loadMessages(activeNumber, activeChat); }, [activeChat]);

  // preselect chat from query (?number=&chat=) coming from a quotation
  useEffect(() => {
    if (!appliedChat.current && wantChat && chats.some((c) => c.chat_id === wantChat)) {
      appliedChat.current = true;
      setActiveChat(wantChat);
    }
  }, [chats, wantChat]);

  // poll chats + open conversation periodically (inbound messages)
  useEffect(() => {
    if (msgTimer.current) clearInterval(msgTimer.current);
    msgTimer.current = setInterval(() => {
      if (activeNumber) loadChats(activeNumber);
      if (activeNumber && activeChat) loadMessages(activeNumber, activeChat);
    }, 6000);
    return () => clearInterval(msgTimer.current);
  }, [activeNumber, activeChat]);

  // ---- connect flow ----
  const startConnect = async (numId) => {
    setError(''); setQr(null); setConnStatus('connecting'); setQrModal(true);
    try {
      await api.post(`/whatsapp/numbers/${numId}/connect`);
      pollQr(numId);
    } catch (e) { setConnStatus('error'); setError(formatApiError(e)); setQrModal(false); }
  };

  const pollQr = (numId) => {
    if (qrTimer.current) clearInterval(qrTimer.current);
    qrTimer.current = setInterval(async () => {
      try {
        const { data } = await api.get(`/whatsapp/numbers/${numId}/qr`);
        setConnStatus(data.status);
        setQr(data.qr || null);
        if (data.status === 'connected') {
          clearInterval(qrTimer.current);
          setQrModal(false);
          loadNumbers();
          loadChats(numId);
        }
      } catch { /* keep polling */ }
    }, 2500);
  };

  const closeQr = () => { if (qrTimer.current) clearInterval(qrTimer.current); setQrModal(false); };

  const logout = async (numId) => {
    if (!window.confirm('¿Desconectar este número de WhatsApp?')) return;
    try { await api.post(`/whatsapp/numbers/${numId}/logout`); loadNumbers(); }
    catch (e) { setError(formatApiError(e)); }
  };

  const removeNumber = async (numId) => {
    if (!window.confirm('¿Eliminar este número de WhatsApp? Se cerrará su sesión y se borrará de la lista. Esta acción no se puede deshacer.')) return;
    setError('');
    try {
      await api.delete(`/whatsapp/numbers/${numId}`);
      if (activeNumber === numId) { setActiveNumber(null); setChats([]); setActiveChat(null); setMessages([]); }
      await loadNumbers();
    } catch (e) { setError(formatApiError(e)); }
  };

  const addNumber = async () => {
    try {
      const { data } = await api.post('/whatsapp/numbers', addForm);
      setAddOpen(false); setAddForm({ label: '', number: '' });
      await loadNumbers();
      setActiveNumber(data.id);
    } catch (e) { setError(formatApiError(e)); }
  };

  const send = async () => {
    if (!text.trim() || !activeChat) return;
    setSending(true); setError('');
    try {
      await api.post('/whatsapp/send', { number_id: activeNumber, to: activeChat, text });
      setText('');
      loadMessages(activeNumber, activeChat);
      loadChats(activeNumber);
    } catch (e) { setError(formatApiError(e)); }
    finally { setSending(false); }
  };

  const generateSummary = async () => {
    setAiLoading(true); setError('');
    try {
      const mapped = messages.map((m) => ({ me: m.from_me, body: m.text }));
      const { data } = await api.post('/ai/chat-summary', { messages: mapped });
      setAiSummary(data.summary);
    } catch (e) { setAiSummary(`No se pudo generar el resumen: ${formatApiError(e)}`); }
    finally { setAiLoading(false); }
  };

  const filteredChats = chats.filter((c) =>
    (c.contact_name || '').toLowerCase().includes(search.toLowerCase()) || (c.phone || '').includes(search));
  const activeChatObj = chats.find((c) => c.chat_id === activeChat);
  const connected = activeNum?.status === 'connected';

  return (
    <AppShell>
      <div className="mb-6 flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight">WhatsApp Inbox</h1>
          <p className="text-ink-500 mt-1">Conecta tus números por QR y conversa en tiempo real.</p>
        </div>
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm mb-4" data-testid="wa-error">{error}</div>}

      {/* Numbers bar */}
      <div className="flex flex-wrap items-center gap-2 mb-4" data-testid="wa-numbers-bar">
        {numbers.map((n) => (
          <div key={n.id}
            className={`flex items-center gap-2 rounded-xl border px-3 py-2 cursor-pointer transition-colors ${activeNumber === n.id ? 'border-brand-500 bg-brand-50' : 'border-ink-100 bg-white hover:border-ink-200'}`}
            onClick={() => setActiveNumber(n.id)} data-testid={`wa-number-${n.id}`}>
            <Smartphone className="w-4 h-4 text-brand-500" />
            <div className="leading-tight">
              <p className="text-sm font-semibold text-ink-900">{n.label}</p>
              <p className="text-[11px] text-ink-400">{n.number || 'Sin número'}</p>
            </div>
            <span className={`pill text-[10px] ${n.status === 'connected' ? 'bg-mint-100 text-emerald-700' : 'bg-peach-100 text-amber-800'}`} data-testid={`wa-number-status-${n.id}`}>
              {n.status === 'connected' ? 'Conectado' : 'Desconectado'}
            </span>
            {isAdmin && (n.status === 'connected'
              ? <button onClick={(e) => { e.stopPropagation(); logout(n.id); }} className="text-ink-400 hover:text-red-600" title="Desconectar" data-testid={`wa-logout-${n.id}`}><Power className="w-4 h-4" /></button>
              : <button onClick={(e) => { e.stopPropagation(); startConnect(n.id); }} className="text-ink-400 hover:text-brand-500" title="Conectar (QR)" data-testid={`wa-connect-${n.id}`}><QrCode className="w-4 h-4" /></button>
            )}
            {isAdmin && (
              <button onClick={(e) => { e.stopPropagation(); removeNumber(n.id); }} className="text-ink-400 hover:text-red-600" title="Eliminar número" data-testid={`wa-delete-${n.id}`}><Trash2 className="w-4 h-4" /></button>
            )}
          </div>
        ))}
        {isAdmin && (
          <button className="btn-ghost text-sm" onClick={() => setAddOpen(true)} data-testid="wa-add-number-btn"><Plus className="w-4 h-4" /> Agregar número</button>
        )}
      </div>

      <div className="card-surface overflow-hidden grid md:grid-cols-[320px_1fr] min-h-[560px]" data-testid="wa-inbox">
        {/* Chat list */}
        <aside className="border-r border-ink-100 flex flex-col">
          <div className="p-3 border-b border-ink-100">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-400" />
              <input className="input-field pl-10" placeholder="Buscar chat" value={search} onChange={(e) => setSearch(e.target.value)} data-testid="wa-search" />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {filteredChats.length === 0 && (
              <p className="p-6 text-sm text-ink-400" data-testid="wa-chats-empty">
                {connected ? 'Aún no hay conversaciones. Cuando te escriban aparecerán aquí.' : 'Conecta este número para empezar a recibir mensajes.'}
              </p>
            )}
            {filteredChats.map((c) => (
              <button key={c.chat_id} onClick={() => setActiveChat(c.chat_id)}
                className={`w-full text-left px-4 py-3 border-b border-ink-100 transition-colors ${activeChat === c.chat_id ? 'bg-brand-50' : 'hover:bg-cream'}`}
                data-testid={`wa-chat-${c.chat_id}`}>
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-ink-900 truncate">{c.contact_name}</p>
                  {c.unread > 0 && <span className="pill bg-brand-500 text-white text-[10px]">{c.unread}</span>}
                </div>
                <p className="text-xs text-ink-400 mt-0.5 flex items-center gap-1"><Phone className="w-3 h-3" />{c.phone}</p>
                {c.quotation_code && <span className="inline-flex items-center gap-1 pill bg-peach-100 text-amber-700 text-[10px] mt-1" data-testid={`wa-chat-quote-${c.chat_id}`}><FileText className="w-3 h-3" />{c.quotation_code}</span>}
                <p className="text-sm text-ink-500 mt-1 truncate">{c.last_text}</p>
              </button>
            ))}
          </div>
        </aside>

        {/* Conversation */}
        <section className="flex flex-col">
          {!activeChat ? (
            <div className="flex-1 flex items-center justify-center text-ink-400 text-sm" data-testid="wa-no-chat">
              <div className="text-center">
                <MessageCircle className="w-10 h-10 mx-auto mb-2 text-ink-200" />
                Selecciona una conversación
              </div>
            </div>
          ) : (
            <>
              <header className="p-4 border-b border-ink-100">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="font-semibold text-ink-900">{activeChatObj?.contact_name}</p>
                    <p className="text-xs text-ink-400">{activeChatObj?.phone} · vía {activeNum?.label}</p>
                  </div>
                  {activeChatObj?.quotation_code && (
                    <button onClick={() => navigate(`/app/quotations/${activeChatObj.quotation_id}`)}
                      className="pill bg-peach-100 text-amber-700 text-xs hover:brightness-95" data-testid="wa-header-quote">
                      <FileText className="w-3.5 h-3.5" /> {activeChatObj.quotation_code}
                    </button>
                  )}
                </div>
                <div className="mt-3 rounded-xl bg-mint-100 p-3 flex gap-3" data-testid="ai-summary">
                  <Sparkles className="w-4 h-4 shrink-0 text-emerald-700 mt-0.5" />
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <p className="text-xs uppercase tracking-widest font-bold text-emerald-800">Resumen IA</p>
                      <button onClick={generateSummary} disabled={aiLoading || messages.length === 0} className="text-xs text-emerald-800 hover:underline disabled:opacity-50" data-testid="generate-ai-summary">
                        {aiLoading ? 'Generando…' : (aiSummary ? 'Regenerar' : 'Generar')}
                      </button>
                    </div>
                    <p className="text-sm text-ink-900 mt-1">{aiSummary || 'Genera un resumen IA de esta conversación.'}</p>
                  </div>
                </div>
              </header>
              <div className="flex-1 overflow-y-auto p-6 space-y-3 bg-cream" data-testid="wa-messages">
                {messages.map((m) => (
                  <div key={m.id} className={`flex ${m.from_me ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm ${m.from_me ? 'bg-brand-500 text-white rounded-br-sm' : 'bg-white text-ink-900 border border-ink-100 rounded-bl-sm'}`}>
                      <p className="whitespace-pre-wrap break-words">{m.text}</p>
                      <p className={`text-[10px] mt-1 ${m.from_me ? 'text-brand-50/80' : 'text-ink-400'}`}>
                        {m.timestamp ? new Date(m.timestamp).toLocaleString('es-MX', { hour: '2-digit', minute: '2-digit' }) : ''}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
              <div className="p-4 border-t border-ink-100 bg-white">
                <div className="flex gap-2">
                  <input className="input-field flex-1" placeholder={connected ? 'Escribe un mensaje…' : 'Conecta el número para enviar'}
                    value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()}
                    disabled={!connected || sending} data-testid="wa-message-input" />
                  <button className="btn-primary" onClick={send} disabled={!connected || sending || !text.trim()} data-testid="wa-send-btn"><Send className="w-4 h-4" /></button>
                </div>
              </div>
            </>
          )}
        </section>
      </div>

      {/* QR connect modal */}
      {qrModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={closeQr}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm text-center" onClick={(e) => e.stopPropagation()} data-testid="wa-qr-modal">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-display text-lg font-semibold text-ink-900">Conectar WhatsApp</h3>
              <button onClick={closeQr} className="text-ink-400 hover:text-ink-700"><X className="w-5 h-5" /></button>
            </div>
            <p className="text-sm text-ink-500 mb-4">Abre WhatsApp → Dispositivos vinculados → Vincular un dispositivo, y escanea este código.</p>
            <div className="aspect-square w-full max-w-[260px] mx-auto rounded-xl border-2 border-dashed border-ink-200 flex items-center justify-center bg-cream">
              {qr ? <img src={qr} alt="QR" className="w-full h-full object-contain p-2" data-testid="wa-qr-image" />
                : <div className="text-ink-400 text-sm flex flex-col items-center gap-2"><RefreshCw className="w-6 h-6 animate-spin" /> Generando código…</div>}
            </div>
            <p className="text-xs text-ink-400 mt-3" data-testid="wa-qr-status">Estado: {connStatus}</p>
          </div>
        </div>
      )}

      {/* Add number modal */}
      {addOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-900/50" onClick={() => setAddOpen(false)}>
          <div className="bg-white rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="wa-add-modal">
            <h3 className="font-display text-lg font-semibold text-ink-900 mb-4">Agregar número de WhatsApp</h3>
            <div className="space-y-3">
              <div><label className="label-text">Etiqueta (área/oficina)</label><input className="input-field" placeholder="Ventas GDL" value={addForm.label} onChange={(e) => setAddForm((f) => ({ ...f, label: e.target.value }))} data-testid="wa-add-label" /></div>
              <div><label className="label-text">Número (opcional)</label><input className="input-field" placeholder="+52 33 1234 5678" value={addForm.number} onChange={(e) => setAddForm((f) => ({ ...f, number: e.target.value }))} data-testid="wa-add-number" /></div>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button className="btn-ghost" onClick={() => setAddOpen(false)} data-testid="wa-add-cancel">Cancelar</button>
              <button className="btn-primary" onClick={addNumber} disabled={!addForm.label.trim()} data-testid="wa-add-submit">Agregar</button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
