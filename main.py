"""Simple CLI to communicate with ServiceNow AI Agent via A2A protocol - v14.0

This version includes a local webhook server to receive push notifications from ServiceNow.
Usage:
  1. Start ngrok: ngrok http 5000
  2. Run: uv run python main.py --webhook-url https://YOUR-NGROK-URL.ngrok.io/webhook
"""


import argparse
import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request


# Global queue to receive webhook notifications
notification_queue: asyncio.Queue = None
# Track pending requests by task ID
pending_requests: dict = {}


def create_app(debug: bool = False) -> FastAPI:
    """Create the FastAPI app for receiving webhook notifications."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global notification_queue
        notification_queue = asyncio.Queue()
        if debug:
            print("[DEBUG] Webhook server started, notification queue initialized")
        yield
        if debug:
            print("[DEBUG] Webhook server shutting down")

    app = FastAPI(lifespan=lifespan)

    @app.post("/webhook")
    async def receive_notification(request: Request):
        """Receive push notifications from ServiceNow A2A."""
        try:
            body = await request.json()
            if debug:
                print(f"\n[DEBUG] Webhook received notification:")
                print(json.dumps(body, indent=2))

            # Put the notification in the queue for the CLI to process
            await notification_queue.put(body)

            return {"status": "received"}
        except Exception as e:
            if debug:
                print(f"[DEBUG] Webhook error: {e}")
            return {"status": "error", "message": str(e)}

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok"}

    return app


async def run_webhook_server(port: int, debug: bool = False):
    """Run the webhook server in the background."""
    app = create_app(debug=debug)
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning" if not debug else "info"
    )
    server = uvicorn.Server(config)
    await server.serve()


async def refresh_token(
    base_url: str, client_id: str, client_secret: str, refresh_token: str, debug: bool = False
) -> str:
    """Refresh the OAuth access token using the refresh token."""
    token_url = f"{base_url.rstrip('/')}/oauth_token.do"


    payload = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }


    if debug:
        print(f"\n[DEBUG] Refresh Token URL: {token_url}")


    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )


        if response.status_code != 200:
            raise Exception(f"Failed to refresh token: {response.status_code} - {response.text}")


        token_data = response.json()
        return token_data["access_token"]




async def get_agent_card(httpx_client: httpx.AsyncClient, base_url: str, agent_id: str, debug: bool = False) -> dict:
    """Fetch the agent card from ServiceNow."""
    agent_card_url = f"{base_url.rstrip('/')}/api/sn_aia/a2a/v2/agent_card/id/{agent_id}"

    if debug:
        print(f"[DEBUG] Fetching agent card from: {agent_card_url}")

    response = await httpx_client.get(agent_card_url)
    response.raise_for_status()
    return response.json()




async def send_message(
    httpx_client: httpx.AsyncClient,
    endpoint_url: str,
    user_text: str,
    webhook_url: str = None,
    message_id: str = None,
    task_id: str = None,
    context_id: str = None,
    use_push: bool = True,
    debug: bool = False
) -> dict:
    """
    Send a message using message/send with optional push notification config.
    """
    message_id = message_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())

    # Build the message object according to ServiceNow A2A V2 spec
    message_obj = {
        "kind": "message",
        "role": "user",
        "parts": [
            {
                "kind": "text",
                "text": user_text
            }
        ],
        "messageId": message_id
    }

    # Add optional fields if provided
    if task_id:
        message_obj["taskId"] = task_id
    if context_id:
        message_obj["contextId"] = context_id

    # Build configuration
    configuration = {
        "acceptedOutputModes": ["application/json"]
    }

    # Only add push notification config if enabled and webhook URL provided
    if use_push and webhook_url:
        configuration["pushNotificationConfig"] = {
            "url": webhook_url,
            "authentication": {
                "schemes": []  # No auth for local testing
            }
        }

    # Build the full JSON-RPC request
    jsonrpc_request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "message/send",
        "params": {
            "message": message_obj,
            "configuration": configuration
        }
    }

    if debug:
        print(f"\n[DEBUG] Request URL: {endpoint_url}")
        print(f"[DEBUG] Request Body:\n{json.dumps(jsonrpc_request, indent=2)}")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        response = await httpx_client.post(
            endpoint_url,
            json=jsonrpc_request,
            headers=headers
        )

        if debug:
            print(f"\n[DEBUG] Response Status: {response.status_code}")
            print(f"[DEBUG] Response Content-Type: {response.headers.get('content-type', 'unknown')}")

        response_body = response.text
        if debug:
            print(f"[DEBUG] Response Body: {response_body}")

        if response.status_code != 200:
            try:
                error_json = json.loads(response_body)
                print(f"\n[ERROR] HTTP {response.status_code}")
                print(f"[ERROR] Response: {json.dumps(error_json, indent=2)}")
            except json.JSONDecodeError:
                print(f"\n[ERROR] HTTP {response.status_code}: {response_body}")
            return None

        return json.loads(response_body)

    except Exception as e:
        print(f"\n[ERROR] Request failed: {e}")
        if debug:
            import traceback
            traceback.print_exc()
        return None




def extract_response_text(response: dict) -> str:
    """Extract text from the JSON-RPC response or notification."""
    if not response:
        return "(No response)"

    # Handle JSON-RPC error
    if "error" in response:
        error = response["error"]
        return f"Error {error.get('code', 'unknown')}: {error.get('message', 'Unknown error')}"

    result = response.get("result", response)  # Use response directly if no 'result' wrapper
    text_parts = []

    # If it's a Task, look at status.message or artifacts
    if "status" in result:
        status = result.get("status", {})
        status_msg = status.get("message", {})
        if status_msg:
            for part in status_msg.get("parts", []):
                if part.get("kind") == "text" or "text" in part:
                    text_parts.append(part.get("text", ""))

        # Also check artifacts
        for artifact in result.get("artifacts", []):
            for part in artifact.get("parts", []):
                if part.get("kind") == "text" or "text" in part:
                    text_parts.append(part.get("text", ""))

    # If it's a Message directly
    elif "parts" in result:
        for part in result.get("parts", []):
            if part.get("kind") == "text" or "text" in part:
                text_parts.append(part.get("text", ""))

    # Check for message in result
    elif "message" in result:
        msg = result["message"]
        for part in msg.get("parts", []):
            if part.get("kind") == "text" or "text" in part:
                text_parts.append(part.get("text", ""))

    return "\n".join(text_parts) if text_parts else "(No text in response)"


async def wait_for_notification(timeout: float = 60.0, debug: bool = False) -> Optional[dict]:
    """Wait for a notification from the webhook."""
    global notification_queue

    if notification_queue is None:
        if debug:
            print("[DEBUG] Notification queue not initialized")
        return None

    try:
        notification = await asyncio.wait_for(notification_queue.get(), timeout=timeout)
        return notification
    except asyncio.TimeoutError:
        if debug:
            print(f"[DEBUG] Timed out waiting for notification after {timeout}s")
        return None




async def cli_loop(
    httpx_client: httpx.AsyncClient,
    execution_url: str,
    webhook_url: str = None,
    use_push: bool = True,
    debug: bool = False
):
    """Run the CLI loop to communicate with the A2A agent."""
    # Track context for conversation continuity
    context_id = None
    task_id = None

    print("\nType your question to the agent and press Enter to send.")
    print("Type 'quit' or 'exit' to end the session\n")

    while True:
        try:
            # Use asyncio-friendly input
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("You: ").strip()
            )
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in ["quit", "exit"]:
            print("Goodbye!")
            break

        if not user_input:
            continue

        # Send message with optional webhook URL
        response = await send_message(
            httpx_client=httpx_client,
            endpoint_url=execution_url,
            user_text=user_input,
            webhook_url=webhook_url,
            task_id=task_id,
            context_id=context_id,
            use_push=use_push,
            debug=debug
        )

        if response:
            result = response.get("result", {})
            if isinstance(result, dict):
                status = result.get("status", {})
                state = status.get("state", "")
                new_task_id = result.get("id")
                new_context_id = result.get("contextId")

                if debug:
                    print(f"[DEBUG] Initial response state: {state}")
                    print(f"[DEBUG] Task ID: {new_task_id}")

                # If task is submitted/working, wait for push notification
                if state in ["submitted", "working"]:
                    print("Agent: (Processing... waiting for response)")

                    # Wait for the webhook notification
                    notification = await wait_for_notification(timeout=120.0, debug=debug)

                    if notification:
                        response_text = extract_response_text(notification)
                        print(f"\nAgent: {response_text}\n")

                        # Update context from notification
                        notif_result = notification.get("result", notification)
                        if isinstance(notif_result, dict):
                            notif_status = notif_result.get("status", {})
                            notif_state = notif_status.get("state", "")

                            if notif_state in ["completed", "failed", "canceled", "rejected"]:
                                context_id = None
                                task_id = None
                            else:
                                context_id = notif_result.get("contextId")
                                task_id = notif_result.get("id")
                    else:
                        print("\nAgent: (Timed out waiting for response)\n")
                        context_id = None
                        task_id = None

                # If we got an immediate response (completed, failed, etc.)
                elif state in ["completed", "failed", "canceled", "rejected"]:
                    response_text = extract_response_text(response)
                    print(f"\nAgent: {response_text}\n")
                    context_id = None
                    task_id = None

                else:
                    # Unknown state, just print what we got
                    response_text = extract_response_text(response)
                    print(f"\nAgent: {response_text}\n")
                    context_id = new_context_id
                    task_id = new_task_id
        else:
            print("\nAgent: (Failed to get response - check error above)\n")


async def main(agent_sys_id: str = None, webhook_url: str = None, port: int = 5000, no_push: bool = False, debug: bool = False):
    """Run the CLI with webhook server to communicate with the A2A agent."""
    load_dotenv()

    base_url = os.getenv("A2A_CLIENT_BASE_URL")
    agent_id = agent_sys_id if agent_sys_id else os.getenv("A2A_CLIENT_AGENT_ID")

    if not agent_id:
        print("Error: Agent sys_id not provided. Use --agent-id parameter or set A2A_CLIENT_AGENT_ID in .env")
        return

    use_push = not no_push

    # Webhook URL is required only if using push notifications
    webhook_url = webhook_url or os.getenv("A2A_WEBHOOK_URL")
    if use_push and not webhook_url:
        print("Error: Webhook URL not provided.")
        print("Usage:")
        print("  1. Start ngrok: ngrok http 5000")
        print("  2. Run: uv run python main.py --webhook-url https://YOUR-NGROK-URL.ngrok.io/webhook")
        print("\nOr set A2A_WEBHOOK_URL in your .env file")
        print("\nAlternatively, use --no-push to disable push notifications (synchronous mode)")
        return

    client_id = os.getenv("A2A_CLIENT_ID")
    client_secret = os.getenv("A2A_CLIENT_SECRET")
    refresh_token_value = os.getenv("A2A_CLIENT_REFRESH_TOKEN")
    existing_auth_token = os.getenv("A2A_CLIENT_AUTH_TOKEN")

    if not base_url:
        print("Error: Missing A2A_CLIENT_BASE_URL environment variable")
        return

    # Get or refresh the auth token
    auth_token = None
    if existing_auth_token:
        print("Using existing auth token from A2A_CLIENT_AUTH_TOKEN...")
        auth_token = existing_auth_token
    elif all([client_id, client_secret, refresh_token_value]):
        print("No existing token found. Refreshing OAuth token...")
        try:
            auth_token = await refresh_token(base_url, client_id, client_secret, refresh_token_value, debug=debug)
            print("Token refreshed successfully!")
        except Exception as e:
            print(f"Error refreshing token: {e}")
            return
    else:
        print("Error: No auth token or refresh credentials provided in .env file")
        return

    # Start the webhook server in the background only if using push notifications
    server_task = None
    if use_push:
        print(f"\nStarting webhook server on port {port}...")
        print(f"Webhook URL configured: {webhook_url}")

        # Create and start the webhook server task
        server_task = asyncio.create_task(run_webhook_server(port=port, debug=debug))

        # Give the server a moment to start
        await asyncio.sleep(1)
    else:
        print("\nRunning in synchronous mode (no push notifications)")

    timeout = httpx.Timeout(300.0)

    async with httpx.AsyncClient(timeout=timeout) as httpx_client:
        # Fetch agent card (no auth needed for public card)
        try:
            agent_card = await get_agent_card(httpx_client, base_url, agent_id, debug=debug)
            print(f"\nConnected to agent: {agent_card.get('name', 'Unknown')}")
            print(f"Description: {agent_card.get('description', 'No description')}")

            if debug:
                print(f"[DEBUG] Agent Card: {json.dumps(agent_card, indent=2)}")
        except Exception as e:
            print(f"Error getting agent card: {e}")
            server_task.cancel()
            return

        # Set auth header for subsequent requests
        httpx_client.headers["Authorization"] = f"Bearer {auth_token}"

        # V2 execution endpoint
        execution_url = f"{base_url.rstrip('/')}/api/sn_aia/a2a/v2/agent/id/{agent_id}"

        if debug:
            print(f"[DEBUG] Execution URL: {execution_url}")

        # Run the CLI loop
        try:
            await cli_loop(
                httpx_client=httpx_client,
                execution_url=execution_url,
                webhook_url=webhook_url,
                use_push=use_push,
                debug=debug
            )
        finally:
            # Clean up the server if it was started
            if server_task:
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass




if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="CLI to communicate with A2A agents via the A2A protocol"
    )
    parser.add_argument(
        "--agent-id",
        type=str,
        help="Agent sys_id (overrides A2A_CLIENT_AGENT_ID in .env file)",
        default=None
    )
    parser.add_argument(
        "--webhook-url",
        type=str,
        help="Public webhook URL (e.g., https://abc123.ngrok.io/webhook)",
        default=None
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Local port for webhook server (default: 5000)",
        default=5000
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Disable push notifications (synchronous mode)",
        default=False
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
        default=False
    )

    args = parser.parse_args()
    asyncio.run(main(
        agent_sys_id=args.agent_id,
        webhook_url=args.webhook_url,
        port=args.port,
        no_push=args.no_push,
        debug=args.debug
    ))
