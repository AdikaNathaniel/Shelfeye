"""Dashboard user accounts, stored in MongoDB so they survive server redeploys.

Each user is one document in the `users` collection:
    {_id, name, email, password_hash, created_at}
Everything else (stock, cameras, shelves, login sessions) stays in SQLite.

Set MONGODB_URI to the cluster's connection string (with the password filled in).
MONGODB_DB picks the database name (default "shelfeye").
"""
import os
import threading
from contextlib import contextmanager

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DB = os.environ.get("MONGODB_DB", "shelfeye")

_lock = threading.Lock()
_collection = None


class EmailTaken(Exception):
    pass


def _users():
    global _collection
    with _lock:
        if _collection is None:
            if not MONGODB_URI:
                raise HTTPException(status_code=503, detail="User accounts aren't set up yet (MONGODB_URI is missing).")
            client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000, tz_aware=True, appname="shelfeye")
            collection = client[MONGODB_DB]["users"]
            collection.create_index("email", unique=True)
            _collection = collection
        return _collection


@contextmanager
def _errors():
    """Turn database outages into a clear message instead of a 500."""
    try:
        yield
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Can't reach the user database right now. Please try again.")


def create_user(name, email, password_hash, created_at):
    """Returns the new user's id. Raises EmailTaken if the email is registered."""
    with _errors():
        try:
            result = _users().insert_one(
                {"name": name, "email": email, "password_hash": password_hash, "created_at": created_at}
            )
        except DuplicateKeyError:
            raise EmailTaken()
    return str(result.inserted_id)


def find_by_email(email):
    with _errors():
        return _users().find_one({"email": email})


def find_by_id(user_id):
    try:
        object_id = ObjectId(user_id)
    except (InvalidId, TypeError):
        return None  # e.g. a session from before accounts moved to MongoDB
    with _errors():
        return _users().find_one({"_id": object_id})


def list_users():
    with _errors():
        return list(_users().find({}, {"email": 1, "created_at": 1}).sort("created_at", 1))


def set_password_hash(user_id, password_hash):
    with _errors():
        _users().update_one({"_id": ObjectId(user_id)}, {"$set": {"password_hash": password_hash}})


def public(user):
    """The fields the dashboard may see."""
    return {"id": str(user["_id"]), "name": user["name"], "email": user["email"]}
