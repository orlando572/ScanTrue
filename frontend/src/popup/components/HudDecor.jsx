// Gráficos vectoriales decorativos. Todos son aria-hidden: no aportan información.

const SEGMENTS = 40;

// Constelación del núcleo: [x, y, color, ritmo en segundos], con el centro en 0,0.
const NODES = [
  [-46, -30, 'var(--color-accent)', 3.4],
  [-12, -54, 'var(--color-acid)', 2.6],
  [38, -40, 'var(--color-accent)', 4.1],
  [58, 6, 'var(--color-coral)', 3],
  [26, 46, 'var(--color-accent)', 3.7],
  [-30, 46, 'var(--color-acid)', 2.9],
  [-58, 10, 'var(--color-accent)', 4.4],
];
const LINKS = [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 0], [0, 5], [2, 4]];

// Núcleo de escaneo: la pieza propia de la extensión, hecha con los elementos de la web.
// Un aro de 40 segmentos (el del dial) recorrido por una luz, una constelación que late,
// la mira ácida que gira y una onda de radar coral que sale del centro. Con `active`
// (análisis en curso) todo va más deprisa.
export function ScanCore({ active = false }) {
  return <div className={`scan-core${active ? ' scan-core--active' : ''}`} aria-hidden="true">
    <svg viewBox="0 0 200 200" fill="none">
      <g transform="translate(100 100)">
        <g>
          {Array.from({ length: SEGMENTS }, (_, index) => <rect key={index} className="scan-core-seg" style={{ '--i': index }} x="82" y="-2.5" width="14" height="5" transform={`rotate(${-90 + (360 / SEGMENTS) * index})`} />)}
        </g>
        <circle className="scan-core-orbit" r="72" />
        {LINKS.map(([from, to], index) => <line key={index} className="scan-core-link" style={{ '--i': index }} x1={NODES[from][0]} y1={NODES[from][1]} x2={NODES[to][0]} y2={NODES[to][1]} />)}
        {NODES.map(([x, y, color, rhythm], index) => <rect key={index} className="scan-core-node" style={{ '--i': index, '--c': color, '--d': `${rhythm}s` }} x={x - 2} y={y - 2} width="4" height="4" />)}
        <circle className="scan-core-pulse" r="72" />
        <circle className="scan-core-pulse scan-core-pulse--b" r="60" />
        <path className="scan-core-reticle" d="M24 0h8M-24 0h-8M0 24v8M0-24v-8" />
        <g className="scan-core-reticle-spin">
          <path className="scan-core-reticle" d="M16 0A16 16 0 0 1-4.94 15.22M-16 0A16 16 0 0 1 4.94-15.22" />
        </g>
        <rect className="scan-core-eye" x="-3" y="-3" width="6" height="6" />
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
