# Changelog

All notable changes to this project are documented in this file.

## 0.1.2 - 2026-07-19

- Add a dedicated Linux VPS/headless deployment guide with SSH-tunneled OAuth authorization.
- Document persistent `token.json` storage, automatic refresh behavior, and VPS environment setup.
- Link the VPS deployment guide prominently from the README.

## 0.1.1 - 2026-07-19

- Replace the JSON recipient allowlist with comma-separated `GMAIL_ALLOSWED_RECIPENTS` addresses.
- Generate `recipient_N` IDs from the configured address order while keeping raw addresses out of MCP send input.

## 0.1.0 - 2026-07-18

- Add a fail-closed startup allowlist addressed only through stable recipient IDs.
- Add exact-scope Gmail Desktop OAuth with atomic `0600` token storage.
- Add plain-text MIME construction followed by an independent serialized-message audit.
- Add a Gmail client that accepts only audited messages and disables automatic retries.
- Add exactly two STDIO MCP tools: list allowed recipients and send to selected IDs.
- Add unit, component, offline STDIO end-to-end, type, lint, and static safety checks.
- Document setup, the application-level guarantee, and the trusted-system boundary.
