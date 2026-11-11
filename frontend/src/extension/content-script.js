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
    style.textContent = `::highlight(${HIGHLIGHT}) { background-color: rgba(56, 225, 255, .32); color: inherit; text-decoration: underline 2px rgb(8, 160, 190); }`;
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
    if (!inField) mark(id);
    window.getSelection()?.removeAllRanges();
    send({ type: 'SELECTION_CAPTURED', text, id }, (response) => {
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
      'z-index:2147483647', 'padding:6px 10px', 'border:1px solid #ff4a3d', 'background:#0a1220', 'color:#ff4a3d',
      'font:12px/1.2 "Share Tech Mono",ui-monospace,monospace', 'letter-spacing:.1em', 'text-transform:uppercase', 'cursor:pointer',
      'box-shadow:0 0 12px rgba(255,74,61,.45)',
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
      .bar { display: flex; align-items: center; gap: 10px; padding: 7px 8px 7px 12px; border: 1px solid #38e1ff;
        background: rgba(5, 8, 15, .94); color: #e6f4ff; font: 12px/1.3 "Share Tech Mono", ui-monospace, "Courier New", monospace;
        letter-spacing: .06em; white-space: nowrap; box-shadow: 0 0 14px rgba(56, 225, 255, .3), inset 0 0 10px rgba(56, 225, 255, .1);
        clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px); }
      .led { flex: none; width: 7px; height: 7px; background: #ffb21e; box-shadow: 0 0 6px #ffb21e; animation: blink 1s steps(1, end) infinite; }
      .label { color: #ffb21e; text-transform: uppercase; letter-spacing: .14em; }
      .meta, .hint { color: #8fa8c4; }
      .meta b { font-weight: 400; color: #ffb21e; } .meta b.count { color: #e6f4ff; }
      .meta b { color: #ff4a3d; } .meta b.ready { color: #f5e14a; } .meta b.good { color: #3dff9a; } .meta b.full { color: #e2b13c; }
      [hidden] { display: none !important; }
      button { padding: 5px 9px; border: 1px solid #3a5878; background: #0f1b2e; color: #e6f4ff; font: inherit;
        letter-spacing: .1em; text-transform: uppercase; cursor: pointer; }
      button:hover { border-color: #38e1ff; }
      button.primary { border-color: #38e1ff; background: #38e1ff; color: #031018; }
      button:focus-visible { outline: 2px solid #ffe45c; outline-offset: 2px; }
      @keyframes blink { 50% { opacity: .25; } }
      @media (prefers-reduced-motion: reduce) { .led { animation: none; } }
    </style>
    <div class="bar" role="region" aria-label="ScanTrue: modo selección" title="Clic en un resaltado para quitarlo">
      <span class="led" aria-hidden="true"></span>
      <span class="label">Seleccionando</span>
      <span class="hint" data-hint>· Marca texto en la página para añadirlo</span>
      <span class="meta" data-meta aria-live="polite" hidden>· <b class="count" data-count>0</b> <span data-noun>fragmentos</span> · <b data-words>0</b> palabras</span>
      <button type="button" data-clear title="Quitar todos los fragmentos">Vaciar</button>
      <button type="button" class="primary" data-stop title="Terminar la selección">Terminar</button>
    </div>`;
    root.querySelector('[data-stop]').addEventListener('click', () => { send({ type: 'STOP_SELECTION' }); stop(); });
    root.querySelector('[data-clear]').addEventListener('click', () => send({ type: 'CLEAR_FRAGMENTS' }));
    document.documentElement.append(host);
    bar = {
      host, count: root.querySelector('[data-count]'), words: root.querySelector('[data-words]'),
      noun: root.querySelector('[data-noun]'), hint: root.querySelector('[data-hint]'), meta: root.querySelector('[data-meta]'),
      clear: root.querySelector('[data-clear]'),
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
      case 'SCANTRUE_REMOVE': unmark(message.id); break;
      case 'SCANTRUE_CLEAR': for (const id of [...ranges.keys()]) unmark(id); break;
      default: break;
    }
  });

  return { start, stop };
}
