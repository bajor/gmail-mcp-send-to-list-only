"""Secure local OAuth handling with the exact Gmail send scope."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

from .config import AuthConfig, ConfigurationError, load_auth_config

SCOPES = ("https://www.googleapis.com/auth/gmail.send",)
TOKEN_DIRECTORY_MODE = 0o700
TOKEN_FILE_MODE = 0o600


class AuthenticationError(RuntimeError):
    """OAuth failure with a secret-free user-facing message."""


def _normalize_scopes(raw_scopes: object) -> tuple[str, ...] | None:
    if raw_scopes is None:
        return None
    if isinstance(raw_scopes, str):
        return tuple(raw_scopes.split())
    if isinstance(raw_scopes, (list, tuple)) and all(
        isinstance(scope, str) for scope in raw_scopes
    ):
        return tuple(raw_scopes)
    raise AuthenticationError("The local OAuth token has an invalid scope declaration.")


def _require_exact_scopes(raw_scopes: object, *, allow_missing: bool = False) -> None:
    scopes = _normalize_scopes(raw_scopes)
    if scopes is None and allow_missing:
        return
    if scopes is None or len(scopes) != len(SCOPES) or set(scopes) != set(SCOPES):
        raise AuthenticationError(
            "The local OAuth token must use only the Gmail send scope. "
            "Run logout-local, then auth, to create a replacement token."
        )


def _read_token_info(token_file: Path) -> dict[str, Any]:
    if not token_file.is_file():
        raise AuthenticationError("No local Gmail token was found. Run auth first.")
    try:
        token_info = json.loads(token_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise AuthenticationError("The local Gmail token cannot be read safely.") from None
    if not isinstance(token_info, dict):
        raise AuthenticationError("The local Gmail token has an invalid format.")
    _require_exact_scopes(token_info.get("scopes"))
    return token_info


def _validate_credentials(credentials: Credentials) -> None:
    _require_exact_scopes(credentials.scopes)
    _require_exact_scopes(credentials.granted_scopes, allow_missing=True)
    if not credentials.has_scopes(SCOPES):  # type: ignore[no-untyped-call]
        raise AuthenticationError("The OAuth token is missing the Gmail send scope.")


def save_credentials(credentials: Credentials, token_file: Path) -> None:
    """Atomically persist exact-scope credentials with mode 0600."""

    _validate_credentials(credentials)
    temporary_path: Path | None = None
    try:
        token_file.parent.mkdir(parents=True, mode=TOKEN_DIRECTORY_MODE, exist_ok=True)
        if not token_file.parent.is_dir():
            raise AuthenticationError("The Gmail token directory is not a directory.")
        token_file.parent.chmod(TOKEN_DIRECTORY_MODE)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=token_file.parent,
            prefix=".token-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            os.chmod(temporary_path, TOKEN_FILE_MODE)
            temporary_file.write(credentials.to_json())  # type: ignore[no-untyped-call]
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, token_file)
        token_file.chmod(TOKEN_FILE_MODE)
    except AuthenticationError:
        raise
    except Exception:
        raise AuthenticationError("The Gmail OAuth token could not be saved securely.") from None
    finally:
        if temporary_path is not None and temporary_path.exists():
            with suppress(OSError):
                temporary_path.unlink()


def authorize(config: AuthConfig | None = None) -> Credentials:
    """Run Google's Desktop OAuth flow with only the Gmail send scope."""

    active_config = config or load_auth_config()
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(active_config.require_client_secret_file()),
            SCOPES,
        )
        credentials = cast(Credentials, flow.run_local_server(port=0))
        _validate_credentials(credentials)
        save_credentials(credentials, active_config.token_file)
        return credentials
    except (AuthenticationError, ConfigurationError):
        raise
    except Exception:
        raise AuthenticationError("Gmail OAuth authorization failed.") from None


def load_credentials(config: AuthConfig | None = None) -> Credentials:
    """Load and refresh an existing exact-scope token."""

    active_config = config or load_auth_config()
    try:
        credentials = cast(
            Credentials,
            Credentials.from_authorized_user_info(
                _read_token_info(active_config.token_file),
                scopes=SCOPES,
            ),  # type: ignore[no-untyped-call]
        )
        _validate_credentials(credentials)
        if credentials.expired:
            if not credentials.refresh_token:
                raise AuthenticationError("The Gmail token is expired. Run auth again.")
            credentials.refresh(Request())  # type: ignore[no-untyped-call]
            _validate_credentials(credentials)
            save_credentials(credentials, active_config.token_file)
        if not credentials.valid:
            raise AuthenticationError("The Gmail token is invalid. Run auth again.")
        return credentials
    except AuthenticationError:
        raise
    except GoogleAuthError:
        raise AuthenticationError("The Gmail token could not be refreshed.") from None
    except Exception:
        raise AuthenticationError("The local Gmail token is invalid.") from None


def token_file_mode(token_file: Path) -> int | None:
    try:
        return stat.S_IMODE(token_file.stat().st_mode)
    except OSError:
        return None


def validate_saved_token(config: AuthConfig | None = None) -> None:
    """Validate the saved token format and exact scopes without refreshing it."""

    _read_token_info((config or load_auth_config()).token_file)


def logout_local(config: AuthConfig | None = None) -> bool:
    """Delete only the configured local OAuth token."""

    token_file = (config or load_auth_config()).token_file
    if not token_file.exists():
        return False
    if not token_file.is_file():
        raise AuthenticationError("The Gmail token path is not a regular file.")
    try:
        token_file.unlink()
    except OSError:
        raise AuthenticationError("The local Gmail token could not be removed.") from None
    return True
