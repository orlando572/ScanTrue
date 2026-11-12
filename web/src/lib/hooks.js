import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { API_BASE, getSession, onSessionChange } from './api.js';

// Carga datos con una función `(signal) => Promise`; se repite al cambiar `deps`.
export function useLoad(load, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [attempt, setAttempt] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    const controller = new AbortController();
    setState((previous) => ({ ...previous, error: null, loading: true }));
    loadRef.current(controller.signal)
      .then((data) => { if (!controller.signal.aborted) setState({ data, error: null, loading: false }); })
      .catch((error) => {
        if (!controller.signal.aborted) setState({ data: null, error, loading: false });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);
  const setData = useCallback((data) => setState({ data, error: null, loading: false }), []);
  return { ...state, reload, setData };
}

// Estado de /salud, consultado cada 30 s y al volver a la pestaña.
export function useHealth() {
  const [state, setState] = useState({ health: 'checking', data: null, latency: null });
  useEffect(() => {
    let cancelled = false;
    async function check() {
      const started = performance.now();
      try {
        const response = await fetch(`${API_BASE}/salud`, {
          headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw new Error('salud');
        const data = await response.json();
        if (!cancelled) {
          setState({
            health: data?.estado === 'ok' ? 'ok' : 'degraded',
            data,
            latency: Math.round(performance.now() - started),
          });
        }
      } catch {
        if (!cancelled) setState({ health: 'unavailable', data: null, latency: null });
      }
    }
    check();
    const timer = setInterval(() => { if (!document.hidden) check(); }, 30_000);
    const visible = () => { if (!document.hidden) check(); };
    document.addEventListener('visibilitychange', visible);
    return () => {
      cancelled = true;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', visible);
    };
  }, []);
  return state;
}

let cached = { raw: undefined, session: null };

function readSession() {
  const session = getSession();
  const raw = JSON.stringify(session);
  if (raw !== cached.raw) cached = { raw, session };
  return cached.session;
}

export function useSession() {
  return useSyncExternalStore(onSessionChange, readSession, () => null);
}

// Valor que se actualiza con retraso: la búsqueda no consulta en cada tecla.
export function useDebounced(value, delay = 350) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}
