# Demonstrating the Atlas branch

Start the API using the README setup and open http://127.0.0.1:8000/docs.
Use a sample customer and keep the returned string IDs for later requests.

## Walkthrough

1. POST `/api/customers` with Moataz Hikal and a fresh example email. Expect 201.
2. PATCH `/api/customers/{id}/preferences` with `{"marketingEnabled":true}`.
3. POST `/api/accounts` with the returned customerId and accountType SAVINGS.
4. GET customer notifications: one low-balance alert and one loan-options message.
5. Open a second account. Check that no extra initial messages were created.
6. Deposit 100.00 in the first account, then withdraw 25.00. Balance is 75.00.
7. Try withdrawing 76.00. Expect 400, with balance and history unchanged.
8. Deposit 9925.00 in the second account. Combined balance is 10000.00, category PREMIUM.
9. GET notifications with kind PREMIUM_MARKETING. Expect one premium message.
10. Search `/api/customers?search=moataz&category=PREMIUM` and locate your sample customer.
11. Disable marketing, then withdraw 9925.00 from the second account. Returning to LOW creates an alert, without another loan message.
12. Query `/api/audit/transactions` with customerId/accountId and a timezone-aware from/to range. Retrieve a single result by txnId.
13. Restart the API, then retrieve the same account. Its balance and history persist.
14. Withdraw the final 75.00, close both accounts, and archive the customer. Audit history remains queryable by customerId.

The first return to LOW at step 6 also creates a new low alert and opted-in loan
message. Remaining within LOW does not repeat either message. Newly created
customers without accounts receive no messages.

## Postman

Import `postman/Banking-App.postman_collection.json`, set baseUrl to
`http://127.0.0.1:8000`, and run the collection in order. It generates a fresh
email, saves IDs, checks responses, demonstrates premium/low triggers, and archives
its sample records at the end. It retains history by design. Re-running uses a new
email. No database URI belongs in the collection.

The exported collection contains executable Postman assertions. The Python replay
checks the request sequence and key response values, but does not run that JavaScript.
Use Postman's Runner to capture actual Postman results for submission.

## Test coverage and verification limits

Unit tests cover configuration, credential redaction, categories, templates, and
money conversion. Integration tests exercise a real transaction-capable MongoDB
server: CRUD, exact cents, persistence across app instances, overdrafts, concurrent
withdrawals, customer totals, preference/lifecycle races, rollback, retry duplicates,
search, UTC boundaries, pagination, history retention, and the collection workflow.

Verified on September 30, 2026 with Python 3.12.14:

- Full suite against an isolated MongoDB 8.0.28 replica set: 97 passed.
- Independent review reran that suite: 97 passed, no blocking findings.
- Live Atlas CRUD, money, audit, and collection workflow checks: 17 passed.
- Atlas connection and required index setup succeeded. Tests used separate,
  generated test databases, not the application database.

Both environments emitted the existing Starlette TestClient/httpx deprecation
warning. Interactive Swagger clicks and Postman's JavaScript Runner were not
performed; the HTTP workflow and OpenAPI schema were checked automatically.
If test settings are missing, pytest skips integration tests explicitly.

Final check on October 1, 2026: 98 tests passed locally. The preference race now
forces an opt-out to commit while a deposit has an older snapshot, and verifies
that retrying the deposit produces no premium marketing message. That focused
test also passed against Atlas. Database-name validation now enforces the
cluster's 38-character limit, including generated test database names.
