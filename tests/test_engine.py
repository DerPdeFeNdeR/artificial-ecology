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
from artificial_ecology.runtime import OllamaController, PlanProposal, ScriptedController, SimulationRunner, SimulationSession


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
        self.assertEqual(inhabitant.current_plan[0]["request"]["action_type"], "eat")
        self.assertEqual(inhabitant.current_plan[0]["status"], "succeeded")
        self.assertEqual(inhabitant.memories[-1]["type"], "action_result")
        self.assertEqual(len(inhabitant.perception_history), 1)

    def test_perception_updates_uncertain_beliefs_and_context(self) -> None:
        contexts = []

        class ContextController:
            def decide(self, inhabitant_id, perception):
                contexts.append(perception["cognition"])
                return None

        engine = make_engine()
        SimulationRunner(engine, ContextController()).run_tick()

        belief = engine.world.inhabitants["a"].beliefs["food_at:1,1"]
        self.assertEqual(belief["value"], {"present": True, "quantity": 2})
        self.assertEqual(belief["source"], "perception")
        self.assertEqual(belief["confidence"], 0.9)
        self.assertEqual(contexts[0]["beliefs"]["food_at:1,1"], belief)
        self.assertEqual(contexts[0]["memories"][0]["type"], "perception")

    def test_spatial_memory_records_present_and_empty_resources(self) -> None:
        engine = make_engine()
        runner = SimulationRunner(engine, ScriptedController())

        runner.run_tick()

        inhabitant = engine.world.inhabitants["a"]
        self.assertEqual(inhabitant.spatial_memory["1,1"]["food"], {"present": True, "quantity": 2})
        self.assertEqual(inhabitant.spatial_memory["1,2"]["food"], {"present": False, "quantity": 0})

    def test_perception_excludes_private_cognition_from_self_observation(self) -> None:
        captured = []

        class CaptureController:
            def decide(self, inhabitant_id, perception):
                captured.append(perception)
                return None

        engine = make_engine()
        SimulationRunner(engine, CaptureController()).run_tick()

        self.assertNotIn("memories", captured[0]["self"])
        self.assertNotIn("beliefs", captured[0]["self"])
        self.assertIn("memories", captured[0]["cognition"])
        self.assertIn("instincts", captured[0]["cognition"])
        self.assertIn("motivations", captured[0]["cognition"])
        self.assertEqual(captured[0]["cognition"]["need_priorities"][0]["need"], "fatigue")
        self.assertIn("rest", captured[0]["action_rules"])
        self.assertIn("visible_occupied_positions", captured[0]["action_rules"])

    def test_decision_context_includes_recent_action_results(self) -> None:
        contexts = []

        class ContextController:
            def decide(self, inhabitant_id, perception):
                contexts.append((inhabitant_id, perception["cognition"]))
                return ActionProposal.move(inhabitant_id, Position(4, 4)) if perception["tick"] == 1 else None

        engine = make_engine()
        runner = SimulationRunner(engine, ContextController())
        runner.run_tick()
        runner.run_tick()

        context = next(context for inhabitant_id, context in contexts if inhabitant_id == "a" and context["tick"] == 2)
        self.assertEqual(context["recent_action_results"][0]["outcome"], "failed")
        self.assertEqual(context["recent_action_results"][0]["reason"], "target_occupied")

    def test_bounded_plan_continues_without_a_new_decision(self) -> None:
        decisions = []

        class PlanningController:
            decision_source = "test_plan"

            def decide(self, inhabitant_id, perception):
                decisions.append((inhabitant_id, perception["tick"]))
                if inhabitant_id == "a":
                    return PlanProposal("a", (
                        ActionProposal.move("a", Position(1, 2)),
                        ActionProposal.move("a", Position(1, 3)),
                    ))
                return None

        engine = make_engine()
        runner = SimulationRunner(engine, PlanningController())

        first = runner.run_tick()
        second = runner.run_tick()

        self.assertEqual(decisions, [("a", 1), ("b", 1), ("b", 2)])
        self.assertEqual(first.events[-1].payload["decision_source"], "test_plan")
        self.assertEqual(second.events[-1].payload["decision_source"], "plan_continuation")
        self.assertEqual(engine.world.inhabitants["a"].position, Position(1, 3))
        self.assertEqual(engine.world.inhabitants["a"].current_plan[0]["status"], "succeeded")

    def test_independent_decisions_are_requested_concurrently(self) -> None:
        state = {"active": 0, "maximum": 0}
        lock = threading.Lock()

        class ConcurrentController:
            def decide(self, inhabitant_id, perception):
                with lock:
                    state["active"] += 1
                    state["maximum"] = max(state["maximum"], state["active"])
                time.sleep(0.02)
                with lock:
                    state["active"] -= 1
                return None

        engine = make_engine()
        SimulationRunner(engine, ConcurrentController()).run_tick()

        self.assertGreater(state["maximum"], 1)

    def test_repeated_no_action_triggers_innate_exploration(self) -> None:
        class PassiveController:
            def decide(self, inhabitant_id, perception):
                return None

        engine = make_engine()
        engine.world.food.clear()
        engine.world.water.clear()
        runner = SimulationRunner(engine, PassiveController())

        first = runner.run_tick()
        second = runner.run_tick()

        self.assertFalse(first.proposals)
        self.assertEqual(second.proposals[0].decision_source, "innate_exploration")
        self.assertEqual(second.proposals[0].action_type, "move")
        self.assertEqual(second.events[-1].event_type, "action_succeeded")

    def test_distant_model_destination_becomes_adjacent_step(self) -> None:
        class GoalController:
            def decide(self, inhabitant_id, perception):
                if inhabitant_id == "a":
                    return ActionProposal.move("a", Position(1, 4))
                return None

        engine = make_engine()
        events = SimulationRunner(engine, GoalController()).run_tick().events

        move = next(event for event in events if event.payload.get("actor_id") == "a")
        self.assertEqual(move.event_type, "action_succeeded")
        self.assertEqual(move.payload["to"], {"x": 1, "y": 2})

    def test_innate_homeostasis_eats_when_at_food(self) -> None:
        class PassiveController:
            def decide(self, inhabitant_id, perception):
                return None

        engine = make_engine()
        engine.world.inhabitants["a"].hunger = 10
        result = SimulationRunner(engine, PassiveController()).run_tick()

        event = next(event for event in result.events if event.payload.get("actor_id") == "a")
        self.assertEqual(event.payload["action_type"], "eat")
        self.assertEqual(event.payload["decision_source"], "innate_homeostasis")
        self.assertEqual(engine.world.inhabitants["a"].hunger, 0)

    def test_failed_plan_action_causes_reconsideration(self) -> None:
        decisions = []

        class PlanningController:
            def decide(self, inhabitant_id, perception):
                decisions.append(perception["tick"])
                return PlanProposal("a", (
                    ActionProposal.move("a", Position(4, 4)),
                    ActionProposal.move("a", Position(4, 3)),
                )) if inhabitant_id == "a" else None

        runner = SimulationRunner(make_engine(), PlanningController())
        runner.run_tick()
        runner.run_tick()

        self.assertEqual(decisions, [1, 1, 2, 2])

    def test_failed_action_updates_plan_and_belief(self) -> None:
        engine = make_engine()
        controller = ScriptedController({1: {"a": ActionProposal.drink("a")}})

        result = SimulationRunner(engine, controller).run_tick()

        inhabitant = engine.world.inhabitants["a"]
        self.assertEqual(result.events[-1].event_type, "action_failed")
        self.assertEqual(inhabitant.current_plan[0]["status"], "failed")
        self.assertEqual(inhabitant.current_plan[0]["result_event_sequence"], result.events[-1].sequence)
        self.assertEqual(inhabitant.beliefs["water_at:1,1"]["value"], False)

    def test_retrieved_memories_are_bounded_and_recent(self) -> None:
        engine = make_engine()
        inhabitant = engine.world.inhabitants["a"]
        inhabitant.memories = [
            {"id": str(index), "tick": index, "type": "test", "content": {"tick": index}}
            for index in range(20)
        ]
        contexts = []

        class ContextController:
            def decide(self, inhabitant_id, perception):
                contexts.append(perception["cognition"]["memories"])
                return None

        SimulationRunner(engine, ContextController()).run_tick()

        self.assertEqual(len(contexts[0]), 8)
        self.assertEqual(contexts[0][0]["type"], "perception")

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

    def test_session_stop_and_observer_state_remain_responsive_during_decision(self) -> None:
        class SlowController:
            def decide(self, inhabitant_id, perception):
                time.sleep(0.2)
                return None

        session = SimulationSession(make_engine, SlowController, tick_interval=0.01)

        self.assertTrue(session.start())
        deadline = time.monotonic() + 1
        while session.decision_progress["completed"] == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        started = time.monotonic()
        self.assertTrue(session.stop())
        self.assertLess(time.monotonic() - started, 0.1)
        self.assertEqual(ObserverView(session).state()["status"], "stopped")
        session.reset()

    def test_session_pauses_after_model_transport_failure(self) -> None:
        def unavailable(url, body, timeout):
            raise OSError("offline")

        session = SimulationSession(
            make_engine,
            lambda: OllamaController(transport=unavailable),
            tick_interval=0.01,
        )

        self.assertTrue(session.start())
        deadline = time.monotonic() + 1
        while session.status == "running" and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertEqual(session.status, "error")
        self.assertIn("unavailable", session.error)
        session.reset()

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

    def test_signal_is_delivered_only_within_range(self) -> None:
        engine = make_engine()
        events = engine.step([ActionProposal.speak("a", "b", "sig-water")])

        self.assertEqual(events[-1].event_type, "message_delivered")
        self.assertEqual(engine.world.inhabitants["b"].received_messages[0]["signal"], "sig-water")
        self.assertIsNone(engine.world.inhabitants["b"].received_messages[0]["interpretation"])

    def test_natural_language_speech_is_rejected_as_a_signal(self) -> None:
        engine = make_engine()

        events = engine.step([ActionProposal.speak("a", "b", "water is here")])

        self.assertEqual(events[-1].event_type, "action_failed")
        self.assertEqual(events[-1].payload["reason"], "invalid_signal")

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

    def test_ollama_response_becomes_bounded_plan(self) -> None:
        content = json.dumps(
            {
                "steps": [
                    {"action_type": "move", "target_x": 2, "target_y": 1, "recipient_id": None, "message": None},
                    {"action_type": "rest", "target_x": None, "target_y": None, "recipient_id": None, "message": None},
                ]
            }
        )
        response = json.dumps({"message": {"content": content}}).encode()
        controller = OllamaController(transport=lambda url, body, timeout: response)

        plan = controller.decide("a", {"tick": 1})

        self.assertIsInstance(plan, PlanProposal)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(controller.drain_calls()[0]["outcome"], "plan")

    def test_ollama_request_disables_thinking_and_bounds_output(self) -> None:
        response = b'{"message":{"content":"{\\"action_type\\":\\"none\\",\\"target_x\\":null,\\"target_y\\":null,\\"recipient_id\\":null,\\"message\\":null}"}}'
        requests = []

        def transport(url, body, timeout):
            requests.append(json.loads(body))
            return response

        controller = OllamaController(transport=transport)

        controller.decide("a", {"tick": 1})

        self.assertFalse(requests[0]["think"])
        self.assertEqual(requests[0]["options"]["num_predict"], 128)
        self.assertEqual(requests[0]["options"]["temperature"], 0)
        self.assertEqual(requests[0]["options"]["top_p"], 0.95)
        self.assertEqual(requests[0]["options"]["top_k"], 64)
        self.assertEqual(requests[0]["keep_alive"], -1)

    def test_ollama_context_removes_repeated_private_details(self) -> None:
        perception = {
            "tick": 4,
            "self": {
                "id": "a",
                "name": "A",
                "position": {"x": 1, "y": 1},
                "hunger": 2,
                "thirst": 3,
                "fatigue": 4,
                "alive": True,
                "received_messages": [],
            },
            "visible_inhabitants": [{"id": "b", "name": "B", "position": {"x": 2, "y": 1}}],
            "visible_food": [],
            "visible_water": [],
            "visible_obstacles": [],
            "action_rules": {"rest": "Reduces fatigue only.", "visible_occupied_positions": [{"x": 2, "y": 1}]},
            "cognition": {
                "desires": {"reduce_hunger": 2},
                "need_priorities": [{"need": "thirst", "value": 3, "urgency": "low"}],
                "beliefs": {"water_at:2,2": {"value": True}},
                "memories": [{"id": "old", "content": {"large": "discarded"}}],
                "recent_action_results": [{"action_type": "rest", "outcome": "succeeded"}],
                "current_plan": [{"status": "succeeded"}],
            },
        }

        compact = OllamaController._compact_perception(perception)

        self.assertNotIn("name", compact["self"])
        self.assertNotIn("desires", compact["cognition"])
        self.assertNotIn("memories", compact["cognition"])
        self.assertNotIn("current_plan", compact["cognition"])
        self.assertEqual(compact["visible_inhabitants"], [{"id": "b", "position": {"x": 2, "y": 1}}])

    def test_ollama_records_successful_call(self) -> None:
        response = b'{"message":{"content":"{\\"action_type\\":\\"none\\",\\"target_x\\":null,\\"target_y\\":null,\\"recipient_id\\":null,\\"message\\":null}"}}'
        controller = OllamaController(transport=lambda url, body, timeout: response)

        self.assertIsNone(controller.decide("a", {"tick": 3}))

        calls = controller.drain_calls()
        self.assertEqual(calls[0]["outcome"], "no_action")
        self.assertEqual(calls[0]["model"], "gemma4:e2b")
        self.assertEqual(controller.drain_calls(), ())

    def test_ollama_records_transport_failure(self) -> None:
        def unavailable(url, body, timeout):
            raise OSError("offline")

        controller = OllamaController(transport=unavailable)

        self.assertIsNone(controller.decide("a", {"tick": 4}))

        call = controller.drain_calls()[0]
        self.assertEqual(call["outcome"], "transport_error")
        self.assertEqual(call["error"], "offline")

    def test_ollama_records_invalid_action(self) -> None:
        response = b'{"message":{"content":"{\\"action_type\\":\\"reduce_hunger\\",\\"target_x\\":null,\\"target_y\\":null,\\"recipient_id\\":null,\\"message\\":null}"}}'
        controller = OllamaController(transport=lambda url, body, timeout: response)

        self.assertIsNone(controller.decide("a", {"tick": 1}))

        self.assertEqual(controller.drain_calls()[0]["outcome"], "invalid_action")

    def test_sqlite_stores_model_calls(self) -> None:
        engine = make_engine()
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "run.sqlite3")
            store.create_run("run-1", seed=7)
            store.save_initial_snapshot("run-1", engine)
            store.save_tick("run-1", engine, (), model_calls=[{
                "inhabitant_id": "a",
                "tick": 1,
                "model": "test-model",
                "outcome": "transport_error",
                "error": "offline",
            }])

            calls = store.model_calls_for_run("run-1")

            self.assertEqual(calls[0]["outcome"], "transport_error")
            self.assertEqual(calls[0]["error"], "offline")
            store.close()

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
        self.assertIn("minmax(320px, 380px)", INDEX_HTML)
        self.assertIn('class="map-panel"', INDEX_HTML)
        self.assertIn('class="sidebar"', INDEX_HTML)
        self.assertIn('class="events-panel"', INDEX_HTML)
        self.assertIn("grid-column: 1 / -1", INDEX_HTML)
        self.assertIn("color-scheme: dark", INDEX_HTML)

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
