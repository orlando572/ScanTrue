import { useCallback, useEffect, useRef, useState } from 'react';
import { sendExtensionMessage } from '../extension-message.js';

function AccountIcon() {
  return <div className="account-art" aria-hidden="true"><svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><circle cx="32" cy="20" r="9" /><path d="M13 55c0-11 8.5-18 19-18s19 7 19 18" /></svg></div>;
}

export default function AccountScreen({ notice, onBack, onLogin, onRegister, onSignedOut, onSigningOutChange }) {
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
    <div className="flex items-start gap-3">
      <button type="button" className="breakdown-back" aria-label="Volver" title="Volver" onClick={onBack} disabled={signingOut}>
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m14 5-7 7 7 7" /></svg>
      </button>
      <h1 className="text-[22px] leading-7 font-semibold tracking-[-0.03em]">Cuenta</h1>
    </div>

    {notice && <p className="mt-5 rounded-lg border border-line bg-white p-3 text-sm leading-5 text-ink" role="status">{notice}</p>}

    {status === 'loading' && <p className="mt-6 text-sm text-muted" role="status">Cargando cuenta…</p>}
    {status === 'error' && <div className="mt-6" role="alert"><p className="text-sm text-muted">No pudimos consultar tu cuenta.</p><button type="button" className="secondary-button mt-5" onClick={load}>Intentar de nuevo</button></div>}

    {status === 'ready' && <>
      <div className="mt-10 flex flex-col items-center text-center">
        <AccountIcon />
        {account.kind === 'account' ? <>
          <p className="mt-5 text-base font-semibold">Sesión iniciada</p>
          {account.email && <p className="mt-2 break-all text-sm text-muted">{account.email}</p>}
        </> : account.kind === 'pending_confirmation' ? <>
          <p className="mt-5 text-base font-semibold">Revisa tu correo para confirmar la cuenta</p>
          {account.email && <p className="mt-2 break-all text-sm text-muted">{account.email}</p>}
          <p className="mt-2 text-sm leading-5 text-muted">Puedes seguir usando ScanTrue como invitado.</p>
        </> : account.kind === 'guest' ? <p className="mt-5 text-base font-semibold">Estás usando ScanTrue como invitado</p>
          : account.kind === 'none' ? <p className="mt-5 text-base font-semibold">Puedes usar ScanTrue como invitado</p>
            : account.kind === 'expired' ? <p className="mt-5 text-base font-semibold">No pudimos renovar tu sesión</p>
              : <p className="mt-5 text-base font-semibold">No pudimos confirmar tu sesión</p>}
      </div>

      <div className="mt-auto pt-10">
        {account.kind === 'account' ? <>
          {signOutError && <p className="mb-3 text-sm leading-5 text-false" role="alert">{signOutError}</p>}
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
