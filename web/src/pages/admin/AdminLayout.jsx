import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { login, logout } from '../../lib/api.js';
import { useSession } from '../../lib/hooks.js';

function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [state, setState] = useState({ sending: false, error: null });

  async function submit(event) {
    event.preventDefault();
    setState({ sending: true, error: null });
    try { await login(email.trim(), password); }
    catch (error) { setState({ sending: false, error }); }
  }

  return (
    <div className="shell login">
      <form className="panel panel--accent panel--mark boot" onSubmit={submit}>
        <span className="label label--accent">Terminal de autenticación</span>
        <h1 className="display" style={{ margin: '8px 0 6px', fontSize: 20 }}>Acceso administrador</h1>
        <p className="muted" style={{ margin: '0 0 20px', fontSize: 14 }}>
          Solo para el equipo de ScanTrue. Los resultados son públicos y no necesitan cuenta.
        </p>
        <label className="field">
          <span>Correo</span>
          <input className="input" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label className="field" style={{ marginTop: 14 }}>
          <span>Contraseña</span>
          <input className="input" type="password" autoComplete="current-password" required minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {state.error && <p className="alert" style={{ margin: '16px 0 0' }} role="alert">{state.error.message}</p>}
        <button type="submit" className="btn" style={{ width: '100%', marginTop: 20 }} disabled={state.sending}>
          {state.sending ? 'Verificando sesión…' : 'Entrar'}
        </button>
      </form>
    </div>
  );
}

const TABS = [
  { to: '/admin', label: 'Panel', end: true },
  { to: '/admin/casos', label: 'Casos' },
  { to: '/admin/datasets', label: 'Datasets' },
  { to: '/admin/modelos', label: 'Modelos' },
];

export default function AdminLayout() {
  const session = useSession();
  if (!session) return <Login />;
  return (
    <div className="shell">
      <nav className="subnav" aria-label="Administración">
        {TABS.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end={tab.end} className={({ isActive }) => (isActive ? 'active' : undefined)}>{tab.label}</NavLink>
        ))}
        <span className="who">
          <span>{session.correo}</span>
          <button type="button" className="text-link" onClick={logout}>Salir</button>
        </span>
      </nav>
      <Outlet />
    </div>
  );
}
