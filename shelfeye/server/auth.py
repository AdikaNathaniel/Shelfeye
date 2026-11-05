"""User accounts for the dashboard: register, log in, log out.

Accounts live in MongoDB (users_db.py); login sessions live in SQLite.
Passwords are hashed with scrypt. A login creates a random session token that
is kept in an httpOnly cookie; only its SHA-256 hash is stored.
"""
import hashlib
import os
import re
import secrets
from contextlib import closing
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel

import users_db
from db import connect

COOKIE_NAME = "shelfeye_session"
SESSION_DAYS = 30
MIN_PASSWORD_LENGTH = 8
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter(prefix="/api/auth")

# Shared by all shelf cameras; set the same value on the server and on each Pi.
DEVICE_TOKEN = os.environ.get("SHELFEYE_DEVICE_TOKEN", "")


def check_device_token(authorization):
    """For routes only the shelf cameras call."""
    if not DEVICE_TOKEN or not secrets.compare_digest(authorization, f"Bearer {DEVICE_TOKEN}"):
        raise HTTPException(status_code=401, detail="Invalid device token")


class RegisterBody(BaseModel):
    name: str
    email: str
    password: str


class LoginBody(BaseModel):
    email: str
    password: str


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return secrets.compare_digest(digest.hex(), digest_hex)


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def _start_session(response, user_id):
    token = secrets.token_urlsafe(32)
    expires_at = (_now() + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (_token_hash(token), user_id, expires_at),
        )
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/"
    )


def current_user(shelfeye_session: str | None = Cookie(None)):
    """Dependency for routes that need a logged-in user."""
    if not shelfeye_session:
        raise HTTPException(status_code=401, detail="Please log in")
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT user_id, expires_at FROM sessions WHERE token_hash = ?", (_token_hash(shelfeye_session),)
        ).fetchone()
    if not row or row["expires_at"] < _now().isoformat(timespec="seconds"):
        raise HTTPException(status_code=401, detail="Your session has expired, please log in again")
    user = users_db.find_by_id(row["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="Your session has expired, please log in again")
    return users_db.public(user)


@router.post("/register", status_code=201)
def register(body: RegisterBody, response: Response):
    name = body.name.strip()
    email = body.email.strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="Please enter your name")
    if not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address")
    if len(body.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

    try:
        user_id = users_db.create_user(name, email, hash_password(body.password), _now().isoformat(timespec="seconds"))
    except users_db.EmailTaken:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    _start_session(response, user_id)
    return {"id": user_id, "name": name, "email": email}


@router.post("/login")
def login(body: LoginBody, response: Response):
    email = body.email.strip().lower()
    user = users_db.find_by_email(email)
    # Same message either way, so the form doesn't reveal which emails have accounts.
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    user_id = str(user["_id"])
    _start_session(response, user_id)
    return users_db.public(user)


@router.post("/logout")
def logout(response: Response, shelfeye_session: str | None = Cookie(None)):
    if shelfeye_session:
        with closing(connect()) as conn, conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(shelfeye_session),))
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user
