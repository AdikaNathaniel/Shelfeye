"""Set a new password for a dashboard account, or list the accounts.

Run on the machine that holds the database (your computer, or Render's Shell tab):
    python reset_password.py                 # list accounts
    python reset_password.py you@example.com # set a new password (asked for, not echoed)

Uses the same database as the server (SHELFEYE_DB, default shelfeye.db).
Logs the account out everywhere, so the new password is needed on every device.
"""
import getpass
import sys
from contextlib import closing

from auth import MIN_PASSWORD_LENGTH, hash_password
from db import DB_PATH, connect, init_db


def main():
    init_db()
    with closing(connect()) as conn, conn:
        if len(sys.argv) < 2:
            rows = conn.execute("SELECT email, created_at FROM users ORDER BY id").fetchall()
            print(f"Accounts in {DB_PATH}:" if rows else f"No accounts in {DB_PATH}.")
            for row in rows:
                print(f"  {row['email']}  (created {row['created_at']})")
            return

        email = sys.argv[1].strip().lower()
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            sys.exit(f"No account for {email} in {DB_PATH}. Register it on the dashboard instead.")

        password = getpass.getpass("New password: ")
        if len(password) < MIN_PASSWORD_LENGTH:
            sys.exit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        if getpass.getpass("Repeat it: ") != password:
            sys.exit("The passwords don't match.")

        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user["id"]))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
        print(f"Password updated for {email}.")


if __name__ == "__main__":
    main()
