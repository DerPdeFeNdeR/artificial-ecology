"""Run a small moving world with the browser observer."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path

from .domain import ActionProposal, Inhabitant, Position, World
from .engine import SimulationEngine
from .observer import create_server
from .persistence import SQLiteStore
from .runtime import OllamaConfig, OllamaController, SimulationSession


class DemoController:
    def decide(self, inhabitant_id: str, perception: dict) -> ActionProposal | None:
        inhabitant = perception["self"]
        if inhabitant["hunger"] >= 20 and self._at_position(inhabitant, perception["visible_food"]):
            return ActionProposal.eat(inhabitant_id)
        if inhabitant["thirst"] >= 20 and self._at_position(inhabitant, perception["visible_water"]):
            return ActionProposal.drink(inhabitant_id)

        targets = perception["visible_food"] if inhabitant["hunger"] >= inhabitant["thirst"] else perception["visible_water"]
        target = self._nearest_target(inhabitant["position"], targets)
        if target is None:
            return self._wander(inhabitant_id, inhabitant["position"], perception["tick"])
        return ActionProposal.move(inhabitant_id, self._step_toward(inhabitant["position"], target))

    @staticmethod
    def _at_position(inhabitant: dict, targets: list[dict]) -> bool:
        return any(target.get("position", target) == inhabitant["position"] for target in targets)

    @staticmethod
    def _nearest_target(origin: dict, targets: list[dict]) -> dict | None:
        if not targets:
            return None
        return min(
            (target.get("position", target) for target in targets),
            key=lambda target: abs(target["x"] - origin["x"]) + abs(target["y"] - origin["y"]),
        )

    @staticmethod
    def _step_toward(origin: dict, target: dict) -> Position:
        x = origin["x"]
        y = origin["y"]
        if target["x"] != origin["x"]:
            x += 1 if target["x"] > origin["x"] else -1
        elif target["y"] != origin["y"]:
            y += 1 if target["y"] > origin["y"] else -1
        return Position(x, y)

    @staticmethod
    def _wander(inhabitant_id: str, origin: dict, tick: int) -> ActionProposal:
        directions = ((1, 0), (0, 1), (-1, 0), (0, -1))
        dx, dy = directions[tick % len(directions)]
        return ActionProposal.move(inhabitant_id, Position(origin["x"] + dx, origin["y"] + dy))


def create_demo_engine() -> SimulationEngine:
    inhabitants = {
        f"inhabitant-{index}": Inhabitant(
            id=f"inhabitant-{index}",
            name=f"Inhabitant {index}",
            position=Position(index % 5, index // 5),
        )
        for index in range(5)
    }
    world = World(
        width=12,
        height=8,
        inhabitants=inhabitants,
        food={Position(2, 5): 3, Position(9, 2): 3},
        water={Position(6, 4), Position(10, 6)},
        obstacles={Position(4, 3), Position(4, 4), Position(7, 5)},
    )
    return SimulationEngine(world, seed=11)


def main() -> None:
    Path("runs").mkdir(exist_ok=True)
    run_id = {"value": datetime.now(timezone.utc).strftime("demo-%Y%m%dT%H%M%S%fZ")}
    store = SQLiteStore(Path("runs") / "demo.sqlite3")
    use_ollama = os.environ.get("AE_CONTROLLER", "scripted").lower() == "ollama"
    ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://172.30.96.1:11434")
    fast_mode = os.environ.get("AE_FAST_MODE", "0").lower() in {"1", "true", "yes"}
    tick_interval = float(os.environ.get("AE_TICK_INTERVAL", "0" if fast_mode else "1"))
    max_decision_workers = int(os.environ.get("AE_MAX_DECISION_WORKERS", "5"))

    def create_recorded_engine():
        engine = create_demo_engine()
        run_id["value"] = datetime.now(timezone.utc).strftime("demo-%Y%m%dT%H%M%S%fZ")
        store.create_run(run_id["value"], seed=11, metadata={
            "scenario": "observer_demo",
            "controller": "ollama" if use_ollama else "scripted",
            "ollama_base_url": ollama_base_url if use_ollama else None,
            "ollama_think": False if use_ollama else None,
            "ollama_max_output_tokens": 128 if use_ollama else None,
            "ollama_temperature": 0 if use_ollama else None,
            "ollama_top_p": 0.95 if use_ollama else None,
            "ollama_top_k": 64 if use_ollama else None,
            "ollama_keep_alive": -1 if use_ollama else None,
            "max_decision_workers": max_decision_workers,
            "fast_mode": fast_mode,
            "tick_interval": tick_interval,
        })
        store.save_initial_snapshot(run_id["value"], engine)
        return engine

    def record_tick(engine, result):
        store.save_tick(
            run_id["value"],
            engine,
            result.events,
            result.proposals,
            result.model_calls,
            result.intention_events,
        )

    session = SimulationSession(
        create_recorded_engine,
        (lambda: OllamaController(OllamaConfig(base_url=ollama_base_url))) if use_ollama else DemoController,
        tick_interval=tick_interval,
        on_tick=record_tick,
        max_decision_workers=max_decision_workers,
    )
    server = create_server(session, store=store, current_run_id=lambda: run_id["value"])
    print("Observer available at http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping observer")
    finally:
        session.stop()
        server.shutdown()
        server.server_close()
        store.close()


if __name__ == "__main__":
    main()
