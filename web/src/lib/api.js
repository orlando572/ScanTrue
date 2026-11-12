// Cliente de la API de ScanTrue. Las rutas /publico no llevan sesión; las de /admin usan
// la sesión del administrador (solo en sessionStorage: se pierde al cerrar la pestaña).
export const API_BASE = (import.meta.env?.VITE_API_BASE ?? 'http://127.0.0.1:8000').replace(/\/$/, '');

const SESSION_KEY = 'scantrue.admin';
const listeners = new Set();

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function messageFrom(data, fallback) {
  const detail = data?.detail;
  if (typeof detail?.mensaje === 'string' && detail.mensaje.trim()) return detail.mensaje;
  if (typeof detail === 'string' && detail.trim()) return detail;
  return fallback;
}

async function send(path, { method = 'GET', body, token, signal, timeout = 20_000 } = {}) {
  const limit = AbortSignal.timeout(timeout);
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: signal ? AbortSignal.any([signal, limit]) : limit,
    });
  } catch (error) {
    if (error?.name === 'AbortError') throw error;
    throw new ApiError(0, 'sin_conexion', 'No pudimos comunicarnos con la API de ScanTrue. Comprueba que esté encendida.');
  }
  return response;
}

async function parse(response) {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      response.status,
      data?.detail?.codigo ?? null,
      messageFrom(data, response.status === 404 ? 'No encontramos lo que buscabas.' : 'No pudimos completar la solicitud.'),
    );
  }
  return data;
}

export function query(params) {
  const search = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

export async function publicApi(path, options) {
  return parse(await send(path, options));
}

// ── Sesión del administrador ──────────────────────────────────────

export function getSession() {
  try {
    const session = JSON.parse(sessionStorage.getItem(SESSION_KEY) ?? 'null');
    return session?.access_token ? session : null;
  } catch { return null; }
}

function storeSession(session) {
  try {
    if (session) sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else sessionStorage.removeItem(SESSION_KEY);
  } catch { /* Sin almacenamiento la sesión dura lo que la página. */ }
  listeners.forEach((listener) => listener(session));
}

export function onSessionChange(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function sessionFrom(data, email) {
  return {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    expiresAt: Date.now() + Number(data.expires_in ?? 0) * 1000,
    correo: email,
  };
}

let renewing = null;

async function renew(session) {
  renewing ??= (async () => {
    try {
      const data = await parse(await send('/sesiones/renovar', {
        method: 'POST', body: { refresh_token: session.refresh_token },
      }));
      const renewed = sessionFrom(data, session.correo);
      storeSession(renewed);
      return renewed;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) storeSession(null);
      throw error;
    } finally { renewing = null; }
  })();
  return renewing;
}

async function adminSend(path, options) {
  let session = getSession();
  if (!session) throw new ApiError(401, 'sesion_requerida', 'Inicia sesión como administrador.');
  if (session.expiresAt < Date.now() + 30_000 && session.refresh_token) session = await renew(session);
  let response = await send(path, { ...options, token: session.access_token });
  if (response.status === 401 && session.refresh_token) {
    session = await renew(session);
    response = await send(path, { ...options, token: session.access_token });
  }
  if (response.status === 401) storeSession(null);
  return response;
}

export async function adminApi(path, options) {
  return parse(await adminSend(path, options));
}

// Descarga con sesión (el CSV de un dataset): devuelve el archivo y su nombre.
export async function adminDownload(path) {
  const response = await adminSend(path, { timeout: 60_000 });
  if (!response.ok) await parse(response);
  const name = /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') ?? '')?.[1];
  return { blob: await response.blob(), name: name ?? 'scantrue_dataset.csv' };
}

export async function login(email, password) {
  const data = await parse(await send('/sesiones', {
    method: 'POST', body: { correo: email, contrasena: password },
  }));
  const session = sessionFrom(data.sesion, email);
  // Solo las cuentas con rol de administrador pueden quedarse con la sesión.
  const check = await send('/admin/yo', { token: session.access_token });
  if (!check.ok) {
    await send('/sesiones/cerrar', { method: 'POST', token: session.access_token }).catch(() => {});
    if (check.status === 403) throw new ApiError(403, 'no_es_admin', 'Esta cuenta no tiene acceso de administrador.');
    await parse(check);
  }
  storeSession(session);
  return session;
}

export async function logout() {
  const session = getSession();
  storeSession(null);
  if (session) await send('/sesiones/cerrar', { method: 'POST', token: session.access_token }).catch(() => {});
}
