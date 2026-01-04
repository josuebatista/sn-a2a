import os
import httpx
import asyncio
from dotenv import load_dotenv
from getpass import getpass

async def get_tokens():
    load_dotenv()
    print("--- ServiceNow OAuth Token Generator ---")
    
    # Get config from .env or prompt
    base_url = os.getenv("A2A_CLIENT_BASE_URL")
    if not base_url:
        base_url = input("Instance URL (e.g., https://instance.service-now.com): ").strip()
        
    client_id = os.getenv("A2A_CLIENT_ID")
    if not client_id:
        client_id = input("Client ID: ").strip()
        
    client_secret = os.getenv("A2A_CLIENT_SECRET")
    if not client_secret:
        client_secret = input("Client Secret: ").strip()
    
    print(f"\nConnecting to: {base_url}")
    username = input("ServiceNow Username: ").strip()
    password = getpass("ServiceNow Password: ")

    token_url = f"{base_url.rstrip('/')}/oauth_token.do"
    
    payload = {
        "grant_type": "password",
        "client_id": client_id,
        "client_secret": client_secret,
        "username": username,
        "password": password
    }

    print("\nRequesting tokens...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                token_url, 
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code == 200:
                data = response.json()
                print("\nSUCCESS! Update your .env file with these values:\n")
                print(f"A2A_CLIENT_REFRESH_TOKEN={data.get('refresh_token')}")
                print(f"A2A_CLIENT_AUTH_TOKEN={data.get('access_token')}")
                print("\nNote: Wrap these values in double quotes in your .env if they contain special characters like '#'.")
            else:
                print(f"\nERROR: {response.status_code}")
                print(response.text)
        except Exception as e:
            print(f"\nConnection Error: {e}")

if __name__ == "__main__":
    asyncio.run(get_tokens())
