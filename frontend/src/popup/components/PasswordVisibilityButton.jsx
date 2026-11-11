export default function PasswordVisibilityButton({ visible, onToggle, label = 'Contraseña' }) {
  const action = `${visible ? 'Ocultar' : 'Mostrar'} ${label.toLowerCase()}`;

  return <button
    type="button"
    className="password-toggle"
    onClick={onToggle}
    aria-label={action}
    title={action}
    aria-pressed={visible}
  >
    <svg aria-hidden="true" className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square" strokeLinejoin="miter">
      <path d="M2 12l5-5h10l5 5-5 5H7z" />
      <path d="M10 10h4v4h-4z" />
      {visible && <path d="m3 3 18 18" />}
    </svg>
  </button>;
}
