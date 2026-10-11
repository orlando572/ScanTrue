import { useCallback, useEffect, useRef, useState } from 'react';
import { getPublishedMetrics } from '../../extension/metrics.js';
import { presentMetrics } from '../metrics-presentation.js';

function Evaluation({ evaluation }) {
  return <section className="metrics-evaluation">
    <h2 className="text-[14px] leading-5 font-semibold">{evaluation.name}</h2>
    {evaluation.accuracy !== null && <dl className="mt-3"><dt className="text-[12px] leading-[18px] text-muted">Aciertos en las pruebas</dt><dd className="mt-0.5 text-[22px] leading-[26px] font-semibold tabular-nums text-accent">{evaluation.accuracy}</dd></dl>}
    {evaluation.examples !== null && <p className="mt-3 text-[12px] leading-[18px] text-muted">{evaluation.examples} textos evaluados</p>}
    {evaluation.f1 !== null && <p className="mt-1 text-[12px] leading-[18px] text-muted">F1: {evaluation.f1}</p>}
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
    <div className="flex items-start gap-3">
      <button type="button" className="breakdown-back" aria-label="Volver" title="Volver" onClick={onBack}>
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m14 5-7 7 7 7" /></svg>
      </button>
      <h1 className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Pruebas del modelo</h1>
    </div>
    {status === 'loading' && <p className="mt-6 text-sm text-muted" role="status">Cargando pruebas…</p>}
    {status === 'error' && <div className="mt-6" role="alert"><p className="text-sm leading-5 text-muted">No pudimos cargar las pruebas.</p><button type="button" className="secondary-button mt-5" onClick={load}>Intentar de nuevo</button></div>}
    {shown?.map((model) => <section key={model.model} className="mt-5" aria-label={`Pruebas de ${model.model}`}>
      <h2 className="text-[14px] font-semibold text-ink">{model.model}</h2>
      {model.evaluations.length === 0 ? <p className="mt-4 text-sm text-muted">Aún no hay pruebas disponibles</p>
        : <div className="metrics-sheet mt-3">{model.evaluations.map((evaluation) => <Evaluation key={evaluation.key} evaluation={evaluation} />)}</div>}
    </section>)}
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
