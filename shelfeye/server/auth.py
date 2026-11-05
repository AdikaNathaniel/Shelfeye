"""User accounts for the dashboard: register, log in, log out.

Accounts and sessions live in MongoDB (see db.py). Passwords are hashed with
scrypt. A login creates a random session token that is kept in an httpOnly
cookie; only its SHA-256 hash is stored.
"""
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from db import database

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


def public_user(user):
    """The fields the dashboard may see."""
    return {"id": str(user["_id"]), "name": user["name"], "email": user["email"]}


def find_user_by_email(email):
    return database().users.find_one({"email": email.strip().lower()})


def _start_session(response, user_id):
    token = secrets.token_urlsafe(32)
    database().sessions.insert_one(
        {"_id": _token_hash(token), "user_id": user_id, "expires_at": _now() + timedelta(days=SESSION_DAYS)}
    )
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/"
    )


def current_user(shelfeye_session: str | None = Cookie(None)):
    """Dependency for routes that need a logged-in user."""
    if not shelfeye_session:
        raise HTTPException(status_code=401, detail="Please log in")
    db = database()
    session = db.sessions.find_one({"_id": _token_hash(shelfeye_session)})
    user = None
    if session and session["expires_at"] > _now():
        try:
            user = db.users.find_one({"_id": ObjectId(session["user_id"])})
        except (InvalidId, TypeError):
            pass
    if not user:
        raise HTTPException(status_code=401, detail="Your session has expired, please log in again")
    return public_user(user)


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

    user = {
        "name": name,
        "email": email,
        "password_hash": hash_password(body.password),
        "created_at": _now().isoformat(timespec="seconds"),
    }
    try:
        database().users.insert_one(user)  # sets user["_id"]
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    _start_session(response, str(user["_id"]))
    return public_user(user)


@router.post("/login")
def login(body: LoginBody, response: Response):
    user = find_user_by_email(body.email)
    # Same message either way, so the form doesn't reveal which emails have accounts.
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    _start_session(response, str(user["_id"]))
    return public_user(user)


@router.post("/logout")
def logout(response: Response, shelfeye_session: str | None = Cookie(None)):
    if shelfeye_session:
        database().sessions.delete_one({"_id": _token_hash(shelfeye_session)})
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user
