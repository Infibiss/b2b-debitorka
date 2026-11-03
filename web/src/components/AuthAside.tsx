import { Brand } from './Brand';

export function AuthAside() {
  return (
    <aside className="auth-aside">
      <Brand light />
      <div>
        <h1>
          Управляйте
          <br />
          дебиторкой
          <br />
          <span>в одном месте.</span>
        </h1>
        <p>Счета, документы, переписка и оплаты — в делах ваших клиентов.</p>
      </div>
    </aside>
  );
}
