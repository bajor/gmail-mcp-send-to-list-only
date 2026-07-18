from __future__ import annotations

from typing import cast
from unittest.mock import Mock

import pytest
from googleapiclient.discovery import Resource  # type: ignore[import-untyped]

from gmail_mcp_send_to_list_only.delivery import AuditedMessage
from gmail_mcp_send_to_list_only.gmail_client import GmailClient, GmailSendError

DEFAULT_RESPONSE = object()


def _message() -> AuditedMessage:
    return AuditedMessage("encoded", ("alice",), ("alice@example.com",))


def _client(
    response: object = DEFAULT_RESPONSE,
    error: Exception | None = None,
) -> tuple[GmailClient, Mock, Mock]:
    request = Mock()
    if error is not None:
        request.execute.side_effect = error
    else:
        request.execute.return_value = (
            {"id": "message-1", "threadId": "thread-1"}
            if response is DEFAULT_RESPONSE
            else response
        )
    service = Mock()
    service.users.return_value.messages.return_value.send.return_value = request
    return GmailClient(cast(Resource, service)), service, request


def test_send_uses_one_non_retrying_gmail_request() -> None:
    client, service, request = _client()

    result = client.send(_message())

    service.users.return_value.messages.return_value.send.assert_called_once_with(
        userId="me",
        body={"raw": "encoded"},
    )
    request.execute.assert_called_once_with(num_retries=0)
    assert result.to_dict() == {
        "gmail_message_id": "message-1",
        "gmail_thread_id": "thread-1",
        "recipient_ids": ["alice"],
        "recipient_addresses": ["alice@example.com"],
    }


def test_send_does_not_retry_or_expose_transport_details() -> None:
    client, _, request = _client(error=TimeoutError("private transport detail"))

    with pytest.raises(GmailSendError, match="delivery status may be unknown") as caught:
        client.send(_message())

    assert "private transport detail" not in str(caught.value)
    request.execute.assert_called_once_with(num_retries=0)


@pytest.mark.parametrize("response", [None, {}, {"id": "message-1"}, {"threadId": "thread-1"}])
def test_send_rejects_invalid_gmail_responses(response: object) -> None:
    client, _, _ = _client(response=response)

    with pytest.raises(GmailSendError, match="invalid response"):
        client.send(_message())
