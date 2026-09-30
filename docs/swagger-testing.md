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
| 5 | POST /api/accounts | `{"customerId":"<customerId>","accountType":"SAVINGS"}` | 201, zero balance, accountId |
| 6 | POST /api/accounts | `{"customerId":"<customerId>","accountType":"CURRENT"}` | 201, a different accountId (`<account2Id>`) |
| 7 | GET /api/customers/`<customerId>`/accounts | Customer ID | 200, both accounts |
| 8 | GET /api/accounts | None | 200, all accounts |
| 9 | PUT /api/accounts/`<accountId>` | `{"accountType":"CURRENT"}` | 200, edited type |
| 10 | POST /api/accounts/`<accountId>`/deposit | `{"amount":"100.00"}`, header `Idempotency-Key: swagger-1` | 200, balance 100.00 |
| 11 | POST /api/accounts/`<accountId>`/deposit | Same body, same `Idempotency-Key: swagger-1` | 200, balance 100.00 again (replay; nothing deposited) |
| 12 | POST /api/accounts/`<accountId>`/deposit | `{"amount":"50.00"}`, same `Idempotency-Key: swagger-1` | 409, key used for a different request |
| 13 | POST /api/accounts/`<accountId>`/withdraw | `{"amount":"25.00"}` | 200, balance 75.00 |
| 14 | GET /api/accounts/`<accountId>` | Account ID | 200, balance 75.00 (the replay did not deposit twice) |
| 15 | GET /api/accounts/`<accountId>`/transactions | Account ID | 200, deposit and withdrawal |
| 16 | GET /api/customers/search | `email` = `updated`, `category` = `LOW` | 200, the customer with totalBalance 75.00 and category LOW |
| 17 | GET /api/alerts | `customerId` = `<customerId>` | 200, one LOW_BALANCE alert (total 75.00, threshold 100.00) with default thresholds |
| 18 | GET /api/audit/transactions | `customerId` = `<customerId>`, `limit` = 1 | 200, the deposit and a `nextCursor` |
| 19 | GET /api/audit/transactions | Same filters and `limit`, `cursor` = the `nextCursor` | 200, the withdrawal and `nextCursor` null |
| 20 | POST /api/accounts/`<accountId>`/withdraw | `{"amount":"76.00"}` | 400, insufficient funds |
| 21 | DELETE /api/accounts/`<accountId>` | Account ID | 409, balance is nonzero |
| 22 | DELETE /api/customers/`<customerId>` | Customer ID | 409, accounts still exist |
| 23 | POST /api/accounts/`<accountId>`/withdraw | `{"amount":"75.00"}` | 200, zero balance |
| 24 | DELETE /api/accounts/`<accountId>` and `<account2Id>` | Each account ID | 204, empty bodies |
| 25 | DELETE /api/customers/`<customerId>` | Customer ID | 204, empty body |
| 26 | GET /api/customers/`<customerId>` | Deleted ID | 404 |
| 27 | GET /api/audit/transactions | `customerId` = `<customerId>` | 200, all three transactions: the history was kept |

Step 16 matches the customer because the `email` filter is a case-insensitive
substring. Steps 17 and 27 show that alerts and transactions outlive the
records they describe. In Swagger, leave optional parameters you do not need
empty. For a time such as `from`, write `2026-09-30T08:00:00Z`. In a
hand-written URL, a `+02:00` offset must be written `%2B02:00`, because a bare
`+` becomes a space and is rejected.

Also try a blank name, invalid email, missing fields, a malformed ID such as
`abc`, and a zero/negative deposit; expect 422. Duplicate email returns 409, and
a valid but unknown customer on account creation returns 404. An audit request
with neither `customerId` nor `accountId` returns 422 with a string `detail`,
while a malformed parameter returns 422 with a `detail` list. A rejected
request must leave the balance and history unchanged.

For Postman, import `postman/Banking-App.postman_collection.json`, leave `baseUrl`
as `http://127.0.0.1:8000`, and select **Run collection** in its stored order.
Every request has a status assertion, with additional balance, relationship, and
response checks where relevant. Setup generates a fresh email and an
`Idempotency-Key` and captures IDs; cleanup drains the sample account and deletes
both accounts before the customer (their transactions and alert are kept by
design), and the last request reads the audit of the deleted customer. The search
and alert checks assume the default thresholds. The
automated pytest suite provides additional validation and concurrency coverage.

## Test coverage

- `python -m pytest -q -p no:cacheprovider`: **246 passed** against MongoDB Atlas.
  The tests need `MONGODB_URI` and fail without it; they use a throwaway
  `paper_maker_test_<hex>` database that is dropped at the end.
- `test_postman_collection.py` reads the collection file and sends its 27 requests
  through TestClient. It checks response codes, balances, the idempotent replay,
  search, alerts, audit paging and history after deletion. It does not execute
  the collection's JavaScript assertions or the `{{$guid}}` pre-request scripts;
  it uses fixed values in their place.
- `test_crud.py` checks the OpenAPI routes, customer ownership field, documented
  response codes, and `/docs` response.
- These results cover the API and collection requests. They do not establish a
  successful interactive Swagger session or a run inside the Postman application.
