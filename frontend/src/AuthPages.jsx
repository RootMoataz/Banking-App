import { useEffect, useState } from 'react';
import { useAuth } from './auth';
import logo from './assets/paper-maker-logo.webp';
import { LanguageSwitcher, useI18n } from './i18n';
import { DEMO_URL, SLOW_AFTER_MS } from './ui';

const passwordRule = 'Use 8 to 72 characters.'; // English key text; shown translated through errorText
const passwordBytes = value => new TextEncoder().encode(value).length;

function AuthShell({ title, children, footer }) {
  const { t } = useI18n();
  return <main id="main" className="auth">
    <div className="auth-art">
      <span className="brand-mark"><img src={logo} alt="" /></span>
      <span className="brand-name">Paper Maker</span>
      <p className="auth-tag">{t('auth.tag')}</p>
      <p className="auth-serial" aria-hidden="true">PM 0042 7719</p>
    </div>
    <div className="auth-side">
      <LanguageSwitcher id="lang-auth" className="auth-lang" />
      <section className="panel auth-card" aria-labelledby="auth-title"><h1 id="auth-title">{title}</h1>{children}<p className="auth-foot">{footer}</p></section>
    </div>
  </main>;
}

// Lockout notice. Re-renders only inside <Remaining/>: once a minute, then every second in the final minute.
// The live region announces minute changes; the per-second digits are hidden from screen readers.
const remainingSeconds = (until, now) => Math.max(0, Math.ceil((until - now) / 1000));
function Remaining({ until, onDone }) {
  const { t } = useI18n();
  const [now, setNow] = useState(() => Date.now());
  const seconds = remainingSeconds(until, now);
  useEffect(() => {
    if (seconds <= 0) { onDone(); return undefined; }
    const wait = seconds > 60 ? (seconds - 60 * Math.floor((seconds - 1) / 60)) * 1000 : 1000;
    const timer = setTimeout(() => setNow(Date.now()), wait);
    return () => clearTimeout(timer);
  }, [seconds, now, until, onDone]);
  if (seconds >= 60) return <>{t('auth.lockout.minutes', { count: Math.ceil(seconds / 60) })}</>;
  return <><span aria-hidden="true">{t('auth.lockout.seconds', { count: seconds })}</span><span className="sr-only">{t('auth.lockout.lessThanMinute')}</span></>;
}

function Lockout({ lock, onDone }) {
  const { t } = useI18n();
  if (!lock) return null;
  return <p role="status" className="lockout">{lock.until === null
    ? t('auth.lockout.unknown')
    : t('auth.lockout.until', { time: <Remaining until={lock.until} onDone={onDone} /> })}</p>;
}

function useSubmit(action) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [lock, setLock] = useState(null);
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!busy) { setSlow(false); return undefined; }
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => clearTimeout(timer);
  }, [busy]);
  const unlock = () => setLock(null);
  async function submit(event, validate) {
    event.preventDefault();
    if (busy) return;
    const problem = validate?.();
    if (problem) { setError(problem); return; }
    setBusy(true); setError(''); setLock(null);
    try { await action(); } catch (err) {
      if (err.status === 429) { setLock({ until: err.retryAfter ? Date.now() + err.retryAfter * 1000 : null }); }
      else setError(err.message);
      setBusy(false);
    }
  }
  return { busy, error, submit, slow, lock, unlock, locked: Boolean(lock?.until) };
}

const pageLink = (path, text, onNavigate) => <a href={path} onClick={event => { event.preventDefault(); onNavigate(path); }}>{text}</a>;

export function Login({ onNavigate }) {
  const { t, errorText } = useI18n();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const { busy, error, submit, slow, lock, unlock, locked } = useSubmit(() => login(email.trim(), password));
  return <AuthShell title={t('auth.signIn.title')} footer={t('auth.signIn.foot', { link: pageLink('/register', t('auth.signIn.footLink'), onNavigate) })}>
    {error && <p role="alert" className="error">{errorText(error)}</p>}
    <Lockout lock={lock} onDone={unlock} />
    <form onSubmit={submit}><fieldset disabled={busy}>
      <label htmlFor="email">{t('common.email')}</label>
      <input id="email" type="email" autoFocus required maxLength={100} autoComplete="username" value={email} onChange={event => setEmail(event.target.value)} />
      <label htmlFor="password">{t('common.password')}</label>
      <input id="password" type="password" required autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} />
      <div className="actions"><button type="submit" disabled={locked}>{busy ? t('auth.signIn.busy') : t('auth.signIn.submit')}</button></div>
      <p className="wake-note" aria-live="polite">{busy && slow ? t('common.wake') : ''}</p>
    </fieldset></form>
    <p className="demo-note">{t('auth.signIn.demo', { link: <a href={DEMO_URL} target="_blank" rel="noopener noreferrer">{t('auth.signIn.demoLink')}<span className="sr-only"> {t('common.newTab')}</span></a> })}</p>
  </AuthShell>;
}

export function Register({ onNavigate }) {
  const { t, errorText } = useI18n();
  const { register } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const { busy, error, submit, slow, lock, unlock, locked } = useSubmit(() => register(name.trim(), email.trim(), password));
  const validate = () => { const size = passwordBytes(password); return size < 8 || size > 72 ? passwordRule : ''; };
  return <AuthShell title={t('auth.register.title')} footer={t('auth.register.foot', { link: pageLink('/login', t('auth.register.footLink'), onNavigate) })}>
    {error && <p role="alert" className="error">{errorText(error)}</p>}
    <Lockout lock={lock} onDone={unlock} />
    <form onSubmit={event => submit(event, validate)}><fieldset disabled={busy}>
      <label htmlFor="name">{t('common.name')}</label>
      <input id="name" autoFocus required maxLength={100} pattern=".*\S.*" autoComplete="name" value={name} onChange={event => setName(event.target.value)} />
      <label htmlFor="email">{t('common.email')}</label>
      <input id="email" type="email" required maxLength={100} autoComplete="username" value={email} onChange={event => setEmail(event.target.value)} />
      <label htmlFor="password">{t('common.password')}</label>
      <input id="password" type="password" required autoComplete="new-password" aria-describedby="password-help" value={password} onChange={event => setPassword(event.target.value)} />
      <p id="password-help">{t('auth.passwordHelp')}</p>
      <div className="actions"><button type="submit" disabled={locked}>{busy ? t('auth.register.busy') : t('auth.register.submit')}</button></div>
      <p className="wake-note" aria-live="polite">{busy && slow ? t('common.wake') : ''}</p>
    </fieldset></form>
  </AuthShell>;
}
