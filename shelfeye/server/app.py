"""ShelfEye server: receives readings from shelf cameras and serves them to the dashboard API.

Run with:
    SHELFEYE_DEVICE_TOKEN=change-me MONGODB_URI=mongodb+srv://... uvicorn app:app --host 0.0.0.0 --port 8000
"""
import logging
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pymongo import ASCENDING, DESCENDING, UpdateOne
from pymongo.errors import PyMongoError

from auth import check_device_token, current_user, router as auth_router
from db import api_doc, database
from live import router as live_router
from password_reset import router as password_reset_router
from settings import read_settings, router as settings_router
from shelves import router as shelves_router

log = logging.getLogger("uvicorn.error")


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


app = FastAPI(title="ShelfEye")
app.include_router(auth_router)
app.include_router(shelves_router)
app.include_router(settings_router)
app.include_router(live_router)
app.include_router(password_reset_router)


@app.exception_handler(PyMongoError)
def database_unavailable(request: Request, exc: PyMongoError):
    log.error("MongoDB error on %s: %s", request.url.path, exc)
    # 503 tells the cameras to keep the reading and retry later.
    return JSONResponse(status_code=503, content={"detail": "Can't reach the database right now. Please try again."})


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.post("/api/nodes/{node_id}/heartbeat")
def post_heartbeat(node_id: str, heartbeat: Heartbeat, authorization: str = Header("")):
    check_device_token(authorization)
    db = database()
    db.nodes.update_one(
        {"_id": node_id}, {"$set": {"last_seen": now_iso(), "live_view": heartbeat.live_view}}, upsert=True
    )
    # The camera applies these, so dashboard changes reach it within one heartbeat.
    return {"status": "ok", "settings": read_settings(db)}


@app.post("/api/nodes/{node_id}/readings")
def post_reading(node_id: str, reading: Reading, authorization: str = Header("")):
    check_device_token(authorization)
    db = database()
    if db.readings.find_one({"_id": reading.reading_id}, {"_id": 1}):
        return {"status": "duplicate"}  # device retried a reading we already have

    # Every write below can safely be repeated, so if one fails part-way the
    # device just sends the reading again and it completes.
    # Each reading is a full snapshot of the shelf, so it replaces the node's inventory.
    names = [i.name for i in reading.items]
    if reading.items:
        db.inventory.bulk_write([
            UpdateOne(
                {"node_id": node_id, "name": i.name},
                {"$set": {"count": i.count, "label_text": i.label_text, "updated_at": reading.captured_at}},
                upsert=True,
            )
            for i in reading.items
        ])
    db.inventory.delete_many({"node_id": node_id, "name": {"$nin": names}})
    if reading.changes:
        db.events.bulk_write([
            UpdateOne(
                {"_id": f"{reading.reading_id}:{c.name}"},
                {"$set": {"node_id": node_id, **c.model_dump(), "captured_at": reading.captured_at}},
                upsert=True,
            )
            for c in reading.changes
        ])
    received_at = now_iso()
    db.nodes.update_one({"_id": node_id}, {"$set": {"last_seen": received_at}}, upsert=True)
    db.readings.update_one(
        {"_id": reading.reading_id},
        {"$set": {"node_id": node_id, "captured_at": reading.captured_at, "image": reading.image,
                  "received_at": received_at}},
        upsert=True,
    )
    return {"status": "ok"}


@app.get("/api/inventory", dependencies=[Depends(current_user)])
def get_inventory():
    rows = database().inventory.find().sort([("node_id", ASCENDING), ("name", ASCENDING)])
    return [api_doc(row) for row in rows]


@app.get("/api/events", dependencies=[Depends(current_user)])
def get_events(limit: int = 50):
    rows = database().events.find().sort([("captured_at", DESCENDING), ("_id", ASCENDING)]).limit(max(1, min(limit, 500)))
    return [api_doc(row, id_field="id") for row in rows]


@app.get("/api/nodes", dependencies=[Depends(current_user)])
def get_nodes():
    rows = database().nodes.find().sort("_id", ASCENDING)
    return [{"node_id": row["_id"], "last_seen": row["last_seen"], "live_view": bool(row.get("live_view"))} for row in rows]
