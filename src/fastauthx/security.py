"""Framework-agnostic cryptographic primitives for authentication.

Nothing in this module knows about FastAPI, HTTP, the database, or
AuthConfig — it only hashes passwords and mints/reads JWTs from whatever
primitives it's constructed with. That separation is what lets
AuthService be unit-tested without a request in play, and lets this
module be imported before any config object exists.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

ACCESS_TOKEN_TYPE = "access"


class PasswordService:
    """Hashes and verifies passwords using Argon2id."""

    def __init__(self) -> None:
        self._hasher = PasswordHasher()

    def hash(self, plain_password: str) -> str:
        return self._hasher.hash(plain_password)

    def verify(self, plain_password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password_hash, plain_password)
        except VerificationError:
            return False


class JWTService:
    """Creates and decodes short-lived access tokens.

    Refresh tokens are intentionally *not* JWTs — they are opaque random
    strings whose hash is stored in `sessions`, so a token can be revoked
    server-side (a JWT can't be invalidated before it expires).
    """

    def __init__(self, *, secret_key: str, algorithm: str, expires_minutes: int) -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._expires_minutes = expires_minutes

    def create_access_token(self, user_id: UUID) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "type": ACCESS_TOKEN_TYPE,
            "iat": now,
            "exp": now + timedelta(minutes=self._expires_minutes),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def decode_access_token(self, token: str) -> dict:
        """Returns the token payload, or raises `jwt.PyJWTError` on any
        signature/expiry/format failure. Callers map that to a 401."""
        payload = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
        if payload.get("type") != ACCESS_TOKEN_TYPE:
            raise jwt.InvalidTokenError("Unexpected token type")
        return payload


def generate_opaque_token() -> str:
    """A high-entropy random token, not a JWT. Used for anything that
    must be revocable server-side before it expires: refresh tokens,
    email-verification links, password-reset links."""
    return secrets.token_urlsafe(48)


def hash_opaque_token(raw_token: str) -> str:
    """SHA-256 is sufficient (and fast) here: the token is already
    cryptographically random, so there's no offline brute-force risk to
    defend against the way there is with user-chosen passwords."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
