import { useCallback, useEffect, useRef, useState } from 'react';
import { getPublishedMetrics } from '../../extension/metrics.js';
import { presentMetrics } from '../metrics-presentation.js';
import ScreenHeader from '../components/ScreenHeader.jsx';
import { SegmentTrack } from '../components/HudDecor.jsx';
import ModelIcon from '../components/ModelIcon.jsx';

// Cada modelo usa el mismo color que su luz en la tira de estado.
const modelColors = { BiLSTM: { key: 'bilstm', color: '#38E1FF' }, mBERT: { key: 'mbert', color: '#A98BFF' } };
// Etiqueta de color según el tipo de conjunto de prueba.
const setTones = { 'Validación': 'green', 'Prueba interna': 'magenta', 'Fuentes reservadas': 'amber', 'Prueba externa': 'amber', 'Prueba': 'cyan' };

function Evaluation({ evaluation }) {
  const accuracy = Number.parseFloat(evaluation.accuracy ?? '');
  const f1 = Number.parseFloat(evaluation.f1 ?? '');
  return <section className="metrics-evaluation">
    <div className="flex items-start justify-between gap-3">
      <h3 className="flex min-w-0 items-center gap-2 text-[14px] leading-5 font-semibold">
        <span className={`set-tag set-tag--${setTones[evaluation.name] ?? 'neutral'}`} aria-hidden="true" />{evaluation.name}
      </h3>
      {evaluation.examples !== null && <span className="metrics-count">{evaluation.examples} textos</span>}
    </div>
    {evaluation.accuracy !== null && <dl className="mt-3">
      <dt className="hud-label text-[11px]">Aciertos en las pruebas</dt>
      <dd className="metrics-value mt-1">{evaluation.accuracy}</dd>
    </dl>}
    {Number.isFinite(accuracy) && <SegmentTrack value={accuracy} segments={25} />}
    {evaluation.f1 !== null && <div className="metrics-f1 mt-3">
      <div className="flex items-baseline justify-between"><span className="hud-label text-[11px]">F1</span><span className="metrics-f1-value">{evaluation.f1}</span></div>
      {Number.isFinite(f1) && <SegmentTrack value={f1} segments={25} />}
    </div>}
  </section>;
}

export default function MetricsScreen({ onBack }) {
  const [status, setStatus] = useState('loading');
  const [data, setData] = useState(null);
  const [unavailable, setUnavailable] = useState([]);
  const loading = useRef(false);
  const mounted = useRef(false);

  const load = useCallback(async () => {
    if (loading.current) return;
    loading.current = true;
    setStatus('loading');
    try {
      const models = ['bilstm', 'mbert'];
      const responses = await Promise.allSettled(models.map(getPublishedMetrics));
      if (!mounted.current) return;
      const available = [];
      const missing = [];
      responses.forEach((result, index) => {
        const metrics = result.status === 'fulfilled' ? result.value : null;
        if (metrics?.modelo === models[index] && Array.isArray(metrics.evaluaciones)) available.push(metrics);
        else missing.push(models[index] === 'mbert' ? 'mBERT' : 'BiLSTM');
      });
      if (available.length === 0) throw new Error('No pudimos cargar las métricas.');
      setData(available);
      setUnavailable(missing);
      setStatus('ready');
    } catch {
      if (mounted.current) setStatus('error');
    } finally { loading.current = false; }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => { mounted.current = false; };
  }, [load]);

  const shown = status === 'ready' ? data.map(presentMetrics) : null;
  const testNotes = (shown?.find((model) => model.model === 'BiLSTM')?.limitations ?? [])
    .filter((note) => note !== 'La salida de probabilidad_falsa del clasificador no está calibrada como probabilidad de falsedad factual.');

  return <section>
    <ScreenHeader title="Pruebas del modelo" onBack={onBack} />
    {status === 'loading' && <p className="hud-readout mt-6" role="status">Cargando pruebas…</p>}
    {status === 'error' && <div className="mt-6" role="alert"><p className="text-sm leading-5 text-muted">No pudimos cargar las pruebas.</p><button type="button" className="secondary-button mt-5" onClick={load}>Intentar de nuevo</button></div>}
    {shown?.map((model) => {
      const identity = modelColors[model.model] ?? { key: 'bilstm', color: '#38E1FF' };
      return <section key={model.model} className="metrics-model mt-5" style={{ '--model-color': identity.color }} aria-label={`Pruebas de ${model.model}`}>
        <div className="flex items-center gap-2.5">
          <span className="metrics-model-icon"><ModelIcon model={identity.key} /></span>
          <h2 className="metrics-model-name">{model.model}</h2>
          {model.evaluations.length > 0 && <span className="hud-code ml-auto">{model.evaluations.length} {model.evaluations.length === 1 ? 'prueba' : 'pruebas'}</span>}
        </div>
        {model.evaluations.length === 0 ? <p className="mt-4 text-sm text-muted">Aún no hay pruebas disponibles</p>
          : <div className="metrics-sheet hud-panel mt-3">{model.evaluations.map((evaluation) => <Evaluation key={evaluation.key} evaluation={evaluation} />)}</div>}
      </section>;
    })}
    {testNotes.length > 0 && <details className="metrics-details mt-5">
      <summary>Sobre estas pruebas<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg></summary>
      <div className="border-t border-line px-4 py-3">{testNotes.map((note, index) => <p key={index} className="mt-1 whitespace-pre-wrap break-words text-[12px] leading-[18px] text-muted">{note}</p>)}</div>
    </details>}
    {status === 'ready' && unavailable.length > 0 && <div className="mt-5" role="alert">
      <p className="text-sm leading-5 text-muted">No pudimos cargar las pruebas de {unavailable.join(' y ')}.</p>
      <button type="button" className="secondary-button mt-3" onClick={load}>Intentar de nuevo</button>
    </div>}
  </section>;
}
