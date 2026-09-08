"""The package's only public entry point for wiring auth into a FastAPI
app: `create_auth_router(...)`. Routes here are thin: parse request ->
call AuthService -> shape response. All policy lives in AuthService.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlencode

from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from fastauthx.config import AuthConfig
from fastauthx.dependencies import (
    REFRESH_TOKEN_COOKIE_NAME,
    GetSession,
    build_dependencies,
)
from fastauthx.email.base import EmailSender
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
from fastauthx.models import Users
from fastauthx.oauth import build_oauth_client
from fastauthx.schemas import (
    AccessTokenResponse,
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    UserPublic,
    VerifyEmailRequest,
)
from fastauthx.service import AuthService, GoogleProfile

REFRESH_TOKEN_COOKIE_PATH = "/auth"

_STATUS_BY_AUTH_ERROR: dict[type[AuthError], int] = {
    EmailAlreadyRegisteredError: status.HTTP_409_CONFLICT,
    InvalidCredentialsError: status.HTTP_401_UNAUTHORIZED,
    InvalidRefreshTokenError: status.HTTP_401_UNAUTHORIZED,
    InvalidAccessTokenError: status.HTTP_401_UNAUTHORIZED,
    # 400, not 401: neither of these is a bearer-auth failure (no
    # WWW-Authenticate applies) — they're a bad/expired one-time link, or
    # a failed/unsafe OAuth exchange, that the client posted.
    InvalidVerificationTokenError: status.HTTP_400_BAD_REQUEST,
    OAuthAccountError: status.HTTP_400_BAD_REQUEST,
}


@dataclass
class FastAuthXKit:
    router: APIRouter
    get_current_user: Callable[..., Awaitable[Users]]
    install_exception_handlers: Callable[[FastAPI], None]


def create_auth_router(
    config: AuthConfig,
    *,
    get_session: GetSession,
    email_sender: EmailSender,
    hooks: AuthHooks | None = None,
) -> FastAuthXKit:
    deps = build_dependencies(
        config=config, get_session=get_session, email_sender=email_sender, hooks=hooks
    )
    oauth = build_oauth_client(config)
    router = APIRouter(prefix="/auth", tags=["auth"])

    def _set_refresh_token_cookie(response: Response, raw_refresh_token: str) -> None:
        response.set_cookie(
            key=REFRESH_TOKEN_COOKIE_NAME,
            value=raw_refresh_token,
            max_age=config.tokens.refresh_expire_days * 24 * 60 * 60,
            path=REFRESH_TOKEN_COOKIE_PATH,
            httponly=True,
            secure=config.secure_cookies,
            samesite="lax",
        )

    def _clear_refresh_token_cookie(response: Response) -> None:
        response.delete_cookie(
            key=REFRESH_TOKEN_COOKIE_NAME, path=REFRESH_TOKEN_COOKIE_PATH
        )

    @router.post(
        "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
    )
    async def register(
        data: RegisterRequest,
        response: Response,
        auth_service: Annotated[AuthService, Depends(deps.get_auth_service)],
    ) -> AuthResponse:
        user, access_token, refresh_token = await auth_service.register(data)
        _set_refresh_token_cookie(response, refresh_token)
        return AuthResponse(
            access_token=access_token, user=UserPublic.model_validate(user)
        )

    @router.post("/login", response_model=AuthResponse)
    async def login(
        data: LoginRequest,
        response: Response,
        auth_service: Annotated[AuthService, Depends(deps.get_auth_service)],
    ) -> AuthResponse:
        user, access_token, refresh_token = await auth_service.login(data)
        _set_refresh_token_cookie(response, refresh_token)
        return AuthResponse(
            access_token=access_token, user=UserPublic.model_validate(user)
        )

    @router.post("/refresh", response_model=AccessTokenResponse)
    async def refresh(
        response: Response,
        auth_service: Annotated[AuthService, Depends(deps.get_auth_service)],
        current_refresh_token: Annotated[str, Depends(deps.get_refresh_token)],
    ) -> AccessTokenResponse:
        access_token, new_refresh_token = await auth_service.refresh(
            current_refresh_token
        )
        _set_refresh_token_cookie(response, new_refresh_token)
        return AccessTokenResponse(access_token=access_token)

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(
        response: Response,
        auth_service: Annotated[AuthService, Depends(deps.get_auth_service)],
        current_refresh_token: Annotated[str, Depends(deps.get_refresh_token)],
    ) -> None:
        await auth_service.logout(current_refresh_token)
        _clear_refresh_token_cookie(response)

    @router.get("/me", response_model=UserPublic)
    async def me(
        current_user: Annotated[Users, Depends(deps.get_current_user)],
    ) -> UserPublic:
        return UserPublic.model_validate(current_user)

    @router.post("/verify-email", response_model=MessageResponse)
    async def verify_email(
        data: VerifyEmailRequest,
        auth_service: Annotated[AuthService, Depends(deps.get_auth_service)],
    ) -> MessageResponse:
        await auth_service.verify_email(data.token)
        return MessageResponse(message="Email verified.")

    @router.post(
        "/verify-email/resend",
        response_model=MessageResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def resend_verification_email(
        current_user: Annotated[Users, Depends(deps.get_current_user)],
        auth_service: Annotated[AuthService, Depends(deps.get_auth_service)],
    ) -> MessageResponse:
        await auth_service.resend_verification_email(current_user)
        return MessageResponse(
            message="If your email isn't already verified, a new link has been sent."
        )

    @router.post(
        "/forgot-password",
        response_model=MessageResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def forgot_password(
        data: ForgotPasswordRequest,
        auth_service: Annotated[AuthService, Depends(deps.get_auth_service)],
    ) -> MessageResponse:
        """Always returns 202 with the same message, whether or not the
        email is registered — see AuthService.request_password_reset."""
        await auth_service.request_password_reset(data.email)
        return MessageResponse(
            message="If that email is registered, a reset link has been sent."
        )

    @router.post("/reset-password", response_model=MessageResponse)
    async def reset_password(
        data: ResetPasswordRequest,
        auth_service: Annotated[AuthService, Depends(deps.get_auth_service)],
    ) -> MessageResponse:
        await auth_service.reset_password(data.token, data.new_password)
        return MessageResponse(message="Password has been reset. Please log in again.")

    if "google" in config.oauth:

        @router.get("/google/login")
        async def google_login(request: Request):
            """Redirects the browser to Google's consent screen. Authlib
            stashes a `state`/`nonce` pair in the session cookie (host app
            must add Starlette's SessionMiddleware) and checks it back in
            the callback — that's the CSRF protection for the whole flow."""
            return await oauth.google.authorize_redirect(
                request, config.oauth["google"].redirect_uri
            )

        @router.get("/google/callback")
        async def google_callback(
            request: Request,
            auth_service: Annotated[AuthService, Depends(deps.get_auth_service)],
        ) -> RedirectResponse:
            try:
                token = await oauth.google.authorize_access_token(request)
            except OAuthError as exc:
                raise OAuthAccountError(str(exc)) from exc

            claims = token.get("userinfo")
            if claims is None or "sub" not in claims or "email" not in claims:
                raise OAuthAccountError(
                    "Google did not return the expected profile data."
                )

            profile = GoogleProfile(
                sub=claims["sub"],
                email=claims["email"],
                name=claims.get("name") or claims["email"],
                avatar_url=claims.get("picture"),
                email_verified=bool(claims.get("email_verified", False)),
            )

            _, access_token, refresh_token = (
                await auth_service.login_or_register_with_google(profile)
            )

            # The access token travels in the URL *fragment*, not a query
            # string: fragments are never sent to the server (no
            # server/proxy access-log leak, no Referer leak) and are only
            # readable by frontend JS via window.location.hash.
            fragment = urlencode({"access_token": access_token})
            redirect_response = RedirectResponse(
                url=f"{config.frontend_url}/oauth/callback#{fragment}"
            )
            _set_refresh_token_cookie(redirect_response, refresh_token)
            return redirect_response

    def install_exception_handlers(app: FastAPI) -> None:
        """Must be called once by the host app — FastAPI only lets the
        top-level app register exception handlers, not sub-routers, so
        create_auth_router can't do this on its own."""

        @app.exception_handler(AuthError)
        async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
            status_code = _STATUS_BY_AUTH_ERROR.get(
                type(exc), status.HTTP_400_BAD_REQUEST
            )
            headers = (
                {"WWW-Authenticate": "Bearer"}
                if status_code == status.HTTP_401_UNAUTHORIZED
                else None
            )
            detail = str(exc) or exc.__class__.__name__
            return JSONResponse(
                status_code=status_code, content={"detail": detail}, headers=headers
            )

    return FastAuthXKit(
        router=router,
        get_current_user=deps.get_current_user,
        install_exception_handlers=install_exception_handlers,
    )
