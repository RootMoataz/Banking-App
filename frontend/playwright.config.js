import { defineConfig } from '@playwright/test';

// Browser gates (axe accessibility + visual baselines). Separate from `npm test` (vitest).
// Set PM_E2E_PORT to use another port when 5173 is taken by a dev server from a different checkout.
const port = Number(process.env.PM_E2E_PORT) || 5173;
const origin = `http://localhost:${port}`;

export default defineConfig({
  testDir: './e2e',
  snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{arg}{ext}',
  fullyParallel: true,
  retries: 0,
  reporter: [['list']],
  expect: { toHaveScreenshot: { animations: 'disabled', maxDiffPixelRatio: 0.01 } },
  use: { baseURL: origin, browserName: 'chromium', reducedMotion: 'reduce' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1280, height: 800 } } },
    { name: 'phone', use: { viewport: { width: 390, height: 844 } } },
  ],
  webServer: { command: port === 5173 ? 'npm run dev' : `npm run dev -- --port ${port} --strictPort`, url: origin, reuseExistingServer: true, timeout: 60_000 },
});
