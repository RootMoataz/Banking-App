# MongoDB Atlas milestone

Status: approved and implemented. Verification results are in docs/swagger-testing.md.

Branch: `2_backend-rest-api-mongodb-atlas`

## Purpose and agreed scope

Move the existing FastAPI banking API from process memory to MongoDB Atlas.
Keep customer and account CRUD, deposits, withdrawals, and transaction history.
Add the instructor's customer search, customer balance categories, audit queries,
and notification logic. Swagger and Postman remain the demonstration clients.

The instructor's Atlas direction replaces the assignment's suggested MySQL
storage. The original no-database branch remains available as milestone one.
React, authentication, transfers, and actual email/push delivery are outside
this milestone. This is a workshop API without protected routes; use sample data.

The agreed category rules use the customer's combined balance across accounts:

| Category | Combined balance |
| --- | --- |
| LOW | Below 100.00 |
| STANDARD | At least 100.00 and below 10,000.00 |
| PREMIUM | At least 10,000.00 |

Crossing into another category triggers notification logic. Repeated operations
inside one category do not generate another category message. Low-balance
marketing may describe available loan options without claiming approval,
prequalification, or eligibility.

## Storage and code boundaries

Use the official PyMongo driver with synchronous repositories, matching the
existing synchronous FastAPI handlers. Open one MongoClient per application
process during application lifespan and close it at shutdown. Fail startup with
a sanitized message if configuration or the database connection is unavailable;
do not silently fall back to memory.

Keep controllers, services, repositories, and validation separate. Introduce
focused modules for database configuration, auditing, and notifications instead
of placing the new behavior entirely in main.py. Database operations and sessions
belong in repositories; category decisions and templates belong in services.

Use these collections:

- `customers`: ObjectId, name, email, normalized email, creation time,
  marketing preference, combined balance in cents, category, and category version.
- `accounts`: ObjectId, customerId, type, balance in cents, creation time,
  and optional closure time.
- `transactions`: ObjectId, customerId, accountId, DEPOSIT/WITHDRAW type,
  amount in cents, resulting account balance in cents, and UTC timestamp.
- `notifications`: ObjectId, customerId, category version, message kind,
  template identifier, rendered message, category, trigger transactionId when
  applicable, and UTC timestamp.

Money remains Decimal-validated at the API boundary and is stored as integer
cents. Responses retain decimal strings with exactly two fractional digits.
Retain the existing per-account and per-operation maximum of 99,999,999.99.
Combined customer balances may exceed that per-account limit, but must fit the
database's signed 64-bit cents representation; reject changes exceeding it.

Expose ObjectIds as 24-character hexadecimal strings in JSON. Malformed IDs
return 422; valid IDs without an accessible record return 404. Preserve existing
camelCase field names and the customerId/userId compatibility alias. Numeric IDs
are a deliberate API change on this branch; update examples and collection
variables. There is no persisted memory data to migrate.

Create a unique index on normalized customer email. Add indexes supporting
customer/account history ordered by date and ObjectId, customer search/category
queries, and customer notifications. Use a unique notification key consisting
of customerId, categoryVersion, and kind to prevent retry duplicates.

## Money operations and consistency

Every deposit or withdrawal must use one database transaction to:

1. Validate the active customer and account.
2. Conditionally update the account balance without overdraft or overflow.
3. Update the customer's combined balance and category.
4. Insert the transaction record.
5. Insert applicable category notifications.

All steps commit together or roll back together. Serialize competing operations
for the same customer through the customer document update, including operations
on different accounts. Use the driver's transaction retry mechanism for transient
conflicts. Transaction callbacks must have no external side effects. Message
creation stays inside the transaction; a callback retry cannot produce duplicate
stored messages. Separate client requests remain separate money operations;
request-level idempotency keys are not part of this scope.

Account creation and closure also coordinate through the customer document in a
transaction, so they cannot race with customer deletion or balance changes.
Lookup the customer's current name when forming account responses instead of
maintaining redundant cached names across account documents.

Keep existing 400 business-rule, 404 missing-record, 409 conflict, and 422
validation responses. Translate database unavailability to a sanitized 503;
never return a URI, credentials, or database traceback to the client.

## Record retention

Proposed change for audit support: deleting a zero-balance account closes it
instead of removing its history. Closed accounts are omitted from active CRUD
lists and cannot receive deposits, withdrawals, or edits. Their transaction
history remains available through audit queries and account history.

Deleting a customer with active accounts still returns 409. Once all accounts
are closed, customer deletion marks the customer inactive. Retain transaction
references and email uniqueness for audit consistency. Deleted customers are
omitted from active customer routes and searches. Audit queries can still use
their IDs. This behavior must be documented as closure/archival, not erasure.

## Search and audit API

Extend `GET /api/customers` with optional literal, case-insensitive name/email
search and category filtering. Escape search input rather than accepting regular
expressions or database expressions. Return each customer's combined balance,
category, and marketing preference.

Add `GET /api/audit/transactions` with optional customerId, accountId, from, and
to filters. Filters combine with AND. Date values are timezone-aware ISO 8601;
normalize to UTC. The lower time boundary is inclusive and the upper boundary
exclusive. Reject reversed or equal boundaries with 422. No matches return [].

Add `GET /api/audit/transactions/{id}` for a single transaction.

Support bounded pagination on customer lists, account lists, account history,
audit queries, and notifications: offset defaults to 0, limit to 50, maximum 100.
Keep list responses as arrays. Use stable ordering with ObjectId as a tie-breaker;
transactions are oldest first, customers/accounts by creation time, notifications
newest first. Document that pagination is not a snapshot across concurrent writes.

## Notification and marketing rules

Operational low-balance alerts and marketing messages are distinct kinds.
Marketing is disabled by default and requires an explicit stored preference.
Add `PATCH /api/customers/{id}/preferences` with `marketingEnabled: boolean`.
Changing a preference affects future messages; it does not retroactively create
marketing or remove existing history. Name/email edits preserve preferences.

Use `GET /api/customers/{id}/notifications` to retrieve stored messages, with
optional kind filtering and bounded pagination. A stored message means created
for API retrieval, not emailed, pushed, or delivered. No external sending occurs.

Initial customer creation sets LOW with a zero combined balance but does not
send a message to a customer with no accounts. Opening the first account creates
the initial low-balance alert and, if opted in, one low-balance marketing message.
Opening subsequent zero-balance accounts does not repeat the initial message.
Keep an initialization marker even if every account is later closed.

After initialization, use these transitions:

| Entered category | Messages |
| --- | --- |
| LOW | Low-balance alert; loan-options marketing only if opted in |
| STANDARD | No message; update category and version |
| PREMIUM | Premium welcome/benefits marketing only if opted in |

Every category transition increments the category version, including transitions
to STANDARD. Returning to a category after leaving it can create a new message;
this milestone has no additional time-based cooldown.

Examples of template content:

- Low alert: Your combined account balance is below 100.00.
- Low marketing: Explore available loan options and learn how to apply.
  Eligibility and approval depend on assessment.
- Premium marketing: Your combined balance has reached 10,000.00.
  Explore available premium banking benefits.

Do not invent specific loan products, rates, benefits, application links, or
approval decisions. These are workshop templates, not a loan approval service.

## Configuration and secrets

Read MONGODB_URI and MONGODB_DATABASE from environment variables or local .env.
Keep .env and local variants ignored, with an explicit exception for a tracked
.env.example containing placeholders only. Never log the connection string.
Keep the connection credential only in local configuration; do not copy it into
source, documentation, Postman, fixtures, or this design.

Live verification requires network access, a reachable Atlas cluster, and a database user with
permissions for the selected workshop database. Do not weaken Atlas network rules
or permissions automatically. Tests must use a separate, explicitly configured
test database and must never clear the application database.

## Verification and submission

Adapt existing API tests to ObjectIds and archive semantics. Add focused unit
tests for category thresholds, preference handling, message templates, literal
search validation, date bounds, and pagination validation.

Run integration tests against a transaction-capable isolated database for:

- CRUD persistence across fresh app instances and unique normalized emails.
- Deposit/withdraw correctness, rejected amounts, limits, and overdrafts.
- Concurrent withdrawals and operations on separate accounts of one customer.
- Rollback when transaction or notification insertion fails.
- Initial account alerts, category crossings, repeated same-category actions,
  opt-in/out, and duplicate prevention during transaction retries.
- Audit filters, archive retention, stable ordering, and pagination.
- Concurrent account/customer lifecycle operations.

Keep unit and integration results distinct. Skipped database tests do not prove
Atlas behavior. Report live verification only after actually running it.

Update Swagger, the Postman collection, README setup instructions, dependency
documentation, and Mermaid diagrams. Preserve the Record Relationships and Code
Structure sections, Moataz Hikal examples, and the current branding. Include no
README roadmap. Commit reviewed implementation on this branch; do not merge the
original milestone. No authentication or frontend completion claims.
