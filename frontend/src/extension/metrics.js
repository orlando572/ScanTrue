const API_BASE = 'http://127.0.0.1:8000';

export async function getPublishedMetrics(model = 'bilstm') {
  if (model !== 'bilstm' && model !== 'mbert') throw new Error('Modelo no reconocido');
  const url = model === 'bilstm' ? `${API_BASE}/metricas` : `${API_BASE}/metricas?modelo=mbert`;
  const response = await fetch(url, {
    headers: { Accept: 'application/json' },
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error('No pudimos cargar las métricas.');
  const data = await response.json();
  if (!data || typeof data !== 'object' || data.modelo !== model || !Array.isArray(data.evaluaciones)
      || data.evaluaciones.some((evaluation) => !evaluation || typeof evaluation !== 'object' || Array.isArray(evaluation))) {
    throw new Error('Respuesta de métricas no reconocida');
  }
  return data;
}
