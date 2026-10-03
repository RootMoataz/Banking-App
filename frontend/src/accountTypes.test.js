import { expect, it } from 'vitest';
import { ACCOUNT_TYPES, accountTypeLabel } from './accountTypes';
import { translate } from './i18n/core.js';

it('translates known types per language and returns unknown or legacy values untouched', () => {
  expect(ACCOUNT_TYPES).toEqual(['Checking', 'Savings', 'Current', 'Business', 'Student']);
  const t = lang => key => translate(lang, key);
  expect(accountTypeLabel(t('en'), 'Savings')).toBe('Savings');
  expect(accountTypeLabel(t('de'), 'Savings')).toBe('Sparkonto');
  expect(accountTypeLabel(t('ar'), 'Student')).toBe('حساب طالب');
  expect(accountTypeLabel(t('de'), 'SAVINGS')).toBe('SAVINGS');
  expect(accountTypeLabel(t('de'), 'Legacy Gold')).toBe('Legacy Gold');
});
