<div align="center">

<img src="assets/paper-maker-logo.png" alt="Paper Maker Banking App logo featuring the Monopoly Man holding banknotes" width="320" />

# Paper Maker Banking App

**React · Vite · FastAPI · MongoDB Atlas**

React frontend for the Paper Maker banking API

[Frontend](#the-react-frontend) · [Setup](#steps-to-initialize-this-branch-of-the-app) · [API](#the-api-at-a-glance) · [Messages](#customer-categories-and-messages) · [Architecture](#current-architecture-of-the-branch)

</div>

---

This branch adds a React frontend (in `frontend/`) on top of the Atlas-backed
FastAPI backend described below. See [The React frontend](#the-react-frontend)
to run it.

Paper Maker Banking App is a FastAPI backend for managing customers and their
accounts. It supports deposits, withdrawals, transfers between any two accounts,
idempotent retries, a transaction history for each account, a premium-accounts
list, customer search with balance categories, category-change notifications with
a marketing opt-in, and a transaction audit. Everything is stored in MongoDB
Atlas, so data survives a server restart. The original in-memory milestone
remains on `1_backend-rest-api-without-db`.

One customer can open several accounts. Each account starts at zero, and every
successful money operation leaves a transaction record. Routes, services, and
repositories handle HTTP requests, business rules, and storage respectively.

> **A note about security:** there is no login in this milestone. Anyone who can
> reach the API can read and change any record, and the audit cursor is not
> signed. Use sample customers and do not expose the server to an untrusted
> network. Notifications are stored for retrieval through the API; they are not
> sent by email or push, and loan messages do not indicate loan eligibility or
> approval.

## The React frontend

A Vite + React app in `frontend/` for the API below: customer list, add, edit and
confirmed delete; per-customer accounts with open, deposit, withdraw, transfer,
transaction history and account delete; and the premium-accounts list. It is
styled as a paper-and-banknote-green private ledger with serif headings.

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm test         # 19 tests, HTTP mocked, no database needed
npm run build
```

Start the backend first (see the steps below). The API URL defaults to
`http://localhost:8000`; set `VITE_API_BASE_URL` in `frontend/.env.local` to
change it. Money is sent as decimal strings with a fresh idempotency key per
deposit, withdrawal or transfer, and there are no automatic retries. Search,
notifications, marketing opt-in and audit views are API-only for now. More
detail is in `frontend/README.md`.

## Steps to initialize this branch of the App

Use Python 3.12 (the version this branch was built and tested on), Git, and a
MongoDB Atlas cluster with a database user that can read and write the chosen
database and create its indexes. Allow your machine's IP in Atlas Network Access.

```sh
git clone --branch 2_api-atlas-claude https://github.com/RootMoataz/Paper-Maker-Banking-App.git
cd Paper-Maker-Banking-App
python -m venv .venv
```

Activate the environment:

| Terminal | Command |
| --- | --- |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| macOS / Linux | `source .venv/bin/activate` |

```sh
python -m pip install -r requirements.txt
```

The repository has no `.env.example`. Create a `.env` file in the project root
(next to `requirements.txt`) and fill in your connection details locally:

```dotenv
MONGODB_URI=mongodb+srv://USERNAME:PASSWORD@YOUR-CLUSTER.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=paper_maker
JWT_SECRET=AT-LEAST-32-RANDOM-CHARACTERS
# JWT_EXPIRATION_MINUTES=60
# ADMIN_EMAIL=staff@example.com
# ADMIN_PASSWORD=A-STRONG-PASSWORD
# LOW_BALANCE_THRESHOLD=100.00
# PREMIUM_BALANCE_THRESHOLD=10000.00
# CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

`.env` is ignored by Git. Never paste a working connection string into the
README, Postman, or a commit, and URL-encode a password that contains reserved
characters. Only `MONGODB_URI` and `JWT_SECRET` (32 characters or more, no
default; startup fails without it) are required. If `ADMIN_EMAIL` and
`ADMIN_PASSWORD` are both set, startup creates that staff (ADMIN) login unless the
email already has one (a warning is logged if that email belongs to a customer);
`ADMIN_PASSWORD` must be at least 12 characters or startup fails; the password is
never logged. The commented lines show the
defaults: delete the `#` to change one, or leave the line out (never empty) to
keep the default. An empty or invalid value stops startup.

| Setting | Meaning |
| --- | --- |
| `MONGODB_URI` | Required. The app and the tests refuse to start without it. |
| `MONGODB_DB` | Database name. Defaults to `paper_maker`. |
| `LOW_BALANCE_THRESHOLD` | Defaults to `100.00`. An amount from 0.00 to 99999999.99 with at most two decimals. |
| `PREMIUM_BALANCE_THRESHOLD` | Defaults to `10000.00`. Must be larger than the low threshold. Also the default `threshold` of the premium-accounts list. |
| `CORS_ALLOWED_ORIGINS` | Comma-separated browser origins, such as `http://localhost:3000`: scheme, host, and optional port, with no path, trailing slash, or `*`. Defaults to `http://localhost:3000,http://localhost:5173`. |

Shell environment variables take precedence over `.env`. The file is read
without being copied into the process environment, and it is found relative to
the code, so it works from any directory.

```sh
python -m uvicorn app.main:app --reload
```

Open [Swagger UI](http://127.0.0.1:8000/docs), expand an endpoint, and choose
**Try it out**. The schema is at `/openapi.json` and ReDoc is at `/redoc`. Startup
creates the required indexes (safe to repeat), and an unavailable database stops
startup; there is no in-memory fallback. To create the indexes ahead of time, run
`python scripts/setup_indexes.py` once with the `.env` in place.

If PowerShell cannot activate the environment, invoke Python directly:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

MongoDB must support transactions: Atlas or another replica set works; a
standalone local MongoDB server does not. Only Atlas was used and tested here.

### CORS

The default origins let a browser frontend on `localhost:3000` or `localhost:5173`
call the API. Any method is allowed, along with the `Content-Type` and
`Idempotency-Key` and `Authorization` request headers; no cookies or credentials are used. A request
from any other origin gets no CORS headers, so the browser blocks it. Postman and
curl are not affected.

### Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Startup fails with a TLS or connection timeout error | A VPN can break the Atlas TLS handshake. Disconnect the VPN, and confirm your IP is allowed in Atlas Network Access. |
| Startup or `setup_indexes.py` fails with an index conflict | Another branch already created incompatible indexes in the same database. Set a separate `MONGODB_DB` for this branch. |
| `RuntimeError: MONGODB_URI is not set` | Create the `.env` described above, or set the variable in your shell. |
| Port 8000 is already in use | Stop the other server, or add `--port 8001` to the uvicorn command. |
| PowerShell blocks `Activate.ps1` | Use the `.venv\Scripts\python.exe` commands above. |

## A small banking session

Create a customer:

```json
{"name": "Moataz Hikal", "email": "moataz@example.com"}
```

Use the returned `customerId` to open an account:

```json
{"customerId": "66f9a1b2c3d4e5f6a7b8c9d0", "accountType": "SAVINGS"}
```

The ID above illustrates the format. Always use the IDs your API returns; all of
them (`customerId`, `accountId`, `txnId`) are 24-character hexadecimal MongoDB
ObjectId strings. `userId` remains an alias for `customerId`, and
`POST /api/users` still works for compatibility.

| Action | Money in | Money out | Account balance |
| --- | ---: | ---: | ---: |
| Open account | — | — | 0.00 |
| Deposit | 100.00 | — | 100.00 |
| Withdraw | — | 25.00 | 75.00 |
| Withdraw 76.00 | — | Rejected | 75.00 |

The rejected request returns **400 Insufficient funds** and changes nothing.
Deposit and withdrawal both accept `{"amount": "25.00"}`; JSON numbers work too.
Money is validated with Decimal, stored as whole cents, and returned as a
string with two decimal places, which keeps values such as `0.10 + 0.20` exact.

<details>
<summary>Example account response after the session</summary>

```json
{
  "accountId": "66f9a1b2c3d4e5f6a7b8c9d1",
  "customerId": "66f9a1b2c3d4e5f6a7b8c9d0",
  "userId": "66f9a1b2c3d4e5f6a7b8c9d0",
  "userName": "Moataz Hikal",
  "accountType": "SAVINGS",
  "balance": "75.00",
  "createdAt": "2026-09-29T12:00:00Z"
}
```

</details>

## The API at a glance

All paths start with `/api`. Everything except `/auth/register`, `/auth/login` and
`/public/health` needs `Authorization: Bearer <token>`; a missing, invalid or
expired token returns 401 (see [Login and roles](#login-and-roles)). A malformed ID returns 422, and a well-formed ID
that does not exist returns 404 (the audit filters return an empty result
instead).

| Method | Path | Purpose | Success |
| --- | --- | --- | --- |
| POST | `/auth/register` | Register: creates a customer and a CUSTOMER login, returns a token | 201 |
| POST | `/auth/login` | Log in with email and password, returns a token | 200 |
| GET | `/auth/me` | The logged-in user: `email`, `role`, `customerId`, `name` | 200 |
| GET | `/public/health` | Public liveness check | 200 |
| GET / POST | `/customers` | List or create customers | 200 / 201 |
| GET | `/customers/search` | Search by name, email, category, or total balance | 200 |
| GET / PUT / DELETE | `/customers/{id}` | Read, replace, or delete a customer and their accounts | 200 / 200 / 204 |
| GET | `/customers/{id}/accounts` | List their accounts | 200 |
| PATCH | `/customers/{id}/preferences` | Opt in to or out of marketing | 200 |
| GET | `/customers/{id}/notifications` | List stored messages, newest first | 200 |
| GET / POST | `/accounts` | List or open accounts | 200 / 201 |
| GET | `/accounts/premium` | Accounts at or above a balance, highest first | 200 |
| GET / PUT / DELETE | `/accounts/{id}` | Read, change the type of, or delete an account | 200 / 200 / 204 |
| POST | `/accounts/{id}/deposit` | Deposit a positive amount | 200 |
| POST | `/accounts/{id}/withdraw` | Withdraw up to the current balance | 200 |
| GET | `/accounts/{id}/transactions` | Account history, oldest first | 200 |
| POST | `/transfers` | Move money between two accounts | 200 |
| GET | `/audit/transactions` | Search history by customer, account, and date | 200 |
| POST | `/users` | Compatibility alias for creating a customer | 201 |

PUT customer requires both `name` and `email` (names cannot be blank; emails
must be valid and unique, ignoring case). PUT account accepts only
`{"accountType": "CURRENT"}` (a nonblank string up to 50 characters). Ownership
and balance cannot be edited. Editing a customer's name also updates the name
shown on their accounts. Extra or missing fields return 422.

### Login and roles

Tokens are HS256 JWTs (`sub` = user id, `exp` after `JWT_EXPIRATION_MINUTES`, 60 by
default). Passwords are 8 to 72 bytes, must differ from the email, and are stored as
salted scrypt hashes. The email is the username, case-insensitive; a duplicate
returns 409. A wrong email and a wrong password return the same 401. Every request
reloads the user from the database, so a deleted or disabled user, or a changed
role, takes effect at once. Registration always creates a CUSTOMER.

- **ADMIN** (staff): every endpoint in the table above.
- **CUSTOMER**: their own customer record, accounts and notifications, opening an
  account for themself, and transfers from their own accounts. Another customer's
  object returns 404 (as if it did not exist); anything else, such as listing or
  searching customers, deposits, withdrawals, premium, audit, or deleting, returns 403.

### Limits and pagination

`GET /customers`, `GET /accounts`, and `GET /accounts/{id}/transactions` accept an
optional `limit` (1 to 200). Without it, everything is returned; with it, only
the first `limit` items. Search, premium, notifications, and audit always cap at
`limit` (1 to 200, default 50). Values outside 1 to 200 return 422.

### Search

`GET /api/customers/search` filters combine, and results come back oldest
customer first. Each result shows `customerId`, `name`, `email`, `totalBalance`,
and `category`. A customer's total is the sum of all their accounts (0.00 with
none).

| Parameter | Meaning |
| --- | --- |
| `name`, `email` | Case-insensitive substring, up to 100 characters. Characters such as `.` match themselves. |
| `category` | `LOW`, `STANDARD`, or `PREMIUM` (see [categories](#customer-categories-and-messages)) |
| `minBalance`, `maxBalance` | Bounds on the total balance, both inclusive |
| `limit` | 1 to 200, default 50 |

Customer responses also include `marketingEnabled`.

### Premium accounts

`GET /api/accounts/premium` lists accounts whose own balance is at least
`threshold`, highest first (equal balances: oldest account first). Each result is
an ordinary account. This list is per account; the `PREMIUM` category is about a
customer's total across all accounts.

| Parameter | Meaning |
| --- | --- |
| `threshold` | Inclusive, 0 to 99999999.99 with at most two decimals. Defaults to `PREMIUM_BALANCE_THRESHOLD`. |
| `limit` | 1 to 200, default 50 |

### Transfers

`POST /api/transfers` moves money between any two different accounts, of the same
customer or of different customers:

```json
{
  "fromAccountId": "66f9a1b2c3d4e5f6a7b8c9d1",
  "toAccountId": "66f9a1b2c3d4e5f6a7b8c9d2",
  "amount": "25.00"
}
```

The amount follows the deposit rules, and no other fields are accepted. One
database transaction debits the source, credits the destination, and writes one
record to each account's history, so either everything happens or nothing does.

```json
{
  "transferId": "66f9a1b2c3d4e5f6a7b8c9e0",
  "fromAccountId": "66f9a1b2c3d4e5f6a7b8c9d1",
  "toAccountId": "66f9a1b2c3d4e5f6a7b8c9d2",
  "amount": "25.00",
  "fromBalanceAfter": "50.00",
  "toBalanceAfter": "25.00",
  "date": "2026-09-29T12:05:00Z"
}
```

The source history gets a `TRANSFER_OUT` record and the destination a
`TRANSFER_IN` record. Both carry the shared `transferId`, `fromAccountId`, and
`toAccountId`; each has its own `txnId`, the `customerId` of its account's owner,
and the `balanceAfter` of its own account. `date` in the response is the
`TRANSFER_OUT` record's date. `toBalanceAfter` is `null` for a customer who
transfers to an account that is not theirs (so a transfer cannot reveal a
stranger's balance); staff, and customers moving money between their own
accounts, always get both balances.

| Situation | Result |
| --- | --- |
| Same account for source and destination | 422 |
| Source or destination does not exist | 404 |
| Source balance is smaller than the amount (no overdraft) | 400 `Insufficient funds` |
| Destination would exceed 99,999,999.99 | 400 |
| `Idempotency-Key` reused for a different request | 409 |

### Idempotency keys

Deposit, withdraw, and transfer accept an optional `Idempotency-Key` header (1 to
200 printable ASCII characters, not starting with a space). It lets a client
retry after a lost response without moving money twice. Keys are scoped to one
account (the source account for a transfer) and never expire.

| Request | Result |
| --- | --- |
| No key | Every request is a new operation; two identical keyless deposits both apply. |
| New key | The operation runs and, if it succeeds, is recorded with the key. A failed attempt records nothing, so a retry runs again. |
| Same key, same account, same operation and amount | The first result is replayed. No balance change, transaction, or notification is added. |
| Same key and account, different operation, amount, or destination | 409 |
| Same key on another account | Independent; runs as a new operation. |

A replayed deposit or withdrawal returns the account with the balance right after
the original operation. If the account has been deleted since, it returns the
original transaction record instead, which has `balanceAfter` and no `balance`, so
clients that retry should accept either shape. A transfer replay is rebuilt from
its stored records, even after either account was deleted.

### Transaction audit

`GET /api/audit/transactions` returns the records of a customer (across all their
accounts) or of one account, oldest first, then by `txnId`. A transfer appears as
`TRANSFER_OUT` under the source and `TRANSFER_IN` under the destination. It is
read page by page.

| Parameter | Meaning |
| --- | --- |
| `customerId`, `accountId` | At least one is required (both may be given); otherwise 422 |
| `from` | Start time, inclusive, ISO 8601 |
| `to` | End time, exclusive, ISO 8601 |
| `limit` | 1 to 200, default 50 |
| `cursor` | The previous page's `nextCursor` |

The response is `{"items": [...], "nextCursor": "..."}`; `nextCursor` is `null`
on the last page. To read the next page, send the same filters with `cursor` set:

```text
GET /api/audit/transactions?customerId=RETURNED_ID&from=2026-09-01T00:00:00Z&limit=50
```

- A time without an offset is read as UTC. Write `Z` in URLs, or encode a `+`
  offset as `%2B02:00`: a bare `+` becomes a space and returns 422.
- Transactions survive deleting their account and customer, so deleted IDs still
  return their history, and no existence check is made for either ID.
- A cursor is tied to the filters it was issued for. Writing the same filters
  differently (ID letter case, `Z` versus `+00:00`) is accepted; a cursor used
  with different filters, or a malformed one, returns 422. `limit` may change
  between pages.
- The cursor is not signed: it guards against mixing up filters, not forgery.
- Order comes from the stored time and the transaction ID. Within one account the
  app keeps each new record later than the previous one; across accounts, exact
  ordering assumes one app server or synchronized server clocks.

A transaction record has `txnId`, `accountId`, `customerId`, `type`, `amount`,
`balanceAfter`, `date` (UTC), and `transferId`, `fromAccountId`, `toAccountId`
(`null` except on transfer records). `type` is `DEPOSIT`, `WITHDRAW`,
`TRANSFER_OUT`, `TRANSFER_IN`, or `ACCOUNT_CLOSED`.

## Customer categories and messages

A customer's category uses the combined balance of all their accounts, with the
default thresholds below (set by `LOW_BALANCE_THRESHOLD` and
`PREMIUM_BALANCE_THRESHOLD`).

| Category | Combined balance | On entry |
| --- | --- | --- |
| LOW | Below 100.00 | `LOW_BALANCE_ALERT`; `LOW_BALANCE_MARKETING` too if opted in |
| STANDARD | 100.00 to below 10,000.00 | No message |
| PREMIUM | 10,000.00 or more | `PREMIUM_MARKETING`, only if opted in |

Exactly 100.00 is `STANDARD` and exactly 10,000.00 is `PREMIUM`.

Marketing starts disabled. Enable it with:

```http
PATCH /api/customers/RETURNED_ID/preferences
Content-Type: application/json

{"marketingEnabled": true}
```

A message is stored only when a deposit, withdrawal, or transfer moves a
customer's total into another category. Staying in one category, or replaying an
idempotent request, stores nothing. A transfer between one customer's own
accounts leaves their total unchanged, so it stores nothing; between different
customers, each is evaluated separately. Opting in does not backfill earlier
marketing; opting out stops future marketing while low-balance alerts remain
active. There is no time-based cooldown, so returning to LOW can create a new
alert. If a preference change arrives during a money operation, whichever commits
first wins.

| Kind | `templateId` | `message` |
| --- | --- | --- |
| `LOW_BALANCE_ALERT` | `low-balance-v1` | Your combined account balance is below 100.00. |
| `LOW_BALANCE_MARKETING` | `loan-options-v1` | Explore available loan options and learn how to apply. Eligibility and approval depend on assessment. |
| `PREMIUM_MARKETING` | `premium-v1` | Your combined balance has reached 10,000.00. Explore available premium banking benefits. |

These are workshop templates: they offer no product, rate, or approval.

`GET /api/customers/{id}/notifications` lists a customer's messages, newest
first, optionally filtered by `kind` and capped by `limit` (1 to 200, default
50). Each message shows `notificationId`, `customerId`, `categoryVersion`,
`category`, `kind`, `templateId`, `message`, `transactionId` (the record that
caused it), and `createdAt`. `categoryVersion` counts the customer's category
changes, including changes to `STANDARD`. Messages are stored in the same
database transaction as the balance change, and `(customerId, categoryVersion,
kind)` is unique, so a retried transaction cannot store a message twice.

## Money and record rules

| Situation | Response |
| --- | --- |
| Zero, negative, non-finite, fractional-cent, or oversized amount | 422 |
| Transfer from an account to itself | 422 |
| Invalid ID, missing or extra fields, or invalid JSON, parameter, date, or cursor | 422 |
| Audit request without `customerId` or `accountId` | 422 |
| Customer or account does not exist | 404 |
| Withdrawal or transfer exceeds the source balance | 400 |
| Deposit or transfer would push a balance above 99,999,999.99 | 400 |
| Email already exists, ignoring case | 409 |
| Delete an account that still has money | 409 |
| Idempotency key reused for a different request | 409 |

Business errors return `{"detail": "message"}`. A 422 has two shapes: business
errors in the audit (missing IDs, cursor problems) carry a string `detail`, while
request validation errors carry FastAPI's `detail` list with the affected fields.
Failed operations leave balances, history, and notifications untouched.

**Delete an account.** Withdraw its remaining balance first; DELETE then returns
204. Its history stays available through the audit, but
`/accounts/{id}/transactions` returns 404 once the account is gone.

**Delete a customer.** The customer and all their accounts are removed in one
database transaction, whatever the balances, so no account is left without an
owner. Each account with a balance gets an `ACCOUNT_CLOSED` transaction recording
the amount removed (balance after 0.00). Transactions and notifications stay
stored, and the audit still returns the transactions; notifications are no longer
readable through the API (their endpoint returns 404 for a deleted customer).
Deleted IDs are never reused.

Operations on the same customer are synchronized, including changes to different
accounts and preference changes, and each balance check is part of the update, so
two withdrawals or transfers cannot spend the same money.

## Current Architecture of the Branch

### Record Relationships

```mermaid
flowchart LR
    C[Customer] --> O[owns many] --> A[Account]
    A --> R[records many] --> T[Transaction]
    C --> N[receives many] --> M[Stored notification]
    classDef relationship fill:none,stroke:none;
    class O,R,N relationship;
```

### Code Structure

```mermaid
flowchart TD
    Client[Swagger or Postman] --> Routes[FastAPI routes]
    Routes --> Services[Customer and account services]
    Services --> Policy[Category and message rules]
    Services --> Repositories[Repositories]
    Repositories --> Atlas[(MongoDB Atlas)]
```

| File | Responsibility |
| --- | --- |
| [`app/main.py`](app/main.py) | HTTP routes, response codes, CORS, and Swagger descriptions |
| [`app/auth.py`](app/auth.py) | Password hashing, JWT issue/verify, registration, login, admin bootstrap |
| [`app/models.py`](app/models.py) | Request validation and response fields |
| [`app/services.py`](app/services.py) | Customer/account rules, transfers, idempotency, search, preferences, notifications, and audit |
| [`app/repositories.py`](app/repositories.py) | MongoDB reads and writes for customers, accounts, transactions, and notifications |
| [`app/notifications.py`](app/notifications.py) | Message kinds and texts for each category change |
| [`app/audit.py`](app/audit.py) | Audit cursors and the filter fingerprint |
| [`app/config.py`](app/config.py) | Settings from the environment and `.env` |
| [`app/db.py`](app/db.py) | MongoDB connection and index creation |
| [`app/money.py`](app/money.py) | Conversion between decimal amounts and whole cents |
| [`scripts/setup_indexes.py`](scripts/setup_indexes.py) | Creates the indexes ahead of time |

The [dependency map](docs/dependencies.md) explains transaction boundaries,
transfers, and record retention.

## Tests and demonstration

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -m "not atlas" -q
```

The offline tier needs no database. The rest need `MONGODB_URI` (from the
environment or `.env`) and fail without it rather than skip. They create a
throwaway database named `paper_maker_test_<hex>` on that cluster and drop it at
the end; fixtures refuse to clear any other database. Thresholds are pinned to
the defaults, so a local `.env` does not change results.

| Command | Runs |
| --- | --- |
| `python -m pytest -m "not atlas" -q` | Offline tier only (no Atlas, no VPN issues) |
| `python -m pytest -m atlas -q` | Tests that use the Atlas test database |
| `python -m pytest -q` | Full suite; a few minutes against Atlas |

`requirements-lock.txt` records the tested dependency versions; install it
instead of `requirements-dev.txt` to use those exact versions.

The suite covers money operations, transfers, idempotency, the premium list,
CRUD and cascade deletes, search and category boundaries, notifications, audit
paging, CORS, settings, and the Postman request sequence. It sends requests
through FastAPI's TestClient and does not launch Swagger or Postman. See
[test coverage](docs/swagger-testing.md#test-coverage) for details and limits.

For a manual walkthrough, follow the [Swagger test steps](docs/swagger-testing.md),
or import the [Postman collection](postman/Banking-App.postman_collection.json)
(31 requests) and run it in its stored order. It creates a fresh email, captures
IDs, and deletes its sample customer and accounts at the end (their transactions
and notifications remain stored). Its search and notification checks assume the
default thresholds, and its premium-accounts check only verifies ordering on a
database with many other accounts.

## Branches

| Branch | Contents |
| --- | --- |
| `1_backend-rest-api-without-db` | In-memory backend milestone |
| `2_api-atlas-claude` | MongoDB Atlas storage |
| `3_react-frontend` | This branch: React frontend on the Atlas backend |
