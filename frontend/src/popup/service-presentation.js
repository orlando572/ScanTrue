// Luces de la tira de estado: una por servicio real de /salud.
// Cada servicio tiene su color cuando funciona; rojo = caído, ámbar = falla en parte.
const FAIL = '#FF4A3D';
const PARTIAL = '#FFB21E';

const services = [
  { key: 'bilstm', name: 'Modelo BiLSTM', short: 'BiLSTM', color: '#38E1FF', read: (data) => data?.modelos?.bilstm },
  { key: 'mbert', name: 'Modelo BETO', short: 'BETO', color: '#A98BFF', read: (data) => data?.modelos?.mbert },
  { key: 'cuentas', name: 'Cuentas e historial', short: 'Cuentas', color: '#3DFF9A', read: (data) => data?.supabase_configurado },
  {
    key: 'cadena', name: 'Registro blockchain', short: 'Cadena', color: '#E6F4FF',
    read: (data) => {
      const chain = data?.blockchain;
      if (!chain || typeof chain !== 'object') return undefined;
      if (chain.conectada === true) return true;
      return chain.configurada === true ? 'partial' : false;
    },
  },
];

const labels = { ok: 'funcionando', partial: 'con fallos', down: 'no disponible', checking: 'comprobando', unknown: 'sin datos' };

function stateOf(value, health) {
  if (health === 'checking') return 'checking';
  if (health === 'unavailable') return 'down';
  if (value === true) return 'ok';
  if (value === false) return 'down';
  if (value === 'partial') return 'partial';
  return health === 'degraded' ? 'partial' : 'unknown';
}

export function presentServices(healthData, health) {
  return services.map(({ key, name, short, color, read }) => {
    const state = stateOf(read(healthData), health);
    const shown = state === 'ok' ? color : state === 'down' ? FAIL : state === 'partial' || state === 'unknown' ? PARTIAL : null;
    return { key, name, short, state, color: shown, label: `${name}: ${labels[state]}` };
  });
}
