"""fastauthx's public surface. Anything a host app needs is importable
directly from here — internals (fastauthx.dependencies, fastauthx.security,
fastauthx.repository, ...) are implementation detail."""

from fastauthx.config import AuthConfig, GoogleOAuthConfig, TokenConfig, VerificationConfig
from fastauthx.email.base import EmailSender
from fastauthx.email.console import ConsoleEmailSender
from fastauthx.exceptions import (
    AuthError,
    EmailAlreadyRegisteredError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidVerificationTokenError,
    OAuthAccountError,
)
from fastauthx.hooks import AuthHooks
from fastauthx.models import Accounts, ProviderEnum, Sessions, Users, Verification, VerificationTypeEnum
from fastauthx.routes import FastAuthXKit, create_auth_router

__all__ = [
    "AuthConfig",
    "AuthError",
    "AuthHooks",
    "FastAuthXKit",
    "Accounts",
    "ConsoleEmailSender",
    "EmailAlreadyRegisteredError",
    "EmailSender",
    "GoogleOAuthConfig",
    "InvalidAccessTokenError",
    "InvalidCredentialsError",
    "InvalidRefreshTokenError",
    "InvalidVerificationTokenError",
    "OAuthAccountError",
    "ProviderEnum",
    "Sessions",
    "TokenConfig",
    "Users",
    "Verification",
    "VerificationConfig",
    "VerificationTypeEnum",
    "create_auth_router",
]
