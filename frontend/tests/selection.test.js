import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runInNewContext } from 'node:vm';
import { buildSync } from 'esbuild';
import { fileURLToPath } from 'node:url';

const workerCode = buildSync({
  entryPoints: [fileURLToPath(new URL('../src/extension/service-worker.js', import.meta.url))],
  bundle: true,
  write: false,
  format: 'iife',
  platform: 'browser',
}).outputFiles[0].text;

function createWorker(tab = { id: 3, url: 'https://ejemplo.test/noticia' }) {
  const values = {};
  let listener;
  let injected = false;
  const chrome = {
    runtime: { onMessage: { addListener(callback) { listener = callback; } } },
    tabs: { async query() { return [tab]; } },
    scripting: { async executeScript() { injected = true; } },
    storage: { session: {
      async get(key) { return { [key]: values[key] }; },
      async set(items) { Object.assign(values, items); },
      async remove(key) { delete values[key]; },
    }, local: { async setAccessLevel() {} } },
  };
  runInNewContext(workerCode, { chrome });
  const send = (message, sender = {}) => new Promise((resolve) => listener(message, sender, resolve));
  return { send, values, get injected() { return injected; } };
}

test('captura el texto solo después de iniciar la selección', async () => {
  const worker = createWorker();
  assert.equal((await worker.send({ type: 'SELECTION_CAPTURED', text: 'Fragmento' }, { tab: { id: 3 } })).ok, false);
  assert.equal((await worker.send({ type: 'START_SELECTION' })).ok, true);
  assert.equal(worker.injected, true);
  assert.equal((await worker.send({ type: 'SELECTION_CAPTURED', text: 'Fragmento' }, { tab: { id: 4 } })).ok, false);
  assert.equal((await worker.send({ type: 'SELECTION_CAPTURED', text: 'Fragmento' }, { tab: { id: 3, url: 'https://ejemplo.test/noticia' } })).ok, true);
  const pending = await worker.send({ type: 'GET_PENDING_SELECTION' });
  assert.equal(pending.selection.text, 'Fragmento');
  assert.equal(pending.selection.url, 'https://ejemplo.test/noticia');
  assert.equal(worker.values.selectionTargetTabId, undefined);
});

test('rechaza pestañas que no son páginas web', async () => {
  const worker = createWorker({ id: 5, url: 'chrome://extensions' });
  assert.equal((await worker.send({ type: 'START_SELECTION' })).ok, false);
  assert.equal(worker.injected, false);
});

test('agregar otra selección conserva el texto anterior y lo une al nuevo', async () => {
  const worker = createWorker();
  worker.values.pendingSelection = { text: 'Texto anterior', url: null };
  assert.equal((await worker.send({ type: 'START_SELECTION' })).ok, true);
  assert.equal((await worker.send({ type: 'GET_PENDING_SELECTION' })).selection.text, 'Texto anterior');
  assert.equal((await worker.send({ type: 'SELECTION_CAPTURED', text: 'Texto nuevo' }, { tab: { id: 3, url: 'https://ejemplo.test/noticia' } })).ok, true);
  assert.equal((await worker.send({ type: 'GET_PENDING_SELECTION' })).selection.text, 'Texto anterior\n\nTexto nuevo');
  assert.equal((await worker.send({ type: 'GET_PENDING_SELECTION' })).selection.url, null);
});

test('agrega una nueva selección al borrador editado en el popup', async () => {
  const worker = createWorker();
  assert.equal((await worker.send({ type: 'START_SELECTION' })).ok, true);
  assert.equal((await worker.send({ type: 'SELECTION_CAPTURED', text: 'Primera parte' }, { tab: { id: 3, url: 'https://ejemplo.test/noticia' } })).ok, true);

  worker.values.pendingSelection = { text: 'Texto pegado', url: null, updatedBy: 'popup' };
  assert.equal((await worker.send({ type: 'GET_PENDING_SELECTION' })).selection.text, 'Texto pegado');
  assert.equal((await worker.send({ type: 'START_SELECTION' })).ok, true);
  assert.equal((await worker.send({ type: 'SELECTION_CAPTURED', text: 'Última parte' }, { tab: { id: 3, url: 'https://ejemplo.test/noticia' } })).ok, true);
  assert.equal((await worker.send({ type: 'GET_PENDING_SELECTION' })).selection.text, 'Texto pegado\n\nÚltima parte');
});

test('conserva la fuente solo si los fragmentos vienen de la misma página', async () => {
  const worker = createWorker();
  await worker.send({ type: 'START_SELECTION' });
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Uno' }, { tab: { id: 3, url: 'https://ejemplo.test/noticia' } });
  await worker.send({ type: 'START_SELECTION' });
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Dos' }, { tab: { id: 3, url: 'https://ejemplo.test/noticia' } });
  assert.equal((await worker.send({ type: 'GET_PENDING_SELECTION' })).selection.url, 'https://ejemplo.test/noticia');
  await worker.send({ type: 'START_SELECTION' });
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Tres' }, { tab: { id: 3, url: 'https://otra.test' } });
  assert.equal((await worker.send({ type: 'GET_PENDING_SELECTION' })).selection.url, null);
});
