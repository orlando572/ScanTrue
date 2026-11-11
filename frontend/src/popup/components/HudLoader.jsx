// Estado de carga estándar de las vistas: rótulo mono con barrido de segmentos y el esqueleto
// de lo que va a aparecer, recorrido por una línea de escaneo. El texto completo (`label`)
// queda para lectores de pantalla; a la vista solo hay un rótulo corto (`code`).
// Aparece con un breve retraso para que una respuesta rápida no produzca un parpadeo.

const SEGMENTS = 14;

export function LoaderSweep({ className = '' }) {
  return <span className={`hud-loader-sweep ${className}`} aria-hidden="true">
    {Array.from({ length: SEGMENTS }, (_, index) => <i key={index} style={{ '--i': index }} />)}
  </span>;
}

function Skeleton({ shape, count }) {
  if (shape === 'rows') {
    return <ul className="hud-loader-rows" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => <li key={index} style={{ '--i': index }}>
        <b className="hud-skeleton hud-skeleton--index" />
        <span className="flex-1">
          <b className="hud-skeleton hud-skeleton--short" />
          <b className="hud-skeleton" />
          <b className="hud-skeleton hud-skeleton--mid" />
        </span>
        <b className="hud-skeleton hud-skeleton--value" />
      </li>)}
    </ul>;
  }
  if (shape === 'account') {
    return <div className="hud-loader-account" aria-hidden="true">
      <b className="hud-skeleton hud-skeleton--avatar" />
      <b className="hud-skeleton hud-skeleton--mid" />
      <b className="hud-skeleton hud-skeleton--short" />
    </div>;
  }
  return <div className="hud-loader-panels" aria-hidden="true">
    {Array.from({ length: count }, (_, index) => <div key={index} className="hud-panel hud-loader-panel" style={{ '--i': index }}>
      <b className="hud-skeleton hud-skeleton--short" />
      <b className="hud-skeleton hud-skeleton--big" />
      <b className="hud-skeleton hud-skeleton--bar" />
      <b className="hud-skeleton hud-skeleton--mid" />
    </div>)}
  </div>;
}

export default function HudLoader({ label, code, shape = 'panels', count = 2, className = 'mt-6' }) {
  return <div className={`hud-loader ${className}`} role="status" aria-live="polite">
    <span className="sr-only">{label}</span>
    <div className="hud-loader-head" aria-hidden="true">
      <span className="hud-loader-code">{code}</span>
      <LoaderSweep />
    </div>
    <Skeleton shape={shape} count={count} />
  </div>;
}
