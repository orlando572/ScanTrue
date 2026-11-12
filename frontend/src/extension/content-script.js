import { lengthLevel } from '../shared/selection.js';

// Se inyecta solo cuando el usuario pulsa «Escoger texto» o usa el atajo de ScanTrue.
// Resalta los fragmentos con la CSS Custom Highlight API (no modifica el HTML de la página)
// y muestra una barra propia dentro de un Shadow DOM para no heredar estilos de la página.
globalThis.__scanTrueSelectionController ??= createSelectionController();

function createSelectionController() {
  const HIGHLIGHT = 'scantrue-fragment';
  const ranges = new Map();
  const highlight = typeof Highlight === 'function' ? new Highlight() : null;
  let active = false;
  let bar = null;
  let removeMenu = null;

  if (highlight && globalThis.CSS?.highlights) CSS.highlights.set(HIGHLIGHT, highlight);
  if (!document.getElementById('scantrue-highlight-style')) {
    const style = document.createElement('style');
    style.id = 'scantrue-highlight-style';
    style.textContent = `::highlight(${HIGHLIGHT}) { background-color: rgba(155, 124, 255, .34); color: inherit; text-decoration: underline 2px rgb(124, 92, 235); }`;
    (document.head ?? document.documentElement).append(style);
  }

  function send(message, callback = () => {}) {
    try {
      chrome.runtime.sendMessage(message, (response) => {
        void chrome.runtime.lastError;
        callback(response);
      });
    } catch { /* La extensión se recargó: este script ya no puede comunicarse. */ }
  }

  function selectedText() {
    const element = document.activeElement;
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      if (element instanceof HTMLInputElement && element.type === 'password') return { text: '', inField: true };
      const { selectionStart, selectionEnd, value } = element;
      if (selectionStart !== null && selectionEnd > selectionStart) {
        return { text: value.slice(selectionStart, selectionEnd), inField: true };
      }
    }
    return { text: window.getSelection()?.toString() ?? '', inField: false };
  }

  function mark(id) {
    const selection = window.getSelection();
    if (!highlight || !selection?.rangeCount) return;
    const range = selection.getRangeAt(0).cloneRange();
    if (range.collapsed) return;
    ranges.set(id, range);
    highlight.add(range);
  }

  function unmark(id) {
    const range = ranges.get(id);
    if (!range) return;
    highlight?.delete(range);
    ranges.delete(id);
  }

  // Posición del <article> que contiene la selección, para avisar si se marcan notas distintas
  // de una misma página (portadas, directos). `null` si la página no usa <article>.
  function articleIndex() {
    const node = window.getSelection()?.anchorNode;
    const element = node instanceof Element ? node : node?.parentElement;
    const article = element?.closest?.('article');
    return article ? [...document.querySelectorAll('article')].indexOf(article) : null;
  }

  // Aviso breve en la barra (fragmento rechazado, notas distintas).
  let noticeTimer;
  function notice(text) {
    if (!bar || typeof text !== 'string') return;
    bar.notice.textContent = `▲ ${text}`;
    bar.notice.hidden = false;
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => { if (bar) bar.notice.hidden = true; }, 3500);
  }

  function isInsideUi(event) {
    return event.composedPath().some((node) => node === bar?.host || node === removeMenu);
  }

  function fragmentAt(x, y) {
    const position = document.caretPositionFromPoint?.(x, y);
    const fallback = position ? null : document.caretRangeFromPoint?.(x, y);
    const node = position?.offsetNode ?? fallback?.startContainer;
    const offset = position?.offset ?? fallback?.startOffset;
    if (!node) return null;
    for (const [id, range] of ranges) {
      try { if (range.isPointInRange(node, offset)) return id; } catch { /* Nodo fuera del documento. */ }
    }
    return null;
  }

  function capture(event) {
    if (!active || isInsideUi(event)) return;
    if (event.type === 'keyup' && event.key !== 'Shift') return;
    const { text, inField } = selectedText();
    if (!text.trim()) {
      if (event.type === 'mouseup') offerRemoval(event);
      return;
    }
    closeRemoveMenu();
    const id = crypto.randomUUID();
    const article = inField ? null : articleIndex();
    if (!inField) mark(id);
    window.getSelection()?.removeAllRanges();
    send({ type: 'SELECTION_CAPTURED', text, id, article }, (response) => {
      if (!response?.ok) unmark(id);
    });
  }

  // Un clic sobre un fragmento ya marcado ofrece quitarlo.
  function offerRemoval(event) {
    closeRemoveMenu();
    const id = fragmentAt(event.clientX, event.clientY);
    if (!id || !bar) return;
    removeMenu = document.createElement('button');
    removeMenu.type = 'button';
    removeMenu.textContent = '✕ Quitar fragmento';
    removeMenu.setAttribute('style', [
      'position:fixed', `left:${Math.min(event.clientX + 8, window.innerWidth - 180)}px`, `top:${Math.max(event.clientY - 40, 8)}px`,
      'z-index:2147483647', 'padding:6px 10px', 'border:1px solid #ff4a3d', 'background:#0a0a0c', 'color:#ff4a3d',
      'font:12px/1.2 "Share Tech Mono",ui-monospace,monospace', 'letter-spacing:.1em', 'text-transform:uppercase', 'cursor:pointer',
    ].join(';'));
    removeMenu.addEventListener('click', () => {
      send({ type: 'REMOVE_FRAGMENT', id }, (response) => { if (response?.ok) unmark(id); });
      closeRemoveMenu();
    });
    document.documentElement.append(removeMenu);
  }

  function closeRemoveMenu() {
    removeMenu?.remove();
    removeMenu = null;
  }

  function showBar() {
    if (bar) return;
    const host = document.createElement('div');
    host.style.position = 'fixed';
    host.style.left = '50%';
    host.style.bottom = '16px';
    host.style.transform = 'translateX(-50%)';
    host.style.zIndex = '2147483647';
    host.style.width = 'max-content';
    host.style.maxWidth = 'calc(100vw - 32px)';
    const root = host.attachShadow({ mode: 'closed' });
    root.innerHTML = `<style>
      :host { all: initial; }
      .bar { display: flex; align-items: center; gap: 10px; padding: 7px 8px 7px 12px; border: 1px solid #9b7cff;
        background: rgba(0, 0, 0, .94); color: #f2f2f5; font: 12px/1.3 "Share Tech Mono", ui-monospace, "Courier New", monospace;
        letter-spacing: .06em; white-space: nowrap;
        clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px)); }
      .led { flex: none; width: 7px; height: 7px; background: #e6ff4d; box-shadow: 0 0 6px #e6ff4d; animation: blink 1s steps(1, end) infinite; }
      .label { color: #e6ff4d; text-transform: uppercase; letter-spacing: .14em; }
      .meta, .hint { color: #9a9aa8; }
      .notice { color: #ffb21e; }
      .meta b { font-weight: 400; } .meta b.count { color: #f2f2f5; }
      .meta b { color: #ff4a3d; } .meta b.ready { color: #f5e14a; } .meta b.good { color: #3dff9a; } .meta b.full { color: #e2b13c; }
      [hidden] { display: none !important; }
      button { padding: 5px 9px; border: 1px solid #3a3a46; background: #131318; color: #f2f2f5; font: inherit;
        letter-spacing: .1em; text-transform: uppercase; cursor: pointer; }
      button:hover { border-color: #9b7cff; }
      button.primary { border-color: #9b7cff; background: #9b7cff; color: #000; }
      button:focus-visible { outline: 2px solid #e6ff4d; outline-offset: 2px; }
      @keyframes blink { 50% { opacity: .25; } }
      @media (prefers-reduced-motion: reduce) { .led { animation: none; } }
    </style>
    <div class="bar" role="region" aria-label="ScanTrue: modo selección" title="Clic en un resaltado para quitarlo">
      <span class="led" aria-hidden="true"></span>
      <span class="label">Seleccionando</span>
      <span class="hint" data-hint>· Marca texto en la página para añadirlo</span>
      <span class="meta" data-meta aria-live="polite" hidden>· <b class="count" data-count>0</b> <span data-noun>fragmentos</span> · <b data-words>0</b> palabras</span>
      <span class="notice" data-notice role="status" hidden></span>
      <button type="button" data-clear title="Quitar todos los fragmentos">Vaciar</button>
      <button type="button" class="primary" data-stop title="Terminar la selección">Terminar</button>
    </div>`;
    root.querySelector('[data-stop]').addEventListener('click', () => { send({ type: 'STOP_SELECTION' }); stop(); });
    root.querySelector('[data-clear]').addEventListener('click', () => send({ type: 'CLEAR_FRAGMENTS' }));
    document.documentElement.append(host);
    bar = {
      host, count: root.querySelector('[data-count]'), words: root.querySelector('[data-words]'),
      noun: root.querySelector('[data-noun]'), hint: root.querySelector('[data-hint]'), meta: root.querySelector('[data-meta]'),
      clear: root.querySelector('[data-clear]'), notice: root.querySelector('[data-notice]'),
    };
    update(0, 0);
  }

  // Sin fragmentos se muestra la pista; desde el primero, solo los contadores.
  function update(count = 0, words = 0) {
    if (!bar) return;
    const empty = !count;
    bar.hint.hidden = !empty;
    bar.meta.hidden = empty;
    bar.clear.hidden = empty;
    bar.count.textContent = String(count);
    bar.noun.textContent = count === 1 ? 'fragmento' : 'fragmentos';
    bar.words.textContent = String(words);
    bar.words.className = lengthLevel(words);
  }

  function start() {
    if (active) return;
    active = true;
    window.getSelection()?.removeAllRanges();
    showBar();
    document.addEventListener('mouseup', capture, true);
    document.addEventListener('keyup', capture, true);
  }

  // Termina el modo; los resaltados quedan visibles hasta recargar la página.
  function stop() {
    active = false;
    closeRemoveMenu();
    clearTimeout(noticeTimer);
    document.removeEventListener('mouseup', capture, true);
    document.removeEventListener('keyup', capture, true);
    bar?.host.remove();
    bar = null;
  }

  chrome.runtime.onMessage.addListener((message) => {
    switch (message?.type) {
      case 'SCANTRUE_START': start(); break;
      case 'SCANTRUE_STOP': stop(); break;
      case 'SCANTRUE_SYNC': update(message.count, message.words); break;
      case 'SCANTRUE_NOTICE': notice(message.text); break;
      case 'SCANTRUE_REMOVE': unmark(message.id); break;
      case 'SCANTRUE_CLEAR': for (const id of [...ranges.keys()]) unmark(id); break;
      default: break;
    }
  });

  return { start, stop };
}
