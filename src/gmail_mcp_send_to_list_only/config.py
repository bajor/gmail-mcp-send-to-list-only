"""Fail-closed delivery policy loaded from the process environment."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from email.errors import HeaderDefect, HeaderParseError
from email.headerregistry import Address
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SENDER_ENVIRONMENT_VARIABLE = "GMAIL_SENDER_EMAIL"
ALLOWLIST_ENVIRONMENT_VARIABLE = "GMAIL_ALLOWED_RECIPIENTS_JSON"
RECIPIENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


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
    def from_json(cls, raw_json: str) -> RecipientAllowlist:
        if not raw_json.strip():
            raise ConfigurationError(f"{ALLOWLIST_ENVIRONMENT_VARIABLE} must not be empty.")
        try:
            decoded = json.loads(raw_json, object_pairs_hook=_reject_duplicate_json_keys)
        except json.JSONDecodeError:
            raise ConfigurationError(
                f"{ALLOWLIST_ENVIRONMENT_VARIABLE} must be a valid JSON object."
            ) from None
        if not isinstance(decoded, dict) or not decoded:
            raise ConfigurationError(
                f"{ALLOWLIST_ENVIRONMENT_VARIABLE} must be a non-empty JSON object."
            )

        recipients: list[AllowedRecipient] = []
        address_owners: dict[str, str] = {}
        for raw_id, raw_address in sorted(decoded.items()):
            recipient_id = RecipientId.parse(raw_id)
            address = EmailAddress.parse(
                raw_address,
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


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key, value in pairs:
        if key in decoded:
            raise ConfigurationError(f"Duplicate recipient ID in allowlist JSON: {key!r}.")
        decoded[key] = value
    return decoded


def load_runtime_policy(
    environment: Mapping[str, str] | None = None,
    *,
    dotenv_path: str | Path | None = None,
) -> RuntimePolicy:
    """Load and validate the immutable delivery policy once at startup."""

    if environment is None:
        load_dotenv(dotenv_path=dotenv_path, override=False)
        active_environment: Mapping[str, str] = os.environ
    else:
        active_environment = environment

    raw_sender = active_environment.get(SENDER_ENVIRONMENT_VARIABLE)
    if raw_sender is None:
        raise ConfigurationError(f"{SENDER_ENVIRONMENT_VARIABLE} is required.")
    raw_allowlist = active_environment.get(ALLOWLIST_ENVIRONMENT_VARIABLE)
    if raw_allowlist is None:
        raise ConfigurationError(f"{ALLOWLIST_ENVIRONMENT_VARIABLE} is required.")
    return RuntimePolicy(
        sender=EmailAddress.parse(raw_sender, field_name=SENDER_ENVIRONMENT_VARIABLE),
        allowlist=RecipientAllowlist.from_json(raw_allowlist),
    )
