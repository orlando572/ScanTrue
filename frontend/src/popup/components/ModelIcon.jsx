// Icono vectorial de cada modelo, compartido por el desglose (P06) y las pruebas (P09).
export default function ModelIcon({ model }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square" strokeLinejoin="miter">
    {model === 'bilstm' ? <><path d="M7 6h10M7 18h10M5 8v8M19 8v8M7 7l10 10M17 7 7 17" /><rect x="3" y="3" width="4" height="4" /><rect x="17" y="3" width="4" height="4" /><rect x="3" y="17" width="4" height="4" /><rect x="17" y="17" width="4" height="4" /></>
      : <><path d="M12 2l9 5v10l-9 5-9-5V7z" /><path d="M12 7v10M7.5 9.5l9 5M16.5 9.5l-9 5" /><rect x="10.5" y="10.5" width="3" height="3" fill="currentColor" stroke="none" /></>}
  </svg>;
}
