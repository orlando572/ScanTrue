const SEGMENTS = 40;
const START = -135;
const SWEEP = 270;
const tones = ['very-low', 'low', 'middle', 'high', 'very-high'];

function polar(radius, degrees) {
  const radians = (degrees * Math.PI) / 180;
  return [90 + radius * Math.sin(radians), 90 - radius * Math.cos(radians)];
}

function Segment({ index, on }) {
  const angle = START + ((index + .5) * SWEEP) / SEGMENTS;
  const [x1, y1] = polar(58, angle);
  const [x2, y2] = polar(70, angle);
  return <line className={`result-gauge-segment${on ? ' result-gauge-segment--on' : ''}`} x1={x1} y1={y1} x2={x2} y2={y2} />;
}

function Dial({ value }) {
  const lit = Math.round((value / 100) * SEGMENTS);
  const needle = START + (value / 100) * SWEEP;
  const [n1x, n1y] = polar(44, needle);
  const [n2x, n2y] = polar(53, needle);
  return <svg viewBox="0 0 180 180" aria-hidden="true">
    <circle className="result-gauge-reticle" cx="90" cy="90" r="48" strokeDasharray="2 5" />
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
    <line className="result-gauge-needle" x1={n1x} y1={n1y} x2={n2x} y2={n2y} />
  </svg>;
}

// Glifos vectoriales para los cinco niveles; conservan el mismo mapeo de `icon`.
function LevelGlyph({ expression }) {
  const eyes = expression === 'joyful'
    ? <><path d="M14 21l3-4 3 4" /><path d="M28 21l3-4 3 4" /></>
    : <><path d="M15 19h4v3h-4z" fill="currentColor" stroke="none" /><path d="M29 19h4v3h-4z" fill="currentColor" stroke="none" /></>;
  const mouths = {
    joyful: <path d="M14 28l4 6h12l4-6" />,
    smile: <path d="M16 29l3 4h10l3-4" />,
    neutral: <path d="M17 31h14" />,
    sad: <path d="M16 34l3-4h10l3 4" />,
    crying: <><path d="M16 35l3-4h10l3 4" /><path d="M35 24l2.5 4-2.5 4-2.5-4z" fill="currentColor" stroke="none" /></>,
  };
  return <svg className="result-level-icon" aria-hidden="true" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="square" strokeLinejoin="miter">
    <path d="M24 3l18 10.5v21L24 45 6 34.5v-21z" />{eyes}{mouths[expression]}
  </svg>;
}

export default function ResultGaugePanel({ level, percentage, className = '' }) {
  const rank = level ? tones.indexOf(level.tone) : -1;
  return <div className={`result-panel hud-panel ${className} ${level ? `result-panel--gauge result-panel--${level.tone}` : 'result-panel--empty'}`}>
    {level ? <>
      <div className="result-summary">
        <div className="result-gauge">
          <Dial value={level.value} />
          <span className="result-gauge-value" aria-label={`${percentage} de salida para falsa`}>{level.value}<span>%</span></span>
        </div>
        <div className="result-verdict">
          <LevelGlyph expression={level.icon} />
          <p className="result-verdict-label">{level.label}</p>
          <div className="w-full" aria-hidden="true">
            <div className="level-scale">{tones.map((tone, index) => <span key={tone} className={index <= rank ? 'on' : ''} />)}</div>
            <span className="hud-readout mt-1.5 block">Nivel {rank + 1}/5</span>
          </div>
        </div>
      </div>
    </> : <p className="hud-readout text-sm">Resultado unificado no disponible</p>}
  </div>;
}
