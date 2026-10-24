import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  outputDir: './e2e/results',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { outputFolder: 'e2e/report', open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:8001',
    // APIRequestContext has no browser-generated Origin. Keep the real Origin
    // guard enabled and send the same allowed origin as the browser frontend.
    extraHTTPHeaders: { Origin: 'http://127.0.0.1:8001' },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } },
    },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: {
    command: 'python3 e2e/run_server.py',
    url: 'http://127.0.0.1:8001/api/health',
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
