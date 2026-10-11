import { formatProbability, presentResult } from './result-presentation.js';

export function domainFromUrl(url) {
  try {
    const parsed = new URL(url);
    return /^https?:$/.test(parsed.protocol) ? parsed.hostname : null;
  } catch { return null; }
}

export function formatDate(value) {
  if (typeof value !== 'string' || !value.trim()) return 'Fecha no disponible';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Fecha no disponible';
  return new Intl.DateTimeFormat('es-PE', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(date);
}

export function presentHistoryItem(item) {
  const preview = typeof item?.vista_previa === 'string' && item.vista_previa.trim() ? item.vista_previa.trim() : null;
  const domain = domainFromUrl(item?.url);
  return {
    id: item?.id,
    date: formatDate(item?.fecha),
    title: preview ?? domain ?? 'Análisis anterior',
    domain: preview ? domain : null,
    percentage: formatProbability(item?.resultado_unificado?.probabilidad_falsa),
  };
}

export function presentHistoryDetail(item) {
  const result = presentResult(item);
  return {
    date: formatDate(item?.fecha),
    domain: domainFromUrl(item?.url),
    text: typeof item?.texto === 'string' && item.texto.trim() ? item.texto : null,
    percentage: result.percentage,
    source: result.source,
    hasBreakdown: result.hasBreakdown,
  };
}

export function appendUniqueHistory(previous, incoming) {
  const seen = new Set(previous.map((item) => item.id));
  return [...previous, ...incoming.filter((item) => {
    if (!item || typeof item.id !== 'string' || !item.id || seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  })];
}
