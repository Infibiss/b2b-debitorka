/// <reference types="vite/client" />
import React, { lazy, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/manrope';
import { PublicSite } from './components/PublicSite';
const Workspace = lazy(async () => {
  const [{ Workspace }] = await Promise.all([
    import('./components/Workspace'),
    import('./styles.css'),
    import('./design-system.css'),
  ]);
  return { default: Workspace };
});
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {location.pathname.startsWith('/app') ? (
      <Suspense
        fallback={
          <main role="status" style={{ padding: '2rem', fontFamily: 'sans-serif' }}>
            Загрузка кабинета…
          </main>
        }
      >
        <Workspace />
      </Suspense>
    ) : (
      <PublicSite />
    )}
  </React.StrictMode>
);
