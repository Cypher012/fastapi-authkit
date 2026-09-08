"""Authlib client registry, built from AuthConfig.oauth.

Unlike email, this isn't hidden behind our own port — Authlib already
*is* the abstraction the OAuth flow needs, and each provider has a
genuinely different claims/registration shape, so wrapping it further
would just be indirection without a second real implementation to
justify it. Only "google" is wired up today; adding a second provider
means adding another `if` branch here, plus a claims-mapper in
fastauthx.routes — not a rewrite.
"""

from authlib.integrations.starlette_client import OAuth

from fastauthx.config import AuthConfig


def build_oauth_client(config: AuthConfig) -> OAuth:
    oauth = OAuth()

    google_config = config.oauth.get("google")
    if google_config is not None:
        oauth.register(
            name="google",
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_id=google_config.client_id,
            client_secret=google_config.client_secret,
            client_kwargs={"scope": "openid email profile"},
        )

    return oauth
