from __future__ import annotations

import ast
from pathlib import Path

from gmail_mcp_send_to_list_only.auth import SCOPES

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
FORBIDDEN_SCOPES = (
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
)
FORBIDDEN_GMAIL_METHODS = {
    "list",
    "get",
    "modify",
    "trash",
    "delete",
    "insert",
    "import_",
    "create",
    "update",
    "sendAs",
}


def _attribute_chain(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Attribute):
        return [*_attribute_chain(node.value), node.attr]
    if isinstance(node, ast.Call):
        return _attribute_chain(node.func)
    if isinstance(node, ast.Name):
        return [node.id]
    return []


def test_source_has_one_send_call_and_no_other_gmail_methods() -> None:
    send_calls: list[str] = []
    forbidden_calls: list[str] = []
    for source_file in sorted(SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            chain = _attribute_chain(node.func)
            if "users" not in chain:
                continue
            if chain[-1] == "send":
                send_calls.append(f"{source_file.name}:{node.lineno}")
            if chain[-1] in FORBIDDEN_GMAIL_METHODS:
                forbidden_calls.append(f"{source_file.name}:{node.lineno}:{chain[-1]}")
    assert len(send_calls) == 1
    assert send_calls[0].startswith("gmail_client.py:")
    assert forbidden_calls == []


def test_source_has_only_the_send_scope_and_stdio_transport() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(SOURCE_ROOT.rglob("*.py"))
    )

    assert SCOPES == ("https://www.googleapis.com/auth/gmail.send",)
    assert all(forbidden_scope not in source for forbidden_scope in FORBIDDEN_SCOPES)
    assert 'run(transport="stdio")' in source
    assert 'run(transport="streamable-http")' not in source
    assert 'run(transport="sse")' not in source
