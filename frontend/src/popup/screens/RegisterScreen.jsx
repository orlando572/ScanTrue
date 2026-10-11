import { useState } from 'react';

const initialValues = { email: '', password: '', confirmation: '' };
const initialTouched = { email: false, password: false, confirmation: false };

function fieldError(name, values) {
  if (name === 'email') {
    if (!values.email.trim()) return 'Escribe tu correo electrónico.';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) return 'Revisa el formato del correo.';
  }
  if (name === 'password' && !values.password) return 'Escribe una contraseña.';
  if (name === 'confirmation') {
    if (!values.confirmation) return 'Confirma tu contraseña.';
    if (values.confirmation !== values.password) return 'Las contraseñas no coinciden.';
  }
  return '';
}

function PasswordField({ id, label, value, onChange, onBlur, error }) {
  const [visible, setVisible] = useState(false);

  return <div className="mt-5">
    <label className="block text-sm font-semibold text-ink" htmlFor={id}>{label}</label>
    <div className="relative mt-2">
      <input
        id={id}
        className="auth-input auth-input--password"
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        onBlur={onBlur}
        autoComplete="new-password"
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
      />
      <button
        type="button"
        className="absolute inset-y-0 right-1 my-1 rounded-md px-3 text-[12px] font-semibold text-accent hover:bg-accent-soft"
        onClick={() => setVisible((current) => !current)}
        aria-label={`${visible ? 'Ocultar' : 'Mostrar'} ${label.toLowerCase()}`}
        aria-pressed={visible}
      >{visible ? 'Ocultar' : 'Mostrar'}</button>
    </div>
    {error && <p id={`${id}-error`} className="mt-1.5 text-[12px] leading-[18px] text-false" role="alert">{error}</p>}
  </div>;
}

export default function RegisterScreen({ onLogin }) {
  const [values, setValues] = useState(initialValues);
  const [touched, setTouched] = useState(initialTouched);

  const change = (name) => (event) => setValues((current) => ({ ...current, [name]: event.target.value }));
  const blur = (name) => () => setTouched((current) => ({ ...current, [name]: true }));
  const error = (name) => touched[name] ? fieldError(name, values) : '';

  return <section className="flex flex-1 flex-col" aria-labelledby="register-title">
    <h1 id="register-title" className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Crear cuenta</h1>
    <form className="mt-7 flex flex-1 flex-col" noValidate onSubmit={(event) => event.preventDefault()}>
      <div>
        <label className="block text-sm font-semibold text-ink" htmlFor="register-email">Correo electrónico</label>
        <input
          id="register-email"
          className="auth-input mt-2"
          type="email"
          value={values.email}
          onChange={change('email')}
          onBlur={blur('email')}
          autoComplete="email"
          inputMode="email"
          aria-invalid={Boolean(error('email'))}
          aria-describedby={error('email') ? 'register-email-error' : undefined}
        />
        {error('email') && <p id="register-email-error" className="mt-1.5 text-[12px] leading-[18px] text-false" role="alert">{error('email')}</p>}
      </div>

      <PasswordField id="register-password" label="Contraseña" value={values.password} onChange={change('password')} onBlur={blur('password')} error={error('password')} />
      <PasswordField id="register-confirmation" label="Confirmar contraseña" value={values.confirmation} onChange={change('confirmation')} onBlur={blur('confirmation')} error={error('confirmation')} />

      <div className="mt-auto pt-8">
        <button type="submit" className="primary-button auth-submit" disabled aria-describedby="register-unavailable">Crear cuenta</button>
        <p id="register-unavailable" className="mt-2 text-center text-[12px] leading-[18px] text-muted">El registro aún no está disponible.</p>
        <button type="button" className="secondary-button mt-5" onClick={onLogin}>Ya tengo cuenta</button>
      </div>
    </form>
  </section>;
}
