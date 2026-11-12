import { useState } from 'react';
import { presentMetrics } from '../../../../frontend/src/popup/metrics-presentation.js';
import { CriterionIcon } from '../../components/Analysis.jsx';
import { ErrorState, Loader, SegmentBar, Sweep } from '../../components/ui.jsx';
import { adminApi } from '../../lib/api.js';
import { useLoad } from '../../lib/hooks.js';
import { CRITERIA, formatDate, percent } from '../../lib/presentation.js';

const toNumber = (text) => (text ? Number.parseInt(text, 10) : 0);

function Evaluation({ evaluation, color }) {
  return (
    <div className="metric" style={{ '--c': color }}>
      <span className="name">{evaluation.name}{evaluation.examples ? ` · ${evaluation.examples} textos` : ''}</span>
      <SegmentBar value={toNumber(evaluation.accuracy)} cells={25} color={color} />
      <span title="Aciertos">{evaluation.accuracy ?? '—'}</span>
      <SegmentBar value={toNumber(evaluation.f1)} cells={25} color="var(--color-muted)" />
      <span className="muted" title="F1 macro">{evaluation.f1 ?? '—'}</span>
    </div>
  );
}

// Un modelo dentro de una versión: su versión, cuántos análisis la usaron y sus pruebas.
function ModelBlock({ model }) {
  const criterion = CRITERIA[model.modelo];
  const metrics = model.metricas ? presentMetrics(model.metricas) : null;
  return (
    <div style={{ display: 'grid', gap: 12, alignContent: 'start' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <CriterionIcon name={model.modelo} />
        <div style={{ minWidth: 0 }}>
          <h4 className="h-panel" style={{ margin: 0, color: criterion.color }}>{criterion.name}</h4>
          <span className="label" style={{ overflowWrap: 'anywhere' }}>{model.version ?? 'sin versión'} · {model.casos} análisis</span>
        </div>
      </div>
      {metrics ? (
        <>
          {metrics.featured.map((evaluation) => <Evaluation key={evaluation.key} evaluation={evaluation} color={criterion.color} />)}
          {metrics.more.length > 0 && (
            <details>
              <summary className="text-link">{metrics.more.length === 1 ? 'Ver 1 prueba más' : `Ver ${metrics.more.length} pruebas más`}</summary>
              <div style={{ display: 'grid', gap: 12, marginTop: 12 }}>
                {metrics.more.map((evaluation) => <Evaluation key={evaluation.key} evaluation={evaluation} color={criterion.color} />)}
              </div>
            </details>
          )}
        </>
      ) : <p className="muted" style={{ margin: 0 }}>Sin métricas publicadas.</p>}
    </div>
  );
}

function VersionCard({ version, busy, onActivate }) {
  const [confirm, setConfirm] = useState(false);
  return (
    <article className={`panel${version.activa ? ' panel--accent' : ''}`} style={version.activa ? { '--accent': 'var(--color-acid)' } : undefined}>
      <div className="version-head">
        <div style={{ minWidth: 0 }}>
          <h3 className="h-panel" style={{ margin: 0 }}>{version.nombre}</h3>
          <span className="label" style={{ overflowWrap: 'anywhere' }}>{version.version}{version.fecha ? ` · ${version.fecha}` : ''}</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          {version.activa ? <span className="tag tag--acid"><i className="led" style={{ '--led': 'var(--color-acid)' }} />Activa</span>
            : version.activable ? <span className="tag tag--ok">Disponible</span>
              : <span className="tag">Archivada</span>}
          {version.activable && !version.activa && (confirm ? (
            <>
              <button type="button" className="btn btn--small" disabled={busy} onClick={() => { setConfirm(false); onActivate(version.version); }}>Confirmar</button>
              <button type="button" className="btn btn--ghost btn--small" disabled={busy} onClick={() => setConfirm(false)}>Cancelar</button>
            </>
          ) : <button type="button" className="btn btn--small" disabled={busy} onClick={() => setConfirm(true)}>Activar</button>)}
        </div>
      </div>
      {version.notas && <p className="muted" style={{ margin: '12px 0 0' }}>{version.notas}</p>}
      {version.pesos && (
        <p className="label" style={{ margin: '12px 0 0' }}>
          Resultado combinado: BETO {percent(version.pesos.mbert)} · BiLSTM {percent(version.pesos.bilstm)}
          {version.temperaturas ? ` · temperaturas ${version.temperaturas.mbert} y ${version.temperaturas.bilstm}` : ''}
        </p>
      )}
      {confirm && (
        <p className="alert alert--info" style={{ margin: '14px 0 0' }}>
          Se cargarán los dos modelos y se hará una predicción de prueba. Solo si responden bien, los
          análisis nuevos usarán esta versión; si algo falla, sigue activa la actual.
        </p>
      )}
      <div className="grid-2" style={{ marginTop: 20, gap: 28 }}>
        {version.modelos.map((model) => <ModelBlock key={model.modelo} model={model} />)}
      </div>
    </article>
  );
}

// Dos versiones lado a lado, con sus pruebas principales por modelo.
function Compare({ versions }) {
  const [left, setLeft] = useState(versions.find((item) => item.activa)?.version ?? versions[0]?.version);
  const [right, setRight] = useState(versions.find((item) => item.version !== left)?.version ?? left);
  const pick = (id) => versions.find((item) => item.version === id);
  const columns = [pick(left), pick(right)].filter(Boolean);
  const select = (value, onChange, label) => (
    <label className="field">
      <span>{label}</span>
      <select className="input" value={value} onChange={(event) => onChange(event.target.value)}>
        {versions.map((item) => <option key={item.version} value={item.version}>{item.nombre}</option>)}
      </select>
    </label>
  );
  return (
    <section className="panel">
      <h2 className="h-panel" style={{ margin: '0 0 14px' }}>Comparar versiones</h2>
      <div className="filter-grid">{select(left, setLeft, 'Versión A')}{select(right, setRight, 'Versión B')}</div>
      <div className="table-wrap" style={{ marginTop: 16 }}>
        <table className="data">
          <thead><tr><th>Modelo</th>{columns.map((item, index) => <th key={index}>{index === 0 ? 'A' : 'B'} · {item.nombre}</th>)}</tr></thead>
          <tbody>
            {['bilstm', 'mbert'].map((name) => (
              <tr key={name}>
                <td style={{ color: CRITERIA[name].color, whiteSpace: 'nowrap' }}>{CRITERIA[name].name}</td>
                {columns.map((item, index) => {
                  const model = item.modelos.find((entry) => entry.modelo === name);
                  const metrics = model?.metricas ? presentMetrics(model.metricas) : null;
                  return (
                    <td key={index}>
                      <span className="label" style={{ overflowWrap: 'anywhere' }}>{model?.version ?? '—'}</span>
                      {metrics ? metrics.featured.map((evaluation) => (
                        <p key={evaluation.key} className="mono" style={{ margin: '6px 0 0' }}>
                          {evaluation.name}: {evaluation.accuracy ?? '—'} aciertos · F1 {evaluation.f1 ?? '—'}
                          <span className="muted"> ({evaluation.examples ?? '?'} textos)</span>
                        </p>
                      )) : <p className="muted" style={{ margin: '6px 0 0' }}>Sin métricas</p>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted" style={{ margin: '12px 0 0', fontSize: 13 }}>
        Cada versión se evaluó con sus propios conjuntos de prueba: los porcentajes solo se pueden
        comparar directamente cuando el conjunto tiene el mismo nombre y los mismos textos.
      </p>
    </section>
  );
}

export default function Models() {
  const { data, error, loading, reload, setData } = useLoad((signal) => adminApi('/admin/modelos', { signal }), []);
  const [action, setAction] = useState({ busy: false, error: null, done: null });

  // Cargar y comprobar los dos modelos puede tardar: la petición espera hasta dos minutos.
  async function change(path, body, done) {
    setAction({ busy: true, error: null, done: null });
    try {
      setData(await adminApi(path, { method: 'POST', body, timeout: 120_000 }));
      setAction({ busy: false, error: null, done });
    } catch (failure) { setAction({ busy: false, error: failure, done: null }); }
  }

  if (loading) return <div className="page-head"><Loader code="Leyendo versiones" label="Cargando versiones de modelos" rows={2} /></div>;
  if (error) return <div className="page-head"><ErrorState error={error} onRetry={reload} /></div>;

  return (
    <div className="stack" style={{ paddingTop: 24 }}>
      <div className="section-head" style={{ margin: 0 }}>
        <h1 className="display h-page" style={{ margin: 0 }}>Versiones de modelos</h1>
        {data.anterior && (
          <button type="button" className="btn btn--ghost" disabled={action.busy} onClick={() => change('/admin/modelos/revertir', undefined, 'Se volvió a la versión anterior.')}>
            Volver a la anterior
          </button>
        )}
      </div>
      <section className="panel" style={{ display: 'grid', gap: 10 }}>
        <span className="label">Versión activa</span>
        <span className="mono" style={{ fontSize: 18, color: 'var(--color-acid)', overflowWrap: 'anywhere' }}>{data.activa ?? 'Ninguna: el servicio de análisis no está disponible'}</span>
        {data.anterior && <span className="label">«Volver a la anterior» activaría {data.anterior}</span>}
        {action.busy && <div style={{ display: 'grid', gap: 8 }} role="status"><span className="label loader-code">Cargando y comprobando modelos</span><Sweep /></div>}
        {action.done && <p className="alert alert--info" style={{ margin: 0 }} role="status">{action.done}</p>}
        {action.error && <p className="alert" style={{ margin: 0 }} role="alert">{action.error.message}</p>}
      </section>

      {data.versiones.map((version) => (
        <VersionCard
          key={version.version} version={version} busy={action.busy}
          onActivate={(id) => change('/admin/modelos/activar', { version: id }, 'Versión activada: los análisis nuevos ya la usan.')}
        />
      ))}

      {data.versiones.length > 1 && <Compare versions={data.versiones} />}

      <section className="panel">
        <h2 className="h-panel" style={{ margin: '0 0 14px' }}>Historial de cambios</h2>
        {data.historial.length === 0 ? <p className="muted" style={{ margin: 0 }}>Todavía no se ha cambiado de versión desde el panel.</p> : (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>Fecha</th><th>Acción</th><th>Versión</th><th>Anterior</th><th>Por</th></tr></thead>
              <tbody>
                {data.historial.map((entry, index) => (
                  <tr key={index}>
                    <td className="mono">{formatDate(entry.fecha)}</td>
                    <td><span className={`tag ${entry.accion === 'revertir' ? 'tag--warn' : 'tag--ok'}`}>{entry.accion}</span></td>
                    <td className="mono">{entry.version}</td>
                    <td className="mono">{entry.anterior ?? '—'}</td>
                    <td>{entry.por ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
