import { useId, useState } from 'react';
import { presentInsights } from '../result-presentation.js';

const zones = ['very-low', 'low', 'middle', 'high', 'very-high'];

// Espectro Real–Falso: dónde cae cada modelo y el resultado combinado (rombo).
// BETO se marca encima de la regla y BiLSTM debajo para que no se tapen si coinciden.
// Al pie, si los modelos coinciden o no; el borde del panel toma ese color.
function Spectrum({ markers, level, consensus }) {
  const described = [...markers.map(({ name, value }) => `${name} ${value} %`), `combinado ${level.value} %`].join(', ');
  const state = consensus?.state ?? 'single';
  return <div className={`result-spectrum hud-panel result-panel--${level.tone} result-spectrum--${state}`}>
    <div className="result-spectrum-labels" aria-hidden="true"><span>Real</span><span>Incierto</span><span>Falso</span></div>
    <div className="result-spectrum-track" role="img" aria-label={`Posición en la escala de real a falso: ${described}`}>
      {zones.map((zone, index) => <i key={zone} className={`result-spectrum-zone result-spectrum-zone--${zone}${zone === level.tone ? ' on' : ''}`} style={{ '--i': index }} />)}
      {markers.map(({ key, name, value }) => <span key={key} className={`spectrum-marker spectrum-marker--${key}`} style={{ '--pos': value }} aria-hidden="true">
        <b>{name} {value}%</b>
      </span>)}
      <span className="spectrum-marker spectrum-marker--combined" style={{ '--pos': level.value }} aria-hidden="true" />
    </div>
    {consensus && <div className="result-consensus" role="note">
      <span className={`result-consensus-link${consensus.model ? ` result-consensus-link--${consensus.model}` : ''}`} aria-hidden="true"><i /><b /><i /></span>
      <p><strong>{consensus.title}</strong></p>
    </div>}
  </div>;
}

// `text` y `url` son el texto analizado y su página; `showText` muestra el fragmento y permite
// desplegar el texto completo (en P08 el texto ya está a la vista, arriba).
export default function ResultInsights({ result, level, text = null, url = null, showText = true }) {
  const { markers, consensus, reading, note } = presentInsights(result, text, url);
  const [textOpen, setTextOpen] = useState(false);
  const textPanel = useId();

  return <>
    {level && markers.length > 0 && <Spectrum markers={markers} level={level} consensus={consensus} />}
    {reading && <section className="result-reading hud-panel" aria-label="Lectura">
      <div className="result-reading-head">
        <span className="hud-code hud-code--cyan" aria-hidden="true">Lectura</span>
        {reading.words && <span className="result-reading-words">{reading.words}</span>}
      </div>
      {reading.domain && <p className="result-reading-source">
        <span className="sr-only">Página de origen: </span>
        <a href={reading.url} target="_blank" rel="noreferrer" title={reading.url}>{reading.domain}</a>
      </p>}
      {showText && reading.text && <>
        {textOpen
          ? <div id={textPanel} className="result-reading-text selection-preview" tabIndex="0" aria-label="Texto analizado">{reading.text}</div>
          : <blockquote className="result-reading-snippet">{reading.snippet}</blockquote>}
        <button type="button" className="result-reading-toggle" aria-expanded={textOpen} aria-controls={textPanel} onClick={() => setTextOpen((open) => !open)}>
          {textOpen ? 'Ocultar texto completo' : 'Ver texto completo'}
        </button>
      </>}
    </section>}
    {note && <p className="result-note">{note}</p>}
  </>;
}
