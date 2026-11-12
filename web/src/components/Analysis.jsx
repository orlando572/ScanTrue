import { Link } from 'react-router-dom';
import { LEVELS } from '../lib/filters.js';
import { CRITERIA } from '../lib/presentation.js';
import { Icon } from './ui.jsx';

// Fragmentos marcados por el usuario: no hay título separado, solo el texto.
export function Fragments({ fragments, hidden = 0, clamp = false }) {
  return (
    <>
      <ol className="fragments">
        {fragments.map((fragment) => (
          <li key={fragment.number} className={`fragment${clamp ? ' fragment--clamp' : ''}`}>
            <span className="n" aria-hidden="true">#{fragment.number}</span>
            <p>{fragment.text}</p>
          </li>
        ))}
      </ol>
      {hidden > 0 && (
        <p className="label" style={{ marginTop: 12 }}>
          + {hidden} {hidden === 1 ? 'fragmento más' : 'fragmentos más'} en el detalle
        </p>
      )}
    </>
  );
}

export function Source({ view }) {
  if (!view.domain) return <span>Sin página de origen</span>;
  const content = <><i className="led" style={{ '--led': 'var(--color-acid)' }} />{view.domain}</>;
  return view.url
    ? <a className="source" href={view.url} target="_blank" rel="noopener noreferrer nofollow">{content}</a>
    : <span className="source">{content}</span>;
}

// Espectro Real–Incierto–Falso: BETO arriba, BiLSTM abajo y el combinado como rombo.
export function Spectrum({ view }) {
  const marks = Object.fromEntries(view.models.map((model) => [model.key, model.value]));
  const summary = [
    view.level ? `Combinado ${view.level.value} %` : null,
    ...view.models.filter((model) => model.value !== null).map((model) => `${model.name} ${model.value} %`),
  ].filter(Boolean).join(', ');
  return (
    <div className="spectrum" role="img" aria-label={`Salida para falsa. ${summary}`}>
      <div className="spectrum-track">
        {LEVELS.map((level) => <i key={level.value} className={`tone-${level.tone}`} />)}
      </div>
      {marks.mbert != null && <span className="marker marker--top" style={{ '--at': `${marks.mbert}%`, '--c': CRITERIA.mbert.color }} />}
      {marks.bilstm != null && <span className="marker marker--bottom" style={{ '--at': `${marks.bilstm}%`, '--c': CRITERIA.bilstm.color }} />}
      {view.level && <span className="marker marker--main" style={{ '--at': `${view.level.value}%` }} />}
    </div>
  );
}

// Los tres criterios: BiLSTM, BETO y la verificación web (aún sin activar).
export function CriteriaList({ view }) {
  return (
    <ul className="criteria">
      {view.models.map((model) => (
        <li key={model.key} style={{ '--c': model.color }}>
          <i className="led" />
          <span>{model.name}</span>
          {model.percentage
            ? <span className="v">{model.percentage}{model.classification ? ` · ${model.classification}` : ''}</span>
            : <span className="off">No disponible</span>}
        </li>
      ))}
      <li style={{ '--c': view.verification.state === 'none' ? 'var(--color-line-2)' : CRITERIA.web.color }}>
        <i className="led" />
        <span>Verif. web</span>
        <span className={view.verification.state === 'none' ? 'off' : 'v'}>{view.verification.label}</span>
      </li>
    </ul>
  );
}

const agreementTag = { agree: 'tag--ok', disagree: 'tag--warn', single: '' };
const chainTag = { ok: 'tag--ok', wait: '', fail: 'tag--fail' };

export function StatusTags({ view }) {
  return (
    <>
      <span className={`tag ${agreementTag[view.agreement.state]}`}>{view.agreement.label}</span>
      <span className={`tag ${chainTag[view.chain.state]}`}>{view.chain.label}</span>
    </>
  );
}

export function Verdict({ view }) {
  return (
    <div className="verdict">
      <span className="pct">{view.level ? view.level.value : '—'}<small> %</small></span>
      <span>
        <span className="lvl">{view.level?.label ?? 'Sin resultado unificado'}</span>
        <span className="label" style={{ display: 'block', marginTop: 4 }}>Salida para falsa</span>
      </span>
    </div>
  );
}

export function ResultCard({ view, to }) {
  return (
    <article className={`panel panel--tone card tone-${view.tone}`}>
      <div>
        <div className="card-meta">
          <span className="code">ID {view.code}</span>
          <span>{view.date}</span>
          <Source view={view} />
          {view.words && <span>{view.words}</span>}
          {view.truncated && <span className="tag" title="El texto superaba lo que leen los modelos; se analizó el comienzo.">Recortado</span>}
        </div>
        <Fragments fragments={view.fragments} hidden={view.hiddenFragments} clamp />
      </div>
      <div className="readout">
        <Verdict view={view} />
        <Spectrum view={view} />
        <CriteriaList view={view} />
        <div className="card-foot">
          <span className="chips"><StatusTags view={view} /></span>
          <Link className="text-link" to={to}>Ver detalle <span aria-hidden="true">→</span></Link>
        </div>
      </div>
    </article>
  );
}

// Dial de 40 segmentos en un arco de 270°, encendidos hasta el valor.
const SEGMENTS = 40;

export function Dial({ view }) {
  const value = view.level?.value ?? 0;
  const lit = Math.round((value / 100) * SEGMENTS);
  return (
    <div className="dial" role="img" aria-label={view.level ? `${view.level.value} % de salida para falsa: ${view.level.label}` : 'Sin resultado unificado'}>
      <svg viewBox="-110 -110 220 220">
        {Array.from({ length: SEGMENTS }, (_, index) => {
          const angle = -225 + (270 / (SEGMENTS - 1)) * index;
          return (
            <rect
              key={index}
              className={`seg${index < lit ? ' on' : ''}`}
              style={{ '--n': index }}
              x="84" y="-3" width="20" height="6"
              transform={`rotate(${angle})`}
            />
          );
        })}
        <circle r="74" fill="none" stroke="var(--color-line)" strokeDasharray="2 6" />
      </svg>
      <div className="dial-value">
        <b>{view.level ? view.level.value : '—'}<small> %</small></b>
        <span className="label" style={{ marginTop: 6 }}>Salida para falsa</span>
      </div>
    </div>
  );
}

export function CriterionIcon({ name }) {
  return (
    <span className="criterion-icon" style={{ '--c': CRITERIA[name].color }}>
      <Icon name={name} />
    </span>
  );
}
