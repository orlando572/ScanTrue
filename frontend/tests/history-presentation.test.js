import { test } from 'node:test';
import assert from 'node:assert/strict';
import { appendUniqueHistory, presentHistoryDetail, presentHistoryItem } from '../src/popup/history-presentation.js';

test('P07 usa la vista previa y el resultado unificado guardado', () => {
  const shown = presentHistoryItem({
    id: 'a1', fecha: '2026-10-10T14:22:00Z', vista_previa: 'Un fragmento guardado',
    url: 'https://ejemplo.org/noticia', resultado_unificado: { probabilidad_falsa: 0.73 },
  });
  assert.equal(shown.id, 'a1');
  assert.equal(shown.title, 'Un fragmento guardado');
  assert.equal(shown.domain, 'ejemplo.org');
  assert.equal(shown.percentage, '73 %');
  assert.notEqual(shown.date, 'Fecha no disponible');
});

test('P07 identifica registros antiguos sin inventar porcentaje o titular', () => {
  const domainOnly = presentHistoryItem({ id: 'a2', fecha: 'fecha inválida', url: 'https://ejemplo.org/ruta' });
  assert.equal(domainOnly.title, 'ejemplo.org');
  assert.equal(domainOnly.date, 'Fecha no disponible');
  assert.equal(domainOnly.percentage, null);
  assert.equal(presentHistoryItem({ id: 'a3', url: 'javascript:alert(1)' }).title, 'Análisis anterior');
  assert.equal(presentHistoryItem({ resultado_unificado: { probabilidad_falsa: 3 } }).percentage, null);
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
  assert.equal(shown.source, 'Resultado combinado de dos modelos');
  assert.equal(shown.hasBreakdown, true);
});

test('P08 no reconstruye texto ni porcentaje de registros antiguos', () => {
  const shown = presentHistoryDetail({ hash_texto: 'hash', vista_previa: 'Fragmento corto', resultados: {} });
  assert.equal(shown.text, null);
  assert.equal(shown.percentage, null);
  assert.equal(shown.hasBreakdown, false);
});
