import { test } from 'node:test';
import assert from 'node:assert/strict';
import { sendExtensionMessage } from '../src/popup/extension-message.js';

test('acepta la respuesta por callback sin exigir una promesa de Chrome', async () => {
  const original = globalThis.chrome;
  globalThis.chrome = {
    runtime: {
      lastError: null,
      sendMessage(message, callback) { callback({ ok: message.type === 'PING' }); },
    },
  };
  try {
    assert.deepEqual(await sendExtensionMessage({ type: 'PING' }), { ok: true });
  } finally {
    globalThis.chrome = original;
  }
});

test('convierte el error de mensajería en rechazo controlado', async () => {
  const original = globalThis.chrome;
  globalThis.chrome = {
    runtime: {
      lastError: { message: 'Worker unavailable' },
      sendMessage(_message, callback) { callback(); },
    },
  };
  try {
    await assert.rejects(sendExtensionMessage({ type: 'PING' }), /Worker unavailable/);
  } finally {
    globalThis.chrome = original;
  }
});
