import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import Accounts from './Accounts';

const customer = { customerId: 'c1', name: 'Moataz Hikal' };
const account = { accountId: 'a1', customerId: 'c1', userName: 'Moataz Hikal', accountType: 'SAVINGS', balance: '0.00' };
const other = { ...account, accountId: 'a2', customerId: 'c2', userName: 'Grace' };
let requests;
let failure;
beforeEach(() => {
  requests = []; failure = null;
  vi.stubGlobal('fetch', vi.fn(async (url, options) => {
    requests.push({ url, ...options });
    const body = options.method === 'POST' || options.method === 'DELETE'
      ? (failure ? { detail: failure.message } : { ...account, balance: '12.34' })
      : url.endsWith('/transactions') ? [{ txnId: 't1', type: 'DEPOSIT', amount: '12.34', balanceAfter: '12.34', date: '2026-10-01T12:00:00Z' }]
      : url.endsWith('/api/accounts') ? [account, other] : [account];
    return { ok: !failure || options.method === 'GET', status: failure && options.method !== 'GET' ? failure.status : 200, json: async () => body };
  }));
});

async function openAction(name) {
  const user = userEvent.setup();
  render(<Accounts customer={customer} onBack={() => {}} />);
  if (name.startsWith('Delete account')) { await screen.findByText('SAVINGS'); await user.click(screen.getByText('More')); }
  await user.click(await screen.findByRole('button', { name }));
  return user;
}

it('deposits decimal strings with an idempotency key and refreshes balances', async () => {
  const user = await openAction('Deposit');
  await user.type(screen.getByLabelText('Amount'), '12.34');
  await user.click(screen.getByRole('button', { name: 'Submit deposit' }));
  await screen.findByText('Deposit completed.');
  const request = requests.find(item => item.method === 'POST');
  expect(request.url).toMatch(/\/accounts\/a1\/deposit$/);
  expect(JSON.parse(request.body)).toEqual({ amount: '12.34' });
  expect(request.headers['Idempotency-Key']).toBeTruthy();
  expect(requests.filter(item => item.url.endsWith('/customers/c1/accounts')).length).toBe(2);
});

it('titles a completed withdrawal and its form heading', async () => {
  const user = await openAction('Withdraw');
  expect(screen.getByRole('heading', { name: 'Withdrawal · a1' })).toBeInTheDocument();
  await user.type(screen.getByLabelText('Amount'), '5');
  await user.click(screen.getByRole('button', { name: 'Submit withdrawal' }));
  await screen.findByText('Withdrawal completed.');
});

it('preserves the withdrawal form when funds are insufficient', async () => {
  const user = await openAction('Withdraw');
  failure = { status: 400, message: 'Insufficient funds' };
  await user.type(screen.getByLabelText('Amount'), '12.34');
  await user.click(screen.getByRole('button', { name: 'Submit withdrawal' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Insufficient funds');
  expect(screen.getByLabelText('Amount')).toHaveValue('12.34');
});

it('transfers between accounts belonging to different customers', async () => {
  const user = await openAction('Transfer');
  await user.selectOptions(await screen.findByLabelText('From account'), 'a1');
  await user.selectOptions(screen.getByLabelText('To account'), 'a2');
  await user.type(screen.getByLabelText('Amount'), '5.25');
  await user.click(screen.getByRole('button', { name: 'Submit transfer' }));
  await screen.findByText('Transfer completed.');
  const request = requests.find(item => item.url.endsWith('/transfers'));
  expect(JSON.parse(request.body)).toEqual({ fromAccountId: 'a1', toAccountId: 'a2', amount: '5.25' });
  expect(request.headers['Idempotency-Key']).toBeTruthy();
});

it('shows the server nonzero-balance error after confirmed deletion', async () => {
  const user = await openAction('Delete account a1');
  expect(requests.some(item => item.method === 'DELETE')).toBe(false);
  failure = { status: 409, message: 'Account balance must be zero' };
  await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete account' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Account balance must be zero');
  expect(screen.getByRole('alertdialog')).toBeInTheDocument();
});

it('opens an account for the selected customer', async () => {
  const user = await openAction('Open account');
  await user.type(screen.getByLabelText('Account type'), 'CURRENT');
  await user.click(screen.getByRole('button', { name: 'Create account' }));
  await screen.findByText('Account opened.');
  expect(JSON.parse(requests.find(item => item.method === 'POST').body)).toEqual({ customerId: 'c1', accountType: 'CURRENT' });
});

it('loads account transaction history', async () => {
  await openAction('View activity');
  expect(await screen.findByText('DEPOSIT')).toBeInTheDocument();
  expect(screen.getAllByText('12.34')).toHaveLength(2);
});

it('loads premium accounts with an explicit result limit', async () => {
  render(<Accounts onBack={() => {}} />);
  await screen.findByText('SAVINGS');
  expect(requests[0].url).toMatch(/\/accounts\/premium\?limit=200$/);
});

it('rejects fractional cents without sending a money request', async () => {
  const user = await openAction('Deposit');
  await user.type(screen.getByLabelText('Amount'), '1.001');
  await user.click(screen.getByRole('button', { name: 'Submit deposit' }));
  await waitFor(() => expect(requests.some(item => item.method === 'POST')).toBe(false));
});

it('removes an account after a successful empty 204 response', async () => {
  const user = await openAction('Delete account a1');
  fetch.mockImplementationOnce(async () => ({ ok: true, status: 204 }))
    .mockImplementationOnce(async () => ({ ok: true, status: 200, json: async () => [] }));
  await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete account' }));
  expect(await screen.findByText('No accounts found.')).toBeInTheDocument();
  expect(screen.getByText('Account deleted.')).toBeInTheDocument();
});

it('disables deletion when the displayed balance is nonzero', async () => {
  fetch.mockResolvedValueOnce({ ok: true, status: 200, json: async () => [{ ...account, balance: '0.01' }] });
  render(<Accounts customer={customer} onBack={() => {}} />);
  await screen.findByText('SAVINGS');
  await userEvent.setup().click(screen.getByText('More'));
  expect(screen.getByRole('button', { name: 'Delete account a1' })).toBeDisabled();
});

it('expands activity within its account and collapses it without reloading accounts', async () => {
  const user = await openAction('View activity');
  const activity = screen.getByRole('button', { name: 'View activity' });
  expect(activity).toHaveAttribute('aria-expanded', 'true');
  expect(await screen.findByText('DEPOSIT')).toBeInTheDocument();
  await user.click(activity);
  expect(activity).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByText('DEPOSIT')).not.toBeInTheDocument();
  expect(requests.filter(item => item.url.endsWith('/customers/c1/accounts'))).toHaveLength(1);
});
