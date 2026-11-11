import { useCallback, useEffect, useRef, useState } from 'react';
import { sendExtensionMessage } from '../extension-message.js';
import { presentHistoryDetail } from '../history-presentation.js';
import ResultGaugePanel from '../components/ResultGaugePanel.jsx';
import ResultInsights from '../components/ResultInsights.jsx';
import HudLoader from '../components/HudLoader.jsx';
import ScreenHeader, { ChevronIcon } from '../components/ScreenHeader.jsx';

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

  return <section className="screen-boot">
    <ScreenHeader title="Análisis anterior" backLabel="Volver al historial" onBack={onBack} disabled={deleting}>
      {shown && <p className="hud-readout mt-2 break-words">{shown.date}{shown.domain && <> · <span className="history-domain history-domain--inline">{shown.domain}</span></>}</p>}
    </ScreenHeader>

    {status === 'loading' && <HudLoader label="Cargando análisis" code="Abriendo archivo" count={2} />}
    {status === 'not_found' && <div className="mt-6"><p className="text-sm leading-5 text-muted">Este análisis ya no está disponible</p><button type="button" className="secondary-button mt-5" onClick={onBack}>Volver al historial</button></div>}
    {status === 'error' && <div className="mt-6" role="alert"><p className="text-sm leading-5 text-muted">No pudimos abrir este análisis.</p><button type="button" className="secondary-button mt-5" onClick={load}>Intentar de nuevo</button></div>}

    {shown && <>
      <span className="hud-code hud-code--cyan mt-5 mb-1.5" aria-hidden="true">Texto archivado</span>
      <div className="selection-preview max-h-[220px] overflow-y-auto whitespace-pre-wrap break-words text-sm leading-5" tabIndex="0" aria-label="Texto analizado">{shown.text ?? 'Texto no disponible'}</div>
      <div className="result-stack mt-4">
        <ResultGaugePanel level={shown.level} percentage={shown.percentage} />
        <ResultInsights result={item} level={shown.level} text={shown.text} url={item.url} showText={false} />
        {shown.hasBreakdown && <button type="button" className="result-detail" onClick={() => onBreakdown(item)} disabled={deleting}>
          <span>Ver desglose por modelo</span>
          <ChevronIcon />
        </button>}
      </div>

      {!confirming ? <button ref={deleteButton} type="button" className="secondary-button delete-button mt-7" onClick={() => setConfirming(true)}>Eliminar análisis</button>
        : <div className="delete-confirmation hud-panel mt-7" role="dialog" aria-labelledby="delete-title" onKeyDown={(event) => { if (event.key === 'Escape') cancelDelete(); }}>
          <div className="hazard-band" aria-hidden="true" />
          <span className="hud-code hud-code--magenta" aria-hidden="true">Orden de borrado · irreversible</span>
          <h2 id="delete-title" className="screen-title mt-1">¿Eliminar este análisis?</h2>
          {deleteError && <p className="hud-alert mt-3 text-sm" role="alert">{deleteError}</p>}
          <div className="mt-5 flex gap-3">
            <button ref={cancelButton} type="button" className="secondary-button" onClick={cancelDelete} disabled={deleting}>Cancelar</button>
            <button type="button" className="delete-confirm-button" onClick={confirmDelete} disabled={deleting}>{deleting ? 'Eliminando…' : 'Eliminar'}</button>
          </div>
        </div>}
    </>}
  </section>;
}
