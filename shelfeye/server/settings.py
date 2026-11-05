"""Settings changed on the dashboard and applied by the shelf cameras.

Cameras receive these in the reply to their heartbeat (every 5 minutes) and
keep the last values on their SD card, so they still apply when offline.
"""
from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user
from db import connect

DEFAULT_KEEP_IMAGES_DAYS = 365
MAX_KEEP_IMAGES_DAYS = 3650

router = APIRouter(prefix="/api/settings", dependencies=[Depends(current_user)])


class SettingsUpdate(BaseModel):
    keep_images_days: int


def read_settings(conn):
    row = conn.execute("SELECT value FROM settings WHERE key = 'keep_images_days'").fetchone()
    return {"keep_images_days": int(row["value"]) if row else DEFAULT_KEEP_IMAGES_DAYS}


@router.get("")
def get_settings():
    with closing(connect()) as conn:
        return read_settings(conn)


@router.patch("")
def update_settings(body: SettingsUpdate):
    days = body.keep_images_days
    if not 1 <= days <= MAX_KEEP_IMAGES_DAYS:
        raise HTTPException(status_code=400, detail=f"Enter a number of days from 1 to {MAX_KEEP_IMAGES_DAYS}.")
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('keep_images_days', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(days),),
        )
        return read_settings(conn)
