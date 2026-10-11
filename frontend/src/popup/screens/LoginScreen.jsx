import { useRef, useState } from 'react';
import { sendExtensionMessage } from '../extension-message.js';
import PasswordVisibilityButton from '../components/PasswordVisibilityButton.jsx';

function emailError(value) {
  if (!value.trim()) return 'Escribe tu correo electrónico.';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())) return 'Revisa el formato del correo.';
  return '';
}

export default function LoginScreen({ onBack, onRegister, onComplete }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [emailTouched, setEmailTouched] = useState(false);
  const [passwordTouched, setPasswordTouched] = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [requiresTransferChoice, setRequiresTransferChoice] = useState(false);
  const submitLock = useRef(false);
  const emailMessage = emailTouched ? emailError(email) : '';
  const passwordMessage = passwordTouched && !password ? 'Escribe tu contraseña.' : '';
  const submit = async (event, skipGuestTransfer = false) => {
    event.preventDefault();
    if (submitLock.current) return;
    setEmailTouched(true);
    setPasswordTouched(true);
    if (emailError(email) || !password) return;
    submitLock.current = true;
    setSubmitting(true);
    setSubmitError('');
    try {
      const response = await sendExtensionMessage({
        type: 'LOGIN_ACCOUNT', email: email.trim(), password, skipGuestTransfer,
      });
      if (!response?.ok || response.account?.kind !== 'account') {
        setRequiresTransferChoice(response?.requiresTransferChoice === true);
        throw new Error(response?.error ?? 'No pudimos iniciar sesión.');
      }
      onComplete(response.account);
    } catch (error) {
      setSubmitError(error?.message ?? 'No pudimos iniciar sesión.');
    } finally { submitLock.current = false; setSubmitting(false); }
  };

  return <section className="flex flex-1 flex-col" aria-labelledby="login-title">
    <div className="flex items-start gap-3">
      <button type="button" className="breakdown-back" aria-label="Volver a cuenta" title="Volver a cuenta" onClick={onBack}>
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m14 5-7 7 7 7" /></svg>
      </button>
      <h1 id="login-title" className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Iniciar sesión</h1>
    </div>
    <form className="mt-7 flex flex-1 flex-col" noValidate onSubmit={submit}>
      <div>
        <label className="block text-sm font-semibold text-ink" htmlFor="login-email">Correo electrónico</label>
        <input
          id="login-email"
          className="auth-input mt-2"
          type="email"
          value={email}
          onChange={(event) => { setEmail(event.target.value); setRequiresTransferChoice(false); }}
          onBlur={() => setEmailTouched(true)}
          autoComplete="username"
          inputMode="email"
          aria-invalid={Boolean(emailMessage)}
          aria-describedby={emailMessage ? 'login-email-error' : undefined}
        />
        {emailMessage && <p id="login-email-error" className="mt-1.5 text-[12px] leading-[18px] text-false" role="alert">{emailMessage}</p>}
      </div>

      <div className="mt-5">
        <label className="block text-sm font-semibold text-ink" htmlFor="login-password">Contraseña</label>
        <div className="relative mt-2">
          <input
            id="login-password"
            className="auth-input auth-input--password"
            type={passwordVisible ? 'text' : 'password'}
            value={password}
            onChange={(event) => { setPassword(event.target.value); setRequiresTransferChoice(false); }}
            onBlur={() => setPasswordTouched(true)}
            autoComplete="current-password"
            aria-invalid={Boolean(passwordMessage)}
            aria-describedby={passwordMessage ? 'login-password-error' : undefined}
          />
          <PasswordVisibilityButton visible={passwordVisible} onToggle={() => setPasswordVisible((current) => !current)} />
        </div>
        {passwordMessage && <p id="login-password-error" className="mt-1.5 text-[12px] leading-[18px] text-false" role="alert">{passwordMessage}</p>}
      </div>

      <div className="mt-auto pt-8">
        {submitError && <p className="mb-3 text-sm leading-5 text-false" role="alert">{submitError}</p>}
        <button type="submit" className="primary-button auth-submit" disabled={submitting}>{submitting ? 'Iniciando sesión…' : 'Iniciar sesión'}</button>
        {requiresTransferChoice && <>
          <p className="mt-3 text-[12px] leading-[18px] text-muted">Puedes entrar sin incorporar el historial de invitado. Esos análisis no aparecerán en tu cuenta.</p>
          <button type="button" className="secondary-button mt-3" onClick={(event) => submit(event, true)} disabled={submitting}>Entrar sin transferir historial</button>
        </>}
        <button type="button" className="secondary-button mt-5" onClick={onRegister} disabled={submitting}>Crear cuenta</button>
      </div>
    </form>
  </section>;
}
