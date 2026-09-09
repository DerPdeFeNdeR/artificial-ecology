import sqlite3
import tempfile
import time
import json
import threading
from urllib.request import urlopen
import unittest
from pathlib import Path

from artificial_ecology.domain import ActionProposal, Inhabitant, Position, World
from artificial_ecology.engine import SimulationEngine
from artificial_ecology.persistence import SQLiteStore, verify_replay
from artificial_ecology.observer import INDEX_HTML, ObserverView, create_server
from artificial_ecology.runtime import OllamaController, ScriptedController, SimulationRunner, SimulationSession


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
    def test_runner_decides_after_needs_advance(self) -> None:
        engine = make_engine()
        controller = ScriptedController({1: {"a": ActionProposal.eat("a")}})

        result = SimulationRunner(engine, controller).run_tick()

        self.assertEqual(result.tick, 1)
        self.assertEqual(result.perceptions["a"]["tick"], 1)
        self.assertEqual(result.events[-1].event_type, "action_succeeded")
        inhabitant = engine.world.inhabitants["a"]
        self.assertEqual(inhabitant.desires["reduce_hunger"], 1)
        self.assertEqual(inhabitant.last_decision["action_type"], "eat")
        self.assertEqual(inhabitant.current_plan[0]["action_type"], "eat")
        self.assertEqual(inhabitant.memories[-1]["type"], "action_result")
        self.assertEqual(len(inhabitant.perception_history), 1)

    def test_session_start_stop_and_reset(self) -> None:
        session = SimulationSession(make_engine, lambda: ScriptedController(), tick_interval=0.01)

        self.assertEqual(session.status, "stopped")
        self.assertTrue(session.start())
        deadline = time.monotonic() + 1
        while session.engine.world.tick == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertGreater(session.engine.world.tick, 0)
        self.assertTrue(session.stop())
        stopped_tick = session.engine.world.tick
        time.sleep(0.03)
        self.assertEqual(session.engine.world.tick, stopped_tick)

        session.reset()

        self.assertEqual(session.status, "stopped")
        self.assertEqual(session.engine.world.tick, 0)

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

        later_events = engine.step()

        self.assertFalse(later_events)
        self.assertEqual(
            len([event for event in engine.events if event.event_type == "inhabitant_died"]),
            1,
        )
        self.assertFalse(engine.is_extinct)

        engine.world.inhabitants["b"].hunger = 100
        engine.step()

        self.assertTrue(engine.is_extinct)

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

    def test_sqlite_replays_recorded_decisions(self) -> None:
        engine = make_engine(seed=7)
        controller = ScriptedController({1: {"a": ActionProposal.eat("a")}})
        runner = SimulationRunner(engine, controller)

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "run.sqlite3")
            store.create_run("run-1", seed=7, metadata={"scenario": "replay"})
            store.save_initial_snapshot("run-1", engine)
            result = runner.run_tick()
            store.save_tick("run-1", engine, result.events, result.proposals)

            replayed = verify_replay(store, "run-1")

            self.assertEqual(replayed.snapshot(), engine.snapshot())
            self.assertEqual(store.run_summaries()[0]["last_tick"], 1)
            store.close()

    def test_ollama_response_becomes_action_proposal(self) -> None:
        response = b'{"message":{"content":"{\\"action_type\\":\\"move\\",\\"target_x\\":2,\\"target_y\\":1,\\"recipient_id\\":null,\\"message\\":null}"}}'
        controller = OllamaController(transport=lambda url, body, timeout: response)

        proposal = controller.decide("a", {"tick": 1})

        self.assertEqual(proposal, ActionProposal.move("a", Position(2, 1)))

    def test_observer_view_is_read_only_and_contains_world_and_events(self) -> None:
        engine = make_engine()
        engine.step([ActionProposal.eat("a")])
        view = ObserverView(engine)

        state = view.state()

        self.assertEqual(state["world"]["tick"], 1)
        self.assertEqual(len(state["events"]), 1)
        self.assertEqual(engine.world.inhabitants["a"].hunger, 0)

    def test_observer_includes_inspection_and_lifecycle_controls(self) -> None:
        self.assertIn("Start", INDEX_HTML)
        self.assertIn("Stop", INDEX_HTML)
        self.assertIn("Reset", INDEX_HTML)
        self.assertIn("event-filter", INDEX_HTML)
        self.assertIn("inspector", INDEX_HTML)
        self.assertIn("overflow-wrap: anywhere", INDEX_HTML)
        self.assertIn("minmax(0, 280px)", INDEX_HTML)

    def test_observer_serves_ui_and_state_api(self) -> None:
        try:
            server = create_server(make_engine(), port=0)
        except PermissionError:
            self.skipTest("socket creation is restricted in this environment")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(f"{base_url}/", timeout=2) as response:
                html = response.read().decode("utf-8")
            with urlopen(f"{base_url}/api/state", timeout=2) as response:
                state = json.loads(response.read())

            self.assertIn("Start", html)
            self.assertIn("inspector", html)
            self.assertEqual(state["status"], "stopped")
            self.assertEqual(state["world"]["tick"], 0)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
