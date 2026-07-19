"""Fail-closed delivery policy loaded from the process environment."""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from email.errors import HeaderDefect, HeaderParseError
from email.headerregistry import Address
from pathlib import Path

SENDER_ENVIRONMENT_VARIABLE = "GMAIL_SENDER_EMAIL"
ALLOWLIST_ENVIRONMENT_VARIABLE = "GMAIL_ALLOSWED_RECIPENTS"
CLIENT_SECRET_ENVIRONMENT_VARIABLE = "GMAIL_CLIENT_SECRET_FILE"
TOKEN_ENVIRONMENT_VARIABLE = "GMAIL_TOKEN_FILE"
RECIPIENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
DEFAULT_TOKEN_FILE = Path("~/.config/gmail-mcp-send-to-list-only/token.json")


class ConfigurationError(ValueError):
    """Raised when the recipient policy is missing or invalid."""


@dataclass(frozen=True, slots=True)
class EmailAddress:
    """One validated ASCII email addr-spec without a display name."""

    value: str

    @classmethod
    def parse(cls, raw_value: object, *, field_name: str) -> EmailAddress:
        if not isinstance(raw_value, str):
            raise ConfigurationError(f"{field_name} must be a string email address.")
        if raw_value != raw_value.strip() or not raw_value or not raw_value.isascii():
            raise ConfigurationError(
                f"{field_name} must be one non-empty ASCII email address without surrounding space."
            )
        if any(unicodedata.category(character) == "Cc" for character in raw_value):
            raise ConfigurationError(f"{field_name} must not contain control characters.")
        try:
            parsed_address = Address(addr_spec=raw_value)
        except (HeaderDefect, HeaderParseError, IndexError, ValueError):
            raise ConfigurationError(
                f"{field_name} must be one valid email address without a display name."
            ) from None
        if not parsed_address.username or not parsed_address.domain:
            raise ConfigurationError(f"{field_name} must contain a local part and domain.")
        return cls(parsed_address.addr_spec)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class RecipientId:
    """Stable caller-facing identifier for one approved recipient."""

    value: str

    @classmethod
    def parse(cls, raw_value: object) -> RecipientId:
        if not isinstance(raw_value, str) or RECIPIENT_ID_PATTERN.fullmatch(raw_value) is None:
            raise ConfigurationError(
                "Recipient IDs must start with a lowercase letter and contain only "
                "lowercase letters, digits, underscores, or hyphens (maximum 64 characters)."
            )
        return cls(raw_value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class AllowedRecipient:
    """One configured recipient ID and its immutable address."""

    recipient_id: RecipientId
    address: EmailAddress


@dataclass(frozen=True, slots=True)
class RecipientAllowlist:
    """Non-empty, duplicate-free collection of allowed recipients."""

    recipients: tuple[AllowedRecipient, ...]

    @classmethod
    def from_comma_separated_addresses(cls, raw_addresses: str) -> RecipientAllowlist:
        if not raw_addresses.strip():
            raise ConfigurationError(f"{ALLOWLIST_ENVIRONMENT_VARIABLE} must not be empty.")

        recipients: list[AllowedRecipient] = []
        address_owners: dict[str, str] = {}
        for index, raw_address in enumerate(raw_addresses.split(","), start=1):
            recipient_id = RecipientId.parse(f"recipient_{index}")
            address = EmailAddress.parse(
                raw_address.strip(),
                field_name=f"Recipient {recipient_id.value!r}",
            )
            canonical_address = address.value.casefold()
            previous_owner = address_owners.get(canonical_address)
            if previous_owner is not None:
                raise ConfigurationError(
                    f"Recipients {previous_owner!r} and {recipient_id.value!r} "
                    "use the same address."
                )
            address_owners[canonical_address] = recipient_id.value
            recipients.append(AllowedRecipient(recipient_id, address))
        return cls(tuple(recipients))

    def as_dict(self) -> dict[str, AllowedRecipient]:
        return {recipient.recipient_id.value: recipient for recipient in self.recipients}


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    """Complete sender and recipient policy required by the MCP server."""

    sender: EmailAddress
    allowlist: RecipientAllowlist


@dataclass(frozen=True, slots=True)
class AuthConfig:
    """Resolved local paths used by Gmail OAuth."""

    client_secret_file: Path | None
    token_file: Path

    def require_client_secret_file(self) -> Path:
        path = self.client_secret_file
        if path is None:
            raise ConfigurationError(f"{CLIENT_SECRET_ENVIRONMENT_VARIABLE} is required.")
        if not path.is_file():
            raise ConfigurationError("The configured Gmail client secret is not a file.")
        return path


def _active_environment(
    environment: Mapping[str, str] | None,
) -> Mapping[str, str]:
    if environment is not None:
        return environment
    return os.environ


def _configured_path(raw_value: str | None, default: Path | None = None) -> Path | None:
    path = default if raw_value is None or not raw_value.strip() else Path(raw_value.strip())
    return path.expanduser().resolve(strict=False) if path is not None else None


def load_runtime_policy(
    environment: Mapping[str, str] | None = None,
) -> RuntimePolicy:
    """Load and validate the immutable delivery policy once at startup."""

    active_environment = _active_environment(environment)

    raw_sender = active_environment.get(SENDER_ENVIRONMENT_VARIABLE)
    if raw_sender is None:
        raise ConfigurationError(f"{SENDER_ENVIRONMENT_VARIABLE} is required.")
    raw_allowlist = active_environment.get(ALLOWLIST_ENVIRONMENT_VARIABLE)
    if raw_allowlist is None:
        raise ConfigurationError(f"{ALLOWLIST_ENVIRONMENT_VARIABLE} is required.")
    return RuntimePolicy(
        sender=EmailAddress.parse(raw_sender, field_name=SENDER_ENVIRONMENT_VARIABLE),
        allowlist=RecipientAllowlist.from_comma_separated_addresses(raw_allowlist),
    )


def load_auth_config(
    environment: Mapping[str, str] | None = None,
) -> AuthConfig:
    """Load OAuth paths while allowing doctor to report a missing client secret."""

    active_environment = _active_environment(environment)
    client_secret_file = _configured_path(
        active_environment.get(CLIENT_SECRET_ENVIRONMENT_VARIABLE)
    )
    token_file = _configured_path(
        active_environment.get(TOKEN_ENVIRONMENT_VARIABLE),
        DEFAULT_TOKEN_FILE,
    )
    assert token_file is not None
    return AuthConfig(client_secret_file=client_secret_file, token_file=token_file)
