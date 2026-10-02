import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import Landing from './Landing';

let onNavigate;
beforeEach(() => { onNavigate = vi.fn(); vi.stubGlobal('fetch', vi.fn()); });
const main = () => within(screen.getByRole('main'));

it('has landmarks, one h1 and a skip link', () => {
  render(<Landing onNavigate={onNavigate} />);
  expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  expect(screen.getByRole('banner')).toBeInTheDocument();
  expect(screen.getByRole('navigation', { name: 'Primary' })).toBeInTheDocument();
  expect(screen.getByRole('contentinfo')).toHaveTextContent('An educational banking application. Not a real bank.');
  expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main');
  expect(screen.getByRole('link', { name: 'What it does' })).toHaveAttribute('href', '#features');
});

it('sends the call-to-action links to login and register without a page load', async () => {
  const user = userEvent.setup();
  render(<Landing onNavigate={onNavigate} />);
  await user.click(main().getAllByRole('link', { name: 'Sign in' })[0]);
  expect(onNavigate).toHaveBeenLastCalledWith('/login');
  await user.click(main().getAllByRole('link', { name: 'Open an account' })[0]);
  expect(onNavigate).toHaveBeenLastCalledWith('/register');
  await user.click(within(screen.getByRole('banner')).getByRole('link', { name: 'Open an account' }));
  expect(onNavigate).toHaveBeenLastCalledWith('/register');
});

it('updates the sample balance and activity, and never calls the API', async () => {
  const user = userEvent.setup();
  render(<Landing onNavigate={onNavigate} />);
  expect(screen.getByText('10,680.00')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Deposit' }));
  expect(screen.getByText('10,780.00')).toBeInTheDocument();
  expect(screen.getByText('2,580.00')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '250.00' }));
  await user.click(screen.getByRole('button', { name: 'Transfer to Savings' }));
  expect(screen.getByText('2,330.00')).toBeInTheDocument();
  expect(screen.getByText('8,450.00')).toBeInTheDocument();
  expect(screen.getByText('10,780.00')).toBeInTheDocument();
  expect(screen.getByText('Transfer to Savings', { selector: 'li span' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Reset' }));
  expect(screen.getByText('10,680.00')).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it('disables a sample withdrawal larger than the checking balance', async () => {
  const user = userEvent.setup();
  render(<Landing onNavigate={onNavigate} />);
  await user.click(screen.getByRole('button', { name: '250.00' }));
  for (let i = 0; i < 9; i += 1) await user.click(screen.getByRole('button', { name: 'Withdraw' }));
  expect(screen.getByText('230.00', { selector: 'dd' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Withdraw' })).toBeDisabled();
});

it('opens and closes the mobile menu with the keyboard', async () => {
  const user = userEvent.setup();
  render(<Landing onNavigate={onNavigate} />);
  const menu = screen.getByRole('button', { name: 'Menu' });
  expect(menu).toHaveAttribute('aria-expanded', 'false');
  await user.click(menu);
  expect(menu).toHaveAttribute('aria-expanded', 'true');
  await user.keyboard('{Escape}');
  expect(menu).toHaveAttribute('aria-expanded', 'false');
  expect(menu).toHaveFocus();
});
