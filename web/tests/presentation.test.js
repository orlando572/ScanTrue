import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  presentAnalysis, presentVerification, readSplit, share, shortId,
} from '../src/lib/presentation.js';

const item = {
  id: '3f9a2c10-0000-4000-8000-000000000000',
  fecha: '2026-11-12T15:00:00Z',
  dominio: 'diario.pe',
  url: 'https://diario.pe/nota',
  fragmentos: ['Primer fragmento.', '  ', 'Segundo fragmento.'],
  fragmentos_total: 5,
  palabras: 1234,
  texto_recortado: true,
  probabilidad_falsa: 0.73,
  comparacion: 'discrepan',
  estado_blockchain: 'confirmado',
  resultados: {
    bilstm: { modelo: 'bilstm', estado: 'ok', clase: 'real', probabilidad_falsa: 0.4 },
    mbert: { modelo: 'mbert', estado: 'ok', clase: 'falsa', probabilidad_falsa: 0.8 },
  },
  verificacion_web: null,
};

test('presenta un análisis con fragmentos numerados y los tres criterios', () => {
  const view = presentAnalysis(item);
  assert.equal(view.code, '3F9A2C');
  assert.deepEqual(view.fragments.map((fragment) => fragment.number), ['01', '02']);
  assert.equal(view.hiddenFragments, 3);
  assert.equal(view.words, '1,234 palabras');
  assert.equal(view.truncated, true);
  assert.equal(view.level.value, 73);
  assert.equal(view.tone, 'high');
  assert.deepEqual(view.models.map((model) => [model.name, model.percentage, model.classification]),
    [['BiLSTM', '40 %', 'real'], ['BETO', '80 %', 'falsa']]);
  assert.equal(view.agreement.state, 'disagree');
  assert.equal(view.chain.state, 'ok');
  assert.equal(view.verification.state, 'none');
  assert.equal(view.verification.label, 'Aún no disponible');
});

test('un análisis incompleto no inventa valores', () => {
  const view = presentAnalysis({ id: null, comparacion: 'no_disponible', resultados: { bilstm: { estado: 'ok', clase: 'real', probabilidad_falsa: 0.1 } } });
  assert.equal(view.level, null);
  assert.equal(view.tone, 'none');
  assert.equal(view.models[1].percentage, null);
  assert.equal(view.agreement.state, 'single');
  assert.equal(view.url, null);
  assert.equal(view.words, null);
  assert.equal(shortId(undefined), '——');
});

test('la verificación web (incremento 2) ya se sabe presentar', () => {
  const done = presentVerification({
    estado: 'completada', conclusion: 'contradicha', resumen: ' Dos fuentes lo desmienten. ',
    fuentes: [{ titulo: 'Agencia', url: 'https://agencia.example/nota' }, 'https://otra.example', { url: 'javascript:alert(1)' }],
    afirmaciones: ['El puente se cerró', { afirmacion: 'Hubo 3 heridos' }],
  });
  assert.equal(done.state, 'done');
  assert.equal(done.label, 'Contradicha por fuentes');
  assert.equal(done.tone, 'very-high');
  assert.equal(done.summary, 'Dos fuentes lo desmienten.');
  assert.deepEqual(done.sources, [
    { text: 'Agencia', url: 'https://agencia.example/nota' },
    { text: 'https://otra.example', url: 'https://otra.example' },
  ]);
  assert.deepEqual(done.claims.map((claim) => claim.text), ['El puente se cerró', 'Hubo 3 heridos']);
  assert.equal(presentVerification({ estado: 'en_proceso' }).state, 'working');
  assert.equal(presentVerification({ estado: 'fallida' }).label, 'No se pudo verificar');
});

test('separa lo que leyó un modelo del resto del fragmento', () => {
  assert.deepEqual(readSplit('uno dos tres', 'uno dos'), { read: 'uno dos', rest: ' tres' });
  assert.deepEqual(readSplit('uno dos', 'otro texto'), { read: 'otro texto', rest: '' });
  assert.equal(readSplit('uno dos', null), null);
  assert.equal(share(1, 3), 33);
  assert.equal(share(1, 0), 0);
});
