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
            proposal = self.controller.decide(inhabitant_id, perception)
            if proposal is not None:
                proposals.append(proposal)

        action_events = self.engine.resolve(proposals)
        return TickResult(
            tick=self.engine.world.tick,
            perceptions=perceptions,
            proposals=tuple(proposals),
            events=tuple(environmental_events) + action_events,
        )


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
