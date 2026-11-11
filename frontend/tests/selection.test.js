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
  const toTabs = [];
  const tabEvents = {};
  let listener;
  let injected = false;
  const chrome = {
    runtime: { onMessage: { addListener(callback) { listener = callback; } }, getManifest: () => ({ action: {} }) },
    tabs: {
      async query() { return [tab]; },
      async sendMessage(tabId, message) { toTabs.push({ tabId, ...message }); },
      onRemoved: { addListener(callback) { tabEvents.removed = callback; } },
      onUpdated: { addListener(callback) { tabEvents.updated = callback; } },
    },
    scripting: { async executeScript() { injected = true; } },
    sidePanel: { async setPanelBehavior() {} },
    storage: { session: {
      async get(keys) { return Object.fromEntries([keys].flat().map((key) => [key, values[key]])); },
      async set(items) { Object.assign(values, items); },
      async remove(key) { delete values[key]; },
    }, local: { async setAccessLevel() {} } },
  };
  runInNewContext(workerCode, { chrome, crypto: globalThis.crypto, URL });
  const send = (message, sender = {}) => new Promise((resolve) => listener(message, sender, resolve));
  return { send, values, toTabs, tabEvents, get injected() { return injected; } };
}

const page = { tab: { id: 3, url: 'https://ejemplo.test/noticia' } };
// Los objetos creados dentro del contexto vm tienen otros prototipos: se comparan como JSON.
const plain = (value) => JSON.parse(JSON.stringify(value));

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
  // El modo selección sigue activo hasta que el usuario lo termina.
  assert.equal(pending.selecting, true);
  assert.equal(worker.values.selectionTargetTabId, 3);
});

test('rechaza pestañas que no son páginas web', async () => {
  const worker = createWorker({ id: 5, url: 'chrome://extensions' });
  const response = await worker.send({ type: 'START_SELECTION' });
  assert.equal(response.ok, false);
  assert.match(response.error, /no permite seleccionar texto/);
  assert.equal(worker.injected, false);
});

test('sin permiso para la página pide aceptar el permiso', async () => {
  const worker = createWorker({ id: 6 });
  const response = await worker.send({ type: 'START_SELECTION' });
  assert.equal(response.ok, false);
  assert.match(response.error, /no tiene permiso/);
  assert.equal(worker.injected, false);
  assert.equal(worker.values.selectionTargetTabId, undefined);
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

test('la fuente ignora el ancla y los parámetros de la misma página', async () => {
  const worker = createWorker();
  await worker.send({ type: 'START_SELECTION' });
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Uno' }, { tab: { id: 3, url: 'https://ejemplo.test/noticia' } });
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Dos' }, { tab: { id: 3, url: 'https://ejemplo.test/noticia?utm=x#comentarios' } });
  assert.equal((await worker.send({ type: 'GET_PENDING_SELECTION' })).selection.url, 'https://ejemplo.test/noticia');
});

test('tras vaciar la selección, el siguiente fragmento vuelve a tener fuente', async () => {
  const worker = createWorker();
  await worker.send({ type: 'START_SELECTION' });
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Uno' }, { tab: { id: 3, url: 'https://otra.test/a' } });
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Dos' }, { tab: { id: 3, url: 'https://ejemplo.test/b' } });
  assert.equal((await worker.send({ type: 'GET_PENDING_SELECTION' })).selection.url, null);
  await worker.send({ type: 'CLEAR_FRAGMENTS' });
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Tres' }, { tab: { id: 3, url: 'https://ejemplo.test/noticia' } });
  assert.equal((await worker.send({ type: 'GET_PENDING_SELECTION' })).selection.url, 'https://ejemplo.test/noticia');
});

test('sin permiso sobre la pestaña usa la URL de la ventana que envió el fragmento', async () => {
  const worker = createWorker();
  await worker.send({ type: 'START_SELECTION' });
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Uno' }, { tab: { id: 3 }, frameId: 0, url: 'https://ejemplo.test/noticia' });
  assert.equal((await worker.send({ type: 'GET_PENDING_SELECTION' })).selection.url, 'https://ejemplo.test/noticia');
});

test('acumula fragmentos en modo continuo y los quita por separado', async () => {
  const worker = createWorker();
  await worker.send({ type: 'START_SELECTION' });
  assert.ok(worker.toTabs.some((message) => message.type === 'SCANTRUE_START'));
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Titular', id: 'f1' }, page);
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Primer párrafo', id: 'f2' }, page);
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Segundo párrafo', id: 'f3' }, page);
  let selection = (await worker.send({ type: 'GET_PENDING_SELECTION' })).selection;
  assert.deepEqual(plain(selection.fragments.map((fragment) => fragment.id)), ['f1', 'f2', 'f3']);
  assert.equal(selection.text, 'Titular\n\nPrimer párrafo\n\nSegundo párrafo');
  assert.deepEqual(worker.toTabs.at(-1), { tabId: 3, type: 'SCANTRUE_SYNC', count: 3, words: 5 });

  const removed = await worker.send({ type: 'REMOVE_FRAGMENT', id: 'f2' });
  assert.equal(removed.ok, true);
  assert.equal(removed.selection.text, 'Titular\n\nSegundo párrafo');
  assert.ok(worker.toTabs.some((message) => message.type === 'SCANTRUE_REMOVE' && message.id === 'f2'));
  assert.equal(worker.values.pendingSelection.updatedBy, 'worker');
});

test('una página no puede quitar fragmentos marcados en otra pestaña', async () => {
  const worker = createWorker();
  await worker.send({ type: 'START_SELECTION' });
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Fragmento', id: 'f1' }, page);
  assert.equal((await worker.send({ type: 'REMOVE_FRAGMENT', id: 'f1' }, { tab: { id: 9 } })).ok, false);
  assert.equal((await worker.send({ type: 'REMOVE_FRAGMENT', id: 'f1' }, page)).ok, true);
});

test('terminar la selección cierra el modo y avisa a la página', async () => {
  const worker = createWorker();
  await worker.send({ type: 'START_SELECTION' });
  assert.equal((await worker.send({ type: 'STOP_SELECTION' }, { tab: { id: 9 } })).ok, false);
  assert.equal((await worker.send({ type: 'STOP_SELECTION' })).ok, true);
  assert.equal(worker.values.selectionTargetTabId, undefined);
  assert.ok(worker.toTabs.some((message) => message.type === 'SCANTRUE_STOP'));
  assert.equal((await worker.send({ type: 'SELECTION_CAPTURED', text: 'Tarde' }, page)).ok, false);
});

test('vaciar quita todos los fragmentos', async () => {
  const worker = createWorker();
  await worker.send({ type: 'START_SELECTION' });
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Uno', id: 'f1' }, page);
  assert.equal((await worker.send({ type: 'CLEAR_FRAGMENTS' }, page)).ok, true);
  const selection = (await worker.send({ type: 'GET_PENDING_SELECTION' })).selection;
  assert.deepEqual(plain([selection.fragments, selection.text]), [[], '']);
  assert.ok(worker.toTabs.some((message) => message.type === 'SCANTRUE_CLEAR'));
});

test('una selección antigua sin fragmentos se conserva como el primero', async () => {
  const worker = createWorker();
  worker.values.pendingSelection = { text: 'Texto anterior', url: null };
  await worker.send({ type: 'START_SELECTION' });
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Texto nuevo', id: 'f1' }, page);
  const selection = (await worker.send({ type: 'GET_PENDING_SELECTION' })).selection;
  assert.deepEqual(plain(selection.fragments.map((fragment) => fragment.text)), ['Texto anterior', 'Texto nuevo']);
});

test('recargar o cerrar la pestaña termina el modo selección', async () => {
  const worker = createWorker();
  await worker.send({ type: 'START_SELECTION' });
  worker.tabEvents.updated(9, { status: 'loading' });
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(worker.values.selectionTargetTabId, 3);
  worker.tabEvents.updated(3, { title: 'Otro título' });
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(worker.values.selectionTargetTabId, 3);
  worker.tabEvents.updated(3, { status: 'loading' });
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(worker.values.selectionTargetTabId, undefined);

  await worker.send({ type: 'START_SELECTION' });
  worker.tabEvents.removed(3);
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(worker.values.selectionTargetTabId, undefined);
});

test('quitar un fragmento que ya no existe no es un error y limpia el resaltado huérfano', async () => {
  const worker = createWorker();
  await worker.send({ type: 'START_SELECTION' });
  await worker.send({ type: 'SELECTION_CAPTURED', text: 'Sigue aquí', id: 'f1' }, page);
  const fromPanel = await worker.send({ type: 'REMOVE_FRAGMENT', id: 'desaparecido' });
  assert.equal(fromPanel.ok, true);
  assert.equal(fromPanel.selection.text, 'Sigue aquí');
  const fromPage = await worker.send({ type: 'REMOVE_FRAGMENT', id: 'huerfano' }, page);
  assert.equal(fromPage.ok, true);
  assert.ok(worker.toTabs.some((message) => message.type === 'SCANTRUE_REMOVE' && message.id === 'huerfano' && message.tabId === 3));
});

test('quitar un fragmento sin selección guardada devuelve una selección vacía', async () => {
  const worker = createWorker();
  const response = await worker.send({ type: 'REMOVE_FRAGMENT', id: 'f1' });
  assert.equal(response.ok, true);
  assert.equal(response.selection.text, '');
});
