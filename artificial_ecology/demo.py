"""Run a small moving world with the browser observer."""

from __future__ import annotations

import time
from threading import Thread

from .domain import ActionProposal, Inhabitant, Position, World
from .engine import SimulationEngine
from .observer import create_server
from .runtime import SimulationRunner


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
    engine = create_demo_engine()
    runner = SimulationRunner(engine, DemoController())
    server = create_server(engine)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print("Observer available at http://127.0.0.1:8000")
    try:
        while True:
            runner.run_tick()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping observer")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
