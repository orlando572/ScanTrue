import { Link } from 'react-router-dom';
import { LEVELS } from '../lib/filters.js';
import { CRITERIA } from '../lib/presentation.js';
import { Icon } from './ui.jsx';

// Líneas que se muestran de cada fragmento en una tarjeta: se reparten unas 12 entre los
// que hay, para que uno o dos fragmentos largos llenen la tarjeta en vez de dejar un hueco.
function clampLines(count) {
  return count <= 1 ? 12 : count === 2 ? 6 : count === 3 ? 4 : 3;
}

// Fragmentos marcados por el usuario: no hay título separado, solo el texto.
// Con una sola parte no se numera: no hay nada que ordenar.
export function Fragments({ fragments, hidden = 0, clamp = false }) {
  const single = fragments.length === 1 && hidden === 0;
  return (
    <>
      <ol className="fragments" style={clamp ? { '--lines': clampLines(fragments.length) } : undefined}>
        {fragments.map((fragment) => (
          <li key={fragment.number} className={`fragment${clamp ? ' fragment--clamp' : ''}${single ? ' fragment--single' : ''}`}>
            {!single && <span className="n" aria-hidden="true">#{fragment.number}</span>}
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
// `ends` pone «Verdadera» y «Falsa» bajo los extremos (en el detalle).
export function Spectrum({ view, ends = false }) {
  const marks = Object.fromEntries(view.models.map((model) => [model.key, model.value]));
  const summary = [
    view.level ? `Combinado ${view.level.value} %` : null,
    ...view.models.filter((model) => model.value !== null).map((model) => `${model.name} ${model.value} %`),
  ].filter(Boolean).join(', ');
  return (
    <div className="spectrum" role="img" aria-label={`Probabilidad de ser falsa. ${summary}`}>
      <div className="spectrum-track">
        {LEVELS.map((level) => <i key={level.value} className={`tone-${level.tone}`} />)}
      </div>
      {marks.mbert != null && <span className="marker marker--top" style={{ '--at': `${marks.mbert}%`, '--c': CRITERIA.mbert.color }} />}
      {marks.bilstm != null && <span className="marker marker--bottom" style={{ '--at': `${marks.bilstm}%`, '--c': CRITERIA.bilstm.color }} />}
      {view.level && <span className="marker marker--main" style={{ '--at': `${view.level.value}%` }} />}
      {ends && <span className="spectrum-ends label" aria-hidden="true"><span>Verdadera</span><span>Falsa</span></span>}
    </div>
  );
}

// Los tres criterios: BiLSTM, BETO y la verificación web (apagada mientras no llegue).
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
      <li className={view.verification.state === 'none' ? 'is-off' : undefined} style={{ '--c': CRITERIA.web.color }}>
        <i className="led" />
        <span>Verif. web</span>
        <span className={view.verification.state === 'none' ? 'off' : 'v'}>{view.verification.label}</span>
      </li>
    </ul>
  );
}

const agreementTag = { agree: 'tag--ok', disagree: 'tag--warn', single: '' };
const chainTag = { ok: 'tag--ok', wait: '', fail: 'tag--fail' };

// `chain={false}` oculta el estado del registro en blockchain (la tarjeta pública no lo muestra).
export function StatusTags({ view, chain = true }) {
  return (
    <>
      <span className={`tag ${agreementTag[view.agreement.state]}`}>{view.agreement.label}</span>
      {chain && <span className={`tag ${chainTag[view.chain.state]}`}>{view.chain.label}</span>}
    </>
  );
}

export function Verdict({ view }) {
  return (
    <div className="verdict">
      <span className="pct">{view.level ? view.level.value : '—'}<small> %</small></span>
      <span>
        <span className="lvl">{view.level?.label ?? 'Sin resultado unificado'}</span>
        <span className="label" style={{ display: 'block', marginTop: 4 }}>Probabilidad de ser falsa</span>
      </span>
    </div>
  );
}

export function ResultCard({ view, to }) {
  return (
    <article className={`panel panel--tone card tone-${view.tone}`}>
      <div>
        <div className="card-meta">
          <span>{view.date}</span>
          <Source view={view} />
          {view.words && <span>{view.words}</span>}
        </div>
        <h3 className="h-panel card-text-label">Texto de la noticia</h3>
        <Fragments fragments={view.fragments} hidden={view.hiddenFragments} clamp />
      </div>
      <div className="readout">
        <Verdict view={view} />
        <Spectrum view={view} />
        <CriteriaList view={view} />
        <div className="card-foot">
          <span className="chips"><StatusTags view={view} chain={false} /></span>
          <Link className="btn btn--small card-link" to={to}>Ver detalle</Link>
        </div>
      </div>
      {/* Capa que hace clicable toda la tarjeta; el botón de arriba es el enlace accesible. */}
      <Link className="card-hit" to={to} tabIndex={-1} aria-hidden="true" />
    </article>
  );
}

// Dial de 40 segmentos en un arco de 270°, encendidos hasta el valor.
const SEGMENTS = 40;

export function Dial({ view }) {
  const value = view.level?.value ?? 0;
  const lit = Math.round((value / 100) * SEGMENTS);
  return (
    <div className="dial" role="img" aria-label={view.level ? `${view.level.value} % de probabilidad de ser falsa: ${view.level.label}` : 'Sin resultado unificado'}>
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
        <span className="label" style={{ marginTop: 6 }}>Probabilidad de ser falsa</span>
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
