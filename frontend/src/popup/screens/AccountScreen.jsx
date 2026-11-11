import { useCallback, useEffect, useRef, useState } from 'react';
import { sendExtensionMessage } from '../extension-message.js';
import ScreenHeader from '../components/ScreenHeader.jsx';

function AccountIcon() {
  return <div className="account-art" aria-hidden="true"><svg viewBox="0 0 112 112" fill="none" stroke="currentColor" strokeLinecap="square">
    <circle cx="56" cy="56" r="52" stroke="#1E3A5C" />
    <circle className="account-art-ring" cx="56" cy="56" r="46" stroke="#38E1FF" strokeOpacity=".7" strokeDasharray="18 10 4 10" />
    <path d="M56 0v10M56 102v10M0 56h10M102 56h10" stroke="#FFB21E" strokeWidth="1.5" />
    <path d="M56 26l11 11-11 11-11-11z" strokeWidth="2.2" />
    <path d="M34 82v-8l10-10h24l10 10v8" strokeWidth="2.2" />
    <path d="M30 30h8M30 30v8M82 30h-8M82 30v8M30 86h8M30 86v-8M82 86h-8M82 86v-8" stroke="#FF3D7F" strokeWidth="1.5" />
  </svg></div>;
}

export default function AccountScreen({ notice, noticeMs = 6000, onBack, onLogin, onRegister, onSignedOut, onSigningOutChange }) {
  const [status, setStatus] = useState('loading');
  const [account, setAccount] = useState(null);
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState('');
  const loading = useRef(false);
  const signOutLock = useRef(false);
  const mounted = useRef(false);

  const load = useCallback(async () => {
    if (loading.current) return;
    loading.current = true;
    setStatus('loading');
    try {
      const response = await sendExtensionMessage({ type: 'GET_ACCOUNT_STATE' });
      if (!mounted.current) return;
      if (!response?.ok || !response.account?.kind) throw new Error('No pudimos consultar tu cuenta.');
      setAccount(response.account);
      setStatus('ready');
    } catch {
      if (mounted.current) setStatus('error');
    } finally { loading.current = false; }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => { mounted.current = false; };
  }, [load]);

  const signOut = async () => {
    if (signOutLock.current) return;
    signOutLock.current = true;
    setSigningOut(true);
    onSigningOutChange(true);
    setSignOutError('');
    try {
      const response = await sendExtensionMessage({ type: 'CLOSE_ACCOUNT_SESSION' });
      if (!response?.ok || response.signedOut !== true) throw new Error(response?.error ?? 'No pudimos cerrar la sesión.');
      if (mounted.current) {
        setAccount({ kind: 'none', email: null });
        onSignedOut();
      }
    } catch (error) {
      if (mounted.current) setSignOutError(error?.message === 'Espera a que termine el análisis para cerrar sesión.'
        ? error.message : 'No pudimos cerrar la sesión. Inténtalo de nuevo.');
    } finally {
      signOutLock.current = false;
      onSigningOutChange(false);
      if (mounted.current) setSigningOut(false);
    }
  };

  return <section className="flex flex-1 flex-col">
    <ScreenHeader title="Cuenta" onBack={onBack} disabled={signingOut} />

    {notice?.text && <div key={notice.text} className={`hud-panel hud-panel--amber mt-5${notice.autoHide ? ' notice-timed' : ''}`} style={{ '--notice-ms': `${noticeMs}ms` }} role="status">
      <span className="hud-code" aria-hidden="true">Mensaje del sistema</span>
      <p className="notice-panel mt-1">{notice.text}</p>
      {notice.autoHide && <span className="notice-timer" aria-hidden="true" />}
    </div>}

    {status === 'loading' && <p className="hud-readout mt-6" role="status">Cargando cuenta…</p>}
    {status === 'error' && <div className="mt-6" role="alert"><p className="text-sm text-muted">No pudimos consultar tu cuenta.</p><button type="button" className="secondary-button mt-5" onClick={load}>Intentar de nuevo</button></div>}

    {status === 'ready' && <>
      <div className="flex flex-1 flex-col items-center justify-center py-8 text-center">
        <AccountIcon />
        {account.kind === 'account' ? <>
          <p className="account-status mt-6">Sesión iniciada</p>
          {account.email && <p className="hud-readout mt-3 break-all text-[13px]">{account.email}</p>}
        </> : account.kind === 'pending_confirmation' ? <>
          <p className="account-status mt-6">Revisa tu correo para confirmar la cuenta</p>
          {account.email && <p className="hud-readout mt-3 break-all text-[13px]">{account.email}</p>}
          <p className="mt-2 text-sm leading-5 text-muted">Puedes seguir usando ScanTrue como invitado.</p>
        </> : account.kind === 'guest' ? <p className="account-status mt-6">Estás usando ScanTrue como invitado</p>
          : account.kind === 'none' ? <p className="account-status mt-6">Puedes usar ScanTrue como invitado</p>
            : account.kind === 'expired' ? <p className="account-status mt-6">No pudimos renovar tu sesión</p>
              : <p className="account-status mt-6">No pudimos confirmar tu sesión</p>}
      </div>

      <div className="pt-6">
        {account.kind === 'account' ? <>
          {signOutError && <p className="hud-alert mb-3 text-sm leading-5" role="alert">{signOutError}</p>}
          <button type="button" className="secondary-button delete-button" onClick={signOut} disabled={signingOut}>{signingOut ? 'Cerrando sesión…' : 'Cerrar sesión'}</button>
        </> : account.kind === 'expired' || account.kind === 'unknown' ? <>
          <button type="button" className="primary-button" onClick={load}>Intentar de nuevo</button>
          <button type="button" className="secondary-button mt-3" onClick={onLogin}>Iniciar sesión</button>
        </> : <>
          <button type="button" className="primary-button" onClick={onLogin}>Iniciar sesión</button>
          {account.kind !== 'pending_confirmation' && <button type="button" className="secondary-button mt-3" onClick={onRegister}>Crear cuenta</button>}
        </>}
      </div>
    </>}
  </section>;
}
