import { test } from 'node:test';
import assert from 'node:assert/strict';
import { countWords, meterState, presentFragments } from '../src/popup/selection-presentation.js';

test('cuenta palabras igual que el TOKEN_PATTERN del backend', () => {
  assert.equal(countWords('Hola, ¿qué tal? El niño comió 3,5 kg_de pan.'), 10);
  assert.equal(countWords('COVID-19 e-mail año 2026'), 6);
  assert.equal(countWords(''), 0);
  assert.equal(countWords(null), 0);
});

test('el medidor pasa de rojo a amarillo, verde y dorado', () => {
  const short = meterState(40);
  assert.deepEqual([short.level, short.ready, short.missing, short.value, short.marker, short.message], ['short', false, 60, 11, 29, 'Faltan 60 palabras']);
  assert.deepEqual([meterState(99).level, meterState(100).level, meterState(100).message], ['short', 'ready', 'Listo para analizar']);
  assert.deepEqual([meterState(279).level, meterState(280).level, meterState(280).message], ['ready', 'good', 'Buena longitud']);
  assert.deepEqual([meterState(349).level, meterState(350).level, meterState(350).value], ['good', 'full', 100]);
  assert.equal(meterState(900).message, 'Longitud completa: lo que siga no se analiza');
  assert.equal(meterState(-3).words, 0);
});

test('presenta fragmentos numerados y trata el texto antiguo como uno', () => {
  const shown = presentFragments({ fragments: [{ id: 'a', text: ' Titular ' }, { id: 'b', text: '   ' }, { id: 'c', text: 'Cuerpo de la noticia' }] });
  assert.deepEqual(shown.map(({ id, number, text, words }) => [id, number, text, words]), [['a', '01', 'Titular', 1], ['c', '02', 'Cuerpo de la noticia', 4]]);
  assert.deepEqual(presentFragments({ text: 'Texto previo' }).map((fragment) => fragment.text), ['Texto previo']);
  assert.deepEqual(presentFragments(null), []);
});
