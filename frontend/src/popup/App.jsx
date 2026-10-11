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

const titles = { P01: 'Inicio', P02: 'Texto seleccionado', P04: 'Analizando texto', P05: 'Resultado del análisis', P06: 'Desglose por modelo', P07: 'Historial de análisis', P08: 'Análisis anterior', P09: 'Métricas de evaluación', P11: 'Cuenta', P12: 'Crear cuenta', P13: 'Iniciar sesión' };

function Icon({ name }) {
  const paths = {
    history: <><path d="M3 12a9 9 0 1 0 2.6-6.4M3 4v4h4" /><path d="M12 7v5l3 2" /></>,
    account: <><circle cx="12" cy="8" r="3.5" /><path d="M5 21a7 7 0 0 1 14 0" /></>,
    back: <path d="m14 5-7 7 7 7" />,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function Brand() {
  return <div className="flex items-center gap-2.5 text-ink">
    <span className="grid size-9 place-items-center rounded-[10px] border border-line bg-white text-accent" aria-hidden="true">
      <svg viewBox="0 0 28 28" className="size-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M7 2.5h10l5 5V24H7z" /><path d="M17 2.5v5h5" /><path d="m10 16 3 3 6-7" /></svg>
    </span>
    <span className="text-[18px] font-semibold tracking-[-0.03em]">Scan<span className="text-accent">True</span></span>
  </div>;
}

function DocumentIllustration() {
  return <div className="document-art" aria-hidden="true"><span className="document-art__rail" />
    <svg viewBox="0 0 112 128" fill="none" className="h-32 w-28">
      <path d="M16 2h55l25 25v96a3 3 0 0 1-3 3H16a3 3 0 0 1-3-3V5a3 3 0 0 1 3-3Z" fill="#F8FBFB" stroke="#D6E1E4" strokeWidth="2" />
      <path d="M71 2v22a3 3 0 0 0 3 3h22" fill="#E3EBEE" />
      <rect x="26" y="35" width="25" height="22" rx="2" fill="#CEDDE1" />
      <path d="M59 39h23M59 47h23M26 66h56" stroke="#BCCDD2" strokeWidth="5" strokeLinecap="round" />
      <rect x="24" y="76" width="63" height="24" rx="4" fill="#CFEFEB" />
      <path d="M29 83h49M29 92h41" stroke="#087D77" strokeWidth="5" strokeLinecap="round" />
      <path d="M26 111h43" stroke="#BCCDD2" strokeWidth="5" strokeLinecap="round" />
    </svg>
  </div>;
}

function ServiceStatus({ health, onRetry }) {
  const labels = {
    checking: 'Comprobando servicio…',
    available: 'Servicio disponible',
    degraded: 'Servicio parcialmente disponible',
    unavailable: 'La API local no responde. Enciéndela en este equipo y vuelve a intentarlo.',
    unknown: 'No se pudo confirmar el estado del servicio.',
  };
  return <footer className="border-t border-line bg-white px-5 py-4" role="status" aria-live="polite">
    <div className="flex items-start gap-2.5 text-[12px] leading-[18px] text-muted">
      <span className={`status-dot status-dot--${health}`} aria-hidden="true" />
      <div className="flex-1">{labels[health]}
        {(health === 'unavailable' || health === 'unknown') && <button type="button" className="ml-2 font-semibold text-accent underline underline-offset-2" onClick={onRetry}>Reintentar</button>}
      </div>
    </div>
  </footer>;
}

function selectionDomain(url) {
  try {
    const parsed = new URL(url);
    return /^https?:$/.test(parsed.protocol) ? parsed.hostname : null;
  } catch { return null; }
}

function SelectionScreen({ selection, error, selecting, submitting, onAnalyze, onReselect }) {
  const domain = selectionDomain(selection.url);
  return <>
    <h1 className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Texto seleccionado</h1>
    {domain && <p className="mt-3 text-[12px] text-muted">Origen: {domain}</p>}
    <div className="selection-preview mt-5 max-h-[180px] overflow-y-auto whitespace-pre-wrap break-words text-sm leading-5" tabIndex="0" aria-label="Fragmento seleccionado">{selection.text}</div>
    <p className="mt-5 text-[12px] leading-[18px] text-muted">
      {selection.url ? 'Al analizar, enviaremos este texto y la dirección de la página. Guardaremos el texto en tu historial.' : 'Al analizar, enviaremos este texto y lo guardaremos en tu historial.'}
    </p>
    {error && <p className="mt-3 text-[12px] leading-[18px] text-[#A3342B]" role="alert">{error}</p>}
    <button type="button" className="primary-button mt-5" onClick={onAnalyze} disabled={submitting || selecting}>{submitting ? 'Iniciando análisis…' : 'Analizar'}</button>
    <button type="button" className="secondary-button mt-3" onClick={onReselect} disabled={submitting || selecting}>{selecting ? 'Preparando selección…' : 'Seleccionar de nuevo'}</button>
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
    <h1 className="text-[22px] leading-7 font-semibold">No pudimos confirmar el resultado</h1>
    <p className="mt-3 text-sm leading-5 text-muted">Revisa tu historial antes de intentarlo de nuevo.</p>
    <button type="button" className="secondary-button mt-6" onClick={onHistory}>Revisar historial</button>
  </section>;

  if (['session_error', 'service_error', 'storage_error', 'error'].includes(operation?.status)) {
    const session = operation.status === 'session_error';
    const storage = operation.status === 'storage_error';
    const title = session ? 'No pudimos iniciar tu sesión' : storage ? 'No pudimos guardar el análisis' : 'No pudimos iniciar el análisis';
    return <section className="analysis-message" role="alert">
      <h1 className="text-[22px] leading-7 font-semibold">{title}</h1>
      <p className="mt-3 text-sm leading-5 text-muted">{session ? 'Comprueba que el servicio esté disponible e inténtalo de nuevo.' : storage ? 'El resultado no se pudo guardar o completar.' : operation.message}</p>
      {operation.retryable && <button type="button" className="primary-button mt-6" onClick={onRetry}>Reintentar</button>}
      <button type="button" className="secondary-button mt-3" onClick={onBack}>Volver al texto</button>
    </section>;
  }

  return <section className="analysis-wait" role="status" aria-live="polite">
    <div className="analysis-art" aria-hidden="true">
      <svg viewBox="0 0 110 128" fill="none" className="h-32 w-28">
        <path d="M20 3h53l26 26v86a7 7 0 0 1-7 7H20a7 7 0 0 1-7-7V10a7 7 0 0 1 7-7Z" stroke="#C8D9DE" strokeWidth="3" />
        <path d="M73 3v20a6 6 0 0 0 6 6h20" stroke="#C8D9DE" strokeWidth="3" />
        <path d="M31 49h45M31 62h45M31 75h34" stroke="#C8D9DE" strokeWidth="5" strokeLinecap="round" />
        <path d="M31 89h29" stroke="#087D77" strokeWidth="5" strokeLinecap="round" />
      </svg>
      <span className="analysis-indicator" />
    </div>
    <h1 className="mt-7 text-[22px] leading-7 font-semibold">Analizando texto</h1>
    <p className="mt-3 text-sm leading-5 text-muted">Estamos preparando el resultado de tu selección.</p>
    <p className="mt-2 text-[12px] leading-[18px] text-muted">{slow ? 'Está tardando más de lo habitual.' : 'Esto puede tardar un momento.'}</p>
  </section>;
}

export default function App() {
  const [stack, setStack] = useState(['P01']);
  const [selection, setSelection] = useState(null);
  const [operation, setOperation] = useState(null);
  const [health, setHealth] = useState('checking');
  const [selectionError, setSelectionError] = useState('');
  const [analysisError, setAnalysisError] = useState('');
  const [selecting, setSelecting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [resultError, setResultError] = useState('');
  const [selectedAnalysisId, setSelectedAnalysisId] = useState(null);
  const [historyDetail, setHistoryDetail] = useState(null);
  const [deletedAnalysis, setDeletedAnalysis] = useState(null);
  const [detailDeleting, setDetailDeleting] = useState(false);
  const [accountSigningOut, setAccountSigningOut] = useState(false);
  const analysisLock = useRef(false);
  const popupScroll = useRef(null);
  const historyScroll = useRef(null);
  const current = stack.at(-1);

  useLayoutEffect(() => {
    if (current === 'P07' && historyScroll.current !== null && popupScroll.current) {
      popupScroll.current.scrollTop = historyScroll.current;
    }
  }, [current]);

  const refreshHealth = useCallback(async () => {
    setHealth('checking');
    try {
      const data = await getServiceHealth();
      if (data?.estado === 'ok' || data?.estado === 'saludable') setHealth('available');
      else if (data?.estado === 'degradado') setHealth('degraded');
      else setHealth('unknown');
    } catch { setHealth('unavailable'); }
  }, []);

  useEffect(() => { refreshHealth(); }, [refreshHealth]);
  useEffect(() => {
    Promise.allSettled([
      sendExtensionMessage({ type: 'GET_PENDING_SELECTION' }),
      sendExtensionMessage({ type: 'GET_ANALYSIS_OPERATION' }),
    ]).then(([pendingResult, activeResult]) => {
      const pending = pendingResult.status === 'fulfilled' ? pendingResult.value : null;
      const active = activeResult.status === 'fulfilled' ? activeResult.value : null;
      const foundSelection = pending?.ok ? pending.selection : null;
      const foundOperation = active?.ok ? active.operation : null;
      if (foundSelection?.text) setSelection(foundSelection);
      if (foundOperation) setOperation(foundOperation);
      if (foundOperation?.status === 'completed') setStack(['P01', 'P05']);
      else if (['working', 'error', 'uncertain', 'session_error', 'service_error', 'storage_error'].includes(foundOperation?.status)) setStack(['P01', 'P02', 'P04']);
      else if (foundSelection?.text) {
        setStack(['P01', 'P02']);
        if (foundOperation?.status === 'validation') setAnalysisError([foundOperation.message, foundOperation.correction].filter(Boolean).join(' '));
      }
    }).catch(() => {});

    if (typeof chrome === 'undefined' || !chrome.storage?.onChanged) return;
    const handleChange = (changes, area) => {
      if (area !== 'session') return;
      if (changes.pendingSelection?.newValue) {
        setSelection(changes.pendingSelection.newValue);
        setStack(['P01', 'P02']);
      }
      const next = changes.analysisOperation?.newValue;
      if (!next) return;
      setOperation(next);
      if (next.status === 'completed') setStack(['P01', 'P05']);
      if (next.status === 'validation') {
        setAnalysisError([next.message, next.correction].filter(Boolean).join(' '));
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
          if (response.operation.status === 'completed') setStack(['P01', 'P05']);
          if (response.operation.status === 'validation') {
            setAnalysisError([response.operation.message, response.operation.correction].filter(Boolean).join(' '));
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
  const startSelection = async () => {
    setSelectionError('');
    setAnalysisError('');
    setSelecting(true);
    try {
      const response = await sendExtensionMessage({ type: 'START_SELECTION' });
      if (!response?.ok) { setSelectionError(response?.error ?? 'No se puede seleccionar texto en esta pestaña.'); return; }
      window.close();
    } catch { setSelectionError('No se puede seleccionar texto en esta pestaña. Prueba en una página web.'); }
    finally { setSelecting(false); }
  };

  const analyze = async () => {
    if (analysisLock.current || !selection?.text) return;
    analysisLock.current = true;
    setSubmitting(true);
    setAnalysisError('');
    setStack(['P01', 'P02', 'P04']);
    try {
      const response = await sendExtensionMessage({ type: 'START_ANALYSIS' });
      if (!response?.ok) {
        setAnalysisError(response?.error ?? 'No pudimos iniciar el análisis.');
        setStack(['P01', 'P02']);
      } else if (response.operation) {
        setOperation((previous) => previous?.id === response.operation.id && previous.status !== 'working' ? previous : response.operation);
      }
    } catch {
      setAnalysisError('No pudimos iniciar el análisis. Inténtalo de nuevo.');
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
      setOperation(null);
      setSelection(null);
      setStack(['P01']);
    } catch { setResultError('No pudimos preparar una nueva selección. Inténtalo de nuevo.'); }
    finally { setClearing(false); }
  };

  return <div ref={popupScroll} className="popup-shell flex min-h-[500px] flex-col bg-canvas text-ink">
    <header className="flex items-center justify-between border-b border-line bg-white px-5 py-4">
      <Brand />
      <nav aria-label="Navegación principal" className="flex items-center gap-1">
        <button type="button" className="icon-button" aria-label="Historial" title="Historial" onClick={() => open('P07')} disabled={detailDeleting || accountSigningOut}><Icon name="history" /></button>
        <button type="button" className="icon-button" aria-label="Cuenta" title="Cuenta" onClick={() => open('P11')} disabled={detailDeleting || accountSigningOut}><Icon name="account" /></button>
      </nav>
    </header>
    <main className={`flex flex-1 flex-col px-5 pb-6 pt-7 ${current === 'P04' ? 'bg-white' : ''}`}>
      {current === 'P01' ? <>
        <DocumentIllustration />
        <h1 className="mt-6 text-[22px] leading-7 font-semibold tracking-[-0.03em]">Analiza un fragmento</h1>
        <p className="mt-2 text-sm leading-5 text-muted">Escoge un fragmento de la página para analizarlo.</p>
        <button type="button" className="primary-button mt-7" onClick={startSelection} disabled={selecting}>{selecting ? 'Preparando selección…' : 'Escoger texto'}</button>
        <p className="mt-3 text-[12px] leading-[18px] text-muted">Elige un fragmento en la página y vuelve al popup.</p>
        {selectionError && <p className="mt-3 text-[12px] leading-[18px] text-[#A3342B]" role="alert">{selectionError}</p>}
        {selection?.text && <button type="button" className="mt-4 w-fit text-[12px] font-semibold text-accent underline underline-offset-4" onClick={() => open('P02')}>Ver texto seleccionado</button>}
        <button type="button" className="mt-7 w-fit text-[12px] font-semibold text-accent underline underline-offset-4" onClick={() => open('P09')}>Métricas de modelos</button>
      </> : <>
        {current !== 'P04' && current !== 'P05' && current !== 'P06' && current !== 'P08' && current !== 'P09' && current !== 'P11' && <button type="button" className="mb-5 flex w-fit items-center gap-1.5 text-sm font-medium text-ink" onClick={back}><span className="size-5"><Icon name="back" /></span>Volver</button>}
        {stack.includes('P07') && <div hidden={current !== 'P07'}><HistoryScreen deletedAnalysis={deletedAnalysis} onOpen={(id) => { historyScroll.current = popupScroll.current?.scrollTop ?? 0; setHistoryDetail(null); setSelectedAnalysisId(id); open('P08'); }} onChooseText={() => setStack(['P01'])} /></div>}
        {stack.includes('P08') && selectedAnalysisId && <div hidden={current !== 'P08'}><HistoryDetailScreen key={selectedAnalysisId} id={selectedAnalysisId} onBack={back} onLoaded={setHistoryDetail} onDeletingChange={setDetailDeleting} onBreakdown={(item) => { setHistoryDetail(item); open('P06'); }} onDeleted={(id) => { setDeletedAnalysis({ id }); setHistoryDetail(null); setSelectedAnalysisId(null); back(); }} /></div>}
        {current === 'P02' && selection ? <SelectionScreen selection={selection} error={analysisError || selectionError} selecting={selecting} submitting={submitting} onAnalyze={analyze} onReselect={startSelection} />
          : current === 'P04' ? <AnalysisScreen operation={operation} onHistory={() => open('P07')} onBack={() => setStack(['P01', 'P02'])} onRetry={analyze} />
          : current === 'P05' ? <ResultScreen result={operation?.result} onBreakdown={() => open('P06')} onStartOver={startOver} clearing={clearing} error={resultError} />
          : current === 'P06' ? <BreakdownScreen result={stack.at(-2) === 'P08' ? historyDetail : operation?.result} onBack={back} />
          : current === 'P07' ? null
          : current === 'P08' ? null
          : current === 'P09' ? <MetricsScreen onBack={back} />
          : current === 'P11' ? <AccountScreen onBack={back} onLogin={() => open('P13')} onRegister={() => open('P12')} onSigningOutChange={setAccountSigningOut} onSignedOut={() => { setOperation(null); setSelection(null); setHistoryDetail(null); setSelectedAnalysisId(null); setStack(['P01', 'P11']); }} />
          : current === 'P12' ? <RegisterScreen onLogin={() => open('P13')} />
          : current === 'P13' ? <LoginScreen onRegister={() => open('P12')} />
          : <><h1 className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">{titles[current]}</h1><p className="mt-4 text-sm text-muted">Sección en preparación.</p></>}
      </>}
    </main>
    {current === 'P01' && <ServiceStatus health={health} onRetry={refreshHealth} />}
  </div>;
}
