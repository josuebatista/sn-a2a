# ServiceNow A2A CLI

A command-line interface to communicate remotely with ServiceNow AI Agents using the A2A (Agent-to-Agent) protocol.

Based on [Vamsee Lakamsani's sn-a2a](https://github.com/ServiceNow/sn-a2a).

## Current Status: Blocked

There is a **known issue** with ServiceNow's A2A V2 implementation that prevents successful communication. See [Known Issues](#known-issues) below.

## Features

- Direct A2A protocol communication with ServiceNow AI Agents
- OAuth token refresh for secure authentication
- Local webhook server for push notifications (FastAPI/uvicorn)
- ngrok integration for public webhook URLs
- Debug mode for verbose logging

## Prerequisites

- Python 3.11 or higher
- UV package manager
- ngrok (for push notification webhook)
- ServiceNow instance with A2A agent configured
- OAuth credentials with `a2aauthscope` permission

## Setup

1. **Copy the example environment file**:
   ```bash
   cp .env.example .env
   ```

2. **Configure your credentials in `.env`**:
   - `A2A_CLIENT_BASE_URL`: Your ServiceNow instance URL
   - `A2A_CLIENT_AGENT_ID`: The sys_id of your A2A agent
   - `A2A_CLIENT_ID`: OAuth client ID
   - `A2A_CLIENT_SECRET`: OAuth client secret
   - `A2A_CLIENT_REFRESH_TOKEN`: Long-lived refresh token

3. **Install dependencies**:
   ```bash
   uv sync
   ```

4. **Install and configure ngrok**:
   ```bash
   # Windows
   winget install ngrok.ngrok

   # Configure auth token (get from https://dashboard.ngrok.com/get-started/your-authtoken)
   ngrok config add-authtoken YOUR_AUTH_TOKEN
   ```

## Usage

1. **Start ngrok tunnel** (Terminal 1):
   ```bash
   ngrok http 5000
   ```

2. **Run the CLI** (Terminal 2):
   ```bash
   uv run python main.py --webhook-url https://YOUR-NGROK-URL.ngrok-free.app/webhook
   ```

### Command Line Options

| Option | Description |
|--------|-------------|
| `--agent-id` | Agent sys_id (overrides `A2A_CLIENT_AGENT_ID` in .env) |
| `--webhook-url` | Public webhook URL (e.g., ngrok URL + `/webhook`) |
| `--port` | Local port for webhook server (default: 5000) |
| `--no-push` | Disable push notifications (synchronous mode) |
| `--debug` | Enable verbose debug logging |

### Debug Mode

```bash
uv run python main.py --webhook-url https://YOUR-NGROK-URL.ngrok-free.app/webhook --debug
```

Debug output includes:
- HTTP request/response details
- Agent card JSON
- Message objects sent and received
- Task state transitions

## Getting OAuth Tokens

The `get_refresh_token.py` script helps you obtain OAuth tokens using the Resource Owner Password Credentials (ROPC) flow. This is useful when:

- Setting up the project for the first time
- Your refresh token has expired
- You need to regenerate tokens after credential changes

### Usage

```bash
uv run python get_refresh_token.py
```

The script will:
1. Read `A2A_CLIENT_BASE_URL`, `A2A_CLIENT_ID`, and `A2A_CLIENT_SECRET` from your `.env` file (or prompt if missing)
2. Ask for your ServiceNow username and password
3. Request tokens from ServiceNow's OAuth endpoint
4. Output both `A2A_CLIENT_REFRESH_TOKEN` and `A2A_CLIENT_AUTH_TOKEN` values to copy into your `.env`

### Token Expiration

| Token Type | Default Expiration |
|------------|-------------------|
| Access Token | 30 minutes |
| Refresh Token | 100 days |

**Note:** Access tokens expire frequently. The main script will automatically use the refresh token to obtain new access tokens. If you're getting authentication errors, run `get_refresh_token.py` to generate fresh tokens.

## Known Issues

### Push Notification Contradiction (Blocker)

ServiceNow's A2A V2 implementation has contradictory behavior:

| Scenario | Error |
|----------|-------|
| **With** push config | `-32003: "Push Notification is not supported"` |
| **Without** push config | `-32602: "Push Notification URL is required for asynchronous requests"` |

The agent card advertises `pushNotifications: true` but rejects all `pushNotificationConfig` payloads. This is a **server-side issue** that needs to be resolved by ServiceNow.

See [CLAUDE.md](./CLAUDE.md) for detailed findings.

## Alternative: A2A Inspector

The A2A Inspector web tool may work differently. See [TESTING_WITH_A2A_INSPECTOR.md](./TESTING_WITH_A2A_INSPECTOR.md).

## Files in This Project

| File | Description |
|------|-------------|
| `main.py` | CLI with webhook server (blocked by push notification issue) |
| `get_refresh_token.py` | Helper script to obtain OAuth tokens via ROPC flow |
| `.env.example` | Template for environment variables |
| `.env` | Your credentials (**git-ignored**) |
| `CLAUDE.md` | Development notes and known issues |
| `TESTING_WITH_A2A_INSPECTOR.md` | A2A Inspector setup guide |

## Security Notes

- **Never commit `.env` files** - they contain secrets
- The `.gitignore` file excludes `.env` files
- Refresh tokens are valid for 100 days; access tokens expire in 30 minutes

## Contributing

1. Never commit `.env` files
2. Use environment variables for all credentials
3. Test with `.env.example` to ensure it has all required fields
4. Update documentation if adding new environment variables
