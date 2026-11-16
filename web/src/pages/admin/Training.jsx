import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { CriterionIcon } from '../../components/Analysis.jsx';
import { Empty, ErrorState, Loader, Sweep } from '../../components/ui.jsx';
import { adminApi } from '../../lib/api.js';
import { useLoad } from '../../lib/hooks.js';
import { CRITERIA, formatDate } from '../../lib/presentation.js';
import { Metrics } from './Models.jsx';

const TYPES = ['bilstm', 'mbert'];
const TYPE_NAMES = { bilstm: 'BiLSTM', mbert: 'BETO / mBERT' };
const BASE_NAMES = { beto: 'BETO', mbert: 'mBERT' };
// Fases del entrenamiento, en orden. «Modelo base» solo aparece en BETO / mBERT.
const PHASES = [
  { key: 'preparando', label: 'Preparando datos' },
  { key: 'descargando_base', label: 'Modelo base', only: 'mbert' },
  { key: 'entrenando', label: 'Entrenando' },
  { key: 'evaluando', label: 'Evaluando' },
  { key: 'guardando', label: 'Guardando contrato' },
];
const STATES = {
  en_curso: { label: 'En curso', tag: 'tag--acid' },
  completado: { label: 'Completado', tag: 'tag--ok' },
  fallido: { label: 'Falló', tag: 'tag--fail' },
  cancelado: { label: 'Cancelado', tag: 'tag--warn' },
};
const DEVICES = [
  { key: 'cuda', label: 'GPU (CUDA)' },
  { key: 'cpu', label: 'Procesador (CPU)' },
];
const POLL_MS = 2_000;
const IDLE_MS = 15_000;

function clock(seconds) {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—';
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, '0');
  return h ? `${h} h ${String(m).padStart(2, '0')} min` : `${m}:${s}`;
}

const elapsed = (job, now) => ((job.fin ? Date.parse(job.fin) : now) - Date.parse(job.inicio)) / 1000;
const sourceName = (fuente) => (fuente?.tipo === 'panel' ? `Panel · ${fuente.nombre}` : fuente?.nombre ?? 'comun_v1');
const recipeName = (type, recipe) => {
  const base = type === 'mbert' ? (BASE_NAMES[recipe?.modelo_base] ?? 'BETO / mBERT') : 'BiLSTM';
  return `${base} ${recipe?.configuracion ?? ''}`.trim();
};

// Hora actual que avanza cada segundo mientras `active`.
function useNow(active) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

// ── Trabajo en curso: la animación de carga ─────────────────────────

function PhaseSteps({ job }) {
  const phases = PHASES.filter((phase) => !phase.only || phase.only === job.tipo);
  const current = phases.findIndex((phase) => phase.key === job.fase);
  return (
    <ol className="train-steps">
      {phases.map((phase, index) => {
        const state = job.estado === 'completado' || index < current ? 'done' : index === current ? 'now' : 'next';
        return (
          <li key={phase.key} data-state={state}>
            <i className={`led${state === 'now' ? ' led--blink' : ''}`} />
            <span className={state === 'now' ? 'loader-code' : undefined}>{phase.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

// Una celda por época: las hechas, llenas; la actual, con su avance por lotes.
function EpochStrip({ job }) {
  const total = job.epocas || 0;
  const epoch = job.epoca || 0;
  const share = job.lotes ? job.lote / job.lotes : 0;
  const training = job.fase === 'entrenando';
  return (
    <div className="train-epochs" style={{ '--epochs': Math.max(total, 1) }}>
      {Array.from({ length: total }, (_, index) => {
        const n = index + 1;
        const after = ['evaluando', 'guardando', 'terminado'].includes(job.fase);
        let fill = 0;
        if (job.estado === 'completado' || n < epoch || (n === epoch && after)) fill = 1;
        else if (n === epoch && training) fill = share;
        const loss = job.perdidas?.find((item) => item.epoca === n)?.perdida;
        return (
          <div key={n} className="train-epoch" data-active={n === epoch && training ? 'true' : undefined}>
            <span className="track"><i style={{ width: `${Math.round(fill * 100)}%` }} /></span>
            <span className="label">Época {n}{loss != null ? ` · pérdida ${loss.toFixed(3)}` : ''}</span>
          </div>
        );
      })}
    </div>
  );
}

// Con «Preparar para calibrar»: una celda por corrida (F1, F2, F3 y el modelo final).
function RunStrip({ job }) {
  const total = job.corridas || 0;
  const run = job.corrida || 0;
  const share = job.epocas_corrida && job.epoca
    ? (job.epoca - 1 + (job.lotes ? job.lote / job.lotes : 0)) / job.epocas_corrida : 0;
  const names = ['F1', 'F2', 'F3', 'Final'];
  return (
    <div className="train-epochs">
      {Array.from({ length: total }, (_, index) => {
        const n = index + 1;
        let fill = 0;
        if (job.estado === 'completado' || n < run || (n === run && job.fase !== 'entrenando')) fill = 1;
        else if (n === run) fill = Math.min(1, share);
        const active = n === run && job.fase === 'entrenando';
        return (
          <div key={n} className="train-epoch" data-active={active ? 'true' : undefined}>
            <span className="track"><i style={{ width: `${Math.round(fill * 100)}%` }} /></span>
            <span className="label">{n < total ? `Pliegue ${names[index]}` : 'Modelo final'}</span>
          </div>
        );
      })}
    </div>
  );
}

// Núcleo animado: anillo de progreso con un barrido que gira mientras entrena.
function Core({ job, color }) {
  const value = Math.round((job.progreso ?? 0) * 100);
  const radius = 52;
  const length = 2 * Math.PI * radius;
  const running = job.estado === 'en_curso';
  return (
    <div className={`train-core${running ? ' is-running' : ''}`} style={{ '--c': color }} role="img"
      aria-label={`Progreso ${value} %`}>
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <circle className="ring-track" cx="60" cy="60" r={radius} />
        <circle className="ring-value" cx="60" cy="60" r={radius} strokeDasharray={length}
          strokeDashoffset={length * (1 - value / 100)} />
        <g className="ring-orbit"><circle cx="60" cy="8" r="3" /></g>
        <circle className="ring-inner" cx="60" cy="60" r="38" />
      </svg>
      <div className="train-core-value">
        <b>{value}<small>%</small></b>
        <span className="label">{running ? 'avance' : STATES[job.estado]?.label}</span>
      </div>
    </div>
  );
}

function LossBars({ losses }) {
  if (!losses?.length) return null;
  const max = Math.max(...losses.map((item) => item.perdida), 1e-6);
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <span className="label">Pérdida por época</span>
      <div className="train-loss">
        {losses.map((item) => (
          <i key={item.epoca} style={{ height: `${Math.max(4, (item.perdida / max) * 100)}%` }}
            title={`Época ${item.epoca}: ${item.perdida.toFixed(4)}`} />
        ))}
      </div>
    </div>
  );
}

function Confirm({ label, busy, onConfirm }) {
  const [open, setOpen] = useState(false);
  if (!open) return <button type="button" className="btn btn--ghost btn--small" disabled={busy} onClick={() => setOpen(true)}>{label}</button>;
  return (
    <>
      <button type="button" className="btn btn--danger btn--small" disabled={busy} onClick={() => { setOpen(false); onConfirm(); }}>Sí, cancelar</button>
      <button type="button" className="btn btn--ghost btn--small" disabled={busy} onClick={() => setOpen(false)}>No</button>
    </>
  );
}

function RunPanel({ job, busy, onCancel }) {
  const running = job.estado === 'en_curso';
  const now = useNow(running);
  const color = CRITERIA[job.tipo].color;
  const phase = PHASES.find((item) => item.key === job.fase);
  const folding = job.corridas > 1 && job.corrida < job.corridas;
  const runLabel = job.corridas > 1 ? `Corrida ${job.corrida} de ${job.corridas} · ${folding ? `pliegue ${job.corrida_nombre}` : 'modelo final'} · ` : '';
  const detail = job.fase === 'entrenando' && job.epoca
    ? `${runLabel}Época ${job.epoca} de ${folding ? `${job.epocas_corrida} como máximo` : job.epocas}${job.lotes ? ` · lote ${job.lote} de ${job.lotes}` : ''}`
    : job.fase === 'descargando_base' ? 'Descargando el modelo base (una sola vez, ~440 MB)'
      : phase?.label ?? 'Arrancando el proceso';
  return (
    <section className={`panel panel--accent panel--mark train-run${running ? ' is-running' : ''}`} style={{ '--accent': color }}
      aria-live="polite" aria-busy={running}>
      <div className="version-head">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, minWidth: 0 }}>
          <CriterionIcon name={job.tipo} />
          <div style={{ minWidth: 0, display: 'grid', gap: 2 }}>
            <span className="label">{running ? 'Entrenando' : 'Último entrenamiento'} · {recipeName(job.tipo, job.receta)}</span>
            <strong className="mono" style={{ fontWeight: 400, color, overflowWrap: 'anywhere' }}>{job.version}</strong>
          </div>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          <span className={`tag ${STATES[job.estado]?.tag ?? ''}`}>
            {running && <i className="led led--blink" style={{ '--led': 'var(--color-acid)' }} />}
            {STATES[job.estado]?.label ?? job.estado}
          </span>
          {running && <Confirm label="Cancelar" busy={busy} onConfirm={onCancel} />}
        </div>
      </div>

      <div className="train-body">
        <Core job={job} color={color} />
        <div className="train-side">
          {running && (
            <div style={{ display: 'grid', gap: 8 }} role="status">
              <span className="label loader-code">{detail}</span>
              <Sweep />
            </div>
          )}
          <PhaseSteps job={job} />
          <dl className="kv">
            <dt>Tiempo</dt><dd>{clock(elapsed(job, now))}</dd>
            <dt>Datos</dt><dd>{sourceName(job.fuente)} · {job.datos?.entrenamiento ?? '—'} fragmentos{job.datos?.prueba ? ` · ${job.datos.prueba} de prueba` : ''}</dd>
            <dt>Receta</dt><dd>{job.receta?.configuracion} · {job.epocas} épocas · semilla {job.semilla}{job.receta?.brazo?.length && job.fuente?.tipo === 'comun_v1' ? ` · brazo ${job.receta.brazo.join(', ')}` : ''}</dd>
            <dt>Calibración</dt><dd>{job.pliegues ? 'Preparado: entrena también F1–F3 y guarda sus predicciones fuera de pliegue' : 'No preparado (sin pliegues)'}</dd>
            <dt>Equipo</dt><dd>{job.dispositivo === 'cuda' ? 'GPU (CUDA)' : 'Procesador (CPU)'}</dd>
          </dl>
        </div>
      </div>

      {job.pliegues && job.corridas > 1 && <RunStrip job={job} />}
      {(!job.pliegues || !(job.corridas > 1) || job.corrida === job.corridas || job.estado === 'completado') && <EpochStrip job={job} />}
      <LossBars losses={job.perdidas} />

      {job.estado === 'completado' && (
        <div className="alert alert--info" role="status" style={{ display: 'grid', gap: 10 }}>
          <span>
            Modelo nuevo guardado en <span className="mono">{job.salida}</span>. Aparece en Modelos como
            «Pendiente de calibrar»: el modelo desplegado no cambió.
            {job.pliegues ? ' Ya tiene sus predicciones fuera de pliegue: se puede calibrar.' : ' Se entrenó sin pliegues: no se podrá calibrar.'}
          </span>
          <span style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
            {job.pliegues && <Link className="text-link" to="/admin/calibracion">Calibrar →</Link>}
            <Link className="text-link" to="/admin/modelos">Ver en Modelos →</Link>
          </span>
        </div>
      )}
      {job.estado === 'completado' && job.metricas && (
        <div style={{ display: 'grid', gap: 10 }}>
          <span className="label">Prueba de la versión del panel</span>
          <Metrics model={{ tipo: job.tipo, metricas: job.metricas }} />
        </div>
      )}
      {job.estado === 'fallido' && <p className="alert" role="alert" style={{ margin: 0, overflowWrap: 'anywhere' }}>{job.error ?? 'El entrenamiento falló.'}</p>}
      {job.estado === 'cancelado' && <p className="alert alert--info" style={{ margin: 0 }}>Entrenamiento cancelado: no se guardó ningún modelo.</p>}

      {job.registro?.length > 0 && (
        <details>
          <summary className="text-link">Registro del proceso</summary>
          <pre className="train-log">{job.registro.join('\n')}</pre>
        </details>
      )}
    </section>
  );
}

// ── Formulario ──────────────────────────────────────────────────────

function sourceKey(source) {
  return source.tipo === 'panel' ? `panel:${source.version_id}` : 'comun_v1';
}

function TrainForm({ options, busy, disabled, onStart }) {
  const [type, setType] = useState('bilstm');
  const sources = options.fuentes;
  const firstUsable = sources.find((source) => source.tipo !== 'panel' || source.apta);
  const [key, setKey] = useState(firstUsable ? sourceKey(firstUsable) : '');
  const recipe = options.tipos[type];
  const [epochs, setEpochs] = useState('');
  const [seed, setSeed] = useState('42');
  const [device, setDevice] = useState(options.cuda ? 'cuda' : 'cpu');
  const [folds, setFolds] = useState(true);
  useEffect(() => { setEpochs(recipe?.epocas ? String(recipe.epocas) : ''); }, [type, recipe?.epocas]);
  const source = sources.find((item) => sourceKey(item) === key);
  const color = CRITERIA[type].color;
  const epochsValue = Number.parseInt(epochs, 10);
  const seedValue = Number.parseInt(seed, 10);
  const valid = recipe && source && (source.tipo !== 'panel' || source.apta)
    && Number.isInteger(epochsValue) && epochsValue >= 1 && epochsValue <= 50
    && Number.isInteger(seedValue) && seedValue >= 0 && (device === 'cpu' || options.cuda);
  const arms = recipe?.brazo ?? [];

  function submit(event) {
    event.preventDefault();
    if (!valid) return;
    onStart({
      tipo: type,
      fuente: source.tipo === 'panel' ? { tipo: 'panel', version_id: source.version_id } : { tipo: 'comun_v1' },
      epocas: epochsValue,
      semilla: seedValue,
      dispositivo: device,
      pliegues: folds,
    });
  }

  return (
    <form className="panel" style={{ display: 'grid', gap: 18 }} onSubmit={submit}>
      <h2 className="h-panel" style={{ margin: 0 }}>Nuevo entrenamiento</h2>

      <div className="grid-2">
        {TYPES.map((item) => (
          <button key={item} type="button" className="train-type" aria-pressed={type === item}
            style={{ '--c': CRITERIA[item].color }} onClick={() => setType(item)} disabled={busy}>
            <CriterionIcon name={item} />
            <span style={{ display: 'grid', gap: 2, textAlign: 'left' }}>
              <strong className="mono" style={{ fontWeight: 400 }}>{TYPE_NAMES[item]}</strong>
              <span className="label">{options.tipos[item] ? `Receta ${recipeName(item, options.tipos[item])}` : 'Sin receta'}</span>
            </span>
          </button>
        ))}
      </div>

      <div className="filter-grid">
        <label className="field" style={{ gridColumn: '1 / -1' }}>
          <span>Datos</span>
          <select className="input" value={key} disabled={busy} onChange={(event) => setKey(event.target.value)}>
            {sources.length === 0 && <option value="">No hay conjuntos disponibles</option>}
            {sources.map((item) => (
              <option key={sourceKey(item)} value={sourceKey(item)} disabled={item.tipo === 'panel' && !item.apta}>
                {item.tipo === 'panel'
                  ? `Panel · ${item.nombre} · ${item.fragmentos ?? 0} fragmentos${item.apta ? '' : ' (anterior al estándar)'}`
                  : `${item.nombre} · ${item.fragmentos ?? '—'} fragmentos`}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Épocas</span>
          <input className="input" type="number" min="1" max="50" required value={epochs} disabled={busy}
            onChange={(event) => setEpochs(event.target.value)} />
        </label>
        <label className="field">
          <span>Semilla</span>
          <input className="input" type="number" min="0" required value={seed} disabled={busy}
            onChange={(event) => setSeed(event.target.value)} />
        </label>
      </div>

      <div className="field">
        <span>Dónde entrenar</span>
        <div className="chips" role="group" aria-label="Dónde entrenar">
          {DEVICES.map((item) => {
            const off = item.key === 'cuda' && !options.cuda;
            return (
              <button key={item.key} type="button" className="chip" aria-pressed={device === item.key}
                style={{ '--tone': color }} disabled={busy || off} title={off ? 'No hay GPU con CUDA en este equipo.' : undefined}
                onClick={() => setDevice(item.key)}>
                <i className="led" />{item.label}{off ? ' · no disponible' : ''}
              </button>
            );
          })}
        </div>
      </div>

      <label className="train-check">
        <input type="checkbox" checked={folds} disabled={busy} onChange={(event) => setFolds(event.target.checked)} />
        <span>
          <strong>Preparar para calibrar</strong>
          <span className="muted">
            Entrena también los 3 pliegues (F1–F3) con la misma receta y guarda sus predicciones fuera de pliegue,
            como se hizo con B6 y M3b. Sin esto el modelo no se puede calibrar ni desplegar.
            Tarda unas 4 veces más{type === 'mbert' ? ' (con BETO, bastante tiempo: mejor en un equipo con GPU grande)' : ' (con el BiLSTM y comun_v1, cerca de un minuto en GPU)'}.
          </span>
        </span>
      </label>

      {recipe && (
        <dl className="kv" style={{ '--c': color }}>
          <dt>Receta</dt>
          <dd>
            {recipeName(type, recipe)} · {recipe.origen === 'desplegado' ? `del modelo desplegado (${recipe.modelo})` : 'del modelo de producción'}
          </dd>
          <dt>Brazos</dt>
          <dd>{arms.length ? arms.join(', ') : 'ninguno'}{arms.length && source?.tipo === 'panel' ? ' · no se usan: la versión del panel no los trae' : ''}</dd>
          <dt>Máx. tokens</dt><dd>{recipe.max_tokens ?? '—'}</dd>
          <dt>Parámetros</dt>
          <dd>{Object.entries(recipe.parametros ?? {}).map(([name, value]) => `${name} ${value}`).join(' · ') || '—'}</dd>
        </dl>
      )}
      {!recipe && options.errores_receta?.[type] && <p className="alert" style={{ margin: 0 }}>{options.errores_receta[type]}</p>}

      <ul className="muted" style={{ margin: 0, paddingLeft: 18, fontSize: 13, display: 'grid', gap: 4 }}>
        <li>Se entrena desde cero, con todos los fragmentos de entrenamiento y las épocas de la receta.</li>
        <li>El modelo se guarda como versión nueva en <span className="mono">{options.salida}/{type}/</span> y aparece en Modelos como «Pendiente de calibrar»; se calibra en <Link className="text-link" to="/admin/calibracion">Calibración</Link>. Aquí no se despliega, no se borra ni se sobrescribe ningún modelo.</li>
        <li>{source?.tipo === 'panel'
          ? (source.con_prueba ? 'Al terminar se evalúa con la prueba de la versión del panel.' : 'La versión no tiene prueba: el modelo saldrá sin métricas.')
          : 'Con comun_v1 no se abre la prueba congelada: el modelo saldrá sin métricas.'}</li>
      </ul>
      {!options.cuda && (
        <p className="alert alert--info" style={{ margin: 0 }}>No hay GPU con CUDA en este equipo: solo se puede entrenar con el procesador.</p>
      )}
      {device === 'cpu' && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Con el procesador tarda más que con la GPU{type === 'mbert' ? ': BETO / mBERT puede tardar horas' : ' (el BiLSTM, unos minutos con comun_v1)'}.
        </p>
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 }}>
        <button type="submit" className="btn" style={{ '--accent': color }} disabled={busy || disabled || !valid}>
          {busy ? 'Lanzando…' : `Entrenar ${TYPE_NAMES[type]}`}
        </button>
        {disabled && <span className="label">Hay un entrenamiento en curso</span>}
      </div>
    </form>
  );
}

// ── Historial ───────────────────────────────────────────────────────

function History({ jobs, selected, onSelect }) {
  return (
    <section className="panel">
      <h2 className="h-panel" style={{ margin: '0 0 14px' }}>Entrenamientos anteriores</h2>
      <div className="table-wrap">
        <table className="data">
          <thead><tr><th>Inicio</th><th>Tipo</th><th>Datos</th><th>Versión</th><th>Estado</th><th>Duración</th><th /></tr></thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id} aria-current={job.id === selected ? 'true' : undefined}>
                <td className="mono">{formatDate(job.inicio)}</td>
                <td style={{ color: CRITERIA[job.tipo].color }}>{recipeName(job.tipo, job.receta)}</td>
                <td>{sourceName(job.fuente)}</td>
                <td className="mono" style={{ overflowWrap: 'anywhere' }}>{job.version}</td>
                <td><span className={`tag ${STATES[job.estado]?.tag ?? ''}`}>{STATES[job.estado]?.label ?? job.estado}</span></td>
                <td className="num">{clock(elapsed(job, Date.now()))}</td>
                <td>
                  <button type="button" className="text-link" onClick={() => onSelect(job.id)}>Ver</button>
                  {job.estado === 'completado' && <>{' · '}<Link className="text-link" to="/admin/modelos">Modelos</Link></>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ── Página ──────────────────────────────────────────────────────────

export default function Training() {
  const options = useLoad((signal) => adminApi('/admin/entrenamientos/opciones', { signal }), []);
  const list = useLoad((signal) => adminApi('/admin/entrenamientos', { signal }), []);
  const [selected, setSelected] = useState(null);
  const [job, setJob] = useState(null);
  const [action, setAction] = useState({ busy: false, error: null });
  const listRef = useRef(list);
  listRef.current = list;

  const active = list.data?.activo ?? null;
  const shownId = selected ?? active?.id ?? list.data?.entrenamientos?.[0]?.id ?? null;

  // Detalle (con registro) del trabajo que se muestra; cada 2 s mientras está en curso.
  useEffect(() => {
    if (!shownId) { setJob(null); return undefined; }
    let cancelled = false;
    let timer = null;
    async function poll() {
      try {
        const fresh = await adminApi(`/admin/entrenamientos/${encodeURIComponent(shownId)}`);
        if (cancelled) return;
        setJob(fresh);
        if (fresh.estado === 'en_curso') timer = setTimeout(poll, POLL_MS);
        else if (listRef.current.data?.activo?.id === fresh.id) listRef.current.reload();
      } catch {
        if (!cancelled) timer = setTimeout(poll, POLL_MS * 2);
      }
    }
    poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [shownId]);

  // Sin trabajo en curso, la lista se refresca de vez en cuando (por si se lanzó en otra pestaña).
  useEffect(() => {
    const timer = setInterval(() => {
      if (!document.hidden && !action.busy) adminApi('/admin/entrenamientos').then(list.setData).catch(() => {});
    }, active ? POLL_MS * 5 : IDLE_MS);
    return () => clearInterval(timer);
  }, [active, action.busy, list.setData]);

  const jobs = list.data?.entrenamientos ?? [];
  const shown = useMemo(() => (job && job.id === shownId ? job : jobs.find((item) => item.id === shownId) ?? null), [job, jobs, shownId]);

  async function start(payload) {
    setAction({ busy: true, error: null });
    try {
      const created = await adminApi('/admin/entrenamientos', { method: 'POST', body: payload, timeout: 120_000 });
      setSelected(created.id);
      setJob(created);
      list.reload();
      setAction({ busy: false, error: null });
    } catch (error) { setAction({ busy: false, error }); }
  }

  async function cancel() {
    if (!shown) return;
    setAction({ busy: true, error: null });
    try {
      setJob(await adminApi(`/admin/entrenamientos/${encodeURIComponent(shown.id)}/cancelar`, { method: 'POST' }));
      list.reload();
      setAction({ busy: false, error: null });
    } catch (error) { setAction({ busy: false, error }); }
  }

  if ((options.loading && !options.data) || (list.loading && !list.data)) {
    return <div className="page-head"><Loader code="Leyendo entrenamientos" label="Cargando entrenamientos" rows={2} /></div>;
  }
  if (options.error && !options.data) return <div className="page-head"><ErrorState error={options.error} onRetry={options.reload} /></div>;
  if (list.error && !list.data) return <div className="page-head"><ErrorState error={list.error} onRetry={list.reload} /></div>;

  return (
    <div className="stack" style={{ paddingTop: 24 }}>
      <div className="section-head" style={{ margin: 0 }}>
        <h1 className="display h-page" style={{ margin: 0 }}>Entrenamiento</h1>
        <button type="button" className="btn btn--ghost" disabled={action.busy}
          onClick={() => { options.reload(); list.reload(); }}>Actualizar</button>
      </div>

      {action.error && <p className="alert" role="alert" style={{ margin: 0 }}>{action.error.message}</p>}
      {shown && <RunPanel key={shown.id} job={shown} busy={action.busy} onCancel={cancel} />}
      {options.data && <TrainForm options={options.data} busy={action.busy} disabled={Boolean(active)} onStart={start} />}
      {jobs.length > 0
        ? <History jobs={jobs} selected={shownId} onSelect={setSelected} />
        : <Empty title="Sin entrenamientos">Lanza el primero con el formulario: el modelo nuevo aparecerá en Modelos al terminar.</Empty>}
    </div>
  );
}
