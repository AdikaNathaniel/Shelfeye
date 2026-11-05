"""Shelves set up on the dashboard's Settings page.

A shelf is a name ("Shelf 1", "Drinks aisle") plus, optionally, the camera
(node_id) that watches it. The dashboard uses the list for its shelf filters
and shows shelf names in place of camera IDs.
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from auth import current_user
from db import connect

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


def _save(conn, sql, params):
    """Run an insert/update, turning unique-constraint clashes into a clear message."""
    try:
        return conn.execute(sql, params)
    except sqlite3.IntegrityError as e:
        if "node_id" in str(e):
            detail = "That camera is already assigned to another shelf."
        else:
            detail = "A shelf with that name already exists."
        raise HTTPException(status_code=409, detail=detail)


def _get(conn, shelf_id):
    row = conn.execute("SELECT * FROM shelves WHERE id = ?", (shelf_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Shelf not found")
    return dict(row)


@router.get("")
def list_shelves():
    with closing(connect()) as conn:
        rows = conn.execute("SELECT * FROM shelves ORDER BY id").fetchall()
    return [dict(row) for row in rows]


@router.post("", status_code=201)
def create_shelf(body: ShelfBody):
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(connect()) as conn, conn:
        cursor = _save(
            conn,
            "INSERT INTO shelves (name, node_id, created_at) VALUES (?, ?, ?)",
            (_clean_name(body.name), _clean_node_id(body.node_id), created_at),
        )
        return _get(conn, cursor.lastrowid)


@router.patch("/{shelf_id}")
def update_shelf(shelf_id: int, body: ShelfUpdate):
    sent = body.model_fields_set  # node_id: null means "remove the camera", so check what was sent
    with closing(connect()) as conn, conn:
        shelf = _get(conn, shelf_id)
        name = _clean_name(body.name) if "name" in sent and body.name is not None else shelf["name"]
        node_id = _clean_node_id(body.node_id) if "node_id" in sent else shelf["node_id"]
        _save(conn, "UPDATE shelves SET name = ?, node_id = ? WHERE id = ?", (name, node_id, shelf_id))
        return _get(conn, shelf_id)


@router.delete("/{shelf_id}", status_code=204)
def delete_shelf(shelf_id: int):
    # The camera's stock stays; it just shows under its camera ID again.
    with closing(connect()) as conn, conn:
        _get(conn, shelf_id)
        conn.execute("DELETE FROM shelves WHERE id = ?", (shelf_id,))
    return Response(status_code=204)
