"""AWS Lambda entry point: wraps the FastAPI app so a Function URL (or API Gateway) can call it.

Lambda keeps a warm container between calls, so the app's startup (one MongoClient, index setup, admin bootstrap)
runs once per cold start and later requests reuse the same database connection.
"""
from mangum import Mangum

from app.main import app

handler = Mangum(app, lifespan="auto")
