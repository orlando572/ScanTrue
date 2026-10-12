import { test } from 'node:test';
import assert from 'node:assert/strict';
import { closeAccountSession, getAccountState, loginAccount, registerAccount } from '../src/extension/account.js';

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

test('registro pendiente conserva la sesión invitada y guarda el correo pendiente', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const guest = { access_token: 'guest-token', refresh_token: 'guest-refresh', anonimo: true, expiresAt: Date.now() + 3_600_000 };
  const local = storageArea({ authSession: guest });
  globalThis.chrome = { storage: { local, session: storageArea() } };
  globalThis.fetch = async (url, options) => {
    assert.ok(url.endsWith('/cuentas'));
    assert.equal(options.headers.Authorization, 'Bearer guest-token');
    assert.deepEqual(JSON.parse(options.body), { correo: 'persona@ejemplo.org', contrasena: 'clave-segura' });
    return response(200, { estado: 'pendiente_confirmacion', sesion: null, registros_incorporados: 0 });
  };
  try {
    assert.deepEqual(await registerAccount('persona@ejemplo.org', 'clave-segura'), {
      kind: 'pending_confirmation', email: 'persona@ejemplo.org',
    });
    assert.equal(local.values.authSession, guest);
    assert.deepEqual(local.values.accountPendingConfirmation, { correo: 'persona@ejemplo.org' });
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('inicio de sesión transfiere historial invitado y cambia tokens solo tras éxito', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const guest = { access_token: 'guest-token', refresh_token: 'guest-refresh', anonimo: true, expiresAt: Date.now() + 3_600_000 };
  const local = storageArea({ authSession: guest, accountPendingConfirmation: { correo: 'persona@ejemplo.org' } });
  const session = storageArea({ pendingSelection: { text: 'texto previo' } });
  globalThis.chrome = { storage: { local, session } };
  let validCredentials = false;
  globalThis.fetch = async (url, options) => {
    assert.ok(url.endsWith('/sesiones'));
    assert.equal(options.headers['X-Guest-Token'], 'guest-token');
    assert.deepEqual(JSON.parse(options.body), { correo: 'persona@ejemplo.org', contrasena: 'clave-segura' });
    return validCredentials
      ? response(200, { sesion: { usuario_id: 'account-id', anonimo: false, access_token: 'account-token', refresh_token: 'account-refresh', expires_in: 3600 }, registros_incorporados: 2 })
      : response(401, { detail: { codigo: 'credenciales_invalidas', mensaje: 'Correo o contraseña incorrectos.' } });
  };
  try {
    await assert.rejects(loginAccount('persona@ejemplo.org', 'clave-segura'), /Correo o contraseña incorrectos/);
    assert.equal(local.values.authSession, guest);
    assert.ok(local.values.accountPendingConfirmation);
    validCredentials = true;
    assert.deepEqual(await loginAccount('persona@ejemplo.org', 'clave-segura'), {
      kind: 'account', email: 'persona@ejemplo.org', transferred: 2, guestHistorySkipped: false,
    });
    assert.equal(local.values.authSession.access_token, 'account-token');
    assert.equal(local.values.authSession.anonimo, false);
    assert.equal(local.values.accountPendingConfirmation, undefined);
    assert.equal(session.values.pendingSelection, undefined);
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});

test('registro activo y sesión invitada vencida no pierden el historial', async () => {
  const originalChrome = globalThis.chrome;
  const originalFetch = globalThis.fetch;
  const guest = { access_token: 'guest-token', refresh_token: 'guest-refresh', anonimo: true, expiresAt: Date.now() + 3_600_000 };
  const local = storageArea({ authSession: guest });
  globalThis.chrome = { storage: { local, session: storageArea() } };
  globalThis.fetch = async (url) => {
    if (url.endsWith('/cuentas')) return response(200, {
      estado: 'activa', sesion: { usuario_id: 'account-id', anonimo: false, access_token: 'account-token', refresh_token: 'account-refresh', expires_in: 3600 }, registros_incorporados: 1,
    });
    throw new Error('No se debe llamar a otra ruta');
  };
  try {
    assert.deepEqual(await registerAccount('persona@ejemplo.org', 'clave-segura'), {
      kind: 'account', email: 'persona@ejemplo.org', transferred: 1,
    });
    assert.equal(local.values.authSession.access_token, 'account-token');
    local.values.authSession = { ...guest, expiresAt: Date.now() - 1000 };
    globalThis.fetch = async () => response(401, { detail: { codigo: 'sesion_invalida' } });
    await assert.rejects(loginAccount('persona@ejemplo.org', 'clave-segura'), /renovar tu sesión invitada/);
    assert.equal(local.values.authSession.access_token, 'guest-token');
    globalThis.fetch = async (url, options) => {
      assert.ok(url.endsWith('/sesiones'));
      assert.equal(options.headers['X-Guest-Token'], undefined);
      return response(200, {
        sesion: { usuario_id: 'account-id', anonimo: false, access_token: 'new-account-token', refresh_token: 'new-account-refresh', expires_in: 3600 },
        registros_incorporados: 0,
      });
    };
    assert.deepEqual(await loginAccount('persona@ejemplo.org', 'clave-segura', true), {
      kind: 'account', email: 'persona@ejemplo.org', transferred: 0, guestHistorySkipped: true,
    });
  } finally {
    globalThis.chrome = originalChrome;
    globalThis.fetch = originalFetch;
  }
});
