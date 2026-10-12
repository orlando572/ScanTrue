import { ensureSession, getAnalysisOperation, renewSession } from './analysis.js';

const API_BASE = 'http://127.0.0.1:8000';
const SESSION_KEY = 'authSession';
const PENDING_KEY = 'accountPendingConfirmation';

class GuestRecoveryError extends Error {
  constructor(message) {
    super(message);
    this.name = 'GuestRecoveryError';
  }
}

function emailFrom(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function apiMessage(data, fallback) {
  const detail = data?.detail;
  if (typeof detail?.mensaje === 'string' && detail.mensaje.trim()) return detail.mensaje;
  if (typeof detail === 'string' && detail.trim()) return detail;
  return fallback;
}

async function postCredentials(path, email, password, headers = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify({ correo: email, contrasena: password }),
      signal: AbortSignal.timeout(25_000),
    });
  } catch {
    throw new Error('No pudimos comunicarnos con la API local. Comprueba que esté encendida.');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(apiMessage(data, 'No pudimos completar la solicitud. Inténtalo de nuevo.'));
    error.code = data?.detail?.codigo;
    throw error;
  }
  return data;
}

async function assertNoActiveAnalysis() {
  const operation = await getAnalysisOperation();
  if (operation?.status === 'working') throw new Error('Espera a que termine el análisis para cambiar de cuenta.');
}

async function saveAccountSession(data, email) {
  if (typeof data?.access_token !== 'string' || !data.access_token
    || typeof data?.refresh_token !== 'string' || !data.refresh_token
    || typeof data?.usuario_id !== 'string' || data.anonimo !== false
    || !Number.isFinite(data.expires_in) || data.expires_in <= 0) {
    throw new Error('La API no devolvió una sesión de cuenta válida.');
  }
  await chrome.storage.local.set({
    [SESSION_KEY]: {
      access_token: data.access_token,
      refresh_token: data.refresh_token,
      usuario_id: data.usuario_id,
      anonimo: false,
      correo: email,
      expiresAt: Date.now() + data.expires_in * 1000,
    },
  });
  await chrome.storage.local.remove(PENDING_KEY);
  try {
    await chrome.storage.session.remove(['analysisOperation', 'pendingSelection', 'selectionTargetTabId']);
  } catch { /* La sesión de cuenta ya quedó guardada. */ }
}

export async function registerAccount(email, password) {
  await chrome.storage.local.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' });
  await assertNoActiveAnalysis();
  const guest = await ensureSession();
  if (guest.anonimo !== true) throw new Error('Ya hay una cuenta iniciada.');
  const data = await postCredentials('/cuentas', email, password, {
    Authorization: `Bearer ${guest.access_token}`,
  });
  if (data?.estado === 'pendiente_confirmacion' && data.sesion == null) {
    await chrome.storage.local.set({ [PENDING_KEY]: { correo: email } });
    return { kind: 'pending_confirmation', email };
  }
  if (data?.estado !== 'activa' || !data.sesion) throw new Error('La API devolvió un registro incompleto.');
  await saveAccountSession(data.sesion, email);
  return { kind: 'account', email, transferred: data.registros_incorporados ?? 0 };
}

export async function loginAccount(email, password, skipGuestTransfer = false) {
  await chrome.storage.local.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' });
  await assertNoActiveAnalysis();
  const stored = await chrome.storage.local.get(SESSION_KEY);
  let current = stored[SESSION_KEY];
  if (!skipGuestTransfer && current?.anonimo === true && !(current.access_token && current.expiresAt > Date.now() + 60_000)) {
    if (!current.refresh_token) throw new GuestRecoveryError('La sesión invitada expiró. No pudimos incorporar su historial.');
    try { current = await renewSession(current); }
    catch { throw new GuestRecoveryError('No pudimos renovar tu sesión invitada para incorporar su historial.'); }
  }
  const headers = !skipGuestTransfer && current?.anonimo === true && current.access_token
    ? { 'X-Guest-Token': current.access_token } : {};
  let data;
  try { data = await postCredentials('/sesiones', email, password, headers); }
  catch (error) {
    if (headers['X-Guest-Token'] && error.code === 'sesion_invalida') {
      throw new GuestRecoveryError('La sesión invitada ya no es válida. No pudimos incorporar su historial.');
    }
    throw error;
  }
  if (!data?.sesion) throw new Error('La API devolvió un inicio de sesión incompleto.');
  await saveAccountSession(data.sesion, email);
  return { kind: 'account', email, transferred: data.registros_incorporados ?? 0, guestHistorySkipped: skipGuestTransfer && current?.anonimo === true };
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
