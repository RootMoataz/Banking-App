import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import Root from './Root';
import { DEMO_URL } from './ui';

const landingHeading = { level: 1, name: /every deposit, transfer and rule/i };

const KEY = 'paper-maker-token';
const admin = { email: 'boss@example.com', role: 'ADMIN', customerId: null, name: 'Boss' };
const ada = { email: 'ada@example.com', role: 'CUSTOMER', customerId: 'c1', name: 'Ada Lovelace' };
const acct = { accountId: 'a1', customerId: 'c1', userName: 'Ada Lovelace', accountType: 'SAVINGS', balance: '10.50', createdAt: '2026-10-01T00:00:00Z' };
const reply = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
let routes; let calls;
beforeEach(() => {
  sessionStorage.clear(); window.history.replaceState(null, '', '/'); calls = []; routes = {};
  vi.stubGlobal('crypto', { randomUUID: vi.fn().mockReturnValueOnce('key-1').mockReturnValueOnce('key-2') });
  vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
    const path = url.replace(/^.*\/api/, '');
    calls.push({ path, ...options });
    const handler = routes[`${options.method || 'GET'} ${path}`];
    return handler ? handler(options) : reply([]);
  }));
});
const signedIn = (user, extra = {}) => {
  sessionStorage.setItem(KEY, 'tok');
  routes['GET /auth/me'] = () => reply(user);
  Object.assign(routes, extra);
};

it('sends unauthenticated visitors to the login page', async () => {
  window.history.replaceState(null, '', '/accounts');
  render(<Root />);
  expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  expect(window.location.pathname).toBe('/login');
  const demo = screen.getByRole('link', { name: /See the demo accounts/ });
  expect(demo).toHaveAttribute('href', DEMO_URL);
  expect(demo).toHaveAttribute('target', '_blank');
  expect(demo).toHaveAttribute('rel', 'noopener noreferrer');
  expect(demo).toHaveAccessibleName('See the demo accounts (opens GitHub in a new tab)');
});

it('shows the landing page at / to logged-out visitors', async () => {
  render(<Root />);
  expect(await screen.findByRole('heading', landingHeading)).toBeInTheDocument();
  expect(window.location.pathname).toBe('/');
  expect(calls.every(c => c.path === '/auth/me')).toBe(true);
});

it('sends unknown paths to the landing page', async () => {
  window.history.replaceState(null, '', '/nowhere');
  render(<Root />);
  expect(await screen.findByRole('heading', landingHeading)).toBeInTheDocument();
  expect(window.location.pathname).toBe('/');
});

it('navigates from the landing page to login and register', async () => {
  const user = userEvent.setup();
  render(<Root />);
  await user.click(within(await screen.findByRole('main')).getAllByRole('link', { name: 'Sign in' })[0]);
  expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  expect(window.location.pathname).toBe('/login');
  await user.click(screen.getByRole('link', { name: 'Create an account' }));
  expect(await screen.findByRole('heading', { name: 'Create your account' })).toBeInTheDocument();
});

it('never shows the landing page to a signed-in admin', async () => {
  signedIn(admin, { 'GET /customers': () => reply([]) });
  render(<Root />);
  expect(await screen.findByRole('heading', { name: 'Customers' })).toBeInTheDocument();
  expect(screen.queryByRole('heading', landingHeading)).toBeNull();
  expect(window.location.pathname).toBe('/');
});

it('sends a signed-in customer from / to My accounts', async () => {
  signedIn(ada, { 'GET /customers/c1/accounts': () => reply([acct]) });
  render(<Root />);
  expect(await screen.findByRole('heading', { name: 'My accounts' })).toBeInTheDocument();
  expect(screen.queryByRole('heading', landingHeading)).toBeNull();
  expect(window.location.pathname).toBe('/accounts');
});

it('logs in, stores the token and shows the admin screens', async () => {
  window.history.replaceState(null, '', '/login');
  routes['POST /auth/login'] = () => reply({ token: 'jwt-1', tokenType: 'Bearer', user: admin });
  routes['GET /customers'] = () => reply([]);
  const user = userEvent.setup();
  render(<Root />);
  await user.type(await screen.findByLabelText('Email'), 'boss@example.com');
  await user.type(screen.getByLabelText('Password'), 'correct horse');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
  expect(await screen.findByRole('heading', { name: 'Customers' })).toBeInTheDocument();
  expect(sessionStorage.getItem(KEY)).toBe('jwt-1');
  expect(JSON.parse(calls.find(c => c.path === '/auth/login').body)).toEqual({ email: 'boss@example.com', password: 'correct horse' });
  await waitFor(() => expect(calls.some(c => c.path === '/customers' && c.headers.Authorization === 'Bearer jwt-1')).toBe(true));
});

it('shows the generic login error inline and keeps the user signed out', async () => {
  window.history.replaceState(null, '', '/login');
  routes['POST /auth/login'] = () => reply({ detail: 'Invalid email or password' }, 401);
  const user = userEvent.setup();
  render(<Root />);
  await user.type(await screen.findByLabelText('Email'), 'x@example.com');
  await user.type(screen.getByLabelText('Password'), 'whatever1');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password');
  expect(sessionStorage.getItem(KEY)).toBeNull();
});

it('registers a customer and lands on My accounts', async () => {
  window.history.replaceState(null, '', '/register');
  routes['POST /auth/register'] = () => reply({ token: 'jwt-2', tokenType: 'Bearer', user: ada }, 201);
  routes['GET /customers/c1/accounts'] = () => reply([]);
  const user = userEvent.setup();
  render(<Root />);
  expect(await screen.findByText(/8 to 72 characters/)).toBeInTheDocument();
  await user.type(screen.getByLabelText('First name'), 'Ada');
  await user.type(screen.getByLabelText('Last name'), 'Lovelace');
  await user.type(screen.getByLabelText('Email'), 'ada@example.com');
  await user.type(screen.getByLabelText('Password'), 'longenough1');
  await user.click(screen.getByRole('button', { name: 'Create account' }));
  expect(await screen.findByRole('heading', { name: 'My accounts' })).toBeInTheDocument();
  expect(JSON.parse(calls.find(c => c.path === '/auth/register').body)).toEqual({ name: 'Ada Lovelace', email: 'ada@example.com', password: 'longenough1' });
});

it('rejects a short password before calling the server', async () => {
  window.history.replaceState(null, '', '/register');
  const user = userEvent.setup();
  render(<Root />);
  await user.type(await screen.findByLabelText('First name'), 'Ada');
  await user.type(screen.getByLabelText('Last name'), 'Lovelace');
  await user.type(screen.getByLabelText('Email'), 'ada@example.com');
  await user.type(screen.getByLabelText('Password'), 'short');
  await user.click(screen.getByRole('button', { name: 'Create account' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('8 to 72');
  expect(calls.some(c => c.path === '/auth/register')).toBe(false);
});

const registerCreate = () => { routes['POST /auth/register'] = () => reply({ token: 'jwt-2', tokenType: 'Bearer', user: ada }, 201); routes['GET /customers/c1/accounts'] = () => reply([]); };
const registerBody = () => JSON.parse(calls.find(c => c.path === '/auth/register').body);

it('gives the register name fields the right autocomplete hints', async () => {
  window.history.replaceState(null, '', '/register');
  render(<Root />);
  const first = await screen.findByLabelText('First name');
  const last = screen.getByLabelText('Last name');
  expect(first).toHaveAttribute('autocomplete', 'given-name');
  expect(last).toHaveAttribute('autocomplete', 'family-name');
  expect(first).toHaveAttribute('aria-required', 'true');
  expect(last).toHaveAttribute('aria-required', 'true');
});

it('requires both register names, with the message in an alert and focus on the field', async () => {
  window.history.replaceState(null, '', '/register');
  const user = userEvent.setup();
  render(<Root />);
  await user.type(await screen.findByLabelText('Last name'), 'Lovelace');
  await user.type(screen.getByLabelText('Email'), 'ada@example.com');
  await user.type(screen.getByLabelText('Password'), 'longenough1');
  await user.click(screen.getByRole('button', { name: 'Create account' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Enter your first name.');
  expect(screen.getByLabelText('First name')).toHaveFocus();
  await user.type(screen.getByLabelText('First name'), 'Ada');
  await user.clear(screen.getByLabelText('Last name'));
  await user.type(screen.getByLabelText('Last name'), '   ');
  await user.click(screen.getByRole('button', { name: 'Create account' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Enter your last name.');
  expect(screen.getByLabelText('Last name')).toHaveFocus();
  expect(calls.some(c => c.path === '/auth/register')).toBe(false);
});

it('rejects register names that are too long or only digits', async () => {
  window.history.replaceState(null, '', '/register');
  const user = userEvent.setup();
  render(<Root />);
  const first = await screen.findByLabelText('First name');
  const last = screen.getByLabelText('Last name');
  await user.type(screen.getByLabelText('Email'), 'ada@example.com');
  await user.type(screen.getByLabelText('Password'), 'longenough1');
  const submit = () => user.click(screen.getByRole('button', { name: 'Create account' }));
  await user.type(first, 'A'.repeat(51));
  await user.type(last, 'Lovelace');
  await submit();
  expect(await screen.findByRole('alert')).toHaveTextContent('First name must be 50 characters or fewer.');
  await user.clear(first);
  await user.type(first, '12345');
  await submit();
  expect(await screen.findByRole('alert')).toHaveTextContent('First name cannot be only digits.');
  await user.clear(first);
  await user.type(first, 'Ada');
  await user.clear(last);
  await user.type(last, 'L'.repeat(51));
  await submit();
  expect(await screen.findByRole('alert')).toHaveTextContent('Last name is too long');
  expect(calls.some(c => c.path === '/auth/register')).toBe(false);
});

it('sends first and last name as one trimmed, single-spaced name', async () => {
  window.history.replaceState(null, '', '/register');
  registerCreate();
  const user = userEvent.setup();
  render(<Root />);
  await user.type(await screen.findByLabelText('First name'), '  Ada   Augusta ');
  await user.type(screen.getByLabelText('Last name'), '  King-Noel  ');
  await user.type(screen.getByLabelText('Email'), 'ada@example.com');
  await user.type(screen.getByLabelText('Password'), 'longenough1');
  await user.click(screen.getByRole('button', { name: 'Create account' }));
  await screen.findByRole('heading', { name: 'My accounts' });
  expect(registerBody().name).toBe('Ada Augusta King-Noel');
});

it('shows translated register labels and messages and still sends one name, in German', async () => {
  localStorage.setItem('pm.lang', 'de');
  window.history.replaceState(null, '', '/register');
  registerCreate();
  const user = userEvent.setup();
  try {
    render(<Root />);
    await user.type(await screen.findByLabelText('Vorname'), 'Ada');
    await user.type(screen.getByLabelText('E-Mail'), 'ada@example.com');
    await user.type(screen.getByLabelText('Passwort'), 'longenough1');
    await user.click(screen.getByRole('button', { name: 'Konto erstellen' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Geben Sie Ihren Nachnamen ein.');
    await user.type(screen.getByLabelText('Nachname'), ' Lovelace ');
    await user.click(screen.getByRole('button', { name: 'Konto erstellen' }));
    await waitFor(() => expect(calls.some(c => c.path === '/auth/register')).toBe(true));
    expect(registerBody().name).toBe('Ada Lovelace');
  } finally { localStorage.removeItem('pm.lang'); }
});

it('loads identity from /auth/me and shows customer-only navigation', async () => {
  signedIn(ada, { 'GET /customers/c1/accounts': () => reply([acct]) });
  render(<Root />);
  expect(await screen.findByRole('cell', { name: '10.50' })).toBeInTheDocument();
  const nav = screen.getByRole('navigation');
  expect(nav).toHaveTextContent('My accounts');
  expect(nav).toHaveTextContent('Transfer');
  expect(nav).toHaveTextContent('Profile');
  expect(nav).not.toHaveTextContent('Customers');
  expect(nav).not.toHaveTextContent('Premium');
  expect(screen.queryByRole('button', { name: /deposit|withdraw|delete/i })).toBeNull();
});

it('opens an account for the customer and shows history', async () => {
  signedIn(ada, {
    'GET /customers/c1/accounts': () => reply([acct]),
    'POST /accounts': () => reply({ ...acct, accountId: 'a2' }, 201),
    'GET /accounts/a1/transactions': () => reply([{ txnId: 't1', type: 'DEPOSIT', amount: '10.50', balanceAfter: '10.50', date: '2026-10-01T12:00:00Z' }]),
  });
  const user = userEvent.setup();
  render(<Root />);
  await user.click(await screen.findByRole('button', { name: 'History' }));
  expect(await screen.findByText('DEPOSIT')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Open account' }));
  await user.selectOptions(screen.getByLabelText('Account type'), 'Checking');
  await user.click(screen.getByRole('button', { name: 'Create account' }));
  expect(await screen.findByText('Account opened.')).toBeInTheDocument();
  expect(JSON.parse(calls.find(c => c.path === '/accounts' && c.method === 'POST').body)).toEqual({ customerId: 'c1', accountType: 'Checking' });
});

it('transfers from an own account with a fresh idempotency key per submit', async () => {
  window.history.replaceState(null, '', '/transfer');
  signedIn(ada, { 'GET /customers/c1/accounts': () => reply([acct]), 'POST /transfers': () => reply({ ok: true }, 201) });
  const user = userEvent.setup();
  render(<Root />);
  await user.selectOptions(await screen.findByLabelText('From account'), 'a1');
  await user.type(screen.getByLabelText('To account ID'), 'zzz9');
  await user.type(screen.getByLabelText('Amount'), '2.50');
  await user.click(screen.getByRole('button', { name: 'Submit transfer' }));
  expect(await screen.findByText('Transfer completed.')).toBeInTheDocument();
  await user.type(screen.getByLabelText('To account ID'), 'zzz9');
  await user.type(screen.getByLabelText('Amount'), '1');
  await user.click(screen.getByRole('button', { name: 'Submit transfer' }));
  await screen.findByText('Transfer completed.');
  const posts = calls.filter(c => c.path === '/transfers');
  expect(JSON.parse(posts[0].body)).toEqual({ fromAccountId: 'a1', toAccountId: 'zzz9', amount: '2.50' });
  expect(posts.map(p => p.headers['Idempotency-Key'])).toEqual(['key-1', 'key-2']);
});

it('shows the profile read-only', async () => {
  window.history.replaceState(null, '', '/profile');
  signedIn(ada);
  render(<Root />);
  expect(await screen.findByText('ada@example.com')).toBeInTheDocument();
  expect(screen.getByText('Ada Lovelace', { selector: 'dd' })).toBeInTheDocument();
  expect(screen.queryByRole('textbox')).toBeNull();
});

it('shows access denied to a customer on an admin route, and to an admin on a customer route', async () => {
  window.history.replaceState(null, '', '/premium');
  signedIn(ada);
  const { unmount } = render(<Root />);
  expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
  unmount();
  window.history.replaceState(null, '', '/transfer');
  signedIn(admin);
  render(<Root />);
  expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
  expect(screen.getByRole('navigation')).toHaveTextContent('Premium accounts');
});

it('clears the token and leaves the signed-in screens on any 401', async () => {
  signedIn(admin, { 'GET /customers': () => reply({ detail: 'Not authenticated' }, 401) });
  render(<Root />);
  expect(await screen.findByRole('heading', landingHeading)).toBeInTheDocument();
  expect(sessionStorage.getItem(KEY)).toBeNull();
});

it('signs out', async () => {
  signedIn(admin, { 'GET /customers': () => reply([]) });
  const user = userEvent.setup();
  render(<Root />);
  await user.click(await screen.findByRole('button', { name: 'Sign out' }));
  expect(await screen.findByRole('heading', landingHeading)).toBeInTheDocument();
  expect(sessionStorage.getItem(KEY)).toBeNull();
});

it('customer open-account select lists the types, blocks submit until chosen, and sends the English type in German', async () => {
  localStorage.setItem('pm.lang', 'de');
  signedIn(ada, {
    'GET /customers/c1/accounts': () => reply([{ ...acct, accountType: 'Savings' }, { ...acct, accountId: 'a9', accountType: 'Legacy Gold' }]),
    'POST /accounts': () => reply({ ...acct, accountId: 'a2' }, 201),
  });
  const user = userEvent.setup();
  render(<Root />);
  expect(await screen.findByText('Sparkonto')).toBeInTheDocument();
  expect(screen.getByText('Legacy Gold')).toBeInTheDocument();
  await user.click(screen.getAllByRole('button', { name: 'Konto eröffnen' })[0]);
  const select = screen.getByLabelText('Kontoart');
  expect(select.tagName).toBe('SELECT');
  expect(select).toHaveFocus();
  expect(within(select).getAllByRole('option').map(o => o.textContent)).toEqual(['Kontoart auswählen', 'Girokonto', 'Sparkonto', 'Kontokorrentkonto', 'Geschäftskonto', 'Studentenkonto']);
  await user.click(screen.getByRole('button', { name: 'Konto erstellen' }));
  expect(select.validationMessage).toBe('Wählen Sie eine Kontoart aus.');
  expect(calls.some(c => c.method === 'POST')).toBe(false);
  await user.selectOptions(select, 'Savings');
  await user.click(screen.getByRole('button', { name: 'Konto erstellen' }));
  await waitFor(() => expect(JSON.parse(calls.find(c => c.path === '/accounts' && c.method === 'POST').body)).toEqual({ customerId: 'c1', accountType: 'Savings' }));
});
