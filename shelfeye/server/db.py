"""SQLite storage for the ShelfEye server."""
import os
import sqlite3
from contextlib import closing

DB_PATH = os.environ.get("SHELFEYE_DB", "shelfeye.db")


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(connect()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                last_seen TEXT NOT NULL,
                live_view INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS readings (
                reading_id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                image TEXT NOT NULL,
                received_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS inventory (
                node_id TEXT NOT NULL,
                name TEXT NOT NULL,
                count INTEGER NOT NULL,
                label_text TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (node_id, name)
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,  -- a MongoDB user id (see users_db.py)
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                name TEXT NOT NULL,
                previous INTEGER NOT NULL,
                current INTEGER NOT NULL,
                delta INTEGER NOT NULL,
                captured_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shelves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                node_id TEXT UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        # Databases from older versions lack this column. (Their unused
        # live_view_url column is from before live view went through the server.)
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(nodes)")]
        if "live_view" not in columns:
            conn.execute("ALTER TABLE nodes ADD COLUMN live_view INTEGER NOT NULL DEFAULT 0")
        conn.commit()
