from fastauthx.email.base import EmailSender
from fastauthx.email.console import ConsoleEmailSender

__all__ = ["EmailSender", "ConsoleEmailSender"]

try:
    from fastauthx.email.resend import ResendEmailSender  # noqa: F401

    __all__.append("ResendEmailSender")
except ImportError:
    pass
