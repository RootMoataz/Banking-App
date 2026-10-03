import { expect, test } from '@playwright/test';
import { admin, customer, mockApi, settle } from './mock-api.js';

// Baselines are per project (desktop / phone). Viewport only, not full page, to keep the PNGs small.
async function shot(page, name, clip) {
  await settle(page);
  await expect(page).toHaveScreenshot(`${name}.png`, clip ? { clip: { x: 0, y: 0, ...page.viewportSize(), ...clip } } : {});
}

test('landing', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await page.getByRole('heading', { level: 1 }).waitFor();
  // The hero is a fine pattern that compresses poorly, so only the top-left corner (header and headline) is captured.
  await shot(page, 'landing', { width: Math.min(640, page.viewportSize().width), height: 420 });
});

test('login', async ({ page }) => {
  await mockApi(page);
  await page.goto('/login');
  await page.getByRole('heading', { name: 'Sign in' }).waitFor();
  await shot(page, 'login');
});

test('admin customers', async ({ page }) => {
  await mockApi(page, admin);
  await page.goto('/');
  await page.getByRole('table').waitFor();
  await shot(page, 'admin-customers');
});

test('customer accounts', async ({ page }) => {
  await mockApi(page, customer);
  await page.goto('/accounts');
  await page.getByRole('table').waitFor();
  await shot(page, 'customer-accounts');
});
