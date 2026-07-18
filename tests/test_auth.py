from __future__ import annotations

import json
import stat
from pathlib import Path
from unittest.mock import Mock

import pytest

from gmail_mcp_send_to_list_only.auth import (
    SCOPES,
    AuthenticationError,
    load_credentials,
    logout_local,
    save_credentials,
)
from gmail_mcp_send_to_list_only.config import AuthConfig, load_auth_config


def _credentials(*, scopes: tuple[str, ...] = SCOPES) -> Mock:
    credentials = Mock()
    credentials.scopes = scopes
    credentials.granted_scopes = scopes
    credentials.has_scopes.return_value = set(scopes) == set(SCOPES)
    credentials.to_json.return_value = json.dumps({"scopes": list(scopes), "token": "fake"})
    return credentials


def test_scope_is_exactly_gmail_send() -> None:
    assert SCOPES == ("https://www.googleapis.com/auth/gmail.send",)


def test_save_credentials_uses_private_permissions(tmp_path: Path) -> None:
    token_file = tmp_path / "private" / "token.json"

    save_credentials(_credentials(), token_file)

    assert stat.S_IMODE(token_file.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600


def test_save_credentials_rejects_broader_scopes(tmp_path: Path) -> None:
    broader = (*SCOPES, "https://www.googleapis.com/auth/gmail.readonly")

    with pytest.raises(AuthenticationError, match="only the Gmail send scope"):
        save_credentials(_credentials(scopes=broader), tmp_path / "token.json")


def test_load_credentials_rejects_broader_token_before_parsing(tmp_path: Path) -> None:
    token_file = tmp_path / "token.json"
    token_file.write_text(
        json.dumps({"scopes": [*SCOPES, "https://mail.google.com/"]}),
        encoding="utf-8",
    )

    with pytest.raises(AuthenticationError, match="only the Gmail send scope"):
        load_credentials(AuthConfig(None, token_file))


def test_logout_removes_only_the_configured_token(tmp_path: Path) -> None:
    token_file = tmp_path / "token.json"
    token_file.write_text("fake", encoding="utf-8")

    assert logout_local(AuthConfig(None, token_file)) is True
    assert token_file.exists() is False
    assert logout_local(AuthConfig(None, token_file)) is False


def test_auth_config_expands_paths(tmp_path: Path) -> None:
    config = load_auth_config(
        {
            "GMAIL_CLIENT_SECRET_FILE": str(tmp_path / "client.json"),
            "GMAIL_TOKEN_FILE": str(tmp_path / "token.json"),
        }
    )

    assert config.client_secret_file == (tmp_path / "client.json").resolve()
    assert config.token_file == (tmp_path / "token.json").resolve()
