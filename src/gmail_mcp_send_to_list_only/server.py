"""Local STDIO MCP server with exactly two recipient-locked tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .config import RuntimePolicy, load_runtime_policy
from .delivery import AuditedMessage, create_audited_message
from .gmail_client import SendResult, build_gmail_client

SERVER_INSTRUCTIONS = (
    "This server sends plain-text Gmail messages only to recipients in the immutable "
    "startup allowlist. Callers select recipient IDs, never addresses. Selected recipients "
    "are visible together in To. There is no Cc, Bcc, HTML, attachment, draft, reply, raw "
    "header, raw MIME, or generic Gmail API tool. Sending is external and non-idempotent."
)

LIST_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
SEND_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)


class GmailSender(Protocol):
    def send(self, message: AuditedMessage) -> SendResult: ...


SenderFactory = Callable[[], GmailSender]


def create_server(
    policy: RuntimePolicy | None = None,
    sender_factory: SenderFactory = build_gmail_client,
) -> FastMCP:
    """Create the server after loading the delivery policy once."""

    active_policy = policy or load_runtime_policy()
    server = FastMCP("gmail-send-to-list-only", instructions=SERVER_INSTRUCTIONS)

    @server.tool(annotations=LIST_ANNOTATIONS)
    def gmail_list_allowed_recipients() -> list[dict[str, str]]:
        """List the only recipient IDs and addresses that this process can use."""

        return [
            {
                "id": recipient.recipient_id.value,
                "address": recipient.address.value,
            }
            for recipient in active_policy.allowlist.recipients
        ]

    @server.tool(annotations=SEND_ANNOTATIONS)
    def gmail_send_email(
        recipient_ids: list[str],
        subject: str,
        body_text: str,
    ) -> dict[str, str | list[str]]:
        """Send one plain-text email to a non-empty allowed subset in visible To."""

        audited_message = create_audited_message(
            active_policy,
            recipient_ids,
            subject,
            body_text,
        )
        return sender_factory().send(audited_message).to_dict()

    return server


def run_server() -> None:
    """Run only over local standard input/output."""

    create_server().run(transport="stdio")
