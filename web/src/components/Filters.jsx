import { useEffect, useState } from 'react';
import {
  ADMIN_ORDERS, AGREEMENTS, LEVELS, PUBLIC_ORDERS, REVIEW_STATES, VERIFICATIONS, VISIBILITIES,
  activeCount, emptyFilters,
} from '../lib/filters.js';
import { useDebounced } from '../lib/hooks.js';
import { Icon } from './ui.jsx';

function Select({ label, value, options, all, onChange }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select className="input" value={value} onChange={(event) => onChange(event.target.value)}>
        {all && <option value="">{all}</option>}
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

// Buscador y filtros de Resultados (`scope="public"`) y de Casos (`scope="admin"`).
// `filters` viene de la URL; `onChange` recibe los filtros nuevos completos.
export default function Filters({ filters, onChange, domains = [], scope = 'public' }) {
  const admin = scope === 'admin';
  const [text, setText] = useState(filters.q);
  const debounced = useDebounced(text);
  const set = (key, value) => onChange({ ...filters, [key]: value });

  // La búsqueda se aplica al dejar de escribir; si la URL cambia desde fuera, se refleja.
  useEffect(() => { if (debounced !== filters.q) set('q', debounced.trim()); /* eslint-disable-next-line */ }, [debounced]);
  useEffect(() => { setText(filters.q); }, [filters.q]);

  const known = domains.some((item) => item.dominio === filters.dominio);
  const domainOptions = [
    ...(filters.dominio && !known ? [{ value: filters.dominio, label: filters.dominio }] : []),
    ...domains.map((item) => ({ value: item.dominio, label: `${item.dominio} (${item.n})` })),
  ];
  const active = activeCount(filters, scope);

  return (
    <form className="panel panel--tight filters" role="search" onSubmit={(event) => { event.preventDefault(); set('q', text.trim()); }}>
      <label className="search">
        <span className="sr-only">Buscar en los fragmentos o por página de origen</span>
        <Icon name="search" />
        <input
          className="input" type="search" value={text} maxLength={100}
          placeholder="Buscar en el texto o por página de origen…"
          onChange={(event) => setText(event.target.value)}
        />
      </label>

      <div className="field">
        <span id={`level-${scope}`}>Nivel del resultado</span>
        <div className="chips" role="group" aria-labelledby={`level-${scope}`}>
          <button type="button" className="chip" aria-pressed={!filters.nivel} onClick={() => set('nivel', '')}>Todos</button>
          {LEVELS.map((level) => (
            <button
              key={level.value} type="button" className={`chip tone-${level.tone}`}
              aria-pressed={filters.nivel === level.value} title={level.label}
              onClick={() => set('nivel', filters.nivel === level.value ? '' : level.value)}
            >
              <i className="led" />{level.short}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-grid">
        <Select label="Acuerdo entre modelos" value={filters.comparacion} options={AGREEMENTS} all="Todos" onChange={(value) => set('comparacion', value)} />
        {admin
          ? <Select label="Revisión" value={filters.revision} options={REVIEW_STATES} all="Todos" onChange={(value) => set('revision', value)} />
          : <Select label="Verificación web" value={filters.verificacion} options={VERIFICATIONS} all="Todas" onChange={(value) => set('verificacion', value)} />}
        <Select label="Página de origen" value={filters.dominio} options={domainOptions} all="Todas" onChange={(value) => set('dominio', value)} />
        {admin && <Select label="Visibilidad" value={filters.visibilidad} options={VISIBILITIES} all="Todos" onChange={(value) => set('visibilidad', value)} />}
        <label className="field">
          <span>Desde</span>
          <input className="input" type="date" value={filters.desde} max={filters.hasta || undefined} onChange={(event) => set('desde', event.target.value)} />
        </label>
        <label className="field">
          <span>Hasta</span>
          <input className="input" type="date" value={filters.hasta} min={filters.desde || undefined} onChange={(event) => set('hasta', event.target.value)} />
        </label>
        <Select label="Orden" value={filters.orden} options={admin ? ADMIN_ORDERS : PUBLIC_ORDERS} onChange={(value) => set('orden', value)} />
      </div>

      {active > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span className="label label--accent">{active} {active === 1 ? 'filtro activo' : 'filtros activos'}</span>
          <button type="button" className="text-link" onClick={() => { setText(''); onChange({ ...emptyFilters(scope), orden: filters.orden }); }}>Limpiar filtros</button>
        </div>
      )}
    </form>
  );
}
