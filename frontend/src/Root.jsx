import { useEffect, useState } from 'react';
import App from './App';
import { Login, Register } from './AuthPages';
import Landing from './Landing';
import { AccessDenied, MyAccounts, Profile, Transfer } from './CustomerPages';
import { AuthProvider, useAuth } from './auth';
import Shell from './Shell';

const adminPaths = ['/', '/customers', '/premium'];
const adminNav = [['/', 'Customers'], ['/premium', 'Premium accounts']];
const customerNav = [['/accounts', 'My accounts'], ['/transfer', 'Transfer'], ['/profile', 'Profile']];
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

const navItems = (nav, current, navigate) => nav.map(([path, label]) => ({ label, current: current === path, onSelect: () => navigate(path) }));

function Routes() {
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
  if (loading) return <main id="main" className="boot"><p className="loading-note">Loading…</p></main>;
  if (!user) {
    if (effective === '/register') return <Register onNavigate={navigate} />;
    return effective === '/login' ? <Login onNavigate={navigate} /> : <Landing onNavigate={navigate} />;
  }
  if (user.role === 'ADMIN') {
    if (adminPaths.includes(effective)) return <App key={effective} initialView={effective === '/premium' ? 'premium' : undefined} onSignOut={logout} />;
    return <Shell items={navItems(adminNav, effective, navigate)} onSignOut={logout}><AccessDenied /></Shell>;
  }
  const Page = customerPages[effective] || AccessDenied;
  return <Shell items={navItems(customerNav, effective, navigate)} onSignOut={logout}><Page /></Shell>;
}

export default function Root() {
  return <AuthProvider><Routes /></AuthProvider>;
}
