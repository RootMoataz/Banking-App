import { useEffect, useRef, useState } from 'react';
import { useAuth } from './auth';
import logo from './assets/paper-maker-logo.webp';
import { LanguageSwitcher, useT } from './i18n';
import { Icon, initials } from './ui';

// Signed-in frame: top bar, left navigation (a sheet under 900px) and the page.
// items: [{ label, icon, current, disabled, onSelect }]
export default function Shell({ items, onSignOut, children }) {
  const t = useT();
  const user = useAuth()?.user;
  const [open, setOpen] = useState(false);
  const roleKey = `role.${user?.role}`;
  const roleName = t(roleKey) === roleKey ? user?.role : t(roleKey); // an unknown role is shown as the server names it
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
    <a className="skip-link" href="#main">{t('common.skip')}</a>
    <header className="topbar">
      <button ref={menuButton} type="button" className="menu-button" aria-label={t('common.menu')} aria-expanded={open} aria-controls="primary-nav" onClick={() => setOpen(value => !value)}><span aria-hidden="true" /></button>
      <div className="brand"><span className="brand-mark"><img src={logo} alt="" /></span><span className="brand-name">Paper Maker</span></div>
      <div className="topbar-end">
        <LanguageSwitcher id="lang-topbar" className="on-dark lang-wide" />
        {user && <div className="who"><span className="monogram" aria-hidden="true">{initials(user.name)}</span><span className="who-text"><span className="who-name">{user.name}</span><span className="who-role">{roleName}</span></span></div>}
      </div>
    </header>
    <div className="scrim" data-open={open} onClick={() => setOpen(false)} aria-hidden="true" />
    <nav id="primary-nav" ref={nav} aria-label={t('nav.main')} data-open={open}>
      <div className="nav-items">
        {items.map(item => <button key={item.icon} type="button" disabled={item.disabled} aria-current={item.current ? 'page' : undefined} onClick={() => { setOpen(false); item.onSelect(); }}><Icon name={item.icon} />{item.label}</button>)}
      </div>
      <div className="nav-foot">
        <LanguageSwitcher id="lang-drawer" className="lang-narrow" />
        {onSignOut && <button type="button" className="signout" onClick={onSignOut}><Icon name="out" />{t('nav.signOut')}</button>}
      </div>
    </nav>
    <div className="page">
      <main id="main">{children}</main>
      <footer>{t('shell.footer')}</footer>
    </div>
  </div>;
}
