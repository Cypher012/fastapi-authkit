"""Domain errors for organizations/membership, kept independent of HTTP
for the same reason as fastauthx core's AuthError: business rules
shouldn't know about status codes."""


class OrgsError(Exception):
    default_message = "Organization error."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)


class OrganizationNotFoundError(OrgsError):
    default_message = "Organization not found."


class NotAMemberError(OrgsError):
    """Deliberately the same message/status whether the organization
    doesn't exist or the caller just isn't a member of it — never confirm
    to an unauthorized caller that an organization ID is even valid."""

    default_message = "Organization not found."


class InsufficientRoleError(OrgsError):
    default_message = "You do not have permission to perform this action."


class LastOwnerError(OrgsError):
    """Raised by attempts to demote or remove an organization's only
    remaining OWNER — doing so would leave the organization ownerless."""

    default_message = "An organization must have at least one owner."


class AlreadyAMemberError(OrgsError):
    default_message = "This user is already a member of the organization."


class InvitationNotFoundError(OrgsError):
    default_message = "Invitation not found."


class InvitationExpiredError(OrgsError):
    default_message = "This invitation has expired."


class InvitationAlreadyAcceptedError(OrgsError):
    default_message = "This invitation has already been accepted."


class InvitationEmailMismatchError(OrgsError):
    """The milestone's "verify the accepting user is the intended
    recipient" rule: an invitation for alice@example.com can't be
    accepted by a logged-in bob@example.com, even with a valid token."""

    default_message = "This invitation was sent to a different email address."
