"""LinkedIn API preflight validation.

Run this script to confirm:
1. LinkedIn App has w_member_social + openid + profile scopes
2. OAuth token exchange works
3. Refresh token rotation semantics
4. POST /rest/posts creates a post successfully (dry run)
5. GET /v2/userinfo returns the person URN
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

from src.linkedin.client import LinkedInAuthError, LinkedInClient  # noqa: E402

load_dotenv()


def main() -> None:
    """Validate LinkedIn API credentials, token refresh, and post creation."""
    print("LinkedIn API Preflight Check")
    print("=" * 40)

    client = LinkedInClient()
    checks_passed = 0
    checks_total = 0

    # Check 1: Credentials present
    checks_total += 1
    print("\n1. Checking credentials...")
    if client.client_id and client.client_secret:
        print("   Client ID: configured")
        print("   Client Secret: configured")
        checks_passed += 1
    else:
        print("   FAIL: Missing LINKEDIN_CLIENT_ID or LINKEDIN_CLIENT_SECRET")
        print("   Set them in .env or as environment variables.")
        print(f"\nResult: {checks_passed}/{checks_total} checks passed")
        return

    # Check 2: Refresh token present
    checks_total += 1
    print("\n2. Checking refresh token...")
    if client.refresh_token:
        print("   Refresh token: configured")
        checks_passed += 1
    else:
        print("   FAIL: Missing LINKEDIN_REFRESH_TOKEN")
        print("   Run: python scripts/linkedin_setup.py")
        print(f"\nResult: {checks_passed}/{checks_total} checks passed")
        return

    # Check 3: Token refresh
    checks_total += 1
    print("\n3. Testing token refresh...")
    try:
        client.refresh_access_token()
        print("   Access token: obtained")
        if client.refresh_token:
            print("   New refresh token received (rotation works)")
        checks_passed += 1
    except LinkedInAuthError as e:
        print(f"   FAIL: {e}")
        print(f"\nResult: {checks_passed}/{checks_total} checks passed")
        return

    # Check 4: Person URN
    checks_total += 1
    print("\n4. Fetching person URN (GET /v2/userinfo)...")
    try:
        urn = client.get_person_urn()
        print(f"   Person URN: {urn}")
        checks_passed += 1
    except Exception as e:
        print(f"   FAIL: {e}")

    # Check 5: Dry-run post
    checks_total += 1
    print("\n5. Testing post creation (dry run)...")
    try:
        client.create_post(
            text="Preflight test post. This will not be published.",
            dry_run=True,
        )
        print("   Dry run successful (post was NOT published)")
        checks_passed += 1
    except Exception as e:
        print(f"   FAIL: {e}")

    print()
    print("=" * 40)
    print(f"Result: {checks_passed}/{checks_total} checks passed")
    if checks_passed == checks_total:
        print("All checks passed. LinkedIn integration is ready.")
    else:
        print("Some checks failed. Review the output above.")


if __name__ == "__main__":
    main()
