import { presentResult } from '../result-presentation.js';

export default function ResultScreen({ result, onBreakdown, onStartOver, clearing, error }) {
  const { percentage, source, comparison, hasBreakdown } = presentResult(result);

  return <section className="flex flex-1 flex-col">
    <h1 className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Resultado del análisis</h1>

    <div className={`result-panel mt-6 ${percentage ? '' : 'result-panel--empty'}`}>
      {percentage ? <>
        <p className="text-sm font-semibold text-false">Salida para falsa</p>
        <p className="mt-3 text-[40px] leading-[44px] font-semibold tracking-[-0.04em] tabular-nums text-false" aria-label={`${percentage} de salida para falsa`}>{percentage}</p>
        {source && <p className="mt-4 text-sm leading-5 text-muted">{source}</p>}
      </> : <p className="text-base leading-[22px] font-semibold text-ink">Resultado unificado no disponible</p>}
      {comparison && <p className="mt-5 flex items-center gap-2 text-sm leading-5 text-ink"><span className="size-2 shrink-0 rounded-full bg-accent" aria-hidden="true" />{comparison}</p>}
    </div>

    {hasBreakdown && <button type="button" className="result-detail mt-5" onClick={onBreakdown}>
      <span>Ver desglose por modelo</span>
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m9 5 7 7-7 7" /></svg>
    </button>}

    <div className="mt-auto pt-8">
      {error && <p className="mb-3 text-[12px] leading-[18px] text-false" role="alert">{error}</p>}
      <button type="button" className="primary-button" onClick={onStartOver} disabled={clearing}>{clearing ? 'Preparando nueva selección…' : 'Escoger otro texto'}</button>
    </div>
  </section>;
}
