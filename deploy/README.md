# Deploying to AWS

Architecture: React build on S3, FastAPI on Lambda (Function URL), data in MongoDB Atlas. See `docs/architecture.md`.

1. **Atlas:** Network Access must allow the Lambda (`0.0.0.0/0`, as the course setup uses); keep the database user's
   password in the Lambda environment only.
2. **Backend:** `python deploy/build_lambda.py`, then create or update the function (Python 3.12, handler
   `lambda_handler.handler`, timeout 29 s, 512 MB) with the zip from `build/bank-api.zip`.
3. **Environment variables on the function:** `MONGODB_URI`, `MONGODB_DB`, `JWT_SECRET` (32+ random characters),
   `CORS_ALLOWED_ORIGINS` (the S3 site origin), `ADMIN_EMAIL`, `ADMIN_PASSWORD` (12+ characters).
4. **Function URL:** auth type NONE, plus the public `InvokeFunctionUrl` and `InvokeFunction` permissions.
5. **Frontend:** `cd frontend`, `VITE_API_BASE_URL=<function url> npm run build`, then
   `aws s3 sync dist s3://<bucket> --delete`. The bucket has static website hosting and a public-read policy.
6. **Check:** open the site, sign in, and confirm the Network tab shows calls to the Function URL returning JSON.
