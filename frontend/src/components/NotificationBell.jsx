import { useEffect, useRef, useState } from 'react';
import { Bell, CheckCheck, BellRing, BellOff } from 'lucide-react';
import api from '@/lib/api';
import { pushSupported, getPushState, subscribePush, unsubscribePush } from '@/lib/push';

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [pushState, setPushState] = useState('default'); // default | subscribed | denied | unsupported
  const [busy, setBusy] = useState(false);
  const ref = useRef(null);

  const load = async () => {
    try {
      const { data } = await api.get('/notifications');
      setItems(data.items || []);
      setUnread(data.unread || 0);
    } catch (_e) { /* noop */ }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    if (pushSupported()) getPushState().then(setPushState);
    else setPushState('unsupported');
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && unread > 0) {
      await api.post('/notifications/read-all').catch(() => null);
      setUnread(0);
    }
  };

  const togglePush = async () => {
    setBusy(true);
    try {
      if (pushState === 'subscribed') setPushState(await unsubscribePush());
      else setPushState(await subscribePush());
    } catch (e) {
      alert(e.message || 'No se pudo activar las notificaciones');
    } finally { setBusy(false); }
  };

  return (
    <div className="relative" ref={ref}>
      <button onClick={toggle} className="relative p-2 rounded-lg text-ink-500 hover:bg-brand-50 hover:text-brand-500 transition-colors" data-testid="notification-bell">
        <Bell className="w-[18px] h-[18px]" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center" data-testid="notification-badge">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-80 max-h-[28rem] overflow-auto bg-white rounded-2xl shadow-2xl border border-ink-100 z-50 animate-fade-up" data-testid="notification-panel">
          <div className="px-4 py-3 border-b border-ink-100 flex items-center justify-between">
            <p className="font-display font-semibold text-ink-900 text-sm">Notificaciones</p>
            <CheckCheck className="w-4 h-4 text-ink-400" />
          </div>
          {pushState !== 'unsupported' && (
            <button onClick={togglePush} disabled={busy || pushState === 'denied'}
              className="w-full flex items-center gap-2 px-4 py-3 text-sm border-b border-ink-100 hover:bg-brand-50/40 disabled:opacity-60 text-left" data-testid="push-toggle-btn">
              {pushState === 'subscribed' ? <BellRing className="w-4 h-4 text-brand-500" /> : <BellOff className="w-4 h-4 text-ink-400" />}
              <span className="flex-1">
                {pushState === 'subscribed' ? 'Notificaciones push activadas' : pushState === 'denied' ? 'Push bloqueado en el navegador' : 'Activar notificaciones push'}
              </span>
              {pushState === 'subscribed' && <span className="pill bg-mint-100 text-emerald-700 text-[10px]">ON</span>}
            </button>
          )}
          {items.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-ink-400">Sin notificaciones</p>
          ) : (
            <ul>
              {items.map((n, i) => (
                <li key={i} className={`px-4 py-3 border-b border-ink-50 last:border-0 ${n.read ? '' : 'bg-brand-50/40'}`} data-testid={`notification-item-${i}`}>
                  <p className="text-sm font-semibold text-ink-900">{n.title}</p>
                  <p className="text-xs text-ink-500 mt-0.5">{n.body}</p>
                  <p className="text-[10px] text-ink-300 mt-1">{(n.created_at || '').slice(0, 16).replace('T', ' ')}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

