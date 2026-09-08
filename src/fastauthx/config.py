"""The entire public configuration surface of fastauthx. A host app builds
one `AuthConfig` (usually from its own Settings) and passes it to
`create_auth_router` — nothing else in this package reads environment
variables or global state directly."""

from pydantic import BaseModel


class TokenConfig(BaseModel):
    algorithm: str = "HS256"
    access_expire_minutes: int = 15
    refresh_expire_days: int = 30


class VerificationConfig(BaseModel):
    email_expire_hours: int = 24
    password_reset_expire_minutes: int = 30


class GoogleOAuthConfig(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: str


class AuthConfig(BaseModel):
    secret_key: str
    frontend_url: str
    secure_cookies: bool = True

    tokens: TokenConfig = TokenConfig()
    verification: VerificationConfig = VerificationConfig()

    # Keyed by provider name (currently only "google" is implemented —
    # see fastauthx.oauth). A dict rather than named fields because the set
    # of providers is open-ended; adding one later is a new key, not a
    # new AuthConfig field.
    oauth: dict[str, GoogleOAuthConfig] = {}
