"""ShelfEye server: receives readings from shelf cameras and serves them to the dashboard API.

Run with:  SHELFEYE_DEVICE_TOKEN=change-me uvicorn app:app --host 0.0.0.0 --port 8000
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header
from pydantic import BaseModel

from auth import check_device_token, current_user, router as auth_router
from db import connect, init_db
from live import router as live_router
from settings import read_settings, router as settings_router
from shelves import router as shelves_router


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
    live_view: bool = False  # the camera relays its live view through this server


init_db()
app = FastAPI(title="ShelfEye")
app.include_router(auth_router)
app.include_router(shelves_router)
app.include_router(settings_router)
app.include_router(live_router)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.post("/api/nodes/{node_id}/heartbeat")
def post_heartbeat(node_id: str, heartbeat: Heartbeat, authorization: str = Header("")):
    check_device_token(authorization)
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO nodes (node_id, last_seen, live_view) VALUES (?, ?, ?) "
            "ON CONFLICT(node_id) DO UPDATE SET last_seen = excluded.last_seen, live_view = excluded.live_view",
            (node_id, now_iso(), int(heartbeat.live_view)),
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
        rows = conn.execute("SELECT node_id, last_seen, live_view FROM nodes ORDER BY node_id").fetchall()
    return [{**dict(row), "live_view": bool(row["live_view"])} for row in rows]
