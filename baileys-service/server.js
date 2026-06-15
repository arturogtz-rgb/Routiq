/**
 * Routiq — WhatsApp (Baileys) microservice.
 *
 * Multi-session (one per company WhatsApp number). Connect via QR, persist the
 * auth state on disk, send messages and forward inbound messages to the FastAPI
 * backend through a secret-protected webhook.
 *
 * All HTTP endpoints (except /health) require the header `x-baileys-secret`
 * matching BAILEYS_SHARED_SECRET. The service is meant to live on a private
 * network, reachable only by the Routiq backend container.
 */
import express from 'express';
import { Boom } from '@hapi/boom';
import pino from 'pino';
import QRCode from 'qrcode';
import axios from 'axios';
import {
  default as makeWASocket,
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
} from '@whiskeysockets/baileys';

const PORT = process.env.PORT || 3001;
const SHARED_SECRET = process.env.BAILEYS_SHARED_SECRET || '';
const WEBHOOK_URL = (process.env.WEBHOOK_URL || '').replace(/\/$/, '');
const AUTH_DIR = process.env.AUTH_DIR || '/data/auth';

const logger = pino({ level: process.env.LOG_LEVEL || 'warn' });
const sessions = new Map(); // sessionId -> { sock, status, qr, jid, starting }

function safeDir(sessionId) {
  return `${AUTH_DIR}/${sessionId.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
}

async function forwardWebhook(event, body) {
  if (!WEBHOOK_URL) return;
  try {
    await axios.post(`${WEBHOOK_URL}/api/whatsapp/webhook`, { event, ...body }, {
      headers: { 'x-baileys-secret': SHARED_SECRET },
      timeout: 10000,
    });
  } catch (e) {
    logger.warn(`webhook ${event} failed: ${e.message}`);
  }
}

async function startSession(sessionId) {
  let s = sessions.get(sessionId);
  if (s && (s.status === 'connected' || s.starting)) return s;
  s = { sock: null, status: 'connecting', qr: null, jid: null, starting: true };
  sessions.set(sessionId, s);

  const { state, saveCreds } = await useMultiFileAuthState(safeDir(sessionId));
  const { version } = await fetchLatestBaileysVersion();
  const sock = makeWASocket({ version, auth: state, logger, printQRInTerminal: false, syncFullHistory: false });
  s.sock = sock;
  s.starting = false;

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      s.status = 'qr';
      try { s.qr = await QRCode.toDataURL(qr); } catch { s.qr = null; }
    }
    if (connection === 'open') {
      s.status = 'connected';
      s.qr = null;
      s.jid = sock.user?.id || null;
      forwardWebhook('status', { session_id: sessionId, status: 'connected', jid: s.jid });
    } else if (connection === 'close') {
      const code = (lastDisconnect?.error instanceof Boom) ? lastDisconnect.error.output?.statusCode : undefined;
      const loggedOut = code === DisconnectReason.loggedOut;
      s.status = loggedOut ? 'logged_out' : 'disconnected';
      forwardWebhook('status', { session_id: sessionId, status: s.status });
      if (!loggedOut) {
        setTimeout(() => startSession(sessionId).catch((e) => logger.error(e)), 3000);
      }
    }
  });

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;
    for (const m of messages) {
      const jid = m.key?.remoteJid || '';
      if (jid === 'status@broadcast') continue;
      const text =
        m.message?.conversation ||
        m.message?.extendedTextMessage?.text ||
        m.message?.imageMessage?.caption ||
        m.message?.videoMessage?.caption || '';
      await forwardWebhook('message', {
        session_id: sessionId,
        chat_id: jid,
        message_id: m.key?.id || '',
        from_me: !!m.key?.fromMe,
        text,
        push_name: m.pushName || '',
        timestamp: (m.messageTimestamp ? Number(m.messageTimestamp) : Math.floor(Date.now() / 1000)),
      });
    }
  });

  return s;
}

const app = express();
app.use(express.json({ limit: '2mb' }));

app.get('/health', (req, res) => res.json({ ok: true, sessions: sessions.size }));

// Secret guard for every other route
app.use((req, res, next) => {
  if (!SHARED_SECRET || req.headers['x-baileys-secret'] !== SHARED_SECRET) {
    return res.status(401).json({ error: 'unauthorized' });
  }
  next();
});

app.post('/sessions/:id/connect', async (req, res) => {
  try {
    const s = await startSession(req.params.id);
    res.json({ status: s.status });
  } catch (e) {
    logger.error(e);
    res.status(500).json({ error: e.message });
  }
});

app.get('/sessions/:id/qr', (req, res) => {
  const s = sessions.get(req.params.id);
  if (!s) return res.json({ status: 'idle', qr: null });
  res.json({ status: s.status, qr: s.qr, jid: s.jid });
});

app.get('/sessions/:id/status', (req, res) => {
  const s = sessions.get(req.params.id);
  res.json({ status: s?.status || 'idle', jid: s?.jid || null });
});

app.post('/sessions/:id/logout', async (req, res) => {
  const s = sessions.get(req.params.id);
  try {
    if (s?.sock) { try { await s.sock.logout(); } catch {} }
  } finally {
    sessions.delete(req.params.id);
    // wipe persisted auth so a fresh QR is required next time
    try {
      const fs = await import('fs/promises');
      await fs.rm(safeDir(req.params.id), { recursive: true, force: true });
    } catch {}
  }
  res.json({ ok: true });
});

app.post('/sessions/:id/send', async (req, res) => {
  const { to, text } = req.body || {};
  const s = sessions.get(req.params.id);
  if (!s || s.status !== 'connected' || !s.sock) {
    return res.status(409).json({ error: 'session_not_connected' });
  }
  const jid = String(to).includes('@') ? to : `${String(to).replace(/[^0-9]/g, '')}@s.whatsapp.net`;
  try {
    const sent = await s.sock.sendMessage(jid, { text: String(text || '') });
    res.json({ ok: true, message_id: sent?.key?.id || '', chat_id: jid });
  } catch (e) {
    logger.error(e);
    res.status(500).json({ error: e.message });
  }
});

app.listen(PORT, () => console.log(`Routiq Baileys service listening on :${PORT}`));
