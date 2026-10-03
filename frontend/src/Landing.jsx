import { useEffect, useRef, useState } from 'react';
import '@fontsource/newsreader/latin-500.css';
import '@fontsource/newsreader/latin-600.css';
import './landing.css';
import logo from './assets/paper-maker-logo.webp';
import { LanguageSwitcher, useT } from './i18n';
import { DEMO_URL, money } from './ui';

// Public landing page. Pure presentation plus a client-side sample: no API calls.
// Copy lives in the dictionaries (src/i18n); these lists hold dictionary key stems only.

const navLinks = [['#features', 'features'], ['#how', 'how'], ['#security', 'security'], ['#roles', 'roles'], ['#learning', 'learning']];
const capabilities = ['records', 'multi', 'move', 'history', 'premium', 'alerts', 'audit', 'token'];
const steps = ['create', 'open', 'move'];
const controls = ['tokens', 'authz', 'throttle', 'generic', 'idem', 'audit'];
const roles = ['admin', 'customer'];

// Sample data lives in cents so the arithmetic is exact.
const START = { checking: 248000, savings: 820000 };
const START_ROWS = [
  { id: 'r1', kind: 'withdraw', cents: -8540 },
  { id: 'r2', kind: 'deposit', cents: 120000 },
];
const AMOUNTS = [5000, 10000, 25000];
const fmt = cents => money(cents / 100);
const signed = cents => `${cents < 0 ? '-' : '+'}${fmt(Math.abs(cents))}`;

function Link({ to, onNavigate, className, children }) {
  return <a className={className} href={to} onClick={event => { event.preventDefault(); onNavigate(to); }}>{children}</a>;
}

function DemoLink({ className = '' }) {
  const t = useT();
  return <a className={`landing-btn landing-btn-demo ${className}`.trim()} href={DEMO_URL} target="_blank" rel="noopener noreferrer">
    {t('landing.cta.demo')}<span className="landing-sr"> {t('common.newTab')}</span><span aria-hidden="true" className="landing-ext">↗</span>
  </a>;
}

function Preview() {
  const t = useT();
  const [checking, setChecking] = useState(START.checking);
  const [savings, setSavings] = useState(START.savings);
  const [rows, setRows] = useState(START_ROWS);
  const [amount, setAmount] = useState(10000);
  const next = useRef(3);
  const push = (kind, cents) => setRows(list => [{ id: `r${next.current++}`, kind, cents }, ...list].slice(0, 4));

  const deposit = () => { setChecking(value => value + amount); push('deposit', amount); };
  const withdraw = () => { setChecking(value => value - amount); push('withdraw', -amount); };
  const transfer = () => { setChecking(value => value - amount); setSavings(value => value + amount); push('transfer', -amount); };
  const reset = () => { setChecking(START.checking); setSavings(START.savings); setRows(START_ROWS); };
  const short = checking < amount;

  return <div className="landing-preview">
    <div className="landing-stack">
    <div className="landing-fan" aria-hidden="true">
      <div className="landing-bill landing-bill-a"><span className="landing-bill-rosette" /></div>
      <div className="landing-bill landing-bill-b"><span className="landing-bill-rosette" /></div>
    </div>
    <article className="landing-note" aria-label={t('landing.preview.label')}>
      <div className="landing-note-top">
        <span className="landing-medallion"><img src={logo} alt={t('landing.preview.mascot')} /></span>
        <div>
          <p className="landing-note-kind">{t('landing.preview.kind')}</p>
          <p className="landing-serial">PM 0042 7719</p>
        </div>
      </div>
      <dl className="landing-balances" aria-live="polite">
        <div className="landing-total"><dt>{t('landing.preview.total')}</dt><dd>{fmt(checking + savings)}</dd></div>
        <div><dt>{t('landing.preview.checking')}</dt><dd>{fmt(checking)}</dd></div>
        <div><dt>{t('landing.preview.savings')}</dt><dd>{fmt(savings)}</dd></div>
      </dl>
      <div className="landing-tape">
        <p className="landing-tape-head">{t('landing.preview.recent')}</p>
        <ul>{rows.map(row => <li key={row.id}><span>{t(`landing.row.${row.kind}`)}</span><span className={row.cents < 0 ? 'landing-debit' : 'landing-credit'}>{signed(row.cents)}</span></li>)}</ul>
      </div>
      <p className="landing-stamp" aria-hidden="true">{t('landing.preview.stamp')}</p>
    </article>
    </div>
    <div className="landing-controls" role="group" aria-label={t('landing.preview.controls')}>
      <div className="landing-amounts" role="group" aria-label={t('landing.preview.amount')}>
        {AMOUNTS.map(value => <button key={value} type="button" aria-pressed={amount === value} onClick={() => setAmount(value)}>{fmt(value)}</button>)}
      </div>
      <div className="landing-moves">
        <button type="button" onClick={deposit}>{t('landing.preview.deposit')}</button>
        <button type="button" disabled={short} onClick={withdraw}>{t('landing.preview.withdraw')}</button>
        <button type="button" disabled={short} onClick={transfer}>{t('landing.preview.transfer')}</button>
      </div>
      <p className="landing-fine">{t('landing.preview.fine')} <button type="button" className="landing-reset" onClick={reset}>{t('landing.preview.reset')}</button></p>
    </div>
  </div>;
}

export default function Landing({ onNavigate }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const toggle = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = event => { if (event.key === 'Escape') { setOpen(false); toggle.current?.focus(); } };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  return <div className="landing">
    <a className="landing-skip" href="#main">{t('common.skip')}</a>
    <header className="landing-header">
      <div className="landing-wrap landing-header-row">
        <Link to="/" onNavigate={onNavigate} className="landing-brand"><span className="landing-brand-mark"><img src={logo} alt="" /></span><span>Paper Maker</span></Link>
        <button ref={toggle} type="button" className="landing-menu" aria-expanded={open} aria-controls="landing-nav" onClick={() => setOpen(value => !value)}>
          <span className="landing-menu-bars" aria-hidden="true" /><span className="landing-sr">{t('common.menu')}</span>
        </button>
        <nav id="landing-nav" aria-label={t('landing.nav.label')} data-open={open}>
          <ul>
            {navLinks.map(([href, key]) => <li key={href}><a href={href} onClick={() => setOpen(false)}>{t(`landing.nav.${key}`)}</a></li>)}
            <li className="landing-nav-cta"><DemoLink /></li>
            <li className="landing-nav-cta"><Link to="/login" onNavigate={onNavigate} className="landing-btn landing-btn-quiet">{t('common.signIn')}</Link></li>
            <li className="landing-nav-cta"><Link to="/register" onNavigate={onNavigate} className="landing-btn landing-btn-solid">{t('landing.cta.open')}</Link></li>
            <li className="landing-nav-lang"><LanguageSwitcher id="lang-landing" /></li>
          </ul>
        </nav>
      </div>
    </header>

    <main id="main" className="landing-main">
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-wrap landing-hero-grid">
          <div className="landing-hero-copy">
            <h1 id="landing-title">{t('landing.hero.title')}</h1>
            <p className="landing-lead">{t('landing.hero.lead')}</p>
            <div className="landing-cta">
              <Link to="/register" onNavigate={onNavigate} className="landing-btn landing-btn-solid">{t('landing.cta.open')}</Link>
              <Link to="/login" onNavigate={onNavigate} className="landing-btn landing-btn-line">{t('common.signIn')}</Link>
              <DemoLink />
            </div>
            <p className="landing-fine">{t('landing.hero.fine')}</p>
          </div>
          <Preview />
        </div>
      </section>

      <section id="features" className="landing-section" aria-labelledby="features-title">
        <div className="landing-wrap">
          <h2 id="features-title">{t('landing.features.title')}</h2>
          <p className="landing-intro">{t('landing.features.intro')}</p>
          <dl className="landing-ledger">
            {capabilities.map(key => <div key={key}><dt>{t(`landing.cap.${key}.title`)}</dt><dd>{t(`landing.cap.${key}.text`)}</dd></div>)}
          </dl>
        </div>
      </section>

      <section id="how" className="landing-section landing-tint" aria-labelledby="how-title">
        <div className="landing-wrap">
          <h2 id="how-title">{t('landing.how.title')}</h2>
          <ol className="landing-steps">
            {steps.map(key => <li key={key}><h3>{t(`landing.step.${key}.title`)}</h3><p>{t(`landing.step.${key}.text`)}</p></li>)}
          </ol>
        </div>
      </section>

      <section id="security" className="landing-section landing-dark" aria-labelledby="security-title">
        <div className="landing-wrap landing-split">
          <div>
            <h2 id="security-title">{t('landing.security.title')}</h2>
            <p className="landing-intro">{t('landing.security.intro')}</p>
            <ul className="landing-checks">
              {controls.map(key => <li key={key}><strong>{t(`landing.ctl.${key}.title`)}.</strong> {t(`landing.ctl.${key}.text`)}</li>)}
            </ul>
          </div>
          <aside className="landing-disclaimer" aria-labelledby="not-title">
            <h3 id="not-title">{t('landing.not.title')}</h3>
            <p>{t('landing.not.text')}</p>
          </aside>
        </div>
      </section>

      <section id="roles" className="landing-section" aria-labelledby="roles-title">
        <div className="landing-wrap">
          <h2 id="roles-title">{t('landing.roles.title')}</h2>
          <div className="landing-roles">
            {roles.map(key => <section key={key} aria-label={t(`landing.role.${key}.name`)}>
              <h3>{t(`landing.role.${key}.name`)}</h3><p className="landing-role-line">{t(`landing.role.${key}.line`)}</p>
              <ul>{[1, 2, 3, 4].map(n => <li key={n}>{t(`landing.role.${key}.item${n}`)}</li>)}</ul>
            </section>)}
          </div>
        </div>
      </section>

      <section id="learning" className="landing-section landing-tint" aria-labelledby="learning-title">
        <div className="landing-wrap landing-learn">
          <span className="landing-seal-wrap"><img src={logo} alt="" className="landing-seal" /></span>
          <div>
            <h2 id="learning-title">{t('landing.learning.title')}</h2>
            <p>{t('landing.learning.text')}</p>
            <div className="landing-cta">
              <Link to="/register" onNavigate={onNavigate} className="landing-btn landing-btn-solid">{t('landing.cta.open')}</Link>
              <Link to="/login" onNavigate={onNavigate} className="landing-btn landing-btn-line">{t('common.signIn')}</Link>
              <DemoLink />
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer className="landing-footer">
      <div className="landing-wrap landing-footer-row">
        <p>{t('landing.footer.text')}</p>
        <ul>
          <li><Link to="/login" onNavigate={onNavigate}>{t('common.signIn')}</Link></li>
          <li><Link to="/register" onNavigate={onNavigate}>{t('landing.cta.open')}</Link></li>
        </ul>
      </div>
    </footer>
  </div>;
}
