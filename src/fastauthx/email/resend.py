"""Adapter over the Resend SDK. Satisfies the EmailSender protocol
structurally (no inheritance needed) — this is the only file in the
package that imports `resend`. Resend isn't even a listed dependency of
fastauthx (see pyproject.toml) — a host app that wants this adapter
installs `resend` itself; everyone else never pays for it."""

import resend


class ResendEmailSender:
    def __init__(self, api_key: str, from_address: str) -> None:
        resend.api_key = api_key
        self._from_address = from_address

    async def send(
        self, *, to: str, subject: str, html: str, text: str | None = None
    ) -> None:
        params: resend.Emails.SendParams = {
            "from": self._from_address,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if text is not None:
            params["text"] = text
        await resend.Emails.send_async(params)
