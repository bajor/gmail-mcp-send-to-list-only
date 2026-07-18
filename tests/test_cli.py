from __future__ import annotations

from pathlib import Path

from gmail_mcp_send_to_list_only.cli import main


def test_doctor_reports_missing_runtime_policy(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GMAIL_SENDER_EMAIL", raising=False)
    monkeypatch.delenv("GMAIL_ALLOWED_RECIPIENTS_JSON", raising=False)
    monkeypatch.setenv("GMAIL_TOKEN_FILE", str(tmp_path / "token.json"))

    assert main(["doctor"]) == 1
    output = capsys.readouterr().out
    assert "[PASS] OAuth scope: exactly Gmail send" in output
    assert "[FAIL] Recipient policy:" in output
