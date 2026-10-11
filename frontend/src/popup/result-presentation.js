export function formatProbability(probability) {
  return typeof probability === 'number' && Number.isFinite(probability) && probability >= 0 && probability <= 1
    ? `${Math.round(probability * 100)} %`
    : null;
}

export function presentResult(result) {
  const unified = result?.resultado_unificado;
  const percentage = formatProbability(unified?.probabilidad_falsa);

  const models = Array.isArray(unified?.modelos_utilizados)
    ? [...new Set(unified.modelos_utilizados.filter((model) => typeof model === 'string' && model.trim()))]
    : [];
  const source = models.length === 2
    ? 'Resultado combinado de dos modelos'
    : models.length === 1 ? 'Resultado basado en un modelo' : null;
  const comparison = models.length === 2
    ? { coinciden: 'Los modelos coinciden', discrepan: 'Los modelos discrepan' }[result?.comparacion] ?? null
    : null;
  const outputs = result?.resultados;
  const hasBreakdown = !!outputs && typeof outputs === 'object' && !Array.isArray(outputs) && Object.keys(outputs).length > 0;

  return { percentage, source, comparison, hasBreakdown };
}

export function presentBreakdown(result) {
  const outputs = result?.resultados;
  const models = [
    { key: 'bilstm', name: 'BiLSTM' },
    { key: 'mbert', name: 'mBERT' },
  ].map(({ key, name }) => {
    const output = outputs && typeof outputs === 'object' && !Array.isArray(outputs) ? outputs[key] : null;
    return { key, name, percentage: output?.estado === 'ok' ? formatProbability(output.probabilidad_falsa) : null };
  });
  const bothAvailable = models.every(({ percentage }) => percentage !== null);
  const comparison = bothAvailable
    ? { coinciden: 'Los modelos coinciden', discrepan: 'Los modelos discrepan' }[result?.comparacion] ?? null
    : null;

  return { models, comparison, noneAvailable: models.every(({ percentage }) => percentage === null) };
}
