import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { CriterionIcon } from '../../components/Analysis.jsx';
import { ErrorState, Loader, SegmentBar, Sweep } from '../../components/ui.jsx';
import { adminApi } from '../../lib/api.js';
import { useLoad } from '../../lib/hooks.js';
import { CRITERIA, formatDate } from '../../lib/presentation.js';

const TYPES = ['bilstm', 'mbert'];
const TYPE_NAMES = { bilstm: 'BiLSTM', mbert: 'BETO / mBERT' };
const METHOD_NAMES = {
  bilstm_sin_calibrar: 'BiLSTM sin calibrar',
  mbert_sin_calibrar: 'BETO sin calibrar',
  media_70_30_actual: 'Media 70/30 sin calibrar (la de antes)',
  bilstm_calibrado: 'BiLSTM calibrado',
  mbert_calibrado: 'BETO calibrado',
  regresion_logistica_libre: 'Regresión logística (pesos libres)',
  regresion_logistica_pesos_no_negativos: 'Regresión logística (pesos ≥ 0)',
  combinacion_elegida: 'Combinación elegida (T a mano)',
  bilstm_elegido: 'BiLSTM con la T elegida',
  mbert_elegido: 'BETO con la T elegida',
};
const methodName = (key) => {
  const match = /^combinacion_bilstm_(\d\.\d+)$/.exec(key);
  if (match) {
    const weight = Math.round(Number(match[1]) * 100);
    return `Combinación ${weight}/${100 - weight}`;
  }
  return METHOD_NAMES[key] ?? key;
};
const pct = (value, digits = 1) => (value == null ? '—' : `${(value * 100).toFixed(digits)} %`);
const num = (value, digits = 3) => (value == null ? '—' : Number(value).toFixed(digits));
const temp = (value) => (value == null ? '—' : Number(value).toFixed(4));

// ── Resultado ───────────────────────────────────────────────────────

function Temperatures({ result }) {
  return (
    <div className="tiles">
      {TYPES.map((type) => {
        const t = result.temperaturas?.[type] ?? {};
        return (
          <div key={type} className="tile" style={{ '--c': CRITERIA[type].color }}>
            <span className="label">T {TYPE_NAMES[type]}{t.manual ? ' · a mano' : ''}</span>
            <b>{temp(t.usada)}</b>
            <small>{t.manual ? `ajustada: ${temp(t.ajustada)}` : 'ajustada con sus predicciones fuera de pliegue'}</small>
          </div>
        );
      })}
      <div className="tile">
        <span className="label">Pesos</span>
        <b>{Math.round((result.combinacion?.pesos?.bilstm ?? 0) * 100)}/{Math.round((result.combinacion?.pesos?.mbert ?? 0) * 100)}</b>
        <small>BiLSTM / BETO en el resultado unificado</small>
      </div>
    </div>
  );
}

function ValidationTable({ validation, chosen }) {
  const rows = Object.entries(validation ?? {});
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr><th>Método</th><th>F1 art. (media)</th><th>Falsas alarmas</th><th>AUC frag.</th><th>Log-loss</th><th>Brier</th><th>ECE</th></tr>
        </thead>
        <tbody>
          {rows.map(([key, item]) => (
            <tr key={key} aria-current={key === chosen ? 'true' : undefined}>
              <td style={key === chosen ? { color: 'var(--accent)' } : undefined}>{methodName(key)}{key === chosen ? ' · elegida' : ''}</td>
              <td className="num">{num(item.f1_macro_articulo_media_pliegues)}</td>
              <td className="num">{pct(item.articulo?.tasa_falsas_alarmas)}</td>
              <td className="num">{num(item.fragmento?.auc_roc)}</td>
              <td className="num">{num(item.log_loss_fragmento)}</td>
              <td className="num">{num(item.fragmento?.brier)}</td>
              <td className="num">{num(item.ece_fragmento)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Levels({ rows, color }) {
  if (!rows?.length) return null;
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      {rows.map((row) => (
        <div key={row.nivel} className="calib-level">
          <span className="name">{row.nivel}</span>
          <SegmentBar value={row.pct_falsas == null ? 0 : row.pct_falsas * 100} cells={25} color={color} />
          <span className="mono">{row.pct_falsas == null ? '—' : pct(row.pct_falsas, 0)}</span>
          <span className="label">objetivo {row.objetivo} · {row.fragmentos} frag.</span>
          <span className={`tag ${row.dentro_objetivo === true ? 'tag--ok' : row.dentro_objetivo === false ? 'tag--warn' : ''}`}>
            {row.dentro_objetivo === true ? 'dentro' : row.dentro_objetivo === false ? 'fuera' : '—'}
          </span>
        </div>
      ))}
    </div>
  );
}

function ResultView({ result }) {
  const data = result.resultado ?? {};
  const joint = result.conjunto_comun !== false && data.validacion_por_fuente;
  return (
    <div className="stack" style={{ gap: 20 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        {result.igual_a_produccion
          ? <span className="tag tag--ok">Igual a la calibración en producción</span>
          : <span className="tag tag--warn">Distinta de la calibración en producción</span>}
        {result.combinacion?.version && <span className="label">{result.combinacion.version}</span>}
      </div>
      <Temperatures result={result} />
      {joint ? (
        <>
          <section style={{ display: 'grid', gap: 10 }}>
            <h3 className="h-panel" style={{ margin: 0 }}>Validación por fuente</h3>
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>
              Cada parámetro se ajusta con dos fuentes y se mide en la tercera. La fila elegida es la que se guardaría.
            </p>
            <ValidationTable validation={data.validacion_por_fuente} chosen={data.metodo_elegido} />
          </section>
          <section style={{ display: 'grid', gap: 10 }}>
            <h3 className="h-panel" style={{ margin: 0 }}>Niveles de la extensión</h3>
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>Porcentaje de noticias realmente falsas en cada nivel (validación por fuente).</p>
            <Levels rows={data.niveles?.combinacion_por_fuente} color="var(--accent)" />
          </section>
          <details>
            <summary className="text-link">Regla de discrepancia y comparaciones (bootstrap)</summary>
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table className="data">
                <thead><tr><th>Umbral</th><th>Fragmentos</th><th>F1 art.</th><th>AUC frag.</th><th>Brier</th></tr></thead>
                <tbody>
                  {Object.entries(data.regla_discrepancia ?? {}).map(([key, row]) => (
                    <tr key={key}><td>{key}</td><td className="num">{row.fragmentos}</td><td className="num">{row.f1_articulo}</td>
                      <td className="num">{row.auc_fragmento}</td><td className="num">{row.brier_fragmento}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="muted" style={{ margin: '12px 0 0', paddingLeft: 18, fontSize: 13 }}>
              {Object.entries(data.comparaciones_pareadas ?? {}).map(([name, item]) => (
                <li key={name}>{name}: {item.diferencia >= 0 ? '+' : ''}{num(item.diferencia)} (IC 95 % {num(item.ic95?.[0])} a {num(item.ic95?.[1])})</li>
              ))}
            </ul>
          </details>
        </>
      ) : (
        <section style={{ display: 'grid', gap: 14 }}>
          <p className="alert alert--info" style={{ margin: 0 }}>
            Los dos modelos no comparten conjunto: cada temperatura se ajusta con las predicciones de su modelo y la
            combinación no se puede validar en conjunto.
          </p>
          {TYPES.map((type) => (
            <div key={type} style={{ display: 'grid', gap: 8 }}>
              <span className="label" style={{ color: CRITERIA[type].color }}>{TYPE_NAMES[type]} · F1 art. {num(data.validacion_por_modelo?.[type]?.f1_macro_articulo_media_pliegues)} · ECE {num(data.validacion_por_modelo?.[type]?.ece_fragmento)}</span>
              <Levels rows={data.niveles?.[type]} color={CRITERIA[type].color} />
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

// ── Formulario ──────────────────────────────────────────────────────

function ModelSelect({ type, candidates, value, onChange, busy }) {
  return (
    <label className="field">
      <span>{TYPE_NAMES[type]}</span>
      <select className="input" value={value ?? ''} disabled={busy} onChange={(event) => onChange(event.target.value)}>
        {candidates.length === 0 && <option value="">No hay modelos</option>}
        {candidates.map((item) => (
          <option key={item.id} value={item.id} disabled={!item.apto} title={item.motivo ?? undefined}>
            {item.nombre} · {item.id}{item.apto ? '' : ' (no calibrable)'}
          </option>
        ))}
      </select>
    </label>
  );
}

function TemperatureField({ type, mode, value, fitted, onMode, onValue, busy }) {
  return (
    <div className="field">
      <span>Temperatura {TYPE_NAMES[type]}</span>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <div className="chips" role="group" aria-label={`Temperatura ${TYPE_NAMES[type]}`}>
          {[['ajustada', 'Ajustada'], ['manual', 'A mano']].map(([key, label]) => (
            <button key={key} type="button" className="chip" aria-pressed={mode === key} disabled={busy}
              style={{ '--tone': CRITERIA[type].color }} onClick={() => onMode(key)}>{label}</button>
          ))}
        </div>
        {mode === 'manual'
          ? <input className="input" type="number" min="0.01" max="100" step="0.0001" value={value} disabled={busy}
            style={{ maxWidth: 140 }} aria-label={`T ${TYPE_NAMES[type]}`} onChange={(event) => onValue(event.target.value)} />
          : <span className="mono muted">{fitted != null ? temp(fitted) : 'se calcula al calibrar'}</span>}
      </div>
    </div>
  );
}

// ── Página ──────────────────────────────────────────────────────────

export default function Calibration() {
  const options = useLoad((signal) => adminApi('/admin/calibraciones/opciones', { signal, timeout: 60_000 }), []);
  const list = useLoad((signal) => adminApi('/admin/calibraciones', { signal }), []);
  const [pair, setPair] = useState({ bilstm: null, mbert: null });
  const [weight, setWeight] = useState(20);
  const [modes, setModes] = useState({ bilstm: 'ajustada', mbert: 'ajustada' });
  const [values, setValues] = useState({ bilstm: '', mbert: '' });
  const [motivo, setMotivo] = useState('');
  const [result, setResult] = useState(null);
  const [state, setState] = useState({ busy: null, error: null, saved: null });

  useEffect(() => {
    const defaults = options.data?.por_defecto;
    if (!defaults) return;
    setPair((current) => ({ bilstm: current.bilstm ?? defaults.bilstm, mbert: current.mbert ?? defaults.mbert }));
    setWeight(Math.round((defaults.peso_bilstm ?? 0.2) * 100));
  }, [options.data]);

  const defaultWeight = Math.round((options.data?.por_defecto?.peso_bilstm ?? 0.2) * 100);
  const manual = TYPES.some((type) => modes[type] === 'manual');
  const needsReason = manual || weight !== defaultWeight;
  const temperatures = Object.fromEntries(TYPES.map((type) => [type, modes[type] === 'manual' ? Number(values[type]) : null]));
  const validTemps = TYPES.every((type) => modes[type] !== 'manual' || (Number(values[type]) > 0 && Number(values[type]) <= 100));
  const ready = pair.bilstm && pair.mbert && validTemps;
  const body = { bilstm: pair.bilstm, mbert: pair.mbert, peso_bilstm: weight / 100, temperaturas: temperatures };
  const fitted = useMemo(() => Object.fromEntries(TYPES.map((type) => [type, result?.temperaturas?.[type]?.ajustada ?? null])), [result]);

  function setMode(type, mode) {
    setModes((current) => ({ ...current, [type]: mode }));
    if (mode === 'manual' && !values[type]) {
      const candidate = options.data?.candidatos?.[type]?.find((item) => item.id === pair[type]);
      const start = fitted[type] ?? candidate?.temperatura ?? 1;
      setValues((current) => ({ ...current, [type]: String(start) }));
    }
  }

  async function preview() {
    setState({ busy: 'Ajustando temperaturas y validando por fuente', error: null, saved: null });
    try {
      setResult(await adminApi('/admin/calibraciones/vista-previa', { method: 'POST', body, timeout: 180_000 }));
      setState({ busy: null, error: null, saved: null });
    } catch (error) { setState({ busy: null, error, saved: null }); }
  }

  async function save() {
    setState({ busy: 'Guardando la versión calibrada', error: null, saved: null });
    try {
      const saved = await adminApi('/admin/calibraciones', { method: 'POST', body: { ...body, motivo }, timeout: 180_000 });
      setState({ busy: null, error: null, saved });
      list.reload();
      options.reload();
    } catch (error) { setState({ busy: null, error, saved: null }); }
  }

  async function show(version) {
    setState({ busy: 'Leyendo la calibración', error: null, saved: null });
    try {
      const detail = await adminApi(`/admin/calibraciones/${encodeURIComponent(version)}`);
      const adjusted = detail.temperaturas_ajustadas ?? detail.temperaturas;
      setResult({
        combinacion: { version: detail.version, pesos: detail.pesos, temperaturas: detail.temperaturas },
        temperaturas: Object.fromEntries(TYPES.map((type) => [type, {
          ajustada: adjusted?.[type], usada: detail.temperaturas?.[type], manual: detail.temperaturas_manuales?.includes(type),
        }])),
        igual_a_produccion: JSON.stringify(detail.temperaturas) === JSON.stringify(options.data?.produccion?.temperaturas)
          && JSON.stringify(detail.pesos) === JSON.stringify(options.data?.produccion?.pesos),
        conjunto_comun: detail.resultado?.conjunto_comun !== false,
        resultado: detail.resultado,
      });
      setState({ busy: null, error: null, saved: null });
    } catch (error) { setState({ busy: null, error, saved: null }); }
  }

  if (options.loading && !options.data) return <div className="page-head"><Loader code="Buscando modelos calibrables" label="Cargando calibración" rows={2} /></div>;
  if (options.error && !options.data) return <div className="page-head"><ErrorState error={options.error} onRetry={options.reload} /></div>;

  const data = options.data;
  const current = data.vigente;
  const production = data.produccion;
  const busy = Boolean(state.busy);

  return (
    <div className="stack" style={{ paddingTop: 24 }}>
      <div className="section-head" style={{ margin: 0 }}>
        <h1 className="display h-page" style={{ margin: 0 }}>Calibración</h1>
        <button type="button" className="btn btn--ghost" disabled={busy} onClick={() => { options.reload(); list.reload(); }}>Actualizar</button>
      </div>

      <section className="panel" style={{ display: 'grid', gap: 12 }}>
        <h2 className="h-panel" style={{ margin: 0 }}>Calibración vigente</h2>
        {current ? (
          <dl className="kv">
            <dt>Versión</dt><dd>{current.version}</dd>
            <dt>Temperaturas</dt><dd>BiLSTM {temp(current.temperaturas?.bilstm)} · BETO {temp(current.temperaturas?.mbert)}</dd>
            <dt>Pesos</dt><dd>{Math.round(current.pesos.bilstm * 100)} / {Math.round(current.pesos.mbert * 100)}</dd>
            <dt>Contratos</dt><dd>{TYPES.map((type) => current.contratos?.[type]).filter(Boolean).join(' + ')}</dd>
          </dl>
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            La pareja desplegada ({Object.values(data.desplegados ?? {}).join(' + ') || 'ninguna'}) no tiene una calibración guardada:
            los análisis usan la temperatura de cada contrato y los pesos del panel.
          </p>
        )}
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Calibrar ajusta la temperatura de cada modelo con sus predicciones fuera de pliegue y fija los pesos de la combinación.
          Guardar crea una versión calibrada nueva (contratos que usan los mismos pesos del modelo): no cambia lo desplegado.
          Se despliega desde <Link className="text-link" to="/admin/modelos">Modelos</Link>.
        </p>
      </section>

      <section className="panel" style={{ display: 'grid', gap: 18 }}>
        <h2 className="h-panel" style={{ margin: 0 }}>Calibrar una pareja</h2>
        <div className="grid-2">
          {TYPES.map((type) => (
            <div key={type} style={{ display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr)', gap: 12, alignItems: 'end' }}>
              <CriterionIcon name={type} />
              <ModelSelect type={type} candidates={data.candidatos[type] ?? []} value={pair[type]} busy={busy}
                onChange={(id) => { setPair((currentPair) => ({ ...currentPair, [type]: id })); setResult(null); }} />
            </div>
          ))}
        </div>
        {TYPES.map((type) => {
          const chosen = data.candidatos[type]?.find((item) => item.id === pair[type]);
          return chosen && !chosen.apto ? <p key={type} className="alert" style={{ margin: 0 }}>{chosen.nombre}: {chosen.motivo}</p> : null;
        })}

        <label className="field">
          <span>Peso en el resultado · BiLSTM {weight} % · BETO / mBERT {100 - weight} %{weight === defaultWeight ? ' (el vigente)' : ''}</span>
          <input type="range" min="0" max="100" step="5" value={weight} disabled={busy}
            aria-label="Peso del BiLSTM" onChange={(event) => setWeight(Number(event.target.value))} />
        </label>

        <div className="grid-2">
          {TYPES.map((type) => (
            <TemperatureField key={type} type={type} mode={modes[type]} value={values[type]} fitted={fitted[type]} busy={busy}
              onMode={(mode) => setMode(type, mode)} onValue={(value) => setValues((currentValues) => ({ ...currentValues, [type]: value }))} />
          ))}
        </div>

        <label className="field">
          <span>Motivo{needsReason ? ' (obligatorio: el peso o las temperaturas no son los vigentes)' : ' (opcional)'}</span>
          <textarea className="input" rows={2} maxLength={2000} value={motivo} disabled={busy}
            placeholder={production?.motivo_pesos ? 'Si lo dejas vacío, se usa el motivo de la calibración vigente.' : ''}
            onChange={(event) => setMotivo(event.target.value)} />
        </label>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
          <button type="button" className="btn" disabled={busy || !ready} onClick={preview}>Calcular</button>
          <button type="button" className="btn btn--ghost" disabled={busy || !ready || (needsReason && !motivo.trim())} onClick={save}>
            Guardar calibración
          </button>
          <span className="label">Con B6 + M3b, peso 20 y temperaturas ajustadas sale la calibración de producción.</span>
        </div>

        {state.busy && (
          <div style={{ display: 'grid', gap: 8 }} role="status">
            <span className="label loader-code">{state.busy}</span>
            <Sweep />
          </div>
        )}
        {state.error && <p className="alert" role="alert" style={{ margin: 0 }}>{state.error.message}</p>}
        {state.saved && (
          <div className="alert alert--info" role="status" style={{ display: 'grid', gap: 8 }}>
            <span>
              Calibración <span className="mono">{state.saved.version}</span> guardada. Sus contratos calibrados
              ({Object.values(state.saved.contratos ?? {}).join(' + ')}) ya aparecen en Modelos como «Disponible»; lo desplegado no cambió.
            </span>
            <Link className="text-link" to="/admin/modelos">Desplegar desde Modelos →</Link>
          </div>
        )}
      </section>

      {result && (
        <section className="panel panel--accent" style={{ display: 'grid', gap: 16 }}>
          <h2 className="h-panel" style={{ margin: 0 }}>Resultado</h2>
          <ResultView result={result} />
        </section>
      )}

      <section className="panel">
        <h2 className="h-panel" style={{ margin: '0 0 14px' }}>Calibraciones guardadas</h2>
        {list.loading && !list.data ? <Loader code="Leyendo calibraciones" rows={1} /> : (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>Fecha</th><th>Versión</th><th>Pareja</th><th>T BiLSTM</th><th>T BETO</th><th>Pesos</th><th /></tr></thead>
              <tbody>
                {[...(list.data?.produccion ? [list.data.produccion] : []), ...(list.data?.calibraciones ?? [])].map((item) => (
                  <tr key={item.version} aria-current={current?.version === item.version ? 'true' : undefined}>
                    <td className="mono">{item.fecha ? formatDate(item.fecha) : 'producción'}</td>
                    <td className="mono" style={{ overflowWrap: 'anywhere' }}>{item.version}{current?.version === item.version ? ' · vigente' : ''}</td>
                    <td>{TYPES.map((type) => item.modelos_origen?.[type]?.id ?? item.contratos?.[type]).filter(Boolean).join(' + ')}</td>
                    <td className="num">{temp(item.temperaturas?.bilstm)}{item.temperaturas_manuales?.includes('bilstm') ? ' ✎' : ''}</td>
                    <td className="num">{temp(item.temperaturas?.mbert)}{item.temperaturas_manuales?.includes('mbert') ? ' ✎' : ''}</td>
                    <td className="num">{Math.round((item.pesos?.bilstm ?? 0) * 100)}/{Math.round((item.pesos?.mbert ?? 0) * 100)}</td>
                    <td><button type="button" className="text-link" disabled={busy} onClick={() => show(item.version)}>Ver</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted" style={{ margin: '12px 0 0', fontSize: 13 }}>✎ = temperatura escrita a mano.</p>
      </section>
    </div>
  );
}
