import { test } from 'node:test';
import assert from 'node:assert/strict';
import { presentResult } from '../src/popup/result-presentation.js';

test('P05 muestra el unificado recibido y la coincidencia de dos modelos', () => {
  assert.deepEqual(presentResult({
    resultado_unificado: { probabilidad_falsa: 0.73, modelos_utilizados: ['bilstm', 'mbert'] },
    comparacion: 'coinciden',
    resultados: { bilstm: { estado: 'ok' }, mbert: { estado: 'ok' } },
  }), {
    percentage: '73 %',
    source: 'Resultado combinado de dos modelos',
    comparison: 'Los modelos coinciden',
    hasBreakdown: true,
  });
});

test('P05 indica un solo modelo sin inventar una comparación', () => {
  const displayed = presentResult({
    resultado_unificado: { probabilidad_falsa: 0, modelos_utilizados: ['bilstm'] },
    comparacion: 'discrepan',
    resultados: { bilstm: { estado: 'ok' }, mbert: { estado: 'no_disponible' } },
  });
  assert.equal(displayed.percentage, '0 %');
  assert.equal(displayed.source, 'Resultado basado en un modelo');
  assert.equal(displayed.comparison, null);
  assert.equal(displayed.hasBreakdown, true);
});

test('P05 informa una discrepancia real y admite el extremo superior', () => {
  const displayed = presentResult({
    resultado_unificado: { probabilidad_falsa: 1, modelos_utilizados: ['bilstm', 'mbert'] },
    comparacion: 'discrepan',
  });
  assert.equal(displayed.percentage, '100 %');
  assert.equal(displayed.comparison, 'Los modelos discrepan');
  assert.equal(displayed.hasBreakdown, false);
});

test('P05 no reemplaza un unificado ausente o inválido por salidas individuales', () => {
  for (const probability of [undefined, null, -0.1, 1.1, NaN, '0.9']) {
    const displayed = presentResult({
      resultado_unificado: { probabilidad_falsa: probability, modelos_utilizados: ['bilstm'] },
      resultados: { bilstm: { estado: 'ok', probabilidad_falsa: 0.9 } },
    });
    assert.equal(displayed.percentage, null);
    assert.equal(displayed.hasBreakdown, true);
  }
  assert.equal(presentResult(null).hasBreakdown, false);
});
