import { test } from 'node:test';
import assert from 'node:assert/strict';
import { presentBreakdown } from '../src/popup/result-presentation.js';

test('P06 presenta BiLSTM y mBERT en orden con sus porcentajes y comparación recibida', () => {
  assert.deepEqual(presentBreakdown({
    resultados: {
      mbert: { estado: 'ok', probabilidad_falsa: 0.76 },
      bilstm: { estado: 'ok', probabilidad_falsa: 0.71 },
    },
    comparacion: 'coinciden',
  }), {
    models: [
      { key: 'bilstm', name: 'BiLSTM', percentage: '71 %' },
      { key: 'mbert', name: 'mBERT', percentage: '76 %' },
    ],
    comparison: 'Los modelos coinciden',
    noneAvailable: false,
  });
});

test('P06 omite comparación si uno de los modelos falló o falta', () => {
  const partial = presentBreakdown({
    resultados: { bilstm: { estado: 'ok', probabilidad_falsa: 0 } },
    comparacion: 'discrepan',
  });
  assert.equal(partial.models[0].percentage, '0 %');
  assert.equal(partial.models[1].percentage, null);
  assert.equal(partial.comparison, null);
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
    assert.equal(displayed.models[1].percentage, null);
    assert.equal(displayed.comparison, null);
    assert.equal(displayed.noneAvailable, true);
  }
});

test('P06 muestra discrepancia solo con dos predicciones válidas', () => {
  const displayed = presentBreakdown({
    resultados: {
      bilstm: { estado: 'ok', probabilidad_falsa: 1 },
      mbert: { estado: 'ok', probabilidad_falsa: 0.2 },
    },
    comparacion: 'discrepan',
  });
  assert.equal(displayed.models[0].percentage, '100 %');
  assert.equal(displayed.comparison, 'Los modelos discrepan');
  assert.equal(presentBreakdown(null).noneAvailable, true);
});
