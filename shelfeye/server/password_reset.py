"""Forgot password: email a one-time link, then set a new password with it.

1. POST /api/auth/forgot-password {email}
   Always answers the same way, so it doesn't reveal which emails have accounts.
   If the account exists, it emails a link to DASHBOARD_URL/reset-password?token=...
2. POST /api/auth/reset-password {token, password}
   Sets the new password, logs the account out everywhere, and logs this browser in.

Links work once and expire after RESET_MINUTES. Only the token's SHA-256 hash is
stored (collection `password_resets`), like login sessions.
"""
import html
import os
import secrets
from datetime import timedelta

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, HTTPException, Response
from pydantic import BaseModel

from auth import (
    EMAIL_PATTERN, MIN_PASSWORD_LENGTH, _now, _start_session, _token_hash, find_user_by_email, hash_password,
    public_user,
)
from db import database
from mailer import send_email

RESET_MINUTES = 60
RESEND_SECONDS = 60  # at most one email per account per minute

router = APIRouter(prefix="/api/auth")


class ForgotBody(BaseModel):
    email: str


class ResetBody(BaseModel):
    token: str
    password: str


def _dashboard_url():
    return os.environ.get("DASHBOARD_URL", "http://localhost:3000").rstrip("/")


def _send_reset_email(user, link):
    name = user["name"]
    text = (
        f"Hi {name},\n\n"
        f"Someone asked to reset the password for your ShelfEye account. To choose a new one, open this link:\n\n"
        f"{link}\n\n"
        f"The link works once and expires in {RESET_MINUTES} minutes.\n"
        f"If you didn't ask for this, ignore this email; your password stays the same.\n"
    )
    page = f"""\
<div style="font-family:Segoe UI,Arial,sans-serif;max-width:480px;margin:0 auto;color:#1f1a16">
  <h2 style="margin:0 0 12px">Reset your ShelfEye password</h2>
  <p>Hi {html.escape(name)},</p>
  <p>Someone asked to reset the password for your ShelfEye account. Choose a new one here:</p>
  <p style="margin:24px 0">
    <a href="{html.escape(link)}" style="background:#f97316;color:#fff;padding:11px 18px;border-radius:8px;
       text-decoration:none;font-weight:600;display:inline-block">Choose a new password</a>
  </p>
  <p style="color:#74675d;font-size:13px">The link works once and expires in {RESET_MINUTES} minutes.
     If you didn't ask for this, ignore this email; your password stays the same.</p>
  <p style="color:#74675d;font-size:12px;word-break:break-all">If the button doesn't work, copy this link:<br>{html.escape(link)}</p>
</div>"""
    send_email(user["email"], name, "Reset your ShelfEye password", text, page)


@router.post("/forgot-password")
def forgot_password(body: ForgotBody, background: BackgroundTasks):
    email = body.email.strip().lower()
    if not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address")

    user = find_user_by_email(email)
    if user:
        user_id = str(user["_id"])
        resets = database().password_resets
        recent = resets.find_one({"user_id": user_id, "created_at": {"$gt": _now() - timedelta(seconds=RESEND_SECONDS)}})
        if not recent:
            token = secrets.token_urlsafe(32)
            resets.delete_many({"user_id": user_id})  # only the newest link works
            resets.insert_one({
                "_id": _token_hash(token),
                "user_id": user_id,
                "created_at": _now(),
                "expires_at": _now() + timedelta(minutes=RESET_MINUTES),
            })
            # Sent after the reply, so the reply takes as long whether or not the account exists.
            background.add_task(_send_reset_email, user, f"{_dashboard_url()}/reset-password?token={token}")
    return {"status": "ok"}


@router.post("/reset-password")
def reset_password(body: ResetBody, response: Response):
    if len(body.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    db = database()
    # Deleting it as we read it makes the link single-use, even if clicked twice at once.
    reset = db.password_resets.find_one_and_delete({"_id": _token_hash(body.token)})
    if not reset or reset["expires_at"] < _now():
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Please request a new one.")

    user = db.users.find_one_and_update(
        {"_id": ObjectId(reset["user_id"])},
        {"$set": {"password_hash": hash_password(body.password)}},
    )
    if not user:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Please request a new one.")
    db.sessions.delete_many({"user_id": reset["user_id"]})  # log out every other device
    _start_session(response, reset["user_id"])
    return public_user(user)
