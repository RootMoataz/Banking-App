import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { DEMO_ACCOUNTS, DEMO_PASSWORD } from './demo.js';

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8');
const demoMd = read('../../DEMO.md');
const seed = read('../../deploy/seed_demo.py');
const emailsIn = text => [...new Set(text.match(/demo-[a-z]+@example\.com/g))].sort();

it('uses the password from DEMO.md and seed_demo.py', () => {
  expect(demoMd.match(/same password: `([^`]+)`/)?.[1]).toBe(DEMO_PASSWORD);
  expect(seed.match(/^DEMO_PASSWORD = "([^"]+)"/m)?.[1]).toBe(DEMO_PASSWORD);
});

it('lists the same emails as DEMO.md and seed_demo.py', () => {
  const emails = DEMO_ACCOUNTS.map(account => account.email).sort();
  expect(emailsIn(demoMd)).toEqual(emails);
  expect(emailsIn(seed)).toEqual(emails);
});

it('lists the same roles as the DEMO.md table', () => {
  for (const { email, role } of DEMO_ACCOUNTS) {
    const row = demoMd.split('\n').find(line => line.startsWith(`| \`${email}\``));
    expect(row?.split('|')[2].trim()).toBe(role);
  }
});
