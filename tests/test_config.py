from __future__ import annotations

import json

import pytest

from gmail_mcp_send_to_list_only.config import (
    ConfigurationError,
    EmailAddress,
    load_runtime_policy,
)


def _environment(**overrides: str) -> dict[str, str]:
    environment = {
        "GMAIL_SENDER_EMAIL": "sender@example.com",
        "GMAIL_ALLOWED_RECIPIENTS_JSON": (
            '{"bob":"bob@example.com","alice":"alice@example.com"}'
        ),
    }
    environment.update(overrides)
    return environment


def test_load_runtime_policy_returns_sorted_frozen_domain_values() -> None:
    policy = load_runtime_policy(_environment())

    assert policy.sender == EmailAddress("sender@example.com")
    assert [item.recipient_id.value for item in policy.allowlist.recipients] == ["alice", "bob"]
    assert [item.address.value for item in policy.allowlist.recipients] == [
        "alice@example.com",
        "bob@example.com",
    ]


@pytest.mark.parametrize(
    "missing_name",
    ["GMAIL_SENDER_EMAIL", "GMAIL_ALLOWED_RECIPIENTS_JSON"],
)
def test_required_environment_values_are_fail_closed(missing_name: str) -> None:
    environment = _environment()
    del environment[missing_name]

    with pytest.raises(ConfigurationError, match=f"{missing_name} is required"):
        load_runtime_policy(environment)


@pytest.mark.parametrize(
    "raw_json",
    ["", "not-json", "[]", "{}", '{"alice": 123}'],
)
def test_allowlist_rejects_invalid_json_shapes(raw_json: str) -> None:
    with pytest.raises(ConfigurationError):
        load_runtime_policy(_environment(GMAIL_ALLOWED_RECIPIENTS_JSON=raw_json))


def test_allowlist_rejects_duplicate_json_keys() -> None:
    raw_json = '{"alice":"a@example.com","alice":"b@example.com"}'

    with pytest.raises(ConfigurationError, match="Duplicate recipient ID"):
        load_runtime_policy(_environment(GMAIL_ALLOWED_RECIPIENTS_JSON=raw_json))


@pytest.mark.parametrize(
    "recipient_id",
    ["", "Alice", "1alice", "alice.example", "alice space", "a" * 65],
)
def test_allowlist_rejects_invalid_recipient_ids(recipient_id: str) -> None:
    raw_json = f'{{"{recipient_id}":"alice@example.com"}}'

    with pytest.raises(ConfigurationError, match="Recipient IDs"):
        load_runtime_policy(_environment(GMAIL_ALLOWED_RECIPIENTS_JSON=raw_json))


@pytest.mark.parametrize(
    "address",
    [
        "",
        " alice@example.com",
        "Alice <alice@example.com>",
        "alice@example.com,bob@example.com",
        "alice@example.com\r\nBcc:evil@example.com",
        "ü@example.com",
        "missing-domain@",
    ],
)
def test_allowlist_rejects_noncanonical_or_unsafe_addresses(address: str) -> None:
    raw_json = '{"alice":' + json.dumps(address) + "}"

    with pytest.raises(ConfigurationError):
        load_runtime_policy(_environment(GMAIL_ALLOWED_RECIPIENTS_JSON=raw_json))


def test_allowlist_rejects_duplicate_addresses_case_insensitively() -> None:
    raw_json = '{"alice":"person@example.com","bob":"PERSON@EXAMPLE.COM"}'

    with pytest.raises(ConfigurationError, match="use the same address"):
        load_runtime_policy(_environment(GMAIL_ALLOWED_RECIPIENTS_JSON=raw_json))
