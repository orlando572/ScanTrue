// Filtros de Resultados y de Casos: se leen de la URL y se traducen a la consulta de la API.
// Lógica pura (sin React) para poder probarla con `node --test`.

export const LEVELS = [
  { value: '1', label: 'Muy probablemente verdadero', short: 'Muy prob. verdadero', tone: 'very-low' },
  { value: '2', label: 'Probablemente verdadero', short: 'Prob. verdadero', tone: 'low' },
  { value: '3', label: 'Resultado incierto', short: 'Incierto', tone: 'middle' },
  { value: '4', label: 'Probablemente falso', short: 'Prob. falso', tone: 'high' },
  { value: '5', label: 'Muy probablemente falso', short: 'Muy prob. falso', tone: 'very-high' },
];

export const AGREEMENTS = [
  { value: 'coinciden', label: 'Coinciden' },
  { value: 'discrepan', label: 'No coinciden' },
  { value: 'no_disponible', label: 'Un solo modelo' },
];

// Tercer criterio (incremento 2): el filtro ya funciona; hoy todos están «sin verificar».
export const VERIFICATIONS = [
  { value: 'sin_verificar', label: 'Sin verificar' },
  { value: 'respaldada', label: 'Respaldada' },
  { value: 'contradicha', label: 'Contradicha' },
  { value: 'fuera_de_contexto', label: 'Fuera de contexto' },
  { value: 'evidencia_insuficiente', label: 'Evidencia insuficiente' },
];

export const PUBLIC_ORDERS = [
  { value: 'recientes', label: 'Más recientes' },
  { value: 'antiguos', label: 'Más antiguos' },
  { value: 'mas_falsa', label: 'Mayor salida para falsa' },
  { value: 'menos_falsa', label: 'Menor salida para falsa' },
];

export const ADMIN_ORDERS = [{ value: 'prioridad', label: 'Discrepan primero' }, ...PUBLIC_ORDERS];

export const REVIEW_STATES = [
  { value: 'pendiente', label: 'Pendientes' },
  { value: 'revisado', label: 'Revisados' },
  { value: 'aprobado', label: 'Aprobados' },
  { value: 'corregido', label: 'Corregidos' },
  { value: 'descartado', label: 'Descartados' },
];

export const VISIBILITIES = [
  { value: 'visibles', label: 'Visibles en la web' },
  { value: 'ocultos', label: 'Ocultos' },
];

const values = (options) => options.map((option) => option.value);
const DATE = /^\d{4}-\d{2}-\d{2}$/;

const PUBLIC_FIELDS = {
  q: { read: (value) => value.trim().slice(0, 100) },
  nivel: { allowed: values(LEVELS) },
  comparacion: { allowed: values(AGREEMENTS) },
  desde: { read: (value) => (DATE.test(value) ? value : '') },
  hasta: { read: (value) => (DATE.test(value) ? value : '') },
  dominio: { read: (value) => value.trim().toLowerCase().slice(0, 253) },
  verificacion: { allowed: values(VERIFICATIONS) },
  orden: { allowed: values(PUBLIC_ORDERS), fallback: 'recientes' },
};

const ADMIN_FIELDS = {
  ...PUBLIC_FIELDS,
  verificacion: undefined,
  revision: { allowed: values(REVIEW_STATES) },
  visibilidad: { allowed: values(VISIBILITIES) },
  orden: { allowed: values(ADMIN_ORDERS), fallback: 'prioridad' },
};

const fieldsOf = (scope) => Object.entries(scope === 'admin' ? ADMIN_FIELDS : PUBLIC_FIELDS)
  .filter(([, rule]) => rule);

// Lee los filtros de la URL; lo que no se reconoce se ignora.
export function readFilters(searchParams, scope = 'public') {
  const filters = {};
  fieldsOf(scope).forEach(([key, rule]) => {
    const raw = searchParams.get(key) ?? '';
    const value = rule.allowed ? (rule.allowed.includes(raw) ? raw : '') : rule.read(raw);
    filters[key] = value || rule.fallback || '';
  });
  return filters;
}

// Parámetros para la URL del navegador: solo lo que no es el valor por defecto.
export function writeFilters(filters, scope = 'public') {
  const params = new URLSearchParams();
  fieldsOf(scope).forEach(([key, rule]) => {
    const value = filters[key];
    if (value && value !== rule.fallback) params.set(key, value);
  });
  return params;
}

// Consulta de la API. `hasta` anterior a `desde` se intercambia en vez de dar una lista vacía.
export function toApiQuery(filters, scope = 'public') {
  const result = {};
  fieldsOf(scope).forEach(([key]) => { if (filters[key]) result[key] = filters[key]; });
  if (result.desde && result.hasta && result.desde > result.hasta) {
    [result.desde, result.hasta] = [result.hasta, result.desde];
  }
  return result;
}

// Filtros activos sin contar el orden.
export function activeCount(filters, scope = 'public') {
  return fieldsOf(scope).filter(([key]) => key !== 'orden' && filters[key]).length;
}

export function emptyFilters(scope = 'public') {
  return readFilters(new URLSearchParams(), scope);
}
