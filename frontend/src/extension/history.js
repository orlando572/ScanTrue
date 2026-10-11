import { ensureSession, renewSession } from './analysis.js';

const API_BASE = 'http://127.0.0.1:8000';
const PAGE_SIZE = 20;

function parsePage(data, offset) {
  const items = Array.isArray(data) ? data : [data?.items, data?.analisis, data?.registros].find(Array.isArray);
  if (!items) throw new Error('Respuesta de historial no reconocida');
  const total = Number.isInteger(data?.total) && data.total >= 0 ? data.total : null;
  const hasMore = typeof data?.hay_mas === 'boolean' ? data.hay_mas
    : typeof data?.has_more === 'boolean' ? data.has_more
      : total !== null ? offset + items.length < total : items.length === PAGE_SIZE;
  return { items, hasMore: items.length > 0 && hasMore, nextOffset: offset + items.length };
}

export async function listHistory(offset = 0) {
  if (!Number.isInteger(offset) || offset < 0) throw new Error('Página de historial inválida');
  const url = `${API_BASE}/analisis?limit=${PAGE_SIZE}&offset=${offset}`;
  const response = await historyRequest(url);
  if (!response.ok) throw new Error(response.status === 401 ? 'Tu sesión ya no está disponible.' : 'No pudimos cargar el historial.');
  const data = await response.json();
  return parsePage(data, offset);
}

export async function getHistoryDetail(id) {
  if (typeof id !== 'string' || !id) throw new Error('Análisis inválido');
  const response = await historyRequest(`${API_BASE}/analisis/${encodeURIComponent(id)}`);
  if (response.status === 404) return { found: false, item: null };
  if (!response.ok) throw new Error(response.status === 401 ? 'Tu sesión ya no está disponible.' : 'No pudimos abrir este análisis.');
  const item = await response.json();
  if (!item || item.id !== id) throw new Error('Detalle de análisis no reconocido');
  return { found: true, item };
}

export async function deleteHistoryDetail(id) {
  if (typeof id !== 'string' || !id) throw new Error('Análisis inválido');
  const response = await historyRequest(`${API_BASE}/analisis/${encodeURIComponent(id)}`, 'DELETE');
  if (!response.ok) throw new Error(response.status === 404 ? 'Este análisis ya no está disponible.' : 'No pudimos eliminar este análisis.');
  const data = await response.json().catch(() => null);
  if (data?.eliminado !== true) throw new Error('No pudimos confirmar la eliminación.');
  return { deleted: true };
}

async function historyRequest(url, method = 'GET') {
  let session = await ensureSession();
  const send = (token) => fetch(url, {
    method,
    headers: { Accept: 'application/json', Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(25_000),
  });
  let response = await send(session.access_token);
  if (response.status === 401 && session.refresh_token) {
    session = await renewSession(session);
    response = await send(session.access_token);
  }
  return response;
}
