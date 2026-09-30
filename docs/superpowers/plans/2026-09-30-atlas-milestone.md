# MongoDB Atlas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the banking API in Atlas, with safe money operations, audit queries, customer categories, and stored notifications.

**Architecture:** Retain synchronous FastAPI controllers and service/repository separation. PyMongo transactions coordinate account balances, customer totals, transaction history, and notification inserts. Pure functions determine categories and notification content.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic 2, PyMongo, python-dotenv, pytest, HTTPX, MongoDB Atlas.

**Spec:** [Approved design](../specs/2026-09-30-atlas-milestone-design.md)

## Global Constraints

- Work on `2_backend-rest-api-mongodb-atlas`; do not merge the original milestone.
- LOW: Below 100.00. STANDARD: At least 100.00 and below 10,000.00. PREMIUM: At least 10,000.00.
- Categories use combined customer balances across accounts.
- Retain the existing per-account and per-operation maximum of 99,999,999.99.
- Store integer cents; reject customer-total overflow beyond signed 64-bit cents.
- Expose ObjectIds as 24-character hexadecimal strings in JSON.
- Date ranges use inclusive lower and exclusive upper UTC boundaries.
- Offset defaults to 0, limit to 50, maximum 100. List responses remain arrays.
- Marketing is disabled by default. Stored messages do not imply external delivery.
- Close/archive records while retaining history; do not erase audited transactions.
- No React, authentication, transfers, external sending, or request-level idempotency in this milestone.
- Keep real secrets out of tracked files. Use a separate, explicitly configured test database.
- Preserve branding, Moataz Hikal examples, Mermaid diagrams, and separate Record Relationships / Code Structure sections. Include no README roadmap.

## Review Focus

- Concurrent first-account requests must create exactly one initial alert (Task 3).
- A preference update racing with a deposit must serialize through the customer document (Task 4).
- Regex metacharacters in search must remain literal text, never database operators (Task 5).
- Equivalent timestamps with different offsets must return the same audit records (Task 5).
- Database failures must never expose connection credentials or leave partial balances/messages (Tasks 1 and 4).

## File map

- `app/config.py`: environment settings and secret-safe validation.
- `app/database.py`: MongoClient lifecycle, session transaction runner, indexes.
- `app/models.py`: API validation, ObjectId strings, money conversion, response models.
- `app/repositories.py`: customer/account persistence and conditional mutations.
- `app/services.py`: customer/account use cases and transaction orchestration.
- `app/notifications.py`: pure category/message policy and notification persistence.
- `app/audit.py`: transaction storage/query repository and audit service.
- `app/routes.py`: existing customer/account controller routes, extracted from main.py.
- `app/reporting_routes.py`: audit, notifications, and preference routes.
- `app/main.py`: app factory, lifespan, dependency wiring, exception handlers.
- `tests/conftest.py`: explicit isolated integration database fixture and app clients.
- `tests/test_config.py`, `tests/test_models.py`, `tests/test_notifications.py`: offline unit tests.
- `tests/test_atlas_crud.py`, `tests/test_atlas_money.py`, `tests/test_atlas_audit.py`: database integration behavior.
- Existing test modules: preserve behavioral coverage while adapting IDs and storage assumptions.
- `.env.example`, `.gitignore`, requirements files, `pytest.ini`: setup and test configuration.
- README, docs, Postman collection: current milestone usage and demonstrations.

## Task 1: Database lifecycle and isolated test harness

**Files:** config.py, database.py, main.py, tests/conftest.py, tests/test_config.py, requirements files, pytest.ini, .gitignore, .env.example.

**Interfaces:** `Settings.from_env() -> Settings` with URI and database name; `MongoStore(settings: Settings)` exposes `database`, `run_transaction(callback)`, `ensure_indexes()`, and `close()`. Callback receives a PyMongo ClientSession. `create_app(settings: Settings | None = None) -> FastAPI` connects during lifespan; services are accessed from app state through a request dependency.

- [ ] Write failing configuration tests: missing settings fail with a safe message; sentinel URI credentials never appear in exception strings or repr. Verify import does not require live configuration.
- [ ] Run `python -m pytest tests/test_config.py -q`; confirm failures describe the missing implementation.
- [ ] Implement Settings with a redacted secret field, local .env loading, bounded connection timeouts, and explicit database naming. Expand ignores to `.env.*` with `!.env.example`; placeholder-only example.
- [ ] Add PyMongo/python-dotenv dependencies, lifespan connect/ping/index initialization and closure. Use driver transaction retry support; no URI in error responses/logs.
- [ ] Add an `integration` marker and fixtures requiring `MONGODB_TEST_URI` and an explicit `MONGODB_TEST_DATABASE` beginning with `paper_maker_test_`. Refuse application database equality. Allocate a unique database suffix per run and clean only that exact generated database in teardown.
- [ ] Test lifecycle reuse/closure and sanitized connection failure; integration fixtures skip with an explicit reason when test settings are absent. No automatic fallback to a mock database.
- [ ] Run `python -m pytest tests/test_config.py -q`; commit `Configure Atlas connection and isolated database tests` after checks pass.

## Task 2: Exact money, ObjectIds, and notification policy

**Files:** models.py, notifications.py, tests/test_models.py, tests/test_notifications.py.

**Interfaces:** `to_cents(amount: Decimal) -> int`, `from_cents(cents: int) -> Decimal`; `category_for(total_cents: int) -> Literal['LOW', 'STANDARD', 'PREMIUM']`; `message_templates(category: str, marketing_enabled: bool) -> list[dict[str, str]]` returns kind, templateId, and message. `NotificationRepository.add_messages(customer_id: ObjectId, version: int, messages: list[dict], transaction_id: ObjectId | None, session: ClientSession) -> None` writes messages with UTC timestamps and unique keys.

- [ ] Write parameterized tests asserting `category_for(9999) == 'LOW'`, `category_for(10000) == 'STANDARD'`, `category_for(999999) == 'STANDARD'`, and `category_for(1000000) == 'PREMIUM'`.
- [ ] Test `to_cents(Decimal('0.10')) == 10`, round-trip fixed two-decimal responses, invalid/bool/non-finite/fractional-cent amounts, and malformed ObjectIds returning validation errors.
- [ ] Test LOW produces only an operational alert when opted out, LOW produces alert plus loan-options copy when opted in, STANDARD produces no messages, PREMIUM marketing requires opt-in. Assert exact approved text from the spec and no eligibility claims.
- [ ] Run `python -m pytest tests/test_models.py tests/test_notifications.py -q`; confirm expected failures.
- [ ] Implement pure policy, new response/preference models, ObjectId string validation, and integer-cent conversion. Keep legacy userId aliases. Add stable notification kind values `LOW_BALANCE_ALERT`, `LOW_BALANCE_MARKETING`, `PREMIUM_MARKETING`.
- [ ] Run the focused tests; commit `Define customer categories and notification rules` when passing.

## Task 3: Persistent CRUD and account lifecycle

**Files:** repositories.py, services.py, routes.py, main.py, notifications.py, tests/test_atlas_crud.py, existing test_api.py and test_crud.py.

**Interfaces:** CustomerService retains existing CRUD method names with ObjectId-string inputs; `set_preferences(customer_id: str, marketing_enabled: bool) -> Customer`. AccountService retains CRUD/history method names with ObjectId-string inputs. Repositories accept an explicit session for mutations and return database records; services construct API response models. Notifications use Task 2 interfaces. Keep BankError(status, detail).

- [ ] Write integration tests for creating customers/accounts, reads from a second app instance, case-insensitive duplicate emails returning 409, name edits appearing on account responses, zero initial balances, and ObjectId responses.
- [ ] Test deletion rejects active owned accounts/nonzero balances; closure hides records from active APIs but preserves stored history and email uniqueness. Test edits preserve preferences and archived records reject mutations.
- [ ] Test first account triggers one initial alert, an opted-in first account also gets one marketing message, concurrent first accounts still yield one initial set, and subsequent/reopened zero-balance accounts do not repeat initialization.
- [ ] Run `python -m pytest -m integration tests/test_atlas_crud.py -q`; require an actual failing run against the isolated database before treating red-phase evidence as complete.
- [ ] Implement repositories and service transactions. Add active flags, initialization marker, category version, zero customer total. Every lifecycle/preference mutation writes the customer document to serialize with competing operations. Protect customer deletion against concurrent account creation and account closure against deposits.
- [ ] Extract current routes into routes.py with service dependencies. Preserve response codes/aliases, sanitize database exceptions, and remove MemoryStore production wiring. Keep services separately testable.
- [ ] Adapt original CRUD/missing-record tests to valid nonexistent ObjectIds and archive semantics; replace restart-clears-data assertions with persistence assertions. Run applicable integration and unit tests; commit `Persist customer and account operations in Atlas` after success.

## Task 4: Atomic money, categories, and stored messages

**Files:** services.py, repositories.py, notifications.py, audit.py, tests/test_atlas_money.py, existing test_api.py.

**Interfaces:** `AccountService.deposit(account_id: str, data: AmountRequest) -> Account` and `withdraw(...) -> Account` invoke one MongoStore.run_transaction callback. `TransactionRepository.add(record: dict, session: ClientSession) -> ObjectId` in audit.py records customerId/accountId, type, cents, resulting balance, and date. NotificationRepository from Task 2 receives the inserted transaction ID and new category version.

- [ ] Write integration tests for 100.00 deposit/25.00 withdrawal yielding 75.00, rejection of 76.00 leaving history unchanged, 0.10+0.20 yielding 0.30, and existing balance/amount limits.
- [ ] Test customer-total overflow rejection using a controlled isolated fixture; account/customer totals, history, and notifications remain unchanged on rejection.
- [ ] Test two concurrent withdrawals cannot overspend, and deposits to different accounts update one correct combined total. Test overlapping preference changes use the preference serialized with each transaction.
- [ ] Test first LOW-to-STANDARD transition produces no message, entry to PREMIUM produces opted-in marketing, return to LOW produces one alert plus optional marketing, and repeated LOW deposits do not duplicate messages.
- [ ] Inject transaction-record and notification-write failures before commit; assert account total, customer total/category/version, and message/history counts all roll back. Exercise a transaction retry and assert one committed history/message set.
- [ ] Run `python -m pytest -m integration tests/test_atlas_money.py -q`; confirm missing behavior fails.
- [ ] Implement conditional balance updates and total/version calculation in one retry-safe transaction callback. Use customer writes to serialize preferences and all accounts; preserve immutable transaction records. Add unique notification indexes.
- [ ] Run money integration tests and existing monetary regression cases; commit `Record balance changes and category notifications atomically` after success.

## Task 5: Search, audit, preferences, and notification endpoints

**Files:** audit.py, repositories.py, notifications.py, reporting_routes.py, routes.py, models.py, tests/test_atlas_audit.py.

**Interfaces:** `AuditService.list_transactions(customer_id: str | None, account_id: str | None, date_from: datetime | None, date_to: datetime | None, offset: int, limit: int) -> list[Transaction]`, `get_transaction(transaction_id: str) -> Transaction`; `NotificationRepository.list_for_customer(customer_id: ObjectId, kind: str | None, offset: int, limit: int) -> list[dict]`. Extend customer/account list service methods with bounded offset/limit; customer search also receives search/category.

- [ ] Write API integration tests for combined customerId/accountId/date filters, get-by-transaction-ID, empty matches, archived history, UTC offset equivalence, inclusive from/exclusive to, and invalid/equal/reversed date bounds returning 422.
- [ ] Test search for literal `.*` does not match everyone; case-insensitive name/email search and category filters work. Test offset/limit defaults and bounds, deterministic ordering, and customer combined balances.
- [ ] Test preference PATCH persists a strict boolean, opt-in generates no retroactive message, name edits retain preference, notification retrieval separates kinds, and no external delivery occurs.
- [ ] Run `python -m pytest -m integration tests/test_atlas_audit.py -q`; confirm expected failures.
- [ ] Add the approved endpoints: GET `/api/audit/transactions`, GET `/api/audit/transactions/{id}`, PATCH `/api/customers/{id}/preferences`, GET `/api/customers/{id}/notifications`. Expose query aliases `from` and `to`; reject unknown category/kind values. Historical account history works for closed accounts.
- [ ] Add bounded paging and stable date/ObjectId sorts. Escape literal search, validate timezone-aware ranges, and create supporting indexes. Active customer routes exclude archived customers while audit accepts historical IDs.
- [ ] Run search/audit integration tests and regression suite; commit `Add customer search and transaction audit endpoints` after success.

## Task 6: Demonstration, documentation, and branch verification

**Files:** README.md, docs/dependencies.md, docs/swagger-testing.md, Postman collection, tests/test_postman_collection.py, requirements-lock.txt.

- [ ] Extend the Postman workflow with string ObjectIds, opt-in, first-account alerts, threshold crossings, audit filtering, preference opt-out, archived history, and rejected operations. Use generated example emails and response-derived IDs.
- [ ] Adapt collection replay to the isolated integration fixture; assert the new response values and notification counts. Keep explicit that Python replay does not execute Postman JavaScript.
- [ ] Run `python -m pytest -m 'not integration' -q` and `python -m pytest -m integration -q`. Record passed/failed/skipped counts separately; missing Atlas configuration is a verification blocker, not success.
- [ ] Update README and Swagger walkthrough for .env placeholders, ObjectIds, Atlas persistence, archive semantics, opt-in stored messages, categories, date boundaries, and lack of login/external delivery. Add setup/index instructions as the Atlas equivalent of the assignment's SQL setup artifact. Preserve Mermaid relationship and code structure sections.
- [ ] Update requirements-lock.txt from the successfully tested environment; verify no unrelated packages or secrets. Validate collection JSON and OpenAPI schema.
- [ ] Perform a live restart-persistence smoke test against sample records in the explicitly selected workshop database only after the rotated URI is configured. Never use the application database for destructive test cleanup.
- [ ] Run `git diff --check`; inspect staged changes and tracked filenames for secrets/env files. Obtain whole-branch review using the selected execution workflow, resolve material findings, and rerun affected tests.
- [ ] Commit `Document and verify the Atlas banking workflow`; push only `2_backend-rest-api-mongodb-atlas`. Report commit/branch links, actual test evidence, and any remaining live-demo limitations. Do not merge or rewrite the original milestone.

## Execution notes

These tasks are ordered because storage interfaces and transaction semantics are shared.
Prefer implementation in this session, followed by a separate whole-branch review.
No live connection can be verified until the rotated credential is configured
locally. Offline unit work can proceed without it. No step authorizes posting
credentials in chat, enabling public Atlas access, or sending marketing externally.
