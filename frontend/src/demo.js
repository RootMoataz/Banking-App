// Public demo accounts. They are synthetic and the password is public on purpose.
// Keep in sync with ../DEMO.md and ../deploy/seed_demo.py (demo.test.js fails if they drift).
export const DEMO_PASSWORD = 'paper-demo-ledger-2026';
export const DEMO_ACCOUNTS = [
  { email: 'demo-admin@example.com', role: 'ADMIN', key: 'admin' },
  { email: 'demo-low@example.com', role: 'CUSTOMER', key: 'low' },
  { email: 'demo-standard@example.com', role: 'CUSTOMER', key: 'standard' },
  { email: 'demo-premium@example.com', role: 'CUSTOMER', key: 'premium' },
];
