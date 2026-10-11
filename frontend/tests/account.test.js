import { test } from 'node:test';
import assert from 'node:assert/strict';
import { closeAccountSession, getAccountState } from '../src/extension/account.js';

function storageArea(initial = {}) {
  const values = { ...initial };
  return {
    values,
    async get(keys) {
      const names = Array.isArray(keys) ? keys : [keys];
      return Object.fromEntries(names.map((key) => [key, values[key]]));
    },
    async set(items) { Object.assign(values, items); },
    async remove(keys) { for (const key of Array.isArray(keys) ? keys : [keys]) delete values[key]; },
    async setAccessLevel() {},
  };
}

function response(status, data) {
  return { ok: status >= 200 && status < 300, status, async json() { return data; } };
}

test('P11 distingue invitado, cuenta y confirmación pendiente sin devolver tokens', async () => {
  const originalChrome = globalThis.chrome;
  const local = storageArea({ authSession: { access_token: 'secreto', anonimo: true, expiresAt: Date.now() + 3_600_000 } });
  globalThis.chrome = { storage: { local } };
  try {
    assert.deepEqual(await getAccountState(), { kind: 'guest', email: null });
    local.values.accountPendingConfirmation = { correo: 'persona@ejemplo.org' };
    assert.deepEqual(await getAccountState(), { kind: 'pending_confirmation', email: 'persona@ejemplo.org' });
    local.values.authSession = { access_token: 'secreto', anonimo: false, correo: 'persona@ejemplo.org', expiresAt: Date.now() + 3_600_000 };
    assert.deepEqual(await getAccountState(), { kind: 'account', email: 'persona@ejemplo.org' });
  } finally { globalThis.chrome = originalChrome; }
});

test('P11 conserva la cuenta al renovar tokens sin datos de tipo de sesión', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const local = storageArea({ authSession: {
    access_token: 'anterior', refresh_token: 'refresco', anonimo: false,
    correo: 'persona@ejemplo.org', expiresAt: Date.now() - 1000,
  } });
  globalThis.chrome = { storage: { local } };
  globalThis.fetch = async (url) => {
    assert.ok(url.endsWith('/sesiones/renovar'));
    return response(200, { access_token: 'nuevo', refresh_token: 'nuevo-refresco', expires_in: 3600 });
  };
  try {
    assert.deepEqual(await getAccountState(), { kind: 'account', email: 'persona@ejemplo.org' });
    assert.equal(local.values.authSession.anonimo, false);
    assert.equal(local.values.authSession.access_token, 'nuevo');
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('P11 conserva la sesión recuperable si falla la renovación', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const session = { access_token: 'anterior', refresh_token: 'refresco', anonimo: true, expiresAt: Date.now() - 1000 };
  const local = storageArea({ authSession: session });
  globalThis.chrome = { storage: { local } };
  globalThis.fetch = async () => response(503, {});
  try {
    assert.deepEqual(await getAccountState(), { kind: 'expired', email: null });
    assert.equal(local.values.authSession, session);
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('P11 solo limpia sesión y selección tras cierre confirmado', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const local = storageArea({ authSession: { access_token: 'actual', refresh_token: 'refresco', anonimo: false, expiresAt: Date.now() + 3_600_000 } });
  const session = storageArea({ analysisOperation: { status: 'completed' }, pendingSelection: { text: 'texto' } });
  let confirmed = false;
  globalThis.chrome = { storage: { local, session } };
  globalThis.fetch = async (url, options) => {
    assert.ok(url.endsWith('/sesiones/cerrar'));
    assert.equal(options.method, 'POST');
    assert.equal(options.headers.Authorization, 'Bearer actual');
    return response(200, { cerrada: confirmed });
  };
  try {
    await assert.rejects(closeAccountSession(), /confirmar/);
    assert.ok(local.values.authSession);
    assert.ok(session.values.analysisOperation);
    confirmed = true;
    assert.deepEqual(await closeAccountSession(), { signedOut: true });
    assert.equal(local.values.authSession, undefined);
    assert.equal(session.values.analysisOperation, undefined);
    assert.equal(session.values.pendingSelection, undefined);
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('P11 no cierra sesión mientras hay un análisis activo', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  globalThis.chrome = { storage: {
    local: storageArea({ authSession: { access_token: 'actual', anonimo: false, expiresAt: Date.now() + 3_600_000 } }),
    session: storageArea({ analysisOperation: { status: 'working', stage: 'request', startedAt: Date.now() } }),
  } };
  globalThis.fetch = async () => { throw new Error('No debe enviar el cierre'); };
  try { await assert.rejects(closeAccountSession(), /termine el análisis/); }
  finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});
