export default function PasswordVisibilityButton({ visible, onToggle, label = 'Contraseña' }) {
  const action = `${visible ? 'Ocultar' : 'Mostrar'} ${label.toLowerCase()}`;

  return <button
    type="button"
    className="absolute inset-y-0 right-1 my-1 grid w-10 place-items-center rounded-md text-accent hover:bg-accent-soft"
    onClick={onToggle}
    aria-label={action}
    title={action}
    aria-pressed={visible}
  >
    <svg aria-hidden="true" className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 12S6 6 12 6s9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
      <circle cx="12" cy="12" r="2.5" />
      {visible && <path d="m3 3 18 18" />}
    </svg>
  </button>;
}
