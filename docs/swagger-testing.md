# Testing with Swagger and Postman

Start the server using the README, then open http://127.0.0.1:8000/docs.
Swagger is generated from the actual routes and schemas; expand an operation,
click **Try it out**, enter its body/path ID, and click **Execute**. Check the
**Server response** status and body. IDs below assume a fresh server; otherwise
use the IDs returned by your requests.

| Step | Operation | Input | Expected |
| --- | --- | --- | --- |
| 1 | GET /api/customers | None | 200, empty array on fresh server |
| 2 | POST /api/customers | `{"name":"Moataz Hikal","email":"moataz@example.com"}` | 201, customerId |
| 3 | GET /api/customers/1 | Returned ID | 200, Moataz Hikal |
| 4 | PUT /api/customers/1 | `{"name":"Moataz Hikal","email":"moataz.updated@example.com"}` | 200, updated email |
| 5 | POST /api/accounts | `{"customerId":1,"accountType":"SAVINGS"}` | 201, zero balance |
| 6 | POST /api/accounts | `{"customerId":1,"accountType":"CURRENT"}` | 201, a different accountId |
| 7 | GET /api/customers/1/accounts | Customer ID | 200, both accounts |
| 8 | GET /api/accounts | None | 200, all accounts |
| 9 | PUT /api/accounts/1 | `{"accountType":"CURRENT"}` | 200, edited type |
| 10 | POST /api/accounts/1/deposit | `{"amount":"100.00"}` | 200, balance 100.00 |
| 11 | POST /api/accounts/1/withdraw | `{"amount":"25.00"}` | 200, balance 75.00 |
| 12 | GET /api/accounts/1 | Account ID | 200, balance 75.00 |
| 13 | GET /api/accounts/1/transactions | Account ID | 200, deposit and withdrawal |
| 14 | POST /api/accounts/1/withdraw | `{"amount":"76.00"}` | 400, insufficient funds |
| 15 | DELETE /api/accounts/1 | Account ID | 409, balance is nonzero |
| 16 | DELETE /api/customers/1 | Customer ID | 409, accounts still exist |
| 17 | POST /api/accounts/1/withdraw | `{"amount":"75.00"}` | 200, zero balance |
| 18 | DELETE /api/accounts/1 and /2 | Each account ID | 204, empty bodies |
| 19 | DELETE /api/customers/1 | Customer ID | 204, empty body |
| 20 | GET /api/customers/1 | Deleted ID | 404 |

Also try a blank name, invalid email, missing fields, and a zero/negative deposit;
expect 422. Duplicate email returns 409, and an unknown customer on account creation
returns 404. A rejected request must leave the balance and history unchanged.

For Postman, import `postman/Banking-App.postman_collection.json`, leave `baseUrl`
as `http://127.0.0.1:8000`, and select **Run collection** in its stored order.
Every request has a status assertion, with additional balance, relationship, and
response checks where relevant. Setup generates a fresh email and captures IDs;
cleanup drains the sample account and deletes both accounts before the customer.
The automated pytest suite provides additional validation and concurrency coverage.

## Test coverage

- `python -m pytest -q -p no:cacheprovider`: **62 passed**.
- `test_postman_collection.py` reads the collection file and sends its 21 requests
  through TestClient. It checks response codes, balances, account ownership, and
  transaction history. It does not execute the collection's JavaScript assertions.
- `test_crud.py` checks the OpenAPI routes, customer ownership field, documented
  response codes, and `/docs` response.
- These results cover the API and collection requests. They do not establish a
  successful interactive Swagger session or a run inside the Postman application.
