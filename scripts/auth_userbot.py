"""
Userbot Authentication Script

Authenticate the Telegram userbot for file uploads.
Run this once to create the session file.

Usage: python scripts/auth_userbot.py
"""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()


async def authenticate_userbot():
    """Authenticate userbot interactively."""

    api_id = os.getenv('UPLOADER_API_ID')
    api_hash = os.getenv('UPLOADER_API_HASH')
    phone = os.getenv('UPLOADER_PHONE')

    if not all([api_id, api_hash, phone]):
        print("[ERROR] Missing credentials in .env file:")
        print("  - UPLOADER_API_ID")
        print("  - UPLOADER_API_HASH")
        print("  - UPLOADER_PHONE")
        print("\nPlease set these in your .env file and try again.")
        return

    print("="*60)
    print("USERBOT AUTHENTICATION".center(60))
    print("="*60)
    print(f"\nAPI ID: {api_id}")
    print(f"Phone: {phone}\n")

    # Create client - use sessions directory
    session_dir = 'sessions'
    os.makedirs(session_dir, exist_ok=True)
    session_name = os.path.join(session_dir, 'uploader_bot')

    client = TelegramClient(session_name, int(api_id), api_hash)

    try:
        # Connect
        print("[1/4] Connecting to Telegram...")
        await client.connect()

        # Check if already authorized
        if await client.is_user_authorized():
            print("[INFO] Session already exists and is authorized!")
            me = await client.get_me()
            print(f"[INFO] Logged in as: {me.first_name} (@{me.username or 'no username'})")
            print("\n[INFO] You can now use the upload module.")
            return

        # Send code request
        print("[2/4] Sending code request to Telegram...")
        await client.send_code_request(phone)

        # Get code from user
        print("\n[INFO] A verification code has been sent to your Telegram app.")
        code = input("Enter the code you received: ")

        # Sign in with code
        print("[3/4] Verifying code...")
        await client.sign_in(phone, code)

        # Check if 2FA password is needed
        if not await client.is_user_authorized():
            print("\n[INFO] Two-factor authentication enabled.")
            password = input("Enter your 2FA password (if enabled): ")
            await client.sign_in(password=password)

        # Get user info
        print("[4/4] Getting user info...")
        me = await client.get_me()

        print(f"\n" + "="*60)
        print("AUTHENTICATION SUCCESSFUL!".center(60))
        print("="*60)
        print(f"  Name: {me.first_name} {me.last_name or ''}")
        print(f"  Username: @{me.username or 'none'}")
        print(f"  User ID: {me.id}")
        print(f"  Phone: {me.phone}")
        print("="*60)
        print(f"\n[INFO] Session file: {session_name}.session")
        print("[INFO] You can now use the upload module.\n")

    except Exception as e:
        print(f"\n[ERROR] Authentication failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await client.disconnect()
        print("[INFO] Disconnected from Telegram")


if __name__ == '__main__':
    try:
        asyncio.run(authenticate_userbot())
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Authentication cancelled")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
