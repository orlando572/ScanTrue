import { countWords } from '../shared/selection.js';

export function formatProbability(probability) {
  return typeof probability === 'number' && Number.isFinite(probability) && probability >= 0 && probability <= 1
    ? `${Math.round(probability * 100)} %`
    : null;
}

const resultLevels = [
  { max: 20, label: 'Muy probablemente verdadero', tone: 'very-low', icon: 'check-double' },
  { max: 40, label: 'Probablemente verdadero', tone: 'low', icon: 'check' },
  { max: 60, label: 'Resultado incierto', tone: 'middle', icon: 'question' },
  { max: 80, label: 'Probablemente falso', tone: 'high', icon: 'alert' },
  { max: 100, label: 'Muy probablemente falso', tone: 'very-high', icon: 'cross' },
];

export function presentResultLevel(probability) {
  if (formatProbability(probability) === null) return null;
  const value = Math.round(probability * 100);
  const { label, tone, icon } = resultLevels.find((level) => value <= level.max);
  return { value, label, tone, icon };
}

export function presentResult(result) {
  const unified = result?.resultado_unificado;
  const percentage = formatProbability(unified?.probabilidad_falsa);
  const level = presentResultLevel(unified?.probabilidad_falsa);

  const models = Array.isArray(unified?.modelos_utilizados)
    ? [...new Set(unified.modelos_utilizados.filter((model) => typeof model === 'string' && model.trim()))]
    : [];
  const source = models.length === 2
    ? 'Resultado combinado de dos modelos'
    : models.length === 1 ? 'Resultado basado en un modelo' : null;
  const outputs = result?.resultados;
  const hasBreakdown = !!outputs && typeof outputs === 'object' && !Array.isArray(outputs) && Object.keys(outputs).length > 0;

  return { percentage, level, source, hasBreakdown };
}

const MODELS = [
  { key: 'bilstm', name: 'BiLSTM' },
  { key: 'mbert', name: 'BETO' },
];

export function presentBreakdown(result) {
  const outputs = result?.resultados;
  const models = MODELS.map(({ key, name }) => {
    const output = outputs && typeof outputs === 'object' && !Array.isArray(outputs) ? outputs[key] : null;
    const level = output?.estado === 'ok' ? presentResultLevel(output.probabilidad_falsa) : null;
    const value = level?.value ?? null;
    const percentage = value === null ? null : `${value} %`;
    const classification = value !== null && ['falsa', 'real'].includes(output.clase) ? output.clase : null;
    return { key, name, percentage, value, classification, level: level?.label ?? null };
  });

  return { models, noneAvailable: models.every(({ percentage }) => percentage === null) };
}

export function domainFromUrl(url) {
  try {
    const parsed = new URL(url);
    return /^https?:$/.test(parsed.protocol) ? parsed.hostname.replace(/^www\./, '') : null;
  } catch { return null; }
}

const SNIPPET_CHARS = 180;

// Comienzo del texto en una línea, cortado en un espacio para no partir palabras.
export function textSnippet(text) {
  const flat = text.replace(/\s+/g, ' ').trim();
  if (flat.length <= SNIPPET_CHARS) return flat;
  const cut = flat.slice(0, SNIPPET_CHARS);
  const space = cut.lastIndexOf(' ');
  return `${(space > SNIPPET_CHARS * .6 ? cut.slice(0, space) : cut).replace(/[\s,.;:]+$/, '')}…`;
}

// Lectura complementaria de P05 y P08: posición de cada modelo en el espectro,
// acuerdo entre modelos y qué se leyó (página de origen, palabras y fragmento del texto).
export function presentInsights(result, text = null, url = null) {
  const { models } = presentBreakdown(result);
  const available = models.filter(({ value }) => value !== null);

  let consensus = null;
  if (result?.comparacion === 'coinciden' && available.length === 2) {
    consensus = { state: 'agree', title: 'Los modelos coinciden' };
  } else if (result?.comparacion === 'discrepan' && available.length === 2) {
    consensus = { state: 'disagree', title: 'Los modelos no coinciden' };
  } else if (available.length === 1) {
    consensus = { state: 'single', model: available[0].key, title: `Solo respondió ${available[0].name}` };
  }

  const fullText = typeof text === 'string' && text.trim() ? text.trim() : null;
  const words = fullText ? countWords(fullText) : 0;
  const domain = domainFromUrl(url);
  const reading = words > 0 || domain ? {
    words: words > 0 ? `${words} ${words === 1 ? 'palabra' : 'palabras'}` : null,
    domain,
    url: domain ? url : null,
    snippet: fullText ? textSnippet(fullText) : null,
    text: fullText,
  } : null;

  return {
    markers: available.map(({ key, name, value }) => ({ key, name, value })),
    consensus,
    reading,
    note: typeof result?.nota === 'string' && result.nota.trim() ? result.nota.trim() : null,
  };
}
