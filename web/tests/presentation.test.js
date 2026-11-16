import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  presentAnalysis, presentQueue, presentTracking, presentVerification, readSplit, share, shortId,
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
  assert.deepEqual(done.sources.map((source) => [source.text, source.url]), [
    ['Agencia', 'https://agencia.example/nota'],
    ['https://otra.example', 'https://otra.example'],
  ]);
  assert.deepEqual(done.claims.map((claim) => claim.text), ['El puente se cerró', 'Hubo 3 heridos']);
  assert.equal(done.note, null);
  assert.equal(presentVerification({ estado: 'en_proceso' }).state, 'working');
  assert.equal(presentVerification({ estado: 'fallida' }).label, 'No se pudo verificar');
});

const COMPLETE = {
  estado: 'completada',
  conclusion: 'contradicha',
  resumen: 'Una afirmación contradice a la noticia.',
  afirmaciones: [
    { id: 1, texto: 'Vargas Llosa recibió el Nobel en 1982', veredicto: 'contradicha', fuente_ids: [1, 3], origen: 'busqueda' },
    { id: 2, texto: 'Nació en Arequipa', veredicto: 'insuficiente', fuente_ids: [], origen: 'base_anterior' },
    { id: 3, texto: 'Dato con veredicto desconocido', veredicto: 'raro' },
    { id: 4, texto: '   ' },
  ],
  fuentes: [
    { id: 1, titulo: 'Wikipedia', url: 'https://es.wikipedia.org/wiki/X', dominio: 'es.wikipedia.org', extracto: 'ganó el Nobel en 2010', consultada_en: '2026-11-15T16:00:00Z' },
    { id: 3, titulo: 'Sin enlace seguro', url: 'javascript:alert(1)', extracto: '   ' },
  ],
};

test('cada afirmación lleva su veredicto, su origen y las fuentes en que se apoya', () => {
  const view = presentVerification(COMPLETE);
  assert.equal(view.state, 'done');
  assert.deepEqual(view.claims.map((claim) => claim.id), [1, 2, 3]);
  assert.deepEqual(view.claims[0].verdict, { key: 'contradicha', label: 'Contradicha', tone: 'very-high' });
  assert.deepEqual(view.claims[0].sourceIds, [1, 3]);
  assert.equal(view.claims[0].origin, null);
  assert.equal(view.claims[1].origin, 'Verificada antes');
  assert.equal(view.claims[1].verdict.label, 'Sin evidencia suficiente');
  assert.equal(view.claims[2].verdict, null);
});

test('las fuentes muestran dominio, cita y fecha, y solo enlazan direcciones http', () => {
  const [wiki, unsafe] = presentVerification(COMPLETE).sources;
  assert.equal(wiki.domain, 'es.wikipedia.org');
  assert.equal(wiki.quote, 'ganó el Nobel en 2010');
  assert.ok(wiki.consulted);
  assert.equal(unsafe.url, null);
  assert.equal(unsafe.quote, null);
  assert.equal(unsafe.id, 3);
});

test('las cuatro conclusiones y los cuatro estados se presentan distinto', () => {
  const conclusions = ['respaldada', 'contradicha', 'fuera_de_contexto', 'evidencia_insuficiente']
    .map((conclusion) => presentVerification({ estado: 'completada', conclusion }));
  assert.deepEqual(conclusions.map((view) => view.label), [
    'Respaldada por fuentes', 'Contradicha por fuentes', 'Fuera de contexto', 'Evidencia insuficiente',
  ]);
  assert.equal(new Set(conclusions.map((view) => view.tone)).size, 4);
  assert.ok(conclusions.every((view) => view.state === 'done' && view.note === null));

  const waiting = ['pendiente', 'en_proceso', 'fallida'].map((estado) => presentVerification({ estado }));
  assert.deepEqual(waiting.map((view) => view.state), ['working', 'working', 'failed']);
  assert.equal(new Set(waiting.map((view) => view.label)).size, 3);
  assert.ok(waiting.every((view) => view.tone === null && view.note));
  assert.match(waiting[2].note, /dos modelos/);
  assert.equal(presentVerification(null).state, 'none');
});

test('un caso completado sin conclusión conocida no inventa una', () => {
  const view = presentVerification({ estado: 'completada', conclusion: 'otra' });
  assert.equal(view.state, 'working');
  assert.equal(view.tone, null);
});

test('el seguimiento explica la falla y dice cuándo se puede reintentar', () => {
  const failed = presentTracking({ estado: 'fallida' }, {
    intentos: 3, ultimo_error: 'llm_no_disponible', version_prompts: 'extraccion-v1',
    iniciado_en: '2026-11-15T10:00:00Z', terminado_en: '2026-11-15T10:00:42Z',
  });
  assert.equal(failed.attempts, 3);
  assert.equal(failed.reason, 'El servidor del LLM no respondió');
  assert.equal(failed.seconds, 42);
  assert.equal(failed.canRetry, true);
  const waiting = presentTracking({ estado: 'pendiente' }, { intentos: 1, proximo_intento: '2026-11-15T10:05:00Z' });
  assert.ok(waiting.next);
  assert.equal(waiting.canRetry, true);
  assert.equal(presentTracking({ estado: 'completada' }, { intentos: 1, copiada_de: 'x' }).canRetry, false);
  assert.equal(presentTracking({ estado: 'en_proceso' }, {}).canRetry, false);
  assert.equal(presentTracking({ estado: 'fallida' }, { ultimo_error: 'algo_nuevo' }).reason, 'algo_nuevo');
  assert.equal(presentTracking(null, null), null);
});

test('el tablero resume el trabajador, el LLM y la cola', () => {
  const on = presentQueue({ habilitada: true, en_pausa: false, llm: { configurado: true, disponible: true }, pendientes: 2, en_proceso: 1, duracion_media_segundos: 33.4 });
  assert.deepEqual([on.worker.state, on.llm.state, on.average, on.waiting], ['running', 'ok', '33 s', 3]);
  const paused = presentQueue({ habilitada: true, en_pausa: true, llm: { configurado: true, disponible: false } });
  assert.deepEqual([paused.worker.label, paused.llm.label, paused.average], ['En pausa', 'No responde', '—']);
  const off = presentQueue({ habilitada: false, llm: { configurado: false, disponible: false } });
  assert.deepEqual([off.worker.state, off.llm.label], ['off', 'Sin configurar']);
  assert.equal(presentQueue(null).worker.state, 'off');
});

test('separa lo que leyó un modelo del resto del fragmento', () => {
  assert.deepEqual(readSplit('uno dos tres', 'uno dos'), { read: 'uno dos', rest: ' tres' });
  assert.deepEqual(readSplit('uno dos', 'otro texto'), { read: 'otro texto', rest: '' });
  assert.equal(readSplit('uno dos', null), null);
  assert.equal(share(1, 3), 33);
  assert.equal(share(1, 0), 0);
});
