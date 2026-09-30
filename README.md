<div align="center">

<img src="assets/paper-maker-logo.png" alt="Paper Maker Banking App logo featuring the Monopoly Man holding banknotes" width="320" />

# Paper Maker Banking App

**Python · FastAPI · MongoDB Atlas**

Backend REST API with MongoDB Atlas

[Setup](#steps-to-initialize-this-branch-of-the-app) · [API](#the-api-at-a-glance) · [Messages](#customer-categories-and-messages) · [Architecture](#current-architecture-of-the-branch)

</div>

---

Paper Maker Banking App manages customers, their accounts, and the money moving
in and out. This branch stores records in MongoDB Atlas, so restarting the API
keeps balances and transaction history. The original in-memory milestone remains
on `1_backend-rest-api-without-db`.

One customer can own several accounts. Every account starts at zero. A deposit
or withdrawal saves the account balance, combined customer balance, transaction,
and any triggered messages together in one database transaction.

This workshop backend has no login or protected routes. Use sample customers.
Notifications are stored for retrieval through the API; they are not sent by
email or push, and loan messages do not indicate loan eligibility or approval.

## Steps to initialize this branch of the App

Use Python 3.10 or newer, Git, and an Atlas cluster with a database user that can
read and write the chosen database and create its indexes. Allow your machine's
IP in Atlas Network Access.

```sh
git clone --branch 2_backend-rest-api-mongodb-atlas https://github.com/RootMoataz/Paper-Maker-Banking-App.git
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

Copy `.env.example` to `.env` and fill in your connection details locally:

```dotenv
MONGODB_URI=mongodb+srv://USERNAME:PASSWORD@YOUR-CLUSTER.mongodb.net/?retryWrites=true&w=majority
MONGODB_DATABASE=paper_maker
```

Use a URL-encoded password if it contains characters reserved in URLs. `.env` and
its local variants are ignored by Git. `.env.example` contains placeholders only.
Never paste a working connection string into README, Postman, or a commit.

```sh
python -m uvicorn app.main:app --reload
```

Open [Swagger UI](http://127.0.0.1:8000/docs). The schema is at `/openapi.json` and
ReDoc is at `/redoc`. Startup checks the database and creates the required indexes.
An unavailable database stops startup; there is no in-memory fallback.

If PowerShell cannot activate the environment, invoke Python directly:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

MongoDB must support transactions: Atlas or a local replica set works; a standalone
local MongoDB server does not. Multiple API processes use the same persisted data.

## A small banking session

Create a customer:

```json
{"name": "Moataz Hikal", "email": "moataz@example.com"}
```

Use the returned `customerId` to open an account:

```json
{"customerId": "507f1f77bcf86cd799439011", "accountType": "SAVINGS"}
```

The ID above illustrates the format. Always use the ID returned by your API.
All IDs are MongoDB ObjectId strings, including `accountId` and `txnId`.
`userId` remains an alias for `customerId`, and `POST /api/users` still works.

| Action | Money in | Money out | Account balance |
| --- | ---: | ---: | ---: |
| Open account | — | — | 0.00 |
| Deposit | 100.00 | — | 100.00 |
| Withdraw | — | 25.00 | 75.00 |
| Withdraw 76.00 | — | Rejected | 75.00 |

Both deposit and withdrawal accept `{"amount":"25.00"}`. JSON numbers work too.
Money is validated with Decimal, stored as integer cents, and returned as a
string with two decimal places. A rejected operation leaves all records unchanged.

## The API at a glance

All paths below start with `/api`.

| Method | Path | Purpose |
| --- | --- | --- |
| POST / GET | `/customers` | Create or list/search active customers |
| GET / PUT / DELETE | `/customers/{id}` | Read, edit, or archive a customer |
| GET | `/customers/{id}/accounts` | List their active accounts |
| PATCH | `/customers/{id}/preferences` | Change `marketingEnabled` |
| GET | `/customers/{id}/notifications` | Retrieve stored messages |
| POST / GET | `/accounts` | Open or list active accounts |
| GET / PUT / DELETE | `/accounts/{id}` | Read, edit type, or close an account |
| POST | `/accounts/{id}/deposit` | Deposit a positive amount |
| POST | `/accounts/{id}/withdraw` | Withdraw up to the current balance |
| GET | `/accounts/{id}/transactions` | History, including closed accounts |
| GET | `/audit/transactions` | Search history by customer, account, and date |
| GET | `/audit/transactions/{id}` | Retrieve a transaction by its ID |

Creating a record returns 201, reading/editing returns 200, and successful
closure/archival returns 204. PUT customer requires both name and email;
PUT account accepts only `accountType`. Balance and ownership cannot be edited.

### Search and pagination

`GET /api/customers?search=moataz&category=PREMIUM` searches literal name/email
text, ignoring case. Categories use the combined balance of the customer's accounts.
Customer responses include `totalBalance`, `category`, and `marketingEnabled`.

List endpoints accept `offset` (default 0) and `limit` (default 50, maximum 100).
Responses remain arrays. Customers/accounts are oldest first, transactions oldest
first, and notifications newest first, with ObjectId breaking timestamp ties.
Pagination is not a frozen snapshot while other requests change records.

### Transaction audit

Example filter:

```text
/api/audit/transactions?customerId=RETURNED_ID&from=2026-09-01T00:00:00Z&to=2026-10-01T00:00:00Z
```

Add `accountId` to narrow it further. Filters combine with AND. Dates must include
a timezone; `from` is inclusive and `to` exclusive. Equal or reversed ranges
return 422. Transactions retain customerId, accountId, type, amount, resulting
account balance, and UTC date. MongoDB stores timestamps with millisecond precision.

## Customer categories and messages

| Category | Combined balance | On entry |
| --- | --- | --- |
| LOW | Below 100.00 | Balance alert; loan-options marketing if opted in |
| STANDARD | 100.00 to below 10,000.00 | No message |
| PREMIUM | 10,000.00 or more | Premium welcome/benefits marketing if opted in |

Marketing starts disabled. Enable it with:

```http
PATCH /api/customers/RETURNED_ID/preferences
Content-Type: application/json

{"marketingEnabled": true}
```

A customer with no accounts receives no messages. Opening their first account
creates the initial low-balance alert and any opted-in marketing. Further
zero-balance accounts do not repeat it.

After that, messages trigger only when the combined balance enters another
category. Returning to LOW after leaving it can create a new alert; there is no
time-based cooldown. Opting in does not backfill earlier marketing. Opting out
stops future marketing while operational low-balance alerts remain active.

Example low-balance marketing:

> Explore available loan options and learn how to apply. Eligibility and approval depend on assessment.

Use `GET /api/customers/{id}/notifications`, optionally filtered by `kind`:
`LOW_BALANCE_ALERT`, `LOW_BALANCE_MARKETING`, or `PREMIUM_MARKETING`.
Messages record their category version and triggering transaction when applicable.
A unique index prevents duplicates from transaction retries. These are workshop
templates; the app does not assess credit or offer specific loan products.

## Money and record rules

| Situation | Response |
| --- | --- |
| Zero, negative, non-finite, fractional-cent, or oversized amount | 422 |
| Invalid ObjectId, missing/extra fields, or invalid date/filter | 422 |
| Well-formed ID without an accessible record | 404 |
| Withdrawal exceeds balance | 400 |
| Deposit exceeds the 99,999,999.99 per-account balance limit | 400 |
| Combined balance exceeds signed 64-bit cents storage | 400 |
| Email already exists, ignoring case | 409 |
| Close an account with money, or archive a customer with active accounts | 409 |
| Database operation unavailable | 503, with sanitized details |

To close an account, withdraw its remaining balance first. DELETE then marks it
closed; history stays available. A customer can be archived after all their
accounts are closed. Archived records are excluded from active CRUD/search,
but audit records and email uniqueness are retained. This is archival, not erasure.

Transactions synchronize competing operations for the same customer, including
changes to different accounts and marketing preferences. Separate repeated HTTP
requests are separate operations; this API does not implement idempotency keys.

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
    Client[Swagger or Postman] --> Routes[Customer, account and reporting controllers]
    Routes --> Services[Banking and audit services]
    Services --> Policy[Category and message rules]
    Services --> Repositories[Repositories]
    Repositories --> Atlas[(MongoDB Atlas)]
```

| File | Responsibility |
| --- | --- |
| `app/main.py` | App lifecycle and shared error handling |
| `app/routes.py` | Customer/account controllers |
| `app/reporting_routes.py` | Audit, preferences, and notifications controllers |
| `app/services.py` | Banking rules and transaction orchestration |
| `app/repositories.py` | Customer/account database operations |
| `app/audit.py` | Transaction storage and history queries |
| `app/notifications.py` | Category rules, templates, and stored notifications |
| `app/models.py` | Input validation and response models |
| `app/config.py`, `app/database.py` | Local settings, connections, indexes, sessions |

The [dependency map](docs/dependencies.md) explains transaction boundaries and
record retention.

## Tests and demonstration

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -m "not integration" -q
```

Integration tests need a separate transaction-capable database. Add these locally:

```dotenv
MONGODB_TEST_URI=mongodb://127.0.0.1:27018/?replicaSet=paperMakerTest
MONGODB_TEST_DATABASE=paper_maker_test_local
```

For Atlas tests, use a separate test URI/database with sufficient permissions.
The database prefix must begin with `paper_maker_test_` and differ from the
application database. Fixtures append a random suffix and delete only their own
generated databases. Never use customer data for tests.

```sh
python -m pytest -m integration -q
python -m pytest -q
```

Without test configuration, integration tests are explicitly skipped. A skipped
run does not verify persistence. `requirements-lock.txt` records the tested versions.

Import the [Postman collection](postman/Banking-App.postman_collection.json) for
the complete workflow, or follow the [Swagger walkthrough](docs/swagger-testing.md).
The collection generates a fresh sample email and captures IDs. Its final cleanup
archives sample records while retaining audit history.

The automated collection replay exercises HTTP requests and response values; it
does not launch Postman or execute its JavaScript. Tests cover precision, limits,
concurrency, rollback, retry duplicates, category boundaries, preferences, audit
filters, and record retention. Live Atlas verification is separate from local
replica-set integration testing.
