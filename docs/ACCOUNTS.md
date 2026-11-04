# Accounts, sign-in and roles (2026-11-04)

Two roles with separate sign-ins: users (`/login`, can also sign up) and care-team staff (`/admin/login`, accounts created only from the command line).
Implementation: `app/auth.py`, endpoints in `app/server.py`, tests in `tests/test_auth.py` (18 tests, temporary database).

| Topic | What is implemented |
|---|---|
| Passwords | scrypt with a per-password salt; at least 8 characters with letters and digits; only the hash is stored |
| Sessions | random token in an HttpOnly, SameSite=Lax cookie; only its SHA-256 is stored; users 14 days, staff 8 hours; `Secure` flag on https or `COACH_COOKIE_SECURE=1`; changing the password signs out all devices |
| Roles | user and staff cookies are different; a user session cannot open `/api/admin/*`, a staff session cannot chat; a wrong role gives the same error as a wrong password |
| Who is asking | chat, approval and profile endpoints take the person from the session; a page can no longer choose a `user_id` |
| Brute force | 5 failed sign-ins per (username, address) in 10 minutes → HTTP 429 (kept in memory: resets on restart, one server only) |
| CSRF | every state-changing request must have a matching `Origin` header when one is sent; chat is a POST, not a link |
| Sign-up | choices (conditions, medicines) are whitelisted and mapped to the English tokens the safety rules read; free text has `;` and line breaks removed; consent is required; the name is never part of the text sent to the LLM |
| Account deletion | settings → deletes the account, profile, records and monitoring-log rows after a password check |
| Care-team audit | opening a person's data, changing an alert and signing in are written to `audit` and shown on the console's “열람 기록” tab |

## Demo mode (`COACH_DEMO`, default **on**)
This project uses synthetic people, so a clone should work without creating accounts: the login page shows the 10 synthetic users (one click, no password) and the
care-team login has “데모 의료진으로 입장”. Real sign-ups never appear in that list and cannot be entered this way; the demo staff sign-in is written to the audit log.
**Set `COACH_DEMO=0` in any deployment that stores real people's data** — the demo staff entry opens the whole care-team console.
Normal sign-in (accounts, passwords, lockout) works the same in both modes.

Create accounts: `scripts/manage_accounts.py seed-demo | create-staff USER "Name" | reset-password USER`.
`seed-demo` writes random passwords to `data/demo_accounts.txt` (mode 600, git-ignored).

Not done (needs a real deployment): HTTPS and `Secure` cookies behind a proxy, shared rate-limit store for several servers, e-mail/phone password reset,
two-factor sign-in for staff, a staff-account management screen, session list and per-device sign-out, a security review by someone else.
