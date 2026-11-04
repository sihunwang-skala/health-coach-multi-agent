"""Create accounts from the command line (care-team accounts cannot be created on the web, on purpose).

  .venv/bin/python scripts/manage_accounts.py create-staff USERNAME "Display name"      # asks for the password
  .venv/bin/python scripts/manage_accounts.py reset-password USERNAME                    # asks for the new password
  .venv/bin/python scripts/manage_accounts.py seed-demo                                  # the 10 synthetic users + one staff
                                                                                         # account, random passwords written to
                                                                                         # data/demo_accounts.txt (git-ignored)
"""
from __future__ import annotations

import getpass
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi import HTTPException  # noqa: E402

from app import auth  # noqa: E402
from mcp_servers.user_server import _db  # noqa: E402


def ask_password() -> str:
    pw = os.environ.get("COACH_NEW_PASSWORD") or getpass.getpass("Password: ")
    if (msg := auth.check_password_rules(pw)):
        sys.exit(msg)
    return pw


def seed_demo() -> None:
    _db().close()   # makes sure the profiles exist
    users = json.loads((ROOT / "data" / "users.json").read_text())
    lines = ["# Demo sign-ins for the 10 synthetic users and one care-team account. Local file, never commit.", ""]
    for u in users:
        name = u["name"].split()[0].lower()
        pw = secrets.token_urlsafe(9) + "7"
        try:
            auth.create_account(name, pw, "user", u["name"], u["id"])
        except HTTPException:
            lines.append(f"user  {name:10s} (already exists, password unchanged)")
            continue
        lines.append(f"user  {name:10s} {pw}   {u['name']}")
    pw = secrets.token_urlsafe(9) + "7"
    try:
        auth.create_account("careteam", pw, "staff", "Care team (demo)")
        lines.append(f"staff careteam   {pw}   /admin/login")
    except HTTPException:
        lines.append("staff careteam   (already exists, password unchanged)")
    out = ROOT / "data" / "demo_accounts.txt"
    out.write_text("\n".join(lines) + "\n")
    out.chmod(0o600)
    print(f"wrote {out} ({len(users)} users + 1 staff)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "seed-demo":
        seed_demo()
    elif cmd == "create-staff" and len(sys.argv) >= 4:
        auth.create_account(sys.argv[2], ask_password(), "staff", sys.argv[3])
        print("created", sys.argv[2])
    elif cmd == "reset-password" and len(sys.argv) >= 3:
        row = auth.run("SELECT id FROM accounts WHERE username = ?", (auth.norm(sys.argv[2]),), one=True)
        if not row:
            sys.exit("no such account")
        auth.set_password(row["id"], ask_password())
        print("password changed; every session of this account was signed out")
    else:
        sys.exit(__doc__)
