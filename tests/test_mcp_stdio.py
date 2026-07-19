from __future__ import annotations

import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

E2E_SERVER = Path(__file__).with_name("e2e_server.py")


def test_stdio_mcp_discovery_rejection_and_send() -> None:
    anyio.run(_exercise_stdio_server)


async def _exercise_stdio_server() -> None:
    environment = dict(os.environ)
    environment.update(
        {
            "GMAIL_SENDER_EMAIL": "sender@example.com",
            "GMAIL_ALLOSWED_RECIPENTS": "alice@example.com",
        }
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(E2E_SERVER)],
        env=environment,
    )
    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        assert [tool.name for tool in tools.tools] == [
            "gmail_list_allowed_recipients",
            "gmail_send_email",
        ]

        listed = await session.call_tool("gmail_list_allowed_recipients", {})
        assert listed.isError is False
        assert listed.structuredContent == {
            "result": [{"id": "recipient_1", "address": "alice@example.com"}]
        }

        rejected = await session.call_tool(
            "gmail_send_email",
            {"recipient_ids": ["evil"], "subject": "No", "body_text": "No"},
        )
        assert rejected.isError is True

        sent = await session.call_tool(
            "gmail_send_email",
            {"recipient_ids": ["recipient_1"], "subject": "Hello", "body_text": "Body"},
        )
        assert sent.isError is False
        assert sent.structuredContent == {
            "gmail_message_id": "e2e-message",
            "gmail_thread_id": "e2e-thread",
            "recipient_ids": ["recipient_1"],
            "recipient_addresses": ["alice@example.com"],
        }
