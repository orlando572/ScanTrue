import { test } from 'node:test';
import assert from 'node:assert/strict';
import { presentServices } from '../src/popup/service-presentation.js';

const healthy = { estado: 'ok', modelos: { bilstm: true, mbert: true }, supabase_configurado: true, blockchain: { configurada: true, conectada: true } };
const states = (list) => list.map((service) => service.state);

test('todo funcionando: cada servicio con su propio color', () => {
  const shown = presentServices(healthy, 'available');
  assert.deepEqual(states(shown), ['ok', 'ok', 'ok', 'ok']);
  assert.equal(new Set(shown.map((service) => service.color)).size, 4);
  assert.ok(shown.every((service) => !['#FF4A3D', '#FFB21E'].includes(service.color)));
  assert.equal(shown[1].label, 'Modelo mBERT: funcionando');
});

test('mBERT caído se pinta en rojo y el resto sigue con su color', () => {
  const shown = presentServices({ ...healthy, estado: 'degradado', modelos: { bilstm: true, mbert: false } }, 'degraded');
  assert.deepEqual(states(shown), ['ok', 'down', 'ok', 'ok']);
  assert.equal(shown[1].color, '#FF4A3D');
});

test('blockchain configurada sin conexión falla en parte (ámbar)', () => {
  const shown = presentServices({ ...healthy, blockchain: { configurada: true, conectada: false } }, 'available');
  assert.equal(shown[3].state, 'partial');
  assert.equal(shown[3].color, '#FFB21E');
  assert.equal(presentServices({ ...healthy, blockchain: { configurada: false, conectada: false } }, 'available')[3].state, 'down');
});

test('API caída: las cuatro en rojo; comprobando: apagadas', () => {
  assert.deepEqual(states(presentServices(null, 'unavailable')), ['down', 'down', 'down', 'down']);
  const checking = presentServices(null, 'checking');
  assert.deepEqual(states(checking), ['checking', 'checking', 'checking', 'checking']);
  assert.ok(checking.every((service) => service.color === null));
});

test('sin datos de un servicio se marca en ámbar, no como funcionando', () => {
  assert.deepEqual(states(presentServices({ estado: 'ok' }, 'available')), ['unknown', 'unknown', 'unknown', 'unknown']);
});
