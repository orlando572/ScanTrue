import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  activeCount, emptyFilters, readFilters, toApiQuery, writeFilters,
} from '../src/lib/filters.js';

test('lee de la URL solo los filtros reconocidos', () => {
  const filters = readFilters(new URLSearchParams(
    'q=%20vacuna%20&nivel=4&comparacion=otra&desde=2026-11-01&hasta=ayer&dominio=Diario.PE&verificacion=contradicha&orden=mas_falsa&revision=pendiente',
  ));
  assert.deepEqual(filters, {
    q: 'vacuna', nivel: '4', comparacion: '', desde: '2026-11-01', hasta: '',
    dominio: 'diario.pe', verificacion: 'contradicha', orden: 'mas_falsa',
  });
});

test('sin parámetros usa el orden por defecto de cada vista', () => {
  assert.equal(emptyFilters().orden, 'recientes');
  assert.equal(emptyFilters('admin').orden, 'prioridad');
  assert.equal(readFilters(new URLSearchParams('orden=prioridad')).orden, 'recientes');
  assert.equal(activeCount(emptyFilters()), 0);
});

test('el panel añade revisión y visibilidad y filtra también por el estado de la cola', () => {
  const filters = readFilters(new URLSearchParams('revision=aprobado&visibilidad=ocultos&verificacion=fallida'), 'admin');
  assert.equal(filters.revision, 'aprobado');
  assert.equal(filters.visibilidad, 'ocultos');
  assert.equal(filters.verificacion, 'fallida');
  assert.equal(activeCount(filters, 'admin'), 3);
  assert.deepEqual(toApiQuery(filters, 'admin'), { verificacion: 'fallida', revision: 'aprobado', visibilidad: 'ocultos', orden: 'prioridad' });
});

test('los estados de la cola solo existen en el panel', () => {
  for (const value of ['pendiente', 'en_proceso', 'fallida']) {
    assert.equal(readFilters(new URLSearchParams(`verificacion=${value}`), 'admin').verificacion, value);
    assert.equal(readFilters(new URLSearchParams(`verificacion=${value}`)).verificacion, '');
  }
  for (const value of ['respaldada', 'contradicha', 'fuera_de_contexto', 'evidencia_insuficiente', 'sin_verificar']) {
    assert.equal(readFilters(new URLSearchParams(`verificacion=${value}`)).verificacion, value);
    assert.equal(readFilters(new URLSearchParams(`verificacion=${value}`), 'admin').verificacion, value);
  }
});

test('la URL solo guarda lo que no es valor por defecto y se vuelve a leer igual', () => {
  const filters = { ...emptyFilters(), q: 'paro minero', nivel: '5' };
  const params = writeFilters(filters);
  assert.equal(params.toString(), 'q=paro+minero&nivel=5');
  assert.deepEqual(readFilters(params), filters);
  assert.equal(writeFilters({ ...emptyFilters('admin'), orden: 'recientes' }, 'admin').toString(), 'orden=recientes');
});

test('la consulta de la API omite vacíos y ordena un rango de fechas invertido', () => {
  const query = toApiQuery({ ...emptyFilters(), desde: '2026-11-10', hasta: '2026-11-01', dominio: 'diario.pe' });
  assert.deepEqual(query, { desde: '2026-11-01', hasta: '2026-11-10', dominio: 'diario.pe', orden: 'recientes' });
  assert.equal(activeCount({ ...emptyFilters(), desde: '2026-11-10', orden: 'antiguos' }), 1);
});
