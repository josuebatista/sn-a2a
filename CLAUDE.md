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

## Alternative: A2A Inspector

The A2A Inspector web tool may handle push notifications differently. See [TESTING_WITH_A2A_INSPECTOR.md](./TESTING_WITH_A2A_INSPECTOR.md) for instructions.
