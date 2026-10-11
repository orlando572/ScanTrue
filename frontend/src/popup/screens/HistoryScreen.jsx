import { useCallback, useEffect, useRef, useState } from 'react';
import { sendExtensionMessage } from '../extension-message.js';
import { appendUniqueHistory, presentHistoryItem } from '../history-presentation.js';

function HistoryRow({ item, onOpen }) {
  const shown = presentHistoryItem(item);
  return <li className="border-t border-line">
    <button type="button" className="history-row" onClick={() => onOpen(shown.id)}>
      <span className="min-w-0 flex-1 text-left">
        <span className="block text-[12px] leading-[18px] text-muted">{shown.date}</span>
        <span className="history-preview mt-1 text-sm leading-5 font-semibold text-ink">{shown.title}</span>
        {shown.domain && <span className="mt-1 block truncate text-[12px] leading-[18px] text-muted">{shown.domain}</span>}
      </span>
      <span className={`history-result min-w-0 shrink-0 text-right${shown.tone ? ` result-panel--${shown.tone}` : ''}`}>
        {shown.percentage === null
          ? <span className="block text-[11px] leading-4 text-muted">Resultado no disponible</span>
          : <span className="history-percentage block font-semibold tabular-nums" aria-label={`${shown.percentage}, ${shown.level}`}>{shown.percentage}</span>}
      </span>
      <svg aria-hidden="true" className="size-4 shrink-0 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m9 5 7 7-7 7" /></svg>
    </button>
  </li>;
}

export default function HistoryScreen({ deletedAnalysis, onBack, onOpen, onChooseText }) {
  const [items, setItems] = useState([]);
  const [nextOffset, setNextOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [status, setStatus] = useState('loading');
  const [moreStatus, setMoreStatus] = useState('idle');
  const [error, setError] = useState('');
  const busy = useRef(false);
  const mounted = useRef(false);

  const loadPage = useCallback(async (offset) => {
    if (busy.current) return;
    busy.current = true;
    setError('');
    if (offset === 0) setStatus('loading');
    else setMoreStatus('loading');
    try {
      const response = await sendExtensionMessage({ type: 'LIST_HISTORY', offset });
      if (!response?.ok || !Array.isArray(response.page?.items)) throw new Error(response?.error ?? 'No pudimos cargar el historial.');
      if (!mounted.current) return;
      setItems((previous) => appendUniqueHistory(offset === 0 ? [] : previous, response.page.items));
      setNextOffset(response.page.nextOffset);
      setHasMore(response.page.hasMore && response.page.items.length > 0);
      setStatus('ready');
      setMoreStatus('idle');
    } catch (cause) {
      if (!mounted.current) return;
      setError(cause?.message === 'Tu sesión ya no está disponible.' ? cause.message : 'No pudimos cargar el historial. Inténtalo de nuevo.');
      if (offset === 0) setStatus('error');
      else setMoreStatus('error');
    } finally { busy.current = false; }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void loadPage(0);
    return () => { mounted.current = false; };
  }, [loadPage]);

  useEffect(() => {
    if (!deletedAnalysis?.id) return;
    if (!items.some((item) => item.id === deletedAnalysis.id)) return;
    setItems((previous) => previous.filter((item) => item.id !== deletedAnalysis.id));
    setNextOffset((offset) => Math.max(0, offset - 1));
  }, [deletedAnalysis]);

  return <section>
    <div className="flex items-center gap-3">
      <button type="button" className="icon-button shrink-0" aria-label="Volver" title="Volver" onClick={onBack}>
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m14 5-7 7 7 7" /></svg>
      </button>
      <h1 className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Historial de análisis</h1>
    </div>
    {status === 'loading' && <p className="mt-6 text-sm text-muted" role="status">Cargando historial…</p>}
    {status === 'error' && <div className="mt-6" role="alert"><p className="text-sm leading-5 text-muted">{error}</p><button type="button" className="secondary-button mt-5" onClick={() => loadPage(0)}>Intentar de nuevo</button></div>}
    {status === 'ready' && items.length === 0 && <div className="mt-8 text-center">
      <p className="text-base font-semibold">Aún no hay análisis</p>
      <button type="button" className="primary-button mt-6" onClick={onChooseText}>Escoger texto</button>
    </div>}
    {status === 'ready' && items.length > 0 && <>
      <ul className="mt-6 border-b border-line">{items.map((item) => <HistoryRow key={item.id} item={item} onOpen={onOpen} />)}</ul>
      {moreStatus === 'error' && <p className="mt-4 text-sm leading-5 text-muted" role="alert">{error}</p>}
      {hasMore && <button type="button" className="secondary-button mt-5" onClick={() => loadPage(nextOffset)} disabled={moreStatus === 'loading'}>{moreStatus === 'loading' ? 'Cargando más…' : moreStatus === 'error' ? 'Intentar de nuevo' : 'Cargar más'}</button>}
    </>}
  </section>;
}
