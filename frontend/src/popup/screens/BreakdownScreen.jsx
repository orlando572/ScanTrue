import { presentBreakdown } from '../result-presentation.js';

function ModelRow({ name, percentage }) {
  return <div className="breakdown-model">
    <h2 className="text-base leading-[22px] font-semibold text-ink">{name}</h2>
    {percentage !== null ? <>
      <p className="mt-2 text-sm leading-5 text-muted">Salida para falsa</p>
      <p className="mt-1 text-[32px] leading-9 font-semibold tracking-[-0.03em] tabular-nums text-false" aria-label={`${percentage} de salida para falsa de ${name}`}>{percentage}</p>
    </> : <p className="mt-3 text-sm leading-5 text-muted">No disponible</p>}
  </div>;
}

export default function BreakdownScreen({ result, onBack }) {
  const { models, comparison, noneAvailable } = presentBreakdown(result);

  return <section>
    <div className="flex items-start gap-3">
      <button type="button" className="breakdown-back" aria-label="Volver al resultado" title="Volver al resultado" onClick={onBack}>
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m14 5-7 7 7 7" /></svg>
      </button>
      <h1 className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Desglose por modelo</h1>
    </div>

    <div className="breakdown-sheet mt-6">
      {models.map((model) => <ModelRow key={model.key} name={model.name} percentage={model.percentage} />)}
      {comparison && <p className="flex items-center gap-2 border-t border-line pt-5 text-sm leading-5 text-ink"><span className="size-2 shrink-0 rounded-full bg-accent" aria-hidden="true" />{comparison}</p>}
    </div>
    {noneAvailable && <p className="mt-4 text-sm leading-5 text-muted">No hay resultados por modelo disponibles</p>}
  </section>;
}
