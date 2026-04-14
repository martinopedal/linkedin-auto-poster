"""Interactive OAuth setup for LinkedIn.

Opens browser for authorization, captures redirect with a local HTTP server,
exchanges the auth code for access tokens, and optionally sets the GitHub
Secret automatically.

Usage:
    python scripts/linkedin_setup.py              # setup + manual secret
    python scripts/linkedin_setup.py --set-secret # setup + auto-set GitHub secret
"""

from __future__ import annotations

import argparse
import http.server
import os
import secrets
import subprocess
import threading
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv

load_dotenv()

SCOPES = "openid profile w_member_social"
REDIRECT_URI = "http://localhost:8080/callback"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"


def _get_repo_slug() -> str:
    """Get the GitHub repo slug (owner/name) from git remote or env."""
    try:
        import subprocess as sp
        result = sp.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Handle both HTTPS and SSH URLs
            if "github.com" in url:
                parts = url.rstrip(".git").split("github.com")[-1].lstrip("/:")
                return parts
    except Exception:
        pass
    return os.environ.get("GITHUB_REPOSITORY", "your-username/linkedin-auto-poster")


def main() -> None:
    """Run interactive LinkedIn OAuth setup and token exchange."""
    parser = argparse.ArgumentParser(description="LinkedIn OAuth setup")
    parser.add_argument(
        "--set-secret",
        action="store_true",
        help="Automatically set LINKEDIN_ACCESS_TOKEN as a GitHub Secret",
    )
    args = parser.parse_args()

    client_id = os.environ.get("LINKEDIN_CLIENT_ID")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("ERROR: Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in .env")
        return

    repo = _get_repo_slug()
    state = secrets.token_urlsafe(32)
    auth_code_holder = {"code": None, "state": state}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            if params.get("state", [None])[0] != auth_code_holder["state"]:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid state parameter. Possible CSRF attack.")
                return
            if "code" in params:
                auth_code_holder["code"] = params["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Authorization successful. You can close this tab.")
            elif "error" in params:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(
                    f"Error: {params.get('error_description', ['Unknown'])[0]}".encode()
                )
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No authorization code received.")

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("localhost", 8080), CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    auth_params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    })
    auth_link = f"{AUTH_URL}?{auth_params}"

    print("Opening browser for LinkedIn authorization...")
    print(f"If it does not open, visit: {auth_link}")
    webbrowser.open(auth_link)

    server_thread.join(timeout=120)
    server.server_close()

    if not auth_code_holder["code"]:
        print("ERROR: No authorization code received. Did you authorize in the browser?")
        return

    print("Exchanging authorization code for tokens...")
    resp = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": auth_code_holder["code"],
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "client_secret": client_secret,
    }, timeout=30)

    if resp.status_code != 200:
        print(f"ERROR: Token exchange failed ({resp.status_code}): {resp.text}")
        return

    tokens = resp.json()
    access_token = tokens.get("access_token", "")
    expires_in = tokens.get("expires_in", 0)

    if not access_token:
        print("ERROR: No access token in response")
        return

    # Verify token works
    verify = requests.get(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if verify.status_code != 200:
        print(f"ERROR: Token verification failed ({verify.status_code})")
        return

    person_id = verify.json().get("sub", "unknown")
    print()
    print("=" * 60)
    print("SUCCESS: LinkedIn OAuth token obtained and verified")
    print("=" * 60)
    print(f"  Authenticated as: urn:li:person:{person_id}")
    print(f"  Expires in: {expires_in // 3600}h (~{expires_in // 86400} days)")

    if args.set_secret:
        print()
        print("Setting GitHub Secret LINKEDIN_ACCESS_TOKEN...")
        result = subprocess.run(
            ["gh", "secret", "set", "LINKEDIN_ACCESS_TOKEN", "-R", repo],
            input=access_token,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("  GitHub Secret set successfully")
        else:
            print(f"  ERROR setting secret: {result.stderr}")
            print("  Set it manually: gh secret set LINKEDIN_ACCESS_TOKEN -R", repo)
    else:
        print()
        print("To set the GitHub Secret, run:")
        print("  python scripts/linkedin_setup.py --set-secret")
        print()
        print("Or manually:")
        print(f"  gh secret set LINKEDIN_ACCESS_TOKEN -R {repo}")
        print("  (paste the token when prompted)")

    # Update local .env if it exists
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        lines = open(env_path, encoding="utf-8").readlines()
        updated = False
        for i, line in enumerate(lines):
            if line.startswith("LINKEDIN_ACCESS_TOKEN="):
                lines[i] = f"LINKEDIN_ACCESS_TOKEN={access_token}\n"
                updated = True
                break
        if not updated:
            lines.append(f"\nLINKEDIN_ACCESS_TOKEN={access_token}\n")
        open(env_path, "w", encoding="utf-8").writelines(lines)
        print("  Updated local .env file")

    print()
    print("Verify with: python main.py preflight")


if __name__ == "__main__":
    main()
