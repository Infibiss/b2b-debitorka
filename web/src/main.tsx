/// <reference types="vite/client" />
import React, { lazy, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/manrope';
import { loadLanguage, t } from './i18n';

// Screens call `t` while their modules load, so translations must arrive first.
void loadLanguage().then(async () => {
  const root = createRoot(document.getElementById('root')!);
  if (!location.pathname.startsWith('/app')) {
    const { PublicSite } = await import('./components/PublicSite');
    root.render(
      <React.StrictMode>
        <PublicSite />
      </React.StrictMode>
    );
    return;
  }
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
