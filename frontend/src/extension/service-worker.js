import { clearCompletedAnalysis, getAnalysisOperation, startAnalysis } from './analysis.js';
import { deleteHistoryDetail, getHistoryDetail, listHistory } from './history.js';
import { getPublishedMetrics } from './metrics.js';
import { closeAccountSession, getAccountState, loginAccount, registerAccount } from './account.js';

const PENDING_SELECTION = 'pendingSelection';
const SELECTION_TARGET = 'selectionTargetTabId';
const restrictLocalStorage = chrome.storage.local.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' });

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === 'START_SELECTION') {
    startSelection()
      .then(() => sendResponse({ ok: true }))
      .catch(() => sendResponse({ ok: false, error: 'No se puede seleccionar texto en esta pestaña. Prueba en una página web.' }));
    return true;
  }

  if (message?.type === 'GET_PENDING_SELECTION') {
    chrome.storage.session.get(PENDING_SELECTION)
      .then((items) => sendResponse({ ok: true, selection: items[PENDING_SELECTION] ?? null }))
      .catch(() => sendResponse({ ok: false, selection: null }));
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
    getPublishedMetrics()
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
    saveSelection(message.text, sender.tab)
      .then((saved) => sendResponse({ ok: saved }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }
});

async function startSelection() {
  await restrictLocalStorage;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !/^https?:\/\//.test(tab.url ?? '')) throw new Error('Unsupported tab');

  await chrome.storage.session.set({ [SELECTION_TARGET]: tab.id });
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ['extension/content-script.js'],
    });
  } catch (error) {
    await chrome.storage.session.remove(SELECTION_TARGET);
    throw error;
  }
}

async function saveSelection(text, tab) {
  if (typeof text !== 'string' || !text.trim()) return false;
  const items = await chrome.storage.session.get(SELECTION_TARGET);
  if (items[SELECTION_TARGET] !== tab.id) return false;

  const url = /^https?:\/\//.test(tab.url ?? '') && tab.url.length <= 2048 ? tab.url : null;
  await chrome.storage.session.set({
    [PENDING_SELECTION]: { text, url, capturedAt: Date.now() },
  });
  const operation = (await chrome.storage.session.get('analysisOperation')).analysisOperation;
  if (operation?.status !== 'working') await chrome.storage.session.remove('analysisOperation');
  await chrome.storage.session.remove(SELECTION_TARGET);
  return true;
}
