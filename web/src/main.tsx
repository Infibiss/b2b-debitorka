import React from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/manrope';
import { Landing } from './components/Landing';
import { Workspace } from './components/Workspace';
import './styles.css';
import './design-system.css';
createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {location.pathname.startsWith('/app') ? <Workspace /> : <Landing />}
  </React.StrictMode>
);
