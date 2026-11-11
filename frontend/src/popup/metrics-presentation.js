import { formatProbability } from './result-presentation.js';

function readableText(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function shortSource(source) {
  if (!source) return null;
  try {
    const url = new URL(source);
    if (/^https?:$/.test(url.protocol)) return url.hostname.replace(/^www\./i, '');
  } catch { /* A descriptive source name is not a URL. */ }
  return source;
}

const evaluationNames = {
  validacion: 'Validación',
  prueba_interna_no_politica: 'Prueba interna',
  fuentes_reservadas: 'Fuentes reservadas',
  prueba_bilstm_filtrada: 'Prueba',
  externa_bilstm_filtrada: 'Prueba externa',
  validacion_por_fuente_articulos: 'Fuentes no vistas',
  fuente_no_vista_v1: 'Fuente no vista: v1',
  fuente_no_vista_fakedes: 'Fuente no vista: FakeDeS',
  fuente_no_vista_polyglot: 'Fuente no vista: Polyglot',
  prueba_congelada: 'Prueba congelada',
  prueba_congelada_falledesinfo: 'Prueba congelada: FalleDesinfo (fuente nueva)',
};

// Pruebas que se muestran de entrada, en este orden; el resto queda en «Ver más».
const featuredSets = ['prueba_congelada', 'validacion_por_fuente_articulos'];
const FEATURED_FALLBACK = 2;
const evaluationNotes = {
  prueba_congelada: 'Evaluación final: textos reservados que se usaron una sola vez.',
  validacion_por_fuente_articulos: 'Noticias de medios que el modelo no vio al entrenar.',
};

export function presentMetrics(data) {
  const model = readableText(data?.modelo);
  const limitations = typeof data?.limitaciones === 'string'
    ? [data.limitaciones.trim()].filter(Boolean)
    : Array.isArray(data?.limitaciones)
      ? data.limitaciones.map(readableText).filter(Boolean)
      : [];
  const evaluations = (data?.evaluaciones ?? []).map((evaluation, index) => {
    const source = readableText(evaluation.fuente);
    const name = readableText(evaluation.conjunto);
    return {
      key: `${name ?? 'conjunto'}-${index}`,
      set: name,
      note: name && Object.hasOwn(evaluationNotes, name) ? evaluationNotes[name] : null,
      name: name && Object.hasOwn(evaluationNames, name) ? evaluationNames[name] : name ?? 'Prueba sin nombre',
      examples: Number.isSafeInteger(evaluation.n) && evaluation.n >= 0 ? evaluation.n.toLocaleString('es-PE') : null,
      source,
      sourceName: shortSource(source),
      accuracy: formatProbability(evaluation.exactitud),
      f1: formatProbability(evaluation.f1_macro),
    };
  });
  // Si no llega ninguna de las pruebas principales conocidas, se destacan las primeras.
  const rank = (evaluation) => featuredSets.indexOf(evaluation.set);
  const known = evaluations.some((evaluation) => rank(evaluation) >= 0);
  const featured = known
    ? evaluations.filter((evaluation) => rank(evaluation) >= 0).sort((a, b) => rank(a) - rank(b))
    : evaluations.slice(0, FEATURED_FALLBACK);
  return {
    model: model === 'bilstm' ? 'BiLSTM' : model === 'mbert' ? 'BETO' : model,
    limitations,
    evaluations,
    featured,
    more: evaluations.filter((evaluation) => !featured.includes(evaluation)),
  };
}
