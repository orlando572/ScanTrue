import { test } from 'node:test';
import assert from 'node:assert/strict';
import { presentBreakdown } from '../src/popup/result-presentation.js';

test('P06 presenta BiLSTM y mBERT con la etiqueta de cada porcentaje', () => {
  assert.deepEqual(presentBreakdown({
    resultados: {
      mbert: { estado: 'ok', clase: 'falsa', probabilidad_falsa: 0.76 },
      bilstm: { estado: 'ok', clase: 'falsa', probabilidad_falsa: 0.71 },
    },
    comparacion: 'coinciden',
  }), {
    models: [
      { key: 'bilstm', name: 'BiLSTM', percentage: '71 %', value: 71, classification: 'falsa', level: 'Probablemente falso' },
      { key: 'mbert', name: 'mBERT', percentage: '76 %', value: 76, classification: 'falsa', level: 'Probablemente falso' },
    ],
    noneAvailable: false,
  });
});

test('P06 conserva el modelo válido cuando el otro falta', () => {
  const partial = presentBreakdown({
    resultados: { bilstm: { estado: 'ok', probabilidad_falsa: 0 } },
    comparacion: 'discrepan',
  });
  assert.equal(partial.models[0].percentage, '0 %');
  assert.equal(partial.models[0].value, 0);
  assert.equal(partial.models[0].classification, null);
  assert.equal(partial.models[0].level, 'Muy probablemente verdadero');
  assert.equal(partial.models[1].percentage, null);
  assert.equal(partial.models[1].value, null);
  assert.equal(partial.models[1].level, null);
  assert.equal(partial.noneAvailable, false);
});

test('P06 trata como no disponible un estado fallido o porcentaje inválido', () => {
  for (const probability of [undefined, null, -0.1, 1.1, NaN, '0.9']) {
    const displayed = presentBreakdown({
      resultados: {
        bilstm: { estado: 'ok', probabilidad_falsa: probability },
        mbert: { estado: 'no_disponible', probabilidad_falsa: 0.4 },
      },
      comparacion: 'coinciden',
    });
    assert.equal(displayed.models[0].percentage, null);
    assert.equal(displayed.models[0].classification, null);
    assert.equal(displayed.models[1].percentage, null);
    assert.equal(displayed.models[0].level, null);
    assert.equal(displayed.noneAvailable, true);
  }
});

test('P06 no presenta comparaciones entre modelos', () => {
  const displayed = presentBreakdown({
    resultados: {
      bilstm: { estado: 'ok', probabilidad_falsa: 1 },
      mbert: { estado: 'ok', probabilidad_falsa: 0.2 },
    },
    comparacion: 'discrepan',
  });
  assert.equal(displayed.models[0].percentage, '100 %');
  assert.equal(displayed.models[0].value, 100);
  assert.equal(displayed.models[0].level, 'Muy probablemente falso');
  assert.equal(Object.hasOwn(displayed, 'comparison'), false);
  assert.equal(presentBreakdown(null).noneAvailable, true);
});

test('P06 muestra la clase recibida y no la infiere del porcentaje', () => {
  const displayed = presentBreakdown({ resultados: {
    bilstm: { estado: 'ok', clase: 'real', probabilidad_falsa: 0.22 },
    mbert: { estado: 'ok', clase: 'otra', probabilidad_falsa: 0.51 },
  } });
  assert.equal(displayed.models[0].classification, 'real');
  assert.equal(displayed.models[0].value, 22);
  assert.equal(displayed.models[0].level, 'Probablemente verdadero');
  assert.equal(displayed.models[1].classification, null);
  assert.equal(displayed.models[1].value, 51);
  assert.equal(displayed.models[1].level, 'Resultado incierto');
});
