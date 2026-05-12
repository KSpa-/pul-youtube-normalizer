"""OAuth2 flow for YouTube Data API."""
from __future__ import annotations

import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/youtube"]
TOKEN_PATH = Path("token.json")
CLIENT_SECRETS_CANDIDATES = [Path("client_secrets.json"), Path("client_secrets.json.json")]


class CredentialsNotFound(RuntimeError):
    pass


def _find_client_secrets() -> Path:
    for p in CLIENT_SECRETS_CANDIDATES:
        if p.exists():
            if p.name == "client_secrets.json.json":
                print(
                    "WARNING: found 'client_secrets.json.json' (double extension). "
                    "Consider renaming to 'client_secrets.json'.",
                    file=sys.stderr,
                )
            return p
    raise CredentialsNotFound(
        "No client_secrets.json found. Download OAuth client credentials from "
        "Google Cloud Console and save as ./client_secrets.json."
    )


def get_credentials() -> Credentials:
    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except (ValueError, OSError) as e:
            print(
                f"WARNING: could not load {TOKEN_PATH} ({e}). Re-authenticating.",
                file=sys.stderr,
            )
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        return creds

    secrets_path = _find_client_secrets()
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
    creds = flow.run_local_server(
        port=0,
        open_browser=False,
        authorization_prompt_message=(
            "\n>>> Copy this URL and paste it into the Chrome profile you want to "
            "authorize as the PUL channel owner:\n\n  {url}\n\n"
            "(A local server is listening for the redirect.)\n"
        ),
    )
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds
