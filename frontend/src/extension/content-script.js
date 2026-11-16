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
  let toast = null;
  let toastTimer;
  // Dónde terminó la última selección: ahí aparece el cartel de aviso.
  let lastPoint = null;

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

  // Punto donde acaba la selección: el del ratón o, con teclado, el final del texto marcado.
  function selectionPoint(event) {
    if (event.type === 'mouseup') return { x: event.clientX, y: event.clientY };
    const selection = window.getSelection();
    const box = selection?.rangeCount ? selection.getRangeAt(0).getBoundingClientRect() : null;
    return box && (box.width || box.height) ? { x: box.right, y: box.bottom } : null;
  }

  // Posición del <article> que contiene la selección, para avisar si se marcan notas distintas
  // de una misma página (portadas, directos). `null` si la página no usa <article>.
  function articleIndex() {
    const node = window.getSelection()?.anchorNode;
    const element = node instanceof Element ? node : node?.parentElement;
    const article = element?.closest?.('article');
    return article ? [...document.querySelectorAll('article')].indexOf(article) : null;
  }

  function closeToast() {
    clearTimeout(toastTimer);
    toast?.remove();
    toast = null;
  }

  // Cartel momentáneo junto al texto marcado (fragmento rechazado o aviso de notas distintas);
  // la barra parpadea a la vez con el mismo color. `error` en rojo, `warn` en ámbar.
  function notice({ level, title, text }) {
    if (!bar || typeof text !== 'string') return;
    closeToast();
    const color = level === 'warn' ? '#ffb21e' : '#ff4a3d';
    const width = Math.min(300, window.innerWidth - 16);
    const point = lastPoint ?? { x: window.innerWidth / 2 - width / 2, y: window.innerHeight - 190 };
    toast = document.createElement('div');
    toast.style.position = 'fixed';
    toast.style.left = `${Math.max(8, Math.min(point.x + 10, window.innerWidth - width - 8))}px`;
    toast.style.top = `${point.y + 14 > window.innerHeight - 150 ? Math.max(8, point.y - 96) : point.y + 14}px`;
    toast.style.zIndex = '2147483647';
    toast.style.width = `${width}px`;
    const root = toast.attachShadow({ mode: 'closed' });
    root.innerHTML = `<style>
      :host { all: initial; }
      .toast { box-sizing: border-box; padding: 10px 14px 12px; border: 2px solid ${color}; background: #000; color: #f2f2f5;
        font: 14px/1.4 "IBM Plex Sans", system-ui, sans-serif; box-shadow: 0 0 22px ${color}66, 0 8px 24px rgba(0, 0, 0, .6);
        clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px));
        animation: pop .5s steps(1, end) both; }
      b { display: block; margin-bottom: 3px; color: ${color}; font: 13px/1.3 "Share Tech Mono", ui-monospace, "Courier New", monospace;
        letter-spacing: .16em; text-transform: uppercase; }
      @keyframes pop { 0% { opacity: 0; } 20% { opacity: 1; } 40% { opacity: .3; } 60%, 100% { opacity: 1; } }
      @media (prefers-reduced-motion: reduce) { .toast { animation: none; } }
    </style><div class="toast" role="alert"><b></b><span></span></div>`;
    root.querySelector('b').textContent = `${level === 'warn' ? '▲' : '✕'} ${title ?? 'Aviso'}`;
    root.querySelector('span').textContent = text;
    document.documentElement.append(toast);
    toastTimer = setTimeout(closeToast, 5000);
    // La barra parpadea tres veces con el color del aviso.
    bar.frame.style.setProperty('--flash', color);
    bar.frame.classList.remove('flash');
    void bar.frame.offsetWidth;
    bar.frame.classList.add('flash');
  }

  function isInsideUi(event) {
    return event.composedPath().some((node) => node === bar?.host || node === removeMenu || node === toast);
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
    closeToast();
    lastPoint = selectionPoint(event);
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
      .bar.flash { animation: flash .9s steps(1, end) both; }
      @keyframes flash { 0%, 33%, 66% { border-color: var(--flash); box-shadow: 0 0 18px var(--flash); } 16%, 50%, 83%, 100% { border-color: #9b7cff; box-shadow: none; } }
      .meta b { font-weight: 400; } .meta b.count { color: #f2f2f5; }
      .meta b { color: #ff4a3d; } .meta b.ready { color: #f5e14a; } .meta b.good { color: #3dff9a; } .meta b.full { color: #e2b13c; }
      [hidden] { display: none !important; }
      button { padding: 5px 9px; border: 1px solid #3a3a46; background: #131318; color: #f2f2f5; font: inherit;
        letter-spacing: .1em; text-transform: uppercase; cursor: pointer; }
      button:hover { border-color: #9b7cff; }
      button.primary { border-color: #9b7cff; background: #9b7cff; color: #000; }
      button:focus-visible { outline: 2px solid #e6ff4d; outline-offset: 2px; }
      @keyframes blink { 50% { opacity: .25; } }
      @media (prefers-reduced-motion: reduce) { .led, .bar.flash { animation: none; } .bar.flash { border-color: var(--flash); } }
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
      clear: root.querySelector('[data-clear]'), frame: root.querySelector('.bar'),
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
    closeToast();
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
      case 'SCANTRUE_NOTICE': notice(message); break;
      case 'SCANTRUE_REMOVE': unmark(message.id); break;
      case 'SCANTRUE_CLEAR': for (const id of [...ranges.keys()]) unmark(id); break;
      default: break;
    }
  });

  return { start, stop };
}
