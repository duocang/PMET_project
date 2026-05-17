// Playwright config — focused on the admin E2E walkthrough. We assume
// the dev server is already running on :3000 against the live backend
// on :5960 (the test:e2e script can start it for you). No CI parallelism
// because most specs touch shared state (audit log, admin token,
// settings JSON) and would race.

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.PMET_E2E_BASE_URL ?? 'http://localhost:3000',
    trace: 'retain-on-failure',
    actionTimeout: 5_000,
    navigationTimeout: 15_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
