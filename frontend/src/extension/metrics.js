const API_BASE = 'http://127.0.0.1:8000';

export async function getPublishedMetrics() {
  const response = await fetch(`${API_BASE}/metricas`, {
    headers: { Accept: 'application/json' },
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error('No pudimos cargar las métricas.');
  const data = await response.json();
  if (!data || typeof data !== 'object' || !Array.isArray(data.evaluaciones)
      || data.evaluaciones.some((evaluation) => !evaluation || typeof evaluation !== 'object' || Array.isArray(evaluation))) {
    throw new Error('Respuesta de métricas no reconocida');
  }
  return data;
}
