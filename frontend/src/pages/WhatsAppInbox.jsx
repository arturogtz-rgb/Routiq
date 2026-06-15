import { useEffect, useMemo, useState } from 'react';
import AppShell from '@/components/AppShell';
import api from '@/lib/api';
import { MessageCircle, Sparkles, Smartphone, Send, Search } from 'lucide-react';

// UI-only mock of WhatsApp Inbox. Real Baileys integration is a dedicated phase.
const MOCK_CHATS = [
  {
    id: 'c1', name: 'Laura Ramírez', phone: '+52 55 2233 4455', wa_number: 'Ventas GDL',
    last: 'Perfecto, me interesa para el fin de semana largo.', unread: 2,
    summary: 'Pide paquete GDL-Tequila 4 días, pareja, marzo 15-18. Cliente recurrente.',
    subthreads: [
      { id: 's1', title: 'COT-2026001 · GDL + Tequila', state: 'cotizando', messages: [
        { me: false, t: '10:12', body: '¿Tienen paquete para Tequila en marzo?' },
        { me: true, t: '10:14', body: '¡Hola Laura! Sí, tenemos el GDL Clásica + Tequila 4 días.' },
        { me: false, t: '10:18', body: 'Perfecto, me interesa para el fin de semana largo.' },
      ]},
    ],
  },
  {
    id: 'c2', name: 'Agencia Viajes del Sol', phone: '+52 33 5566 7788', wa_number: 'Ventas GDL',
    last: '¿Tarifa agencia para grupo de 12?', unread: 0,
    summary: 'Solicita tarifa agencia (10%) para grupo corporativo a Puerto Vallarta en abril.',
    subthreads: [
      { id: 's2', title: 'COT-2026005 · PV Lujo grupo 12', state: 'negociacion', messages: [
        { me: false, t: 'Ayer', body: '¿Tarifa agencia para grupo de 12?' },
      ]},
    ],
  },
];

export default function WhatsAppInbox() {
  const [selectedChat, setSelectedChat] = useState(MOCK_CHATS[0].id);
  const chat = useMemo(() => MOCK_CHATS.find((c) => c.id === selectedChat), [selectedChat]);
  const [waStatus, setWaStatus] = useState('disconnected');
  const [aiSummary, setAiSummary] = useState('');
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get('/companies/me');
        const n = data?.whatsapp_numbers?.[0];
        if (n) setWaStatus(n.status);
      } catch (_e) { /* noop */ }
    })();
  }, []);

  useEffect(() => { setAiSummary(''); }, [selectedChat]);

  const generateSummary = async () => {
    setAiLoading(true);
    try {
      const messages = chat.subthreads[0].messages;
      const { data } = await api.post('/ai/chat-summary', { messages });
      setAiSummary(data.summary);
    } catch (_e) {
      setAiSummary('No se pudo generar el resumen. Verifica que EMERGENT_LLM_KEY esté configurada.');
    } finally { setAiLoading(false); }
  };

  return (
    <AppShell>
      <div className="mb-6 flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold text-ink-900 tracking-tight">WhatsApp Inbox</h1>
          <p className="text-ink-500 mt-1">Sub-hilos por cotización en un solo lugar.</p>
        </div>
        <span className={`pill ${waStatus === 'connected' ? 'bg-mint-100 text-emerald-700' : 'bg-peach-100 text-amber-800'}`} data-testid="wa-status-pill">
          <Smartphone className="w-3.5 h-3.5" /> {waStatus === 'connected' ? 'Número conectado' : 'Pendiente de conexión (fase Baileys)'}
        </span>
      </div>

      <div className="card-surface overflow-hidden grid md:grid-cols-[320px_1fr] min-h-[600px]" data-testid="wa-inbox">
        {/* Chat list */}
        <aside className="border-r border-ink-100 flex flex-col">
          <div className="p-3 border-b border-ink-100">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-400" />
              <input className="input-field pl-10" placeholder="Buscar chat" data-testid="wa-search" />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {MOCK_CHATS.map((c) => (
              <button key={c.id} onClick={() => setSelectedChat(c.id)}
                className={`w-full text-left px-4 py-3 border-b border-ink-100 transition-colors ${selectedChat === c.id ? 'bg-brand-50' : 'hover:bg-cream'}`}
                data-testid={`wa-chat-${c.id}`}>
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-ink-900">{c.name}</p>
                  {c.unread > 0 && <span className="pill bg-brand-500 text-white text-[10px]">{c.unread}</span>}
                </div>
                <p className="text-xs text-ink-400 mt-0.5">{c.wa_number}</p>
                <p className="text-sm text-ink-500 mt-1 truncate">{c.last}</p>
              </button>
            ))}
          </div>
        </aside>

        {/* Conversation */}
        <section className="flex flex-col">
          {chat && (
            <>
              <header className="p-4 border-b border-ink-100">
                <p className="font-semibold text-ink-900">{chat.name}</p>
                <p className="text-xs text-ink-400">{chat.phone} · vía {chat.wa_number}</p>
                <div className="mt-3 rounded-xl bg-mint-100 p-3 flex gap-3" data-testid="ai-summary">
                  <Sparkles className="w-4 h-4 shrink-0 text-emerald-700 mt-0.5" />
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <p className="text-xs uppercase tracking-widest font-bold text-emerald-800">Resumen IA</p>
                      <button onClick={generateSummary} disabled={aiLoading} className="text-xs text-emerald-800 hover:underline disabled:opacity-50" data-testid="generate-ai-summary">
                        {aiLoading ? 'Generando…' : (aiSummary ? 'Regenerar' : 'Generar')}
                      </button>
                    </div>
                    <p className="text-sm text-ink-900 mt-1">{aiSummary || chat.summary}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {chat.subthreads.map((s) => (
                    <span key={s.id} className="pill bg-brand-50 text-brand-500" data-testid={`subthread-${s.id}`}>
                      <MessageCircle className="w-3 h-3" /> {s.title} · {s.state}
                    </span>
                  ))}
                </div>
              </header>
              <div className="flex-1 overflow-y-auto p-6 space-y-3 bg-cream">
                {chat.subthreads[0].messages.map((m, i) => (
                  <div key={i} className={`flex ${m.me ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm ${m.me ? 'bg-brand-500 text-white rounded-br-sm' : 'bg-white text-ink-900 border border-ink-100 rounded-bl-sm'}`}>
                      <p>{m.body}</p>
                      <p className={`text-[10px] mt-1 ${m.me ? 'text-brand-50/80' : 'text-ink-400'}`}>{m.t}</p>
                    </div>
                  </div>
                ))}
              </div>
              <div className="p-4 border-t border-ink-100 bg-white">
                <div className="flex gap-2">
                  <input className="input-field flex-1" placeholder="Envío real disponible al conectar WhatsApp" disabled data-testid="wa-message-input" />
                  <button className="btn-primary opacity-60 cursor-not-allowed" disabled data-testid="wa-send-btn"><Send className="w-4 h-4" /></button>
                </div>
                <p className="text-xs text-ink-400 mt-2">El envío real se habilita al conectar un número con Baileys (fase 6).</p>
              </div>
            </>
          )}
        </section>
      </div>
    </AppShell>
  );
}
