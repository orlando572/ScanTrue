import { useMemo } from 'react';

// Gráficos vectoriales decorativos del HUD. Todos son aria-hidden: no aportan información.

const ticks = Array.from({ length: 72 }, (_, index) => index * 5);

function polar(radius, degrees, cx = 100, cy = 100) {
  const radians = (degrees * Math.PI) / 180;
  return [cx + radius * Math.sin(radians), cy - radius * Math.cos(radians)];
}

export function Radar({ active = false }) {
  const [sweepX, sweepY] = polar(92, 40);
  return <div className={`radar${active ? ' radar--active' : ''}`} aria-hidden="true">
    <svg viewBox="0 0 200 200" fill="none">
      <circle cx="100" cy="100" r="92" fill="#06101c" stroke="#38E1FF" strokeOpacity=".75" />
      {[68, 44, 20].map((radius) => <circle key={radius} cx="100" cy="100" r={radius} stroke="#1E3A5C" />)}
      <path d="M100 8v184M8 100h184" stroke="#1E3A5C" />
      <path d="M35 35l130 130M165 35 35 165" stroke="#1E3A5C" strokeDasharray="2 4" />
      {ticks.map((degrees) => {
        const major = degrees % 30 === 0;
        const [x1, y1] = polar(92, degrees);
        const [x2, y2] = polar(major ? 100 : 96, degrees);
        return <line key={degrees} x1={x1} y1={y1} x2={x2} y2={y2} stroke={major ? '#E6F4FF' : '#38E1FF'} strokeOpacity={major ? .9 : .45} />;
      })}
      {[['000', 100, -6], ['090', 211, 103], ['180', 100, 212], ['270', -11, 103]].map(([label, x, y]) => <text key={label} x={x} y={y} fill="#8FA8C4" fontFamily="Share Tech Mono, monospace" fontSize="8" textAnchor="middle">{label}</text>)}

      <g className="radar-sweep">
        <path d={`M100 100 L100 8 A92 92 0 0 1 ${sweepX} ${sweepY} Z`} fill="#38E1FF" fillOpacity=".16" />
        <line x1="100" y1="100" x2={sweepX} y2={sweepY} stroke="#38E1FF" strokeWidth="1.5" />
      </g>

      <circle className="radar-blip" cx="138" cy="58" r="3" fill="#FFB21E" />
      <circle className="radar-blip radar-blip--b" cx="52" cy="132" r="2.5" fill="#FF3D7F" />
      <circle className="radar-blip radar-blip--c" cx="146" cy="142" r="2.5" fill="#3DFF9A" />

      <g className="radar-target">
        <path d="M74 84v-6h6M126 84v-6h-6M74 116v6h6M126 116v6h-6" stroke="#FFB21E" strokeWidth="2" />
        <path d="M82 90h36M82 97h28M82 104h36M82 111h20" stroke="#E6F4FF" strokeOpacity=".7" strokeWidth="3" />
        <path d="M126 78l18-18h22" stroke="#FFB21E" />
        <text x="148" y="56" fill="#FFB21E" fontFamily="Share Tech Mono, monospace" fontSize="8">OBJ-01</text>
      </g>
      <circle cx="100" cy="100" r="2" fill="#38E1FF" />
    </svg>
  </div>;
}

// Tira bajo la cabecera: una luz por servicio real de /salud, un «bus de datos» animado
// y el resumen del estado de la API con su latencia.
export function LedStrip({ health = 'checking', code, label, latency, services = [] }) {
  // Ritmo de parpadeo propio y aleatorio para cada luz: nunca parpadean todas a la vez.
  const rhythms = useMemo(() => services.map(() => ({
    '--flicker-dur': `${(2.5 + Math.random() * 3.5).toFixed(2)}s`,
    '--flicker-delay': `${(-Math.random() * 6).toFixed(2)}s`,
  })), [services.length]);
  const live = services.filter((service) => service.state === 'ok').map((service) => service.color);
  const bus = { '--bus-a': live[0] ?? '#1e3a5c', '--bus-b': live[1] ?? live[0] ?? '#1e3a5c', '--bus-c': live[2] ?? live[0] ?? '#1e3a5c' };
  return <div className="led-strip">
    <ul className="service-lights" aria-label="Servicios">
      {services.map((service, index) => <li key={service.key} className={`service-light service-light--${service.state}`} style={{ '--svc': service.color ?? undefined, ...rhythms[index] }} title={service.label}>
        <i aria-hidden="true" />
        <span className="service-name" aria-hidden="true">{service.short}</span>
        <span className="sr-only">{service.label}</span>
      </li>)}
    </ul>
    <span className={`data-bus data-bus--${health}`} style={bus} aria-hidden="true" />
    <span className={`led-strip-status led-strip-status--${health}`} role="status" aria-live="polite" title={label}>
      <span className={`status-dot status-dot--${health}`} aria-hidden="true" />
      <span aria-hidden="true">{code}{latency != null && health !== 'unavailable' && health !== 'checking' ? <b className="latency"> · {latency} ms</b> : null}</span>
      <span className="sr-only">{label}</span>
    </span>
  </div>;
}

export function CoreGrid() {
  const cores = ['#38E1FF', '#FFB21E', '#FF3D7F'];
  const hex = ['3F·A9·0C·7E', 'B2·14·D8·61', '09·FF·3A·C4', '7D·52·E0·1B', 'C6·08·9A·F3', '41·BE·27·D5', '3F·A9·0C·7E'];
  return <div className="w-full" aria-hidden="true">
    <div className="core-grid">
      {cores.map((color) => <div key={color} className="core-cell">
        <div className="core-cell-bars" style={{ '--bar': color }}>{Array.from({ length: 7 }, (_, index) => <span key={index} />)}</div>
      </div>)}
    </div>
    <div className="hex-stream">{hex.map((line, index) => <span key={index}>{line}</span>)}</div>
  </div>;
}

// `marker` (0–100) dibuja una muesca de referencia, p. ej. el mínimo de palabras.
export function SegmentTrack({ value, segments = 20, marker }) {
  const lit = Math.round((Math.max(0, Math.min(100, value)) / 100) * segments);
  return <div className={`segment-track${marker !== undefined ? ' segment-track--marked' : ''}`} aria-hidden="true">
    {Array.from({ length: segments }, (_, index) => <i key={index} className={index < lit ? 'on' : ''} />)}
    {marker !== undefined && <b className="segment-marker" style={{ left: `${marker}%` }} />}
  </div>;
}
