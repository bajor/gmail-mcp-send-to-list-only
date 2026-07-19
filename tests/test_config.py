from __future__ import annotations

from pathlib import Path

import pytest

from gmail_mcp_send_to_list_only.config import (
    ConfigurationError,
    EmailAddress,
    load_runtime_policy,
)


def _environment(**overrides: str) -> dict[str, str]:
    environment = {
        "GMAIL_SENDER_EMAIL": "sender@example.com",
        "GMAIL_ALLOSWED_RECIPENTS": "bob@example.com,alice@example.com",
    }
    environment.update(overrides)
    return environment


def test_load_runtime_policy_returns_sender() -> None:
    policy = load_runtime_policy(_environment())

    assert policy.sender == EmailAddress("sender@example.com")


def test_load_runtime_policy_returns_generated_ids_in_configured_order() -> None:
    policy = load_runtime_policy(_environment())

    assert [item.recipient_id.value for item in policy.allowlist.recipients] == [
        "recipient_1",
        "recipient_2",
    ]
    assert [item.address.value for item in policy.allowlist.recipients] == [
        "bob@example.com",
        "alice@example.com",
    ]


@pytest.mark.parametrize(
    "missing_name",
    ["GMAIL_SENDER_EMAIL", "GMAIL_ALLOSWED_RECIPENTS"],
)
def test_required_environment_values_are_fail_closed(missing_name: str) -> None:
    environment = _environment()
    del environment[missing_name]

    with pytest.raises(ConfigurationError, match=f"{missing_name} is required"):
        load_runtime_policy(environment)


def test_runtime_policy_ignores_dotenv_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GMAIL_SENDER_EMAIL", raising=False)
    monkeypatch.delenv("GMAIL_ALLOSWED_RECIPENTS", raising=False)
    (tmp_path / ".env").write_text(
        "GMAIL_SENDER_EMAIL=sender@example.com\n"
        "GMAIL_ALLOSWED_RECIPENTS=alice@example.com\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="GMAIL_SENDER_EMAIL is required"):
        load_runtime_policy()


@pytest.mark.parametrize(
    "raw_addresses",
    ["", ",", "alice@example.com,"],
)
def test_allowlist_rejects_empty_address_entries(raw_addresses: str) -> None:
    with pytest.raises(ConfigurationError):
        load_runtime_policy(_environment(GMAIL_ALLOSWED_RECIPENTS=raw_addresses))


@pytest.mark.parametrize(
    "address",
    [
        "Alice <alice@example.com>",
        "alice@example.com\r\nBcc:evil@example.com",
        "ü@example.com",
        "missing-domain@",
    ],
)
def test_allowlist_rejects_noncanonical_or_unsafe_addresses(address: str) -> None:
    with pytest.raises(ConfigurationError):
        load_runtime_policy(_environment(GMAIL_ALLOSWED_RECIPENTS=address))


def test_allowlist_allows_spaces_around_commas() -> None:
    policy = load_runtime_policy(
        _environment(GMAIL_ALLOSWED_RECIPENTS="alice@example.com, bob@example.com")
    )

    assert [item.address.value for item in policy.allowlist.recipients] == [
        "alice@example.com",
        "bob@example.com",
    ]


def test_allowlist_rejects_duplicate_addresses_case_insensitively() -> None:
    with pytest.raises(ConfigurationError, match="use the same address"):
        load_runtime_policy(
            _environment(GMAIL_ALLOSWED_RECIPENTS="person@example.com,PERSON@EXAMPLE.COM")
        )
