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

test('P09 consulta las pruebas de mBERT por separado', async () => {
  const originalFetch = globalThis.fetch;
  const payload = { modelo: 'mbert', evaluaciones: [{ conjunto: 'prueba_bilstm_filtrada', exactitud: 0.94, f1_macro: 0.93 }] };
  globalThis.fetch = async (url, options) => {
    assert.equal(url, 'http://127.0.0.1:8000/metricas?modelo=mbert');
    assert.deepEqual(options.headers, { Accept: 'application/json' });
    return response(200, payload);
  };
  try {
    assert.deepEqual(await getPublishedMetrics('mbert'), payload);
    const shown = presentMetrics(payload);
    assert.equal(shown.model, 'mBERT');
    assert.equal(shown.evaluations[0].name, 'Prueba');
    assert.equal(shown.evaluations[0].accuracy, '94 %');
    assert.equal(shown.evaluations[0].f1, '93 %');
  } finally { globalThis.fetch = originalFetch; }
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

test('P09 muestra aciertos, F1 y tamaño de cada prueba', () => {
  const shown = presentMetrics({
    modelo: 'bilstm', version: 'v1', limitaciones: ['Evaluación local.'],
    evaluaciones: [
      { conjunto: 'Prueba', n: 1200, fuente: 'Conjunto publicado', exactitud: 0.86, f1_macro: 0.84, precision_falsa: 0, recall_falsa: 1, f1_falsa: 0.72 },
      { conjunto: 'Otro conjunto', n: 0, exactitud: 0 },
    ],
  });
  assert.equal(shown.model, 'BiLSTM');
  assert.equal('version' in shown, false);
  assert.deepEqual(shown.limitations, ['Evaluación local.']);
  assert.equal(shown.evaluations.length, 2);
  assert.equal(shown.evaluations[0].examples, '1,200');
  assert.equal(shown.evaluations[0].accuracy, '86 %');
  assert.equal(shown.evaluations[0].f1, '84 %');
  assert.equal(shown.evaluations[0].sourceName, 'Conjunto publicado');
  assert.equal('main' in shown.evaluations[0], false);
  assert.equal('extra' in shown.evaluations[0], false);
  assert.equal(shown.evaluations[1].examples, '0');
  assert.equal(shown.evaluations[1].accuracy, '0 %');
  assert.equal(shown.evaluations[1].f1, null);
});

test('P09 acorta fuentes web sin perder su nombre original', () => {
  const shown = presentMetrics({ evaluaciones: [{ fuente: 'https://www.ejemplo.org/datos/prueba-2026.csv', exactitud: 0.8 }] });
  assert.equal(shown.evaluations[0].source, 'https://www.ejemplo.org/datos/prueba-2026.csv');
  assert.equal(shown.evaluations[0].sourceName, 'ejemplo.org');
});

test('P09 omite aciertos inválidos y datos ausentes', () => {
  const shown = presentMetrics({
    evaluaciones: [{ conjunto: 'Prueba', n: -2, exactitud: null, f1_macro: 1.5, precision_falsa: '0.5' }],
  });
  assert.equal(shown.model, null);
  assert.deepEqual(shown.limitations, []);
  assert.equal(shown.evaluations[0].examples, null);
  assert.equal(shown.evaluations[0].accuracy, null);
  assert.equal(shown.evaluations[0].f1, null);
  assert.equal(shown.evaluations[0].source, null);
  assert.equal(shown.evaluations[0].sourceName, null);
});
