import { t } from '../i18n';
import { Brand } from './Brand';

export function AuthAside() {
  return (
    <aside className="auth-aside">
      <Brand light />
      <div>
        <h1>
          {t('Управляйте')}
          <br />
          {t('дебиторкой')}
          <br />
          <span>{t('в одном месте.')}</span>
        </h1>
        <p>{t('Счета, документы, переписка и оплаты по каждому должнику — в одном месте.')}</p>
      </div>
    </aside>
  );
}
