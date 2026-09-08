"""Owns *what* the invitation email says. Knows nothing about how it's
actually sent — delegated to whatever EmailSender it's given, same port
fastauthx core's AuthEmailService uses for verification/reset emails."""

from fastauthx.email.base import EmailSender


class OrgsEmailService:
    def __init__(self, email_sender: EmailSender, frontend_url: str) -> None:
        self._email_sender = email_sender
        self._frontend_url = frontend_url

    async def send_invitation_email(
        self, *, to_email: str, organization_name: str, raw_token: str
    ) -> None:
        link = f"{self._frontend_url}/invitations/{raw_token}"
        await self._email_sender.send(
            to=to_email,
            subject=f"You've been invited to join {organization_name}",
            html=(
                f"<p>You've been invited to join <strong>{organization_name}</strong>.</p>"
                f'<p><a href="{link}">Accept invitation</a></p>'
                "<p>If you weren't expecting this, you can ignore this email.</p>"
            ),
            text=f"You've been invited to join {organization_name}: {link}",
        )
