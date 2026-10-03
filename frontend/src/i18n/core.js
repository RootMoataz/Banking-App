import { Fragment, createElement } from 'react';
import ar from './ar.js';
import de from './de.js';
import en from './en.js';
import es from './es.js';
import fr from './fr.js';

// Small i18n layer, no dependency. English (en.js) is the source of truth and the fallback for any missing key.
// A value is a string with {name} placeholders, or a plural object ({ one, other, ... }) chosen by params.count.

export const LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'ar', name: 'العربية' },
  { code: 'fr', name: 'Français' },
  { code: 'es', name: 'Español' },
  { code: 'de', name: 'Deutsch' },
];
export const DICTIONARIES = { en, ar, fr, es, de };
export const STORAGE_KEY = 'pm.lang';
export const isSupported = code => Object.prototype.hasOwnProperty.call(DICTIONARIES, code);
export const dirOf = lang => (lang === 'ar' ? 'rtl' : 'ltr');

// The language the shared formatters (money, dates) use. The provider keeps it in step with the UI.
let current = 'en';
export const getLang = () => current;
export const setCurrentLang = lang => { if (isSupported(lang)) current = lang; };

export function readStoredLang() {
  try { const stored = localStorage.getItem(STORAGE_KEY); return isSupported(stored) ? stored : null; } catch { return null; }
}
export function storeLang(lang) {
  try { localStorage.setItem(STORAGE_KEY, lang); } catch { /* storage unavailable */ }
}

// First visit: the first browser language whose primary subtag we support (fr-CA -> fr), else English.
export function detectLang(nav = typeof navigator === 'undefined' ? null : navigator) {
  const wanted = [...(nav?.languages || []), nav?.language].filter(Boolean);
  for (const tag of wanted) {
    const primary = String(tag).toLowerCase().split('-')[0];
    if (isSupported(primary)) return primary;
  }
  return 'en';
}
export const initialLang = () => readStoredLang() || detectLang();

function pick(value, lang, params) {
  if (typeof value !== 'object' || value === null) return value;
  const count = Number(params?.count);
  let form = 'other';
  try { form = new Intl.PluralRules(lang).select(Number.isFinite(count) ? count : 0); } catch { /* unsupported locale */ }
  return value[form] ?? value.other;
}

// Replaces {name} placeholders. If a param is not a string or number (for example a link element),
// the result is an array of strings and elements that React can render.
export function interpolate(text, params) {
  if (!params) return text;
  const parts = text.split(/\{(\w+)\}/);
  let rich = false;
  const out = parts.map((part, index) => {
    if (index % 2 === 0) return part;
    if (!(part in params)) return `{${part}}`;
    const value = params[part];
    if (typeof value === 'string' || typeof value === 'number') return String(value);
    rich = true;
    return createElement(Fragment, { key: index }, value);
  });
  return rich ? out : out.join('');
}

export function translate(lang, key, params) {
  const value = DICTIONARIES[lang]?.[key] ?? en[key];
  if (value === undefined) return key;
  const text = pick(value, DICTIONARIES[lang]?.[key] === undefined ? 'en' : lang, params);
  return interpolate(text, params);
}

// API errors arrive from the server in English. Known messages are mapped by their exact text.
// Anything else is shown as it came.
const ERROR_KEYS = {
  'Invalid email or password': 'err.invalidLogin',
  'Too many failed login attempts, try again later': 'err.tooManyLogins',
  'A user with this email already exists': 'err.userExists',
  'A customer with this email already exists': 'err.customerExists',
  'You can only open accounts for yourself': 'err.openForSelf',
  'You can only transfer from your own accounts': 'err.transferOwn',
  'This action is only for bank staff': 'err.staffOnly',
  'Customer not found': 'err.customerNotFound',
  'Account not found': 'err.accountNotFound',
  'Source account not found': 'err.sourceNotFound',
  'Destination account not found': 'err.destinationNotFound',
  'Insufficient funds': 'err.insufficientFunds',
  'Balance would exceed 99999999.99': 'err.balanceLimit',
  'Withdraw the remaining balance before deleting the account': 'err.withdrawFirst',
  'Idempotency-Key was already used for a different request': 'err.idempotencyReuse',
  'fromAccountId and toAccountId must be different accounts': 'err.sameAccount',
  'Missing, invalid or expired token': 'err.badToken',
  'Not authenticated': 'err.badToken',
  'Unable to reach the server. Check your connection and try again.': 'err.network',
  'Your session has expired. Please sign in again.': 'err.sessionExpired',
  'The server returned an invalid response. Please try again.': 'err.invalidResponse',
  'Enter a positive amount up to 99999999.99 with at most two decimal places.': 'err.amountInvalid',
  'Choose two different accounts.': 'err.chooseTwo',
  'Select an account type.': 'err.accountType',
  'Choose your account and a different destination account.': 'err.chooseOwnAndOther',
  'Use 8 to 72 characters.': 'auth.passwordRule',
  'Enter your first name.': 'auth.firstNameRequired',
  'Enter your last name.': 'auth.lastNameRequired',
  'First name must be 50 characters or fewer.': 'auth.firstNameTooLong',
  'Last name is too long. Use 50 characters or fewer, and no more than 100 for both names together.': 'auth.lastNameTooLong',
  'First name cannot be only digits.': 'auth.firstNameInvalid',
  'Last name cannot be only digits.': 'auth.lastNameInvalid',
  'The result is unknown. Check account balances and history before submitting again.': 'err.unknownResultAccounts',
  'The result is unknown. Check your balances and history before submitting again.': 'err.unknownResultOwn',
};

export function translateError(lang, message) {
  if (typeof message !== 'string' || !message) return message;
  const key = ERROR_KEYS[message];
  if (key) return translate(lang, key);
  const failed = /^Request failed \((\d+)\)\. Please try again\.$/.exec(message);
  if (failed) return translate(lang, 'err.requestFailed', { status: failed[1] });
  // "<known message> <known sentence>", as when a network failure leaves a money operation unconfirmed.
  for (const [english, tail] of Object.entries(ERROR_KEYS)) {
    if (message.endsWith(` ${english}`) && english.startsWith('The result is unknown')) {
      return `${translateError(lang, message.slice(0, -english.length - 1))} ${translate(lang, tail)}`;
    }
  }
  return message;
}
