import { test } from 'node:test';
import assert from 'node:assert/strict';
import { getPublishedMetrics } from '../src/extension/metrics.js';
import { presentMetrics } from '../src/popup/metrics-presentation.js';

function response(status, data) {
  return { ok: status >= 200 && status < 300, async json() { return data; } };
}

test('P09 consulta las métricas públicas sin sesión y conserva los datos recibidos', async () => {
  const originalFetch = globalThis.fetch;
  const payload = { modelo: 'bilstm', version: 'v1', evaluaciones: [{ conjunto: 'Prueba', exactitud: 0.86 }] };
  globalThis.fetch = async (url, options) => {
    assert.equal(url, 'http://127.0.0.1:8000/metricas');
    assert.deepEqual(options.headers, { Accept: 'application/json' });
    return response(200, payload);
  };
  try { assert.deepEqual(await getPublishedMetrics(), payload); }
  finally { globalThis.fetch = originalFetch; }
});

test('P09 rechaza errores y formatos inesperados sin mostrar cifras de ejemplo', async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => response(503, {});
    await assert.rejects(getPublishedMetrics(), /cargar/);
    globalThis.fetch = async () => response(200, { modelo: 'bilstm' });
    await assert.rejects(getPublishedMetrics(), /no reconocida/);
  } finally { globalThis.fetch = originalFetch; }
});

test('P09 muestra las medidas válidas de cada conjunto, incluidos los valores cero', () => {
  const shown = presentMetrics({
    modelo: 'bilstm', version: 'v1', limitaciones: ['Evaluación local.'],
    evaluaciones: [
      { conjunto: 'Prueba', n: 1200, fuente: 'Conjunto publicado', exactitud: 0.86, f1_macro: 0.84, precision_falsa: 0, recall_falsa: 1, f1_falsa: 0.72 },
      { conjunto: 'Otro conjunto', n: 0, exactitud: 0.5 },
    ],
  });
  assert.equal(shown.model, 'BiLSTM');
  assert.equal(shown.version, 'v1');
  assert.deepEqual(shown.limitations, ['Evaluación local.']);
  assert.equal(shown.evaluations.length, 2);
  assert.equal(shown.evaluations[0].examples, '1,200');
  assert.deepEqual(shown.evaluations[0].main, [
    { label: 'Exactitud', percentage: '86 %' },
    { label: 'F1 macro', percentage: '84 %' },
  ]);
  assert.equal(shown.evaluations[0].extra[0].percentage, '0 %');
  assert.equal(shown.evaluations[0].extra[1].percentage, '100 %');
  assert.equal(shown.evaluations[1].examples, '0');
  assert.equal(shown.evaluations[1].main.length, 1);
});

test('P09 omite medidas inválidas y limitaciones ausentes', () => {
  const shown = presentMetrics({
    evaluaciones: [{ conjunto: 'Prueba', n: -2, exactitud: null, f1_macro: 1.5, precision_falsa: '0.5' }],
  });
  assert.equal(shown.model, null);
  assert.equal(shown.version, null);
  assert.deepEqual(shown.limitations, []);
  assert.equal(shown.evaluations[0].examples, null);
  assert.deepEqual(shown.evaluations[0].main, []);
  assert.deepEqual(shown.evaluations[0].extra, []);
});
