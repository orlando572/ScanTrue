import { useRef, useState } from 'react';
import { sendExtensionMessage } from '../extension-message.js';
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
      <PasswordVisibilityButton visible={visible} onToggle={() => setVisible((current) => !current)} label={label} />
    </div>
    {error && <p id={`${id}-error`} className="mt-1.5 text-[12px] leading-[18px] text-false" role="alert">{error}</p>}
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
    <div className="flex items-start gap-3">
      <button type="button" className="breakdown-back" aria-label="Volver a cuenta" title="Volver a cuenta" onClick={onBack}>
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m14 5-7 7 7 7" /></svg>
      </button>
      <h1 id="register-title" className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Crear cuenta</h1>
    </div>
    <form className="mt-7 flex flex-1 flex-col" noValidate onSubmit={submit}>
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
        {submitError && <p className="mb-3 text-sm leading-5 text-false" role="alert">{submitError}</p>}
        <button type="submit" className="primary-button auth-submit" disabled={submitting}>{submitting ? 'Creando cuenta…' : 'Crear cuenta'}</button>
        <button type="button" className="secondary-button mt-5" onClick={onLogin} disabled={submitting}>Ya tengo cuenta</button>
      </div>
    </form>
  </section>;
}
