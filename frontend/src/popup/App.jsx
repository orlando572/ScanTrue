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
import scanTrueMark from './assets/scantrue-mark.svg';

const titles = { P01: 'Inicio', P02: 'Texto para analizar', P04: 'Analizando texto', P05: 'Resultado del análisis', P06: 'Desglose por modelo', P07: 'Historial de análisis', P08: 'Análisis anterior', P09: 'Pruebas del modelo', P11: 'Cuenta', P12: 'Crear cuenta', P13: 'Iniciar sesión' };

function Icon({ name }) {
  const paths = {
    history: <><path d="M3 12a9 9 0 1 0 2.6-6.4M3 4v4h4" /><path d="M12 7v5l3 2" /></>,
    metrics: <><path d="M3 20h18" /><path d="M5 17v-5h3v5M10.5 17V5h3v12M16 17V9h3v8" /></>,
    account: <><circle cx="12" cy="8" r="3.5" /><path d="M5 21a7 7 0 0 1 14 0" /></>,
    back: <path d="m14 5-7 7 7 7" />,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function Brand({ onHome, disabled }) {
  return <button type="button" className="flex items-center gap-2.5 rounded-[10px] text-left text-ink hover:bg-accent-soft disabled:cursor-wait disabled:opacity-60" aria-label="ScanTrue, ir al inicio" title="Ir al inicio" onClick={onHome} disabled={disabled}>
    <img src={scanTrueMark} alt="" className="size-9" />
    <span className="text-[18px] font-semibold tracking-[-0.03em]">Scan<span className="text-accent">True</span></span>
  </button>;
}

function DocumentIllustration() {
  return <div className="document-art" aria-hidden="true">
    <svg viewBox="0 0 112 128" fill="none" className="h-[92px] w-[81px]">
      <path d="M16 2h55l25 25v96a3 3 0 0 1-3 3H16a3 3 0 0 1-3-3V5a3 3 0 0 1 3-3Z" fill="#F8FBFB" stroke="#A9BEC5" strokeWidth="2.5" />
      <path d="M71 2v22a3 3 0 0 0 3 3h22" fill="#E3EBEE" stroke="#A9BEC5" strokeWidth="2.5" strokeLinejoin="round" />
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
  return <footer className="border-t border-line bg-white px-5 py-1.5" role="status" aria-live="polite">
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

function validationMessage(operation) {
  if (/(?:al menos|mínim[oa]).{0,40}token/i.test(`${operation?.message ?? ''} ${operation?.correction ?? ''}`)) {
    return 'El texto es muy corto. Añade más contenido.';
  }
  return [operation?.message, operation?.correction].filter(Boolean).join(' ');
}

function SelectionScreen({ selection, error, selecting, submitting, onAnalyze, onAddText, onEdit, onBack }) {
  const domain = selectionDomain(selection.url);
  return <>
    <div className="flex items-start gap-3">
      <button type="button" className="breakdown-back" aria-label="Volver" title="Volver" onClick={onBack}><Icon name="back" /></button>
      <h1 className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Texto para analizar</h1>
    </div>
    {domain && <p className="mt-3 text-[12px] text-muted">Origen: {domain}</p>}
    <textarea className="selection-preview mt-5 h-[160px] w-full resize-none overflow-y-auto text-sm leading-5" aria-label="Texto para analizar" placeholder="Escribe o pega texto aquí" value={selection.text} onChange={(event) => onEdit(event.target.value)} disabled={submitting || selecting} />
    {error && <p className="mt-3 text-[12px] leading-[18px] text-[#A3342B]" role="alert">{error}</p>}
    <button type="button" className="primary-button mt-5" onClick={onAnalyze} disabled={submitting || selecting || !selection.text.trim()}>{submitting ? 'Iniciando análisis…' : 'Analizar'}</button>
    <button type="button" className="secondary-button mt-3" onClick={onAddText} disabled={submitting || selecting}>{selecting ? 'Preparando selección…' : 'Seleccionar nuevo texto'}</button>
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
        <path d="M31 89h29" stroke="#C8D9DE" strokeWidth="5" strokeLinecap="round" />
        <path className="analysis-scan" d="M31 39h49" stroke="#087D77" strokeWidth="4" strokeLinecap="round" />
      </svg>
      <svg className="analysis-indicator" viewBox="0 0 48 48" fill="none" focusable="false">
        <circle className="analysis-indicator-track" cx="24" cy="24" r="18" />
        <circle className="analysis-indicator-arc" cx="24" cy="24" r="18" strokeDasharray="58 120" />
      </svg>
    </div>
    <h1 className="mt-7 text-[22px] leading-7 font-semibold">Analizando texto</h1>
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
  const [accountNotice, setAccountNotice] = useState('');
  const analysisLock = useRef(false);
  const draftWrite = useRef(Promise.resolve());
  const draftVersion = useRef(0);
  const selectionRef = useRef(null);
  const popupScroll = useRef(null);
  const historyScroll = useRef(null);
  const current = stack.at(-1);
  selectionRef.current = selection;

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
      const foundSelection = pending?.ok && typeof pending.selection?.text === 'string' ? pending.selection : null;
      const foundOperation = active?.ok ? active.operation : null;
      if (foundSelection) setSelection(foundSelection);
      if (foundOperation) setOperation(foundOperation);
      if (foundOperation?.status === 'completed') setStack(['P01', 'P05']);
      else if (['working', 'error', 'uncertain', 'session_error', 'service_error', 'storage_error'].includes(foundOperation?.status)) setStack(['P01', 'P02', 'P04']);
      else if (foundSelection) {
        setStack(['P01', 'P02']);
        if (foundOperation?.status === 'validation') setAnalysisError(validationMessage(foundOperation));
      }
    }).catch(() => {});

    if (typeof chrome === 'undefined' || !chrome.storage?.onChanged) return;
    const handleChange = (changes, area) => {
      if (area !== 'session') return;
      if (changes.pendingSelection?.newValue && changes.pendingSelection.newValue.updatedBy !== 'popup') {
        setSelection(changes.pendingSelection.newValue);
        setStack(['P01', 'P02']);
      }
      const next = changes.analysisOperation?.newValue;
      if (!next) return;
      setOperation(next);
      if (next.status === 'completed') setStack(['P01', 'P05']);
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
          if (response.operation.status === 'completed') setStack(['P01', 'P05']);
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
    const draft = { ...selectionRef.current, text, url: null, capturedAt: Date.now(), updatedBy: 'popup' };
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
      if (current === 'P02' && selection) await persistSelection();
      const response = await sendExtensionMessage({ type: 'START_SELECTION' });
      if (!response?.ok) { setSelectionError(response?.error ?? 'No se puede seleccionar texto en esta pestaña.'); return; }
      window.close();
    } catch (error) { setSelectionError(error?.message ?? 'No se puede seleccionar texto en esta pestaña. Prueba en una página web.'); }
    finally { setSelecting(false); }
  };

  const analyze = async () => {
    if (analysisLock.current || !selection?.text?.trim()) return;
    analysisLock.current = true;
    setSubmitting(true);
    setAnalysisError('');
    try {
      await persistSelection();
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
      setOperation(null);
      setSelection(null);
      setStack(['P01']);
    } catch { setResultError('No pudimos preparar una nueva selección. Inténtalo de nuevo.'); }
    finally { setClearing(false); }
  };

  const accountCompleted = (account) => {
    if (account.kind === 'pending_confirmation') {
      setAccountNotice('Te enviamos un correo de confirmación. Confirma tu cuenta y después inicia sesión aquí. Tu sesión invitada y su historial siguen disponibles.');
    } else {
      const count = Number.isInteger(account.transferred) ? account.transferred : 0;
      setAccountNotice(account.guestHistorySkipped
        ? 'Sesión iniciada sin incorporar el historial invitado.'
        : count > 0
          ? `Sesión iniciada. Se incorporaron ${count} análisis de tu historial invitado.`
          : 'Sesión iniciada.');
      setOperation(null);
      setSelection(null);
      setHistoryDetail(null);
      setSelectedAnalysisId(null);
    }
    setStack(['P01', 'P11']);
  };

  return <div ref={popupScroll} className={`popup-shell flex flex-col bg-canvas text-ink ${current === 'P01' ? '' : 'min-h-[500px]'}`}>
    <header className="flex items-center justify-between border-b border-line bg-white px-5 py-4">
      <Brand onHome={() => setStack(['P01'])} disabled={detailDeleting || accountSigningOut} />
      <nav aria-label="Navegación principal" className="flex items-center gap-1">
        <button type="button" className="icon-button" aria-label="Historial" title="Historial" onClick={() => open('P07')} disabled={detailDeleting || accountSigningOut}><Icon name="history" /></button>
        <button type="button" className="icon-button" aria-label="Pruebas del modelo" title="Pruebas del modelo" onClick={() => open('P09')} disabled={detailDeleting || accountSigningOut}><Icon name="metrics" /></button>
        <button type="button" className="icon-button" aria-label="Cuenta" title="Cuenta" onClick={() => open('P11')} disabled={detailDeleting || accountSigningOut}><Icon name="account" /></button>
      </nav>
    </header>
    <main className={`flex flex-col px-5 ${current === 'P01' ? 'pb-3 pt-11' : 'flex-1 pb-6 pt-7'} ${current === 'P04' ? 'bg-white' : ''}`}>
      {current === 'P01' ? <>
        <DocumentIllustration />
        <h1 className="mt-10 text-[22px] leading-7 font-semibold tracking-[-0.03em]">Analiza un fragmento</h1>
        <p className="mt-2 text-sm leading-5 text-muted">Escoge un fragmento de la página para analizarlo.</p>
        <button type="button" className="primary-button mt-7" onClick={startSelection} disabled={selecting}>{selecting ? 'Preparando selección…' : 'Escoger texto'}</button>
        {selectionError && <p className="mt-3 text-[12px] leading-[18px] text-[#A3342B]" role="alert">{selectionError}</p>}
        {selection && <button type="button" className="mt-4 w-fit text-[12px] font-semibold text-accent underline underline-offset-4" onClick={() => open('P02')}>Ver texto para analizar</button>}
      </> : <>
        {current !== 'P02' && current !== 'P04' && current !== 'P05' && current !== 'P06' && current !== 'P07' && current !== 'P08' && current !== 'P09' && current !== 'P11' && current !== 'P12' && current !== 'P13' && <button type="button" className="mb-5 flex w-fit items-center gap-1.5 text-sm font-medium text-ink" onClick={back}><span className="size-5"><Icon name="back" /></span>Volver</button>}
        {stack.includes('P07') && <div hidden={current !== 'P07'}><HistoryScreen deletedAnalysis={deletedAnalysis} onBack={back} onOpen={(id) => { historyScroll.current = popupScroll.current?.scrollTop ?? 0; setHistoryDetail(null); setSelectedAnalysisId(id); open('P08'); }} onChooseText={() => setStack(['P01'])} /></div>}
        {stack.includes('P08') && selectedAnalysisId && <div hidden={current !== 'P08'}><HistoryDetailScreen key={selectedAnalysisId} id={selectedAnalysisId} onBack={back} onLoaded={setHistoryDetail} onDeletingChange={setDetailDeleting} onBreakdown={(item) => { setHistoryDetail(item); open('P06'); }} onDeleted={(id) => { setDeletedAnalysis({ id }); setHistoryDetail(null); setSelectedAnalysisId(null); back(); }} /></div>}
        {current === 'P02' && selection ? <SelectionScreen selection={selection} error={analysisError || selectionError} selecting={selecting} submitting={submitting} onAnalyze={analyze} onAddText={startSelection} onEdit={editSelection} onBack={back} />
          : current === 'P04' ? <AnalysisScreen operation={operation} onHistory={() => open('P07')} onBack={() => setStack(['P01', 'P02'])} onRetry={analyze} />
          : current === 'P05' ? <ResultScreen result={operation?.result} onBack={back} onBreakdown={() => open('P06')} onStartOver={startOver} clearing={clearing} error={resultError} />
          : current === 'P06' ? <BreakdownScreen result={stack.at(-2) === 'P08' ? historyDetail : operation?.result} onBack={back} />
          : current === 'P07' ? null
          : current === 'P08' ? null
          : current === 'P09' ? <MetricsScreen onBack={back} />
          : current === 'P11' ? <AccountScreen notice={accountNotice} onBack={back} onLogin={() => { setAccountNotice(''); open('P13'); }} onRegister={() => { setAccountNotice(''); open('P12'); }} onSigningOutChange={setAccountSigningOut} onSignedOut={() => { setAccountNotice(''); setOperation(null); setSelection(null); setHistoryDetail(null); setSelectedAnalysisId(null); setStack(['P01', 'P11']); }} />
          : current === 'P12' ? <RegisterScreen onBack={back} onLogin={() => open('P13')} onComplete={accountCompleted} />
          : current === 'P13' ? <LoginScreen onBack={back} onRegister={() => open('P12')} onComplete={accountCompleted} />
          : <><h1 className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">{titles[current]}</h1><p className="mt-4 text-sm text-muted">Sección en preparación.</p></>}
      </>}
    </main>
    {current === 'P01' && <ServiceStatus health={health} onRetry={refreshHealth} />}
  </div>;
}
