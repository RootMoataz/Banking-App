import { useState } from 'react';
import { useAuth } from './auth';
import logo from './assets/paper-maker-logo.png';

const passwordRule = 'Use 8 to 72 characters.';
const passwordBytes = value => new TextEncoder().encode(value).length;

function AuthShell({ title, children, footer }) {
  return <main id="main" className="auth">
    <div className="auth-brand"><span className="brand-mark"><img src={logo} alt="" /></span><span className="brand-name">Paper Maker</span></div>
    <section className="panel auth-card" aria-labelledby="auth-title"><h1 id="auth-title">{title}</h1>{children}</section>
    <p className="auth-foot">{footer}</p>
  </main>;
}

function useSubmit(action) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event, validate) {
    event.preventDefault();
    if (busy) return;
    const problem = validate?.();
    if (problem) { setError(problem); return; }
    setBusy(true); setError('');
    try { await action(); } catch (err) { setError(err.message); setBusy(false); }
  }
  return { busy, error, submit };
}

export function Login({ onNavigate }) {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const { busy, error, submit } = useSubmit(() => login(email.trim(), password));
  return <AuthShell title="Sign in" footer={<>New here? <a href="/register" onClick={event => { event.preventDefault(); onNavigate('/register'); }}>Create an account</a></>}>
    {error && <p role="alert" className="error">{error}</p>}
    <form onSubmit={submit}><fieldset disabled={busy}>
      <label htmlFor="email">Email</label>
      <input id="email" type="email" autoFocus required maxLength={100} autoComplete="username" value={email} onChange={event => setEmail(event.target.value)} />
      <label htmlFor="password">Password</label>
      <input id="password" type="password" required autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} />
      <div className="actions"><button type="submit">{busy ? 'Signing in…' : 'Sign in'}</button></div>
    </fieldset></form>
  </AuthShell>;
}

export function Register({ onNavigate }) {
  const { register } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const { busy, error, submit } = useSubmit(() => register(name.trim(), email.trim(), password));
  const validate = () => { const size = passwordBytes(password); return size < 8 || size > 72 ? passwordRule : ''; };
  return <AuthShell title="Create your account" footer={<>Already registered? <a href="/login" onClick={event => { event.preventDefault(); onNavigate('/login'); }}>Sign in</a></>}>
    {error && <p role="alert" className="error">{error}</p>}
    <form onSubmit={event => submit(event, validate)}><fieldset disabled={busy}>
      <label htmlFor="name">Name</label>
      <input id="name" autoFocus required maxLength={100} pattern=".*\S.*" autoComplete="name" value={name} onChange={event => setName(event.target.value)} />
      <label htmlFor="email">Email</label>
      <input id="email" type="email" required maxLength={100} autoComplete="username" value={email} onChange={event => setEmail(event.target.value)} />
      <label htmlFor="password">Password</label>
      <input id="password" type="password" required autoComplete="new-password" aria-describedby="password-help" value={password} onChange={event => setPassword(event.target.value)} />
      <p id="password-help">{passwordRule} It must not be the same as your email.</p>
      <div className="actions"><button type="submit">{busy ? 'Creating…' : 'Create account'}</button></div>
    </fieldset></form>
  </AuthShell>;
}
