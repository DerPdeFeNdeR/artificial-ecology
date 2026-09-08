"""Run a tiny deterministic core demonstration with ``python -m artificial_ecology``."""

from .domain import ActionProposal, Inhabitant, Position, World
from .engine import SimulationEngine


def main() -> None:
    world = World(
        width=5,
        height=5,
        inhabitants={"one": Inhabitant("one", "One", Position(1, 1))},
        food={Position(1, 1): 1},
        water={Position(2, 1)},
    )
    engine = SimulationEngine(world, seed=1)
    for event in engine.step([ActionProposal.eat("one")]):
        print(event.to_dict())


if __name__ == "__main__":
    main()
