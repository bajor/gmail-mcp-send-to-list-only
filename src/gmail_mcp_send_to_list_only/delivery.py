"""Recipient resolution, MIME construction, and final outbound audit."""

from __future__ import annotations

import base64
from collections import Counter
from dataclasses import dataclass
from email import policy as email_policy
from email.headerregistry import Address
from email.message import EmailMessage, Message
from email.parser import BytesParser

from .config import AllowedRecipient, EmailAddress, RecipientAllowlist, RuntimePolicy

EXPECTED_HEADERS = Counter(
    {
        "from": 1,
        "to": 1,
        "subject": 1,
        "content-type": 1,
        "content-transfer-encoding": 1,
        "mime-version": 1,
    }
)


class DeliveryPolicyError(ValueError):
    """Raised before Gmail is called when a message violates delivery policy."""


@dataclass(frozen=True, slots=True)
class RecipientSelection:
    """Non-empty approved recipient subset in caller-supplied order."""

    recipients: tuple[AllowedRecipient, ...]

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(item.recipient_id.value for item in self.recipients)

    @property
    def addresses(self) -> tuple[str, ...]:
        return tuple(item.address.value for item in self.recipients)


@dataclass(frozen=True, slots=True)
class AuditedMessage:
    """Base64url MIME that passed the final recipient and structure audit."""

    raw_base64url: str
    recipient_ids: tuple[str, ...]
    recipient_addresses: tuple[str, ...]


def resolve_recipients(
    allowlist: RecipientAllowlist,
    recipient_ids: list[str],
) -> RecipientSelection:
    """Resolve a duplicate-free list of IDs without accepting raw addresses."""

    if not recipient_ids:
        raise DeliveryPolicyError("At least one recipient ID is required.")
    if len(recipient_ids) != len(set(recipient_ids)):
        raise DeliveryPolicyError("Recipient IDs must not contain duplicates.")
    allowed_by_id = allowlist.as_dict()
    unknown_ids = [
        recipient_id for recipient_id in recipient_ids if recipient_id not in allowed_by_id
    ]
    if unknown_ids:
        raise DeliveryPolicyError("Unknown recipient IDs: " + ", ".join(unknown_ids))
    return RecipientSelection(tuple(allowed_by_id[recipient_id] for recipient_id in recipient_ids))


def _header_addresses(message: Message, name: str) -> tuple[str, ...]:
    header = message[name]
    raw_addresses = getattr(header, "addresses", None)
    if not isinstance(raw_addresses, tuple):
        raise DeliveryPolicyError(f"The serialized {name} header is invalid.")
    addresses: list[str] = []
    for raw_address in raw_addresses:
        addr_spec = getattr(raw_address, "addr_spec", None)
        if not isinstance(addr_spec, str):
            raise DeliveryPolicyError(f"The serialized {name} address is invalid.")
        addresses.append(addr_spec)
    return tuple(addresses)


def audit_serialized_message(
    raw_message: bytes,
    *,
    sender: EmailAddress,
    selection: RecipientSelection,
) -> bytes:
    """Reject any serialized message that differs from the approved policy."""

    parsed = BytesParser(policy=email_policy.default).parsebytes(raw_message)
    if parsed.defects:
        raise DeliveryPolicyError("The serialized message contains MIME parser defects.")
    actual_headers = Counter(name.casefold() for name in parsed)
    if actual_headers != EXPECTED_HEADERS:
        raise DeliveryPolicyError("The serialized message contains unexpected headers.")
    if _header_addresses(parsed, "From") != (sender.value,):
        raise DeliveryPolicyError("The serialized From address does not match the policy.")
    if _header_addresses(parsed, "To") != selection.addresses:
        raise DeliveryPolicyError("The serialized recipients do not match the approved selection.")
    if parsed.is_multipart() or parsed.get_content_type() != "text/plain":
        raise DeliveryPolicyError("Only a single plain-text MIME body is allowed.")
    if parsed.get_content_disposition() is not None:
        raise DeliveryPolicyError("Attachments and content disposition are not allowed.")
    return raw_message


def create_audited_message(
    policy: RuntimePolicy,
    recipient_ids: list[str],
    subject: str,
    body_text: str,
) -> AuditedMessage:
    """Resolve recipients, create plain text MIME, audit it, and encode it."""

    if not isinstance(subject, str) or any(character in subject for character in "\r\n\0"):
        raise DeliveryPolicyError("Subject must be text without CR, LF, or NUL characters.")
    if not isinstance(body_text, str):
        raise DeliveryPolicyError("Body must be plain text.")
    selection = resolve_recipients(policy.allowlist, recipient_ids)
    message = EmailMessage(policy=email_policy.SMTP)
    message["From"] = Address(addr_spec=policy.sender.value)
    message["To"] = [Address(addr_spec=address) for address in selection.addresses]
    message["Subject"] = subject
    message.set_content(body_text, subtype="plain", charset="utf-8")
    raw_message = audit_serialized_message(
        message.as_bytes(),
        sender=policy.sender,
        selection=selection,
    )
    return AuditedMessage(
        raw_base64url=base64.urlsafe_b64encode(raw_message).decode("ascii"),
        recipient_ids=selection.ids,
        recipient_addresses=selection.addresses,
    )
