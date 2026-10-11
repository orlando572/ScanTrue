import { useState } from 'react';

function emailError(value) {
  if (!value.trim()) return 'Escribe tu correo electrónico.';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())) return 'Revisa el formato del correo.';
  return '';
}

export default function LoginScreen({ onRegister }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [emailTouched, setEmailTouched] = useState(false);
  const [passwordTouched, setPasswordTouched] = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const emailMessage = emailTouched ? emailError(email) : '';
  const passwordMessage = passwordTouched && !password ? 'Escribe tu contraseña.' : '';

  return <section className="flex flex-1 flex-col" aria-labelledby="login-title">
    <h1 id="login-title" className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Iniciar sesión</h1>
    <form className="mt-7 flex flex-1 flex-col" noValidate onSubmit={(event) => event.preventDefault()}>
      <div>
        <label className="block text-sm font-semibold text-ink" htmlFor="login-email">Correo electrónico</label>
        <input
          id="login-email"
          className="auth-input mt-2"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
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
            onChange={(event) => setPassword(event.target.value)}
            onBlur={() => setPasswordTouched(true)}
            autoComplete="current-password"
            aria-invalid={Boolean(passwordMessage)}
            aria-describedby={passwordMessage ? 'login-password-error' : undefined}
          />
          <button
            type="button"
            className="absolute inset-y-0 right-1 my-1 rounded-md px-3 text-[12px] font-semibold text-accent hover:bg-accent-soft"
            onClick={() => setPasswordVisible((current) => !current)}
            aria-label={`${passwordVisible ? 'Ocultar' : 'Mostrar'} contraseña`}
            aria-pressed={passwordVisible}
          >{passwordVisible ? 'Ocultar' : 'Mostrar'}</button>
        </div>
        {passwordMessage && <p id="login-password-error" className="mt-1.5 text-[12px] leading-[18px] text-false" role="alert">{passwordMessage}</p>}
      </div>

      <div className="mt-auto pt-8">
        <button type="submit" className="primary-button auth-submit" disabled aria-describedby="login-unavailable">Iniciar sesión</button>
        <p id="login-unavailable" className="mt-2 text-center text-[12px] leading-[18px] text-muted">El inicio de sesión aún no está disponible.</p>
        <button type="button" className="secondary-button mt-5" onClick={onRegister}>Crear cuenta</button>
      </div>
    </form>
  </section>;
}
