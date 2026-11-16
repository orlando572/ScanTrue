import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  CriterionIcon, Dial, Fragments, Source, Spectrum, StatusTags,
} from '../components/Analysis.jsx';
import { ErrorState, Icon, Loader, SegmentBar } from '../components/ui.jsx';
import { publicApi } from '../lib/api.js';
import { useLoad } from '../lib/hooks.js';
import { CRITERIA, percent, presentAnalysis, readSplit } from '../lib/presentation.js';

const CHECKS = {
  registro_coincide: { tag: 'tag--ok', text: 'El registro en la cadena coincide con este análisis.' },
  registro_no_coincide: { tag: 'tag--fail', text: 'El registro en la cadena no coincide con este análisis.' },
  registro_pendiente: { tag: '', text: 'El registro todavía está pendiente de enviarse.' },
  registro_no_enviado: { tag: '', text: 'Este análisis no tiene un registro enviado.' },
  sin_confirmar: { tag: '', text: 'La transacción todavía no tiene confirmación.' },
  blockchain_no_configurada: { tag: 'tag--warn', text: 'El registro en blockchain no está configurado en este servidor.' },
};

// Lo que respondió y lo que leyó un modelo: su texto es un prefijo del fragmento original.
export function ModelPanel({ model, output, original }) {
  const split = readSplit(original, output?.texto_modelo);
  return (
    <article className="panel" style={{ '--edge': `color-mix(in srgb, ${model.color} 45%, var(--color-line))`, '--c': model.color }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <CriterionIcon name={model.key} />
        <div style={{ minWidth: 0 }}>
          <h3 className="h-panel" style={{ margin: 0, color: model.color }}>{model.name}</h3>
          <span className="label">{output?.version ?? 'Sin versión registrada'}</span>
        </div>
      </div>
      {model.percentage ? (
        <>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, margin: '16px 0 8px' }}>
            <span className="mono" style={{ fontSize: 30 }}>{model.percentage}</span>
            <span className={`tag ${model.classification === 'falsa' ? 'tag--fail' : 'tag--ok'}`}>Clase {model.classification}</span>
          </div>
          <SegmentBar value={model.value} color={model.color} />
          <p className="label" style={{ margin: '12px 0 0' }}>
            {model.level}{output?.tokens_leidos ? ` · ${output.tokens_leidos} ${model.key === 'mbert' ? 'subpalabras' : 'palabras'} leídas` : ''}
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

// Tercer criterio: la verificación con fuentes externas (incremento 2). `footer` es para lo que
// solo ve el administrador (intentos, causa de la falla y el botón de reintento).
export function WebPanel({ verification, footer = null }) {
  const color = CRITERIA.web.color;
  const { claims, sources } = verification;
  return (
    <article className={`panel${verification.state === 'none' ? '' : ' panel--wide'}`} style={{ '--edge': `color-mix(in srgb, ${color} 45%, var(--color-line))`, '--c': color }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <CriterionIcon name="web" />
        <div>
          <h3 className="h-panel" style={{ margin: 0, color }}>{CRITERIA.web.name}</h3>
          <span className="label">Tercer criterio</span>
        </div>
      </div>
      <p className={`mono${verification.tone ? ` tone-${verification.tone}` : ''}`} style={{ margin: '16px 0 8px', fontSize: 18, color: verification.tone ? 'var(--tone)' : 'var(--color-muted)' }}>
        {verification.label}
      </p>
      {verification.state === 'none' && (
        <p className="muted" style={{ margin: 0 }}>
          Cuando se active, aquí aparecerá si fuentes externas respaldan o contradicen las afirmaciones
          del texto, con sus enlaces. Por ahora el resultado depende solo de los dos modelos.
        </p>
      )}
      {verification.note && <p className="muted" style={{ margin: 0 }}>{verification.note}</p>}
      {verification.summary && (
        <>
          <p style={{ margin: 0 }}>{verification.summary}</p>
          <p className="label" style={{ margin: '8px 0 0' }}>
            Resumen redactado por un modelo de lenguaje: puede equivocarse. Lo comprobable son las afirmaciones y sus fuentes.
          </p>
        </>
      )}
      {claims.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <span className="label">Afirmaciones revisadas</span>
          <ol className="claims">
            {claims.map((claim) => (
              <li key={claim.id}>
                <span className="chips" style={{ marginBottom: 4 }}>
                  {claim.verdict && <span className={`tag tone-${claim.verdict.tone}`} style={{ '--tag': 'var(--tone)' }}>{claim.verdict.label}</span>}
                  {claim.origin && <span className="tag">{claim.origin}</span>}
                </span>
                <span>{claim.url ? <a href={claim.url} target="_blank" rel="noopener noreferrer nofollow">{claim.text}</a> : claim.text}</span>
                {claim.sourceIds.length > 0 && <span className="label" style={{ display: 'block', marginTop: 2 }}>Fuentes: {claim.sourceIds.map((id) => `[${id}]`).join(' ')}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
      {sources.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <span className="label">Fuentes consultadas</span>
          <ul className="sources">
            {sources.map((source) => (
              <li key={source.id}>
                <span className="n" aria-hidden="true">[{source.id}]</span>
                <span>
                  {source.url ? <a href={source.url} target="_blank" rel="noopener noreferrer nofollow">{source.text}</a> : source.text}
                  {(source.domain || source.consulted) && (
                    <span className="label" style={{ display: 'block' }}>{[source.domain, source.consulted && `consultada el ${source.consulted}`].filter(Boolean).join(' · ')}</span>
                  )}
                  {source.quote && <q className="quote">{source.quote}</q>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {footer}
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
  const result = state.data ? CHECKS[state.data.detalle] ?? { tag: 'tag--warn', text: 'No pudimos consultar la cadena en este momento.' } : null;
  return (
    <div style={{ marginTop: 14 }}>
      <button type="button" className="btn btn--ghost btn--small" onClick={check} disabled={state.loading}>
        {state.loading ? 'Consultando…' : 'Comprobar registro'}
      </button>
      {result && <p style={{ margin: '10px 0 0' }} role="status"><span className={`tag ${result.tag}`} style={{ marginRight: 8 }}>Cadena</span>{result.text}</p>}
      {state.error && <p className="alert" style={{ marginTop: 10 }} role="alert">{state.error.message}</p>}
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
        <Link className="text-link" to="/resultados"><span aria-hidden="true">←</span> Resultados</Link>
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
        <Link className="text-link" to="/resultados"><span aria-hidden="true">←</span> Resultados</Link>
        <h1 className="display h-page" style={{ margin: '14px 0 10px' }}>Análisis {view.code}</h1>
        <div className="card-meta" style={{ margin: 0 }}>
          <span>{view.date}</span>
          <Source view={view} />
          {view.words && <span>{view.words} analizadas</span>}
          {view.truncated && <span className="tag">Texto recortado</span>}
          <StatusTags view={view} />
        </div>
      </header>

      <div className="detail">
        <div className="stack boot">
          <section className={`panel panel--tone tone-${view.tone}`}>
            <Dial view={view} />
            <p className="display" style={{ margin: '4px 0 16px', textAlign: 'center', fontSize: 15, color: 'var(--tone)' }}>
              {view.level?.label ?? 'Sin resultado unificado'}
            </p>
            <Spectrum view={view} />
            <div className="legend" style={{ justifyContent: 'center' }}>
              <span style={{ '--tone': CRITERIA.mbert.color }}><i className="led" />BETO ▼</span>
              <span style={{ '--tone': CRITERIA.bilstm.color }}><i className="led" />BiLSTM ▲</span>
              <span className={`tone-${view.tone}`}><i className="led" />Combinado ◆</span>
            </div>
            <p className="muted" style={{ margin: '16px 0 0', fontSize: 13 }}>
              Las probabilidades son salidas experimentales de clasificadores; no verifican hechos.
            </p>
          </section>

          <section className="panel">
            <h2 className="h-panel" style={{ margin: '0 0 14px' }}>Registro</h2>
            <dl className="kv">
              <dt>Combinación</dt>
              <dd>{unified?.version_combinacion ?? unified?.version_regla ?? '—'}</dd>
              <dt>Pesos</dt>
              <dd>{unified ? `BETO ${percent(unified.pesos_aplicados?.mbert)} · BiLSTM ${percent(unified.pesos_aplicados?.bilstm)}` : '—'}</dd>
              <dt>Huella del texto</dt>
              <dd title="SHA-256 del texto analizado">{data.hash_texto.slice(0, 16)}…</dd>
              <dt>Blockchain</dt>
              <dd>{view.chain.label}</dd>
              {data.hash_transaccion && <><dt>Transacción</dt><dd>{data.hash_transaccion.slice(0, 18)}…</dd></>}
            </dl>
            <ChainCheck id={id} />
          </section>
        </div>

        <div className="stack boot">
          <section className="panel panel--accent">
            <div className="section-head" style={{ marginBottom: 16 }}>
              <h2 className="h-panel" style={{ margin: 0 }}>
                {view.fragments.length === 1 ? 'Fragmento analizado' : `${view.fragments.length} fragmentos analizados`}
              </h2>
            </div>
            {/* En el detalle se ve la dirección completa de la noticia, no solo el sitio. */}
            {view.url && (
              <p className="source-url">
                <span className="label">Página de origen</span>
                <a href={view.url} target="_blank" rel="noopener noreferrer nofollow">
                  <i className="led" style={{ '--led': 'var(--color-acid)' }} />
                  <span>{view.url}</span>
                  <Icon name="external" />
                </a>
              </p>
            )}
            <Fragments fragments={view.fragments} />
          </section>

          <h2 className="display" style={{ margin: '12px 0 0', fontSize: 16 }}>Los tres criterios</h2>
          <div className="grid-3">
            {view.models.map((model) => (
              <ModelPanel key={model.key} model={model} output={data.resultados?.[model.key]} original={original} />
            ))}
            <WebPanel verification={view.verification} />
          </div>
        </div>
      </div>
    </div>
  );
}
