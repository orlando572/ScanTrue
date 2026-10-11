export function formatProbability(probability) {
  return typeof probability === 'number' && Number.isFinite(probability) && probability >= 0 && probability <= 1
    ? `${Math.round(probability * 100)} %`
    : null;
}

const resultLevels = [
  { max: 20, label: 'Muy probablemente verdadero', tone: 'very-low', icon: 'joyful' },
  { max: 40, label: 'Probablemente verdadero', tone: 'low', icon: 'smile' },
  { max: 60, label: 'Resultado incierto', tone: 'middle', icon: 'neutral' },
  { max: 80, label: 'Probablemente falso', tone: 'high', icon: 'sad' },
  { max: 100, label: 'Muy probablemente falso', tone: 'very-high', icon: 'crying' },
];

export function presentResultLevel(probability) {
  if (formatProbability(probability) === null) return null;
  const value = Math.round(probability * 100);
  const { label, tone, icon } = resultLevels.find((level) => value <= level.max);
  return { value, label, tone, icon };
}

export function presentResult(result) {
  const unified = result?.resultado_unificado;
  const percentage = formatProbability(unified?.probabilidad_falsa);
  const level = presentResultLevel(unified?.probabilidad_falsa);

  const models = Array.isArray(unified?.modelos_utilizados)
    ? [...new Set(unified.modelos_utilizados.filter((model) => typeof model === 'string' && model.trim()))]
    : [];
  const source = models.length === 2
    ? 'Resultado combinado de dos modelos'
    : models.length === 1 ? 'Resultado basado en un modelo' : null;
  const outputs = result?.resultados;
  const hasBreakdown = !!outputs && typeof outputs === 'object' && !Array.isArray(outputs) && Object.keys(outputs).length > 0;

  return { percentage, level, source, hasBreakdown };
}

export function presentBreakdown(result) {
  const outputs = result?.resultados;
  const models = [
    { key: 'bilstm', name: 'BiLSTM' },
    { key: 'mbert', name: 'mBERT' },
  ].map(({ key, name }) => {
    const output = outputs && typeof outputs === 'object' && !Array.isArray(outputs) ? outputs[key] : null;
    const level = output?.estado === 'ok' ? presentResultLevel(output.probabilidad_falsa) : null;
    const value = level?.value ?? null;
    const percentage = value === null ? null : `${value} %`;
    const classification = value !== null && ['falsa', 'real'].includes(output.clase) ? output.clase : null;
    return { key, name, percentage, value, classification, level: level?.label ?? null };
  });

  return { models, noneAvailable: models.every(({ percentage }) => percentage === null) };
}
