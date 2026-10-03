import { useEffect, useRef, useState } from 'react';
import '@fontsource/newsreader/latin-500.css';
import '@fontsource/newsreader/latin-600.css';
import './landing.css';
import logo from './assets/paper-maker-logo.webp';
import { money } from './ui';

// Public landing page. Pure presentation plus a client-side sample: no API calls.

const navLinks = [['#features', 'What it does'], ['#how', 'How it works'], ['#security', 'Controls'], ['#roles', 'Roles'], ['#learning', 'Learning']];

const capabilities = [
  ['Customer records', 'Administrators add, edit and delete customers.'],
  ['More than one account', 'A customer can hold several accounts, each with its own balance and history.'],
  ['Deposit, withdraw, transfer', 'Money moves between accounts. Transfers carry an idempotency key, so a repeated submit does not move money twice.'],
  ['Transaction history', 'Every account lists its entries, newest first, with the balance after each one.'],
  ['Premium list', 'Administrators get a separate view of premium accounts.'],
  ['Category alerts', 'Notifications are raised for account activity by category.'],
  ['Audit records', 'Sensitive actions leave an audit record of what happened.'],
  ['Sign in with a token', 'Login issues a JWT. Accounts are either ADMIN or CUSTOMER.'],
];

const steps = [
  ['Create a login', 'Register with a name, an email and a password of 8 to 72 characters.'],
  ['Open accounts', 'Open one account or several, and see each balance on its own card.'],
  ['Move money, read the tape', 'Transfer between accounts, then check the history line by line.'],
];

const controls = [
  ['Signed tokens', 'Each request carries a JWT that identifies who is asking.'],
  ['Server-side authorization', 'Screens hide what you cannot use, but the server makes the final decision for every request.'],
  ['Login throttling', 'After 5 failed sign-ins an email is locked for 15 minutes.'],
  ['One generic login error', 'A failed sign-in does not reveal whether the email exists.'],
  ['Idempotency keys', 'A retried transfer is recognised instead of applied twice.'],
  ['Audit records', 'Sensitive actions are recorded for later review.'],
];

const roles = [
  ['Administrator', 'Runs the books', ['Adds, edits and deletes customers', 'Opens accounts for customers', 'Deposits and withdraws', 'Sees the premium accounts list']],
  ['Customer', 'Sees only their own', ['Views their own accounts and history', 'Opens another account', 'Transfers between accounts', 'Reads a read-only profile']],
];

// Sample data lives in cents so the arithmetic is exact.
const START = { checking: 248000, savings: 820000 };
const START_ROWS = [
  { id: 'r1', label: 'Withdrawal', cents: -8540 },
  { id: 'r2', label: 'Deposit', cents: 120000 },
];
const AMOUNTS = [5000, 10000, 25000];
const fmt = cents => money(cents / 100);
const signed = cents => `${cents < 0 ? '-' : '+'}${fmt(Math.abs(cents))}`;

function Link({ to, onNavigate, className, children }) {
  return <a className={className} href={to} onClick={event => { event.preventDefault(); onNavigate(to); }}>{children}</a>;
}

function Preview() {
  const [checking, setChecking] = useState(START.checking);
  const [savings, setSavings] = useState(START.savings);
  const [rows, setRows] = useState(START_ROWS);
  const [amount, setAmount] = useState(10000);
  const next = useRef(3);
  const push = (label, cents) => setRows(list => [{ id: `r${next.current++}`, label, cents }, ...list].slice(0, 4));

  const deposit = () => { setChecking(value => value + amount); push('Deposit', amount); };
  const withdraw = () => { setChecking(value => value - amount); push('Withdrawal', -amount); };
  const transfer = () => { setChecking(value => value - amount); setSavings(value => value + amount); push('Transfer to Savings', -amount); };
  const reset = () => { setChecking(START.checking); setSavings(START.savings); setRows(START_ROWS); };
  const short = checking < amount;

  return <div className="landing-preview">
    <article className="landing-note" aria-label="Sample account preview">
      <div className="landing-note-top">
        <span className="landing-medallion"><img src={logo} alt="Paper Maker mascot, a top-hatted banker holding a fan of banknotes" /></span>
        <div>
          <p className="landing-note-kind">Sample account</p>
          <p className="landing-serial">PM 0042 7719</p>
        </div>
      </div>
      <dl className="landing-balances" aria-live="polite">
        <div className="landing-total"><dt>Total balance</dt><dd>{fmt(checking + savings)}</dd></div>
        <div><dt>Checking</dt><dd>{fmt(checking)}</dd></div>
        <div><dt>Savings</dt><dd>{fmt(savings)}</dd></div>
      </dl>
      <div className="landing-tape">
        <p className="landing-tape-head">Recent activity</p>
        <ul>{rows.map(row => <li key={row.id}><span>{row.label}</span><span className={row.cents < 0 ? 'landing-debit' : 'landing-credit'}>{signed(row.cents)}</span></li>)}</ul>
      </div>
      <p className="landing-stamp" aria-hidden="true">Sample</p>
    </article>
    <div className="landing-controls" role="group" aria-label="Try the sample account">
      <div className="landing-amounts" role="group" aria-label="Amount">
        {AMOUNTS.map(value => <button key={value} type="button" aria-pressed={amount === value} onClick={() => setAmount(value)}>{fmt(value)}</button>)}
      </div>
      <div className="landing-moves">
        <button type="button" onClick={deposit}>Deposit</button>
        <button type="button" disabled={short} onClick={withdraw}>Withdraw</button>
        <button type="button" disabled={short} onClick={transfer}>Transfer to Savings</button>
      </div>
      <p className="landing-fine">Sample data in your browser. Nothing is sent anywhere. <button type="button" className="landing-reset" onClick={reset}>Reset</button></p>
    </div>
  </div>;
}

export default function Landing({ onNavigate }) {
  const [open, setOpen] = useState(false);
  const toggle = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = event => { if (event.key === 'Escape') { setOpen(false); toggle.current?.focus(); } };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  return <div className="landing">
    <a className="landing-skip" href="#main">Skip to content</a>
    <header className="landing-header">
      <div className="landing-wrap landing-header-row">
        <Link to="/" onNavigate={onNavigate} className="landing-brand"><span className="landing-brand-mark"><img src={logo} alt="" /></span><span>Paper Maker</span></Link>
        <button ref={toggle} type="button" className="landing-menu" aria-expanded={open} aria-controls="landing-nav" onClick={() => setOpen(value => !value)}>
          <span className="landing-menu-bars" aria-hidden="true" /><span className="landing-sr">Menu</span>
        </button>
        <nav id="landing-nav" aria-label="Primary" data-open={open}>
          <ul>
            {navLinks.map(([href, label]) => <li key={href}><a href={href} onClick={() => setOpen(false)}>{label}</a></li>)}
            <li className="landing-nav-cta"><Link to="/login" onNavigate={onNavigate} className="landing-btn landing-btn-quiet">Sign in</Link></li>
            <li className="landing-nav-cta"><Link to="/register" onNavigate={onNavigate} className="landing-btn landing-btn-solid">Open an account</Link></li>
          </ul>
        </nav>
      </div>
    </header>

    <main id="main" className="landing-main">
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-wrap landing-hero-grid">
          <div className="landing-hero-copy">
            <h1 id="landing-title">Every deposit, transfer and rule in plain sight.</h1>
            <p className="landing-lead">Paper Maker is a small banking app built for learning. Open a sample account, move money between accounts, and read the history line by line.</p>
            <div className="landing-cta">
              <Link to="/register" onNavigate={onNavigate} className="landing-btn landing-btn-solid">Open an account</Link>
              <Link to="/login" onNavigate={onNavigate} className="landing-btn landing-btn-line">Sign in</Link>
            </div>
            <p className="landing-fine">An educational project. No real money moves.</p>
          </div>
          <Preview />
        </div>
      </section>

      <section id="features" className="landing-section" aria-labelledby="features-title">
        <div className="landing-wrap">
          <h2 id="features-title">What the app does</h2>
          <p className="landing-intro">Everything here is implemented and running against the same API you sign in to.</p>
          <dl className="landing-ledger">
            {capabilities.map(([term, text]) => <div key={term}><dt>{term}</dt><dd>{text}</dd></div>)}
          </dl>
        </div>
      </section>

      <section id="how" className="landing-section landing-tint" aria-labelledby="how-title">
        <div className="landing-wrap">
          <h2 id="how-title">How it works</h2>
          <ol className="landing-steps">
            {steps.map(([title, text]) => <li key={title}><h3>{title}</h3><p>{text}</p></li>)}
          </ol>
        </div>
      </section>

      <section id="security" className="landing-section landing-dark" aria-labelledby="security-title">
        <div className="landing-wrap landing-split">
          <div>
            <h2 id="security-title">Controls that exist today</h2>
            <p className="landing-intro">A short, honest list of what the code actually does.</p>
            <ul className="landing-checks">
              {controls.map(([title, text]) => <li key={title}><strong>{title}.</strong> {text}</li>)}
            </ul>
          </div>
          <aside className="landing-disclaimer" aria-labelledby="not-title">
            <h3 id="not-title">What this is not</h3>
            <p>Not a real bank. Not regulated or insured. No real money, cards or payments. It is a learning project, so use a throwaway password and never one you use elsewhere.</p>
          </aside>
        </div>
      </section>

      <section id="roles" className="landing-section" aria-labelledby="roles-title">
        <div className="landing-wrap">
          <h2 id="roles-title">Two roles, two views</h2>
          <div className="landing-roles">
            {roles.map(([name, line, items]) => <section key={name} aria-label={name}>
              <h3>{name}</h3><p className="landing-role-line">{line}</p>
              <ul>{items.map(item => <li key={item}>{item}</li>)}</ul>
            </section>)}
          </div>
        </div>
      </section>

      <section id="learning" className="landing-section landing-tint" aria-labelledby="learning-title">
        <div className="landing-wrap landing-learn">
          <img src={logo} alt="" className="landing-seal" />
          <div>
            <h2 id="learning-title">A place to learn, and to break things</h2>
            <p>Register with any email, open a few accounts and try the transfers. Read the request, the response and the history. The point is to see how a banking system holds together.</p>
            <div className="landing-cta">
              <Link to="/register" onNavigate={onNavigate} className="landing-btn landing-btn-solid">Open an account</Link>
              <Link to="/login" onNavigate={onNavigate} className="landing-btn landing-btn-line">Sign in</Link>
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer className="landing-footer">
      <div className="landing-wrap landing-footer-row">
        <p>An educational banking application. Not a real bank.</p>
        <ul>
          <li><Link to="/login" onNavigate={onNavigate}>Sign in</Link></li>
          <li><Link to="/register" onNavigate={onNavigate}>Open an account</Link></li>
        </ul>
      </div>
    </footer>
  </div>;
}
