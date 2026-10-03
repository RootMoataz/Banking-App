import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { Login } from './AuthPages';
import { AuthProvider } from './auth';
import { DEMO_ACCOUNTS, DEMO_PASSWORD } from './demo';

const renderLogin = () => render(<AuthProvider><Login onNavigate={() => {}} /></AuthProvider>);

it('lists the demo accounts and the shared password', () => {
  renderLogin();
  const card = screen.getByRole('region', { name: 'Try it with a demo account' });
  const rows = within(card).getAllByRole('listitem');
  expect(rows).toHaveLength(DEMO_ACCOUNTS.length);
  DEMO_ACCOUNTS.forEach(({ email, role }, index) => {
    expect(rows[index]).toHaveTextContent(email);
    expect(rows[index]).toHaveTextContent(role);
  });
  expect(within(card).getByText(DEMO_PASSWORD)).toBeInTheDocument();
  expect(within(card).getByRole('link', { name: /See the demo accounts/ })).toBeInTheDocument();
});

it('fills the form with an account and moves focus to Sign in without submitting', async () => {
  const user = userEvent.setup();
  const fetchSpy = vi.fn();
  vi.stubGlobal('fetch', fetchSpy);
  renderLogin();
  await user.click(screen.getByRole('button', { name: 'Use demo-low@example.com' }));
  expect(screen.getByLabelText('Email')).toHaveValue('demo-low@example.com');
  expect(screen.getByLabelText('Password')).toHaveValue(DEMO_PASSWORD);
  expect(screen.getByRole('button', { name: 'Sign in' })).toHaveFocus();
  expect(fetchSpy).not.toHaveBeenCalled();
});

it('copies the password and announces it politely', async () => {
  const user = userEvent.setup();
  const writeText = vi.fn().mockResolvedValue();
  vi.spyOn(navigator.clipboard, 'writeText').mockImplementation(writeText);
  renderLogin();
  await user.click(screen.getByRole('button', { name: 'Copy password' }));
  expect(writeText).toHaveBeenCalledWith(DEMO_PASSWORD);
  const note = await screen.findByText('Copied');
  expect(note).toHaveAttribute('aria-live', 'polite');
});

it('falls back to execCommand when the clipboard API is missing', async () => {
  const user = userEvent.setup();
  renderLogin();
  vi.stubGlobal('navigator', { ...navigator, clipboard: undefined });
  document.execCommand = vi.fn(() => true);
  await user.click(screen.getByRole('button', { name: 'Copy password' }));
  expect(document.execCommand).toHaveBeenCalledWith('copy');
  expect(await screen.findByText('Copied')).toBeInTheDocument();
});
