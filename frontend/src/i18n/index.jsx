import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import { LANGUAGES, dirOf, initialLang, isSupported, setCurrentLang, storeLang, translate, translateError } from './core.js';

export { LANGUAGES } from './core.js';

const make = (lang, setLang) => ({
  lang, dir: dirOf(lang), setLang,
  t: (key, params) => translate(lang, key, params),
  errorText: message => translateError(lang, message),
});
// Without a provider (isolated component tests) everything is English.
const I18nContext = createContext(make('en', () => {}));

// Strings that CSS pseudo-elements print (the error label, card captions) are handed over as custom properties.
const CSS_STRINGS = { '--t-error': 'css.error', '--t-owner': 'css.owner', '--t-balance': 'css.balance', '--t-opened': 'css.opened' };
const useIsoLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect;

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(initialLang);
  setCurrentLang(lang);
  const setLang = useCallback(next => {
    if (!isSupported(next)) return;
    storeLang(next);
    setCurrentLang(next);
    setLangState(next);
  }, []);
  const value = useMemo(() => make(lang, setLang), [lang, setLang]);

  useIsoLayoutEffect(() => {
    const root = document.documentElement;
    root.lang = lang;
    root.dir = dirOf(lang);
    for (const [name, key] of Object.entries(CSS_STRINGS)) root.style.setProperty(name, JSON.stringify(translate(lang, key)));
  }, [lang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export const useI18n = () => useContext(I18nContext);
export const useT = () => useContext(I18nContext).t;

// Native select, each language in its own name. `className` picks the ground it sits on.
export function LanguageSwitcher({ id, className = '' }) {
  const { lang, setLang, t } = useI18n();
  return <span className={`lang-switch ${className}`.trim()}>
    <select id={id} aria-label={t('lang.label')} value={lang} onChange={event => setLang(event.target.value)}>
      {LANGUAGES.map(item => <option key={item.code} value={item.code} lang={item.code}>{item.name}</option>)}
    </select>
  </span>;
}
