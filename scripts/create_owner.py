"""Create (or reset the password of) the single LockedIn user via the Supabase admin API.

Usage: make owner EMAIL=you@example.com  (asks for the password, so it stays out of your shell history)
Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env (or the environment).
"""

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

from dotenv import load_dotenv


def call(method: str, url: str, key: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"apikey": key, "Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--password", help="avoid: it lands in your shell history; leave it out to be asked")
    a = p.parse_args()
    if not a.password:
        a.password = getpass.getpass("Password: ")
        if a.password != getpass.getpass("Again: "):
            print("The passwords don't match.")
            return 1
    if not a.password:
        print("The password can't be empty.")
        return 1
    base, key = os.environ["SUPABASE_URL"].rstrip("/"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not key:
        print("Set SUPABASE_SERVICE_ROLE_KEY (from `supabase status` or the dashboard).")
        return 1
    if a.email.lower() != os.environ.get("OWNER_EMAIL", "").lower():
        print(f"Warning: OWNER_EMAIL is {os.environ.get('OWNER_EMAIL')!r}; the API only lets that address in.")

    status, body = call("POST", f"{base}/auth/v1/admin/users", key,
                        {"email": a.email, "password": a.password, "email_confirm": True})
    if status in (200, 201):
        print(f"Created user {body['id']} ({a.email})")
        return 0
    if status == 422 and "already" in json.dumps(body).lower():
        _, users = call("GET", f"{base}/auth/v1/admin/users?per_page=1000", key)
        user = next((u for u in users.get("users", []) if u["email"].lower() == a.email.lower()), None)
        if user:
            call("PUT", f"{base}/auth/v1/admin/users/{user['id']}", key, {"password": a.password})
            print(f"User exists; password updated ({a.email})")
            return 0
    print(f"Failed ({status}): {body}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
