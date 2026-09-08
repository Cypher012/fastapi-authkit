"""Owns *what* the verification/reset emails say. Knows nothing about how
they're actually sent — that's delegated to whatever EmailSender it was
given, so switching providers never touches this file."""

from fastauthx.config import VerificationConfig
from fastauthx.email.base import EmailSender


class AuthEmailService:
    def __init__(
        self,
        email_sender: EmailSender,
        frontend_url: str,
        verification_config: VerificationConfig,
    ) -> None:
        self._email_sender = email_sender
        self._frontend_url = frontend_url
        self._verification_config = verification_config

    async def send_verification_email(
        self, *, to_email: str, name: str, raw_token: str
    ) -> None:
        link = f"{self._frontend_url}/verify-email?token={raw_token}"
        await self._email_sender.send(
            to=to_email,
            subject="Verify your email address",
            html=(
                f"<p>Hi {name},</p>"
                "<p>Confirm your email address by clicking the link below:</p>"
                f'<p><a href="{link}">Verify email</a></p>'
                f"<p>This link expires in {self._verification_config.email_expire_hours} hours.</p>"
            ),
            text=f"Hi {name}, verify your email: {link}",
        )

    async def send_password_reset_email(
        self, *, to_email: str, name: str, raw_token: str
    ) -> None:
        link = f"{self._frontend_url}/reset-password?token={raw_token}"
        await self._email_sender.send(
            to=to_email,
            subject="Reset your password",
            html=(
                f"<p>Hi {name},</p>"
                "<p>Someone requested a password reset for your account. "
                "If this was you, click the link below:</p>"
                f'<p><a href="{link}">Reset password</a></p>'
                f"<p>This link expires in {self._verification_config.password_reset_expire_minutes} minutes. "
                "If you didn't request this, you can safely ignore this email.</p>"
            ),
            text=f"Hi {name}, reset your password: {link}",
        )
