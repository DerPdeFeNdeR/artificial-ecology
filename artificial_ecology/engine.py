"""Deterministic simulation engine and action resolution."""

from __future__ import annotations

import base64
import json
import pickle
import random
from dataclasses import dataclass
from typing import Any, Iterable

from .domain import ActionProposal, Inhabitant, Position, World


@dataclass(frozen=True, slots=True)
class Event:
    sequence: int
    tick: int
    event_type: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "tick": self.tick,
            "event_type": self.event_type,
            "payload": self.payload,
        }


class SimulationEngine:
    """Owns world truth and applies validated consequences."""

    def __init__(self, world: World, seed: int = 0) -> None:
        self.world = world
        self.seed = seed
        self._random = random.Random(seed)
        self._next_sequence = 1
        self.events: list[Event] = []

    def advance(self) -> tuple[Event, ...]:
        """Advance environmental effects and needs to the decision barrier."""
        self.world.tick += 1
        emitted: list[Event] = []

        for inhabitant in sorted(self.world.inhabitants.values(), key=lambda item: item.id):
            if not inhabitant.alive:
                continue
            inhabitant.increase_needs()
            critical_need = inhabitant.critical_need()
            if critical_need:
                inhabitant.alive = False
                emitted.append(self._emit("inhabitant_died", {
                    "inhabitant_id": inhabitant.id,
                    "cause": critical_need,
                }))

        self.events.extend(emitted)
        return tuple(emitted)

    def resolve(self, proposals: Iterable[ActionProposal] = ()) -> tuple[Event, ...]:
        """Resolve proposals against the current decision-barrier world state."""
        emitted: list[Event] = []
        valid_proposals = [proposal for proposal in proposals if proposal.actor_id in self.world.inhabitants]
        ordered_proposals = list(valid_proposals)
        self._random.shuffle(ordered_proposals)
        for proposal in ordered_proposals:
            emitted.append(self._resolve(proposal))

        self.events.extend(emitted)
        return tuple(emitted)

    def step(self, proposals: Iterable[ActionProposal] = ()) -> tuple[Event, ...]:
        """Advance exactly one tick and resolve proposals immediately."""
        return self.advance() + self.resolve(proposals)

    def perceive(self, inhabitant_id: str, radius: int = 3) -> dict[str, Any]:
        inhabitant = self._require_inhabitant(inhabitant_id)
        visible_inhabitants = []
        visible_food = []
        visible_water = []

        for other in sorted(self.world.inhabitants.values(), key=lambda item: item.id):
            if not other.alive or inhabitant.position.distance_to(other.position) > radius:
                continue
            visible_inhabitants.append({
                "id": other.id,
                "name": other.name,
                "position": {"x": other.position.x, "y": other.position.y},
            })

        for position, quantity in sorted(self.world.food.items()):
            if quantity > 0 and inhabitant.position.distance_to(position) <= radius:
                visible_food.append({"position": {"x": position.x, "y": position.y}, "quantity": quantity})

        for position in sorted(self.world.water):
            if inhabitant.position.distance_to(position) <= radius:
                visible_water.append({"x": position.x, "y": position.y})

        return {
            "tick": self.world.tick,
            "self": inhabitant.to_dict(),
            "visible_inhabitants": visible_inhabitants,
            "visible_food": visible_food,
            "visible_water": visible_water,
        }

    def snapshot(self) -> dict[str, Any]:
        random_state = base64.b64encode(pickle.dumps(self._random.getstate())).decode("ascii")
        return {
            "seed": self.seed,
            "next_sequence": self._next_sequence,
            "world": self.world.to_dict(),
            "random_state": random_state,
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> "SimulationEngine":
        engine = cls(World.from_dict(snapshot["world"]), seed=snapshot["seed"])
        engine._next_sequence = snapshot["next_sequence"]
        state = pickle.loads(base64.b64decode(snapshot["random_state"]))
        engine._random.setstate(state)
        return engine

    def snapshot_json(self) -> str:
        return json.dumps(self.snapshot(), sort_keys=True)

    def _resolve(self, proposal: ActionProposal) -> Event:
        actor = self._require_inhabitant(proposal.actor_id)
        if not actor.alive:
            return self._action_failed(proposal, "inhabitant_dead")

        handlers = {
            "move": self._move,
            "eat": self._eat,
            "drink": self._drink,
            "rest": self._rest,
            "speak": self._speak,
        }
        handler = handlers.get(proposal.action_type)
        if handler is None:
            return self._action_failed(proposal, "unknown_action")
        return handler(proposal)

    def _move(self, proposal: ActionProposal) -> Event:
        actor = self._require_inhabitant(proposal.actor_id)
        if proposal.target is None:
            return self._action_failed(proposal, "missing_target")
        if actor.position.distance_to(proposal.target) != 1:
            return self._action_failed(proposal, "target_not_adjacent")
        if not self.world.contains(proposal.target):
            return self._action_failed(proposal, "target_out_of_bounds")
        if proposal.target in self.world.obstacles:
            return self._action_failed(proposal, "target_blocked")
        if self.world.occupied(proposal.target, excluding=actor.id):
            return self._action_failed(proposal, "target_occupied")

        origin = actor.position
        actor.position = proposal.target
        return self._action_succeeded(proposal, {
            "from": {"x": origin.x, "y": origin.y},
            "to": {"x": actor.position.x, "y": actor.position.y},
        })

    def _eat(self, proposal: ActionProposal) -> Event:
        actor = self._require_inhabitant(proposal.actor_id)
        quantity = self.world.food.get(actor.position, 0)
        if quantity <= 0:
            return self._action_failed(proposal, "no_food_here")
        self.world.food[actor.position] = quantity - 1
        actor.hunger = max(0, actor.hunger - 40)
        return self._action_succeeded(proposal, {"hunger": actor.hunger, "remaining_food": quantity - 1})

    def _drink(self, proposal: ActionProposal) -> Event:
        actor = self._require_inhabitant(proposal.actor_id)
        if actor.position not in self.world.water:
            return self._action_failed(proposal, "no_water_here")
        actor.thirst = max(0, actor.thirst - 40)
        return self._action_succeeded(proposal, {"thirst": actor.thirst})

    def _rest(self, proposal: ActionProposal) -> Event:
        actor = self._require_inhabitant(proposal.actor_id)
        actor.fatigue = max(0, actor.fatigue - 35)
        return self._action_succeeded(proposal, {"fatigue": actor.fatigue})

    def _speak(self, proposal: ActionProposal) -> Event:
        actor = self._require_inhabitant(proposal.actor_id)
        if not proposal.recipient_id or proposal.message is None:
            return self._action_failed(proposal, "missing_recipient_or_message")
        recipient = self.world.inhabitants.get(proposal.recipient_id)
        if recipient is None or not recipient.alive:
            return self._action_failed(proposal, "recipient_unavailable")
        if actor.position.distance_to(recipient.position) > 5:
            return self._action_failed(proposal, "recipient_out_of_range")

        message = {
            "sender_id": actor.id,
            "tick": self.world.tick,
            "content": proposal.message,
        }
        recipient.received_messages.append(message)
        return self._action_succeeded(proposal, {
            "recipient_id": recipient.id,
            "sender_position": {"x": actor.position.x, "y": actor.position.y},
            "channel": "speech",
            "message": proposal.message,
        }, event_type="message_delivered")

    def _action_succeeded(self, proposal: ActionProposal, details: dict[str, Any], event_type: str = "action_succeeded") -> Event:
        return self._emit(event_type, {
            "actor_id": proposal.actor_id,
            "action_type": proposal.action_type,
            **details,
        })

    def _action_failed(self, proposal: ActionProposal, reason: str) -> Event:
        return self._emit("action_failed", {
            "actor_id": proposal.actor_id,
            "action_type": proposal.action_type,
            "reason": reason,
        })

    def _emit(self, event_type: str, payload: dict[str, Any]) -> Event:
        event = Event(self._next_sequence, self.world.tick, event_type, payload)
        self._next_sequence += 1
        return event

    def _require_inhabitant(self, inhabitant_id: str) -> Inhabitant:
        try:
            return self.world.inhabitants[inhabitant_id]
        except KeyError as exc:
            raise ValueError(f"Unknown inhabitant: {inhabitant_id}") from exc
