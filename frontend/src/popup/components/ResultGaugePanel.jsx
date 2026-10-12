const circumference = 2 * Math.PI * 56;

function FaceIcon({ expression }) {
  const eyes = expression === 'joyful'
    ? <><path d="M13 21c2-3 5-3 7 0" /><path d="M28 21c2-3 5-3 7 0" /></>
    : <><circle cx="17" cy="20" r="1.5" fill="currentColor" stroke="none" /><circle cx="31" cy="20" r="1.5" fill="currentColor" stroke="none" /></>;
  const mouths = {
    joyful: <path d="M13 28c3 9 19 9 22 0" />,
    smile: <path d="M16 29c3 5 13 5 16 0" />,
    neutral: <path d="M17 31h14" />,
    sad: <path d="M16 34c4-6 12-6 16 0" />,
    crying: <><path d="M16 35c4-6 12-6 16 0" /><path d="M35 23c0 3-3 6-3 9a3 3 0 0 0 6 0c0-3-3-6-3-9Z" fill="currentColor" stroke="none" /></>,
  };
  return <svg className="result-level-icon" aria-hidden="true" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><circle cx="24" cy="24" r="19" />{eyes}{mouths[expression]}</svg>;
}

export default function ResultGaugePanel({ level, percentage, className = '' }) {
  return <div className={`result-panel ${className} ${level ? `result-panel--gauge result-panel--${level.tone}` : 'result-panel--empty'}`}>
    {level ? <div className="result-summary">
      <div className="result-gauge">
        <svg viewBox="0 0 140 140" aria-hidden="true">
          <circle className="result-gauge-track" cx="70" cy="70" r="56" />
          {level.value > 0 && <circle className="result-gauge-progress" cx="70" cy="70" r="56" strokeDasharray={`${circumference * level.value / 100} ${circumference}`} />}
        </svg>
        <span className="result-gauge-value" aria-label={`${percentage} de salida para falsa`}>{level.value}<span>%</span></span>
      </div>
      <div className="result-verdict">
        <p className="result-verdict-label">{level.label}</p>
        <FaceIcon expression={level.icon} />
      </div>
    </div> : <p className="text-base leading-[22px] font-semibold text-ink">Resultado unificado no disponible</p>}
  </div>;
}
