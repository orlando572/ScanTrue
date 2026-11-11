import { test } from 'node:test';
import assert from 'node:assert/strict';
import { presentInsights, presentResult, presentResultLevel } from '../src/popup/result-presentation.js';

test('P05 muestra el unificado recibido', () => {
  assert.deepEqual(presentResult({
    resultado_unificado: { probabilidad_falsa: 0.73, modelos_utilizados: ['bilstm', 'mbert'] },
    comparacion: 'coinciden',
    resultados: { bilstm: { estado: 'ok' }, mbert: { estado: 'ok' } },
  }), {
    percentage: '73 %',
    level: { value: 73, label: 'Probablemente falso', tone: 'high', icon: 'alert' },
    source: 'Resultado combinado de dos modelos',
    hasBreakdown: true,
  });
});

test('P05 indica un solo modelo', () => {
  const displayed = presentResult({
    resultado_unificado: { probabilidad_falsa: 0, modelos_utilizados: ['bilstm'] },
    comparacion: 'discrepan',
    resultados: { bilstm: { estado: 'ok' }, mbert: { estado: 'no_disponible' } },
  });
  assert.equal(displayed.percentage, '0 %');
  assert.deepEqual(displayed.level, { value: 0, label: 'Muy probablemente verdadero', tone: 'very-low', icon: 'check-double' });
  assert.equal(displayed.source, 'Resultado basado en un modelo');
  assert.equal(Object.hasOwn(displayed, 'comparison'), false);
  assert.equal(displayed.hasBreakdown, true);
});

test('P05 admite el extremo superior', () => {
  const displayed = presentResult({
    resultado_unificado: { probabilidad_falsa: 1, modelos_utilizados: ['bilstm', 'mbert'] },
    comparacion: 'discrepan',
  });
  assert.equal(displayed.percentage, '100 %');
  assert.deepEqual(displayed.level, { value: 100, label: 'Muy probablemente falso', tone: 'very-high', icon: 'cross' });
  assert.equal(Object.hasOwn(displayed, 'comparison'), false);
  assert.equal(displayed.hasBreakdown, false);
});

test('P05 no reemplaza un unificado ausente o inválido por salidas individuales', () => {
  for (const probability of [undefined, null, -0.1, 1.1, NaN, '0.9']) {
    const displayed = presentResult({
      resultado_unificado: { probabilidad_falsa: probability, modelos_utilizados: ['bilstm'] },
      resultados: { bilstm: { estado: 'ok', probabilidad_falsa: 0.9 } },
    });
    assert.equal(displayed.percentage, null);
    assert.equal(displayed.level, null);
    assert.equal(displayed.hasBreakdown, true);
  }
  assert.equal(presentResult(null).hasBreakdown, false);
});

test('P05 asigna los cinco niveles según el porcentaje visible', () => {
  const expected = [
    [0, 'very-low'], [20, 'very-low'],
    [21, 'low'], [40, 'low'],
    [41, 'middle'], [60, 'middle'],
    [61, 'high'], [80, 'high'],
    [81, 'very-high'], [100, 'very-high'],
  ];
  for (const [percent, tone] of expected) {
    assert.equal(presentResultLevel(percent / 100).tone, tone, `${percent} %`);
  }
  assert.deepEqual(presentResultLevel(0.405), { value: 41, label: 'Resultado incierto', tone: 'middle', icon: 'question' });
  assert.deepEqual(presentResultLevel(0.404), { value: 40, label: 'Probablemente verdadero', tone: 'low', icon: 'check' });
});

const ok = (clase, probabilidad_falsa) => ({ estado: 'ok', clase, probabilidad_falsa, tokens_leidos: 150 });

test('P05 sitúa los modelos en el espectro y resume que coinciden', () => {
  const insights = presentInsights({
    resultados: { bilstm: ok('real', 0.25), mbert: ok('real', 0.12) },
    comparacion: 'coinciden',
    estado_blockchain: 'pendiente',
    nota: ' Salida experimental. ',
  }, '  Uno dos tres\ncuatro.  ', 'https://www.eltiempo.com/politica/nota?utm=x');
  assert.deepEqual(insights.markers, [
    { key: 'bilstm', name: 'BiLSTM', value: 25 },
    { key: 'mbert', name: 'BETO', value: 12 },
  ]);
  assert.deepEqual(insights.consensus, { state: 'agree', title: 'Los modelos coinciden' });
  assert.deepEqual(insights.reading, {
    words: '4 palabras',
    domain: 'eltiempo.com',
    url: 'https://www.eltiempo.com/politica/nota?utm=x',
    snippet: 'Uno dos tres cuatro.',
    text: 'Uno dos tres\ncuatro.',
  });
  assert.equal(Object.hasOwn(insights, 'chain'), false);
  assert.equal(insights.note, 'Salida experimental.');
});

test('P05 resume que los modelos discrepan', () => {
  const insights = presentInsights({ resultados: { bilstm: ok('falsa', 0.7), mbert: ok('real', 0.2) }, comparacion: 'discrepan' });
  assert.deepEqual(insights.consensus, { state: 'disagree', title: 'Los modelos no coinciden' });
});

test('P05 indica qué modelo respondió cuando falta el otro', () => {
  const insights = presentInsights({
    resultados: { bilstm: ok('real', 0.3), mbert: { estado: 'no_disponible' } },
    comparacion: 'no_disponible',
  }, 'una');
  assert.deepEqual(insights.markers, [{ key: 'bilstm', name: 'BiLSTM', value: 30 }]);
  assert.deepEqual(insights.consensus, { state: 'single', model: 'bilstm', title: 'Solo respondió BiLSTM' });
  assert.equal(insights.reading.words, '1 palabra');
  assert.equal(insights.reading.domain, null);
});

test('P05 recorta el fragmento sin partir palabras', () => {
  const text = 'palabra '.repeat(60);
  const { snippet } = presentInsights({ resultados: {} }, text).reading;
  assert.ok(snippet.length <= 181);
  assert.ok(snippet.endsWith('palabra…'));
});

test('P08 sin texto ni página no muestra lectura y no inventa la fuente', () => {
  const insights = presentInsights({ resultados: {} }, '   ', 'chrome://extensions');
  assert.equal(insights.consensus, null);
  assert.equal(insights.reading, null);
  assert.equal(insights.note, null);
  assert.deepEqual(presentInsights(null).markers, []);
  assert.equal(presentInsights({ resultados: {} }, null, 'https://diario.test/a').reading.domain, 'diario.test');
});
