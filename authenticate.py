#!/usr/bin/env python3
"""Standalone script to run initial OAuth 2.0 authorization and verify connection.

Run this script directly in a terminal window to open your browser, authorize the app,
and generate the credentials/token.json file.
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.auth import get_credentials, find_client_secret_file
from src.studio import get_channel_overview


def main():
    print("=" * 60)
    print("  Custom YouTube MCP - Initial OAuth 2.0 Setup")
    print("=" * 60)

    secret_file = find_client_secret_file()
    if not secret_file:
        print("\n[!] Error: No client secret file found in credentials/ directory.")
        print("Please follow these steps:")
        print("1. Go to Google Cloud Console (https://console.cloud.google.com/)")
        print("2. Create or select a project, then enable:")
        print("   - YouTube Data API v3")
        print("   - YouTube Analytics API")
        print("3. Configure OAuth consent screen (User type: External, add your email as Test user).")
        print("4. Go to Credentials -> Create Credentials -> OAuth client ID (Type: Desktop app).")
        print("5. Download the JSON file and save it as:")
        print(f"   {PROJECT_ROOT / 'credentials' / 'client_secret.json'}\n")
        sys.exit(1)

    print(f"\n[+] Found client secret: {secret_file.name}")
    print("[+] Initiating browser authorization...")

    try:
        creds = get_credentials()
        print("\n[✓] OAuth 2.0 authorization successful!")
        print(f"[✓] Token saved to {PROJECT_ROOT / 'credentials' / 'token.json'}")

        print("\n[+] Testing connection to YouTube Data API...")
        overview = get_channel_overview()
        if "error" in overview:
            print(f"[!] Warning: API returned an error: {overview['error']}")
        else:
            print(f"[✓] Successfully connected to channel: '{overview.get('title')}'")
            print(f"    - Custom URL: {overview.get('custom_url')}")
            print(f"    - Subscribers: {overview.get('subscriber_count')}")
            print(f"    - Total Views: {overview.get('total_views')}")
            print(f"    - Videos: {overview.get('video_count')}")

        print("\nSetup complete! You can now use this MCP server in Antigravity or Claude Desktop.")

    except Exception as e:
        print(f"\n[!] Authorization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
