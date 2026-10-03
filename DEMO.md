# Paper Maker demo accounts

Live site: <http://moataz-hikal-s3bucket.s3-website-us-east-1.amazonaws.com>

Paper Maker is a small banking app built to learn how deposits, transfers, roles and audit records fit together.
These accounts let you sign in and try it without registering.

**What to know first**

- The data is synthetic. No real money, cards or people are involved, and this is not a real bank.
- The demo accounts are public, and so is their password. Anyone can sign in with them and change things.
- The data can be reset at any time, so what you did may disappear. That is expected.
- The first request after a quiet period can take a few seconds while the server wakes up.
- Do not enter real personal data anywhere on the site.

## Demo accounts

All four accounts use the same password: `paper-demo-ledger-2026`

The sign-in page also lists these accounts and this password, with buttons to fill the form.

| Email | Role | Balance category | What it can do |
| --- | --- | --- | --- |
| `demo-admin@example.com` | ADMIN | none | Staff view: every customer, open accounts, deposit, withdraw, add and delete customers, delete empty accounts, the premium accounts list. Search and the audit trail are available through the API. |
| `demo-low@example.com` | CUSTOMER | LOW (total under 100.00) | Own accounts only: Checking and Savings with a small history and a low-balance alert. |
| `demo-standard@example.com` | CUSTOMER | STANDARD (100.00 up to 10000.00) | Own accounts only: Checking and Savings with a short history of deposits, a withdrawal and a transfer. |
| `demo-premium@example.com` | CUSTOMER | PREMIUM (total 10000.00 or more) | Own accounts only: Checking and Savings; opted in to marketing, so a premium message is waiting. Its Savings account appears in the admin's premium list. |

## Things to try

**As the admin (`demo-admin@example.com`)**

1. Open the customer list and see all three demo customers.
2. Open a customer, look at their accounts and read an account's transaction history.
3. Deposit into and withdraw from an account, then watch the balance and history change.
4. Open the premium accounts list and see which accounts are at or above 10000.00.
5. Add a customer of your own, open an account for them, then delete the customer to see the closing record it leaves behind.

**As a customer (`demo-low@example.com`, `demo-standard@example.com` or `demo-premium@example.com`)**

1. Open My accounts and read each account's history; every line shows the balance after it.
2. Transfer money between the two accounts. Try more than the balance to see the error.
3. Open another account for yourself.
4. Read the notifications. As the low customer, withdraw a little more to trigger or see the low-balance alert; the premium customer has a marketing message because they opted in.
5. If you are comfortable with an API client, call `GET /api/customers` with this account's token. The server answers 403: a customer can only reach their own data.

## The lockout rule

Five wrong passwords for one email lock that email for 15 minutes, even for the right password. The sign-in page
shows a countdown. This applies to the demo accounts too, so a typo streak by one visitor can briefly lock an account
for everyone; try another demo account or wait.

## Source

The code is in this repository. The demo accounts are created by `deploy/seed_demo.py`, which can also restore them
after visitors have changed the data.
