/// <reference types="vite/client" />
import React, { lazy, Suspense } from 'react';
import { createRoot, hydrateRoot } from 'react-dom/client';
import '@fontsource-variable/onest';
import { language, loadLanguage, t } from './i18n';

// Screens call `t` while their modules load, so translations must arrive first.
void loadLanguage().then(async () => {
  const container = document.getElementById('root')!;
  if (!location.pathname.startsWith('/app')) {
    const { PublicSite } = await import('./components/PublicSite');
    document.documentElement.classList.toggle('landing-page', location.pathname === '/');
    const page = (
      <React.StrictMode>
        <PublicSite />
      </React.StrictMode>
    );
    // Prerendered pages are hydrated in place so the intro does not restart.
    if (container.hasChildNodes() && language === 'ru') hydrateRoot(container, page);
    else {
      container.textContent = '';
      createRoot(container).render(page);
    }
    return;
  }
  const root = createRoot(container);
  const Workspace = lazy(async () => {
    const [{ Workspace }] = await Promise.all([
      import('./components/Workspace'),
      import('./styles.css'),
      import('./design-system.css'),
    ]);
    return { default: Workspace };
  });
  root.render(
    <React.StrictMode>
      <Suspense
        fallback={
          <main role="status" style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
            {t('Загрузка кабинета…')}
          </main>
        }
      >
        <Workspace />
      </Suspense>
    </React.StrictMode>
  );
});
