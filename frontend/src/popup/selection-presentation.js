import { MAX_WORDS, MIN_WORDS, countWords, lengthLevel, normalizeFragments } from '../shared/selection.js';

export { countWords };

const messages = {
  short: (missing) => `Faltan ${missing} palabras`,
  ready: () => 'Listo para analizar',
  good: () => 'Buena longitud',
  full: () => 'Longitud completa: lo que siga no se analiza',
};

// Medidor de P02: la barra va de 0 a ~350 palabras (lo que lee mBERT) con una marca en el mínimo (100).
export function meterState(words) {
  const count = Number.isInteger(words) && words > 0 ? words : 0;
  const level = lengthLevel(count);
  const missing = Math.max(0, MIN_WORDS - count);
  return {
    words: count,
    level,
    ready: count >= MIN_WORDS,
    missing,
    value: Math.min(100, Math.round((count / MAX_WORDS) * 100)),
    marker: Math.round((MIN_WORDS / MAX_WORDS) * 100),
    message: messages[level](missing),
  };
}

export function presentFragments(selection) {
  return normalizeFragments(selection).map((fragment, index) => ({
    id: fragment.id,
    number: String(index + 1).padStart(2, '0'),
    text: fragment.text.trim(),
    words: countWords(fragment.text),
  }));
}
