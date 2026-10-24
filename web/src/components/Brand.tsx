export function Brand({ light = false }: { light?: boolean }) {
  return (
    <a
      className={`brand brand-mandato ${light ? 'brand-light' : ''}`}
      href="/"
      aria-label="Mandato — на главную"
    >
      <svg className="mandato-mark" viewBox="0 0 32 32" fill="currentColor" aria-hidden="true">
        <path d="M4 26V7h4l8 10L24 7h4v19h-5V16l-7 9-7-9v10Z" />
      </svg>
      <span>mandato</span>
    </a>
  );
}
