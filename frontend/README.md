# Customer frontend

Requires Node.js 20.19+ or 22.12+ and npm.

```sh
npm install
npm run dev
```

The development server uses http://localhost:5173. Start the FastAPI backend separately using the repository README. The API URL defaults to http://localhost:8000; copy `.env.example` to `.env.local` to override `VITE_API_BASE_URL`, then restart Vite. This URL is public browser configuration: never put credentials in a `VITE_` variable. The backend must allow the frontend origin through CORS.

The UI supports customer list, add, edit, and confirmed deletion. Deleting a customer also deletes their accounts and balances, as described in the confirmation.

Choose Accounts on a customer to list or open accounts, deposit, withdraw, view transaction history, or delete an account with a zero balance. Transfer lets you choose any two accounts, including accounts owned by different customers. Premium accounts shows up to 200 accounts at the backend's configured threshold, highest balance first.

Money is sent as a decimal string, with a fresh idempotency key for each submitted deposit, withdrawal, or transfer. There are no automatic mutation retries. After a connection failure, check balances and history before submitting a new operation. Successful operations reload the account list; if that reload fails, Retry only reloads the list.

```sh
npm test
npm run build
```

Tests mock HTTP responses and cover customer CRUD and error recovery. They do not contact a database. The production build is written to `dist/`; configure the backend to allow the deployed frontend origin before deployment.
