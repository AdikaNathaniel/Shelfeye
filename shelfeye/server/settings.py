"""Settings changed on the dashboard and applied by the shelf cameras.

Cameras receive these in the reply to their heartbeat (every 5 minutes) and
keep the last values on their SD card, so they still apply when offline.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user
from db import database

DEFAULT_KEEP_IMAGES_DAYS = 365
MAX_KEEP_IMAGES_DAYS = 3650

router = APIRouter(prefix="/api/settings", dependencies=[Depends(current_user)])


class SettingsUpdate(BaseModel):
    keep_images_days: int


def read_settings(db):
    doc = db.settings.find_one({"_id": "keep_images_days"})
    return {"keep_images_days": int(doc["value"]) if doc else DEFAULT_KEEP_IMAGES_DAYS}


@router.get("")
def get_settings():
    return read_settings(database())


@router.patch("")
def update_settings(body: SettingsUpdate):
    days = body.keep_images_days
    if not 1 <= days <= MAX_KEEP_IMAGES_DAYS:
        raise HTTPException(status_code=400, detail=f"Enter a number of days from 1 to {MAX_KEEP_IMAGES_DAYS}.")
    db = database()
    db.settings.update_one({"_id": "keep_images_days"}, {"$set": {"value": days}}, upsert=True)
    return read_settings(db)
