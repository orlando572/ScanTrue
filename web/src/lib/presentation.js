// Presentación de un análisis en la web. Reutiliza la lógica de la extensión para que el
// mismo resultado se lea igual en los dos productos (niveles, redondeo y textos).
import { presentBreakdown, presentResultLevel } from '../../../frontend/src/popup/result-presentation.js';
import { formatDate } from '../../../frontend/src/popup/history-presentation.js';

export { formatDate, presentResultLevel };

// Un color por criterio: BiLSTM, BETO y la verificación web (incremento 2).
export const CRITERIA = {
  bilstm: { name: 'BiLSTM', color: 'var(--color-acid)', role: 'Red recurrente: lee el texto palabra por palabra.' },
  mbert: { name: 'BETO', color: 'var(--color-violet)', role: 'Transformer en español: lee el texto en contexto.' },
  web: { name: 'Verificación web', color: 'var(--color-coral)', role: 'Contrasta las afirmaciones con fuentes externas.' },
};

const AGREEMENT = {
  coinciden: { state: 'agree', label: 'Los modelos coinciden' },
  discrepan: { state: 'disagree', label: 'Los modelos no coinciden' },
  no_disponible: { state: 'single', label: 'Respondió un solo modelo' },
};

const CHAIN = {
  confirmado: { state: 'ok', label: 'Registro confirmado' },
  pendiente: { state: 'wait', label: 'Registro pendiente' },
  no_iniciado: { state: 'wait', label: 'Registro pendiente' },
  fallido: { state: 'fail', label: 'Registro fallido' },
};

const CONCLUSIONS = {
  respaldada: { label: 'Respaldada por fuentes', tone: 'very-low' },
  contradicha: { label: 'Contradicha por fuentes', tone: 'very-high' },
  fuera_de_contexto: { label: 'Fuera de contexto', tone: 'high' },
  evidencia_insuficiente: { label: 'Evidencia insuficiente', tone: 'middle' },
};

const VERIFICATION_STATES = {
  pendiente: 'En cola de verificación',
  en_proceso: 'Verificando con fuentes externas',
  fallida: 'No se pudo verificar',
};

// Tercer criterio: mientras no llegue del backend se muestra como «aún no disponible».
export function presentVerification(verification) {
  if (!verification) {
    return { state: 'none', label: 'Aún no disponible', tone: null, summary: null, sources: [], claims: [] };
  }
  const conclusion = verification.estado === 'completada' ? CONCLUSIONS[verification.conclusion] : null;
  const list = (items) => (Array.isArray(items) ? items : []).map((item) => {
    if (typeof item === 'string') return { text: item, url: /^https?:\/\//.test(item) ? item : null };
    const url = typeof item?.url === 'string' && /^https?:\/\//.test(item.url) ? item.url : null;
    const text = item?.titulo ?? item?.texto ?? item?.afirmacion ?? url;
    return typeof text === 'string' && text.trim() ? { text: text.trim(), url } : null;
  }).filter(Boolean);
  return {
    state: conclusion ? 'done' : verification.estado === 'fallida' ? 'failed' : 'working',
    label: conclusion?.label ?? VERIFICATION_STATES[verification.estado] ?? 'En cola de verificación',
    tone: conclusion?.tone ?? null,
    summary: typeof verification.resumen === 'string' && verification.resumen.trim() ? verification.resumen.trim() : null,
    sources: list(verification.fuentes),
    claims: list(verification.afirmaciones),
  };
}

export function shortId(id) {
  return typeof id === 'string' ? id.replace(/-/g, '').slice(0, 6).toUpperCase() : '——';
}

export function presentAnalysis(item) {
  const level = presentResultLevel(item?.probabilidad_falsa);
  const { models } = presentBreakdown(item);
  const fragments = (Array.isArray(item?.fragmentos) ? item.fragmentos : [])
    .filter((text) => typeof text === 'string' && text.trim())
    .map((text, index) => ({ number: String(index + 1).padStart(2, '0'), text: text.trim() }));
  const total = Number.isInteger(item?.fragmentos_total) ? item.fragmentos_total : fragments.length;
  const words = Number.isInteger(item?.palabras) ? item.palabras : 0;
  return {
    id: item?.id,
    code: shortId(item?.id),
    date: formatDate(item?.fecha),
    domain: item?.dominio ?? null,
    url: item?.dominio ? item?.url ?? null : null,
    fragments,
    hiddenFragments: Math.max(0, total - fragments.length),
    words: words > 0 ? `${words.toLocaleString('es-PE')} ${words === 1 ? 'palabra' : 'palabras'}` : null,
    truncated: item?.texto_recortado === true,
    level,
    tone: level?.tone ?? 'none',
    models: models.map((model) => ({ ...model, ...CRITERIA[model.key] })),
    agreement: AGREEMENT[item?.comparacion] ?? AGREEMENT.no_disponible,
    chain: CHAIN[item?.estado_blockchain] ?? CHAIN.pendiente,
    verification: presentVerification(item?.verificacion_web),
  };
}

// Qué parte del fragmento original leyó un modelo: su texto es un prefijo del original.
export function readSplit(original, modelText) {
  if (typeof original !== 'string' || !original) return null;
  if (typeof modelText !== 'string' || !modelText) return null;
  if (!original.startsWith(modelText)) return { read: modelText, rest: '' };
  return { read: modelText, rest: original.slice(modelText.length) };
}

export function percent(value) {
  return typeof value === 'number' && Number.isFinite(value) ? `${Math.round(value * 100)} %` : '—';
}

export function share(part, total) {
  return total > 0 ? Math.round((part / total) * 100) : 0;
}
