import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { expect, test } from '@playwright/test';
import { admin, customer, mockApi, settle } from './mock-api.js';

// Review screenshots go to the temp folder, not into the baselines.
const OUT = join(tmpdir(), 'papermaker-i18n');
mkdirSync(OUT, { recursive: true });
const LANGS = ['en', 'ar', 'fr', 'es', 'de'];
const useLang = (page, lang) => page.addInitScript(code => localStorage.setItem('pm.lang', code), lang);

for (const lang of ['ar', 'de']) {
  test(`landing in ${lang}: screenshot, direction and no sideways scroll`, async ({ page }, info) => {
    await mockApi(page);
    await useLang(page, lang);
    await page.goto('/');
    await page.getByRole('heading', { level: 1 }).waitFor();
    await settle(page);
    await expect(page.locator('html')).toHaveAttribute('lang', lang);
    await expect(page.locator('html')).toHaveAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: join(OUT, `landing-${lang}-${info.project.name}.png`), fullPage: true });
    await page.screenshot({ path: join(OUT, `landing-${lang}-${info.project.name}-top.png`) });
  });
}

// Every language keeps the landing header on one line when the links show, and switches to the menu button when they do not fit.
for (const lang of LANGS) {
  for (const width of [1181, 1280, 1440]) {
    test(`landing header in ${lang} at ${width}px stays on one line`, async ({ page }, info) => {
      test.skip(info.project.name !== 'desktop', 'width is set by the test');
      await mockApi(page);
      await useLang(page, lang);
      await page.setViewportSize({ width, height: 800 });
      await page.goto('/');
      await page.getByRole('heading', { level: 1 }).waitFor();
      await settle(page);
      const menuShown = await page.locator('.landing-menu').isVisible();
      if (!menuShown) {
        const row = await page.locator('.landing-header-row').boundingBox();
        expect(row.height).toBeLessThan(90);
        const middles = await page.locator('.landing-header nav ul > li').evaluateAll(items => items.map(item => { const box = item.getBoundingClientRect(); return box.top + box.height / 2; }));
        expect(Math.max(...middles) - Math.min(...middles)).toBeLessThan(4);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      if (width === 1280) await page.screenshot({ path: join(OUT, `header-${lang}-${width}.png`), clip: { x: 0, y: 0, width, height: 110 } });
    });
  }
}

test('the language switcher on the landing page changes the page without a reload and is remembered', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await page.getByRole('heading', { level: 1 }).waitFor();
  if (await page.locator('.landing-menu').isVisible()) await page.locator('.landing-menu').click();
  await page.getByLabel('Language').selectOption('de');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Jede Einzahlung');
  expect(await page.evaluate(() => localStorage.getItem('pm.lang'))).toBe('de');
  await page.reload();
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Jede Einzahlung');
});

// Wide tables and long labels in the longest languages must not push the page sideways.
for (const lang of ['de', 'fr', 'ar']) {
  for (const [name, user, path, ready] of [
    ['admin customers', admin, '/', page => page.getByRole('table').waitFor()],
    ['customer accounts', customer, '/accounts', page => page.getByRole('table').waitFor()],
    ['customer transfer', customer, '/transfer', page => page.locator('#from-account').waitFor()],
  ]) {
    test(`${name} in ${lang}: screenshot and no sideways scroll`, async ({ page }, info) => {
      await mockApi(page, user);
      await useLang(page, lang);
      await page.goto(path);
      await ready(page);
      await settle(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.screenshot({ path: join(OUT, `${name.replace(' ', '-')}-${lang}-${info.project.name}.png`), fullPage: true });
    });
  }
}
