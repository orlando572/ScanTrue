export function BackIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="square" strokeLinejoin="miter"><path d="m14 5-7 7 7 7" /></svg>;
}

export function ChevronIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="square" strokeLinejoin="miter"><path d="m9 5 7 7-7 7" /></svg>;
}

export default function ScreenHeader({ title, titleId, backLabel = 'Volver', onBack, disabled, children }) {
  return <div className="screen-header">
    <button type="button" className="hud-back" aria-label={backLabel} title={backLabel} onClick={onBack} disabled={disabled}><BackIcon /></button>
    <div className="min-w-0 flex-1">
      <h1 id={titleId} className="screen-title mt-1">{title}</h1>
      {children}
    </div>
  </div>;
}
