import { presentBreakdown } from '../result-presentation.js';
import ScreenHeader from '../components/ScreenHeader.jsx';
import { SegmentTrack } from '../components/HudDecor.jsx';
import ModelIcon from '../components/ModelIcon.jsx';

function ModelCard({ model }) {
  const { key, name, percentage, value, classification, level } = model;
  return <article className={`breakdown-model hud-panel breakdown-model--${classification ?? 'neutral'}`}>
    <div className="breakdown-model-header">
      <span className="breakdown-model-icon"><ModelIcon model={key} /></span>
      <h2 className="breakdown-model-name">{name}</h2>
      {classification && <span className="breakdown-model-badge" aria-label={`Clasificación del modelo: ${classification}`}>{classification.toUpperCase()}</span>}
    </div>
    {percentage !== null ? <>
      <div className="breakdown-model-result">
        <p className="breakdown-model-percentage" aria-label={`${percentage} de salida para falsa de ${name}`}>{percentage}</p>
        <p className="breakdown-model-caption">{level}</p>
      </div>
      <SegmentTrack value={value} />
    </> : <p className="breakdown-model-unavailable">No disponible</p>}
  </article>;
}

export default function BreakdownScreen({ result, onBack }) {
  const { models, noneAvailable } = presentBreakdown(result);

  return <section>
    <ScreenHeader title="Desglose por modelo" backLabel="Volver al resultado" onBack={onBack} />

    <div className="breakdown-sheet mt-5">
      {models.map((model) => <ModelCard key={model.key} model={model} />)}
    </div>
    {noneAvailable && <p className="mt-4 text-sm leading-5 text-muted">No hay resultados por modelo disponibles</p>}
    <p className="breakdown-note">Los modelos analizan las palabras y su contexto, pero no comprueban los hechos con fuentes externas.</p>
  </section>;
}
