"""MongoDB storage for the ShelfEye server.

Everything lives in MongoDB, so redeploying or restarting the server loses nothing.
Set MONGODB_URI to the cluster's connection string (password filled in);
MONGODB_DB picks the database (default "shelfeye").

Collections:
  users      {_id, name, email, password_hash, created_at}       dashboard accounts
  sessions   {_id: token hash, user_id, expires_at}              logins (removed by MongoDB once expired)
  nodes      {_id: node_id, last_seen, live_view}                cameras
  readings   {_id: reading_id, node_id, captured_at, image, received_at}
  inventory  {node_id, name, count, label_text, updated_at}      latest count per product
  events     {_id: "<reading_id>:<name>", node_id, name, previous, current, delta, captured_at}
  shelves    {_id, name, name_key, node_id, created_at}
  settings   {_id: key, value}
"""
import os
import threading

from fastapi import HTTPException
from pymongo import ASCENDING, DESCENDING, MongoClient

MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DB = os.environ.get("MONGODB_DB", "shelfeye")

_lock = threading.Lock()
_database = None


def database():
    """The ShelfEye database, connected (and indexes created) on first use."""
    global _database
    with _lock:
        if _database is None:
            if not MONGODB_URI:
                raise HTTPException(status_code=503, detail="The server's database isn't set up (MONGODB_URI is missing).")
            client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000, tz_aware=True, appname="shelfeye")
            db = client[MONGODB_DB]
            _create_indexes(db)
            _database = db
        return _database


def _create_indexes(db):
    db.users.create_index("email", unique=True)
    db.sessions.create_index("expires_at", expireAfterSeconds=0)
    db.inventory.create_index([("node_id", ASCENDING), ("name", ASCENDING)], unique=True)
    db.events.create_index([("captured_at", DESCENDING)])
    # Shelf names are unique ignoring case (name_key is the lowercased name);
    # each camera belongs to at most one shelf.
    db.shelves.create_index("name_key", unique=True)
    db.shelves.create_index("node_id", unique=True, partialFilterExpression={"node_id": {"$type": "string"}})


def api_doc(doc, id_field=None):
    """A document as the API returns it: `_id` dropped, or returned as a string under `id_field`."""
    doc = dict(doc)
    _id = doc.pop("_id")
    if id_field:
        doc[id_field] = str(_id)
    return doc
