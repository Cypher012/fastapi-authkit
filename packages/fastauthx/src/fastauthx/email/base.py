"""The port. AuthEmailService depends only on this Protocol — never on
Resend or any other concrete provider. A host app passes in whichever
EmailSender it wants; fastauthx ships two adapters (console, Resend) as a
convenience, but any object satisfying this shape works."""

from typing import Protocol


class EmailSender(Protocol):
    async def send(
        self, *, to: str, subject: str, html: str, text: str | None = None
    ) -> None: ...
