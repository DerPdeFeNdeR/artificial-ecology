"""SQLite persistence for runs, events, and snapshots."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

from .domain import ActionProposal, Position
from .engine import Event, SimulationEngine


def _proposal_to_dict(proposal: ActionProposal) -> dict[str, Any]:
    return {
        "actor_id": proposal.actor_id,
        "action_type": proposal.action_type,
        "target": (
            {"x": proposal.target.x, "y": proposal.target.y}
            if proposal.target is not None
            else None
        ),
        "recipient_id": proposal.recipient_id,
        "message": proposal.message,
    }


def _proposal_from_dict(data: dict[str, Any]) -> ActionProposal:
    target = data.get("target")
    return ActionProposal(
        actor_id=data["actor_id"],
        action_type=data["action_type"],
        target=Position(target["x"], target["y"]) if target else None,
        recipient_id=data.get("recipient_id"),
        message=data.get("message"),
    )


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
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
                sequence INTEGER NOT NULL,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                tick INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence)
            );
            CREATE TABLE IF NOT EXISTS decisions (
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                tick INTEGER NOT NULL,
                actor_id TEXT NOT NULL,
                proposal_json TEXT NOT NULL,
                PRIMARY KEY (run_id, tick, actor_id)
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
        with self._lock:
            self.connection.execute(
                "INSERT INTO runs (run_id, seed, metadata_json) VALUES (?, ?, ?)",
                (run_id, seed, json.dumps(metadata or {}, sort_keys=True)),
            )
            self.connection.commit()

    def save_initial_snapshot(self, run_id: str, engine: SimulationEngine) -> None:
        with self._lock:
            self.connection.execute(
                "INSERT OR REPLACE INTO snapshots (run_id, tick, state_json) VALUES (?, ?, ?)",
                (run_id, engine.world.tick, engine.snapshot_json()),
            )
            self.connection.commit()

    def save_tick(
        self,
        run_id: str,
        engine: SimulationEngine,
        events: Iterable[Event],
        proposals: Iterable[ActionProposal] = (),
    ) -> None:
        events = tuple(events)
        proposals = tuple(proposals)
        with self._lock, self.connection:
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
            self.connection.executemany(
                "INSERT OR REPLACE INTO decisions (run_id, tick, actor_id, proposal_json) VALUES (?, ?, ?, ?)",
                [
                    (run_id, engine.world.tick, proposal.actor_id, json.dumps(_proposal_to_dict(proposal), sort_keys=True))
                    for proposal in proposals
                ],
            )

    def events_for_run(self, run_id: str) -> list[Event]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT sequence, tick, event_type, payload_json FROM events WHERE run_id = ? ORDER BY sequence",
                (run_id,),
            )
            return [
                Event(row["sequence"], row["tick"], row["event_type"], json.loads(row["payload_json"]))
                for row in rows
            ]

    def latest_snapshot(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT state_json FROM snapshots WHERE run_id = ? ORDER BY tick DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            return json.loads(row["state_json"]) if row else None

    def initial_snapshot(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT state_json FROM snapshots WHERE run_id = ? ORDER BY tick ASC LIMIT 1",
                (run_id,),
            ).fetchone()
            return json.loads(row["state_json"]) if row else None

    def decisions_for_run(self, run_id: str) -> dict[int, tuple[ActionProposal, ...]]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT tick, proposal_json FROM decisions WHERE run_id = ? ORDER BY tick, actor_id",
                (run_id,),
            )
            decisions: dict[int, list[ActionProposal]] = {}
            for row in rows:
                decisions.setdefault(row["tick"], []).append(_proposal_from_dict(json.loads(row["proposal_json"])))
            return {tick: tuple(proposals) for tick, proposals in decisions.items()}

    def ticks_for_run(self, run_id: str) -> list[int]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT tick FROM snapshots WHERE run_id = ? ORDER BY tick",
                (run_id,),
            )
            return [row["tick"] for row in rows]

    def close(self) -> None:
        with self._lock:
            self.connection.close()


class ReplayMismatch(AssertionError):
    """Raised when replayed events differ from the recorded event trace."""


def verify_replay(store: SQLiteStore, run_id: str) -> SimulationEngine:
    """Replay a run from its initial snapshot and verify every recorded event."""
    initial_snapshot = store.initial_snapshot(run_id)
    if initial_snapshot is None:
        raise ValueError(f"Run {run_id!r} has no initial snapshot")

    engine = SimulationEngine.from_snapshot(initial_snapshot)
    recorded_events = store.events_for_run(run_id)
    events_by_tick: dict[int, list[Event]] = {}
    for event in recorded_events:
        events_by_tick.setdefault(event.tick, []).append(event)

    decisions = store.decisions_for_run(run_id)
    for tick in store.ticks_for_run(run_id):
        if tick == engine.world.tick:
            continue
        replayed = engine.step(decisions.get(tick, ()))
        expected = tuple(events_by_tick.get(tick, ()))
        if [event.to_dict() for event in replayed] != [event.to_dict() for event in expected]:
            raise ReplayMismatch(f"Replay diverged at tick {tick}")
    return engine
