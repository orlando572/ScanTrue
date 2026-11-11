// Mínimo de tokens que exige la API (MIN_INPUT_TOKENS en backend/services/analysis.py).
export const MIN_WORDS = 100;
// Esos 100 tokens son del BiLSTM (\b\w+\b), es decir, palabras.
// Máximo útil: mBERT lee 512 subpalabras (max_length en backend/models/mbert.py). Medido con su
// tokenizador sobre 2878 fragmentos de datasets/comun_v1: 1 palabra ≈ 1,44 subpalabras, así que
// 510 subpalabras útiles ≈ 354 palabras (p10–p90: 328–380). Lo que pase de ahí se recorta.
export const MAX_WORDS = 350;
// A partir del 80 % del máximo útil la longitud se considera buena.
export const GOOD_WORDS = 280;

// Estado de longitud compartido por el panel y la barra de la página:
// short (rojo) < 100 ≤ ready (amarillo) < 280 ≤ good (verde) < 350 ≤ full (dorado).
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
