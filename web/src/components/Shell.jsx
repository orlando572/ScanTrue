import { Link, NavLink } from 'react-router-dom';
import { presentServices } from '../../../frontend/src/popup/service-presentation.js';
import { Mark } from './ui.jsx';

// Una luz por servicio real de /salud, con los colores de la web.
const COLORS = {
  bilstm: 'var(--color-acid)',
  mbert: 'var(--color-violet)',
  cuentas: 'var(--color-real)',
  cadena: 'var(--color-ink)',
};
const STATE_COLORS = { down: 'var(--color-false)', partial: '#ffb21e', unknown: '#ffb21e' };
const SUMMARY = {
  ok: 'En línea', degraded: 'Servicio limitado', unavailable: 'Sin conexión', checking: 'Conectando…',
};

export function serviceLights(health) {
  return presentServices(health.data, health.health).map((service) => ({
    ...service,
    color: service.state === 'ok' ? COLORS[service.key] : STATE_COLORS[service.state] ?? null,
  }));
}

export function ServiceStrip({ health, names = true }) {
  const summary = SUMMARY[health.health] ?? 'Estado desconocido';
  return (
    <div className="service-strip">
      <ul aria-label="Estado de los servicios">
        {serviceLights(health).map((service) => (
          <li key={service.key} title={service.label}>
            <i
              className={`led${service.state === 'down' || service.state === 'checking' ? ' led--blink' : ''}`}
              style={{ '--led': service.color ?? undefined }}
            />
            {names ? <span aria-hidden="true">{service.short}</span> : null}
            <span className="sr-only">{service.label}</span>
          </li>
        ))}
      </ul>
      <span role="status">
        {summary}{health.health === 'ok' && health.latency != null ? ` · ${health.latency} ms` : ''}
      </span>
    </div>
  );
}

export function SiteHeader({ health }) {
  return (
    <header className="site-header">
      <div className="shell">
        <Link className="brand" to="/" aria-label="ScanTrue, inicio">
          <Mark />
          <span>SCAN<i>//</i>TRUE</span>
        </Link>
        <nav className="nav" aria-label="Principal">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : undefined)}>Inicio</NavLink>
          <NavLink to="/resultados" className={({ isActive }) => (isActive ? 'active' : undefined)}>Resultados</NavLink>
        </nav>
        <ServiceStrip health={health} names={false} />
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="shell">
        <span>ScanTrue orienta con dos modelos de lenguaje. No verifica los hechos de una noticia.</span>
        <Link className="text-link" to="/admin">Acceso administrador</Link>
      </div>
    </footer>
  );
}
