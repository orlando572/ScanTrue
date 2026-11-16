import { MAX_WORDS, MIN_WORDS, countWords, hasSelectionText, lengthLevel, normalizeFragments } from '../shared/selection.js';

export { countWords, hasSelectionText };

const messages = {
  short: (missing) => `Añade ${missing} ${missing === 1 ? 'palabra' : 'palabras'} más para poder analizar`,
  ready: () => 'Ya puedes analizar. Con más texto, el resultado es más fiable',
  good: () => 'Buena cantidad de texto',
  full: () => 'Ya hay texto de sobra: lo que añadas no se tendrá en cuenta',
};

// Medidor de P02: la barra va de 0 a ~200 palabras (lo que leen los modelos) con una marca en el mínimo (100).
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

// El resultado guardado es de este mismo texto: cualquier cambio (editar, añadir o quitar
// fragmentos) le pone un `capturedAt` nuevo a la selección. Sirve para volver al resultado sin
// analizar otra vez (lo que crearía un duplicado).
export function resultForSelection(operation, selection) {
  return operation?.status === 'completed'
    && Boolean(operation.result)
    && operation.selectionCapturedAt !== undefined
    && operation.selectionCapturedAt === selection?.capturedAt;
}

export function presentFragments(selection) {
  return normalizeFragments(selection).map((fragment, index) => ({
    id: fragment.id,
    number: String(index + 1).padStart(2, '0'),
    text: fragment.text.trim(),
    words: countWords(fragment.text),
  }));
}
