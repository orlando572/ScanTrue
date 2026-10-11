import { presentBreakdown } from '../result-presentation.js';

function ModelIcon({ model }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {model === 'bilstm' ? <><path d="M7 6h10M7 18h10M5 8v8M19 8v8M7 7l10 10M17 7 7 17" /><rect x="3" y="3" width="4" height="4" rx="1" /><rect x="17" y="3" width="4" height="4" rx="1" /><rect x="3" y="17" width="4" height="4" rx="1" /><rect x="17" y="17" width="4" height="4" rx="1" /></>
      : <><path d="M9 20v-3H7a5 5 0 0 1-2-9 7 7 0 0 1 13-1 5 5 0 0 1 1 9v4" /><path d="M10 10h5M10 14h5M12.5 10v4M15 14v6" /><circle cx="10" cy="10" r="1" fill="currentColor" stroke="none" /><circle cx="15" cy="14" r="1" fill="currentColor" stroke="none" /></>}
  </svg>;
}

function ModelCard({ model }) {
  const { key, name, percentage, value, classification, level } = model;
  return <article className={`breakdown-model breakdown-model--${classification ?? 'neutral'}`}>
    <div className="breakdown-model-header">
      <span className="breakdown-model-icon"><ModelIcon model={key} /></span>
      <h2 className="text-sm font-semibold text-ink">{name}</h2>
      {classification && <span className="breakdown-model-badge" aria-label={`Clasificación del modelo: ${classification}`}>{classification.toUpperCase()}</span>}
    </div>
    {percentage !== null ? <>
      <div className="breakdown-model-result">
        <p className="breakdown-model-percentage" aria-label={`${percentage} de salida para falsa de ${name}`}>{percentage}</p>
        <p className="breakdown-model-caption">{level}</p>
      </div>
      <div className="breakdown-model-track" aria-hidden="true"><span style={{ width: `${value}%` }} /></div>
    </> : <p className="breakdown-model-unavailable">No disponible</p>}
  </article>;
}

export default function BreakdownScreen({ result, onBack }) {
  const { models, noneAvailable } = presentBreakdown(result);

  return <section>
    <div className="flex items-start gap-3">
      <button type="button" className="breakdown-back" aria-label="Volver al resultado" title="Volver al resultado" onClick={onBack}>
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m14 5-7 7 7 7" /></svg>
      </button>
      <h1 className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Desglose por modelo</h1>
    </div>

    <div className="breakdown-sheet mt-6">
      {models.map((model) => <ModelCard key={model.key} model={model} />)}
    </div>
    {noneAvailable && <p className="mt-4 text-sm leading-5 text-muted">No hay resultados por modelo disponibles</p>}
    <p className="breakdown-note">Los modelos analizan las palabras y su contexto, pero no comprueban los hechos con fuentes externas.</p>
  </section>;
}
