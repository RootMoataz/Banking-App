import { useEffect, useRef, useState } from 'react';
import { useAuth } from './auth';
import logo from './assets/paper-maker-logo.png';
import { initials } from './ui';

const roleLabel = { ADMIN: 'Administrator', CUSTOMER: 'Customer' };

// Signed-in frame: top bar, left navigation (a sheet under 900px) and the page.
// items: [{ label, current, disabled, onSelect }]
export default function Shell({ items, onSignOut, children }) {
  const user = useAuth()?.user;
  const [open, setOpen] = useState(false);
  const menuButton = useRef(null);
  const nav = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = event => { if (event.key === 'Escape') { setOpen(false); menuButton.current?.focus(); } };
    document.addEventListener('keydown', onKey);
    nav.current?.querySelector('button')?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  return <div className="shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <header className="topbar">
      <button ref={menuButton} type="button" className="menu-button" aria-label="Menu" aria-expanded={open} aria-controls="primary-nav" onClick={() => setOpen(value => !value)}><span aria-hidden="true" /></button>
      <div className="brand"><span className="brand-mark"><img src={logo} alt="" /></span><span className="brand-name">Paper Maker</span></div>
      {user && <div className="who"><span className="monogram" aria-hidden="true">{initials(user.name)}</span><span className="who-text"><span className="who-name">{user.name}</span><span className="who-role">{roleLabel[user.role] || user.role}</span></span></div>}
    </header>
    <div className="scrim" data-open={open} onClick={() => setOpen(false)} aria-hidden="true" />
    <nav id="primary-nav" ref={nav} aria-label="Main navigation" data-open={open}>
      <div className="nav-items">
        {items.map(item => <button key={item.label} type="button" disabled={item.disabled} aria-current={item.current ? 'page' : undefined} onClick={() => { setOpen(false); item.onSelect(); }}>{item.label}</button>)}
      </div>
      {onSignOut && <button type="button" className="signout" onClick={onSignOut}>Sign out</button>}
    </nav>
    <div className="page">
      <main id="main">{children}</main>
      <footer>Paper Maker Banking. Amounts are shown without a currency symbol.</footer>
    </div>
  </div>;
}
