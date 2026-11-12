import { useEffect, useRef, useState } from 'react';

// Marca: el ojo-radar de ScanTrue dentro del marco de esquinas cortadas. Examina, no
// promete un veredicto, así que no usa ✓ ni símbolos de verificación.
export function Mark() {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path d="M9 3h17l3 3v17l-6 6H6l-3-3V9z" stroke="var(--accent)" strokeWidth="1.5" />
      <path d="M6 16c3-5 6.5-7 10-7s7 2 10 7c-3 5-6.5 7-10 7s-7-2-10-7z" stroke="var(--color-ink)" strokeWidth="1.5" />
      <circle cx="16" cy="16" r="3.2" fill="var(--color-acid)" />
    </svg>
  );
}

const paths = {
  search: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 5 5" /></>,
  arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
  back: <path d="M19 12H5m6-6-6 6 6 6" />,
  external: <><path d="M14 5h5v5" /><path d="m19 5-8 8" /><path d="M17 14v5H5V7h5" /></>,
  radar: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.5" /><path d="M12 12 19 6" /></>,
  bilstm: <><path d="M3 8h4l3 8h4l3-8h4" /><path d="M3 16h4l3-8h4l3 8h4" /></>,
  mbert: <><rect x="4" y="4" width="6" height="6" /><rect x="14" y="4" width="6" height="6" /><rect x="9" y="14" width="6" height="6" /><path d="M7 10v2h10v-2M12 12v2" /></>,
  web: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></>,
  download: <path d="M12 4v11m-5-5 5 5 5-5M5 20h14" />,
};

export function Icon({ name }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="square" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

// Carga estándar: rótulo corto con cursor, barra recorrida por una luz y esqueleto.
// Aparece con retraso para que una respuesta rápida no parpadee.
export function Loader({ code = 'Recuperando registros', label = 'Cargando', rows = 3 }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setShown(true), 150);
    return () => clearTimeout(timer);
  }, []);
  return (
    <div className="loader" role="status" style={{ visibility: shown ? 'visible' : 'hidden' }}>
      <span className="sr-only">{label}</span>
      <span className="label loader-code" aria-hidden="true">{code}</span>
      <Sweep />
      {Array.from({ length: rows }, (_, index) => <div key={index} className="skeleton" aria-hidden="true" />)}
    </div>
  );
}

export function Sweep() {
  return (
    <span className="sweep" aria-hidden="true">
      {Array.from({ length: 18 }, (_, index) => <i key={index} style={{ '--n': index }} />)}
    </span>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="alert" role="alert">
      <p style={{ margin: 0 }}>{error?.message ?? 'No pudimos cargar los datos.'}</p>
      {onRetry && <button type="button" className="text-link" style={{ marginTop: 10 }} onClick={onRetry}>Reintentar</button>}
    </div>
  );
}

export function Empty({ title, children }) {
  return (
    <div className="panel empty">
      <Icon name="radar" />
      <h2 className="h-panel">{title}</h2>
      <div className="muted" style={{ maxWidth: 460 }}>{children}</div>
    </div>
  );
}

// Número que cuenta hasta su valor al aparecer.
export function CountUp({ value, duration = 900 }) {
  const [shown, setShown] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return undefined;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setShown(value); return undefined; }
    const start = performance.now();
    const origin = from.current;
    let frame = requestAnimationFrame(function step(now) {
      const progress = Math.min(1, (now - start) / duration);
      const current = Math.round(origin + (value - origin) * (1 - (1 - progress) ** 3));
      setShown(current);
      from.current = current;
      if (progress < 1) frame = requestAnimationFrame(step);
    });
    return () => cancelAnimationFrame(frame);
  }, [value, duration]);
  return typeof value === 'number' && Number.isFinite(value) ? shown.toLocaleString('es-PE') : '—';
}

// Barra de segmentos (0–100) que se enciende en orden.
export function SegmentBar({ value, cells = 20, color }) {
  const lit = Math.round(((value ?? 0) / 100) * cells);
  return (
    <span className="bar" style={{ '--cells': cells, '--c': color }} aria-hidden="true">
      {Array.from({ length: cells }, (_, index) => (
        <i key={index} className={index < lit ? 'on' : undefined} style={{ '--n': index }} />
      ))}
    </span>
  );
}
