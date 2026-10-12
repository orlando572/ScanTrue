const API_BASE = 'http://127.0.0.1:8000';
const OPERATION_KEY = 'analysisOperation';
const SESSION_KEY = 'authSession';

let startGate = null;
let running = false;

class AnalysisFailure extends Error {
  constructor(status, message, retryable = false) {
    super(message);
    this.status = status;
    this.retryable = retryable;
  }
}

export function startAnalysis() {
  if (startGate) return startGate;
  startGate = prepareAnalysis().finally(() => { startGate = null; });
  return startGate;
}

export async function getAnalysisOperation() {
  const items = await chrome.storage.session.get(OPERATION_KEY);
  const operation = items[OPERATION_KEY] ?? null;
  if (operation?.status === 'working' && !running && Date.now() - operation.startedAt > 35_000) {
    const sent = operation.stage === 'request';
    const recovered = {
      ...operation,
      status: sent ? 'uncertain' : 'service_error',
      message: sent
        ? 'No pudimos confirmar el resultado. Revisa tu historial antes de intentarlo de nuevo.'
        : 'No pudimos iniciar el análisis. Inténtalo de nuevo.',
      retryable: !sent,
      finishedAt: Date.now(),
    };
    await chrome.storage.session.set({ [OPERATION_KEY]: recovered });
    return recovered;
  }
  return operation;
}

export async function clearCompletedAnalysis() {
  const operation = await getAnalysisOperation();
  if (operation?.status !== 'completed') return false;
  await chrome.storage.session.remove(OPERATION_KEY);
  return true;
}

async function prepareAnalysis() {
  const items = await chrome.storage.session.get('pendingSelection');
  const selection = items.pendingSelection;
  if (!selection?.text?.trim()) return { ok: false, error: 'Primero escoge un fragmento de la página.' };
  const previous = await getAnalysisOperation();
  if (previous?.status === 'working') return { ok: true, operation: previous };
  if (previous?.status === 'uncertain' && previous.selectionCapturedAt === selection.capturedAt) {
    return { ok: false, error: 'Revisa tu historial antes de volver a analizar este texto.' };
  }

  const operation = {
    id: crypto.randomUUID(),
    status: 'working',
    stage: 'session',
    startedAt: Date.now(),
    selectionCapturedAt: selection.capturedAt,
  };
  await chrome.storage.session.set({ [OPERATION_KEY]: operation });
  running = true;
  void performAnalysis(selection, operation)
    .catch(() => {})
    .finally(() => { running = false; });
  return { ok: true, operation };
}

async function performAnalysis(selection, operation) {
  let sent = false;
  try {
    const session = await ensureSession();
    await markRequestStarted(operation);
    sent = true;
    let response = await request('/analisis', {
      method: 'POST',
      headers: { Authorization: `Bearer ${session.access_token}` },
      body: JSON.stringify({ texto: selection.text, url: selection.url ?? null }),
    });
    if (response.status === 401 && session.refresh_token) {
      sent = false;
      await chrome.storage.session.set({ [OPERATION_KEY]: { ...operation, stage: 'session' } });
      const renewed = await renewSession(session);
      await markRequestStarted(operation);
      sent = true;
      response = await request('/analisis', {
        method: 'POST',
        headers: { Authorization: `Bearer ${renewed.access_token}` },
        body: JSON.stringify({ texto: selection.text, url: selection.url ?? null }),
      });
    }
    if (response.status === 422) {
      const detail = response.data?.detail;
      await finish(operation, 'validation', {
        message: typeof detail?.mensaje === 'string' ? detail.mensaje : 'No se pudo analizar este fragmento.',
        correction: typeof detail?.como_corregir === 'string' ? detail.como_corregir : null,
      });
      return;
    }
    if (response.status === 401) throw new AnalysisFailure('session_error', 'No pudimos iniciar tu sesión. Inténtalo de nuevo.', true);
    if (response.status === 502 && response.data?.detail?.codigo === 'supabase_rechazo_operacion') {
      throw new AnalysisFailure('storage_error', 'No pudimos guardar el análisis. Vuelve al texto antes de intentarlo de nuevo.');
    }
    if (response.status === 503) throw new AnalysisFailure('service_error', 'El servicio no está disponible en este momento.', response.data?.detail?.reintentar === true);
    if (response.status >= 500) throw new AnalysisFailure('uncertain', 'No pudimos confirmar el resultado. Revisa tu historial antes de intentarlo de nuevo.');
    if (!response.ok) throw new AnalysisFailure('service_error', 'No pudimos completar el análisis. Vuelve al texto antes de intentarlo de nuevo.');
    if (typeof response.data?.id !== 'string' || typeof response.data?.resultados !== 'object' || !response.data.resultados) {
      const invalid = new Error('Incomplete analysis response');
      invalid.name = 'InvalidResponseError';
      throw invalid;
    }
    await finish(operation, 'completed', { result: response.data });
    try { await chrome.storage.session.remove('pendingSelection'); } catch { /* The result is already saved. */ }
  } catch (error) {
    if (error instanceof AnalysisFailure) {
      await finish(operation, error.status, { message: error.message, retryable: error.retryable });
      return;
    }
    if (sent) {
      await finish(operation, 'uncertain', {
        message: 'No pudimos confirmar el resultado. Revisa tu historial antes de intentarlo de nuevo.',
        retryable: false,
      });
      return;
    }
    await finish(operation, 'session_error', {
      message: 'No pudimos iniciar tu sesión. Comprueba el servicio e inténtalo de nuevo.',
      retryable: true,
    });
  }
}

async function markRequestStarted(operation) {
  await chrome.storage.session.set({ [OPERATION_KEY]: { ...operation, stage: 'request' } });
}

async function finish(operation, status, details) {
  await chrome.storage.session.set({
    [OPERATION_KEY]: { ...operation, status, finishedAt: Date.now(), ...details },
  });
}

export async function ensureSession() {
  await chrome.storage.local.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' });
  const items = await chrome.storage.local.get(SESSION_KEY);
  const session = items[SESSION_KEY];
  if (session?.access_token && session.expiresAt > Date.now() + 60_000) return session;
  if (session?.refresh_token) return renewSession(session);

  const response = await request('/invitados', { method: 'POST' });
  if (!response.ok) throw new AnalysisFailure('session_error', 'No pudimos iniciar tu sesión. Inténtalo de nuevo.', true);
  return saveSession(response.data);
}

export async function renewSession(session) {
  const response = await request('/sesiones/renovar', {
    method: 'POST', body: JSON.stringify({ refresh_token: session.refresh_token }),
  });
  if (!response.ok) throw new AnalysisFailure('session_error', 'No pudimos iniciar tu sesión. Inténtalo de nuevo.', true);
  return saveSession(response.data, session);
}

async function saveSession(data, previous = null) {
  if (typeof data?.access_token !== 'string' || typeof data?.refresh_token !== 'string') {
    throw new AnalysisFailure('session_error', 'No pudimos iniciar tu sesión. Inténtalo de nuevo.', true);
  }
  const session = {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    usuario_id: data.usuario_id ?? previous?.usuario_id ?? null,
    anonimo: data.anonimo ?? previous?.anonimo ?? true,
    correo: typeof data.correo === 'string' ? data.correo : previous?.correo ?? null,
    expiresAt: Date.now() + Number(data.expires_in ?? 0) * 1000,
  };
  await chrome.storage.local.set({ [SESSION_KEY]: session });
  return session;
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...options.headers },
    signal: AbortSignal.timeout(25_000),
  });
  const data = await response.json().catch(() => null);
  return { ok: response.ok, status: response.status, data };
}
