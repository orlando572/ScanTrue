import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { getServiceHealth } from '../shared/api.js';
import { sendExtensionMessage } from './extension-message.js';
import ResultScreen from './screens/ResultScreen.jsx';
import BreakdownScreen from './screens/BreakdownScreen.jsx';
import HistoryScreen from './screens/HistoryScreen.jsx';
import HistoryDetailScreen from './screens/HistoryDetailScreen.jsx';
import MetricsScreen from './screens/MetricsScreen.jsx';
import AccountScreen from './screens/AccountScreen.jsx';
import RegisterScreen from './screens/RegisterScreen.jsx';
import LoginScreen from './screens/LoginScreen.jsx';
import ScreenHeader from './components/ScreenHeader.jsx';
import { CoreGrid, LedStrip, Radar, SegmentTrack } from './components/HudDecor.jsx';
import { countWords, meterState, presentFragments } from './selection-presentation.js';
import { presentServices } from './service-presentation.js';
import scanTrueMark from './assets/scantrue-mark.svg';

// Misma App en el panel lateral (sidepanel.html) y en el popup (popup.html).
const inPanel = typeof document !== 'undefined' && document.body.classList.contains('in-panel');

// Tiempo que se muestran los avisos que se cierran solos (la barra de cuenta atrás usa el mismo valor).
const NOTICE_MS = 6000;

const titles = { P01: 'Inicio', P02: 'Texto para analizar', P04: 'Analizando texto', P05: 'Resultado del análisis', P06: 'Desglose por modelo', P07: 'Historial de análisis', P08: 'Análisis anterior', P09: 'Pruebas del modelo', P11: 'Cuenta', P12: 'Crear cuenta', P13: 'Iniciar sesión' };

function Icon({ name }) {
  const paths = {
    history: <><path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4" /><path d="M12 7v5l3 2" /></>,
    metrics: <><path d="M3 20h18" /><path d="M5 17v-5h3v5M10.5 17V5h3v12M16 17V9h3v8" /></>,
    account: <><path d="M12 3l4 4-4 4-4-4z" /><path d="M4 21v-3l4-4h8l4 4v3" /></>,
    back: <path d="m14 5-7 7 7 7" />,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square" strokeLinejoin="miter">{paths[name]}</svg>;
}

function Brand({ onHome, disabled }) {
  return <button type="button" className="brand-button" aria-label="ScanTrue, ir al inicio" title="Ir al inicio" onClick={onHome} disabled={disabled}>
    <img src={scanTrueMark} alt="" className="brand-mark" />
    <span aria-hidden="true">
      <span className="brand-word">SCAN<i>//</i><em>TRUE</em></span>
      <span className="brand-sub">Análisis de noticias</span>
    </span>
  </button>;
}

const serviceLabels = {
  checking: 'Comprobando servicio…',
  available: 'Servicio disponible',
  degraded: 'Servicio parcialmente disponible',
  unavailable: 'La API local no responde. Enciéndela en este equipo y vuelve a intentarlo.',
  unknown: 'No se pudo confirmar el estado del servicio.',
};
const serviceCodes = { checking: 'Conectando…', available: 'En línea', degraded: 'Servicio limitado', unavailable: 'Sin conexión', unknown: 'Estado desconocido' };

// Aviso junto a la acción principal, solo cuando el servicio no está disponible.
function ServiceAlert({ health, onRetry }) {
  if (health !== 'unavailable' && health !== 'unknown') return null;
  return <div className={`hud-panel ${health === 'unavailable' ? 'hud-panel--false' : 'hud-panel--amber'} mt-4`} role="alert">
    <p className="hud-code" aria-hidden="true">{serviceCodes[health]}</p>
    <p className="mt-1 text-sm leading-5 text-ink">{serviceLabels[health]}</p>
    <button type="button" className="secondary-button mt-3" onClick={onRetry}>Reintentar</button>
  </div>;
}

function selectionDomain(url) {
  try {
    const parsed = new URL(url);
    return /^https?:$/.test(parsed.protocol) ? parsed.hostname : null;
  } catch { return null; }
}

function validationMessage(operation) {
  if (/(?:al menos|mínim[oa]).{0,40}token/i.test(`${operation?.message ?? ''} ${operation?.correction ?? ''}`)) {
    return 'El texto es muy corto. Añade más contenido.';
  }
  return [operation?.message, operation?.correction].filter(Boolean).join(' ');
}

function RemoveIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="square"><path d="M6 6l12 12M18 6 6 18" /></svg>;
}

function SelectionScreen({ selection, error, selecting, selectionMode, submitting, onAnalyze, onAddText, onEdit, onBack, onRemoveFragment, onClear }) {
  const domain = selectionDomain(selection.url);
  const fragments = presentFragments(selection);
  const meter = meterState(countWords(selection.text));
  return <>
    <ScreenHeader title="Texto para analizar" onBack={onBack}>
      {selectionMode && <span className="live-chip mt-2" role="status"><span aria-hidden="true">Seleccionando</span><span className="sr-only">Modo selección activo en la página</span></span>}
    </ScreenHeader>
    {domain && <p className="hud-readout mt-4">Origen: <b>{domain}</b></p>}

    <div className={`word-meter word-meter--${meter.level} mt-4`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="hud-code hud-code--cyan" aria-hidden="true">Longitud</span>
        <span className="hud-readout"><b>{meter.words}</b> palabras</span>
      </div>
      <SegmentTrack value={meter.value} segments={24} marker={meter.marker} />
      <p className="mt-1.5 text-[12px] leading-[18px] text-muted">{meter.message}</p>
    </div>

    {/* La acción principal va junto al medidor: no hay que bajar hasta el final de la lista. */}
    {error && <p className="hud-alert mt-3 text-[12px] leading-[18px]" role="alert">{error}</p>}
    <button type="button" className="primary-button mt-4" onClick={onAnalyze} disabled={submitting || selecting || !selection.text.trim()}>{submitting ? 'Iniciando análisis…' : 'Analizar'}</button>

    <div className="input-buffer-meta mt-5 items-center">
      <span className="hud-code hud-code--cyan" aria-hidden="true">Fragmentos · {String(fragments.length).padStart(2, '0')} marcados</span>
      <button type="button" className="clear-link" aria-label="Vaciar la selección" title="Empezar de cero" onClick={onClear} disabled={submitting || !selection.text.trim()}>Vaciar</button>
    </div>
    {fragments.length === 0
      ? <p className="fragment-empty">{selectionMode ? 'Selecciona texto en la página para añadirlo aquí.' : 'Aún no hay fragmentos. Pulsa «Seleccionar más texto» o escribe en «Editar texto completo».'}</p>
      : <ul className="fragment-list">{fragments.map((fragment) => <li key={fragment.id} className="fragment-item">
        <span className="fragment-number" aria-hidden="true">#{fragment.number}</span>
        <p className="fragment-text">{fragment.text}</p>
        <button type="button" className="fragment-remove" aria-label={`Quitar fragmento ${fragment.number}`} title="Quitar fragmento" onClick={() => onRemoveFragment(fragment.id)} disabled={submitting}><RemoveIcon /></button>
      </li>)}</ul>}

    <details className="metrics-details mt-4">
      <summary>Editar texto completo<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square"><path d="m6 9 6 6 6-6" /></svg></summary>
      <div className="border-t border-line p-3">
        <textarea className="selection-preview text-editor w-full resize-none overflow-y-auto text-sm leading-5" aria-label="Texto para analizar" placeholder="Escribe o pega texto aquí" value={selection.text} onChange={(event) => onEdit(event.target.value)} disabled={submitting || selecting} />
      </div>
    </details>

    {!selectionMode && <button type="button" className="secondary-button mt-5" onClick={onAddText} disabled={submitting || selecting}>{selecting ? 'Preparando selección…' : 'Seleccionar más texto'}</button>}
  </>;
}

function AnalysisScreen({ operation, onHistory, onBack, onRetry }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (operation?.status && operation.status !== 'working') return;
    const remaining = Math.max(0, 12_000 - (Date.now() - (operation?.startedAt ?? Date.now())));
    setSlow(remaining === 0);
    const timer = setTimeout(() => setSlow(true), remaining);
    return () => clearTimeout(timer);
  }, [operation?.id, operation?.status, operation?.startedAt]);

  if (operation?.status === 'uncertain') return <section className="analysis-message" role="alert">
    <div className="hud-panel hud-panel--amber">
      <h1 className="screen-title">No pudimos confirmar el resultado</h1>
      <p className="mt-3 text-sm leading-5 text-muted">Revisa tu historial antes de intentarlo de nuevo.</p>
    </div>
    <button type="button" className="secondary-button mt-6" onClick={onHistory}>Revisar historial</button>
  </section>;

  if (['session_error', 'service_error', 'storage_error', 'error'].includes(operation?.status)) {
    const session = operation.status === 'session_error';
    const storage = operation.status === 'storage_error';
    const title = session ? 'No pudimos iniciar tu sesión' : storage ? 'No pudimos guardar el análisis' : 'No pudimos iniciar el análisis';
    return <section className="analysis-message" role="alert">
      <div className="hud-panel hud-panel--false">
        <h1 className="screen-title">{title}</h1>
        <p className="mt-3 text-sm leading-5 text-muted">{session ? 'Comprueba que el servicio esté disponible e inténtalo de nuevo.' : storage ? 'El resultado no se pudo guardar o completar.' : operation.message}</p>
      </div>
      {operation.retryable && <button type="button" className="primary-button mt-6" onClick={onRetry}>Reintentar</button>}
      <button type="button" className="secondary-button mt-3" onClick={onBack}>Volver al texto</button>
    </section>;
  }

  return <section className="analysis-wait" role="status" aria-live="polite">
    <Radar active />
    <h1 className="screen-title mt-6">Analizando texto</h1>
    <p className={`mt-2 text-[12px] leading-[18px] ${slow ? 'text-amber' : 'text-muted'}`}>{slow ? 'Está tardando más de lo habitual.' : 'Esto puede tardar un momento.'}</p>
    <CoreGrid />
  </section>;
}

export default function App() {
  const [stack, setStack] = useState(['P01']);
  const [selection, setSelection] = useState(null);
  const [operation, setOperation] = useState(null);
  const [health, setHealth] = useState('checking');
  const [healthData, setHealthData] = useState(null);
  const [latency, setLatency] = useState(null);
  const [selectionError, setSelectionError] = useState('');
  const [analysisError, setAnalysisError] = useState('');
  const [selecting, setSelecting] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [resultError, setResultError] = useState('');
  const [selectedAnalysisId, setSelectedAnalysisId] = useState(null);
  const [historyDetail, setHistoryDetail] = useState(null);
  const [deletedAnalysis, setDeletedAnalysis] = useState(null);
  const [detailDeleting, setDetailDeleting] = useState(false);
  const [accountSigningOut, setAccountSigningOut] = useState(false);
  const [accountNotice, setAccountNotice] = useState(null);
  const analysisLock = useRef(false);
  const draftWrite = useRef(Promise.resolve());
  const draftVersion = useRef(0);
  const selectionRef = useRef(null);
  const popupScroll = useRef(null);
  const historyScroll = useRef(null);
  const current = stack.at(-1);
  // Desde el resultado, «Volver» regresa al texto analizado para poder editarlo.
  const resultStack = () => (selectionRef.current?.text?.trim() ? ['P01', 'P02', 'P05'] : ['P01', 'P05']);
  selectionRef.current = selection;

  useLayoutEffect(() => {
    if (current === 'P07' && historyScroll.current !== null && popupScroll.current) {
      popupScroll.current.scrollTop = historyScroll.current;
    }
  }, [current]);

  const refreshHealth = useCallback(async () => {
    setHealth('checking');
    const started = performance.now();
    try {
      const data = await getServiceHealth();
      setLatency(Math.round(performance.now() - started));
      setHealthData(data ?? null);
      if (data?.estado === 'ok' || data?.estado === 'saludable') setHealth('available');
      else if (data?.estado === 'degradado') setHealth('degraded');
      else setHealth('unknown');
    } catch { setLatency(null); setHealthData(null); setHealth('unavailable'); }
  }, []);

  useEffect(() => { refreshHealth(); }, [refreshHealth]);
  useEffect(() => {
    Promise.allSettled([
      sendExtensionMessage({ type: 'GET_PENDING_SELECTION' }),
      sendExtensionMessage({ type: 'GET_ANALYSIS_OPERATION' }),
    ]).then(([pendingResult, activeResult]) => {
      const pending = pendingResult.status === 'fulfilled' ? pendingResult.value : null;
      const active = activeResult.status === 'fulfilled' ? activeResult.value : null;
      const foundSelection = pending?.ok && typeof pending.selection?.text === 'string' ? pending.selection : null;
      const foundOperation = active?.ok ? active.operation : null;
      if (foundSelection) setSelection(foundSelection);
      if (pending?.ok) setSelectionMode(pending.selecting === true);
      if (foundOperation) setOperation(foundOperation);
      if (foundOperation?.status === 'completed') setStack(foundSelection ? ['P01', 'P02', 'P05'] : ['P01', 'P05']);
      else if (['working', 'error', 'uncertain', 'session_error', 'service_error', 'storage_error'].includes(foundOperation?.status)) setStack(['P01', 'P02', 'P04']);
      else if (foundSelection) {
        setStack(['P01', 'P02']);
        if (foundOperation?.status === 'validation') setAnalysisError(validationMessage(foundOperation));
      }
    }).catch(() => {});

    if (typeof chrome === 'undefined' || !chrome.storage?.onChanged) return;
    const handleChange = (changes, area) => {
      if (area !== 'session') return;
      if ('selectionTargetTabId' in changes) setSelectionMode(changes.selectionTargetTabId.newValue !== undefined);
      const pendingChange = changes.pendingSelection?.newValue;
      // Si se borra del almacenamiento, la App no conserva una copia vieja.
      if ('pendingSelection' in changes && !pendingChange) setSelection((previous) => previous && { text: '', fragments: [], url: null });
      if (pendingChange && pendingChange.updatedBy !== 'popup') {
        setSelection(pendingChange);
        if (pendingChange.updatedBy === 'page') setStack(['P01', 'P02']);
      }
      const next = changes.analysisOperation?.newValue;
      if (!next) return;
      setOperation(next);
      if (next.status === 'completed') setStack(resultStack());
      if (next.status === 'validation') {
        setAnalysisError(validationMessage(next));
        setStack(['P01', 'P02']);
      }
    };
    chrome.storage.onChanged.addListener(handleChange);
    return () => chrome.storage.onChanged.removeListener(handleChange);
  }, []);

  useEffect(() => {
    if (current !== 'P04' || operation?.status !== 'working') return;
    const timer = setInterval(() => {
      sendExtensionMessage({ type: 'GET_ANALYSIS_OPERATION' })
        .then((response) => {
          if (!response?.ok || !response.operation) return;
          setOperation(response.operation);
          if (response.operation.status === 'completed') setStack(resultStack());
          if (response.operation.status === 'validation') {
            setAnalysisError(validationMessage(response.operation));
            setStack(['P01', 'P02']);
          }
        })
        .catch(() => {});
    }, 5000);
    return () => clearInterval(timer);
  }, [current, operation?.status]);

  const open = (screen) => {
    if (!(screen in titles) || screen === current) return;
    if (screen === 'P07' && !stack.includes('P07')) {
      historyScroll.current = null;
      setDeletedAnalysis(null);
    }
    setStack((items) => {
      if (screen === 'P07' && items.includes('P07')) return items.slice(0, items.indexOf('P07') + 1);
      if (['P12', 'P13'].includes(items.at(-1)) && ['P12', 'P13'].includes(screen)) return [...items.slice(0, -1), screen];
      return [...items, screen];
    });
  };
  const back = () => setStack((items) => items.length > 1 ? items.slice(0, -1) : items);
  const editSelection = (text) => {
    const draft = { ...selectionRef.current, text, fragments: text.trim() ? [{ id: 'manual', text }] : [], url: null, capturedAt: Date.now(), updatedBy: 'popup' };
    selectionRef.current = draft;
    setSelection(draft);
    setSelectionError('');
    setAnalysisError('');
    const version = ++draftVersion.current;
    const write = draftWrite.current.catch(() => {}).then(async () => {
      await chrome.storage.session.set({ pendingSelection: draft });
      const { analysisOperation } = await chrome.storage.session.get('analysisOperation');
      if (analysisOperation?.status !== 'working') await chrome.storage.session.remove('analysisOperation');
    });
    draftWrite.current = write;
    void write.catch(() => {
      if (draftVersion.current === version) setSelectionError('No pudimos guardar los cambios del texto.');
    });
  };
  const persistSelection = async () => {
    try { await draftWrite.current; }
    catch { throw new Error('No pudimos guardar los cambios del texto.'); }
  };
  const startSelection = async () => {
    setSelectionError('');
    setAnalysisError('');
    setSelecting(true);
    try {
      // Primero, dentro del gesto del clic: Chrome solo muestra el permiso la primera vez.
      const granted = await chrome.permissions?.request?.({ origins: ['http://*/*', 'https://*/*'] }) ?? true;
      if (!granted) { setSelectionError('ScanTrue necesita permiso para leer la página y marcar el texto. Pulsa «Escoger texto» y acepta el permiso.'); return; }
      if (current === 'P02' && selection) await persistSelection();
      const response = await sendExtensionMessage({ type: 'START_SELECTION' });
      if (!response?.ok) { setSelectionError(response?.error ?? 'No se puede seleccionar texto en esta pestaña.'); return; }
      if (!inPanel) { window.close(); return; }
      // En el panel lateral la App sigue visible: se muestra la lista en vivo.
      setSelectionMode(true);
      setSelection((previous) => previous ?? { text: '', fragments: [], url: null });
      setStack(['P01', 'P02']);
    } catch (error) { setSelectionError(error?.message ?? 'No se puede seleccionar texto en esta pestaña. Prueba en una página web.'); }
    finally { setSelecting(false); }
  };

  const removeFragment = async (id) => {
    try {
      const response = await sendExtensionMessage({ type: 'REMOVE_FRAGMENT', id });
      if (response?.ok && response.selection) setSelection(response.selection);
      else setSelectionError('No pudimos quitar ese fragmento.');
    } catch { setSelectionError('No pudimos quitar ese fragmento.'); }
  };
  const clearSelection = async () => {
    setSelectionError('');
    setAnalysisError('');
    try {
      const response = await sendExtensionMessage({ type: 'CLEAR_FRAGMENTS' });
      if (!response?.ok) throw new Error();
      setSelection({ text: '', fragments: [], url: null });
    } catch { setSelectionError('No pudimos vaciar la selección. Inténtalo de nuevo.'); }
  };
  const stopSelectionMode = async () => {
    try {
      const response = await sendExtensionMessage({ type: 'STOP_SELECTION' });
      if (response?.ok) setSelectionMode(false);
    } catch { /* El aviso de la página se puede cerrar desde su propia barra. */ }
  };

  const analyze = async () => {
    if (analysisLock.current || !selection?.text?.trim()) return;
    analysisLock.current = true;
    setSubmitting(true);
    setAnalysisError('');
    try {
      await persistSelection();
      if (selectionMode) await stopSelectionMode();
      setStack(['P01', 'P02', 'P04']);
      const response = await sendExtensionMessage({ type: 'START_ANALYSIS' });
      if (!response?.ok) {
        setAnalysisError(response?.error ?? 'No pudimos iniciar el análisis.');
        setStack(['P01', 'P02']);
      } else if (response.operation) {
        setOperation((previous) => previous?.id === response.operation.id && previous.status !== 'working' ? previous : response.operation);
      }
    } catch (error) {
      setAnalysisError(error?.message ?? 'No pudimos iniciar el análisis. Inténtalo de nuevo.');
      setStack(['P01', 'P02']);
    } finally {
      analysisLock.current = false;
      setSubmitting(false);
    }
  };

  const startOver = async () => {
    if (clearing) return;
    setClearing(true);
    setResultError('');
    try {
      const response = await sendExtensionMessage({ type: 'CLEAR_COMPLETED_ANALYSIS' });
      if (!response?.ok) throw new Error('No se pudo limpiar el resultado.');
      // Empezar de cero: vacía los fragmentos y quita los resaltados de la página.
      await sendExtensionMessage({ type: 'CLEAR_FRAGMENTS' }).catch(() => {});
      setOperation(null);
      setSelection(null);
      setStack(['P01']);
    } catch { setResultError('No pudimos preparar una nueva selección. Inténtalo de nuevo.'); }
    finally { setClearing(false); }
  };

  // Los avisos de sesión iniciada se cierran solos; el de confirmación pendiente se queda.
  useEffect(() => {
    if (!accountNotice?.autoHide) return;
    const timer = setTimeout(() => setAccountNotice(null), NOTICE_MS);
    return () => clearTimeout(timer);
  }, [accountNotice]);

  const accountCompleted = (account) => {
    if (account.kind === 'pending_confirmation') {
      // Persistente: pide un paso al usuario y no debe perderse.
      setAccountNotice({ text: 'Te enviamos un correo de confirmación. Confirma tu cuenta y después inicia sesión aquí. Tu sesión invitada y su historial siguen disponibles.', autoHide: false });
    } else {
      const count = Number.isInteger(account.transferred) ? account.transferred : 0;
      setAccountNotice({
        text: account.guestHistorySkipped
          ? 'Sesión iniciada sin incorporar el historial invitado.'
          : count > 0
            ? `Sesión iniciada. Se incorporaron ${count} análisis de tu historial invitado.`
            : 'Sesión iniciada.',
        autoHide: true,
      });
      setOperation(null);
      setSelection(null);
      setHistoryDetail(null);
      setSelectedAnalysisId(null);
    }
    setStack(['P01', 'P11']);
  };

  return <div ref={popupScroll} className={`popup-shell flex flex-col text-ink ${current === 'P01' ? '' : 'min-h-[500px]'}`}>
    <header className="console-header">
      <div className="flex items-center justify-between px-5 py-3">
      <Brand onHome={() => setStack(['P01'])} disabled={detailDeleting || accountSigningOut} />
      <nav aria-label="Navegación principal" className="flex items-center gap-1.5">
        <button type="button" className="icon-button" aria-label="Historial" title="Historial" onClick={() => open('P07')} disabled={detailDeleting || accountSigningOut}><Icon name="history" /></button>
        <button type="button" className="icon-button" aria-label="Pruebas del modelo" title="Pruebas del modelo" onClick={() => open('P09')} disabled={detailDeleting || accountSigningOut}><Icon name="metrics" /></button>
        <button type="button" className="icon-button" aria-label="Cuenta" title="Cuenta" onClick={() => open('P11')} disabled={detailDeleting || accountSigningOut}><Icon name="account" /></button>
      </nav>
      </div>
      <LedStrip health={health} code={serviceCodes[health]} label={serviceLabels[health]} services={presentServices(healthData, health)} latency={latency} />
    </header>
    <main className={`flex flex-1 flex-col px-5 ${current === 'P01' ? 'pb-5 pt-2' : 'pb-6 pt-6'}`}>
      {current === 'P01' ? <>
        <div className="home-radar"><div className="radar-frame"><Radar /></div></div>
        <div className="hud-panel">
          <h1 className="screen-title">¿Dudas de una noticia?</h1>
          <p className="mt-2 text-sm leading-5 text-muted">Marca el titular y unos párrafos de la noticia. Te mostramos si se parece más a una noticia falsa o a una real.</p>
          <p className="mt-2 text-[12px] leading-[18px] text-muted opacity-80">Es una orientación, no una verificación de los hechos.</p>
          <ServiceAlert health={health} onRetry={refreshHealth} />
          <button type="button" className="primary-button mt-5" onClick={startSelection} disabled={selecting}>{selecting ? 'Preparando selección…' : 'Escoger texto'}</button>
          {selectionError && <p className="hud-alert mt-3 text-[12px] leading-[18px]" role="alert">{selectionError}</p>}
          {selection?.text?.trim() && <button type="button" className="text-link mt-4 w-fit" onClick={() => open('P02')}>Ver texto para analizar</button>}
        </div>
      </> : <>
        {current !== 'P02' && current !== 'P04' && current !== 'P05' && current !== 'P06' && current !== 'P07' && current !== 'P08' && current !== 'P09' && current !== 'P11' && current !== 'P12' && current !== 'P13' && <button type="button" className="text-link mb-5 flex w-fit items-center gap-1.5" onClick={back}><span className="size-5"><Icon name="back" /></span>Volver</button>}
        {stack.includes('P07') && <div hidden={current !== 'P07'}><HistoryScreen deletedAnalysis={deletedAnalysis} onBack={back} onOpen={(id) => { historyScroll.current = popupScroll.current?.scrollTop ?? 0; setHistoryDetail(null); setSelectedAnalysisId(id); open('P08'); }} onChooseText={() => setStack(['P01'])} /></div>}
        {stack.includes('P08') && selectedAnalysisId && <div hidden={current !== 'P08'}><HistoryDetailScreen key={selectedAnalysisId} id={selectedAnalysisId} onBack={back} onLoaded={setHistoryDetail} onDeletingChange={setDetailDeleting} onBreakdown={(item) => { setHistoryDetail(item); open('P06'); }} onDeleted={(id) => { setDeletedAnalysis({ id }); setHistoryDetail(null); setSelectedAnalysisId(null); back(); }} /></div>}
        {current === 'P02' && selection ? <SelectionScreen selection={selection} error={analysisError || selectionError} selecting={selecting} selectionMode={selectionMode} submitting={submitting} onAnalyze={analyze} onAddText={startSelection} onEdit={editSelection} onBack={back} onRemoveFragment={removeFragment} onClear={clearSelection} />
          : current === 'P04' ? <AnalysisScreen operation={operation} onHistory={() => open('P07')} onBack={() => setStack(['P01', 'P02'])} onRetry={analyze} />
          : current === 'P05' ? <ResultScreen result={operation?.result} onBack={back} onBreakdown={() => open('P06')} onStartOver={startOver} clearing={clearing} error={resultError} />
          : current === 'P06' ? <BreakdownScreen result={stack.at(-2) === 'P08' ? historyDetail : operation?.result} onBack={back} />
          : current === 'P07' ? null
          : current === 'P08' ? null
          : current === 'P09' ? <MetricsScreen onBack={back} />
          : current === 'P11' ? <AccountScreen notice={accountNotice} noticeMs={NOTICE_MS} onBack={back} onLogin={() => { setAccountNotice(null); open('P13'); }} onRegister={() => { setAccountNotice(null); open('P12'); }} onSigningOutChange={setAccountSigningOut} onSignedOut={() => { setAccountNotice(null); setOperation(null); setSelection(null); setHistoryDetail(null); setSelectedAnalysisId(null); setStack(['P01', 'P11']); }} />
          : current === 'P12' ? <RegisterScreen onBack={back} onLogin={() => open('P13')} onComplete={accountCompleted} />
          : current === 'P13' ? <LoginScreen onBack={back} onRegister={() => open('P12')} onComplete={accountCompleted} />
          : <><h1 className="screen-title">{titles[current]}</h1><p className="mt-4 text-sm text-muted">Sección en preparación.</p></>}
      </>}
    </main>
  </div>;
}
