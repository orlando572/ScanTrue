const API_BASE = 'http://127.0.0.1:8000';

export async function getServiceHealth() {
  const response = await fetch(`${API_BASE}/salud`, {
    headers: { Accept: 'application/json' },
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error('Health request failed');
  return response.json();
}
