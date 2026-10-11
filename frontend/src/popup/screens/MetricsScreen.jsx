import { useCallback, useEffect, useRef, useState } from 'react';
import { sendExtensionMessage } from '../extension-message.js';
import { presentMetrics } from '../metrics-presentation.js';

function Metric({ label, percentage }) {
  return <div><dt className="text-[12px] leading-[18px] text-muted">{label}</dt><dd className="mt-1 text-[24px] leading-7 font-semibold tabular-nums text-accent">{percentage}</dd></div>;
}

function Evaluation({ evaluation }) {
  return <section className="metrics-evaluation">
    <h3 className="text-base leading-[22px] font-semibold">{evaluation.name}</h3>
    {evaluation.examples !== null && <p className="mt-1 text-[12px] leading-[18px] text-muted">{evaluation.examples} ejemplos</p>}
    {evaluation.source && <p className="mt-1 break-words text-[12px] leading-[18px] text-muted">Fuente: {evaluation.source}</p>}
    {evaluation.main.length > 0 && <dl className="mt-5 grid grid-cols-2 gap-4">{evaluation.main.map((metric) => <Metric key={metric.label} {...metric} />)}</dl>}
    {evaluation.extra.length > 0 && <details className="metrics-details mt-5">
      <summary>Ver más medidas<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg></summary>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-5 border-t border-line px-4 py-5">{evaluation.extra.map((metric) => <Metric key={metric.label} {...metric} />)}</dl>
    </details>}
  </section>;
}

export default function MetricsScreen({ onBack }) {
  const [status, setStatus] = useState('loading');
  const [data, setData] = useState(null);
  const loading = useRef(false);
  const mounted = useRef(false);

  const load = useCallback(async () => {
    if (loading.current) return;
    loading.current = true;
    setStatus('loading');
    try {
      const response = await sendExtensionMessage({ type: 'GET_METRICS' });
      if (!mounted.current) return;
      if (!response?.ok || !Array.isArray(response.metrics?.evaluaciones)) throw new Error('No pudimos cargar las métricas.');
      setData(response.metrics);
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

  const shown = status === 'ready' ? presentMetrics(data) : null;

  return <section>
    <div className="flex items-start gap-3">
      <button type="button" className="breakdown-back" aria-label="Volver" title="Volver" onClick={onBack}>
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m14 5-7 7 7 7" /></svg>
      </button>
      <h1 className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Métricas de evaluación</h1>
    </div>
    {status === 'loading' && <p className="mt-6 text-sm text-muted" role="status">Cargando métricas…</p>}
    {status === 'error' && <div className="mt-6" role="alert"><p className="text-sm leading-5 text-muted">No pudimos cargar las métricas.</p><button type="button" className="secondary-button mt-5" onClick={load}>Intentar de nuevo</button></div>}
    {shown && <>
      {shown.model && <p className="mt-6 text-base font-semibold">{shown.model}</p>}
      {shown.version && <p className="mt-1 break-all text-[12px] leading-[18px] text-muted">Versión: {shown.version}</p>}
      <p className="mt-3 text-[12px] leading-[18px] text-muted">Evaluaciones publicadas del modelo.</p>
      {shown.evaluations.length === 0 ? <p className="mt-8 text-sm text-muted">Aún no hay métricas disponibles</p>
        : <div className="metrics-sheet mt-5">{shown.evaluations.map((evaluation) => <Evaluation key={evaluation.key} evaluation={evaluation} />)}</div>}
      {shown.limitations.length > 0 && <section className="mt-6"><h2 className="text-base font-semibold">Limitaciones</h2>
        {shown.limitations.map((limitation, index) => <p key={index} className="mt-2 whitespace-pre-wrap break-words text-sm leading-5 text-muted">{limitation}</p>)}
      </section>}
    </>}
  </section>;
}
