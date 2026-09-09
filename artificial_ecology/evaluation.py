"""Controlled evaluations for inhabitant intention controllers."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from typing import Any, Callable

from .domain import Inhabitant, Position, World
from .engine import SimulationEngine
from .runtime import DecisionController, IntentionProposal, OllamaConfig, OllamaController, SimulationRunner


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    name: str
    passed: bool
    expected: str
    observed: dict[str, Any] | None
    model_calls: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "expected": self.expected,
            "observed": self.observed,
            "model_calls": len(self.model_calls),
        }


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    name: str
    expected: str
    world: World
    accepts: Callable[[dict[str, Any] | None], bool]


class _SubjectController:
    def __init__(self, delegate: DecisionController) -> None:
        self.delegate = delegate
        self.decision_source = getattr(delegate, "decision_source", "evaluation")

    @property
    def infrastructure_failure(self) -> bool:
        return bool(getattr(self.delegate, "infrastructure_failure", False))

    def decide(self, inhabitant_id: str, perception: dict[str, Any]):
        if inhabitant_id != "subject":
            return IntentionProposal(inhabitant_id, "wait")
        return self.delegate.decide(inhabitant_id, perception)

    def drain_calls(self) -> tuple[dict[str, Any], ...]:
        if hasattr(self.delegate, "drain_calls"):
            return tuple(self.delegate.drain_calls())
        return ()


def controlled_cases() -> tuple[EvaluationCase, ...]:
    def inhabitant(**needs: int) -> Inhabitant:
        return Inhabitant("subject", "Subject", Position(2, 2), **needs)

    return (
        EvaluationCase(
            "critical fatigue",
            "rest",
            World(7, 7, {"subject": inhabitant(fatigue=79)}),
            lambda goal: goal is not None and goal["intention_type"] == "rest",
        ),
        EvaluationCase(
            "standing on food",
            "consume food",
            World(7, 7, {"subject": inhabitant(hunger=9)}, food={Position(2, 2): 1}),
            lambda goal: goal is not None
            and goal["intention_type"] == "consume"
            and goal["resource_type"] == "food",
        ),
        EvaluationCase(
            "visible distant food",
            "move_to (4,2)",
            World(7, 7, {"subject": inhabitant(hunger=49)}, food={Position(4, 2): 1}),
            lambda goal: goal is not None
            and goal["intention_type"] == "move_to"
            and goal["target"] == {"x": 4, "y": 2},
        ),
        EvaluationCase(
            "occupied destination",
            "do not move_to occupied (3,2)",
            World(
                7,
                7,
                {
                    "subject": inhabitant(),
                    "other": Inhabitant("other", "Other", Position(3, 2)),
                },
            ),
            lambda goal: goal is not None
            and not (
                goal["intention_type"] == "move_to"
                and goal["target"] == {"x": 3, "y": 2}
            ),
        ),
        EvaluationCase(
            "no visible resources",
            "exploratory move_to another in-bounds cell",
            World(7, 7, {"subject": inhabitant()}),
            lambda goal: goal is not None
            and goal["intention_type"] == "move_to"
            and goal["target"] != {"x": 2, "y": 2}
            and 0 <= goal["target"]["x"] < 7
            and 0 <= goal["target"]["y"] < 7,
        ),
    )


def evaluate_intention_controller(
    controller_factory: Callable[[], DecisionController],
) -> tuple[EvaluationResult, ...]:
    results = []
    for case in controlled_cases():
        controller = _SubjectController(controller_factory())
        engine = SimulationEngine(case.world, seed=7)
        tick = SimulationRunner(engine, controller, max_decision_workers=1).run_tick()
        decision = engine.world.inhabitants["subject"].last_decision or {}
        observed = decision.get("intention")
        results.append(EvaluationResult(
            name=case.name,
            passed=case.accepts(observed),
            expected=case.expected,
            observed=observed,
            model_calls=tick.model_calls,
        ))
    return tuple(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a local inhabitant intention model")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OLLAMA_BASE_URL", "http://172.30.96.1:11434"),
    )
    parser.add_argument("--model", default="gemma4:e2b")
    arguments = parser.parse_args()
    results = evaluate_intention_controller(lambda: OllamaController(OllamaConfig(
        model=arguments.model,
        base_url=arguments.base_url,
    )))
    report = {
        "model": arguments.model,
        "passed": sum(result.passed for result in results),
        "total": len(results),
        "results": [result.to_dict() for result in results],
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
