// Mínimo de tokens que exige la API (MIN_INPUT_TOKENS en backend/services/analysis.py).
export const MIN_WORDS = 100;
// Esos 100 tokens son del BiLSTM (\b\w+\b), es decir, palabras.
// Máximo útil: el BiLSTM lee 192 palabras y BETO 256 subpalabras (max_tokens en los contratos de
// datasets/*_produccion/modelo/contrato.json). Medido con el tokenizador de BETO sobre los fragmentos
// de datasets/comun_v1 que recorta: 254 subpalabras útiles ≈ 197 palabras (p10–p90: 181–209).
// Lo que pase de ~200 palabras no lo lee ningún modelo.
export const MAX_WORDS = 200;
// A partir del 80 % del máximo útil la longitud se considera buena.
export const GOOD_WORDS = 160;

// Estado de longitud compartido por el panel y la barra de la página:
// short (rojo) < 100 ≤ ready (amarillo) < 160 ≤ good (verde) < 200 ≤ full (dorado).
export function lengthLevel(words) {
  if (words < MIN_WORDS) return 'short';
  if (words < GOOD_WORDS) return 'ready';
  return words < MAX_WORDS ? 'good' : 'full';
}

// Equivale a TOKEN_PATTERN = \b\w+\b (Unicode) de bilstm/modelo.py.
const WORD = /[\p{L}\p{N}_]+/gu;

export function countWords(text) {
  return typeof text === 'string' ? (text.match(WORD)?.length ?? 0) : 0;
}

// Hay texto que analizar (no basta con una selección vacía guardada tras vaciarla).
export function hasSelectionText(selection) {
  return typeof selection?.text === 'string' && selection.text.trim() !== '';
}

export function joinFragments(fragments) {
  return fragments.map((fragment) => fragment.text).join('\n\n');
}

// Devuelve los fragmentos de una selección; las selecciones antiguas (solo `text`) cuentan como uno.
export function normalizeFragments(selection) {
  if (Array.isArray(selection?.fragments)) {
    return selection.fragments.filter((fragment) => typeof fragment?.id === 'string' && typeof fragment.text === 'string' && fragment.text.trim());
  }
  return typeof selection?.text === 'string' && selection.text.trim() ? [{ id: 'previo', text: selection.text }] : [];
}

// ── Una selección pertenece a una sola página ──────────────────────────────

// Misma página aunque cambien el ancla o los parámetros (p. ej. #comentarios, ?utm=…).
export function samePage(a, b) {
  try {
    const first = new URL(a);
    const second = new URL(b);
    return first.origin === second.origin && first.pathname === second.pathname;
  } catch { return false; }
}

const flat = (text) => text.replace(/\s+/g, ' ').trim();

// El texto editado conserva la página de origen solo si no añade nada: cada párrafo debe
// estar contenido en lo que se marcó en la página. Recortar o borrar partes sí la conserva.
export function keepsSource(sourceText, edited) {
  if (typeof sourceText !== 'string' || typeof edited !== 'string') return false;
  const source = flat(sourceText);
  const parts = edited.split(/\n\s*\n/).map(flat).filter(Boolean);
  return parts.length > 0 && parts.every((part) => source.includes(part));
}

export function isDuplicate(fragments, text) {
  const wanted = flat(text);
  return fragments.some((fragment) => flat(fragment.text) === wanted);
}

// Página y texto marcados de una selección. Las guardadas antes de esta regla no traen
// `source`: se toma su propia URL y su texto.
export function sourceOf(selection) {
  const source = selection?.source;
  if (source && typeof source === 'object') {
    return { url: typeof source.url === 'string' ? source.url : null, text: typeof source.text === 'string' ? source.text : '' };
  }
  return { url: typeof selection?.url === 'string' ? selection.url : null, text: typeof selection?.text === 'string' ? selection.text : '' };
}

// Los fragmentos caen en bloques <article> distintos de la misma página.
export function hasMixedArticles(fragments) {
  return new Set(fragments.map((fragment) => fragment.article).filter((article) => Number.isInteger(article))).size > 1;
}

export function pageDomain(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return null; }
}
