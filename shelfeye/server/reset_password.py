"""Set a new password for a dashboard account, or list the accounts.

Run anywhere MONGODB_URI is set (your computer, or Render's Shell tab):
    python reset_password.py                 # list accounts
    python reset_password.py you@example.com # set a new password (asked for, not echoed)

Logs the account out everywhere, so the new password is needed on every device.
"""
import getpass
import sys

from auth import MIN_PASSWORD_LENGTH, find_user_by_email, hash_password
from db import MONGODB_DB, MONGODB_URI, database


def main():
    if not MONGODB_URI:
        sys.exit("Set MONGODB_URI first (the same value as on Render).")
    db = database()
    if len(sys.argv) < 2:
        users = list(db.users.find({}, {"email": 1, "created_at": 1}).sort("created_at", 1))
        print(f"Accounts in MongoDB database '{MONGODB_DB}':" if users else "No accounts yet.")
        for user in users:
            print(f"  {user['email']}  (created {user['created_at']})")
        return

    user = find_user_by_email(sys.argv[1])
    if not user:
        sys.exit(f"No account for {sys.argv[1]}. Register it on the dashboard instead.")

    password = getpass.getpass("New password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if getpass.getpass("Repeat it: ") != password:
        sys.exit("The passwords don't match.")

    db.users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": hash_password(password)}})
    db.sessions.delete_many({"user_id": str(user["_id"])})
    print(f"Password updated for {user['email']}.")


if __name__ == "__main__":
    main()
