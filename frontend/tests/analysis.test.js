import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startAnalysis, getAnalysisOperation } from '../src/extension/analysis.js';

function storageArea(initial = {}) {
  const values = { ...initial };
  return {
    values,
    async get(keys) {
      const names = Array.isArray(keys) ? keys : [keys];
      return Object.fromEntries(names.map((key) => [key, values[key]]));
    },
    async set(items) { Object.assign(values, items); },
    async remove(key) { delete values[key]; },
    async setAccessLevel() {},
  };
}

function response(status, data) {
  return { ok: status >= 200 && status < 300, status, async json() { return data; } };
}

async function waitForStatus(status) {
  for (let i = 0; i < 100; i += 1) {
    const operation = await getAnalysisOperation();
    if (operation?.status === status) return operation;
    await new Promise((resolve) => setTimeout(resolve, 1));
  }
  throw new Error(`Operation did not reach ${status}`);
}

test('Analizar inicia una sola solicitud y guarda el resultado recibido', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const session = storageArea({ pendingSelection: { text: 'Texto elegido', url: 'https://ejemplo.test', capturedAt: 1 } });
  const local = storageArea();
  let analysisCalls = 0;
  globalThis.chrome = { storage: { session, local } };
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/invitados')) return response(200, { access_token: 'token', refresh_token: 'refresh', expires_in: 3600 });
    if (url.endsWith('/analisis')) {
      analysisCalls += 1;
      assert.deepEqual(JSON.parse(options.body), { texto: 'Texto elegido', url: 'https://ejemplo.test' });
      return response(200, { id: 'resultado-1', resultados: { bilstm: { estado: 'ok' } } });
    }
    throw new Error(`Unexpected request: ${url}`);
  };
  try {
    const [first, second] = await Promise.all([startAnalysis(), startAnalysis()]);
    assert.equal(first.ok, true);
    assert.equal(first.operation.id, second.operation.id);
    const completed = await waitForStatus('completed');
    assert.equal(completed.result.id, 'resultado-1');
    assert.equal(analysisCalls, 1);
    assert.equal(session.values.pendingSelection, undefined);
    assert.equal(local.values.authSession.access_token, 'token');
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('una validación 422 conserva el texto para seleccionarlo de nuevo', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const session = storageArea({ pendingSelection: { text: 'Corto', url: null, capturedAt: 2 } });
  const local = storageArea();
  globalThis.chrome = { storage: { session, local } };
  globalThis.fetch = async (url) => url.endsWith('/invitados')
    ? response(200, { access_token: 'token', refresh_token: 'refresh', expires_in: 3600 })
    : response(422, { detail: { mensaje: 'El texto es muy corto.', como_corregir: 'Selecciona más contenido.' } });
  try {
    assert.equal((await startAnalysis()).ok, true);
    const rejected = await waitForStatus('validation');
    assert.equal(rejected.message, 'El texto es muy corto.');
    assert.equal(rejected.correction, 'Selecciona más contenido.');
    assert.equal(session.values.pendingSelection.text, 'Corto');
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('una espera sin respuesta queda incierta y no reenvía el texto', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const session = storageArea({ pendingSelection: { text: 'Texto elegido', url: null, capturedAt: 3 } });
  const local = storageArea();
  let analysisCalls = 0;
  globalThis.chrome = { storage: { session, local } };
  globalThis.fetch = async (url) => {
    if (url.endsWith('/invitados')) return response(200, { access_token: 'token', refresh_token: 'refresh', expires_in: 3600 });
    analysisCalls += 1;
    throw new DOMException('Timed out', 'TimeoutError');
  };
  try {
    assert.equal((await startAnalysis()).ok, true);
    const uncertain = await waitForStatus('uncertain');
    assert.equal(uncertain.retryable, false);
    assert.equal((await startAnalysis()).ok, false);
    assert.equal(analysisCalls, 1);
    assert.equal(session.values.pendingSelection.text, 'Texto elegido');
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('un fallo de sesión deja el texto disponible para reintentar', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const session = storageArea({ pendingSelection: { text: 'Texto elegido', url: null, capturedAt: 4 } });
  globalThis.chrome = { storage: { session, local: storageArea() } };
  globalThis.fetch = async () => response(503, { detail: { codigo: 'invitados_no_disponibles' } });
  try {
    assert.equal((await startAnalysis()).ok, true);
    const failed = await waitForStatus('session_error');
    assert.equal(failed.retryable, true);
    assert.equal(session.values.pendingSelection.text, 'Texto elegido');
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('un fallo de guardado no se presenta como resultado completado', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const session = storageArea({ pendingSelection: { text: 'Texto elegido', url: null, capturedAt: 5 } });
  globalThis.chrome = { storage: { session, local: storageArea() } };
  globalThis.fetch = async (url) => url.endsWith('/invitados')
    ? response(200, { access_token: 'token', refresh_token: 'refresh', expires_in: 3600 })
    : response(502, { detail: { codigo: 'supabase_rechazo_operacion' } });
  try {
    assert.equal((await startAnalysis()).ok, true);
    const failed = await waitForStatus('storage_error');
    assert.equal(failed.result, undefined);
    assert.equal(session.values.pendingSelection.text, 'Texto elegido');
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('una operación enviada que perdió su worker se marca incierta', async () => {
  const originalChrome = globalThis.chrome;
  const session = storageArea({ analysisOperation: { id: 'old', status: 'working', stage: 'request', startedAt: Date.now() - 40_000 } });
  globalThis.chrome = { storage: { session, local: storageArea() } };
  try {
    const recovered = await getAnalysisOperation();
    assert.equal(recovered.status, 'uncertain');
    assert.equal(session.values.analysisOperation.status, 'uncertain');
  } finally {
    globalThis.chrome = originalChrome;
  }
});

test('un 401 renueva la sesión una vez antes de repetir la petición', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const session = storageArea({ pendingSelection: { text: 'Texto elegido', url: null, capturedAt: 6 } });
  const local = storageArea({ authSession: { access_token: 'old', refresh_token: 'refresh-old', expiresAt: Date.now() + 3_600_000 } });
  let analysisCalls = 0;
  let renewals = 0;
  globalThis.chrome = { storage: { session, local } };
  globalThis.fetch = async (url) => {
    if (url.endsWith('/sesiones/renovar')) {
      renewals += 1;
      return response(200, { access_token: 'new', refresh_token: 'refresh-new', expires_in: 3600 });
    }
    if (url.endsWith('/analisis')) {
      analysisCalls += 1;
      return analysisCalls === 1
        ? response(401, { detail: { codigo: 'sesion_invalida' } })
        : response(200, { id: 'resultado-2', resultados: { bilstm: { estado: 'ok' } } });
    }
    throw new Error(`Unexpected request: ${url}`);
  };
  try {
    assert.equal((await startAnalysis()).ok, true);
    assert.equal((await waitForStatus('completed')).result.id, 'resultado-2');
    assert.equal(analysisCalls, 2);
    assert.equal(renewals, 1);
    assert.equal(local.values.authSession.access_token, 'new');
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('un fallo inesperado tras el envío no habilita un reenvío automático', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const session = storageArea({ pendingSelection: { text: 'Texto elegido', url: null, capturedAt: 7 } });
  globalThis.chrome = { storage: { session, local: storageArea() } };
  globalThis.fetch = async (url) => url.endsWith('/invitados')
    ? response(200, { access_token: 'token', refresh_token: 'refresh', expires_in: 3600 })
    : response(500, { detail: 'unexpected' });
  try {
    assert.equal((await startAnalysis()).ok, true);
    assert.equal((await waitForStatus('uncertain')).retryable, false);
    assert.equal((await startAnalysis()).ok, false);
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});
