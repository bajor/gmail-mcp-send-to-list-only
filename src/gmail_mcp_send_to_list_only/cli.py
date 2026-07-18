"""Command-line setup and diagnostic interface."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from .auth import (
    SCOPES,
    AuthenticationError,
    authorize,
    logout_local,
    token_file_mode,
    validate_saved_token,
)
from .config import ConfigurationError, load_auth_config, load_runtime_policy
from .server import run_server


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gmail-mcp-send-to-list-only",
        description="Recipient-locked Gmail MCP setup commands.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("auth", help="Run the Google OAuth Desktop flow.")
    commands.add_parser("doctor", help="Check local policy and OAuth configuration.")
    commands.add_parser("logout-local", help="Delete only the local OAuth token.")
    commands.add_parser("mcp", help="Run the local STDIO MCP server.")
    return parser


def _doctor_checks() -> list[DoctorCheck]:
    checks = [
        DoctorCheck(
            "Python",
            "PASS" if sys.version_info >= (3, 11) else "FAIL",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ),
        DoctorCheck(
            "OAuth scope",
            "PASS" if SCOPES == ("https://www.googleapis.com/auth/gmail.send",) else "FAIL",
            "exactly Gmail send",
        ),
    ]
    try:
        policy = load_runtime_policy()
        checks.append(
            DoctorCheck(
                "Recipient policy",
                "PASS",
                f"sender configured; {len(policy.allowlist.recipients)} recipients",
            )
        )
    except ConfigurationError as error:
        checks.append(DoctorCheck("Recipient policy", "FAIL", str(error)))

    auth_config = load_auth_config()
    secret_exists = bool(
        auth_config.client_secret_file and auth_config.client_secret_file.is_file()
    )
    checks.append(
        DoctorCheck(
            "Client secret",
            "PASS" if secret_exists else "WARN",
            "configured file exists" if secret_exists else "configure the client secret path",
        )
    )
    mode = token_file_mode(auth_config.token_file)
    checks.append(
        DoctorCheck(
            "Token permissions",
            "PASS" if mode == 0o600 else ("WARN" if mode is None else "FAIL"),
            "0600" if mode == 0o600 else ("token not present" if mode is None else oct(mode)),
        )
    )
    if mode is None:
        checks.append(DoctorCheck("Token scope", "WARN", "token not present"))
    else:
        try:
            validate_saved_token(auth_config)
            checks.append(DoctorCheck("Token scope", "PASS", "exactly Gmail send"))
        except AuthenticationError as error:
            checks.append(DoctorCheck("Token scope", "FAIL", str(error)))
    return checks


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "auth":
            authorize()
            print("OAuth authorization completed; the local token was saved with mode 0600.")
            return 0
        if args.command == "doctor":
            checks = _doctor_checks()
            for check in checks:
                print(f"[{check.status}] {check.name}: {check.detail}")
            return 1 if any(check.status == "FAIL" for check in checks) else 0
        if args.command == "logout-local":
            print("Local OAuth token removed." if logout_local() else "No local token was present.")
            return 0
        if args.command == "mcp":
            run_server()
            return 0
    except (AuthenticationError, ConfigurationError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return 2
