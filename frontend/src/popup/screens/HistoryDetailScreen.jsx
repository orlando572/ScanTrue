import { useCallback, useEffect, useRef, useState } from 'react';
import { sendExtensionMessage } from '../extension-message.js';
import { presentHistoryDetail } from '../history-presentation.js';
import ResultGaugePanel from '../components/ResultGaugePanel.jsx';

export default function HistoryDetailScreen({ id, onBack, onBreakdown, onLoaded, onDeleted, onDeletingChange }) {
  const [status, setStatus] = useState('loading');
  const [item, setItem] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const mounted = useRef(false);
  const loading = useRef(false);
  const deletingLock = useRef(false);
  const cancelButton = useRef(null);
  const deleteButton = useRef(null);

  const load = useCallback(async () => {
    if (loading.current) return;
    loading.current = true;
    setStatus('loading');
    try {
      const response = await sendExtensionMessage({ type: 'GET_HISTORY_DETAIL', id });
      if (!mounted.current) return;
      if (!response?.ok) throw new Error('No pudimos abrir este análisis.');
      if (!response.found) { setStatus('not_found'); return; }
      if (response.item?.id !== id) throw new Error('El análisis recibido no coincide.');
      setItem(response.item);
      onLoaded(response.item);
      setStatus('ready');
    } catch {
      if (mounted.current) setStatus('error');
    } finally { loading.current = false; }
  }, [id, onLoaded]);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => { mounted.current = false; };
  }, [load]);

  useEffect(() => {
    if (confirming) cancelButton.current?.focus();
  }, [confirming]);

  const cancelDelete = () => {
    if (deletingLock.current) return;
    setConfirming(false);
    setDeleteError('');
    requestAnimationFrame(() => deleteButton.current?.focus());
  };

  const confirmDelete = async () => {
    if (deletingLock.current) return;
    deletingLock.current = true;
    setDeleting(true);
    onDeletingChange(true);
    setDeleteError('');
    try {
      const response = await sendExtensionMessage({ type: 'DELETE_HISTORY_DETAIL', id });
      if (!response?.ok || response.deleted !== true) throw new Error('La eliminación no se confirmó.');
      if (mounted.current) onDeleted(id);
    } catch {
      if (mounted.current) setDeleteError('No pudimos eliminar este análisis. Inténtalo de nuevo.');
    } finally {
      deletingLock.current = false;
      onDeletingChange(false);
      if (mounted.current) setDeleting(false);
    }
  };

  const shown = status === 'ready' ? presentHistoryDetail(item) : null;

  return <section>
    <div className="flex items-start gap-3">
      <button type="button" className="breakdown-back" aria-label="Volver al historial" title="Volver al historial" onClick={onBack} disabled={deleting}>
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m14 5-7 7 7 7" /></svg>
      </button>
      <div className="min-w-0"><h1 className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Análisis anterior</h1>
        {shown && <p className="mt-2 break-words text-[12px] leading-[18px] text-muted">{shown.date}{shown.domain ? ` · ${shown.domain}` : ''}</p>}
      </div>
    </div>

    {status === 'loading' && <p className="mt-6 text-sm text-muted" role="status">Cargando análisis…</p>}
    {status === 'not_found' && <div className="mt-6"><p className="text-sm leading-5 text-muted">Este análisis ya no está disponible</p><button type="button" className="secondary-button mt-5" onClick={onBack}>Volver al historial</button></div>}
    {status === 'error' && <div className="mt-6" role="alert"><p className="text-sm leading-5 text-muted">No pudimos abrir este análisis.</p><button type="button" className="secondary-button mt-5" onClick={load}>Intentar de nuevo</button></div>}

    {shown && <>
      <div className="selection-preview mt-5 max-h-[220px] overflow-y-auto whitespace-pre-wrap break-words text-sm leading-5" tabIndex="0" aria-label="Texto analizado">{shown.text ?? 'Texto no disponible'}</div>
      <ResultGaugePanel level={shown.level} percentage={shown.percentage} className="mt-5" />
      {shown.hasBreakdown && <button type="button" className="result-detail mt-5" onClick={() => onBreakdown(item)} disabled={deleting}>
        <span>Ver desglose por modelo</span>
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m9 5 7 7-7 7" /></svg>
      </button>}

      {!confirming ? <button ref={deleteButton} type="button" className="secondary-button delete-button mt-7" onClick={() => setConfirming(true)}>Eliminar análisis</button>
        : <div className="delete-confirmation mt-7" role="dialog" aria-labelledby="delete-title" onKeyDown={(event) => { if (event.key === 'Escape') cancelDelete(); }}>
          <h2 id="delete-title" className="text-base font-semibold">¿Eliminar este análisis?</h2>
          {deleteError && <p className="mt-3 text-sm text-false" role="alert">{deleteError}</p>}
          <div className="mt-5 flex gap-3">
            <button ref={cancelButton} type="button" className="secondary-button" onClick={cancelDelete} disabled={deleting}>Cancelar</button>
            <button type="button" className="delete-confirm-button" onClick={confirmDelete} disabled={deleting}>{deleting ? 'Eliminando…' : 'Eliminar'}</button>
          </div>
        </div>}
    </>}
  </section>;
}
