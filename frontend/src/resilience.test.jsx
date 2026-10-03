import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Accounts from './Accounts';
import App from './App';
import { Login } from './AuthPages';
import { AuthProvider } from './auth';
import { Loading, dateTime, money, shortDate } from './ui';

const reply = (body, status = 200, headers = {}) => ({ ok: status < 400, status, json: async () => body, headers: { get: name => headers[name] ?? null } });
const stubFetch = handler => vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => handler(url.replace(/^.*\/api/, ''), options)));
const renderLogin = () => render(<AuthProvider><Login onNavigate={() => {}} /></AuthProvider>);
const signIn = async user => {
  await user.type(screen.getByLabelText('Email'), 'ada@example.com');
  await user.type(screen.getByLabelText('Password'), 'wrong password');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
};

beforeEach(() => sessionStorage.clear());
afterEach(() => vi.useRealTimers());

// Lockout (HTTP 429)
it('shows the minutes message on 429 and disables Sign in until the countdown ends', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  stubFetch(() => reply({ detail: 'Too many failed login attempts, try again later', retryAfter: 700 }, 429, { 'Retry-After': '700' }));
  renderLogin();
  await signIn(user);
  const note = await screen.findByRole('status');
  expect(note).toHaveTextContent('Too many failed attempts. Try again in 12 minutes.');
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  await act(async () => { await vi.advanceTimersByTimeAsync(15 * 1000); });
  expect(screen.getByRole('status')).toHaveTextContent('Try again in 12 minutes');
  await act(async () => { await vi.advanceTimersByTimeAsync(30 * 1000); });
  expect(screen.getByRole('status')).toHaveTextContent('Try again in 11 minutes');
  // One step per second: each tick renders before the next timer is scheduled, as in a real browser.
  for (let i = 0; i < 660; i += 1) await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled());
  expect(screen.queryByText(/Too many failed attempts/)).not.toBeInTheDocument();
});

it('shows seconds when the lock is under a minute', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  stubFetch(() => reply({ detail: 'Too many', retryAfter: 45 }, 429));
  renderLogin();
  await signIn(user);
  expect(await screen.findByText('45 seconds')).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('less than a minute');
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled();
});

it('reads Retry-After from the header when the body has no retryAfter', async () => {
  const user = userEvent.setup();
  stubFetch(() => reply({ detail: 'Too many' }, 429, { 'Retry-After': '120' }));
  renderLogin();
  await signIn(user);
  expect(await screen.findByRole('status')).toHaveTextContent('Try again in 2 minutes.');
});

it('falls back to a generic lockout message when no retry time is given', async () => {
  const user = userEvent.setup();
  stubFetch(() => reply({ detail: 'Too many failed login attempts, try again later' }, 429));
  renderLogin();
  await signIn(user);
  expect(await screen.findByRole('status')).toHaveTextContent('Too many failed attempts. Try again in a few minutes.');
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
});

it('keeps the generic error for a normal 401', async () => {
  const user = userEvent.setup();
  stubFetch(() => reply({ detail: 'Invalid email or password' }, 401));
  renderLogin();
  await signIn(user);
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password');
  expect(screen.queryByText(/Too many failed attempts/)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
});

// Slow first load (Lambda cold start)
it('says the server is waking up only after two seconds of loading', () => {
  vi.useFakeTimers();
  render(<Loading label="Loading customers…" />);
  expect(screen.getByText('Loading customers…')).toBeInTheDocument();
  act(() => { vi.advanceTimersByTime(1900); });
  expect(screen.queryByText(/Waking up the server/)).not.toBeInTheDocument();
  act(() => { vi.advanceTimersByTime(200); });
  const note = screen.getByText('Waking up the server, this can take a few seconds.');
  expect(note).toHaveAttribute('aria-live', 'polite');
});

it('shows the waking note on a slow sign-in and then the error with the form usable again', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  let finish;
  stubFetch(() => new Promise(resolve => { finish = () => resolve(reply({ detail: 'Invalid email or password' }, 401)); }));
  renderLogin();
  await signIn(user);
  expect(screen.queryByText(/Waking up the server/)).not.toBeInTheDocument();
  await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
  expect(screen.getByText(/Waking up the server/)).toBeInTheDocument();
  await act(async () => { finish(); });
  expect(await screen.findByRole('alert')).toBeInTheDocument();
  expect(screen.queryByText(/Waking up the server/)).not.toBeInTheDocument();
});

it('offers Retry after a failed customers load and recovers', async () => {
  const user = userEvent.setup();
  let calls = 0;
  stubFetch(() => (++calls === 1 ? reply({ detail: 'Unable to load' }, 503) : reply([])));
  render(<App onSignOut={() => {}} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load');
  await user.click(screen.getByRole('button', { name: 'Retry' }));
  expect(await screen.findByText('No customers yet.')).toBeInTheDocument();
});

// Formatters
it('formats money consistently', () => {
  expect(money('1234567.8')).toBe('1,234,567.80');
  expect(money(0)).toBe('0.00');
  expect(money('-5')).toBe('-5.00');
  expect(money(null)).toBe('—');
  expect(money('abc')).toBe('—');
});

it('formats dates and times consistently and tolerates bad input', () => {
  expect(shortDate('2026-10-01T12:00:00Z')).toMatch(/^\d{1,2} Oct 2026$/);
  expect(dateTime('2026-10-01T12:00:00Z')).toMatch(/^\d{1,2} Oct 2026, \d{2}:\d{2}$/);
  expect(shortDate('')).toBe('');
  expect(dateTime('not a date')).toBe('');
});

// Empty states with a next action
it('offers to add the first customer from the empty list', async () => {
  const user = userEvent.setup();
  stubFetch(() => reply([]));
  render(<App onSignOut={() => {}} />);
  await user.click(await screen.findByRole('button', { name: 'Add the first customer' }));
  expect(screen.getByRole('heading', { name: 'Add customer' })).toBeInTheDocument();
});

const customer = { customerId: 'c1', name: 'Ada' };
const account = { accountId: 'a1', customerId: 'c1', userName: 'Ada', accountType: 'SAVINGS', balance: '5.00', createdAt: '2026-10-01T00:00:00Z' };

it('offers to open the first account, and to deposit from an empty history', async () => {
  const user = userEvent.setup();
  stubFetch(path => reply(path.endsWith('/transactions') ? [] : path.includes('/customers/') ? [] : [account]));
  const { unmount } = render(<Accounts customer={customer} onBack={() => {}} />);
  await user.click(await screen.findByRole('button', { name: 'Open the first account' }));
  expect(screen.getByRole('heading', { name: 'Open account' })).toBeInTheDocument();
  unmount();

  stubFetch(path => reply(path.endsWith('/transactions') ? [] : [account]));
  render(<Accounts customer={customer} onBack={() => {}} />);
  await user.click(await screen.findByRole('button', { name: 'History' }));
  expect(await screen.findByText('No transactions yet.')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Make a deposit' }));
  expect(screen.getByRole('heading', { name: /Deposit/ })).toBeInTheDocument();
});

// Focus return
it('returns focus to the button that opened a form when it is cancelled', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  stubFetch(() => reply([account]));
  render(<Accounts customer={customer} onBack={() => {}} />);
  const deposit = await screen.findByRole('button', { name: 'Deposit' });
  await user.click(deposit);
  expect(screen.getByLabelText('Amount')).toHaveFocus();
  await user.click(screen.getByRole('button', { name: 'Cancel' }));
  await act(async () => { await vi.advanceTimersByTimeAsync(10); });
  expect(screen.getByRole('button', { name: 'Deposit' })).toHaveFocus();
});

it('returns focus to History when the history panel is closed', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  stubFetch(path => reply(path.endsWith('/transactions') ? [] : [account]));
  render(<Accounts customer={customer} onBack={() => {}} />);
  await user.click(await screen.findByRole('button', { name: 'History' }));
  await user.click(await screen.findByRole('button', { name: 'Close history' }));
  await act(async () => { await vi.advanceTimersByTimeAsync(10); });
  expect(screen.getByRole('button', { name: 'History' })).toHaveFocus();
});

it('announces operation errors with role=alert', async () => {
  const user = userEvent.setup();
  stubFetch((path, options) => (options.method === 'POST' ? reply({ detail: 'Insufficient funds' }, 409) : reply([account])));
  render(<Accounts customer={customer} onBack={() => {}} />);
  await user.click(await screen.findByRole('button', { name: 'Withdraw' }));
  await user.type(screen.getByLabelText('Amount'), '9');
  await user.click(screen.getByRole('button', { name: 'Submit withdrawal' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Insufficient funds');
});

it('returns focus to the Delete button after the delete dialog is cancelled', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  stubFetch(() => reply([{ customerId: 'c1', name: 'Ada Lovelace', email: 'ada@example.com', createdAt: '2026-09-01T10:00:00Z' }]));
  render(<App onSignOut={() => {}} />);
  await user.click(await screen.findByRole('button', { name: 'Delete Ada Lovelace' }));
  expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
  await user.click(screen.getByRole('button', { name: 'Cancel' }));
  await act(async () => { await vi.advanceTimersByTimeAsync(10); });
  expect(screen.getByRole('button', { name: 'Delete Ada Lovelace' })).toHaveFocus();
});
