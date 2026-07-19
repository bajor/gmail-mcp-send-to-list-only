from __future__ import annotations

from typing import Any

import anyio

from gmail_mcp_send_to_list_only.config import load_runtime_policy
from gmail_mcp_send_to_list_only.delivery import AuditedMessage
from gmail_mcp_send_to_list_only.gmail_client import SendResult
from gmail_mcp_send_to_list_only.server import create_server


def _policy():
    return load_runtime_policy(
        {
            "GMAIL_SENDER_EMAIL": "sender@example.com",
            "GMAIL_ALLOSWED_RECIPENTS": "alice@example.com,bob@example.com",
        }
    )


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[AuditedMessage] = []

    def send(self, message: AuditedMessage) -> SendResult:
        self.messages.append(message)
        return SendResult(
            "message-1",
            "thread-1",
            message.recipient_ids,
            message.recipient_addresses,
        )


def test_server_exposes_only_the_two_audited_tools() -> None:
    server = create_server(_policy(), FakeSender)
    tools = anyio.run(server.list_tools)
    by_name = {tool.name: tool for tool in tools}

    assert set(by_name) == {"gmail_list_allowed_recipients", "gmail_send_email"}
    send_tool = by_name["gmail_send_email"]
    assert set(send_tool.inputSchema["properties"]) == {"recipient_ids", "subject", "body_text"}
    assert send_tool.annotations is not None
    assert send_tool.annotations.readOnlyHint is False
    assert send_tool.annotations.destructiveHint is True
    assert send_tool.annotations.idempotentHint is False
    assert send_tool.annotations.openWorldHint is True


def test_server_lists_configured_recipients() -> None:
    server = create_server(_policy(), FakeSender)

    _, structured_result = anyio.run(
        server.call_tool,
        "gmail_list_allowed_recipients",
        {},
    )

    assert structured_result == {
        "result": [
            {"id": "recipient_1", "address": "alice@example.com"},
            {"id": "recipient_2", "address": "bob@example.com"},
        ]
    }


def test_server_audits_before_using_sender() -> None:
    sender = FakeSender()
    server = create_server(_policy(), lambda: sender)
    arguments: dict[str, Any] = {
        "recipient_ids": ["recipient_2"],
        "subject": "Hello",
        "body_text": "Plain body",
    }

    _, structured_result = anyio.run(server.call_tool, "gmail_send_email", arguments)

    assert structured_result["gmail_message_id"] == "message-1"
    assert len(sender.messages) == 1
    assert sender.messages[0].recipient_addresses == ("bob@example.com",)
