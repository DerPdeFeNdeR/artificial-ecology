"""SQLite persistence for runs, events, and snapshots."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .engine import Event, SimulationEngine


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                seed INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                tick INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                tick INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                PRIMARY KEY (run_id, tick)
            );
            """
        )
        self.connection.commit()

    def create_run(self, run_id: str, seed: int, metadata: dict[str, Any] | None = None) -> None:
        self.connection.execute(
            "INSERT INTO runs (run_id, seed, metadata_json) VALUES (?, ?, ?)",
            (run_id, seed, json.dumps(metadata or {}, sort_keys=True)),
        )
        self.connection.commit()

    def save_tick(self, run_id: str, engine: SimulationEngine, events: Iterable[Event]) -> None:
        events = tuple(events)
        with self.connection:
            self.connection.executemany(
                "INSERT INTO events (sequence, run_id, tick, event_type, payload_json) VALUES (?, ?, ?, ?, ?)",
                [
                    (event.sequence, run_id, event.tick, event.event_type, json.dumps(event.payload, sort_keys=True))
                    for event in events
                ],
            )
            self.connection.execute(
                "INSERT OR REPLACE INTO snapshots (run_id, tick, state_json) VALUES (?, ?, ?)",
                (run_id, engine.world.tick, engine.snapshot_json()),
            )

    def events_for_run(self, run_id: str) -> list[Event]:
        rows = self.connection.execute(
            "SELECT sequence, tick, event_type, payload_json FROM events WHERE run_id = ? ORDER BY sequence",
            (run_id,),
        )
        return [
            Event(row["sequence"], row["tick"], row["event_type"], json.loads(row["payload_json"]))
            for row in rows
        ]

    def latest_snapshot(self, run_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT state_json FROM snapshots WHERE run_id = ? ORDER BY tick DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        return json.loads(row["state_json"]) if row else None

    def close(self) -> None:
        self.connection.close()
