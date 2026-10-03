import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import Root from './Root';
import { DICTIONARIES, LANGUAGES, STORAGE_KEY, detectLang, initialLang, translate, translateError } from './i18n/core.js';
import { dateTime, money, shortDate } from './ui';

const en = DICTIONARIES.en;
const others = LANGUAGES.map(item => item.code).filter(code => code !== 'en');
const forms = value => (typeof value === 'string' ? [value] : Object.values(value));
const placeholders = value => [...new Set(forms(value).flatMap(text => [...text.matchAll(/\{(\w+)\}/g)].map(match => match[1])))].sort();

it.each(others)('%s has exactly the keys of English, none empty, with the same placeholders', code => {
  const dict = DICTIONARIES[code];
  expect(Object.keys(dict).filter(key => !(key in en))).toEqual([]);
  expect(Object.keys(en).filter(key => !(key in dict))).toEqual([]);
  for (const [key, value] of Object.entries(dict)) {
    expect(typeof value, key).toBe(typeof en[key]);
    for (const text of forms(value)) expect(text.trim(), key).not.toBe('');
    if (typeof value === 'object') expect(value.other, key).toBeTruthy();
    // Forms such as "one minute" may leave out the count, so compare what each language uses with English.
    expect(placeholders(value).filter(name => !placeholders(en[key]).includes(name)), key).toEqual([]);
    if (typeof value === 'string') expect(placeholders(value), key).toEqual(placeholders(en[key]));
  }
});

it('English itself has no empty strings', () => {
  for (const [key, value] of Object.entries(en)) for (const text of forms(value)) expect(text.trim(), key).not.toBe('');
});

it('interpolates, picks plural forms per language and falls back to English, then to the key', () => {
  expect(translate('en', 'customers.deleteTitle', { name: 'Ada' })).toBe('Delete Ada?');
  expect(translate('en', 'customers.caption', { count: 1 })).toBe('1 customer');
  expect(translate('en', 'customers.caption', { count: 3 })).toBe('3 customers');
  expect(translate('ar', 'auth.lockout.minutes', { count: 2 })).toBe('دقيقتين');
  expect(translate('ar', 'auth.lockout.minutes', { count: 5 })).toBe('5 دقائق');
  expect(translate('de', 'nonexistent.key')).toBe('nonexistent.key');
  expect(translate('xx', 'common.cancel')).toBe('Cancel');
});

it('chooses the first supported browser language by primary subtag, else English', () => {
  expect(detectLang({ languages: ['fr-CA', 'en'] })).toBe('fr');
  expect(detectLang({ languages: ['pt-BR', 'de-AT'] })).toBe('de');
  expect(detectLang({ languages: ['ja'], language: 'ja' })).toBe('en');
  expect(detectLang({ languages: [] })).toBe('en');
});

it('prefers the stored language and survives storage that throws', () => {
  localStorage.setItem(STORAGE_KEY, 'es');
  expect(initialLang()).toBe('es');
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
  expect(() => initialLang()).not.toThrow();
  vi.restoreAllMocks();
});

it('starts from the browser language on a first visit and sets lang and dir', async () => {
  vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['ar-EG']);
  vi.stubGlobal('fetch', vi.fn());
  render(<Root />);
  expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('كل إيداع');
  expect(document.documentElement.lang).toBe('ar');
  expect(document.documentElement.dir).toBe('rtl');
  expect(document.title).toContain('Paper Maker');
  vi.restoreAllMocks();
});

it('switches language without a reload, remembers it, and sets lang, dir and the title', async () => {
  const user = userEvent.setup();
  vi.stubGlobal('fetch', vi.fn());
  render(<Root />);
  await screen.findByRole('heading', { level: 1, name: /every deposit/i });
  expect(document.documentElement.lang).toBe('en');
  expect(document.documentElement.dir).toBe('ltr');
  const select = screen.getByRole('combobox', { name: 'Language' });
  expect(within(select).getAllByRole('option').map(option => option.textContent)).toEqual(['English', 'العربية', 'Français', 'Español', 'Deutsch']);
  await user.selectOptions(select, 'de');
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Jede Einzahlung');
  expect(screen.getByRole('combobox', { name: 'Sprache' })).toHaveValue('de');
  expect(localStorage.getItem(STORAGE_KEY)).toBe('de');
  expect(document.documentElement.lang).toBe('de');
  expect(document.title).toBe('Bankgeschäfte, sichtbar gemacht | Paper Maker');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Sprache' }), 'ar');
  expect(document.documentElement.dir).toBe('rtl');
  expect(document.documentElement.style.getPropertyValue('--t-error')).toBe('"خطأ. "');
});

it('maps known server messages to the current language and leaves unknown ones as they came', () => {
  expect(translateError('fr', 'Invalid email or password')).toBe(translate('fr', 'err.invalidLogin'));
  expect(translateError('de', 'Too many failed login attempts, try again later')).toBe(translate('de', 'err.tooManyLogins'));
  expect(translateError('es', 'You can only open accounts for yourself')).toBe(translate('es', 'err.openForSelf'));
  expect(translateError('ar', 'Request failed (503). Please try again.')).toContain('503');
  expect(translateError('de', 'Unable to reach the server. Check your connection and try again. The result is unknown. Check your balances and history before submitting again.'))
    .toBe(`${translate('de', 'err.network')} ${translate('de', 'err.unknownResultOwn')}`);
  expect(translateError('de', 'Something new from the server')).toBe('Something new from the server');
  expect(translateError('en', 'Insufficient funds')).toBe('Insufficient funds');
});

it('shows a translated login error and keeps it in step with a language change', async () => {
  const user = userEvent.setup();
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 401, headers: new Headers(), json: async () => ({ detail: 'Invalid email or password' }) })));
  window.history.replaceState(null, '', '/login');
  render(<Root />);
  await user.type(await screen.findByLabelText('Email'), 'a@b.co');
  await user.type(screen.getByLabelText('Password'), 'whatever1');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'fr');
  expect(screen.getByRole('alert')).toHaveTextContent('E-mail ou mot de passe incorrect');
});

it('keeps Western digits in every language, with separators and months of the language', () => {
  expect(money(1234.5, 'en')).toBe('1,234.50');
  expect(money(1234.5, 'de')).toBe('1.234,50');
  expect(money(-1234.5, 'es')).toBe('-1.234,50');
  expect(money(1234.5, 'fr')).toMatch(/^1\s234,50$/);
  for (const lang of LANGUAGES.map(item => item.code)) {
    expect(money(9876543.21, lang), lang).toMatch(/^[0-9.,\s  -]+$/);
    expect(shortDate('2026-10-01T12:00:00Z', lang), lang).not.toMatch(/[٠-٩۰-۹]/);
    expect(dateTime('2026-10-01T12:00:00Z', lang), lang).toMatch(/\d{2}:\d{2}$/);
  }
  expect(money(-5, 'ar')).toBe('-5.00');
  expect(money(1234.5, 'ar')).toBe('1,234.50');
  expect(shortDate('2026-10-01T12:00:00Z', 'ar')).toMatch(/^\d{1,2} أكتوبر 2026$/);
  expect(shortDate('2026-10-01T12:00:00Z', 'de')).toMatch(/^\d{1,2}\. Okt\. 2026$/);
  expect(money(null, 'ar')).toBe('—');
});
