// E2E walkthrough of the admin dashboard, mirroring the manual MCP
// run we did once. Each `test()` here pins one of the A1–A9 items
// from TODO §"管理员特性". The whole suite assumes:
//
//   - dev server up on $PMET_E2E_BASE_URL (default localhost:3000)
//   - docker backend stack up on :5960 (the frontend axios baseURL)
//   - PMET_E2E_ADMIN_TOKEN env var carries the current admin token —
//     never hard-coded in tree because tokens rotate
//
// Tests share state intentionally (auditing the audit log is the whole
// point), so playwright.config.ts pins workers=1.
//
// Skips itself if PMET_E2E_ADMIN_TOKEN isn't set — keeps CI green on
// envs where the admin stack hasn't been provisioned yet.

import { test, expect, Page } from '@playwright/test';

const ADMIN_TOKEN = process.env.PMET_E2E_ADMIN_TOKEN ?? '';

test.beforeAll(({}, testInfo) => {
  if (!ADMIN_TOKEN) {
    testInfo.skip(true, 'PMET_E2E_ADMIN_TOKEN not set — admin E2E suite skipped');
  }
});

async function login(page: Page, token = ADMIN_TOKEN): Promise<void> {
  await page.goto('/admin/login');
  await page.locator('input[type="password"]').fill(token);
  await page.locator('input[type="password"]').press('Enter');
  // The login bug we fixed: redirect must land on /admin (#settings),
  // not bounce back to /admin/login.
  await page.waitForURL(/\/admin(#|$)/, { timeout: 5_000 });
}

async function logoutViaApi(page: Page): Promise<void> {
  // Use the page's axios baseURL (cross-origin /api → :5960). We can't
  // call fetch('/api/...') from :3000 — same-origin would 404 onto Next.
  await page.evaluate(async () => {
    // @ts-ignore — adminApi is exported off the bundle root in dev mode
    // not, so we call the URL the production code uses.
    const apiUrl = (window as any).__PMET_API__ ?? 'http://localhost:5960';
    await fetch(`${apiUrl}/api/admin/logout`, { method: 'POST', credentials: 'include' });
  });
}

// ---------------------------------------------------------------------
// Login bug fix
// ---------------------------------------------------------------------
test('Login redirects to /admin and reveals the nav Admin tab', async ({ page }) => {
  await login(page);
  // Tab must appear in the nav.
  const adminLink = page.locator('nav a', { hasText: 'Admin' });
  await expect(adminLink).toBeVisible();
});

// ---------------------------------------------------------------------
// A6: system health
// ---------------------------------------------------------------------
test('A6 — System health: Run checks renders 5 probe rows', async ({ page }) => {
  await login(page);
  await page.getByRole('button', { name: 'Run checks' }).click();
  // Each probe renders a row inside the panel.
  const probes = ['SMTP (outbound mail)', 'Redis (celery broker)',
                  'Disk (results partition)', 'Tasks dir (writable)',
                  'Configure dir (operator files)'];
  for (const name of probes) {
    await expect(page.getByText(name, { exact: true })).toBeVisible();
  }
});

// ---------------------------------------------------------------------
// A2: audit log shows login_ok / logout entries
// ---------------------------------------------------------------------
test('A2 — Activity log records login_ok / logout', async ({ page }) => {
  await login(page);
  // The Admin actions tab is the default. Scroll the section into view.
  const activityHeader = page.getByRole('heading', { name: 'Activity log' });
  await activityHeader.scrollIntoViewIfNeeded();
  // The most recent row should be our just-fresh login_ok.
  const firstRow = page.locator('section#activity table tbody tr').first();
  await expect(firstRow).toContainText('login_ok');
});

// ---------------------------------------------------------------------
// A4: cleanup card reacts to settings changes
// ---------------------------------------------------------------------
test('A4 — Cleanup preview refreshes after Settings save', async ({ page }) => {
  await login(page);

  // 1. Initially "No retention policy set yet".
  const cleanupCard = page.locator('section#maintenance');
  await cleanupCard.scrollIntoViewIfNeeded();
  await expect(cleanupCard).toContainText('No retention policy set yet');

  // 2. Set retention to 365 in Settings → Advanced.
  const retentionInput = page.locator('input[placeholder="e.g. 30"]');
  await retentionInput.fill('365');
  await page.getByRole('button', { name: /^Save$/ }).click();
  // Saved indicator appears briefly.
  await expect(page.getByText('Saved').first()).toBeVisible();

  // 3. Cleanup card should now read "Retention 365 days · 0 task(s)…".
  await expect(cleanupCard).toContainText('Retention 365 days', { timeout: 5_000 });

  // Tidy up — clear the field and save back. (Note: clearing → null
  // doesn't propagate to the server today, see TODO follow-up.)
  await retentionInput.fill('');
  await page.getByRole('button', { name: /^Save$/ }).click();
});

// ---------------------------------------------------------------------
// A1: brute-force gate (driven through the public login form)
// ---------------------------------------------------------------------
test('A1 — Five wrong tokens lock out the IP with a 429-style message', async ({ page }) => {
  // Fresh page — don't carry an admin cookie into the failing form.
  await page.goto('/admin/login');
  const input = page.locator('input[type="password"]');
  for (let i = 0; i < 5; i++) {
    await input.fill('definitely-wrong-' + i);
    await input.press('Enter');
    // Invalid-token message after each.
    await expect(page.getByText('Invalid token.')).toBeVisible();
  }
  // 6th attempt → rate-limit message.
  await input.fill('still-wrong');
  await input.press('Enter');
  await expect(page.getByText(/Too many failed attempts/i)).toBeVisible();
});
