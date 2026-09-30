# Records and code dependencies

A customer owns accounts, an account records transactions, and a customer receives
stored notifications. ObjectId references connect the four Atlas collections.
Customers and accounts are archived rather than erased when DELETE succeeds.

Controllers in `routes.py` and `reporting_routes.py` validate input through
`models.py`, then call services. `main.py` owns startup/shutdown and safe error
responses. Each process creates one MongoClient and shares its connection pool.

`services.py` uses customer/account repositories, the transaction repository in
`audit.py`, and notification policy/storage in `notifications.py`. Repositories
accept the caller's session; they do not commit transactions independently.

## A deposit or withdrawal

1. Find the active account and write its customer document to coordinate competing operations.
2. Check and update the account balance using a conditional database update.
3. Update the combined customer balance and category.
4. Insert the immutable money transaction.
5. On category entry, insert the operational alert and any opted-in marketing.
6. Commit everything together. Any failure aborts the entire operation.

Customer preference edits, account creation/closure, and customer archival also
write the customer document. This makes conflicting operations retry against the
new state rather than calculate from an outdated total or preference.

PyMongo may repeat a transaction callback after a transient conflict. Callbacks
perform only database work, and the notification uniqueness key is customerId,
categoryVersion, and kind. No email or push calls happen inside or outside them.

## Stored values and indexes

Money uses integer cents in MongoDB and Decimal strings at the HTTP boundary.
Customer totals are maintained in the same transactions as account changes.
Account display names are read from the current customer record.

Startup creates the normalized-email unique index, account ownership indexes,
transaction customer/account/date indexes, and notification uniqueness and date
indexes. There is no SQL script for this Atlas milestone.

Audit history can be queried after account closure or customer archival. Active
CRUD endpoints omit those records. Email uniqueness is retained after archival.
