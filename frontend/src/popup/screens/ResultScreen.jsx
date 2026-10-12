import { presentResult } from '../result-presentation.js';
import ResultGaugePanel from '../components/ResultGaugePanel.jsx';

export default function ResultScreen({ result, onBack, onBreakdown, onStartOver, clearing, error }) {
  const { percentage, level, hasBreakdown } = presentResult(result);

  return <section className="flex flex-1 flex-col">
    <div className="flex items-start gap-3">
      <button type="button" className="breakdown-back" aria-label="Volver al inicio" title="Volver al inicio" onClick={onBack}>
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m14 5-7 7 7 7" /></svg>
      </button>
      <h1 className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Resultado del análisis</h1>
    </div>

    <ResultGaugePanel level={level} percentage={percentage} className="mt-6" />

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
