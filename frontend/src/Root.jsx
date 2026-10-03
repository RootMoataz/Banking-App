import { useEffect, useState } from 'react';
import App from './App';
import { Login, Register } from './AuthPages';
import Landing from './Landing';
import { AccessDenied, MyAccounts, Profile, Transfer } from './CustomerPages';
import { AuthProvider, useAuth } from './auth';
import { I18nProvider, useT } from './i18n';
import Shell from './Shell';
import { Loading } from './ui';

const adminPaths = ['/', '/customers', '/premium'];
const adminNav = [['/', 'customers', 'users'], ['/premium', 'premium', 'star']];
const customerNav = [['/accounts', 'myAccounts', 'wallet'], ['/transfer', 'transfer', 'swap'], ['/profile', 'profile', 'person']];
const customerPages = { '/accounts': MyAccounts, '/transfer': Transfer, '/profile': Profile };

// Role guards are UX only; the server enforces access.
function resolve(path, user) {
  if (!user) {
    if (path === '/login' || path === '/register') return path;
    return path in customerPages || adminPaths.includes(path) && path !== '/' ? '/login' : '/';
  }
  if (path in customerPages || (adminPaths.includes(path) && path !== '/')) return path;
  return user.role === 'ADMIN' ? '/' : '/accounts';
}

const navItems = (nav, current, navigate, t) => nav.map(([path, key, icon]) => ({ label: t(`nav.${key}`), icon, current: current === path, onSelect: () => navigate(path) }));

function Routes() {
  const t = useT();
  const { user, loading, logout } = useAuth();
  const [path, setPath] = useState(window.location.pathname);
  const navigate = (next, replace = false) => {
    window.history[replace ? 'replaceState' : 'pushState'](null, '', next); setPath(next);
  };
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  const effective = resolve(path, user);
  useEffect(() => { if (!loading && effective !== path) navigate(effective, true); });
  // A distinct document title per screen, so screen reader users hear where they are.
  useEffect(() => {
    const names = { '/': user ? 'customers' : 'landing', '/customers': 'customers', '/premium': 'premium', '/accounts': 'myAccounts', '/transfer': 'transfer', '/profile': 'profile', '/login': 'signIn', '/register': 'register' };
    document.title = `${t(`title.${names[effective] || 'notAvailable'}`)} | Paper Maker`;
  }, [effective, user, t]);
  if (loading) return <main id="main" className="boot"><Loading /></main>;
  if (!user) {
    if (effective === '/register') return <Register onNavigate={navigate} />;
    return effective === '/login' ? <Login onNavigate={navigate} /> : <Landing onNavigate={navigate} />;
  }
  if (user.role === 'ADMIN') {
    if (adminPaths.includes(effective)) return <App key={effective} initialView={effective === '/premium' ? 'premium' : undefined} onSignOut={logout} />;
    return <Shell items={navItems(adminNav, effective, navigate, t)} onSignOut={logout}><AccessDenied /></Shell>;
  }
  const Page = customerPages[effective] || AccessDenied;
  return <Shell items={navItems(customerNav, effective, navigate, t)} onSignOut={logout}><Page /></Shell>;
}

export default function Root() {
  return <I18nProvider><AuthProvider><Routes /></AuthProvider></I18nProvider>;
}
