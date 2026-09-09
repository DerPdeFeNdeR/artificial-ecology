"""Run a small moving world with the browser observer."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .domain import ActionProposal, Inhabitant, Position, World
from .engine import SimulationEngine
from .observer import create_server
from .persistence import SQLiteStore
from .runtime import SimulationSession


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
    def create_recorded_engine():
        engine = create_demo_engine()
        run_id["value"] = datetime.now(timezone.utc).strftime("demo-%Y%m%dT%H%M%S%fZ")
        store.create_run(run_id["value"], seed=11, metadata={"scenario": "scripted_observer_demo"})
        store.save_initial_snapshot(run_id["value"], engine)
        return engine

    def record_tick(engine, result):
        store.save_tick(run_id["value"], engine, result.events, result.proposals)

    session = SimulationSession(
        create_recorded_engine,
        DemoController,
        on_tick=record_tick,
    )
    server = create_server(session)
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
