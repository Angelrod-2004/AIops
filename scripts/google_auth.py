"""One-time OAuth helper: links Gmail + Google Calendar to this machine.

Usage:
    python scripts/google_auth.py

It opens a browser, asks for the Gmail + Calendar scopes, and writes a
refreshable token to credentials/google_token.json (path configurable through
GOOGLE_TOKEN_PATH).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402


def main() -> int:
    secret = config.GOOGLE_CLIENT_SECRET_PATH
    if not secret.exists():
        print("Missing OAuth client file.")
        print("  1. Create an OAuth client (Desktop app) at https://console.cloud.google.com/apis/credentials")
        print("  2. Enable the Gmail API and the Google Calendar API")
        print(f"  3. Download the JSON and save it as: {secret}")
        return 1

    from google_auth_oauthlib.flow import InstalledAppFlow

    print(f"Using client secret: {secret}")
    print("Scopes:")
    for scope in config.GOOGLE_SCOPES:
        print(f"  - {scope}")
    print("\nA browser window will open. Sign in and grant access.\n")

    flow = InstalledAppFlow.from_client_secrets_file(str(secret), config.GOOGLE_SCOPES)
    credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline", open_browser=True)

    token_path = config.GOOGLE_TOKEN_PATH
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    print(f"\nToken saved to {token_path}")
    print("Gmail and Google Calendar are now LIVE. Restart streamlit to pick it up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
