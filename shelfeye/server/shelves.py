"""Shelves set up on the dashboard's Settings page.

A shelf is a name ("Shelf 1", "Drinks aisle") plus, optionally, the camera
(node_id) that watches it. The dashboard uses the list for its shelf filters
and shows shelf names in place of camera IDs.
"""
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from auth import current_user
from db import api_doc, database

MAX_NAME_LENGTH = 60

router = APIRouter(prefix="/api/shelves", dependencies=[Depends(current_user)])


class ShelfBody(BaseModel):
    name: str
    node_id: str | None = None


class ShelfUpdate(BaseModel):
    name: str | None = None
    node_id: str | None = None


def _clean_name(name):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Give the shelf a name.")
    if len(name) > MAX_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"Shelf names can be at most {MAX_NAME_LENGTH} characters.")
    return name


def _clean_node_id(node_id):
    return (node_id or "").strip() or None  # empty means "no camera"


def _clash(node_id, shelf_id=None):
    """Explain a unique-index clash: the camera is taken, or else the name is."""
    if node_id and database().shelves.find_one({"node_id": node_id, "_id": {"$ne": shelf_id}}, {"_id": 1}):
        detail = "That camera is already assigned to another shelf."
    else:
        detail = "A shelf with that name already exists."
    return HTTPException(status_code=409, detail=detail)


def _object_id(shelf_id):
    try:
        return ObjectId(shelf_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=404, detail="Shelf not found")


def _shelf(doc):
    if not doc:
        raise HTTPException(status_code=404, detail="Shelf not found")
    doc = api_doc(doc, id_field="id")
    doc.pop("name_key", None)
    return doc


@router.get("")
def list_shelves():
    return [_shelf(doc) for doc in database().shelves.find().sort("_id", ASCENDING)]  # oldest first


@router.post("", status_code=201)
def create_shelf(body: ShelfBody):
    name = _clean_name(body.name)
    shelf = {
        "name": name,
        "name_key": name.lower(),
        "node_id": _clean_node_id(body.node_id),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        database().shelves.insert_one(shelf)
    except DuplicateKeyError:
        raise _clash(shelf["node_id"])
    return _shelf(shelf)


@router.patch("/{shelf_id}")
def update_shelf(shelf_id: str, body: ShelfUpdate):
    changes = {}
    sent = body.model_fields_set  # node_id: null means "remove the camera", so check what was sent
    if "name" in sent and body.name is not None:
        changes["name"] = _clean_name(body.name)
        changes["name_key"] = changes["name"].lower()
    if "node_id" in sent:
        changes["node_id"] = _clean_node_id(body.node_id)
    shelves = database().shelves
    _id = _object_id(shelf_id)
    if not changes:
        return _shelf(shelves.find_one({"_id": _id}))
    try:
        doc = shelves.find_one_and_update({"_id": _id}, {"$set": changes}, return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:
        raise _clash(changes.get("node_id"), _id)
    return _shelf(doc)


@router.delete("/{shelf_id}", status_code=204)
def delete_shelf(shelf_id: str):
    # The camera's stock stays; it just shows under its camera ID again.
    if not database().shelves.delete_one({"_id": _object_id(shelf_id)}).deleted_count:
        raise HTTPException(status_code=404, detail="Shelf not found")
    return Response(status_code=204)
