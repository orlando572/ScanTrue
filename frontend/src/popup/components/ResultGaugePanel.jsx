import { useEffect, useState } from 'react';

const SEGMENTS = 40;
const START = -135;
const SWEEP = 270;
const COUNT_MS = 1000;
const tones = ['very-low', 'low', 'middle', 'high', 'very-high'];

function polar(radius, degrees) {
  const radians = (degrees * Math.PI) / 180;
  return [90 + radius * Math.sin(radians), 90 - radius * Math.cos(radians)];
}

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

// Cuenta de 0 al valor final al mismo ritmo que la aguja; con movimiento reducido, valor fijo.
function useCountUp(target) {
  const [shown, setShown] = useState(() => (prefersReducedMotion() ? target : 0));
  useEffect(() => {
    if (prefersReducedMotion()) { setShown(target); return undefined; }
    let frame;
    const started = performance.now();
    const tick = (now) => {
      const progress = Math.min(1, (now - started) / COUNT_MS);
      setShown(Math.round(target * (1 - (1 - progress) ** 3)));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target]);
  return shown;
}

function Segment({ index, on }) {
  const angle = START + ((index + .5) * SWEEP) / SEGMENTS;
  const [x1, y1] = polar(58, angle);
  const [x2, y2] = polar(70, angle);
  return <line className={`result-gauge-segment${on ? ' result-gauge-segment--on' : ''}`} style={on ? { '--i': index } : undefined} x1={x1} y1={y1} x2={x2} y2={y2} />;
}

function Dial({ value }) {
  const lit = Math.round((value / 100) * SEGMENTS);
  const needle = START + (value / 100) * SWEEP;
  return <svg viewBox="0 0 180 180" aria-hidden="true">
    <g className="result-gauge-reticle-spin">
      <circle className="result-gauge-reticle" cx="90" cy="90" r="48" strokeDasharray="2 5" />
    </g>
    <path className="result-gauge-reticle" d="M90 30v12M90 138v12M30 90h12M138 90h12" />
    {Array.from({ length: SEGMENTS }, (_, index) => <Segment key={index} index={index} on={index < lit} />)}
    {Array.from({ length: 11 }, (_, step) => {
      const angle = START + step * (SWEEP / 10);
      const major = step % 5 === 0;
      const [x1, y1] = polar(74, angle);
      const [x2, y2] = polar(major ? 82 : 78, angle);
      return <line key={step} className={`result-gauge-tick${major ? ' result-gauge-tick--major' : ''}`} x1={x1} y1={y1} x2={x2} y2={y2} />;
    })}
    {[0, 50, 100].map((mark) => {
      const [x, y] = polar(90, START + (mark / 100) * SWEEP);
      return <text key={mark} className="result-gauge-scale" x={x} y={y + 3} textAnchor="middle">{mark}</text>;
    })}
    {/* La aguja se dibuja vertical y se gira: así puede barrer el arco desde 0. */}
    <g className="result-gauge-needle-arm" style={{ '--needle': `${needle}deg` }}>
      <line className="result-gauge-needle" x1="90" y1="46" x2="90" y2="37" />
    </g>
  </svg>;
}

// Glifos de estado dentro del hexágono, de menos a más señales de falsedad.
// Los extremos llevan un segundo hexágono interior para distinguirlos de los niveles 2 y 4.
const symbols = {
  'check-double': <><path pathLength="1" d="M24 10l12.2 7v14L24 38l-12.2-7V17z" /><path pathLength="1" d="M17.5 24.5l4.5 4.5 9-10" /></>,
  check: <path pathLength="1" d="M15 24.5l6 6 12-13" />,
  question: <><path pathLength="1" d="M18.5 19.5a5.5 5.5 0 1 1 8 4.9c-1.7.9-2.5 1.9-2.5 3.9v1" /><path d="M22.6 33.2h2.8v2.8h-2.8z" fill="currentColor" stroke="none" /></>,
  alert: <><path pathLength="1" d="M24 13.5v14" /><path d="M22.6 31.5h2.8v2.8h-2.8z" fill="currentColor" stroke="none" /></>,
  cross: <><path pathLength="1" d="M24 10l12.2 7v14L24 38l-12.2-7V17z" /><path pathLength="1" d="M19 19l10 10M29 19 19 29" /></>,
};

function LevelGlyph({ icon }) {
  return <span className={`result-level-icon result-level-icon--${icon}`} aria-hidden="true">
    <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="square" strokeLinejoin="miter">
      <path className="result-level-ring" d="M24 3l18 10.5v21L24 45 6 34.5v-21z" />
      <path pathLength="1" d="M24 3l18 10.5v21L24 45 6 34.5v-21z" />
      <g className="result-level-symbol">{symbols[icon]}</g>
    </svg>
  </span>;
}

export default function ResultGaugePanel({ level, percentage, className = '' }) {
  const rank = level ? tones.indexOf(level.tone) : -1;
  const counted = useCountUp(level?.value ?? 0);
  return <div className={`result-panel hud-panel ${className} ${level ? `result-panel--gauge result-panel--${level.tone}` : 'result-panel--empty'}`}>
    {level ? <>
      <div className="result-summary">
        <div className="result-gauge">
          <Dial value={level.value} />
          {/* Solo las cifras se centran en el dial; el «%» cuelga a la derecha. */}
          <span className={`result-gauge-value${level.value === 100 ? ' result-gauge-value--wide' : ''}`} aria-label={`${percentage} de salida para falsa`}>
            <span aria-hidden="true">{counted}<small>%</small></span>
          </span>
          {/* Bajo la regla 0/100, en el hueco inferior del arco: no pisa los segmentos. */}
          <span className="result-gauge-caption" aria-hidden="true">Salida para falsa</span>
        </div>
        <div className="result-verdict">
          <LevelGlyph icon={level.icon} />
          <p className="result-verdict-label">{level.label}</p>
          <div className="w-full" aria-hidden="true">
            <div className="level-scale">{tones.map((tone, index) => <span key={tone} className={index <= rank ? 'on' : ''} style={{ '--i': index }} />)}</div>
            <span className="hud-readout mt-1.5 block">Nivel {rank + 1}/5</span>
          </div>
        </div>
      </div>
    </> : <p className="hud-readout text-sm">Resultado unificado no disponible</p>}
  </div>;
}
