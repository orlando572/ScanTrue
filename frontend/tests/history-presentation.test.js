import { test } from 'node:test';
import assert from 'node:assert/strict';
import { appendUniqueHistory, presentHistoryDetail, presentHistoryItem } from '../src/popup/history-presentation.js';
import { presentResult } from '../src/popup/result-presentation.js';

test('P07 usa la vista previa y el resultado unificado guardado', () => {
  const shown = presentHistoryItem({
    id: 'a1', fecha: '2026-10-10T14:22:00Z', vista_previa: 'Un fragmento guardado',
    url: 'https://ejemplo.org/noticia', resultado_unificado: { probabilidad_falsa: 0.73 },
  });
  assert.equal(shown.id, 'a1');
  assert.equal(shown.title, 'Un fragmento guardado');
  assert.equal(shown.domain, 'ejemplo.org');
  assert.equal(shown.percentage, '73 %');
  assert.equal(shown.level, 'Probablemente falso');
  assert.equal(shown.tone, 'high');
  assert.notEqual(shown.date, 'Fecha no disponible');
});

test('P07 comparte los cinco niveles y sus límites con P05', () => {
  const cases = [
    [0, '0 %', 'Muy probablemente verdadero', 'very-low'],
    [0.2, '20 %', 'Muy probablemente verdadero', 'very-low'],
    [0.21, '21 %', 'Probablemente verdadero', 'low'],
    [0.4, '40 %', 'Probablemente verdadero', 'low'],
    [0.41, '41 %', 'Resultado incierto', 'middle'],
    [0.6, '60 %', 'Resultado incierto', 'middle'],
    [0.61, '61 %', 'Probablemente falso', 'high'],
    [0.8, '80 %', 'Probablemente falso', 'high'],
    [0.81, '81 %', 'Muy probablemente falso', 'very-high'],
    [1, '100 %', 'Muy probablemente falso', 'very-high'],
    [0.405, '41 %', 'Resultado incierto', 'middle'],
  ];
  for (const [probability, percentage, level, tone] of cases) {
    const shown = presentHistoryItem({ resultado_unificado: { probabilidad_falsa: probability } });
    assert.deepEqual([shown.percentage, shown.level, shown.tone], [percentage, level, tone]);
  }
});

test('P07 identifica registros antiguos sin inventar porcentaje o titular', () => {
  const domainOnly = presentHistoryItem({ id: 'a2', fecha: 'fecha inválida', url: 'https://ejemplo.org/ruta' });
  assert.equal(domainOnly.title, 'ejemplo.org');
  assert.equal(domainOnly.date, 'Fecha no disponible');
  assert.equal(domainOnly.percentage, null);
  assert.equal(domainOnly.level, null);
  assert.equal(domainOnly.tone, null);
  assert.equal(presentHistoryItem({ id: 'a3', url: 'javascript:alert(1)' }).title, 'Análisis anterior');
  const invalid = presentHistoryItem({ resultado_unificado: { probabilidad_falsa: 3 } });
  assert.deepEqual([invalid.percentage, invalid.level, invalid.tone], [null, null, null]);
});

test('P07 añade páginas sin repetir registros ni cambiar su orden', () => {
  const first = [{ id: 'a' }, { id: 'b' }];
  const merged = appendUniqueHistory(first, [{ id: 'b' }, { id: 'c' }, { id: null }, { id: 'd' }]);
  assert.deepEqual(merged.map((item) => item.id), ['a', 'b', 'c', 'd']);
  assert.equal(first.length, 2);
});

test('P08 conserva el texto completo y muestra el resultado guardado', () => {
  const text = 'Fragmento completo\ncon otra línea';
  const shown = presentHistoryDetail({
    fecha: '2026-10-10T14:22:00Z', url: 'https://ejemplo.org/noticia', texto: text,
    resultado_unificado: { probabilidad_falsa: 0.73, modelos_utilizados: ['bilstm', 'mbert'] },
    resultados: { bilstm: { estado: 'ok', probabilidad_falsa: 0.71 } },
  });
  assert.equal(shown.text, text);
  assert.equal(shown.domain, 'ejemplo.org');
  assert.equal(shown.percentage, '73 %');
  assert.deepEqual(shown.level, presentResult({ resultado_unificado: { probabilidad_falsa: 0.73 } }).level);
  assert.equal(shown.source, 'Resultado combinado de dos modelos');
  assert.equal(shown.hasBreakdown, true);
});

test('P08 no reconstruye texto ni porcentaje de registros antiguos', () => {
  const shown = presentHistoryDetail({ hash_texto: 'hash', vista_previa: 'Fragmento corto', resultados: {} });
  assert.equal(shown.text, null);
  assert.equal(shown.percentage, null);
  assert.equal(shown.level, null);
  assert.equal(shown.hasBreakdown, false);
});

test('P08 conserva el desglose si falta el resultado unificado', () => {
  const shown = presentHistoryDetail({ resultados: { bilstm: { estado: 'ok', probabilidad_falsa: 0.71 } } });
  assert.equal(shown.percentage, null);
  assert.equal(shown.level, null);
  assert.equal(shown.hasBreakdown, true);
});
