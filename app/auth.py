"""Password hashing, JWT issue and verification, registration, login, and the admin bootstrap."""

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass

import jwt
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .config import MIN_JWT_SECRET_LENGTH, Settings
from .models import AuthUser, LoginRequest, RegisterRequest, TokenResponse
from .repositories import CustomerRepository, UserRepository
from .services import BankError, _in_transaction

logger = logging.getLogger(__name__)

# scrypt cost: N=2^15, r=8, p=1 needs about 32 MiB (128 * N * r bytes), fine inside a 512 MB Lambda. The parameters
# are stored in each hash, so they can be raised later and old hashes (e.g. N=2^14) still verify.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1
MIN_ADMIN_PASSWORD_LENGTH = 12
ALGORITHM = "HS256"
BAD_TOKEN = "Missing, invalid or expired token"
BAD_LOGIN = "Invalid email or password"


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int = 64) -> bytes:
    # hashlib refuses more than 32 MiB unless maxmem is given, so state it explicitly, sized from the parameters.
    maxmem = 128 * n * r * p * 2 + 1024 * 1024
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=maxmem, dklen=dklen)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        expected = bytes.fromhex(digest)
        actual = _scrypt(password, bytes.fromhex(salt), int(n), int(r), int(p), dklen=len(expected))
    except (ValueError, UnicodeEncodeError):  # not our format, or parameters scrypt refuses
        return False
    return scheme == "scrypt" and hmac.compare_digest(actual, expected)


_DUMMY_HASH = hash_password("a password nobody has")  # verified against when the email is unknown, to cost the same


def issue_token(user_id: str, settings: Settings) -> str:
    now = int(time.time())
    claims = {"sub": user_id, "iat": now, "exp": now + settings.jwt_expiration_minutes * 60}
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str, settings: Settings) -> str:
    """The user id in a valid token. Only HS256 is accepted, so an unsigned or re-signed token never passes."""
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        raise BankError(401, BAD_TOKEN) from None
    return claims["sub"]


@dataclass(frozen=True)
class Principal:
    """Who is calling, as stored now (not as the token claimed)."""
    user_id: ObjectId
    email: str
    role: str
    customer_id: ObjectId | None

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"


class AuthService:
    def __init__(self, db: Database, settings: Settings):
        self.settings = settings
        self.users = UserRepository(db)
        self.customers = CustomerRepository(db)
        self.db = db

    def _view(self, user: dict) -> AuthUser:
        name = user["name"]
        if user["customerId"] is not None and (customer := self.customers.get(user["customerId"])) is not None:
            name = customer["name"]  # follows a rename made by staff
        return AuthUser(email=user["email"], role=user["role"],
                        customer_id=None if user["customerId"] is None else str(user["customerId"]), name=name)

    def _token_for(self, user: dict) -> TokenResponse:
        return TokenResponse(token=issue_token(str(user["_id"]), self.settings), user=self._view(user))

    def register(self, data: RegisterRequest) -> TokenResponse:
        email, password_hash = str(data.email), hash_password(data.password)

        def work(session):
            # The customer and the login commit together or not at all.
            customer = self.customers.insert(data.name, email, session)
            return self.users.insert(email, password_hash, "CUSTOMER", customer["_id"], data.name, session)

        try:
            user = _in_transaction(self.db, work)
        except DuplicateKeyError:
            raise BankError(409, "A user with this email already exists") from None
        return self._token_for(user)

    def login(self, data: LoginRequest) -> TokenResponse:
        user = self.users.by_email(data.email)
        ok = verify_password(data.password, user["passwordHash"] if user else _DUMMY_HASH)
        if user is None or not ok or user.get("disabled"):
            raise BankError(401, BAD_LOGIN)
        return self._token_for(user)

    def authenticate(self, token: str | None) -> Principal:
        if not token:
            raise BankError(401, BAD_TOKEN)
        try:
            user = self.users.get(ObjectId(decode_token(token, self.settings)))
        except InvalidId:
            raise BankError(401, BAD_TOKEN) from None
        if user is None or user.get("disabled"):
            raise BankError(401, BAD_TOKEN)
        return Principal(user["_id"], user["email"], user["role"], user["customerId"])

    def me(self, principal: Principal) -> AuthUser:
        return self._view(self.users.get(principal.user_id))

    def bootstrap_admin(self) -> None:
        """Create the ADMIN from ADMIN_EMAIL and ADMIN_PASSWORD unless that email already has a login."""
        email, password = self.settings.admin_email, self.settings.admin_password
        if not email or not password:
            return
        if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
            raise RuntimeError(f"ADMIN_PASSWORD must be at least {MIN_ADMIN_PASSWORD_LENGTH} characters")
        if (existing := self.users.by_email(email)) is not None:
            if existing["role"] != "ADMIN":
                logger.warning("ADMIN_EMAIL %s already belongs to a non-admin user; no admin was created", email)
            return
        try:
            self.users.insert(email, hash_password(password), "ADMIN", None, "Administrator")
        except DuplicateKeyError:  # another instance started at the same moment and won
            return
        logger.info("Created the admin user %s", email)


def check_secret(settings: Settings) -> None:
    if len(settings.jwt_secret) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(f"JWT_SECRET must be set to at least {MIN_JWT_SECRET_LENGTH} characters")
