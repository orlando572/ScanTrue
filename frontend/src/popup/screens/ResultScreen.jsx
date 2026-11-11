import { presentResult } from '../result-presentation.js';
import ResultGaugePanel from '../components/ResultGaugePanel.jsx';
import ScreenHeader, { ChevronIcon } from '../components/ScreenHeader.jsx';

export default function ResultScreen({ result, onBack, onBreakdown, onStartOver, clearing, error }) {
  const { percentage, level, hasBreakdown } = presentResult(result);

  return <section className="flex flex-1 flex-col">
    <ScreenHeader title="Resultado del análisis" backLabel="Volver al texto" onBack={onBack} />

    <ResultGaugePanel level={level} percentage={percentage} className="mt-5" />

    {hasBreakdown && <button type="button" className="result-detail mt-4" onClick={onBreakdown}>
      <span>Ver desglose por modelo</span>
      <ChevronIcon />
    </button>}

    <div className="mt-auto pt-8">
      {error && <p className="hud-alert mb-3 text-[12px] leading-[18px]" role="alert">{error}</p>}
      <button type="button" className="primary-button" onClick={onStartOver} disabled={clearing}>{clearing ? 'Preparando nueva selección…' : 'Escoger otro texto'}</button>
    </div>
  </section>;
}
