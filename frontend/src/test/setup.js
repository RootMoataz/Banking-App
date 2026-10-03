import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';
import { setCurrentLang } from '../i18n/core.js';

afterEach(() => {
  cleanup(); vi.unstubAllGlobals();
  // Each test starts as a first visit in English.
  try { localStorage.clear(); } catch { /* storage unavailable */ }
  setCurrentLang('en');
  document.documentElement.removeAttribute('lang');
  document.documentElement.removeAttribute('dir');
});

HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
