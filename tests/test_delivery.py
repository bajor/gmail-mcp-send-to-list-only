from __future__ import annotations

import base64
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

import pytest

from gmail_mcp_send_to_list_only.config import load_runtime_policy
from gmail_mcp_send_to_list_only.delivery import (
    DeliveryPolicyError,
    audit_serialized_message,
    create_audited_message,
    resolve_recipients,
)


def _policy():
    return load_runtime_policy(
        {
            "GMAIL_SENDER_EMAIL": "sender@example.com",
            "GMAIL_ALLOWED_RECIPIENTS_JSON": (
                '{"alice":"alice@example.com","bob":"bob@example.com"}'
            ),
        }
    )


def test_create_audited_message_uses_only_selected_to_addresses() -> None:
    audited = create_audited_message(_policy(), ["bob", "alice"], "Hello", "Plain body")
    raw_message = base64.urlsafe_b64decode(audited.raw_base64url)
    parsed = BytesParser(policy=policy.default).parsebytes(raw_message)

    assert [address.addr_spec for address in parsed["To"].addresses] == [
        "bob@example.com",
        "alice@example.com",
    ]
    assert parsed["Cc"] is None
    assert parsed["Bcc"] is None
    assert parsed.get_content_type() == "text/plain"
    assert audited.recipient_ids == ("bob", "alice")


@pytest.mark.parametrize("recipient_ids", [[], ["unknown"], ["alice", "alice"]])
def test_invalid_recipient_selections_fail_before_composition(recipient_ids: list[str]) -> None:
    with pytest.raises(DeliveryPolicyError):
        create_audited_message(_policy(), recipient_ids, "Subject", "Body")


def test_subject_header_injection_is_rejected() -> None:
    with pytest.raises(DeliveryPolicyError, match="CR, LF, or NUL"):
        create_audited_message(_policy(), ["alice"], "Hello\r\nBcc: evil@example.net", "Body")


def test_header_like_body_text_remains_body_text() -> None:
    audited = create_audited_message(
        _policy(),
        ["alice"],
        "Hello",
        "First line\nBcc: evil@example.net\nLast line",
    )
    parsed = BytesParser(policy=policy.default).parsebytes(
        base64.urlsafe_b64decode(audited.raw_base64url)
    )

    assert parsed["Bcc"] is None
    assert "Bcc: evil@example.net" in parsed.get_content()


def test_final_audit_rejects_added_bcc_header() -> None:
    runtime_policy = _policy()
    selection = resolve_recipients(runtime_policy.allowlist, ["alice"])
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = "sender@example.com"
    message["To"] = "alice@example.com"
    message["Bcc"] = "evil@example.net"
    message["Subject"] = "Hello"
    message.set_content("Body")

    with pytest.raises(DeliveryPolicyError, match="unexpected headers"):
        audit_serialized_message(
            message.as_bytes(),
            sender=runtime_policy.sender,
            selection=selection,
        )
