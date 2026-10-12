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
};

export function presentMetrics(data) {
  const model = readableText(data?.modelo);
  const limitations = typeof data?.limitaciones === 'string'
    ? [data.limitaciones.trim()].filter(Boolean)
    : Array.isArray(data?.limitaciones)
      ? data.limitaciones.map(readableText).filter(Boolean)
      : [];
  return {
    model: model === 'bilstm' ? 'BiLSTM' : model === 'mbert' ? 'mBERT' : model,
    limitations,
    evaluations: (data?.evaluaciones ?? []).map((evaluation, index) => {
      const source = readableText(evaluation.fuente);
      const name = readableText(evaluation.conjunto);
      return {
        key: `${name ?? 'conjunto'}-${index}`,
        name: name && Object.hasOwn(evaluationNames, name) ? evaluationNames[name] : name ?? 'Prueba sin nombre',
        examples: Number.isSafeInteger(evaluation.n) && evaluation.n >= 0 ? evaluation.n.toLocaleString('es-PE') : null,
        source,
        sourceName: shortSource(source),
        accuracy: formatProbability(evaluation.exactitud),
        f1: formatProbability(evaluation.f1_macro),
      };
    }),
  };
}
