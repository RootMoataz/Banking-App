import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { admin, customer, mockApi, settle } from './mock-api.js';

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21aa'];

async function audit(page) {
  await settle(page);
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(violations.map(item => `${item.id}: ${item.nodes.map(node => node.target.join(' ')).join(' | ')}`)).toEqual([]);
}

const screens = [
  ['landing', null, '/', async () => {}],
  ['login', null, '/login', async () => {}],
  ['register', null, '/register', async () => {}],
  ['admin customers list', admin, '/', page => page.getByRole('table').waitFor()],
  ['admin customer accounts', admin, '/', async page => {
    await page.getByRole('button', { name: 'Accounts for Asha Rao' }).click();
    await page.getByRole('table').waitFor();
  }],
  ['admin open account form', admin, '/', async page => {
    await page.getByRole('button', { name: 'Accounts for Asha Rao' }).click();
    await page.getByRole('table').waitFor();
    await page.getByRole('button', { name: 'Open account' }).click();
    await page.getByLabel('Account type').waitFor();
  }],
  ['customer open account form', customer, '/accounts', async page => {
    await page.getByRole('table').waitFor();
    await page.getByRole('button', { name: 'Open account' }).click();
    await page.getByLabel('Account type').waitFor();
  }],
  ['premium list', admin, '/premium', page => page.getByRole('table').waitFor()],
  ['admin delete dialog', admin, '/', async page => {
    await page.getByRole('button', { name: 'Delete Ben Carter' }).click();
    await page.getByRole('alertdialog').waitFor();
  }],
  ['customer my accounts', customer, '/accounts', page => page.getByRole('table').waitFor()],
  ['customer transfer', customer, '/transfer', page => page.getByLabel('From account').waitFor()],
  ['customer profile', customer, '/profile', page => page.getByRole('heading', { name: 'Profile' }).waitFor()],
];

// The public pages again in Arabic (right to left) and German (longest words).
for (const lang of ['ar', 'de']) {
  for (const [name, path] of [['landing', '/'], ['login', '/login']]) {
    test(`axe: ${name} in ${lang}`, async ({ page }) => {
      await mockApi(page);
      await page.addInitScript(code => localStorage.setItem('pm.lang', code), lang);
      await page.goto(path);
      await page.locator(`html[lang="${lang}"] h1`).first().waitFor();
      await audit(page);
    });
  }
}

for (const [name, user, path, prepare] of screens) {
  test(`axe: ${name}`, async ({ page }) => {
    await mockApi(page, user);
    await page.goto(path);
    await prepare(page);
    await audit(page);
  });
}
