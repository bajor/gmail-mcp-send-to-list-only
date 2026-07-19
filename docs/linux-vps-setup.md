# Linux VPS setup

This guide covers the intended headless Linux/VPS deployment path for `gmail-mcp-send-to-list-only`.

The normal `auth` command uses Google Desktop OAuth and starts a temporary loopback callback listener. On a VPS connected over SSH, there is usually no local desktop browser, so authorization should be completed once through an SSH tunnel. After that, keep `token.json` on the VPS. The server refreshes expired access tokens automatically when a refresh token is available.

## 1. Install on the VPS

```bash
git clone https://github.com/bajor/gmail-mcp-send-to-list-only.git
cd gmail-mcp-send-to-list-only
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

## 2. Create the Google OAuth client

In Google Cloud:

1. Create or select a project.
2. Enable the Gmail API.
3. Configure the OAuth consent screen.
4. Add exactly this scope:

   ```text
   https://www.googleapis.com/auth/gmail.send
   ```

5. Create an OAuth client of type **Desktop app**.
6. Download the client JSON to the VPS, outside the repository.

Example:

```bash
mkdir -p ~/.config/gmail-mcp-send-to-list-only
chmod 700 ~/.config/gmail-mcp-send-to-list-only

mv ~/client_secret*.json \
  ~/.config/gmail-mcp-send-to-list-only/client_secret.json

chmod 600 ~/.config/gmail-mcp-send-to-list-only/client_secret.json
```

Do not commit either the client secret or token file.

## 3. Configure the environment

Set the values in the shell, service manager, or wrapper that starts Claude Code, Codex, OpenCode, or another MCP client:

```bash
export GMAIL_CLIENT_SECRET_FILE="$HOME/.config/gmail-mcp-send-to-list-only/client_secret.json"
export GMAIL_TOKEN_FILE="$HOME/.config/gmail-mcp-send-to-list-only/token.json"
export GMAIL_SENDER_EMAIL='sender@gmail.com'
export GMAIL_ALLOSWED_RECIPENTS='alice@example.com,bob@example.com'
```

`GMAIL_SENDER_EMAIL` must be the Gmail account used during OAuth authorization.

`GMAIL_TOKEN_FILE` is only the destination path at this point. `token.json` does not need to exist yet.

The project currently uses the environment variable name `GMAIL_ALLOSWED_RECIPENTS` exactly as shown above.

## 4. Authorize once on a headless VPS

### Recommended method: fixed callback port over SSH

The normal CLI uses an ephemeral callback port. For a VPS, using a fixed port makes SSH forwarding predictable.

On your **local computer**, open an SSH connection with local port forwarding:

```bash
ssh -L 8765:127.0.0.1:8765 ubuntu@YOUR_VPS_IP
```

If SSH runs on a non-default port, include the usual `-p PORT` option.

Inside that SSH session, go to the repository and run the OAuth flow with browser opening disabled:

```bash
cd ~/gmail-mcp-send-to-list-only
source .venv/bin/activate

python - <<'PY'
from google_auth_oauthlib.flow import InstalledAppFlow

from gmail_mcp_send_to_list_only.auth import SCOPES, save_credentials
from gmail_mcp_send_to_list_only.config import load_auth_config

config = load_auth_config()

print("Client secret:", config.require_client_secret_file())
print("Token will be saved to:", config.token_file)

flow = InstalledAppFlow.from_client_secrets_file(
    str(config.require_client_secret_file()),
    SCOPES,
)

credentials = flow.run_local_server(
    host="127.0.0.1",
    port=8765,
    open_browser=False,
)

save_credentials(credentials, config.token_file)

print("SUCCESS")
print("Token saved to:", config.token_file)
PY
```

The command prints a Google authorization URL.

Copy that full URL and open it in a browser on your **local computer**. Sign in with the exact account configured in `GMAIL_SENDER_EMAIL` and approve the requested Gmail send permission.

Google redirects the browser to `http://127.0.0.1:8765/...`. Because SSH forwards local port `8765` to `127.0.0.1:8765` on the VPS, the OAuth callback reaches the Python process running on the VPS.

After successful authorization, the VPS should contain:

```text
~/.config/gmail-mcp-send-to-list-only/
├── client_secret.json
└── token.json
```

Check permissions:

```bash
chmod 700 ~/.config/gmail-mcp-send-to-list-only
chmod 600 ~/.config/gmail-mcp-send-to-list-only/client_secret.json
chmod 600 ~/.config/gmail-mcp-send-to-list-only/token.json
```

The SSH tunnel is only needed for this one-time browser authorization and can be closed afterwards.

## 5. Verify the installation

Run:

```bash
cd ~/gmail-mcp-send-to-list-only
.venv/bin/gmail-mcp-send-to-list-only doctor
```

Fix every `FAIL` before starting the MCP server. The important checks include:

- OAuth scope;
- recipient policy;
- client secret path;
- token file permissions;
- token scope.

You can also verify the files directly:

```bash
ls -la ~/.config/gmail-mcp-send-to-list-only/
```

## 6. Start the MCP client with the same environment

The MCP server reads configuration from the environment inherited from its parent process. Setting variables in one SSH shell does not automatically make them available to a different service, `systemd` unit, `tmux` session, or future login.

For an interactive session:

```bash
export GMAIL_CLIENT_SECRET_FILE="$HOME/.config/gmail-mcp-send-to-list-only/client_secret.json"
export GMAIL_TOKEN_FILE="$HOME/.config/gmail-mcp-send-to-list-only/token.json"
export GMAIL_SENDER_EMAIL='sender@gmail.com'
export GMAIL_ALLOSWED_RECIPENTS='alice@example.com,bob@example.com'

codex
```

Use the equivalent parent environment for Claude Code or OpenCode.

For long-running VPS installations, prefer a protected wrapper script or service-manager environment configuration instead of manually exporting variables after every reboot.

## 7. You do not normally authorize on every restart

`token.json` persists on disk. When the access token expires, the application loads the saved credentials, uses the refresh token to obtain a new access token, and writes the refreshed credentials back to the same token file.

Normal lifecycle:

```text
one-time browser authorization
          |
          v
      token.json
          |
          v
MCP starts and loads token
          |
          v
access token expires
          |
          v
refresh automatically
          |
          v
updated token.json
```

Reauthorization is only required if the saved refresh token can no longer be used, for example after access is revoked or credentials are otherwise invalidated.

If the Google OAuth app is configured as an External app in Testing, review Google's current OAuth token-expiration rules before relying on it for unattended long-term VPS operation.

## Troubleshooting

### `Error: Gmail OAuth authorization failed.`

The CLI intentionally returns a sanitized OAuth error. On a headless VPS this can hide the underlying cause.

First verify:

```bash
echo "$GMAIL_CLIENT_SECRET_FILE"
echo "$GMAIL_TOKEN_FILE"
ls -l "$GMAIL_CLIENT_SECRET_FILE"
```

Then use the fixed-port Python authorization command from this guide. Unlike the normal wrapper error, a direct Python traceback can expose the actual configuration or network failure.

### Browser cannot reach the callback

Confirm that the SSH connection was created with exactly:

```bash
-L 8765:127.0.0.1:8765
```

and that the OAuth command is still running on the VPS while the browser completes authorization.

Do not expose port `8765` publicly in the VPS firewall. The callback should remain loopback-only and travel through SSH forwarding.

### Token disappears after logout

`logout-local` deliberately deletes only the configured local token. Run authorization again to create a replacement.

### MCP client works in one shell but not after reboot

This usually means the four `GMAIL_*` environment variables were exported only in an interactive shell. Configure them in the process that actually starts the MCP client.