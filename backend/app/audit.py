"""Append-only decision log in SQLite.

Every analyst decision is a new row; nothing is ever changed or removed.
  1. The database refuses UPDATE and DELETE on the table (triggers).
  2. Each row stores a hash of its content and of the previous row's hash, so a
     change made behind the API's back (e.g. with another SQLite tool) shows up
     in `verify()`.
This class has no update or delete method on purpose.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

DECISIONS = ("clear", "monitor", "educate", "convert", "restrict", "escalate")

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    analyst TEXT NOT NULL,
    risk REAL,
    band TEXT,
    created_at TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS decisions_no_update BEFORE UPDATE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS decisions_no_delete BEFORE DELETE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END;
"""
FIELDS = ("case_id", "decision", "reason", "analyst", "risk", "band", "created_at")
GENESIS = "0" * 64


def _hash(prev_hash: str, row: dict) -> str:
    payload = json.dumps({k: row[k] for k in FIELDS}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def append(self, case_id: str, decision: str, reason: str, analyst: str, risk, band) -> dict:
        if decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        row = {
            "case_id": case_id,
            "decision": decision,
            "reason": reason,
            "analyst": analyst,
            "risk": risk,
            "band": band,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        with self._connect() as db:
            last = db.execute("SELECT hash FROM decisions ORDER BY id DESC LIMIT 1").fetchone()
            prev = last["hash"] if last else GENESIS
            row["prev_hash"], row["hash"] = prev, _hash(prev, row)
            cur = db.execute(
                "INSERT INTO decisions (case_id, decision, reason, analyst, risk, band, "
                "created_at, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(row[k] for k in (*FIELDS, "prev_hash", "hash")),
            )
            row["id"] = cur.lastrowid
        return row

    def history(self, case_id: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM decisions", ()
        if case_id is not None:
            sql, args = sql + " WHERE case_id = ?", (case_id,)
        with self._connect() as db:
            return [dict(r) for r in db.execute(sql + " ORDER BY id", args)]

    def verify(self) -> bool:
        """True if no row was changed, removed or reordered behind the API's back."""
        prev = GENESIS
        for row in self.history():
            if row["prev_hash"] != prev or row["hash"] != _hash(prev, row):
                return False
            prev = row["hash"]
        return True
