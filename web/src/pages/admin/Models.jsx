import { useEffect, useRef, useState } from 'react';
import { presentMetrics } from '../../../../frontend/src/popup/metrics-presentation.js';
import { CriterionIcon } from '../../components/Analysis.jsx';
import { ErrorState, Loader, SegmentBar, Sweep } from '../../components/ui.jsx';
import { adminApi, adminUpload } from '../../lib/api.js';
import { useLoad } from '../../lib/hooks.js';
import { CRITERIA, formatDate, percent } from '../../lib/presentation.js';

const TYPES = ['bilstm', 'mbert'];
const TYPE_NAMES = { bilstm: 'BiLSTM', mbert: 'BETO / mBERT' };
const STATES = {
  disponible: { label: 'Disponible', tag: 'tag--ok' },
  pendiente_calibrar: { label: 'Pendiente de calibrar', tag: 'tag--warn' },
  no_admitido: { label: 'No admitido', tag: 'tag--fail' },
  no_valido: { label: 'No válido', tag: 'tag--fail' },
  archivado: { label: 'Archivado', tag: '' },
};
const ORIGINS = { repositorio: 'Repositorio', entrenamiento: 'Entrenamiento', importado: 'Importado', calibracion: 'Calibración' };
const ACTIONS = { desplegar: 'Desplegar', desplegar_calibracion: 'Desplegar calibración', retirar: 'Retirar', pesos: 'Pesos', revertir: 'Volver atrás' };
const REFRESH_MS = 30_000;

const toNumber = (text) => (text ? Number.parseInt(text, 10) : 0);
const sameWeights = (a, b) => a && b && Math.abs(a.bilstm - b.bilstm) < 1e-6;
const findModel = (data, type, id) => data.modelos[type]?.find((model) => model.id === id) ?? null;

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

export function Metrics({ model }) {
  const color = CRITERIA[model.tipo].color;
  const metrics = model.metricas ? presentMetrics(model.metricas) : null;
  if (!metrics) return <p className="muted" style={{ margin: 0 }}>Sin métricas publicadas.</p>;
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {metrics.featured.map((evaluation) => <Evaluation key={evaluation.key} evaluation={evaluation} color={color} />)}
      {metrics.more.length > 0 && (
        <details>
          <summary className="text-link">{metrics.more.length === 1 ? 'Ver 1 prueba más' : `Ver ${metrics.more.length} pruebas más`}</summary>
          <div style={{ display: 'grid', gap: 12, marginTop: 12 }}>
            {metrics.more.map((evaluation) => <Evaluation key={evaluation.key} evaluation={evaluation} color={color} />)}
          </div>
        </details>
      )}
    </div>
  );
}

// Botón con confirmación en dos pasos.
function Confirm({ label, confirmLabel = 'Confirmar', danger, busy, disabled, title, onConfirm }) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return <button type="button" className={`btn btn--small${danger ? ' btn--ghost' : ''}`} disabled={busy || disabled} title={title} onClick={() => setOpen(true)}>{label}</button>;
  }
  return (
    <>
      <button type="button" className={`btn btn--small${danger ? ' btn--danger' : ''}`} disabled={busy} onClick={() => { setOpen(false); onConfirm(); }}>{confirmLabel}</button>
      <button type="button" className="btn btn--ghost btn--small" disabled={busy} onClick={() => setOpen(false)}>Cancelar</button>
    </>
  );
}

// Un tipo (hueco) de modelo: qué hay desplegado y si está cargado.
function Slot({ data, type }) {
  const id = data.desplegados[type];
  const model = findModel(data, type, id);
  const loaded = data.cargados.includes(type);
  const color = CRITERIA[type].color;
  return (
    <div className="panel" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
      <CriterionIcon name={type} />
      <div style={{ minWidth: 0, display: 'grid', gap: 4 }}>
        <span className="label">{TYPE_NAMES[type]}</span>
        <strong className="mono" style={{ fontWeight: 400, color: id ? color : 'var(--color-muted)' }}>
          {id ? (model?.nombre ?? id) : 'Retirado'}
        </strong>
        {id && <span className="label" style={{ overflowWrap: 'anywhere' }}>{id}</span>}
      </div>
      <span style={{ marginLeft: 'auto' }}>
        {id ? (loaded
          ? <span className="tag tag--acid"><i className="led" style={{ '--led': 'var(--color-acid)' }} />Desplegado</span>
          : <span className="tag tag--fail" title="Está desplegado, pero no se pudo cargar al arrancar.">No cargó</span>)
          : <span className="tag">Sin modelo</span>}
      </span>
    </div>
  );
}

function WeightsPanel({ data, busy, onSave }) {
  const [mbert, setMbert] = useState(Math.round(data.pesos.mbert * 100));
  useEffect(() => { setMbert(Math.round(data.pesos.mbert * 100)); }, [data.pesos.mbert]);
  const both = data.cargados.length === 2;
  const calibrated = data.pesos_calibrados;
  const isCalibrated = sameWeights(data.pesos, calibrated);
  const changed = mbert !== Math.round(data.pesos.mbert * 100);
  const save = (value) => onSave({ bilstm: Math.round(100 - value) / 100, mbert: Math.round(value) / 100 });
  return (
    <section className="panel" style={{ display: 'grid', gap: 12 }}>
      <div className="version-head">
        <h2 className="h-panel" style={{ margin: 0 }}>Peso de cada modelo en el resultado</h2>
        <span className={`tag ${isCalibrated ? 'tag--ok' : 'tag--warn'}`}>{isCalibrated ? 'Pesos calibrados' : 'Pesos editados'}</span>
      </div>
      <label className="field">
        <span>BiLSTM {100 - mbert} % · BETO / mBERT {mbert} %</span>
        <input type="range" min="0" max="100" step="5" value={mbert} disabled={busy || !both}
          aria-label="Peso de BETO / mBERT" onChange={(event) => setMbert(Number(event.target.value))} />
      </label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <button type="button" className="btn btn--small" disabled={busy || !both || !changed} onClick={() => save(mbert)}>Guardar pesos</button>
        {calibrated && !isCalibrated && (
          <button type="button" className="btn btn--ghost btn--small" disabled={busy} onClick={() => save(Math.round(calibrated.mbert * 100))}>
            Volver a los calibrados ({percent(calibrated.bilstm)} / {percent(calibrated.mbert)})
          </button>
        )}
        <span className="label" style={{ overflowWrap: 'anywhere' }}>Combinación: {data.combinacion ?? '—'}</span>
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        {both
          ? 'Cada modelo aporta su probabilidad calibrada con la temperatura de su contrato; los pesos solo cambian cuánto cuenta cada uno. Los calibrados son los que se eligieron para B6 + BETO M3b.'
          : 'Con un solo modelo desplegado, el resultado es su probabilidad: los pesos no se usan.'}
      </p>
    </section>
  );
}

function ModelCard({ model, data, busy, onDeploy, onRetire, onDelete }) {
  const state = STATES[model.estado] ?? STATES.no_valido;
  const others = data.cargados.filter((type) => type !== model.tipo).length;
  const isPrevious = data.anterior?.desplegados?.[model.tipo] === model.id;
  return (
    <article className={`panel${model.desplegado ? ' panel--accent' : ''}`} style={model.desplegado ? { '--accent': CRITERIA[model.tipo].color } : undefined}>
      <div className="version-head">
        <div style={{ minWidth: 0 }}>
          <h3 className="h-panel" style={{ margin: 0, color: model.desplegado ? CRITERIA[model.tipo].color : undefined }}>{model.nombre}</h3>
          <span className="label" style={{ overflowWrap: 'anywhere' }}>{model.id}{model.fecha ? ` · ${model.fecha}` : ''} · {model.casos} análisis</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          <span className="tag">{ORIGINS[model.origen] ?? model.origen}</span>
          {model.desplegado
            ? <span className="tag tag--acid"><i className="led" style={{ '--led': 'var(--color-acid)' }} />{model.cargado ? 'Desplegado' : 'Desplegado · no cargó'}</span>
            : <span className={`tag ${state.tag}`}>{state.label}</span>}
          {model.estado === 'disponible' && (!model.desplegado || !model.cargado) && (
            <Confirm label="Desplegar" busy={busy} onConfirm={() => onDeploy(model)} />
          )}
          {model.desplegado && (
            <Confirm label="Retirar" danger busy={busy} disabled={others === 0}
              title={others === 0 ? 'Debe quedar al menos un modelo desplegado.' : undefined}
              onConfirm={() => onRetire(model)} />
          )}
          {model.origen === 'importado' && !model.desplegado && (
            <Confirm label="Borrar" confirmLabel="Borrar" danger busy={busy} disabled={isPrevious}
              title={isPrevious ? 'Es al que se volvería con «Volver atrás».' : undefined}
              onConfirm={() => onDelete(model)} />
          )}
        </div>
      </div>
      {model.motivo && model.estado !== 'disponible' && (
        <p className={`alert${model.estado === 'pendiente_calibrar' || model.estado === 'archivado' ? ' alert--info' : ''}`} style={{ margin: '12px 0 0' }}>{model.motivo}</p>
      )}
      {model.notas && <p className="muted" style={{ margin: '12px 0 0' }}>{model.notas}</p>}
      <p className="label" style={{ margin: '12px 0 0', overflowWrap: 'anywhere' }}>
        {[model.temperatura != null && `Temperatura ${model.temperatura}`, model.max_tokens && `${model.max_tokens} ${model.tipo === 'bilstm' ? 'palabras' : 'subpalabras'}`, model.ruta]
          .filter(Boolean).join(' · ')}
      </p>
      <div style={{ marginTop: 16 }}><Metrics model={model} /></div>
    </article>
  );
}

// Dos modelos del mismo tipo lado a lado, con sus pruebas principales.
function Compare({ models, type }) {
  const [left, setLeft] = useState(models.find((item) => item.desplegado)?.id ?? models[0]?.id);
  const [right, setRight] = useState(models.find((item) => item.id !== left)?.id ?? left);
  const columns = [left, right].map((id) => models.find((item) => item.id === id)).filter(Boolean);
  const select = (value, onChange, label) => (
    <label className="field">
      <span>{label}</span>
      <select className="input" value={value} onChange={(event) => onChange(event.target.value)}>
        {models.map((item) => <option key={item.id} value={item.id}>{item.nombre} · {item.id}</option>)}
      </select>
    </label>
  );
  return (
    <details className="panel">
      <summary className="text-link">Comparar dos modelos {TYPE_NAMES[type]}</summary>
      <div className="filter-grid" style={{ marginTop: 14 }}>{select(left, setLeft, 'Modelo A')}{select(right, setRight, 'Modelo B')}</div>
      <div className="grid-2" style={{ marginTop: 16, gap: 28 }}>
        {columns.map((model, index) => (
          <div key={`${index}-${model.id}`} style={{ display: 'grid', gap: 10, alignContent: 'start' }}>
            <strong className="mono" style={{ fontWeight: 400, color: CRITERIA[type].color }}>{index === 0 ? 'A' : 'B'} · {model.nombre}</strong>
            <span className="label" style={{ overflowWrap: 'anywhere' }}>{model.id}</span>
            <Metrics model={model} />
          </div>
        ))}
      </div>
      <p className="muted" style={{ margin: '12px 0 0', fontSize: 13 }}>
        Los porcentajes solo se pueden comparar directamente cuando la prueba tiene el mismo nombre y los mismos textos.
      </p>
    </details>
  );
}

function ImportPanel({ busy, onUpload }) {
  const input = useRef(null);
  const [file, setFile] = useState(null);
  return (
    <section className="panel" style={{ display: 'grid', gap: 12 }}>
      <h2 className="h-panel" style={{ margin: 0 }}>Importar un modelo de otro equipo</h2>
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>
        Los modelos que entrenas en este equipo aparecen solos al terminar el entrenamiento: no hace falta importarlos.
        Para traer uno de otro equipo, sube un ZIP con su <span className="mono">contrato.json</span>, sus pesos
        (y, si los tiene, <span className="mono">metricas.json</span>). Se comprueba el contrato y el SHA-256 de los pesos
        antes de guardarlo en <span className="mono">datasets/modelos/</span>.
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <input ref={input} type="file" accept=".zip,application/zip" className="input" style={{ maxWidth: 360 }}
          disabled={busy} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        <button type="button" className="btn btn--small" disabled={busy || !file}
          onClick={() => { onUpload(file); setFile(null); if (input.current) input.current.value = ''; }}>Importar</button>
      </div>
    </section>
  );
}

function History({ entries, data }) {
  const name = (type, id) => (type && id ? findModel(data, type, id)?.nombre ?? id : null);
  const detail = (entry) => {
    if (entry.accion === 'pesos') return `BiLSTM ${percent(entry.pesos?.bilstm)} · BETO / mBERT ${percent(entry.pesos?.mbert)}`;
    if (entry.accion === 'revertir') return 'Estado anterior al último cambio';
    if (entry.accion === 'desplegar_calibracion') return `Pareja y pesos de ${entry.version}`;
    return `${TYPE_NAMES[entry.tipo] ?? ''}: ${name(entry.tipo, entry.version) ?? '—'}`;
  };
  const before = (entry) => {
    const previous = entry.anterior;
    if (!previous) return '—';
    if (entry.accion === 'pesos' || entry.accion === 'revertir' || entry.accion === 'desplegar_calibracion') {
      return `${TYPES.map((type) => name(type, previous.desplegados?.[type]) ?? 'retirado').join(' + ')} · ${percent(previous.pesos?.bilstm)}/${percent(previous.pesos?.mbert)}`;
    }
    return name(entry.tipo, previous.desplegados?.[entry.tipo]) ?? 'retirado';
  };
  return (
    <section className="panel">
      <h2 className="h-panel" style={{ margin: '0 0 14px' }}>Historial de cambios</h2>
      {entries.length === 0 ? <p className="muted" style={{ margin: 0 }}>Todavía no se ha cambiado nada desde el panel.</p> : (
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>Fecha</th><th>Acción</th><th>Cambio</th><th>Antes</th><th>Por</th></tr></thead>
            <tbody>
              {entries.map((entry, index) => (
                <tr key={index}>
                  <td className="mono">{formatDate(entry.fecha)}</td>
                  <td><span className={`tag ${entry.accion === 'revertir' || entry.accion === 'retirar' ? 'tag--warn' : 'tag--ok'}`}>{ACTIONS[entry.accion] ?? entry.accion}</span></td>
                  <td>{detail(entry)}</td>
                  <td className="muted">{before(entry)}</td>
                  <td>{entry.por ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function Models() {
  const { data, error, loading, reload, setData } = useLoad((signal) => adminApi('/admin/modelos', { signal }), []);
  const [action, setAction] = useState({ busy: false, label: null, error: null, done: null, progress: null });
  const busy = useRef(false);
  busy.current = action.busy;

  // Los modelos que termina el entrenamiento (o que se calibran) aparecen sin recargar.
  useEffect(() => {
    const timer = setInterval(() => {
      if (busy.current || document.hidden) return;
      adminApi('/admin/modelos').then((fresh) => { if (!busy.current) setData(fresh); }).catch(() => {});
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [setData]);

  // Cargar y comprobar un modelo puede tardar: la petición espera hasta dos minutos.
  async function run(label, request, done) {
    setAction({ busy: true, label, error: null, done: null, progress: null });
    try {
      setData(await request());
      setAction({ busy: false, label: null, error: null, done, progress: null });
    } catch (failure) { setAction({ busy: false, label: null, error: failure, done: null, progress: null }); }
  }
  const call = (path, method, body) => () => adminApi(path, { method, body, timeout: 120_000 });

  if (loading && !data) return <div className="page-head"><Loader code="Leyendo modelos" label="Cargando modelos" rows={2} /></div>;
  if (error && !data) return <div className="page-head"><ErrorState error={error} onRetry={reload} /></div>;
  // Una API arrancada antes de este cambio responde con el formato anterior (versiones por pareja).
  if (!data?.desplegados || !data?.modelos) {
    return (
      <div className="page-head">
        <ErrorState
          error={{ message: 'La API responde con el formato anterior de modelos: reinicia la API (o ./levantar.sh) para cargar la versión nueva.' }}
          onRetry={reload}
        />
      </div>
    );
  }

  const deploy = (model) => run('Cargando y comprobando el modelo', call('/admin/modelos/desplegar', 'POST', { tipo: model.tipo, id: model.id }),
    `${model.nombre} desplegado: los análisis nuevos ya lo usan.`);
  const retire = (model) => run('Retirando el modelo', call('/admin/modelos/retirar', 'POST', { tipo: model.tipo }),
    `${model.nombre} retirado: los análisis nuevos usan solo el otro modelo.`);
  const remove = (model) => run('Borrando el modelo', call(`/admin/modelos/${model.tipo}/${encodeURIComponent(model.id)}`, 'DELETE'),
    `${model.nombre} borrado.`);
  const saveWeights = (weights) => run('Aplicando los pesos', call('/admin/modelos/pesos', 'PUT', weights),
    `Pesos guardados: BiLSTM ${percent(weights.bilstm)} · BETO / mBERT ${percent(weights.mbert)}.`);
  const revert = () => run('Volviendo al estado anterior', call('/admin/modelos/revertir', 'POST'), 'Se volvió al estado anterior.');
  const upload = (file) => run('Subiendo y comprobando el ZIP',
    () => adminUpload('/admin/modelos/importar', file, (progress) => setAction((current) => ({ ...current, progress }))),
    `${file.name} importado: ya aparece en su tipo.`);

  return (
    <div className="stack" style={{ paddingTop: 24 }}>
      <div className="section-head" style={{ margin: 0 }}>
        <h1 className="display h-page" style={{ margin: 0 }}>Modelos</h1>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <button type="button" className="btn btn--ghost" disabled={action.busy} onClick={reload}>Actualizar</button>
          {data.anterior && <button type="button" className="btn btn--ghost" disabled={action.busy} onClick={revert}>Volver atrás</button>}
        </div>
      </div>

      <div className="grid-2">{TYPES.map((type) => <Slot key={type} data={data} type={type} />)}</div>
      {data.cargados.length === 0 && <p className="alert" role="alert" style={{ margin: 0 }}>Ningún modelo está cargado: el servicio de análisis no está disponible.</p>}
      {action.busy && (
        <div style={{ display: 'grid', gap: 8 }} role="status">
          <span className="label loader-code">{action.label}{action.progress != null ? ` · ${Math.round(action.progress * 100)} %` : ''}</span>
          <Sweep />
        </div>
      )}
      {action.done && <p className="alert alert--info" style={{ margin: 0 }} role="status">{action.done}</p>}
      {action.error && <p className="alert" style={{ margin: 0 }} role="alert">{action.error.message}</p>}

      <WeightsPanel data={data} busy={action.busy} onSave={saveWeights} />

      {TYPES.map((type) => (
        <section key={type} className="stack" style={{ gap: 16 }}>
          <h2 className="h-panel" style={{ margin: '12px 0 0', color: CRITERIA[type].color }}>{TYPE_NAMES[type]}</h2>
          {data.modelos[type].length === 0
            ? <p className="muted" style={{ margin: 0 }}>No hay modelos de este tipo.</p>
            : data.modelos[type].map((model) => (
              <ModelCard key={model.id} model={model} data={data} busy={action.busy}
                onDeploy={deploy} onRetire={retire} onDelete={remove} />
            ))}
          {data.modelos[type].length > 1 && <Compare models={data.modelos[type]} type={type} />}
        </section>
      ))}

      <ImportPanel busy={action.busy} onUpload={upload} />
      <History entries={data.historial} data={data} />
    </div>
  );
}
