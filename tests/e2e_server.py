"""Test-only STDIO server using the production MCP surface and a fake Gmail sender."""

from gmail_mcp_send_to_list_only.config import load_runtime_policy
from gmail_mcp_send_to_list_only.delivery import AuditedMessage
from gmail_mcp_send_to_list_only.gmail_client import SendResult
from gmail_mcp_send_to_list_only.server import create_server


class FakeSender:
    def send(self, message: AuditedMessage) -> SendResult:
        return SendResult(
            "e2e-message",
            "e2e-thread",
            message.recipient_ids,
            message.recipient_addresses,
        )


if __name__ == "__main__":
    create_server(load_runtime_policy(), FakeSender).run(transport="stdio")
