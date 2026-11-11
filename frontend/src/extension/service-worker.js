import { clearCompletedAnalysis, getAnalysisOperation, startAnalysis } from './analysis.js';
import { deleteHistoryDetail, getHistoryDetail, listHistory } from './history.js';
import { getPublishedMetrics } from './metrics.js';
import { closeAccountSession, getAccountState, loginAccount, registerAccount } from './account.js';
import { countWords, joinFragments, normalizeFragments } from '../shared/selection.js';

const PENDING_SELECTION = 'pendingSelection';
const SELECTION_TARGET = 'selectionTargetTabId';
const restrictLocalStorage = chrome.storage.local.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' });

// Panel lateral por defecto. Si el manifiesto vuelve a declarar `default_popup`, se usa el popup.
const usesPopup = () => Boolean(chrome.runtime.getManifest?.()?.action?.default_popup);
chrome.sidePanel?.setPanelBehavior?.({ openPanelOnActionClick: !usesPopup() })?.catch?.(() => {});

// Si la pestaña en modo selección se recarga, navega o se cierra, su barra desaparece:
// el modo se da por terminado para que el panel no lo muestre activo para siempre.
async function endSelectionForTab(tabId) {
  const target = (await chrome.storage.session.get(SELECTION_TARGET))[SELECTION_TARGET];
  if (target === tabId) await chrome.storage.session.remove(SELECTION_TARGET);
}
chrome.tabs.onRemoved?.addListener((tabId) => { void endSelectionForTab(tabId).catch(() => {}); });
chrome.tabs.onUpdated?.addListener((tabId, change) => {
  if (change.status === 'loading') void endSelectionForTab(tabId).catch(() => {});
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === 'START_SELECTION') {
    startSelection()
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: selectionErrors[error?.message] ?? selectionErrors.unsupported }));
    return true;
  }

  if (message?.type === 'GET_PENDING_SELECTION') {
    chrome.storage.session.get([PENDING_SELECTION, SELECTION_TARGET])
      .then((items) => sendResponse({ ok: true, selection: items[PENDING_SELECTION] ?? null, selecting: items[SELECTION_TARGET] !== undefined }))
      .catch(() => sendResponse({ ok: false, selection: null }));
    return true;
  }

  if (message?.type === 'REMOVE_FRAGMENT') {
    removeFragment(message.id, sender.tab)
      .then((selection) => sendResponse({ ok: selection !== false, selection: selection || null }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }

  if (message?.type === 'STOP_SELECTION') {
    stopSelection(sender.tab)
      .then((stopped) => sendResponse({ ok: stopped }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }

  if (message?.type === 'CLEAR_FRAGMENTS') {
    clearFragments(sender.tab)
      .then((cleared) => sendResponse({ ok: cleared }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }

  if (message?.type === 'START_ANALYSIS' && !sender.tab) {
    startAnalysis()
      .then(sendResponse)
      .catch(() => sendResponse({ ok: false, error: 'No pudimos iniciar el análisis.' }));
    return true;
  }

  if (message?.type === 'GET_ANALYSIS_OPERATION' && !sender.tab) {
    getAnalysisOperation()
      .then((operation) => sendResponse({ ok: true, operation }))
      .catch(() => sendResponse({ ok: false, operation: null }));
    return true;
  }

  if (message?.type === 'CLEAR_COMPLETED_ANALYSIS' && !sender.tab) {
    clearCompletedAnalysis()
      .then((cleared) => sendResponse({ ok: cleared }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }

  if (message?.type === 'LIST_HISTORY' && !sender.tab) {
    listHistory(message.offset)
      .then((page) => sendResponse({ ok: true, page }))
      .catch((error) => sendResponse({ ok: false, error: error?.message ?? 'No pudimos cargar el historial.' }));
    return true;
  }

  if (message?.type === 'GET_HISTORY_DETAIL' && !sender.tab) {
    getHistoryDetail(message.id)
      .then((detail) => sendResponse({ ok: true, ...detail }))
      .catch(() => sendResponse({ ok: false, error: 'No pudimos abrir este análisis.' }));
    return true;
  }

  if (message?.type === 'DELETE_HISTORY_DETAIL' && !sender.tab) {
    deleteHistoryDetail(message.id)
      .then(() => sendResponse({ ok: true, deleted: true }))
      .catch(() => sendResponse({ ok: false, error: 'No pudimos eliminar este análisis.' }));
    return true;
  }

  if (message?.type === 'GET_METRICS' && !sender.tab) {
    getPublishedMetrics(message.model)
      .then((metrics) => sendResponse({ ok: true, metrics }))
      .catch(() => sendResponse({ ok: false, error: 'No pudimos cargar las métricas.' }));
    return true;
  }

  if (message?.type === 'GET_ACCOUNT_STATE' && !sender.tab) {
    getAccountState()
      .then((account) => sendResponse({ ok: true, account }))
      .catch(() => sendResponse({ ok: false, error: 'No pudimos consultar tu cuenta.' }));
    return true;
  }

  if (message?.type === 'REGISTER_ACCOUNT' && !sender.tab) {
    registerAccount(message.email, message.password)
      .then((account) => sendResponse({ ok: true, account }))
      .catch((error) => sendResponse({ ok: false, error: error?.message ?? 'No pudimos crear la cuenta.' }));
    return true;
  }

  if (message?.type === 'LOGIN_ACCOUNT' && !sender.tab) {
    loginAccount(message.email, message.password, message.skipGuestTransfer === true)
      .then((account) => sendResponse({ ok: true, account }))
      .catch((error) => sendResponse({
        ok: false,
        error: error?.message ?? 'No pudimos iniciar sesión.',
        requiresTransferChoice: error?.name === 'GuestRecoveryError',
      }));
    return true;
  }

  if (message?.type === 'CLOSE_ACCOUNT_SESSION' && !sender.tab) {
    closeAccountSession()
      .then((result) => sendResponse({ ok: true, ...result }))
      .catch((error) => sendResponse({ ok: false, error: error?.message ?? 'No pudimos cerrar la sesión.' }));
    return true;
  }

  if (message?.type === 'SELECTION_CAPTURED' && sender.tab?.id) {
    saveSelection(message.text, sender.tab, message.id, pageUrl(sender))
      .then((saved) => sendResponse({ ok: saved }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }
});

const selectionErrors = {
  permission: 'ScanTrue no tiene permiso para leer esta página. Pulsa «Escoger texto» y acepta el permiso.',
  unsupported: 'Esta página no permite seleccionar texto. Prueba en una página de noticias.',
};

async function startSelection() {
  await restrictLocalStorage;
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab?.id) throw new Error('unsupported');
  // Sin permiso de host ni activeTab, Chrome no expone la URL de la pestaña.
  if (tab.url === undefined) throw new Error('permission');
  if (!/^https?:\/\//.test(tab.url)) throw new Error('unsupported');

  const previous = (await chrome.storage.session.get(SELECTION_TARGET))[SELECTION_TARGET];
  if (previous !== undefined && previous !== tab.id) notifyTab(previous, { type: 'SCANTRUE_STOP' });
  await chrome.storage.session.set({ [SELECTION_TARGET]: tab.id });
  try {
    await injectSelectionScript(tab.id);
  } catch {
    // Páginas protegidas (Chrome Web Store, visor de PDF…) rechazan la inyección.
    await chrome.storage.session.remove(SELECTION_TARGET);
    throw new Error('unsupported');
  }
  notifyTab(tab.id, { type: 'SCANTRUE_START' });
  await syncTab(tab.id);
}

function injectSelectionScript(tabId) {
  return chrome.scripting.executeScript({ target: { tabId }, files: ['extension/content-script.js'] });
}

// Los avisos a la página son mejores esfuerzos: la pestaña puede haberse cerrado o recargado.
function notifyTab(tabId, message) {
  try {
    const sent = chrome.tabs.sendMessage?.(tabId, message);
    sent?.catch?.(() => {});
  } catch { /* Sin content script en esa pestaña. */ }
}

async function readSelection() {
  return (await chrome.storage.session.get(PENDING_SELECTION))[PENDING_SELECTION] ?? null;
}

async function syncTab(tabId) {
  if (tabId === undefined) return;
  const fragments = normalizeFragments(await readSelection());
  notifyTab(tabId, { type: 'SCANTRUE_SYNC', count: fragments.length, words: countWords(joinFragments(fragments)) });
}

async function writeFragments(fragments, url, updatedBy) {
  const selection = { fragments, text: joinFragments(fragments), url, capturedAt: Date.now(), updatedBy };
  await chrome.storage.session.set({ [PENDING_SELECTION]: selection });
  const operation = (await chrome.storage.session.get('analysisOperation')).analysisOperation;
  if (operation?.status !== 'working') await chrome.storage.session.remove('analysisOperation');
  return selection;
}

// URL de la página que envió el fragmento. `tab.url` solo existe con permiso sobre la pestaña
// (activeTab se pierde al navegar dentro de ella); `sender.url` de la ventana principal, siempre.
function pageUrl(sender) {
  const candidate = sender?.tab?.url ?? (sender?.frameId === 0 ? sender.url : undefined);
  return typeof candidate === 'string' && /^https?:\/\//.test(candidate) && candidate.length <= 2048 ? candidate : null;
}

// Misma página aunque cambien el ancla o los parámetros (p. ej. #comentarios, ?utm=…).
function samePage(a, b) {
  try {
    const first = new URL(a);
    const second = new URL(b);
    return first.origin === second.origin && first.pathname === second.pathname;
  } catch { return false; }
}

async function addFragment(text, tab, id, url) {
  const previous = await readSelection();
  const fragmentId = typeof id === 'string' && /^[\w-]{1,64}$/.test(id) ? id : crypto.randomUUID();
  const kept = normalizeFragments(previous);
  const fragments = [...kept, { id: fragmentId, text, tabId: tab.id }];
  // Sin fragmentos previos (selección nueva o vaciada), la fuente es esta página. Con fragmentos,
  // se conserva solo si vienen de la misma página; texto pegado o de otra página no tiene fuente única.
  const keepUrl = kept.length === 0 ? url : previous?.url && url && samePage(previous.url, url) ? previous.url : null;
  return writeFragments(fragments, keepUrl, 'page');
}

async function saveSelection(text, tab, id, url = null) {
  if (typeof text !== 'string' || !text.trim()) return false;
  const items = await chrome.storage.session.get(SELECTION_TARGET);
  if (items[SELECTION_TARGET] !== tab.id) return false;
  await addFragment(text, tab, id, url);
  await syncTab(tab.id);
  return true;
}

async function removeFragment(id, senderTab) {
  const selection = await readSelection();
  const fragments = normalizeFragments(selection);
  const fragment = fragments.find((item) => item.id === id);
  if (!fragment) {
    // Ya no existe (p. ej. se vació la selección): se da por quitado y se limpia el resaltado huérfano.
    if (senderTab?.id !== undefined) notifyTab(senderTab.id, { type: 'SCANTRUE_REMOVE', id });
    return selection ?? { fragments: [], text: '', url: null };
  }
  // Desde una página solo se puede quitar un fragmento marcado en esa misma pestaña.
  if (senderTab && fragment.tabId !== senderTab.id) return false;
  const remaining = fragments.filter((item) => item.id !== id);
  const updated = await writeFragments(remaining, remaining.length ? selection.url : null, 'worker');
  if (fragment.tabId !== undefined) {
    notifyTab(fragment.tabId, { type: 'SCANTRUE_REMOVE', id });
    await syncTab(fragment.tabId);
  }
  return updated;
}

async function stopSelection(senderTab) {
  const target = (await chrome.storage.session.get(SELECTION_TARGET))[SELECTION_TARGET];
  if (target === undefined) return true;
  if (senderTab && senderTab.id !== target) return false;
  await chrome.storage.session.remove(SELECTION_TARGET);
  notifyTab(target, { type: 'SCANTRUE_STOP' });
  return true;
}

async function clearFragments(senderTab) {
  const target = (await chrome.storage.session.get(SELECTION_TARGET))[SELECTION_TARGET];
  if (senderTab && senderTab.id !== target) return false;
  const tabs = new Set(normalizeFragments(await readSelection()).map((fragment) => fragment.tabId).filter((tabId) => tabId !== undefined));
  await writeFragments([], null, 'worker');
  for (const tabId of tabs) notifyTab(tabId, { type: 'SCANTRUE_CLEAR' });
  await syncTab(target);
  return true;
}
