import { getAnalysisOperation, renewSession } from './analysis.js';

const API_BASE = 'http://127.0.0.1:8000';
const SESSION_KEY = 'authSession';
const PENDING_KEY = 'accountPendingConfirmation';

function emailFrom(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

export async function getAccountState() {
  await chrome.storage.local.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' });
  const stored = await chrome.storage.local.get([SESSION_KEY, PENDING_KEY]);
  let session = stored[SESSION_KEY];
  const pendingEmail = emailFrom(stored[PENDING_KEY]?.correo);

  if (!session?.access_token && !session?.refresh_token) {
    return pendingEmail ? { kind: 'pending_confirmation', email: pendingEmail } : { kind: 'none', email: null };
  }
  if (!session?.access_token || !(session.expiresAt > Date.now() + 60_000)) {
    if (!session.refresh_token) return { kind: 'expired', email: emailFrom(session.correo) };
    try { session = await renewSession(session); }
    catch { return { kind: 'expired', email: emailFrom(session.correo) }; }
  }
  if (session.anonimo === false) return { kind: 'account', email: emailFrom(session.correo) };
  if (session.anonimo === true) return pendingEmail
    ? { kind: 'pending_confirmation', email: pendingEmail }
    : { kind: 'guest', email: null };
  return { kind: 'unknown', email: null };
}

export async function closeAccountSession() {
  await chrome.storage.local.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' });
  const operation = await getAnalysisOperation();
  if (operation?.status === 'working') throw new Error('Espera a que termine el análisis para cerrar sesión.');
  const stored = await chrome.storage.local.get(SESSION_KEY);
  let session = stored[SESSION_KEY];
  if (session?.anonimo !== false || !session?.access_token) throw new Error('No hay una cuenta activa.');
  if (!(session.expiresAt > Date.now() + 60_000)) {
    if (!session.refresh_token) throw new Error('Tu sesión ya no está disponible.');
    session = await renewSession(session);
  }

  const send = (token) => fetch(`${API_BASE}/sesiones/cerrar`, {
    method: 'POST',
    headers: { Accept: 'application/json', Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(25_000),
  });
  let response = await send(session.access_token);
  if (response.status === 401 && session.refresh_token) {
    session = await renewSession(session);
    response = await send(session.access_token);
  }
  if (!response.ok) throw new Error('No pudimos cerrar la sesión.');
  const data = await response.json().catch(() => null);
  if (data?.cerrada !== true) throw new Error('No pudimos confirmar el cierre de sesión.');
  await chrome.storage.local.remove([SESSION_KEY, PENDING_KEY]);
  await chrome.storage.session.remove(['analysisOperation', 'pendingSelection', 'selectionTargetTabId']);
  return { signedOut: true };
}
