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

// Lo que decidió el juicio de cada afirmación con las fuentes que encontró.
const CLAIM_VERDICTS = {
  apoyada: { label: 'Respaldada', tone: 'very-low' },
  contradicha: { label: 'Contradicha', tone: 'very-high' },
  fuera_de_contexto: { label: 'Fuera de contexto', tone: 'high' },
  insuficiente: { label: 'Sin evidencia suficiente', tone: 'middle' },
};
const CLAIM_ORIGINS = { base_anterior: 'Verificada antes' };

const VERIFICATION_STATES = {
  pendiente: 'En cola de verificación',
  en_proceso: 'Verificando con fuentes externas',
  fallida: 'No se pudo verificar',
};

// Qué le pasa a un caso que todavía no tiene conclusión.
const VERIFICATION_NOTES = {
  pendiente: 'Está en la cola y se contrastará con fuentes externas cuando le toque.',
  en_proceso: 'Se está contrastando con fuentes externas ahora mismo.',
  fallida: 'No se pudo contrastar este texto con fuentes externas. La salida de los dos modelos sigue siendo válida.',
};

// Causas guardadas en `ultimo_error` (solo las ve el administrador).
const FAILURE_REASONS = {
  llm_no_disponible: 'El servidor del LLM no respondió',
  tiempo_agotado: 'El LLM tardó demasiado',
  no_autorizado: 'El LLM rechazó la clave de API',
  salida_invalida: 'El LLM respondió algo que no se pudo usar',
  busqueda_fallida: 'La búsqueda web falló',
  busqueda_no_autorizada: 'La búsqueda web rechazó la clave de API',
  busqueda_cupo_agotado: 'Se agotó el cupo de la búsqueda web',
  analisis_no_encontrado: 'El análisis ya no existe',
  intentos_agotados: 'Se agotaron los intentos',
  error_interno: 'Error interno del servidor',
};

const text = (value) => (typeof value === 'string' && value.trim() ? value.trim() : null);
const httpUrl = (value) => (typeof value === 'string' && /^https?:\/\//.test(value) ? value : null);

function presentClaim(item, index) {
  if (typeof item === 'string') return text(item) ? { id: index + 1, text: item.trim(), url: httpUrl(item), verdict: null, origin: null, sourceIds: [] } : null;
  const label = text(item?.texto) ?? text(item?.afirmacion) ?? httpUrl(item?.url);
  if (!label) return null;
  return {
    id: Number.isInteger(item?.id) ? item.id : index + 1,
    text: label,
    url: httpUrl(item?.url),
    verdict: CLAIM_VERDICTS[item?.veredicto] ? { key: item.veredicto, ...CLAIM_VERDICTS[item.veredicto] } : null,
    origin: CLAIM_ORIGINS[item?.origen] ?? null,
    sourceIds: (Array.isArray(item?.fuente_ids) ? item.fuente_ids : []).filter(Number.isInteger),
  };
}

function presentSource(item, index) {
  if (typeof item === 'string') return text(item) ? { id: index + 1, text: item.trim(), url: httpUrl(item), domain: null, quote: null, consulted: null } : null;
  const url = httpUrl(item?.url);
  const label = text(item?.titulo) ?? text(item?.texto) ?? url;
  if (!label) return null;
  return {
    id: Number.isInteger(item?.id) ? item.id : index + 1,
    text: label,
    url,
    domain: text(item?.dominio),
    quote: text(item?.extracto),
    consulted: item?.consultada_en ? formatDate(item.consultada_en) : null,
  };
}

// Tercer criterio: la verificación con fuentes externas (incremento 2).
export function presentVerification(verification) {
  if (!verification) {
    return { state: 'none', label: 'Aún no disponible', tone: null, summary: null, note: null, sources: [], claims: [] };
  }
  const conclusion = verification.estado === 'completada' ? CONCLUSIONS[verification.conclusion] : null;
  const list = (items, present) => (Array.isArray(items) ? items : []).map(present).filter(Boolean);
  return {
    state: conclusion ? 'done' : verification.estado === 'fallida' ? 'failed' : 'working',
    label: conclusion?.label ?? VERIFICATION_STATES[verification.estado] ?? 'En cola de verificación',
    tone: conclusion?.tone ?? null,
    summary: text(verification.resumen),
    note: conclusion ? null : VERIFICATION_NOTES[verification.estado] ?? VERIFICATION_NOTES.pendiente,
    sources: list(verification.fuentes, presentSource),
    claims: list(verification.afirmaciones, presentClaim),
  };
}

// Seguimiento de un caso para el administrador: intentos, causa de la falla y si se puede reintentar.
export function presentTracking(verification, tracking) {
  if (!verification) return null;
  const started = Date.parse(tracking?.iniciado_en ?? '');
  const finished = Date.parse(tracking?.terminado_en ?? '');
  return {
    attempts: Number.isInteger(tracking?.intentos) ? tracking.intentos : 0,
    reason: tracking?.ultimo_error ? FAILURE_REASONS[tracking.ultimo_error] ?? tracking.ultimo_error : null,
    next: tracking?.proximo_intento && verification.estado === 'pendiente' ? formatDate(tracking.proximo_intento) : null,
    version: text(tracking?.version_prompts),
    copied: Boolean(tracking?.copiada_de),
    seconds: Number.isFinite(started) && Number.isFinite(finished) && finished > started ? Math.round((finished - started) / 1000) : null,
    canRetry: verification.estado === 'fallida' || verification.estado === 'pendiente',
  };
}

// Estado de la cola y del trabajador para el tablero del panel.
export function presentQueue(status) {
  const llm = status?.llm ?? {};
  return {
    worker: !status?.habilitada
      ? { state: 'off', label: 'Apagado' }
      : status.en_pausa ? { state: 'paused', label: 'En pausa' } : { state: 'running', label: 'Activo' },
    llm: !llm.configurado
      ? { state: 'off', label: 'Sin configurar' }
      : llm.disponible ? { state: 'ok', label: 'Responde' } : { state: 'down', label: 'No responde' },
    average: typeof status?.duracion_media_segundos === 'number' ? `${Math.round(status.duracion_media_segundos)} s` : '—',
    waiting: (status?.pendientes ?? 0) + (status?.en_proceso ?? 0),
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

// Estándar de los datasets (datos_comunes/estandar.py): por qué una noticia queda fuera y qué se recorta.
export const DATASET_EXCLUDED = {
  no_espanol: 'no está en español',
  sin_fin_de_oracion: 'no tiene ninguna oración terminada en punto',
  menos_de_100_tokens: 'tiene menos de 100 palabras en oraciones completas',
  oraciones_demasiado_largas: 'sus oraciones pasan de 200 palabras',
  cruce_prueba_congelada: 'ya está en la prueba congelada de comun_v1',
  conflicto_etiquetas: 'otra copia del mismo texto tiene la etiqueta contraria',
};

export const DATASET_CUTS = {
  tope_noticia: 'cortadas al tope de palabras por noticia',
  inicio_incompleto: 'sin la oración inicial cortada',
  final_incompleto: 'sin la oración final cortada',
  oraciones_sueltas: 'con alguna oración que no cabía en un fragmento',
};

// Lo mismo para un solo caso (vista previa al revisarlo).
export const CASE_CUTS = {
  tope_noticia: 'Se corta al tope de 400 palabras por noticia.',
  inicio_incompleto: 'Se quita la oración inicial, que empieza cortada.',
  final_incompleto: 'Se quita la oración final, que quedó cortada.',
  oraciones_sueltas: 'Alguna oración no cabe en un fragmento y se deja fuera.',
};
