// Mocks every call the app makes to the API. Nothing here reaches a real server.
export const FIXED_DATE = new Date('2026-10-03T10:00:00Z');
const TOKEN = 'fake-token-for-tests';

export const admin = { userId: 'u-admin', name: 'Demo Admin', email: 'demo-admin@example.com', role: 'ADMIN', customerId: null };
export const customer = { userId: 'u-cust', name: 'Asha Rao', email: 'demo-customer@example.com', role: 'CUSTOMER', customerId: 'c-1001' };

const customers = [
  { customerId: 'c-1001', name: 'Asha Rao', email: 'demo-customer@example.com', createdAt: '2026-09-01T09:00:00Z', marketingEnabled: true },
  { customerId: 'c-1002', name: 'Ben Carter', email: 'ben.carter@example.com', createdAt: '2026-09-12T09:00:00Z', marketingEnabled: false },
  { customerId: 'c-1003', name: 'Chen Wei', email: 'chen.wei@example.com', createdAt: '2026-09-20T09:00:00Z', marketingEnabled: true },
];
const accounts = [
  { accountId: 'acc-10010001', customerId: 'c-1001', userName: 'Asha Rao', accountType: 'Savings', balance: '12500.50', createdAt: '2026-09-02T09:00:00Z' },
  { accountId: 'acc-10010002', customerId: 'c-1001', userName: 'Asha Rao', accountType: 'Checking', balance: '0.00', createdAt: '2026-09-03T09:00:00Z' },
  { accountId: 'acc-10020001', customerId: 'c-1002', userName: 'Ben Carter', accountType: 'Savings', balance: '250000.00', createdAt: '2026-09-13T09:00:00Z' },
];
const transactions = [
  { txnId: 't-1', type: 'DEPOSIT', amount: '5000.00', balanceAfter: '5000.00', date: '2026-09-02T10:00:00Z' },
  { txnId: 't-2', type: 'WITHDRAW', amount: '250.00', balanceAfter: '4750.00', date: '2026-09-05T10:00:00Z' },
];

const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

// Call before page.goto. `user` is admin or customer; null means signed out.
export async function mockApi(page, user = null) {
  await page.clock.setFixedTime(FIXED_DATE);
  if (user) await page.addInitScript(token => sessionStorage.setItem('paper-maker-token', token), TOKEN);
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, '');
    const method = route.request().method();
    if (path === '/auth/me') return user ? json(route, user) : json(route, { detail: 'Not authenticated' }, 401);
    if (path === '/auth/login' || path === '/auth/register') return json(route, { token: TOKEN, user: user || customer });
    if (path === '/customers' && method === 'GET') return json(route, customers);
    if (/^\/customers\/[^/]+\/accounts$/.test(path)) return json(route, accounts.filter(item => item.customerId === path.split('/')[2]));
    if (path === '/accounts/premium') return json(route, accounts.filter(item => Number(item.balance) >= 100000));
    if (path === '/accounts') return json(route, accounts);
    if (/^\/accounts\/[^/]+\/transactions$/.test(path)) return json(route, transactions);
    if (path.startsWith('/notifications')) return json(route, []);
    return json(route, { detail: `No mock for ${method} ${path}` }, 404);
  });
}

// Wait until web fonts are loaded so screenshots do not depend on font timing.
export const settle = page => page.evaluate(() => document.fonts.ready);
