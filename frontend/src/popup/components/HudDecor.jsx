import { useEffect, useRef } from 'react';

// Gráficos vectoriales decorativos. Todos son aria-hidden: no aportan información.

const IRIS_SEGMENTS = 28;
// Contorno del ojo y marco del logo (scantrue-mark.svg), ampliados y centrados en 0,0.
const EYE = 'M-64 0c19-31 41-44 64-44s45 13 64 44c-19 31-41 44-64 44s-45-13-64-44z';
const FRAME = 'M-44-84H62l22 22V44L44 84H-62l-22-22V-44z';
// Cuánto se desplaza la mirada (en unidades del dibujo) y cuánto dura tras mover el ratón.
const LOOK_X = 20;
const LOOK_Y = 7;
const TRACK_MS = 2200;

// Ojo de escaneo: el logo de ScanTrue ampliado y vivo. Marco de esquinas cortadas, contorno
// del ojo, iris de segmentos recorrido por una luz y pupila ácida con la mira girando.
// Parpadea, mira a los lados como leyendo y sigue al puntero cuando se mueve sobre el panel;
// una línea de escaneo lo recorre y de la pupila sale una onda coral. Con `active`
// (análisis en curso) lee sin parar y no parpadea.
export function ScanEye({ active = false }) {
  const root = useRef(null);

  useEffect(() => {
    const element = root.current;
    if (active || !element || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined;
    let timer;
    const rest = () => {
      element.classList.remove('scan-eye--tracking');
      element.style.removeProperty('--gx');
      element.style.removeProperty('--gy');
    };
    const follow = (event) => {
      const box = element.getBoundingClientRect();
      const dx = event.clientX - (box.left + box.width / 2);
      const dy = event.clientY - (box.top + box.height / 2);
      const reach = Math.max(box.width, 1);
      element.style.setProperty('--gx', (Math.max(-1, Math.min(1, dx / reach)) * LOOK_X).toFixed(1));
      element.style.setProperty('--gy', (Math.max(-1, Math.min(1, dy / reach)) * LOOK_Y).toFixed(1));
      element.classList.add('scan-eye--tracking');
      clearTimeout(timer);
      timer = setTimeout(rest, TRACK_MS);
    };
    window.addEventListener('pointermove', follow, { passive: true });
    return () => { window.removeEventListener('pointermove', follow); clearTimeout(timer); rest(); };
  }, [active]);

  return <div ref={root} className={`scan-eye${active ? ' scan-eye--active' : ''}`} aria-hidden="true">
    <svg viewBox="0 0 200 200" fill="none">
      <defs><clipPath id="scan-eye-shape"><path d={EYE} /></clipPath></defs>
      <g transform="translate(100 100)">
        <path className="scan-eye-frame" d={FRAME} />
        <path className="scan-eye-ticks" d="M-78 0h8M70 0h8M0-78v8M0 70v8" />
        <g className="scan-eye-lids">
          <g clipPath="url(#scan-eye-shape)">
            <path className="scan-eye-white" d={EYE} />
            <g className="scan-eye-look">
              <g className="scan-eye-gaze">
                <g>
                  {Array.from({ length: IRIS_SEGMENTS }, (_, index) => <rect key={index} className="scan-eye-seg" style={{ '--i': index }} x="24" y="-2" width="11" height="4" transform={`rotate(${-90 + (360 / IRIS_SEGMENTS) * index})`} />)}
                </g>
                <circle className="scan-eye-pulse" r="34" />
                <g className="scan-eye-reticle-spin">
                  <path className="scan-eye-reticle" d="M17 0A17 17 0 0 1-5.25 16.17M-17 0A17 17 0 0 1 5.25-16.17" />
                </g>
                <circle className="scan-eye-pupil" r="8" />
              </g>
            </g>
            <path className="scan-eye-scan" d="M-70 0H70" />
          </g>
          <path className="scan-eye-outline" d={EYE} />
        </g>
      </g>
    </svg>
  </div>;
}

// Tira bajo la cabecera: una luz por servicio real de /salud y el resumen del estado de
// la API con su latencia.
export function LedStrip({ health = 'checking', code, label, latency, services = [] }) {
  return <div className="led-strip">
    <ul className="service-lights" aria-label="Servicios">
      {services.map((service) => <li key={service.key} className={`service-light service-light--${service.state}`} style={{ '--svc': service.color ?? undefined }} title={service.label}>
        <i aria-hidden="true" />
        <span className="service-name" aria-hidden="true">{service.short}</span>
        <span className="sr-only">{service.label}</span>
      </li>)}
    </ul>
    <span className={`led-strip-status led-strip-status--${health}`} role="status" aria-live="polite" title={label}>
      <span className={`status-dot status-dot--${health}`} aria-hidden="true" />
      <span aria-hidden="true">{code}{latency != null && health !== 'unavailable' && health !== 'checking' ? <b className="latency"> · {latency} ms</b> : null}</span>
      <span className="sr-only">{label}</span>
    </span>
  </div>;
}

// `marker` (0–100) dibuja una muesca de referencia, p. ej. el mínimo de palabras.
export function SegmentTrack({ value, segments = 20, marker }) {
  const lit = Math.round((Math.max(0, Math.min(100, value)) / 100) * segments);
  return <div className={`segment-track${marker !== undefined ? ' segment-track--marked' : ''}`} aria-hidden="true">
    {Array.from({ length: segments }, (_, index) => <i key={index} className={index < lit ? 'on' : ''} style={{ '--i': index }} />)}
    {marker !== undefined && <b className="segment-marker" style={{ left: `${marker}%` }} />}
  </div>;
}
