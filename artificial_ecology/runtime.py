"""Inhabitant decision coordination and local model integration."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib import request

from .domain import ActionProposal, Position
from .engine import Event, SimulationEngine


class DecisionController(Protocol):
    def decide(self, inhabitant_id: str, perception: dict[str, Any]) -> ActionProposal | None:
        """Return one proposal or no action for the current decision barrier."""


@dataclass(frozen=True, slots=True)
class TickResult:
    tick: int
    perceptions: dict[str, dict[str, Any]]
    proposals: tuple[ActionProposal, ...]
    events: tuple[Event, ...]


class SimulationRunner:
    """Coordinates the engine barrier without owning world rules."""

    def __init__(self, engine: SimulationEngine, controller: DecisionController) -> None:
        self.engine = engine
        self.controller = controller

    def run_tick(self) -> TickResult:
        environmental_events = list(self.engine.advance())
        perceptions: dict[str, dict[str, Any]] = {}
        proposals: list[ActionProposal] = []

        for inhabitant_id in sorted(self.engine.world.inhabitants):
            inhabitant = self.engine.world.inhabitants[inhabitant_id]
            if not inhabitant.alive:
                continue
            perception = self.engine.perceive(inhabitant_id)
            perceptions[inhabitant_id] = perception
            inhabitant.desires = self._desires_for(inhabitant)
            self._update_beliefs(inhabitant, perception)
            inhabitant.perception_history.append({
                "tick": perception["tick"],
                "visible_inhabitants": [item["id"] for item in perception["visible_inhabitants"]],
                "visible_food": len(perception["visible_food"]),
                "visible_water": len(perception["visible_water"]),
            })
            inhabitant.perception_history = inhabitant.perception_history[-20:]
            self._remember(inhabitant, "perception", inhabitant.perception_history[-1])
            decision_context = self._decision_context(inhabitant, perception)
            decision_perception = {**perception, "cognition": decision_context}
            proposal = self.controller.decide(inhabitant_id, decision_perception)
            inhabitant.last_decision = self._decision_record(inhabitant, proposal, decision_context)
            inhabitant.current_plan = [self._plan_for(inhabitant, proposal)]
            if proposal is None:
                inhabitant.current_plan[0]["status"] = "no_action"
            if proposal is not None:
                proposals.append(proposal)

        action_events = self.engine.resolve(proposals)
        self._record_action_results(action_events)
        return TickResult(
            tick=self.engine.world.tick,
            perceptions=perceptions,
            proposals=tuple(proposals),
            events=tuple(environmental_events) + action_events,
        )

    def _record_action_results(self, events: list[Event] | tuple[Event, ...]) -> None:
        for event in events:
            actor_id = event.payload.get("actor_id")
            inhabitant = self.engine.world.inhabitants.get(actor_id)
            if inhabitant is None:
                continue
            self._remember(inhabitant, "action_result", event.to_dict())
            self._complete_plan(inhabitant, event)
            self._learn_from_action(inhabitant, event)

    @staticmethod
    def _complete_plan(inhabitant: Any, event: Event) -> None:
        if not inhabitant.current_plan:
            return
        plan = inhabitant.current_plan[-1]
        if plan.get("status") != "pending":
            return
        plan["status"] = "succeeded" if event.event_type in {"action_succeeded", "message_delivered"} else "failed"
        plan["completed_tick"] = event.tick
        plan["result_event_sequence"] = event.sequence

    @staticmethod
    def _learn_from_action(inhabitant: Any, event: Event) -> None:
        reason = event.payload.get("reason")
        action_type = event.payload.get("action_type")
        if reason == "no_food_here" and action_type == "eat":
            SimulationRunner._update_belief(inhabitant, f"food_at:{inhabitant.position.x},{inhabitant.position.y}", False, .95, "failed_action", event.tick)
        if reason == "no_water_here" and action_type == "drink":
            SimulationRunner._update_belief(inhabitant, f"water_at:{inhabitant.position.x},{inhabitant.position.y}", False, .95, "failed_action", event.tick)

    @staticmethod
    def _decision_record(inhabitant: Any, proposal: ActionProposal | None, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "actor_id": inhabitant.id,
            "tick": context["tick"],
            "action_type": proposal.action_type if proposal is not None else "none",
            "proposal": proposal.to_dict() if proposal is not None else None,
            "desires": dict(context["desires"]),
            "beliefs": dict(context["beliefs"]),
            "retrieved_memory_ids": [memory["id"] for memory in context["memories"]],
        }

    @staticmethod
    def _plan_for(inhabitant: Any, proposal: ActionProposal | None) -> dict[str, Any]:
        return {
            "created_tick": inhabitant.perception_history[-1]["tick"],
            "status": "pending" if proposal is not None else "no_action",
            "request": proposal.to_dict() if proposal is not None else None,
        }

    @staticmethod
    def _decision_context(inhabitant: Any, perception: dict[str, Any]) -> dict[str, Any]:
        return {
            "tick": perception["tick"],
            "desires": dict(inhabitant.desires),
            "beliefs": dict(inhabitant.beliefs),
            "memories": SimulationRunner._retrieve_memories(inhabitant, perception),
            "current_plan": list(inhabitant.current_plan),
        }

    @staticmethod
    def _retrieve_memories(inhabitant: Any, perception: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
        memories = list(reversed(inhabitant.memories))
        selected = memories[:limit]
        return [dict(memory) for memory in selected]

    @classmethod
    def _update_beliefs(cls, inhabitant: Any, perception: dict[str, Any]) -> None:
        tick = perception["tick"]
        visible_food = {f"food_at:{item['position']['x']},{item['position']['y']}": item for item in perception["visible_food"]}
        visible_water = {f"water_at:{item['x']},{item['y']}": item for item in perception["visible_water"]}
        for key, item in visible_food.items():
            cls._update_belief(inhabitant, key, {"present": True, "quantity": item["quantity"]}, .9, "perception", tick)
        for key in visible_water:
            cls._update_belief(inhabitant, key, True, .9, "perception", tick)

    @staticmethod
    def _update_belief(inhabitant: Any, key: str, value: Any, confidence: float, source: str, tick: int) -> None:
        previous = inhabitant.beliefs.get(key, {})
        inhabitant.beliefs[key] = {
            "value": value,
            "confidence": confidence,
            "source": source,
            "first_observed_tick": previous.get("first_observed_tick", tick),
            "updated_tick": tick,
        }

    @staticmethod
    def _desires_for(inhabitant: Any) -> dict[str, int]:
        return {
            "reduce_hunger": inhabitant.hunger,
            "reduce_thirst": inhabitant.thirst,
            "reduce_fatigue": inhabitant.fatigue,
        }

    @staticmethod
    def _remember(inhabitant: Any, memory_type: str, content: dict[str, Any]) -> None:
        memory_id = f"{inhabitant.id}:{content.get('tick', 0)}:{len(inhabitant.memories) + 1}"
        inhabitant.memories.append({"id": memory_id, "tick": content.get("tick"), "type": memory_type, "content": content})
        inhabitant.memories = inhabitant.memories[-100:]


class SimulationSession:
    """Owns the controllable lifecycle around a simulation runner."""

    def __init__(
        self,
        engine_factory: Callable[[], SimulationEngine],
        controller_factory: Callable[[], DecisionController],
        tick_interval: float = 1.0,
        on_tick: Callable[[SimulationEngine, TickResult], None] | None = None,
        on_reset: Callable[[SimulationEngine], None] | None = None,
    ) -> None:
        self._engine_factory = engine_factory
        self._controller_factory = controller_factory
        self._tick_interval = tick_interval
        self._on_tick = on_tick
        self._on_reset = on_reset
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.engine = engine_factory()
        self._runner = SimulationRunner(self.engine, controller_factory())
        self._status = "stopped"
        self._error: str | None = None

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def start(self) -> bool:
        with self._lock:
            if self._status == "running":
                return False
            if self.engine.is_extinct:
                return False
            self._stop_event.clear()
            self._error = None
            self._status = "running"
            self._thread = threading.Thread(target=self._run, name="simulation", daemon=True)
            self._thread.start()
            return True

    def stop(self) -> bool:
        with self._lock:
            if self._status != "running":
                return False
            self._status = "stopped"
            self._stop_event.set()
            return True

    def reset(self) -> None:
        self.stop()
        with self._lock:
            self.engine = self._engine_factory()
            self._runner = SimulationRunner(self.engine, self._controller_factory())
            self._status = "stopped"
            self._error = None
            if self._on_reset is not None:
                self._on_reset(self.engine)

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                with self._lock:
                    if self._status != "running":
                        return
                    result = self._runner.run_tick()
                    if self._on_tick is not None:
                        self._on_tick(self.engine, result)
                    if self.engine.is_extinct:
                        self._status = "extinct"
                        return
                time.sleep(self._tick_interval)
        except Exception as error:  # surface infrastructure failures to the observer
            with self._lock:
                self._error = str(error)
                self._status = "error"


class ScriptedController:
    """Deterministic controller for engine tests and baseline experiments."""

    def __init__(self, decisions: dict[int, dict[str, ActionProposal | None]] | None = None) -> None:
        self._decisions = decisions or {}

    def decide(self, inhabitant_id: str, perception: dict[str, Any]) -> ActionProposal | None:
        return self._decisions.get(perception["tick"], {}).get(inhabitant_id)


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    model: str = "gemma4:e2b"
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 30.0


class OllamaController:
    """Turns local Ollama JSON responses into engine-validated proposals."""

    def __init__(
        self,
        config: OllamaConfig | None = None,
        transport: Callable[[str, bytes, float], bytes] | None = None,
    ) -> None:
        self.config = config or OllamaConfig()
        self._transport = transport or self._post

    def decide(self, inhabitant_id: str, perception: dict[str, Any]) -> ActionProposal | None:
        payload = {
            "model": self.config.model,
            "stream": False,
            "format": {
                "type": "object",
                "properties": {
                    "action_type": {"type": "string"},
                    "target_x": {"type": ["integer", "null"]},
                    "target_y": {"type": ["integer", "null"]},
                    "recipient_id": {"type": ["string", "null"]},
                    "message": {"type": ["string", "null"]},
                },
                "required": ["action_type", "target_x", "target_y", "recipient_id", "message"],
            },
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Choose one action from move, eat, drink, rest, speak, or none. "
                        "Return only the requested JSON object. The simulation engine decides whether it is legal."
                    ),
                },
                {"role": "user", "content": json.dumps({"inhabitant_id": inhabitant_id, "perception": perception})},
            ],
        }
        try:
            response = self._transport(
                f"{self.config.base_url.rstrip('/')}/api/chat",
                json.dumps(payload).encode("utf-8"),
                self.config.timeout_seconds,
            )
            outer = json.loads(response)
            content = outer["message"]["content"]
            return self._proposal_from_json(inhabitant_id, json.loads(content))
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _proposal_from_json(inhabitant_id: str, data: dict[str, Any]) -> ActionProposal | None:
        action_type = data.get("action_type")
        if action_type in (None, "none"):
            return None
        if action_type == "move":
            if not isinstance(data.get("target_x"), int) or not isinstance(data.get("target_y"), int):
                return None
            return ActionProposal.move(inhabitant_id, Position(data["target_x"], data["target_y"]))
        if action_type in {"eat", "drink", "rest"}:
            return ActionProposal(inhabitant_id, action_type)
        if action_type == "speak":
            recipient_id = data.get("recipient_id")
            message = data.get("message")
            if isinstance(recipient_id, str) and isinstance(message, str):
                return ActionProposal.speak(inhabitant_id, recipient_id, message)
        return None

    @staticmethod
    def _post(url: str, body: bytes, timeout: float) -> bytes:
        http_request = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with request.urlopen(http_request, timeout=timeout) as response:
            return response.read()
