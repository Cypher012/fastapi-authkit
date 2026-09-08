"""FastAPI dependency wiring, built once by `create_auth_router` and
closed over `config`/`get_session`/`email_sender`/`hooks` — nothing here
reads global state, so two `create_auth_router` calls in the same
process (e.g. in tests) never share state by accident.
"""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Cookie, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from fastauthx.config import AuthConfig
from fastauthx.email.base import EmailSender
from fastauthx.email_service import AuthEmailService
from fastauthx.exceptions import InvalidAccessTokenError, InvalidRefreshTokenError
from fastauthx.hooks import AuthHooks
from fastauthx.models import Users
from fastauthx.repository import AuthRepository
from fastauthx.security import JWTService, PasswordService
from fastauthx.service import AuthService

REFRESH_TOKEN_COOKIE_NAME = "refresh_token"

GetSession = Callable[[], AsyncIterator[AsyncSession]]


@dataclass
class AuthDependencies:
    get_auth_service: Callable[..., AuthService]
    get_refresh_token: Callable[..., str]
    get_current_user: Callable[..., "AsyncIterator[Users] | Users"]


def build_dependencies(
    *,
    config: AuthConfig,
    get_session: GetSession,
    email_sender: EmailSender,
    hooks: AuthHooks | None,
) -> AuthDependencies:
    bearer_scheme = HTTPBearer(auto_error=False)

    def _build_jwt_service() -> JWTService:
        return JWTService(
            secret_key=config.secret_key,
            algorithm=config.tokens.algorithm,
            expires_minutes=config.tokens.access_expire_minutes,
        )

    def get_auth_service(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> AuthService:
        return AuthService(
            repository=AuthRepository(session),
            password_service=PasswordService(),
            jwt_service=_build_jwt_service(),
            email_service=AuthEmailService(
                email_sender=email_sender,
                frontend_url=config.frontend_url,
                verification_config=config.verification,
            ),
            token_config=config.tokens,
            verification_config=config.verification,
            hooks=hooks,
        )

    def get_refresh_token(
        refresh_token: Annotated[
            str | None, Cookie(alias=REFRESH_TOKEN_COOKIE_NAME)
        ] = None,
    ) -> str:
        if refresh_token is None:
            raise InvalidRefreshTokenError()
        return refresh_token

    async def get_current_user(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
        ],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> Users:
        if credentials is None:
            raise InvalidAccessTokenError()

        try:
            payload = _build_jwt_service().decode_access_token(credentials.credentials)
            user_id = UUID(payload["sub"])
        except (jwt.PyJWTError, ValueError) as exc:
            raise InvalidAccessTokenError() from exc

        user = await AuthRepository(session).get_user_by_id(user_id)
        if user is None:
            raise InvalidAccessTokenError()
        return user

    return AuthDependencies(
        get_auth_service=get_auth_service,
        get_refresh_token=get_refresh_token,
        get_current_user=get_current_user,
    )
