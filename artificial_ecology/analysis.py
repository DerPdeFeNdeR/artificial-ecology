"""Post-run metrics that preserve the boundary between cognition and world truth."""

from __future__ import annotations

from collections import Counter
import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from .engine import Event


def summarize_intentions(
    intention_events: Iterable[dict[str, Any]],
    world_events: Iterable[Event] = (),
    model_calls: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Summarize recorded intention lifecycles without interpreting motives."""
    lifecycle = list(intention_events)
    physical = list(world_events)
    calls = list(model_calls)
    starts: dict[str, dict[str, Any]] = {}
    durations: list[int] = []
    terminal_reasons: Counter[str] = Counter()
    event_counts = Counter(event["event_type"] for event in lifecycle)
    repeated = 0
    previous_goal_by_inhabitant: dict[str, str] = {}

    for event in lifecycle:
        intention_id = event["intention_id"]
        if event["event_type"] == "intention_started":
            starts[intention_id] = event
            goal_key = json.dumps(event["payload"]["goal"], sort_keys=True)
            inhabitant_id = event["inhabitant_id"]
            if previous_goal_by_inhabitant.get(inhabitant_id) == goal_key:
                repeated += 1
            previous_goal_by_inhabitant[inhabitant_id] = goal_key
            continue
        start = starts.get(intention_id)
        if start is not None:
            durations.append(event["tick"] - start["tick"])
        reason = event.get("payload", {}).get("reason")
        if reason:
            terminal_reasons[reason] += 1

    intention_actions = [
        event
        for event in physical
        if event.payload.get("intention_id") is not None
    ]
    continuations = sum(
        event.payload.get("decision_source") == "intention_continuation"
        for event in intention_actions
    )
    return {
        "started": event_counts["intention_started"],
        "completed": event_counts["intention_completed"],
        "failed": event_counts["intention_failed"],
        "interrupted": event_counts["intention_interrupted"],
        "unterminated": max(
            0,
            event_counts["intention_started"]
            - event_counts["intention_completed"]
            - event_counts["intention_failed"]
            - event_counts["intention_interrupted"],
        ),
        "average_duration_ticks": (
            round(sum(durations) / len(durations), 2) if durations else 0.0
        ),
        "maximum_duration_ticks": max(durations, default=0),
        "repeated_intentions": repeated,
        "destinations_reached": terminal_reasons["target_reached"],
        "terminal_reasons": dict(sorted(terminal_reasons.items())),
        "model_calls": len(calls),
        "intention_actions": len(intention_actions),
        "continuation_actions": continuations,
        "model_calls_avoided": continuations,
    }


def main() -> None:
    from .persistence import SQLiteStore

    parser = argparse.ArgumentParser(description="Summarize intention behavior in a recorded run")
    parser.add_argument("database", nargs="?", default="runs/demo.sqlite3", type=Path)
    parser.add_argument("--run-id")
    arguments = parser.parse_args()
    store = SQLiteStore(arguments.database)
    try:
        summaries = store.run_summaries()
        if not summaries:
            raise SystemExit("No recorded runs found")
        run_id = arguments.run_id or summaries[0]["run_id"]
        metrics = summarize_intentions(
            store.intention_events_for_run(run_id),
            store.events_for_run(run_id),
            store.model_calls_for_run(run_id),
        )
        print(json.dumps({"run_id": run_id, **metrics}, indent=2, sort_keys=True))
    finally:
        store.close()


if __name__ == "__main__":
    main()
