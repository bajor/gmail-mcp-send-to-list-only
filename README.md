# gmail-mcp-send-to-list-only

A local Python [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that
sends plain-text Gmail messages only to a fixed startup allowlist.

The MCP caller selects generated recipient IDs such as `recipient_1`; it never supplies email
addresses. The server rejects an empty selection, duplicate IDs, unknown IDs, extra headers,
and any serialized message whose `From` or `To` addresses differ from the startup policy.

## Linux VPS / headless deployment

> [!IMPORTANT]
> **Running this on a Linux VPS or other headless server over SSH?**
> Follow the **[Linux VPS deployment and OAuth guide](docs/linux-vps-setup.md)** before running
> `auth`. It covers SSH-tunneled OAuth, persistent `token.json` storage, automatic token refresh,
> persistent environment configuration, and VPS-specific troubleshooting.

The default Desktop OAuth flow starts a localhost callback and attempts to open a browser. On a
headless VPS, use the dedicated guide so the callback is carried through an SSH tunnel and the
resulting token is stored directly on the server.

## Security guarantee and boundary

For an unchanged process started from trusted code and trusted configuration, every Gmail API
send request produced by this server has exactly these properties:

- every direct recipient is an address in `GMAIL_ALLOSWED_RECIPENTS`;
- the caller cannot provide an address, `Cc`, `Bcc`, sender, header, or raw MIME value;
- the MIME message has one `From`, one visible `To`, one `Subject`, and one plain-text body;
- the final serialized MIME is parsed and audited before it can reach the Gmail client;
- the only Gmail OAuth scope is `https://www.googleapis.com/auth/gmail.send`;
- the only Gmail API operation is one non-retrying `users.messages.send` call; and
- the MCP server uses local standard input/output (STDIO), not a network listener.

This is an application-level recipient lock, not a recipient-scoped Google permission. Google
does not provide an OAuth scope that restricts sending to particular addresses. The
`gmail.send` token can send to arbitrary addresses if it is stolen or used by different code.

| Inside the guarantee | Outside the guarantee |
| --- | --- |
| Untrusted MCP tool arguments and model-generated content | An attacker who can modify the code, Python environment, process environment, or process memory |
| Header injection attempts through subject or body inputs | Direct use or theft of the OAuth token or OAuth client secret |
| Unknown, duplicate, or empty recipient-ID selections | Forwarding, aliases, or group expansion performed after delivery to an allowed address |
| Attempts to add `Cc`, `Bcc`, HTML, attachments, or arbitrary MIME through MCP | Compromise of Gmail, Google Cloud, the host, or an allowed recipient mailbox |

If the ultimate human recipients must also be constrained, allow only direct mailboxes that
you control. Do not allow mailing lists, groups, aliases, or addresses with forwarding rules.
Enforce the same restriction independently in Google Workspace routing or another outbound
mail gateway when a host or token compromise is in scope.

All recipients selected for one message appear together in `To` and can see one another. Send
separate messages when recipients must not be disclosed to each other.

## Deliberately unsupported

The server has no raw-address input, `Cc`, `Bcc`, HTML, attachments, custom headers, drafts,
replies, mailbox reads, generic Gmail API calls, HTTP transport, GUI, database, telemetry,
preview workflow, or automatic send retry.

Sending is immediate, external, and non-idempotent. A timeout or transport error can leave
delivery status unknown. Do not resend automatically after an ambiguous failure; inspect the
Gmail Sent folder manually first.

## Requirements

- Python 3.11 or newer;
- one Google account with Gmail enabled;
- one Google Cloud project with the Gmail API enabled;
- a Desktop OAuth client for that project; and
- local filesystem permissions that protect the OAuth files and MCP client configuration.

The project runs on Linux and macOS. The commands below use a POSIX shell.

## 1. Install

Clone the repository and create an isolated virtual environment:

```bash
git clone https://github.com/bajor/gmail-mcp-send-to-list-only.git
cd gmail-mcp-send-to-list-only
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

Do not install into the system Python or use `--break-system-packages`.

## 2. Create the Google OAuth client

Follow Google's current [Gmail Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)
for the Google Cloud console steps, with these project-specific constraints:

1. Create or select one Google Cloud project.
2. Enable only the Gmail API needed by this project.
3. Configure the Google Auth platform. For a personal Gmail account, choose an External
   audience and add the one Gmail account under test users while the app is in Testing. For a
   Google Workspace account, the administrator can choose Internal when appropriate.
4. Under Data Access, add exactly the sensitive
   [`gmail.send` scope](https://developers.google.com/workspace/gmail/api/auth/scopes):
   `https://www.googleapis.com/auth/gmail.send`.
5. Create an OAuth client with application type **Desktop app**.
6. Download the client JSON outside the repository, for example to
   `~/.config/gmail-mcp-send-to-list-only/client_secret.json`.
7. Restrict the local files:

```bash
mkdir -p ~/.config/gmail-mcp-send-to-list-only
chmod 700 ~/.config/gmail-mcp-send-to-list-only
chmod 600 ~/.config/gmail-mcp-send-to-list-only/client_secret.json
```

Never commit the downloaded client JSON. The repository ignores common client-secret and token
filenames, but filesystem permissions and operator discipline remain required.

## 3. Configure the immutable startup policy

The server reads configuration from the process environment inherited from the MCP client. It does
not load a repository `.env` file, and normal setup should not duplicate these values inside each
MCP client's server definition. Export the variables once in the shell, service manager, or wrapper
that starts Claude Code, Codex, OpenCode, or another local STDIO MCP launcher.

Set these variables before starting the MCP client:

```bash
export GMAIL_CLIENT_SECRET_FILE=/home/USERNAME/.config/gmail-mcp-send-to-list-only/client_secret.json
export GMAIL_TOKEN_FILE=/home/USERNAME/.config/gmail-mcp-send-to-list-only/token.json
export GMAIL_SENDER_EMAIL=sender@example.com
export GMAIL_ALLOSWED_RECIPENTS=alice@example.com,bob@example.com
```

Replace every example value locally. `GMAIL_SENDER_EMAIL` must be the Gmail address used during
authorization. `GMAIL_ALLOSWED_RECIPENTS` must be a non-empty comma-separated list of the only
permitted direct email addresses.

Recipient IDs are generated at startup as `recipient_1`, `recipient_2`, and so on in the same
order as the comma-separated addresses. Reordering the list changes which address each generated
ID resolves to. Addresses must be unique ASCII addr-spec values without display names. Spaces
around commas are ignored.

The process loads and validates the complete policy once at startup. Changing the parent shell or
client configuration has no effect on a running MCP server. Restart the MCP client after any
intentional allowlist change. An invalid or empty policy prevents the server from starting.

## 4. Authorize the one Gmail account

> [!NOTE]
> On a Linux VPS or other headless host, use the
> **[Linux VPS deployment and OAuth guide](docs/linux-vps-setup.md)**. It shows how to complete the
> localhost OAuth callback through an SSH tunnel and keep the resulting token on the VPS.

Run the local Desktop OAuth flow:

```bash
.venv/bin/gmail-mcp-send-to-list-only auth
```

Sign in only to the account named by `GMAIL_SENDER_EMAIL`. The command requests exactly
`gmail.send`, opens a local callback on an ephemeral port, and atomically stores the token with
mode `0600` in a directory with mode `0700`.

Run the diagnostic command:

```bash
.venv/bin/gmail-mcp-send-to-list-only doctor
```

Expected results are `PASS` for Python, OAuth scope, recipient policy, client secret, token
permissions, and token scope. `WARN` means a setup artifact is not present yet. `FAIL` produces
a non-zero exit status and must be fixed before use.

To remove only the configured local token:

```bash
.venv/bin/gmail-mcp-send-to-list-only logout-local
```

This does not revoke access at Google. Revoke the app separately in the Google account security
settings when the token may have been exposed.

## 5. Connect an MCP client

Use a local STDIO MCP configuration that starts this repository's Python entry point. Keep the
`GMAIL_*` values in the parent process environment, not repeated as per-client config values. If a
client requires an explicit forwarding allowlist, list only the variable names. Keep approval
prompts enabled for `gmail_send_email`; sending is external and non-idempotent.

You can also start the server manually from a shell that already exports the variables:

```bash
.venv/bin/gmail-mcp-send-to-list-only mcp
```

Do not type into that process: standard output carries the MCP protocol.

### Claude Code

Claude Code supports local STDIO servers in user, project, or local scope. Replace both absolute
repository paths below, and start Claude Code from an environment where the four `GMAIL_*`
variables are already set:

```bash
claude mcp add-json --scope user gmail-send-to-list-only '{
  "type": "stdio",
  "command": "/ABSOLUTE/PATH/gmail-mcp-send-to-list-only/.venv/bin/python",
  "args": ["-m", "gmail_mcp_send_to_list_only", "mcp"],
  "cwd": "/ABSOLUTE/PATH/gmail-mcp-send-to-list-only"
}'
```

Restart Claude Code after editing MCP configuration or changing the exported variables.

### Codex

Codex supports local STDIO servers in `~/.codex/config.toml` or a trusted project's
`.codex/config.toml`. Replace both absolute repository paths below. The `env_vars` line forwards
values that were exported before Codex started; it does not store the values in `config.toml`.

```toml
[mcp_servers.gmail-send-to-list-only]
command = "/ABSOLUTE/PATH/gmail-mcp-send-to-list-only/.venv/bin/python"
args = ["-m", "gmail_mcp_send_to_list_only", "mcp"]
cwd = "/ABSOLUTE/PATH/gmail-mcp-send-to-list-only"
env_vars = ["GMAIL_CLIENT_SECRET_FILE", "GMAIL_TOKEN_FILE", "GMAIL_SENDER_EMAIL", "GMAIL_ALLOSWED_RECIPENTS"]
enabled = true
required = true
startup_timeout_sec = 20
tool_timeout_sec = 120
enabled_tools = ["gmail_list_allowed_recipients", "gmail_send_email"]
default_tools_approval_mode = "writes"
```

`writes` asks for approval before the send tool because the server marks it as non-read-only;
the list tool remains read-only. Keep approval prompts enabled. Restart Codex after editing its
configuration or changing the exported variables. See the current
[Codex MCP configuration reference](https://learn.chatgpt.com/docs/extend/mcp.md) for
client-specific setup details.

### OpenCode

OpenCode supports local MCP servers in `opencode.json`, `opencode.jsonc`, or the global
`~/.config/opencode/opencode.jsonc`. Replace both absolute repository paths below, and start
OpenCode from an environment where the four `GMAIL_*` variables are already set:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "gmail-send-to-list-only": {
      "type": "local",
      "command": [
        "/ABSOLUTE/PATH/gmail-mcp-send-to-list-only/.venv/bin/python",
        "-m",
        "gmail_mcp_send_to_list_only",
        "mcp"
      ],
      "cwd": "/ABSOLUTE/PATH/gmail-mcp-send-to-list-only",
      "enabled": true,
      "timeout": 120000
    }
  }
}
```

Restart OpenCode after editing its configuration or changing the exported variables.

## MCP tools

### `gmail_list_allowed_recipients`

Input: none.

Output: the startup policy's recipient IDs and addresses. Listing is read-only and
idempotent.

### `gmail_send_email`

Input:

```json
{
  "recipient_ids": ["recipient_1"],
  "subject": "Example subject",
  "body_text": "Example plain-text body."
}
```

- `recipient_ids` must be a non-empty, duplicate-free subset of configured IDs.
- `subject` must not contain carriage return, line feed, or NUL characters.
- `body_text` is encoded as UTF-8 plain text.
- there is no address field and no optional delivery-header field.

Success returns the Gmail message ID, Gmail thread ID, selected recipient IDs, and resolved
recipient addresses. Failure is returned before Gmail is called when policy validation fails.
Gmail and transport failures use sanitized errors and do not expose OAuth secrets.

## Change or revoke access

To change the recipient set:

1. Stop or restart the MCP client so the old process cannot send.
2. Edit `GMAIL_ALLOSWED_RECIPENTS` in the environment that starts the MCP client.
3. Run `doctor` and confirm the recipient count.
4. Restart the MCP client.
5. Call `gmail_list_allowed_recipients` and verify every ID and address before sending.

To rotate credentials, run `logout-local`, replace the Desktop client JSON when necessary, and
run `auth` again. If a token or host is suspected compromised, revoke the Google account grant
before creating a replacement token.

## Troubleshooting

- **Server fails to start:** run `doctor`; fix the reported sender or allowlist error. The
  allowlist must be one non-empty comma-separated list with unique addresses.
- **Client secret warning:** set `GMAIL_CLIENT_SECRET_FILE` to an existing Desktop client JSON
  file outside the repository.
- **Token missing or expired:** run `auth`. If the stored scopes differ, run `logout-local` and
  then `auth`; the application refuses broader or different saved scopes.
- **Token permission failure:** run `chmod 600` on the token. The parent configuration directory
  should use mode `0700`.
- **Unknown recipient ID:** call `gmail_list_allowed_recipients`; callers must use generated IDs
  exactly as listed and cannot submit an address instead.
- **Send error says status may be unknown:** inspect Gmail's Sent folder before deciding whether
  to send a new message. The application deliberately performs no automatic retry.
- **MCP client cannot initialize the server:** use absolute paths, start the MCP client from an
  environment with all required `GMAIL_*` variables set, and run the `mcp` command manually to
  expose startup errors.

## Development and verification

Install development dependencies and run the complete local gate:

```bash
.venv/bin/python -m pip install -e ".[dev]"
make test
```

`make test` runs Ruff, strict mypy, and pytest. The tests include:

- allowlist parsing and immutable policy validation;
- exact OAuth scope and secure token-file behavior;
- recipient resolution, MIME injection cases, and an independent final MIME audit;
- a fake Gmail client that verifies exactly one non-retrying send call;
- MCP schema and tool behavior tests; and
- an offline end-to-end MCP client/server test proving that an off-list ID fails before the fake
  sender is invoked.

The test suite never uses real credentials and never sends real email. A live Gmail smoke test
is intentionally excluded because it creates an external, non-idempotent side effect.

## Provenance

The project structure, local OAuth workflow, diagnostics, and CI approach were adapted from
[`bajor/gmail-mcp-read-only`](https://github.com/bajor/gmail-mcp-read-only). The recipient-lock,
MIME audit, send-only client, and send-specific tests are implemented for this repository.
