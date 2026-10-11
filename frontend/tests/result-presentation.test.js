import { test } from 'node:test';
import assert from 'node:assert/strict';
import { presentResult, presentResultLevel } from '../src/popup/result-presentation.js';

test('P05 muestra el unificado recibido sin comentarios de comparación', () => {
  assert.deepEqual(presentResult({
    resultado_unificado: { probabilidad_falsa: 0.73, modelos_utilizados: ['bilstm', 'mbert'] },
    comparacion: 'coinciden',
    resultados: { bilstm: { estado: 'ok' }, mbert: { estado: 'ok' } },
  }), {
    percentage: '73 %',
    level: { value: 73, label: 'Probablemente falso', tone: 'high', icon: 'sad' },
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
  assert.deepEqual(displayed.level, { value: 0, label: 'Muy probablemente verdadero', tone: 'very-low', icon: 'joyful' });
  assert.equal(displayed.source, 'Resultado basado en un modelo');
  assert.equal(Object.hasOwn(displayed, 'comparison'), false);
  assert.equal(displayed.hasBreakdown, true);
});

test('P05 admite el extremo superior sin mostrar discrepancia', () => {
  const displayed = presentResult({
    resultado_unificado: { probabilidad_falsa: 1, modelos_utilizados: ['bilstm', 'mbert'] },
    comparacion: 'discrepan',
  });
  assert.equal(displayed.percentage, '100 %');
  assert.deepEqual(displayed.level, { value: 100, label: 'Muy probablemente falso', tone: 'very-high', icon: 'crying' });
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
  assert.deepEqual(presentResultLevel(0.405), { value: 41, label: 'Resultado incierto', tone: 'middle', icon: 'neutral' });
  assert.deepEqual(presentResultLevel(0.404), { value: 40, label: 'Probablemente verdadero', tone: 'low', icon: 'smile' });
});
