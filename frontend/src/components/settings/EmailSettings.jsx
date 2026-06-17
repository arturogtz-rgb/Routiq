import { Mail, Server, Send, Trash2, BarChart3 } from 'lucide-react';

const WEEKDAYS = [['1', 'Lunes'], ['2', 'Martes'], ['3', 'Miércoles'], ['4', 'Jueves'], ['5', 'Viernes'], ['6', 'Sábado'], ['0', 'Domingo']];

export const EmailSettings = ({
  integ, setInteg, company, backend,
  connectGmail, disconnectGmail,
  testSmtp, smtpTesting, smtpTestEmail, setSmtpTestEmail,
  testResend, resendTesting, resendTestEmail, setResendTestEmail,
  sendReportNow, sendingReport,
}) => {
  const provider = integ.email_provider || 'resend';
  return (
    <div className="space-y-4">
      <h3 className="font-semibold text-ink-900 flex items-center gap-2"><Mail className="w-4 h-4 text-brand-500" /> Correo saliente</h3>
      <div>
        <label className="label-text">Proveedor de envío</label>
        <select className="input-field" value={provider}
          onChange={(e) => setInteg((s) => ({ ...s, email_provider: e.target.value }))} data-testid="email-provider-select">
          <option value="resend">Resend (API)</option>
          <option value="smtp">SMTP propio (correo corporativo)</option>
          <option value="gmail">Gmail (OAuth)</option>
        </select>
        <p className="text-xs text-ink-400 mt-1">Las cotizaciones y cobros se enviarán con el proveedor seleccionado.</p>
      </div>

      {provider === 'gmail' ? (
        <div className="rounded-xl border border-ink-100 bg-cream/50 p-4 space-y-3" data-testid="gmail-section">
          <p className="text-xs text-ink-500">Registra un <b>OAuth Client (Web)</b> en Google Cloud y agrega esta Redirect URI:
            <code className="block mt-1 px-2 py-1 bg-white rounded border border-ink-100 text-[11px] break-all" data-testid="gmail-redirect-uri">{backend}/api/oauth/gmail/callback</code>
          </p>
          <div><label className="label-text">Client ID</label><input className="input-field" placeholder="xxxx.apps.googleusercontent.com" value={integ.gmail_client_id || ''} onChange={(e) => setInteg((s) => ({ ...s, gmail_client_id: e.target.value }))} data-testid="gmail-client-id-input" /></div>
          <div>
            <label className="label-text">Client Secret</label>
            <input type="password" className="input-field" placeholder={integ.gmail_client_secret_set ? 'Guardado ••••' : 'GOCSPX-...'}
              value={integ.gmail_client_secret || ''} onChange={(e) => setInteg((s) => ({ ...s, gmail_client_secret: e.target.value }))} data-testid="gmail-client-secret-input" />
            <p className="text-xs text-ink-400 mt-1">Guarda primero (botón abajo) y luego conecta con Google.</p>
          </div>
          <div><label className="label-text">Nombre remitente</label><input className="input-field" placeholder={company?.name || 'Tu empresa'} value={integ.gmail_from_name || ''} onChange={(e) => setInteg((s) => ({ ...s, gmail_from_name: e.target.value }))} data-testid="gmail-from-name-input" /></div>
          <div className="pt-2 border-t border-ink-100">
            {integ.gmail_connected ? (
              <div className="flex items-center justify-between gap-2" data-testid="gmail-connected">
                <p className="text-sm text-emerald-700 font-semibold">✓ Conectado: {integ.gmail_email}</p>
                <button type="button" className="btn-ghost text-xs text-red-600" onClick={disconnectGmail} data-testid="gmail-disconnect-btn"><Trash2 className="w-3.5 h-3.5" /> Desconectar</button>
              </div>
            ) : (
              <button type="button" className="btn-primary text-sm" onClick={connectGmail} disabled={!integ.gmail_client_id_set || !integ.gmail_client_secret_set} data-testid="gmail-connect-btn">
                <Mail className="w-4 h-4" /> Conectar con Google
              </button>
            )}
          </div>
        </div>
      ) : provider === 'resend' ? (
        <>
          <div>
            <label className="label-text">API key de Resend</label>
            <input type="password" className="input-field" placeholder={integ.resend_api_key_set ? `Guardada ${integ.resend_api_key_masked}` : 're_...'}
              value={integ.resend_api_key || ''} onChange={(e) => setInteg((s) => ({ ...s, resend_api_key: e.target.value }))} data-testid="resend-key-input" />
          </div>
          <div>
            <label className="label-text">Correo remitente (verificado en Resend)</label>
            <input className="input-field" value={integ.resend_from_email || ''} placeholder="no-reply@tudominio.com"
              onChange={(e) => setInteg((s) => ({ ...s, resend_from_email: e.target.value }))} data-testid="resend-from-input" />
          </div>
          <div>
            <label className="label-text">Nombre remitente</label>
            <input className="input-field" value={integ.resend_from_name || ''} placeholder={company?.name || 'Tu empresa'}
              onChange={(e) => setInteg((s) => ({ ...s, resend_from_name: e.target.value }))} data-testid="resend-name-input" />
          </div>
          <div className="rounded-xl border border-ink-100 bg-cream/50 p-4">
            <label className="label-text">Enviar prueba a (opcional)</label>
            <div className="flex gap-2">
              <input className="input-field flex-1" placeholder={integ.resend_from_email || 'correo@destino.com'} value={resendTestEmail} onChange={(e) => setResendTestEmail(e.target.value)} data-testid="resend-test-email-input" />
              <button className="btn-ghost whitespace-nowrap" onClick={testResend} disabled={resendTesting || (!integ.resend_api_key && !integ.resend_api_key_set)} data-testid="resend-test-btn">
                <Send className="w-4 h-4" /> {resendTesting ? 'Enviando…' : 'Probar'}
              </button>
            </div>
            <p className="text-xs text-ink-400 mt-1">Confirma que tu dominio esté verificado en Resend antes de usarlo en producción.</p>
          </div>
        </>
      ) : (
        <div className="rounded-xl border border-ink-100 bg-cream/50 p-4 space-y-3" data-testid="smtp-section">
          <p className="text-xs text-ink-500 flex items-center gap-1.5"><Server className="w-3.5 h-3.5" /> Datos de tu servidor de correo (Gmail, Outlook, cPanel, etc.).</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2"><label className="label-text">Servidor SMTP (host)</label><input className="input-field" placeholder="smtp.gmail.com" value={integ.smtp_host || ''} onChange={(e) => setInteg((s) => ({ ...s, smtp_host: e.target.value }))} data-testid="smtp-host-input" /></div>
            <div><label className="label-text">Puerto</label><input type="number" className="input-field" placeholder="587" value={integ.smtp_port || 587} onChange={(e) => setInteg((s) => ({ ...s, smtp_port: e.target.value }))} data-testid="smtp-port-input" /></div>
            <div className="flex items-end pb-2">
              <label className="flex items-center gap-2 cursor-pointer text-sm text-ink-700">
                <input type="checkbox" checked={integ.smtp_use_tls !== false} onChange={(e) => setInteg((s) => ({ ...s, smtp_use_tls: e.target.checked }))} data-testid="smtp-tls-input" />
                Usar TLS/STARTTLS
              </label>
            </div>
            <div className="col-span-2"><label className="label-text">Usuario</label><input className="input-field" placeholder="tucorreo@tudominio.com" value={integ.smtp_username || ''} onChange={(e) => setInteg((s) => ({ ...s, smtp_username: e.target.value }))} data-testid="smtp-username-input" /></div>
            <div className="col-span-2">
              <label className="label-text">Contraseña / App Password</label>
              <input type="password" className="input-field" placeholder={integ.smtp_password_set ? 'Guardada ••••' : 'Contraseña del correo'}
                value={integ.smtp_password || ''} onChange={(e) => setInteg((s) => ({ ...s, smtp_password: e.target.value }))} data-testid="smtp-password-input" />
              <p className="text-xs text-ink-400 mt-1">Déjala vacía para conservar la actual. En Gmail usa una "Contraseña de aplicación".</p>
            </div>
            <div className="col-span-2"><label className="label-text">Correo remitente (From)</label><input className="input-field" placeholder="ventas@tudominio.com" value={integ.smtp_from_email || ''} onChange={(e) => setInteg((s) => ({ ...s, smtp_from_email: e.target.value }))} data-testid="smtp-from-input" /></div>
            <div className="col-span-2"><label className="label-text">Nombre remitente</label><input className="input-field" placeholder={company?.name || 'Tu empresa'} value={integ.smtp_from_name || ''} onChange={(e) => setInteg((s) => ({ ...s, smtp_from_name: e.target.value }))} data-testid="smtp-from-name-input" /></div>
          </div>
          <div className="pt-2 border-t border-ink-100">
            <label className="label-text">Enviar prueba a (opcional)</label>
            <div className="flex gap-2">
              <input className="input-field flex-1" placeholder={integ.smtp_from_email || 'correo@destino.com'} value={smtpTestEmail} onChange={(e) => setSmtpTestEmail(e.target.value)} data-testid="smtp-test-email-input" />
              <button className="btn-ghost whitespace-nowrap" onClick={testSmtp} disabled={smtpTesting || !integ.smtp_host || !integ.smtp_username} data-testid="smtp-test-btn">
                <Send className="w-4 h-4" /> {smtpTesting ? 'Enviando…' : 'Probar'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div>
        <label className="label-text">Correo de avisos (ventas / ejecutivo)</label>
        <input className="input-field" value={integ.notify_email || ''} placeholder="ventas@tudominio.com"
          onChange={(e) => setInteg((s) => ({ ...s, notify_email: e.target.value }))} data-testid="notify-email-input" />
        <p className="text-xs text-ink-400 mt-1">Recibe avisos cuando un cliente acepta o paga una cotización.</p>
      </div>

      <div className="rounded-xl border border-ink-100 bg-cream/50 p-4 space-y-3" data-testid="report-section">
        <h3 className="font-semibold text-ink-900 flex items-center gap-2"><BarChart3 className="w-4 h-4 text-brand-500" /> Resumen automático de ventas</h3>
        <label className="flex items-center gap-2 cursor-pointer text-sm text-ink-700">
          <input type="checkbox" checked={!!integ.report_enabled}
            onChange={(e) => setInteg((s) => ({ ...s, report_enabled: e.target.checked }))} data-testid="report-enabled-input" />
          Enviar un resumen periódico con los KPIs y el Excel adjunto al correo de avisos.
        </label>
        {integ.report_enabled && (
          <div className="grid grid-cols-2 gap-3" data-testid="report-config">
            <div>
              <label className="label-text">Frecuencia</label>
              <select className="input-field" value={integ.report_frequency || 'weekly'}
                onChange={(e) => setInteg((s) => ({ ...s, report_frequency: e.target.value }))} data-testid="report-frequency-input">
                <option value="weekly">Semanal</option>
                <option value="monthly">Mensual</option>
              </select>
            </div>
            <div>
              <label className="label-text">{(integ.report_frequency || 'weekly') === 'weekly' ? 'Día de la semana' : 'Día del mes'}</label>
              {(integ.report_frequency || 'weekly') === 'weekly' ? (
                <select className="input-field" value={String(integ.report_day ?? 1)}
                  onChange={(e) => setInteg((s) => ({ ...s, report_day: Number(e.target.value) }))} data-testid="report-day-input">
                  {WEEKDAYS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              ) : (
                <select className="input-field" value={String(integ.report_day ?? 1)}
                  onChange={(e) => setInteg((s) => ({ ...s, report_day: Number(e.target.value) }))} data-testid="report-day-input">
                  {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              )}
            </div>
            <div>
              <label className="label-text">Hora de envío</label>
              <select className="input-field" value={String(integ.report_hour ?? 8)}
                onChange={(e) => setInteg((s) => ({ ...s, report_hour: Number(e.target.value) }))} data-testid="report-hour-input">
                {Array.from({ length: 24 }, (_, i) => i).map((h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}
              </select>
              <p className="text-xs text-ink-400 mt-1">Hora de México (CDMX).</p>
            </div>
            <div className="flex items-end">
              <button type="button" className="btn-ghost text-sm" onClick={sendReportNow} disabled={sendingReport} data-testid="report-send-now-btn">
                <Send className="w-4 h-4" /> {sendingReport ? 'Enviando…' : 'Enviar ahora (prueba)'}
              </button>
            </div>
          </div>
        )}
        <p className="text-xs text-ink-400">Guarda los cambios para activarlo. El correo se envía con tu proveedor configurado arriba.</p>
      </div>
    </div>
  );
};
