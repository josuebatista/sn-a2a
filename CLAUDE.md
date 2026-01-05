# ServiceNow A2A V2 - Known Issues and Findings

## Push Notification Contradiction (Blocker)

ServiceNow's A2A V2 implementation has a **contradictory behavior** that prevents successful communication:

| Scenario | Error Code | Error Message |
|----------|------------|---------------|
| **With** `pushNotificationConfig` | `-32003` | "Push Notification is not supported" |
| **Without** `pushNotificationConfig` | `-32602` | "Push Notification URL is required for asynchronous requests" |

This is a catch-22: the server **requires** push notifications but **rejects** the push config when provided.

### Agent Card vs Reality

The agent card advertises:
```json
"capabilities": {
  "streaming": false,
  "pushNotifications": true,
  "stateTransitionHistory": false
}
```

But the implementation rejects all `pushNotificationConfig` payloads with error `-32003`.

### Testing Performed

1. Set up ngrok tunnel (`ngrok http 5000`)
2. Created local FastAPI webhook server listening on `/webhook`
3. Sent request WITH `pushNotificationConfig.url` pointing to ngrok URL
4. Received error: "Push Notification is not supported"
5. Sent request WITHOUT `pushNotificationConfig`
6. Received error: "Push Notification URL is required for asynchronous requests"

### Conclusion

This appears to be a **server-side bug or misconfiguration** in the ServiceNow A2A implementation. The agent needs to be fixed on the ServiceNow side to either:
- Accept and use the push notification config, OR
- Support synchronous responses without requiring push notifications

## Summary of What We Learned

ServiceNow A2A V2 requirements:
1. **`kind: "message"`** required on the Message object
2. **Real push notification webhook** required (but currently broken - see above)
3. The `blocking: true` flag is ignored
4. The `message/stream` method isn't supported by this agent (`streaming: false`)

## Script Features

The `main.py` script includes:
- Local webhook server (FastAPI/uvicorn) on port 5000
- ngrok integration for public webhook URL
- `--webhook-url` parameter for specifying the public URL
- `--no-push` flag to attempt synchronous mode (fails due to server requirement)
- `--debug` flag for verbose logging

### Usage (when server-side is fixed)

```bash
# Terminal 1: Start ngrok
ngrok http 5000

# Terminal 2: Run the CLI with the ngrok URL
uv run python main.py --webhook-url https://YOUR-NGROK-URL.ngrok-free.app/webhook --debug
```

## A2A Inspector Findings

The [A2A Inspector](https://github.com/a2aproject/a2a-inspector) is a web-based tool for testing A2A agents. We tested it against the ServiceNow Timestamp Agent.

### How A2A Inspector Works

A2A Inspector uses a **different approach** than our `main.py` script:

| Aspect | sn-a2a (main.py) | a2a-inspector |
|--------|------------------|---------------|
| **Communication** | Push notifications via webhook | Streaming responses |
| **Transport** | HTTP POST to ngrok webhook | Socket.IO WebSocket |
| **Config sent** | `pushNotificationConfig` in params | No push config |
| **Server requirement** | Public webhook URL (ngrok) | Local WebSocket only |

From `a2a-inspector/backend/app.py`:
```python
response_stream = a2a_client.send_message(message)
async for stream_result in response_stream:
    await _process_a2a_response(stream_result, sid, message_id)
```

The inspector streams responses using the A2A client library, avoiding push notifications entirely.

### OAuth 2.0 Authentication Workaround

A2A Inspector does **not** have a built-in OAuth 2.0 flow. Available auth options:
- No Auth
- Basic Auth
- **Bearer Token** ← Use this for ServiceNow
- API Key

**Workaround:** Pre-generate an OAuth access token and use it as a Bearer Token.

#### Steps:
1. Generate a fresh access token:
   ```bash
   cd C:\Users\josue\workarea\sn-a2a
   uv run python get_refresh_token.py
   ```

2. Copy the `access_token` value from the output

3. In A2A Inspector:
   - Select **"Bearer Token"** as auth type
   - Paste the access token

4. Enter the Agent Card URL:
   ```
   https://procmine01.service-now.com/api/sn_aia/a2a/v2/agent_card/id/f70a943f4782b6106cbb1c25f16d4302
   ```

5. Click "Fetch Agent Card"

**Note:** Access tokens expire in ~30 minutes. Regenerate as needed.

### Issues Encountered

#### 1. Agent Card Fetches Successfully
The inspector successfully retrieves the agent card via HTTP:
```
POST /agent-card HTTP/1.1" 200 OK
```

#### 2. Client Initialization Fails Silently
After fetching the agent card, the frontend should emit an `initialize_client` Socket.IO event. This event never reaches the backend, causing:
- Message input remains greyed out
- "No active session" status
- Cannot send messages

**Suspected cause:** Socket.IO connection issue between frontend (port 5173) and backend (port 5001).

#### 3. Streaming Not Supported
Even if Socket.IO worked, the Timestamp Agent has `streaming: false`, so the inspector's streaming approach would likely fail anyway.

### A2A Inspector Setup

```bash
# Clone the repo
git clone https://github.com/a2aproject/a2a-inspector
cd a2a-inspector

# Install dependencies
uv sync

# Terminal 1: Start backend
uv run uvicorn backend.app:app --host 127.0.0.1 --port 5001

# Terminal 2: Start frontend
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`, backend on `http://localhost:5001`.

### Conclusion

A2A Inspector is **not compatible** with the ServiceNow Timestamp Agent because:
1. The agent has `streaming: false` - inspector relies on streaming
2. The agent requires push notifications but rejects the config (same catch-22)
3. Socket.IO connection issues prevent testing

The fundamental problem remains on ServiceNow's side: the agent configuration is broken.
