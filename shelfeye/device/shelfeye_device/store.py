"""Local SQLite storage on the SD card: current counts plus an outbox of unsent readings."""
import json
import sqlite3


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path))
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS counts (
                name TEXT PRIMARY KEY,
                count INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

    def current_counts(self):
        return dict(self.db.execute("SELECT name, count FROM counts ORDER BY name"))

    def apply_reading(self, items, captured_at):
        """Save new counts and return what changed since the previous reading.

        Products missing from the new reading are treated as count 0.
        """
        previous = self.current_counts()
        current = {item["name"]: item["count"] for item in items}
        changes = []
        with self.db:
            for name in sorted(set(previous) | set(current)):
                before, after = previous.get(name, 0), current.get(name, 0)
                if before != after:
                    changes.append({"name": name, "previous": before, "current": after, "delta": after - before})
                self.db.execute(
                    "INSERT INTO counts (name, count, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET count = excluded.count, updated_at = excluded.updated_at",
                    (name, after, captured_at),
                )
        return changes

    def queue(self, payload):
        with self.db:
            self.db.execute(
                "INSERT INTO outbox (id, payload, created_at) VALUES (?, ?, ?)",
                (payload["reading_id"], json.dumps(payload), payload["captured_at"]),
            )

    def pending(self):
        return list(self.db.execute("SELECT id, payload FROM outbox ORDER BY created_at"))

    def remove(self, reading_id):
        with self.db:
            self.db.execute("DELETE FROM outbox WHERE id = ?", (reading_id,))
