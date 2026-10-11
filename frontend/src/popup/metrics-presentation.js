import { formatProbability } from './result-presentation.js';

function readableText(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function measure(label, value) {
  const percentage = formatProbability(value);
  return percentage === null ? null : { label, percentage };
}

export function presentMetrics(data) {
  const model = readableText(data?.modelo);
  const limitations = typeof data?.limitaciones === 'string'
    ? [data.limitaciones.trim()].filter(Boolean)
    : Array.isArray(data?.limitaciones)
      ? data.limitaciones.map(readableText).filter(Boolean)
      : [];
  return {
    model: model === 'bilstm' ? 'BiLSTM' : model === 'mbert' ? 'mBERT' : model,
    version: readableText(data?.version),
    limitations,
    evaluations: (data?.evaluaciones ?? []).map((evaluation, index) => ({
      key: `${readableText(evaluation.conjunto) ?? 'conjunto'}-${index}`,
      name: readableText(evaluation.conjunto) ?? 'Conjunto sin nombre',
      examples: Number.isSafeInteger(evaluation.n) && evaluation.n >= 0 ? evaluation.n.toLocaleString('es-PE') : null,
      source: readableText(evaluation.fuente),
      main: [measure('Exactitud', evaluation.exactitud), measure('F1 macro', evaluation.f1_macro)].filter(Boolean),
      extra: [
        measure('Precisión de la clase falsa', evaluation.precision_falsa),
        measure('Cobertura de la clase falsa', evaluation.recall_falsa),
        measure('F1 de la clase falsa', evaluation.f1_falsa),
      ].filter(Boolean),
    })),
  };
}
