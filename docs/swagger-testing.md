# Testing with Swagger and Postman

Start the server using the README (with the `.env` for your Atlas cluster), then
open http://127.0.0.1:8000/docs. Swagger is generated from the actual routes and
schemas; expand an operation, click **Try it out**, enter its body/path ID, and
click **Execute**. Check the **Server response** status and body.

IDs are 24-character hexadecimal strings that MongoDB generates, so write down
the ones your requests return. Below, `<customerId>`, `<accountId>`, and
`<account2Id>` stand for those values. Data stays in the database between runs,
so use a new email each time (a duplicate returns 409) and expect earlier
customers in list results.

| Step | Operation | Input | Expected |
| --- | --- | --- | --- |
| 1 | GET /api/customers | None | 200, an array |
| 2 | POST /api/customers | `{"name":"Moataz Hikal","email":"moataz@example.com"}` | 201, customerId |
| 3 | GET /api/customers/`<customerId>` | Returned ID | 200, Moataz Hikal |
| 4 | PUT /api/customers/`<customerId>` | `{"name":"Moataz Hikal","email":"moataz.updated@example.com"}` | 200, updated email |
| 5 | PATCH /api/customers/`<customerId>`/preferences | `{"marketingEnabled":true}` | 200, marketingEnabled true |
| 6 | POST /api/accounts | `{"customerId":"<customerId>","accountType":"SAVINGS"}` | 201, zero balance, accountId |
| 7 | POST /api/accounts | `{"customerId":"<customerId>","accountType":"CURRENT"}` | 201, a different accountId (`<account2Id>`) |
| 8 | GET /api/customers/`<customerId>`/accounts | Customer ID | 200, both accounts |
| 9 | GET /api/accounts | None (optional `?limit=1` to 200 caps the list; the same works on GET /api/customers and the transactions list) | 200, all accounts |
| 10 | PUT /api/accounts/`<accountId>` | `{"accountType":"CURRENT"}` | 200, edited type |
| 11 | POST /api/accounts/`<accountId>`/deposit | `{"amount":"100.00"}`, header `Idempotency-Key: swagger-1` | 200, balance 100.00 |
| 12 | POST /api/accounts/`<accountId>`/deposit | Same body, same `Idempotency-Key: swagger-1` | 200, balance 100.00 again (replay; nothing deposited) |
| 13 | POST /api/accounts/`<accountId>`/deposit | `{"amount":"50.00"}`, same `Idempotency-Key: swagger-1` | 409, key used for a different request |
| 14 | POST /api/accounts/`<accountId>`/withdraw | `{"amount":"25.00"}` | 200, balance 75.00 |
| 15 | GET /api/accounts/`<accountId>` | Account ID | 200, balance 75.00 (the replay did not deposit twice) |
| 16 | GET /api/accounts/`<accountId>`/transactions | Account ID | 200, deposit and withdrawal |
| 17 | GET /api/customers/search | `email` = `updated`, `category` = `LOW` | 200, the customer with totalBalance 75.00 and category LOW |
| 18 | GET /api/customers/`<customerId>`/notifications | Customer ID | 200, LOW_BALANCE_ALERT and LOW_BALANCE_MARKETING, both category LOW and categoryVersion 2, with default thresholds |
| 19 | GET /api/audit/transactions | `customerId` = `<customerId>`, `limit` = 1 | 200, the deposit and a `nextCursor` |
| 20 | GET /api/audit/transactions | Same filters and `limit`, `cursor` = the `nextCursor` | 200, the withdrawal and `nextCursor` null |
| 21 | POST /api/transfers | `{"fromAccountId":"<accountId>","toAccountId":"<account2Id>","amount":"25.00"}`, header `Idempotency-Key: swagger-transfer-1` | 200, `fromBalanceAfter` 50.00, `toBalanceAfter` 25.00, a `transferId` |
| 22 | POST /api/transfers | Same body, same `Idempotency-Key: swagger-transfer-1` | 200, the same `transferId` and balances (replay; nothing moved) |
| 23 | POST /api/transfers | `<accountId>` as both `fromAccountId` and `toAccountId`, `"amount":"1.00"` | 422, the accounts must differ |
| 24 | GET /api/accounts/premium | `threshold` = `25.00`, `limit` = 200 | 200, accounts with a balance of at least 25.00, highest first (yours are 50.00 and 25.00; earlier runs may add more) |
| 25 | POST /api/accounts/`<accountId>`/withdraw | `{"amount":"76.00"}` | 400, insufficient funds (the balance is now 50.00) |
| 26 | DELETE /api/accounts/`<accountId>` | Account ID | 409, balance is nonzero |
| 27 | POST /api/accounts/`<accountId>`/withdraw | `{"amount":"50.00"}` | 200, zero balance |
| 28 | DELETE /api/accounts/`<accountId>` | Account ID | 204, empty body |
| 29 | DELETE /api/customers/`<customerId>` | Customer ID | 204, empty body; `<account2Id>` still holds 25.00 and is deleted with the customer |
| 30 | GET /api/customers/`<customerId>` | Deleted ID | 404 |
| 31 | GET /api/accounts/`<account2Id>` | Account ID | 404, deleted with its customer |
| 32 | GET /api/audit/transactions | `customerId` = `<customerId>` | 200, all six transactions (deposit, withdrawal, TRANSFER_OUT, TRANSFER_IN, final withdrawal, and an ACCOUNT_CLOSED record of the 25.00 removed from `<account2Id>`): the history was kept |

Note on replays: a deposit or withdraw replayed with the same `Idempotency-Key` returns the
Account while the account exists. If the account was deleted in between, the response is the
stored Transaction instead: it has `balanceAfter`, not `balance`.

A transfer writes two records that share a `transferId`: TRANSFER_OUT on the source
account and TRANSFER_IN on the destination, each with `fromAccountId`,
`toAccountId` and its own account's `balanceAfter`. Step 16 ran before the
transfer, so it lists only the deposit and withdrawal; the transactions list
of either account now shows its transfer record too. Because both accounts
belong to one customer in this walkthrough, the customer's total does not
change and the transfer stores no notification. A key on a transfer belongs
to the source account, like a withdrawal's, and reusing it with a different
body or destination returns 409. Step 29 shows the cascade: deleting a customer
deletes all their accounts whatever their balances (an `ACCOUNT_CLOSED` record
shows the 25.00 removed from the second account), while transactions and
notifications stay.

Step 17 matches the customer because the `email` filter is a case-insensitive
substring. In step 18, the deposit to 100.00 moved the customer from LOW to
STANDARD (version 1, no message) and the withdrawal to 75.00 moved them back to
LOW (version 2): the low-balance alert is always stored, and the loan-options
message only because step 5 opted in. Step 32 shows that transactions outlive the
records they describe. In Swagger, leave optional parameters you do not need
empty. For a time such as `from`, write `2026-09-30T08:00:00Z`. In a
hand-written URL, a `+02:00` offset must be written `%2B02:00`, because a bare
`+` becomes a space and is rejected.

Also try a blank name, invalid email, missing fields, a malformed ID such as
`abc`, a zero/negative deposit or transfer, and a transfer from an account to
itself; expect 422. A transfer with an unknown source or destination account
returns 404, and a transfer that would overdraw the source or push the
destination past 99999999.99 returns 400 and changes neither balance. Duplicate email returns 409, and
a valid but unknown customer on account creation returns 404. An audit request
with neither `customerId` nor `accountId` returns 422 with a string `detail`,
while a malformed parameter returns 422 with a `detail` list. A rejected
request must leave the balance and history unchanged.

For Postman, import `postman/Banking-App.postman_collection.json`, leave `baseUrl`
as `http://127.0.0.1:8000`, and select **Run collection** in its stored order.
Every request has a status assertion, with additional balance, relationship, and
response checks where relevant. Setup generates a fresh email and an
`Idempotency-Key` and captures IDs. The transfer requests follow the audit
pages (the transfer step generates its own key), then the premium list.
Cleanup drains and deletes the first account, deletes the customer (which
deletes the second account too; transactions and notifications are kept by
design), checks that the second account is gone, and the last request reads the
audit of the deleted customer. The
search and notification checks assume the default thresholds. The
automated pytest suite provides additional validation and concurrency coverage.

## Test coverage

- `python -m pytest -q -p no:cacheprovider` runs the whole suite. Some tests need no
  database; the rest need `MONGODB_URI` and fail
  without it; they use a throwaway `paper_maker_test_<hex>` database that is dropped
  at the end.
- `test_postman_collection.py` reads the collection file and sends its 31 requests
  through TestClient. It checks response codes, balances, the idempotent replay,
  search, the marketing opt-in and notifications, audit paging, transfers and
  their replay, the premium list, the customer cascade delete and history after
  deletion. It does not execute
  the collection's JavaScript assertions or the `{{$guid}}` pre-request scripts;
  it uses fixed values in their place.
- `test_crud.py` checks the OpenAPI routes, customer ownership field, documented
  response codes, and `/docs` response.
- These results cover the API and collection requests. They do not establish a
  successful interactive Swagger session or a run inside the Postman application.
