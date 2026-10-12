import { test } from 'node:test';
import assert from 'node:assert/strict';
import { deleteHistoryDetail, getHistoryDetail, listHistory } from '../src/extension/history.js';

function storageArea(initial = {}) {
  const values = { ...initial };
  return {
    values,
    async get(key) { return { [key]: values[key] }; },
    async set(items) { Object.assign(values, items); },
    async setAccessLevel() {},
  };
}

function response(status, data) {
  return { ok: status >= 200 && status < 300, status, async json() { return data; } };
}

test('P07 consulta solo el historial de la sesión activa y pagina por offset', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const local = storageArea({ authSession: { access_token: 'actual', refresh_token: 'refresh', expiresAt: Date.now() + 3_600_000 } });
  globalThis.chrome = { storage: { local } };
  globalThis.fetch = async (url, options) => {
    assert.equal(url, 'http://127.0.0.1:8000/analisis?limit=20&offset=20');
    assert.equal(options.headers.Authorization, 'Bearer actual');
    return response(200, { analisis: [{ id: 'a21' }], total: 21 });
  };
  try {
    assert.deepEqual(await listHistory(20), { items: [{ id: 'a21' }], hasMore: false, nextOffset: 21 });
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('P07 renueva un token rechazado una vez y conserva la sesión guardada', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const local = storageArea({ authSession: { access_token: 'anterior', refresh_token: 'refresh', expiresAt: Date.now() + 3_600_000 } });
  let listCalls = 0;
  globalThis.chrome = { storage: { local } };
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/sesiones/renovar')) return response(200, { access_token: 'nuevo', refresh_token: 'nuevo-refresh', expires_in: 3600 });
    listCalls += 1;
    return options.headers.Authorization === 'Bearer anterior' ? response(401, {}) : response(200, [{ id: 'a1' }]);
  };
  try {
    assert.deepEqual(await listHistory(), { items: [{ id: 'a1' }], hasMore: false, nextOffset: 1 });
    assert.equal(listCalls, 2);
    assert.equal(local.values.authSession.access_token, 'nuevo');
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('P07 rechaza un formato inesperado sin simular un historial vacío', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  globalThis.chrome = { storage: { local: storageArea({ authSession: { access_token: 'actual', expiresAt: Date.now() + 3_600_000 } }) } };
  globalThis.fetch = async () => response(200, { sin_lista: [] });
  try { await assert.rejects(listHistory(), /no reconocida/); }
  finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('P08 consulta el detalle guardado por id y distingue un 404', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  globalThis.chrome = { storage: { local: storageArea({ authSession: { access_token: 'actual', expiresAt: Date.now() + 3_600_000 } }) } };
  globalThis.fetch = async (url, options) => {
    assert.equal(options.method, 'GET');
    assert.equal(options.headers.Authorization, 'Bearer actual');
    return url.endsWith('/analisis/guardado')
      ? response(200, { id: 'guardado', texto: null, resultado_unificado: { probabilidad_falsa: 0.73 } })
      : response(404, {});
  };
  try {
    assert.deepEqual(await getHistoryDetail('guardado'), {
      found: true, item: { id: 'guardado', texto: null, resultado_unificado: { probabilidad_falsa: 0.73 } },
    });
    assert.deepEqual(await getHistoryDetail('inexistente'), { found: false, item: null });
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('P08 solo confirma una eliminación si la API responde eliminado true', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  globalThis.chrome = { storage: { local: storageArea({ authSession: { access_token: 'actual', expiresAt: Date.now() + 3_600_000 } }) } };
  let confirmed = false;
  globalThis.fetch = async (url, options) => {
    assert.equal(url, 'http://127.0.0.1:8000/analisis/guardado');
    assert.equal(options.method, 'DELETE');
    return response(200, { eliminado: confirmed });
  };
  try {
    await assert.rejects(deleteHistoryDetail('guardado'), /confirmar/);
    confirmed = true;
    assert.deepEqual(await deleteHistoryDetail('guardado'), { deleted: true });
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('P08 no acepta el detalle de otro registro', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  globalThis.chrome = { storage: { local: storageArea({ authSession: { access_token: 'actual', expiresAt: Date.now() + 3_600_000 } }) } };
  globalThis.fetch = async () => response(200, { id: 'otro' });
  try { await assert.rejects(getHistoryDetail('guardado'), /no reconocido/); }
  finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});
