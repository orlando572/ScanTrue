import { Fragment, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  CriterionIcon, Dial, Fragments, Source, Spectrum, StatusTags,
} from '../components/Analysis.jsx';
import { ErrorState, Icon, Loader, SegmentBar } from '../components/ui.jsx';
import { publicApi } from '../lib/api.js';
import { useLoad } from '../lib/hooks.js';
import { CRITERIA, percent, presentAnalysis, readSplit } from '../lib/presentation.js';

const CHECKS = {
  registro_coincide: { tag: 'tag--ok', short: 'Coincide', text: 'El análisis no ha cambiado desde que se guardó.' },
  registro_no_coincide: { tag: 'tag--fail', short: 'No coincide', text: 'Lo guardado es distinto de lo que se muestra aquí.' },
  registro_pendiente: { tag: '', short: 'Pendiente', text: 'Todavía se está guardando. Prueba de nuevo en unos minutos.' },
  registro_no_enviado: { tag: '', short: 'Sin guardar', text: 'Este análisis no se guardó en blockchain.' },
  sin_confirmar: { tag: '', short: 'Pendiente', text: 'Ya se envió, pero falta que la red lo confirme. Prueba en unos minutos.' },
  blockchain_no_configurada: { tag: 'tag--warn', short: 'No disponible', text: 'Este servidor no tiene blockchain configurada, así que no se puede comprobar.' },
};
const CHECK_ERROR = { tag: 'tag--warn', short: 'Sin respuesta', text: 'No pudimos comprobarlo en este momento.' };

// Qué hace cada revisión, dicho sin tecnicismos (igual que en la portada).
const ROLES = {
  bilstm: 'Lee palabra por palabra',
  mbert: 'Lee cada palabra en su contexto',
  web: 'Busca en otras fuentes',
};

// Estado del guardado en blockchain, en una frase.
const CHAIN_TEXT = {
  ok: 'Este análisis quedó guardado en blockchain, así que nadie puede cambiarlo después.',
  wait: 'Se está guardando en blockchain. Cuando termine, nadie podrá cambiarlo.',
  fail: 'No se pudo guardar en blockchain.',
};

// La dirección de la noticia, legible (sin %C3%B3…); el enlace usa la original.
function readableUrl(url) {
  try { return decodeURI(url); } catch { return url; }
}

// Lo que respondió y lo que leyó un modelo: su texto es un prefijo del fragmento original.
// `simple`: versión del detalle público, sin versiones ni términos técnicos (Casos usa la completa).
export function ModelPanel({ model, output, original, simple = false }) {
  const split = readSplit(original, output?.texto_modelo);
  const reading = split ? (split.rest ? 'Leyó solo el comienzo: llegó a su límite' : 'Leyó el texto completo') : null;
  return (
    <article className="panel" style={{ '--edge': `color-mix(in srgb, ${model.color} 45%, var(--color-line))`, '--c': model.color }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <CriterionIcon name={model.key} />
        <div style={{ minWidth: 0 }}>
          <h3 className="h-panel" style={{ margin: 0, color: model.color }}>{model.name}</h3>
          <span className="label">{simple ? ROLES[model.key] : output?.version ?? 'Sin versión registrada'}</span>
        </div>
      </div>
      {model.percentage ? (
        <>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, margin: '16px 0 8px' }}>
            <span className="mono" style={{ fontSize: 30 }}>{model.percentage}</span>
            {model.classification && (
              <span className={`tag ${model.classification === 'falsa' ? 'tag--fail' : 'tag--ok'}`}>
                {simple ? `Dice: ${model.classification === 'falsa' ? 'falsa' : 'verdadera'}` : `Clase ${model.classification}`}
              </span>
            )}
          </div>
          {simple && <p className="label" style={{ margin: '0 0 10px' }}>Probabilidad de ser falsa</p>}
          <SegmentBar value={model.value} color={model.color} />
          <p className="label" style={{ margin: '12px 0 0' }}>
            {simple
              ? [model.level, reading].filter(Boolean).join(' · ')
              : `${model.level}${output?.tokens_leidos ? ` · ${output.tokens_leidos} ${model.key === 'mbert' ? 'subpalabras' : 'palabras'} leídas` : ''}`}
          </p>
          {split && (
            <details style={{ marginTop: 12 }}>
              <summary className="text-link">Ver el texto que leyó</summary>
              <p className="read-text">{split.read}<span className="rest">{split.rest}</span></p>
              {split.rest && <p className="label" style={{ margin: '8px 0 0' }}>En gris: lo que quedó fuera del límite de este modelo.</p>}
            </details>
          )}
        </>
      ) : <p className="muted" style={{ margin: '16px 0 0' }}>No disponible: este modelo no respondió en este análisis.</p>}
    </article>
  );
}

// Tercer criterio. Queda listo para el incremento 2: hoy siempre dice «aún no disponible».
// En el detalle público (`simple`) se ve apagado mientras no esté activo.
export function WebPanel({ verification, simple = false }) {
  const color = CRITERIA.web.color;
  const off = simple && verification.state === 'none';
  return (
    <article className={`panel${off ? ' panel--off' : ''}`} style={{ '--edge': `color-mix(in srgb, ${color} ${off ? 20 : 45}%, var(--color-line))`, '--c': color }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <CriterionIcon name="web" />
        <div style={{ minWidth: 0, flex: 1 }}>
          <h3 className="h-panel" style={{ margin: 0, color }}>{CRITERIA.web.name}</h3>
          <span className="label">{simple ? ROLES.web : 'Tercer criterio'}</span>
        </div>
      </div>
      {off ? (
        <>
          <span className="tag tag--warn" style={{ marginTop: 16 }}>Próximamente</span>
          <p className="muted" style={{ margin: '10px 0 0' }}>
            Cuando esté activa, aquí verás si otras fuentes confirman o desmienten lo que dice la noticia.
          </p>
        </>
      ) : (
        <p className={`mono${verification.tone ? ` tone-${verification.tone}` : ''}`} style={{ margin: '16px 0 8px', fontSize: 18, color: verification.tone ? 'var(--tone)' : 'var(--color-muted)' }}>
          {verification.label}
        </p>
      )}
      {!simple && verification.state === 'none' && (
        <p className="muted" style={{ margin: 0 }}>
          Cuando se active, aquí aparecerá si fuentes externas respaldan o contradicen las afirmaciones
          del texto, con sus enlaces. Por ahora el resultado depende solo de los dos modelos.
        </p>
      )}
      {verification.summary && <p style={{ margin: 0 }}>{verification.summary}</p>}
      {[['Afirmaciones revisadas', verification.claims], ['Fuentes consultadas', verification.sources]].map(([title, items]) => (
        items.length > 0 && (
          <div key={title} style={{ marginTop: 14 }}>
            <span className="label">{title}</span>
            <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
              {items.map((item, index) => (
                <li key={index}>
                  {item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer nofollow">{item.text}</a> : item.text}
                </li>
              ))}
            </ul>
          </div>
        )
      ))}
    </article>
  );
}

function ChainCheck({ id }) {
  const [state, setState] = useState({ loading: false, data: null, error: null });
  async function check() {
    setState({ loading: true, data: null, error: null });
    try { setState({ loading: false, data: await publicApi(`/publico/analisis/${id}/verificacion`), error: null }); }
    catch (error) { setState({ loading: false, data: null, error }); }
  }
  const result = state.data ? CHECKS[state.data.detalle] ?? CHECK_ERROR : null;
  return (
    <div style={{ marginTop: 14 }}>
      <button type="button" className="btn btn--ghost btn--small" onClick={check} disabled={state.loading}>
        {state.loading ? 'Comprobando…' : 'Comprobar que no ha cambiado'}
      </button>
      {result && <p style={{ margin: '10px 0 0' }} role="status"><span className={`tag ${result.tag}`} style={{ marginRight: 8 }}>{result.short}</span>{result.text}</p>}
      {state.error && <p className="alert" style={{ marginTop: 10 }} role="alert">{state.error.message}</p>}
    </div>
  );
}

// Flecha de volver: si se llegó desde la web, regresa a la página anterior (la lista con sus
// filtros); si se abrió el enlace directo, va a Resultados.
function BackButton() {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <button
      type="button" className="btn btn--ghost back-btn" aria-label="Volver" title="Volver"
      onClick={() => (location.key !== 'default' ? navigate(-1) : navigate('/resultados'))}
    >
      <Icon name="back" />
    </button>
  );
}

function PageTitle() {
  return (
    <div className="title-row">
      <BackButton />
      <h1 className="display h-page" style={{ margin: 0 }}>Detalle del análisis</h1>
    </div>
  );
}

export default function ResultDetail() {
  const { id } = useParams();
  const { data, error, loading, reload } = useLoad((signal) => publicApi(`/publico/analisis/${id}`, { signal }), [id]);

  if (loading) return <div className="shell page-head"><Loader code="Abriendo archivo" label="Cargando el análisis" rows={2} /></div>;
  if (error) {
    return (
      <div className="shell page-head">
        <PageTitle />
        <div style={{ marginTop: 18 }}>
          {error.status === 404
            ? <div className="alert alert--info">Este análisis no existe o ya no está publicado.</div>
            : <ErrorState error={error} onRetry={reload} />}
        </div>
      </div>
    );
  }

  const view = presentAnalysis(data);
  const original = data.texto_original ?? data.texto;
  const unified = data.resultado_unificado;

  return (
    <div className="shell">
      <header className="page-head">
        <PageTitle />
        <div className="card-meta" style={{ margin: '14px 0 0' }}>
          <span>{view.date}</span>
          <Source view={view} />
          {view.words && <span>{view.words}</span>}
          {view.truncated && <span className="tag" title="El texto superaba lo que leen los modelos; se analizó el comienzo.">Se leyó solo el comienzo</span>}
          <StatusTags view={view} chain={false} />
        </div>
      </header>

      <div className="detail boot">
        <section className={`panel panel--tone detail-verdict tone-${view.tone}`}>
          <Dial view={view} />
          <p className="display" style={{ margin: '4px 0 16px', textAlign: 'center', fontSize: 15, color: 'var(--tone)' }}>
            {view.level?.label ?? 'Sin resultado unificado'}
          </p>
          <Spectrum view={view} ends />
          <div className="legend" style={{ justifyContent: 'center' }}>
            <span style={{ '--tone': CRITERIA.mbert.color }}><i className="led" />BETO ▼</span>
            <span style={{ '--tone': CRITERIA.bilstm.color }}><i className="led" />BiLSTM ▲</span>
            <span className={`tone-${view.tone}`}><i className="led" />Resultado final ◆</span>
          </div>
          <p className="muted" style={{ margin: '16px 0 0', fontSize: 13 }}>
            Es una estimación a partir de la forma en que está escrito el texto. No comprueba si los hechos son ciertos.
          </p>
        </section>

        <section className="panel panel--accent">
          <h2 className="h-panel" style={{ margin: '0 0 16px' }}>
            Texto de la noticia
          </h2>
          {/* En el detalle se ve la dirección completa de la noticia, no solo el sitio. */}
          {view.url && (
            <p className="source-url">
              <span className="label">Página de origen</span>
              <a href={view.url} target="_blank" rel="noopener noreferrer nofollow">
                <i className="led" style={{ '--led': 'var(--color-acid)' }} />
                <span>{readableUrl(view.url)}</span>
                <Icon name="external" />
              </a>
            </p>
          )}
          <Fragments fragments={view.fragments} />
        </section>
      </div>

      <section className="detail-block">
        <h2 className="display h-section">Las tres revisiones</h2>
        <div className="detail-criteria boot">
          {view.models.map((model) => (
            <ModelPanel key={model.key} model={model} output={data.resultados?.[model.key]} original={original} simple />
          ))}
          <WebPanel verification={view.verification} simple />
        </div>
      </section>

      <section className="panel detail-block">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span className="criterion-icon" style={{ '--c': 'var(--color-muted)', flex: 'none' }}><Icon name="chain" /></span>
          <div style={{ minWidth: 0 }}>
            <h2 className="h-panel" style={{ margin: '0 0 4px' }}>Constancia del análisis</h2>
            <p className="muted" style={{ margin: 0 }}>{CHAIN_TEXT[view.chain.state]}</p>
          </div>
        </div>
        <ChainCheck id={id} />
        <details className="tech">
          <summary className="text-link">Datos técnicos</summary>
          <dl className="kv">
            <dt>Código</dt>
            <dd>{view.code}</dd>
            <dt>Combinación</dt>
            <dd>{unified?.version_combinacion ?? unified?.version_regla ?? '—'}</dd>
            <dt>Pesos</dt>
            <dd>{unified ? `BETO ${percent(unified.pesos_aplicados?.mbert)} · BiLSTM ${percent(unified.pesos_aplicados?.bilstm)}` : '—'}</dd>
            {view.models.map((model) => (
              <Fragment key={model.key}>
                <dt>Versión {model.name}</dt>
                <dd>{data.resultados?.[model.key]?.version ?? '—'}</dd>
              </Fragment>
            ))}
            <dt>Huella del texto</dt>
            <dd title="SHA-256 del texto analizado">{data.hash_texto.slice(0, 16)}…</dd>
            <dt>Blockchain</dt>
            <dd>{view.chain.label}</dd>
            {data.hash_transaccion && <><dt>Transacción</dt><dd>{data.hash_transaccion.slice(0, 18)}…</dd></>}
          </dl>
        </details>
      </section>
    </div>
  );
}
