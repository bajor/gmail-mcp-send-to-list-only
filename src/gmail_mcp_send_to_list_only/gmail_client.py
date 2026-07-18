"""Narrow Gmail client exposing only one non-retrying send operation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from google.auth.exceptions import GoogleAuthError
from googleapiclient.discovery import Resource, build  # type: ignore[import-untyped]
from googleapiclient.errors import HttpError  # type: ignore[import-untyped]

from .auth import AuthenticationError, load_credentials
from .config import AuthConfig
from .delivery import AuditedMessage

GMAIL_API_NAME = "gmail"
GMAIL_API_VERSION = "v1"
GMAIL_USER_ID = "me"


class GmailSendError(RuntimeError):
    """Sanitized Gmail API or transport error."""


@dataclass(frozen=True, slots=True)
class SendResult:
    gmail_message_id: str
    gmail_thread_id: str
    recipient_ids: tuple[str, ...]
    recipient_addresses: tuple[str, ...]

    def to_dict(self) -> dict[str, str | list[str]]:
        return {
            "gmail_message_id": self.gmail_message_id,
            "gmail_thread_id": self.gmail_thread_id,
            "recipient_ids": list(self.recipient_ids),
            "recipient_addresses": list(self.recipient_addresses),
        }


def _http_status(error: HttpError) -> int | None:
    status = getattr(error.resp, "status", None)
    return status if isinstance(status, int) else None


def _sanitized_send_error(error: Exception) -> GmailSendError:
    if isinstance(error, HttpError):
        status = _http_status(error)
        suffix = f" with HTTP status {status}" if status is not None else ""
        return GmailSendError(f"Gmail send failed{suffix}; delivery status may be unknown.")
    if isinstance(error, GoogleAuthError):
        return GmailSendError("Gmail send failed because OAuth credentials are invalid.")
    return GmailSendError("Gmail send failed; delivery status may be unknown.")


class GmailClient:
    """Synchronous sender that accepts audited messages, never raw MIME."""

    def __init__(self, service: Resource) -> None:
        self._service = service

    def send(self, message: AuditedMessage) -> SendResult:
        """Send once with Google client retries explicitly disabled."""

        try:
            request = self._service.users().messages().send(
                userId=GMAIL_USER_ID,
                body={"raw": message.raw_base64url},
            )
            response = request.execute(num_retries=0)
        except Exception as error:
            raise _sanitized_send_error(error) from None
        if not isinstance(response, dict):
            raise GmailSendError("Gmail send returned an invalid response.")
        message_id = response.get("id")
        thread_id = response.get("threadId")
        if not isinstance(message_id, str) or not isinstance(thread_id, str):
            raise GmailSendError("Gmail send returned an invalid response.")
        return SendResult(
            gmail_message_id=message_id,
            gmail_thread_id=thread_id,
            recipient_ids=message.recipient_ids,
            recipient_addresses=message.recipient_addresses,
        )


def build_gmail_client(config: AuthConfig | None = None) -> GmailClient:
    """Build an authenticated Gmail v1 client from local credentials."""

    try:
        service = cast(
            Resource,
            build(
                GMAIL_API_NAME,
                GMAIL_API_VERSION,
                credentials=load_credentials(config),
                cache_discovery=False,
            ),
        )
    except AuthenticationError:
        raise
    except Exception:
        raise GmailSendError("The Gmail API client could not be built.") from None
    return GmailClient(service)
