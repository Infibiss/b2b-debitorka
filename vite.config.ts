import { defineConfig, normalizePath } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  root: 'web',
  plugins: [
    react(),
    {
      name: 'local-font-preloads',
      apply: 'serve',
      // The dev root is web/, while dependencies live one directory above it.
      transformIndexHtml(html, context) {
        if (!context.server) return html;
        const root = normalizePath(context.server.config.root);
        const dependencies = `${root.slice(0, root.lastIndexOf('/'))}/node_modules/`;
        return html.replaceAll('href="../node_modules/', `href="/@fs/${dependencies}`);
      },
    },
  ],
  build: { outDir: 'dist', sourcemap: false },
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8000' } },
  preview: { port: 4173 },
});
