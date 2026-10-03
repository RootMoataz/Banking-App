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
  ['premium list', admin, '/premium', page => page.getByRole('table').waitFor()],
  ['admin delete dialog', admin, '/', async page => {
    await page.getByRole('button', { name: 'Delete Ben Carter' }).click();
    await page.getByRole('alertdialog').waitFor();
  }],
  ['customer my accounts', customer, '/accounts', page => page.getByRole('table').waitFor()],
  ['customer transfer', customer, '/transfer', page => page.getByLabel('From account').waitFor()],
  ['customer profile', customer, '/profile', page => page.getByRole('heading', { name: 'Profile' }).waitFor()],
];

for (const [name, user, path, prepare] of screens) {
  test(`axe: ${name}`, async ({ page }) => {
    await mockApi(page, user);
    await page.goto(path);
    await prepare(page);
    await audit(page);
  });
}
