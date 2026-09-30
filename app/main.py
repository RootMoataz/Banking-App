"""App lifecycle and shared HTTP error handling."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError, PyMongoError

from .audit import AuditService
from .config import Settings
from .database import MongoStore
from .errors import BankError
from .services import AccountService, CustomerService


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        store = None
        try:
            try:
                store = MongoStore(settings or Settings.from_env())
                store.connect()
            except (PyMongoError, ValueError):
                raise RuntimeError('Database startup failed. Check local MongoDB settings, credentials and replica-set access.') from None
            app.state.store = store
            app.state.customers = CustomerService(store)
            app.state.accounts = AccountService(store)
            app.state.audit = AuditService(store)
            yield
        finally:
            if store is not None:
                store.close()

    app = FastAPI(title='Paper Maker Banking App', version='2.0.0', lifespan=lifespan,
                  description='MongoDB Atlas banking API with transaction audits and stored customer notifications. '
                              'Workshop API: no authentication or external message delivery.')

    @app.exception_handler(BankError)
    async def bank_error(request, exc):
        return JSONResponse(status_code=exc.status, content={'detail':exc.detail})

    @app.exception_handler(DuplicateKeyError)
    async def duplicate_error(request, exc):
        return JSONResponse(status_code=409, content={'detail':'A record with this unique value already exists'})

    @app.exception_handler(PyMongoError)
    async def database_error(request, exc):
        return JSONResponse(status_code=503, content={'detail':'Database operation unavailable. Try again later.'})

    from .routes import router
    from .reporting_routes import router as reporting_router
    app.include_router(router)
    app.include_router(reporting_router)
    return app


app = create_app()
