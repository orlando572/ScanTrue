import { useCallback, useEffect, useRef, useState } from 'react';
import { sendExtensionMessage } from '../extension-message.js';
import { appendUniqueHistory, presentHistoryItem } from '../history-presentation.js';
import ScreenHeader, { ChevronIcon } from '../components/ScreenHeader.jsx';
import HudLoader, { LoaderSweep } from '../components/HudLoader.jsx';

function HistoryRow({ item, index, onOpen }) {
  const shown = presentHistoryItem(item);
  // Cada página nueva entra en cascada desde su primera fila (20 por página, máximo 10 pasos).
  return <li className="history-item" style={{ '--i': Math.min(index % 20, 10) }}>
    <button type="button" className="history-row" onClick={() => onOpen(shown.id)}>
      <span className="history-index" aria-hidden="true">#{String(index + 1).padStart(3, '0')}</span>
      <span className="min-w-0 flex-1 text-left">
        <span className="history-date">{shown.date}</span>
        <span className="history-preview mt-1 text-sm leading-5 font-semibold text-ink">{shown.title}</span>
        {shown.domain && <span className="history-domain mt-1">{shown.domain}</span>}
      </span>
      <span className={`history-result min-w-0 shrink-0 text-right${shown.tone ? ` result-panel--${shown.tone}` : ''}`}>
        {shown.percentage === null
          ? <span className="hud-readout block text-[11px] leading-4">Resultado no disponible</span>
          : <span className="history-percentage block tabular-nums" aria-label={`${shown.percentage}, ${shown.level}`}>{shown.percentage}</span>}
      </span>
      <span className="size-4 shrink-0 text-accent"><ChevronIcon /></span>
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

  return <section className="screen-boot">
    <ScreenHeader title="Historial de análisis" onBack={onBack} />
    {status === 'loading' && <HudLoader label="Cargando historial" code="Recuperando registros" shape="rows" count={5} />}
    {status === 'error' && <div className="mt-6" role="alert"><p className="text-sm leading-5 text-muted">{error}</p><button type="button" className="secondary-button mt-5" onClick={() => loadPage(0)}>Intentar de nuevo</button></div>}
    {status === 'ready' && items.length === 0 && <div className="hud-panel mt-6 empty-state">
      <span className="hud-code" aria-hidden="true">Registro vacío · 000 entradas</span>
      <p className="screen-title mt-2">Aún no hay análisis</p>
      <button type="button" className="primary-button mt-6" onClick={onChooseText}>Escoger texto</button>
    </div>}
    {status === 'ready' && items.length > 0 && <>
      <div className="mt-5 mb-2 flex justify-between" aria-hidden="true"><span className="hud-code hud-code--cyan">Registro de operaciones</span><span className="hud-code">{String(items.length).padStart(3, '0')} entradas</span></div>
      <ul className="history-log">{items.map((item, index) => <HistoryRow key={item.id} item={item} index={index} onOpen={onOpen} />)}</ul>
      {moreStatus === 'error' && <p className="hud-alert mt-4 text-sm leading-5" role="alert">{error}</p>}
      {hasMore && <button type="button" className="secondary-button mt-5" onClick={() => loadPage(nextOffset)} disabled={moreStatus === 'loading'}>{moreStatus === 'loading' ? <><LoaderSweep className="hud-loader-sweep--button" /><span className="sr-only">Cargando más análisis</span></> : moreStatus === 'error' ? 'Intentar de nuevo' : 'Cargar más'}</button>}
    </>}
  </section>;
}
