import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import App from './App';

const ada = { customerId: '0123456789abcdef01234567', name: 'Ada Lovelace', email: 'ada@example.com' };
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
let fetchMock;
beforeEach(() => { fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock); });

it('shows loading and the customer list using customerId', async () => {
  fetchMock.mockResolvedValue(response([ada]));
  render(<App />);
  expect(screen.getByText('Loading customers…')).toBeInTheDocument();
  expect(await screen.findByText(ada.name)).toBeInTheDocument();
  expect(screen.getByText(ada.customerId)).toBeInTheDocument();
});

it('adds a customer and displays the returned record', async () => {
  fetchMock.mockResolvedValueOnce(response([])).mockResolvedValueOnce(response(ada, 201));
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText('No customers yet.');
  await user.click(screen.getByRole('button', { name: 'Add customer' }));
  await user.type(screen.getByLabelText('Name'), ada.name);
  await user.type(screen.getByLabelText('Email'), ada.email);
  await user.click(screen.getByRole('button', { name: 'Save customer' }));
  expect(await screen.findByText(ada.name)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenLastCalledWith(expect.stringMatching(/\/api\/customers$/), expect.objectContaining({ method: 'POST', body: JSON.stringify({ name: ada.name, email: ada.email }) }));
});

it('edits a customer with PUT and both fields', async () => {
  fetchMock.mockResolvedValueOnce(response([ada])).mockResolvedValueOnce(response({ ...ada, name: 'Ada Byron' }));
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole('button', { name: `Edit ${ada.name}` }));
  await user.clear(screen.getByLabelText('Name'));
  await user.type(screen.getByLabelText('Name'), 'Ada Byron');
  await user.click(screen.getByRole('button', { name: 'Save customer' }));
  expect(await screen.findByText('Ada Byron')).toBeInTheDocument();
  expect(fetchMock).toHaveBeenLastCalledWith(expect.stringContaining(ada.customerId), expect.objectContaining({ method: 'PUT', body: JSON.stringify({ name: 'Ada Byron', email: ada.email }) }));
});

it('requires confirmation, supports cancel, and handles an empty 204 delete response', async () => {
  fetchMock.mockResolvedValueOnce(response([ada])).mockResolvedValueOnce({ ok: true, status: 204 });
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole('button', { name: `Delete ${ada.name}` }));
  expect(screen.getByRole('alertdialog')).toHaveTextContent('all their accounts');
  await user.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(fetchMock).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole('button', { name: `Delete ${ada.name}` }));
  await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete customer' }));
  expect(await screen.findByText('No customers yet.')).toBeInTheDocument();
  expect(fetchMock).toHaveBeenLastCalledWith(expect.stringContaining(ada.customerId), expect.objectContaining({ method: 'DELETE' }));
});

it('shows a load failure and retries', async () => {
  fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(response([ada]));
  const user = userEvent.setup();
  render(<App />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to reach');
  await user.click(screen.getByRole('button', { name: 'Retry' }));
  expect(await screen.findByText(ada.name)).toBeInTheDocument();
});

it('keeps form values on a rejected save and displays API errors', async () => {
  fetchMock.mockResolvedValueOnce(response([ada])).mockResolvedValueOnce(response({ detail: 'Email already exists' }, 409));
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole('button', { name: `Edit ${ada.name}` }));
  await user.click(screen.getByRole('button', { name: 'Save customer' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Email already exists'));
  expect(screen.getByLabelText('Email')).toHaveValue(ada.email);
});

it('opens the selected customer accounts and returns to customers', async () => {
  fetchMock.mockResolvedValueOnce(response([ada])).mockResolvedValueOnce(response([]));
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole('button', { name: `Accounts for ${ada.name}` }));
  expect(await screen.findByText('No accounts found.')).toBeInTheDocument();
  expect(fetchMock).toHaveBeenLastCalledWith(expect.stringContaining(`/customers/${ada.customerId}/accounts`), expect.any(Object));
  await user.click(screen.getByRole('button', { name: 'Back to customers' }));
  expect(screen.getByText(ada.name)).toBeInTheDocument();
});
