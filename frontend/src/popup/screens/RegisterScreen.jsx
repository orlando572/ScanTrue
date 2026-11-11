import { useRef, useState } from 'react';
import { sendExtensionMessage } from '../extension-message.js';
import ScreenHeader from '../components/ScreenHeader.jsx';
import PasswordVisibilityButton from '../components/PasswordVisibilityButton.jsx';

const initialValues = { email: '', password: '', confirmation: '' };
const initialTouched = { email: false, password: false, confirmation: false };

function fieldError(name, values) {
  if (name === 'email') {
    if (!values.email.trim()) return 'Escribe tu correo electrónico.';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) return 'Revisa el formato del correo.';
  }
  if (name === 'password') {
    if (!values.password) return 'Escribe una contraseña.';
    if (values.password.length < 8) return 'Usa al menos 8 caracteres.';
  }
  if (name === 'confirmation') {
    if (!values.confirmation) return 'Confirma tu contraseña.';
    if (values.confirmation !== values.password) return 'Las contraseñas no coinciden.';
  }
  return '';
}

function PasswordField({ id, label, value, onChange, onBlur, error }) {
  const [visible, setVisible] = useState(false);

  return <div className="mt-5">
    <label className="hud-label" htmlFor={id}>{label}</label>
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
      <PasswordVisibilityButton visible={visible} onToggle={() => setVisible((current) => !current)} label={label} />
    </div>
    {error && <p id={`${id}-error`} className="hud-alert mt-1.5 text-[12px] leading-[18px]" role="alert">{error}</p>}
  </div>;
}

export default function RegisterScreen({ onBack, onLogin, onComplete }) {
  const [values, setValues] = useState(initialValues);
  const [touched, setTouched] = useState(initialTouched);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const submitLock = useRef(false);

  const change = (name) => (event) => setValues((current) => ({ ...current, [name]: event.target.value }));
  const blur = (name) => () => setTouched((current) => ({ ...current, [name]: true }));
  const error = (name) => touched[name] ? fieldError(name, values) : '';
  const submit = async (event) => {
    event.preventDefault();
    if (submitLock.current) return;
    setTouched({ email: true, password: true, confirmation: true });
    if (Object.keys(initialValues).some((name) => fieldError(name, values))) return;
    submitLock.current = true;
    setSubmitting(true);
    setSubmitError('');
    try {
      const response = await sendExtensionMessage({
        type: 'REGISTER_ACCOUNT', email: values.email.trim(), password: values.password,
      });
      if (!response?.ok || !response.account?.kind) throw new Error(response?.error ?? 'No pudimos crear la cuenta.');
      onComplete(response.account);
    } catch (error) {
      setSubmitError(error?.message ?? 'No pudimos crear la cuenta.');
    } finally { submitLock.current = false; setSubmitting(false); }
  };

  return <section className="flex flex-1 flex-col" aria-labelledby="register-title">
    <ScreenHeader title="Crear cuenta" titleId="register-title" backLabel="Volver a cuenta" onBack={onBack} />
    <form className="mt-6 flex flex-1 flex-col" noValidate onSubmit={submit}>
      <div className="hud-panel">
      <span className="hud-code hud-code--cyan mb-4" aria-hidden="true">Terminal de autenticación</span>
      <div>
        <label className="hud-label" htmlFor="register-email">Correo electrónico</label>
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
        {error('email') && <p id="register-email-error" className="hud-alert mt-1.5 text-[12px] leading-[18px]" role="alert">{error('email')}</p>}
      </div>

      <PasswordField id="register-password" label="Contraseña" value={values.password} onChange={change('password')} onBlur={blur('password')} error={error('password')} />
      <PasswordField id="register-confirmation" label="Confirmar contraseña" value={values.confirmation} onChange={change('confirmation')} onBlur={blur('confirmation')} error={error('confirmation')} />

      </div>

      <div className="mt-auto pt-8">
        {submitError && <p className="hud-alert mb-3 text-sm leading-5" role="alert">{submitError}</p>}
        <button type="submit" className="primary-button auth-submit" disabled={submitting}>{submitting ? 'Creando cuenta…' : 'Crear cuenta'}</button>
        <button type="button" className="secondary-button mt-5" onClick={onLogin} disabled={submitting}>Ya tengo cuenta</button>
      </div>
    </form>
  </section>;
}
