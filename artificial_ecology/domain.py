"""Authoritative domain values used by the simulation engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True, order=True)
class Position:
    x: int
    y: int

    def distance_to(self, other: "Position") -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)


@dataclass(frozen=True, slots=True)
class ActionProposal:
    """A request made by an inhabitant; it is not a state change."""

    actor_id: str
    action_type: str
    target: Position | None = None
    recipient_id: str | None = None
    message: str | None = None

    @classmethod
    def move(cls, actor_id: str, target: Position) -> "ActionProposal":
        return cls(actor_id, "move", target=target)

    @classmethod
    def eat(cls, actor_id: str) -> "ActionProposal":
        return cls(actor_id, "eat")

    @classmethod
    def drink(cls, actor_id: str) -> "ActionProposal":
        return cls(actor_id, "drink")

    @classmethod
    def rest(cls, actor_id: str) -> "ActionProposal":
        return cls(actor_id, "rest")

    @classmethod
    def speak(cls, actor_id: str, recipient_id: str, message: str) -> "ActionProposal":
        return cls(actor_id, "speak", recipient_id=recipient_id, message=message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "action_type": self.action_type,
            "target": {"x": self.target.x, "y": self.target.y} if self.target else None,
            "recipient_id": self.recipient_id,
            "message": self.message,
        }


@dataclass(slots=True)
class Inhabitant:
    id: str
    name: str
    position: Position
    hunger: int = 0
    thirst: int = 0
    fatigue: int = 0
    alive: bool = True
    received_messages: list[dict[str, Any]] = field(default_factory=list)
    memories: list[dict[str, Any]] = field(default_factory=list)
    beliefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    desires: dict[str, int] = field(default_factory=dict)
    current_plan: list[dict[str, Any]] = field(default_factory=list)
    last_decision: dict[str, Any] | None = None
    perception_history: list[dict[str, Any]] = field(default_factory=list)

    def increase_needs(self) -> None:
        if not self.alive:
            return
        self.hunger = min(100, self.hunger + 1)
        self.thirst = min(100, self.thirst + 1)
        self.fatigue = min(100, self.fatigue + 1)

    def critical_need(self) -> str | None:
        for name, value in (("hunger", self.hunger), ("thirst", self.thirst), ("fatigue", self.fatigue)):
            if value >= 100:
                return name
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "position": {"x": self.position.x, "y": self.position.y},
            "hunger": self.hunger,
            "thirst": self.thirst,
            "fatigue": self.fatigue,
            "alive": self.alive,
            "received_messages": list(self.received_messages),
            "memories": list(self.memories),
            "beliefs": dict(self.beliefs),
            "desires": dict(self.desires),
            "current_plan": list(self.current_plan),
            "last_decision": self.last_decision,
            "perception_history": list(self.perception_history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Inhabitant":
        position = data["position"]
        return cls(
            id=data["id"],
            name=data["name"],
            position=Position(position["x"], position["y"]),
            hunger=data["hunger"],
            thirst=data["thirst"],
            fatigue=data["fatigue"],
            alive=data["alive"],
            received_messages=list(data.get("received_messages", [])),
            memories=list(data.get("memories", [])),
            beliefs=dict(data.get("beliefs", {})),
            desires=dict(data.get("desires", {})),
            current_plan=list(data.get("current_plan", [])),
            last_decision=data.get("last_decision"),
            perception_history=list(data.get("perception_history", [])),
        )


@dataclass(slots=True)
class World:
    width: int
    height: int
    inhabitants: dict[str, Inhabitant] = field(default_factory=dict)
    food: dict[Position, int] = field(default_factory=dict)
    water: set[Position] = field(default_factory=set)
    obstacles: set[Position] = field(default_factory=set)
    tick: int = 0

    def contains(self, position: Position) -> bool:
        return 0 <= position.x < self.width and 0 <= position.y < self.height

    def occupied(self, position: Position, excluding: str | None = None) -> bool:
        return any(
            inhabitant.alive
            and inhabitant.id != excluding
            and inhabitant.position == position
            for inhabitant in self.inhabitants.values()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "tick": self.tick,
            "inhabitants": {
                inhabitant_id: inhabitant.to_dict()
                for inhabitant_id, inhabitant in sorted(self.inhabitants.items())
            },
            "food": [
                {"position": {"x": position.x, "y": position.y}, "quantity": quantity}
                for position, quantity in sorted(self.food.items())
            ],
            "water": [{"x": p.x, "y": p.y} for p in sorted(self.water)],
            "obstacles": [{"x": p.x, "y": p.y} for p in sorted(self.obstacles)],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "World":
        food = {
            Position(item["position"]["x"], item["position"]["y"]): item["quantity"]
            for item in data["food"]
        }
        return cls(
            width=data["width"],
            height=data["height"],
            tick=data["tick"],
            inhabitants={
                inhabitant_id: Inhabitant.from_dict(inhabitant)
                for inhabitant_id, inhabitant in data["inhabitants"].items()
            },
            food=food,
            water={Position(item["x"], item["y"]) for item in data["water"]},
            obstacles={Position(item["x"], item["y"]) for item in data["obstacles"]},
        )
