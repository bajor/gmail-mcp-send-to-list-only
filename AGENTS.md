# Repository guidelines

- Keep the Gmail OAuth scope exactly `https://www.googleapis.com/auth/gmail.send`.
- Keep `users.messages.send` as the only Gmail API operation.
- Never accept raw email addresses, `Cc`, `Bcc`, custom headers, or raw MIME through MCP.
- Resolve recipient IDs from the startup allowlist and audit serialized MIME before sending.
- Keep the MCP transport local STDIO only; do not add HTTP, a GUI, a database, or telemetry.
- Run `make test` after every code change.
- Never commit real email addresses, email bodies, OAuth tokens, client-secret files, or credentials.
