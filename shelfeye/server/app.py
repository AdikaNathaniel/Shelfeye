"""ShelfEye server: receives readings from shelf cameras and serves them to the dashboard API.

Run with:  SHELFEYE_DEVICE_TOKEN=change-me uvicorn app:app --host 0.0.0.0 --port 8000
"""
import logging
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import requests
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import current_user, router as auth_router
from db import connect, init_db
from settings import read_settings, router as settings_router
from shelves import router as shelves_router

log = logging.getLogger("uvicorn.error")

DEVICE_TOKEN = os.environ.get("SHELFEYE_DEVICE_TOKEN", "")


class Item(BaseModel):
    name: str
    count: int
    label_text: str = ""


class Change(BaseModel):
    name: str
    previous: int
    current: int
    delta: int


class Reading(BaseModel):
    reading_id: str
    captured_at: str
    image: str = ""
    items: list[Item]
    changes: list[Change] = []


class Heartbeat(BaseModel):
    live_view_url: str | None = None


init_db()
app = FastAPI(title="ShelfEye")
app.include_router(auth_router)
app.include_router(shelves_router)
app.include_router(settings_router)


def check_device_token(authorization):
    if not DEVICE_TOKEN or not secrets.compare_digest(authorization, f"Bearer {DEVICE_TOKEN}"):
        raise HTTPException(status_code=401, detail="Invalid device token")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.post("/api/nodes/{node_id}/heartbeat")
def post_heartbeat(node_id: str, heartbeat: Heartbeat, authorization: str = Header("")):
    check_device_token(authorization)
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO nodes (node_id, last_seen, live_view_url) VALUES (?, ?, ?) "
            "ON CONFLICT(node_id) DO UPDATE SET last_seen = excluded.last_seen, live_view_url = excluded.live_view_url",
            (node_id, now_iso(), heartbeat.live_view_url),
        )
        # The camera applies these, so dashboard changes reach it within one heartbeat.
        return {"status": "ok", "settings": read_settings(conn)}


@app.post("/api/nodes/{node_id}/readings")
def post_reading(node_id: str, reading: Reading, authorization: str = Header("")):
    check_device_token(authorization)

    received_at = now_iso()
    with closing(connect()) as conn, conn:
        try:
            conn.execute(
                "INSERT INTO readings VALUES (?, ?, ?, ?, ?)",
                (reading.reading_id, node_id, reading.captured_at, reading.image, received_at),
            )
        except sqlite3.IntegrityError:
            return {"status": "duplicate"}  # device retried a reading we already have

        conn.execute(
            "INSERT INTO nodes (node_id, last_seen) VALUES (?, ?) "
            "ON CONFLICT(node_id) DO UPDATE SET last_seen = excluded.last_seen",
            (node_id, received_at),
        )
        # Each reading is a full snapshot of the shelf, so replace the node's inventory.
        conn.execute("DELETE FROM inventory WHERE node_id = ?", (node_id,))
        conn.executemany(
            "INSERT INTO inventory VALUES (?, ?, ?, ?, ?)",
            [(node_id, i.name, i.count, i.label_text, reading.captured_at) for i in reading.items],
        )
        conn.executemany(
            "INSERT INTO events (node_id, name, previous, current, delta, captured_at) VALUES (?, ?, ?, ?, ?, ?)",
            [(node_id, c.name, c.previous, c.current, c.delta, reading.captured_at) for c in reading.changes],
        )
    return {"status": "ok"}


@app.get("/api/inventory", dependencies=[Depends(current_user)])
def get_inventory():
    with closing(connect()) as conn:
        rows = conn.execute("SELECT * FROM inventory ORDER BY node_id, name").fetchall()
    return [dict(row) for row in rows]


@app.get("/api/events", dependencies=[Depends(current_user)])
def get_events(limit: int = 50):
    with closing(connect()) as conn:
        rows = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (min(limit, 500),)).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/nodes", dependencies=[Depends(current_user)])
def get_nodes():
    with closing(connect()) as conn:
        rows = conn.execute("SELECT * FROM nodes ORDER BY node_id").fetchall()
    return [dict(row) for row in rows]


@app.get("/api/nodes/{node_id}/stream", dependencies=[Depends(current_user)])
def get_stream(node_id: str):
    """Relay a camera's live view, so viewers never need to reach the Pi directly."""
    with closing(connect()) as conn:
        row = conn.execute("SELECT live_view_url FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
    if not row or not row["live_view_url"]:
        raise HTTPException(status_code=404, detail="This camera has no live view")
    try:
        upstream = requests.get(row["live_view_url"], stream=True, timeout=(5, 30))
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="Camera unreachable")
    if upstream.status_code != 200:
        upstream.close()
        raise HTTPException(status_code=503, detail="Camera busy or unavailable")

    def relay():
        try:
            # A fixed chunk size; chunk_size=None would wait for the never-ending stream to finish.
            yield from upstream.iter_content(chunk_size=8192)
        except requests.RequestException as e:
            # The dashboard reconnects by itself; one line is enough here.
            log.warning("Live view from %s stopped: %s", node_id, e.__class__.__name__)
        finally:
            upstream.close()  # tells the Pi the viewer left, so counting resumes

    return StreamingResponse(
        relay(),
        media_type=upstream.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=FRAME"),
        headers={"Cache-Control": "no-cache, no-store"},
    )
