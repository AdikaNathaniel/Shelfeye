"""Set a new password for a dashboard account, or list the accounts.

Run anywhere MONGODB_URI is set (your computer, or Render's Shell tab):
    python reset_password.py                 # list accounts
    python reset_password.py you@example.com # set a new password (asked for, not echoed)

Logs the account out everywhere on this server, so the new password is needed on every device.
"""
import getpass
import sys
from contextlib import closing

import users_db
from auth import MIN_PASSWORD_LENGTH, hash_password
from db import connect, init_db


def main():
    if len(sys.argv) < 2:
        users = users_db.list_users()
        print(f"Accounts in MongoDB database '{users_db.MONGODB_DB}':" if users else "No accounts yet.")
        for user in users:
            print(f"  {user['email']}  (created {user['created_at']})")
        return

    email = sys.argv[1].strip().lower()
    user = users_db.find_by_email(email)
    if not user:
        sys.exit(f"No account for {email}. Register it on the dashboard instead.")

    password = getpass.getpass("New password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if getpass.getpass("Repeat it: ") != password:
        sys.exit("The passwords don't match.")

    user_id = str(user["_id"])
    users_db.set_password_hash(user_id, hash_password(password))
    init_db()
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    print(f"Password updated for {email}.")


if __name__ == "__main__":
    main()
