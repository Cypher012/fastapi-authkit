"""Domain-level errors for authentication.

AuthService raises these instead of HTTPException so it stays independent
of FastAPI/HTTP. fastauthx's own router registers the FastAPI exception
handler that maps these to status codes (see fastauthx.routes) — a host
app embedding fastauthx's router gets this mapping for free.
"""


class AuthError(Exception):
    """Base class for authentication domain errors."""

    default_message = "Authentication error."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)


class EmailAlreadyRegisteredError(AuthError):
    default_message = "An account with this email already exists."


class InvalidCredentialsError(AuthError):
    default_message = "Incorrect email or password."


class InvalidRefreshTokenError(AuthError):
    default_message = "Refresh token is missing, expired, or revoked."


class InvalidAccessTokenError(AuthError):
    default_message = "Could not validate credentials."


class InvalidVerificationTokenError(AuthError):
    """Shared by email verification and password reset — both are the
    same underlying mechanism (a single-use hashed token in `verification`),
    so a single error type covers both without adding meaningless variety."""

    default_message = "This link is invalid or has expired."


class OAuthAccountError(AuthError):
    """Google sign-in failed, or succeeded but can't be safely linked to
    an existing account (e.g. Google reports the email as unverified)."""

    default_message = "Could not complete sign-in with Google."
