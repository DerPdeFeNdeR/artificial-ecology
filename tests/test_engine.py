import sqlite3
import tempfile
import unittest
from pathlib import Path

from artificial_ecology.domain import ActionProposal, Inhabitant, Position, World
from artificial_ecology.engine import SimulationEngine
from artificial_ecology.persistence import SQLiteStore


def make_engine(seed: int = 7) -> SimulationEngine:
    world = World(
        width=5,
        height=5,
        inhabitants={
            "a": Inhabitant("a", "A", Position(1, 1)),
            "b": Inhabitant("b", "B", Position(2, 1)),
        },
        food={Position(1, 1): 2},
        water={Position(2, 1)},
    )
    return SimulationEngine(world, seed=seed)


class SimulationEngineTests(unittest.TestCase):
    def test_valid_move_changes_world_and_emits_event(self) -> None:
        engine = make_engine()
        events = engine.step([ActionProposal.move("a", Position(1, 2))])

        self.assertEqual(engine.world.inhabitants["a"].position, Position(1, 2))
        self.assertEqual(events[-1].event_type, "action_succeeded")
        self.assertEqual(events[-1].payload["action_type"], "move")

    def test_invalid_move_does_not_change_world(self) -> None:
        engine = make_engine()
        events = engine.step([ActionProposal.move("a", Position(4, 4))])

        self.assertEqual(engine.world.inhabitants["a"].position, Position(1, 1))
        self.assertEqual(events[-1].event_type, "action_failed")
        self.assertEqual(events[-1].payload["reason"], "target_not_adjacent")

    def test_speech_is_delivered_only_within_range(self) -> None:
        engine = make_engine()
        events = engine.step([ActionProposal.speak("a", "b", "water is here")])

        self.assertEqual(events[-1].event_type, "message_delivered")
        self.assertEqual(engine.world.inhabitants["b"].received_messages[0]["content"], "water is here")

    def test_needs_increase_and_critical_inhabitant_dies(self) -> None:
        engine = make_engine()
        engine.world.inhabitants["a"].hunger = 99

        events = engine.step()

        self.assertFalse(engine.world.inhabitants["a"].alive)
        self.assertEqual(events[0].event_type, "inhabitant_died")

    def test_snapshot_restores_world_and_random_state(self) -> None:
        engine = make_engine(seed=11)
        engine.step([ActionProposal.move("a", Position(1, 2))])

        restored = SimulationEngine.from_snapshot(engine.snapshot())

        self.assertEqual(restored.world.to_dict(), engine.world.to_dict())
        self.assertEqual(restored.snapshot(), engine.snapshot())

    def test_sqlite_stores_events_and_snapshot(self) -> None:
        engine = make_engine()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "run.sqlite3"
            store = SQLiteStore(database)
            store.create_run("run-1", seed=7, metadata={"scenario": "test"})

            events = engine.step([ActionProposal.eat("a")])
            store.save_tick("run-1", engine, events)

            self.assertEqual(len(store.events_for_run("run-1")), len(events))
            self.assertEqual(store.latest_snapshot("run-1")["world"]["tick"], 1)
            store.close()

            with sqlite3.connect(database) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
