"""Dev/test adapter: logs instead of sending. Handy default for local
development and test suites so nobody needs a real provider or API key
just to exercise the auth flows."""

import logging

logger = logging.getLogger("fastauthx.email")


class ConsoleEmailSender:
    async def send(
        self, *, to: str, subject: str, html: str, text: str | None = None
    ) -> None:
        logger.info("EMAIL to=%s subject=%r\n%s", to, subject, text or html)
