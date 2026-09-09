"""Inhabitant decision coordination and local model integration."""

from __future__ import annotations

import json
import threading
import time
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Protocol
from urllib import request

from .domain import ActionProposal, Position
from .engine import Event, SimulationEngine


class DecisionController(Protocol):
    def decide(self, inhabitant_id: str, perception: dict[str, Any]) -> "DecisionResult":
        """Return an intention, bounded plan, one action, or no decision."""


@dataclass(frozen=True, slots=True)
class PlanProposal:
    actor_id: str
    steps: tuple[ActionProposal, ...]


@dataclass(frozen=True, slots=True)
class IntentionProposal:
    """A persistent goal selected by a controller, not a physical action."""

    actor_id: str
    intention_type: str
    target: Position | None = None
    resource_type: str | None = None
    recipient_id: str | None = None
    signal: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "intention_type": self.intention_type,
            "target": {"x": self.target.x, "y": self.target.y} if self.target else None,
            "resource_type": self.resource_type,
            "recipient_id": self.recipient_id,
            "signal": self.signal,
        }


DecisionResult = ActionProposal | PlanProposal | IntentionProposal | None


@dataclass(frozen=True, slots=True)
class TickResult:
    tick: int
    perceptions: dict[str, dict[str, Any]]
    proposals: tuple[ActionProposal, ...]
    events: tuple[Event, ...]
    model_calls: tuple[dict[str, Any], ...] = ()
    intention_events: tuple[dict[str, Any], ...] = ()


class SimulationRunner:
    """Coordinates the engine barrier without owning world rules."""

    def __init__(
        self,
        engine: SimulationEngine,
        controller: DecisionController,
        on_decision_progress: Callable[[int, int, int], None] | None = None,
        max_decision_workers: int = 5,
    ) -> None:
        self.engine = engine
        self.controller = controller
        self._on_decision_progress = on_decision_progress
        self._max_decision_workers = max(1, max_decision_workers)
        self._active_plans: dict[str, dict[str, Any]] = self._restore_plans()
        self._active_intentions: dict[str, dict[str, Any]] = self._restore_intentions()
        self._intention_events: list[dict[str, Any]] = []

    def run_tick(self) -> TickResult:
        self._intention_events = []
        environmental_events = list(self.engine.advance())
        self._interrupt_dead_inhabitants(environmental_events)
        perceptions: dict[str, dict[str, Any]] = {}
        proposals: list[ActionProposal] = []

        active_ids = [
            inhabitant_id
            for inhabitant_id in sorted(self.engine.world.inhabitants)
            if self.engine.world.inhabitants[inhabitant_id].alive
        ]
        total_decisions = len(active_ids)
        decision_inputs: dict[str, tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any] | None, dict[str, Any] | None, str]] = {}
        decision_futures = {}
        for inhabitant_id in active_ids:
            inhabitant = self.engine.world.inhabitants[inhabitant_id]
            perception = self.engine.perceive(inhabitant_id)
            perceptions[inhabitant_id] = perception
            inhabitant.desires = self._desires_for(inhabitant, perception)
            self._update_spatial_memory(inhabitant, perception)
            self._update_beliefs(inhabitant, perception)
            inhabitant.perception_history.append({
                "tick": perception["tick"],
                "visible_inhabitants": [item["id"] for item in perception["visible_inhabitants"]],
                "visible_food": len(perception["visible_food"]),
                "visible_water": len(perception["visible_water"]),
                "visible_obstacles": len(perception["visible_obstacles"]),
            })
            inhabitant.perception_history = inhabitant.perception_history[-20:]
            self._remember(inhabitant, "perception", inhabitant.perception_history[-1])
            active_plan = self._active_plans.get(inhabitant_id)
            active_intention = self._active_intentions.get(inhabitant_id)
            if active_plan is not None:
                if active_plan.get("observation_signature") is None:
                    active_plan["observation_signature"] = self._observation_signature(perception)
                elif self._plan_interrupted(active_plan, perception, inhabitant):
                    self._finish_plan(inhabitant, "interrupted")
                    active_plan = None
            interruption_reason = (
                self._intention_interruption_reason(active_intention, inhabitant)
                if active_intention is not None
                else None
            )
            if active_intention is not None and interruption_reason is not None:
                self._finish_intention(inhabitant, "interrupted", reason=interruption_reason)
                active_intention = None
            if active_plan is None and active_intention is None:
                homeostasis = self._innate_homeostasis(inhabitant, perception)
                if homeostasis is not None:
                    active_plan = self._new_plan(
                        inhabitant,
                        perception,
                        [homeostasis],
                        "innate_homeostasis",
                    )
                    self._active_plans[inhabitant_id] = active_plan
            decision_context = self._decision_context(inhabitant, perception)
            decision_perception = {
                **perception,
                "action_rules": self._action_rules(perception),
                "cognition": decision_context,
            }
            decision_inputs[inhabitant_id] = (
                inhabitant,
                perception,
                decision_context,
                active_plan,
                active_intention,
                getattr(self.controller, "decision_source", "controller"),
            )
            if active_plan is None and active_intention is None:
                decision_futures[inhabitant_id] = decision_perception

        decisions: dict[str, DecisionResult] = {}
        if decision_futures:
            with ThreadPoolExecutor(
                max_workers=min(len(decision_futures), self._max_decision_workers)
            ) as executor:
                futures = {
                    executor.submit(self.controller.decide, inhabitant_id, decision_perception): inhabitant_id
                    for inhabitant_id, decision_perception in decision_futures.items()
                }
                for future in as_completed(futures):
                    decisions[futures[future]] = future.result()

        for completed_decisions, inhabitant_id in enumerate(active_ids, start=1):
            inhabitant, perception, decision_context, active_plan, active_intention, decision_source = decision_inputs[inhabitant_id]
            selected_intention = None
            if active_plan is None and active_intention is None:
                decision = decisions.get(inhabitant_id)
                if isinstance(decision, IntentionProposal):
                    selected_intention = decision
                    active_intention = self._new_intention(inhabitant, perception, decision, decision_source)
                    self._active_intentions[inhabitant_id] = active_intention
                    decision_source = "model_intention"
                    if decision.intention_type == "wait":
                        self._finish_intention(inhabitant, "succeeded", reason="wait_selected")
                        active_intention = None
                steps = self._steps_from(decision)
                if active_intention is None and selected_intention is None and not steps:
                    homeostasis = self._innate_homeostasis(inhabitant, perception)
                    if homeostasis is not None:
                        steps = [homeostasis]
                        decision_source = "innate_homeostasis"
                if active_intention is None and selected_intention is None and not steps:
                    exploration = self._innate_exploration(inhabitant, perception)
                    if exploration is not None:
                        steps = [exploration]
                        decision_source = "innate_exploration"
                if active_intention is None and steps:
                    steps[0] = self._legalize_first_step(inhabitant, perception, steps[0])
                active_plan = self._new_plan(inhabitant, perception, steps, decision_source) if active_intention is None and steps else None
                if active_plan is not None:
                    self._active_plans[inhabitant_id] = active_plan
            elif active_intention is not None:
                decision_source = "intention_continuation"
            else:
                decision_source = (
                    active_plan["source"]
                    if active_plan["created_tick"] == perception["tick"]
                    else "plan_continuation"
                )

            proposal = (
                self._action_for_intention(inhabitant, active_intention, decision_source)
                if active_intention is not None
                else self._next_proposal(active_plan, decision_source)
            )
            if active_intention is not None and proposal is None:
                self._finish_intention(inhabitant, "interrupted", reason="no_legal_action")
                active_intention = None
            if proposal is None:
                inhabitant.no_action_streak += 1
            else:
                inhabitant.no_action_streak = 0
            inhabitant.last_decision = self._decision_record(
                inhabitant, proposal, decision_context, selected_intention
            )
            if active_plan is not None and proposal is not None:
                inhabitant.current_plan = [self._plan_view(active_plan, proposal, decision_source)]
            elif active_intention is not None:
                inhabitant.current_plan = []
            elif active_intention is None:
                inhabitant.current_plan = [{
                    "created_tick": perception["tick"],
                    "status": "no_action",
                    "request": None,
                }]
            if proposal is not None:
                proposals.append(proposal)
            if self._on_decision_progress is not None:
                self._on_decision_progress(self.engine.world.tick, completed_decisions, total_decisions)
            if getattr(self.controller, "infrastructure_failure", False):
                break

        action_events = self.engine.resolve(proposals)
        self._record_action_results(action_events)
        model_calls = tuple(self.controller.drain_calls()) if hasattr(self.controller, "drain_calls") else ()
        return TickResult(
            tick=self.engine.world.tick,
            perceptions=perceptions,
            proposals=tuple(proposals),
            events=tuple(environmental_events) + action_events,
            model_calls=model_calls,
            intention_events=tuple(self._intention_events),
        )

    def _interrupt_dead_inhabitants(self, events: list[Event]) -> None:
        for event in events:
            if event.event_type != "inhabitant_died":
                continue
            inhabitant = self.engine.world.inhabitants[event.payload["inhabitant_id"]]
            self._finish_plan(inhabitant, "interrupted", event)
            self._finish_intention(inhabitant, "interrupted", event, "inhabitant_died")

    def _record_action_results(self, events: list[Event] | tuple[Event, ...]) -> None:
        for event in events:
            actor_id = event.payload.get("actor_id")
            inhabitant = self.engine.world.inhabitants.get(actor_id)
            if inhabitant is None:
                continue
            self._remember(inhabitant, "action_result", event.to_dict())
            self._complete_plan(inhabitant, event)
            self._complete_intention(inhabitant, event)
            self._learn_from_action(inhabitant, event)

    def _complete_plan(self, inhabitant: Any, event: Event) -> None:
        plan = self._active_plans.get(inhabitant.id)
        if plan is None or plan.get("plan_id") != event.payload.get("plan_id"):
            return
        if event.event_type not in {"action_succeeded", "message_delivered"}:
            self._finish_plan(inhabitant, "failed", event)
            return
        if plan["steps"]:
            plan["last_request"] = self._next_proposal(plan, event.payload.get("decision_source", "controller")).to_dict()
        plan["steps"] = plan["steps"][1:]
        if plan["steps"]:
            plan["observation_signature"] = None
            inhabitant.current_plan = [self._plan_view(plan, plan["steps"][0], "plan_continuation")]
            return
        self._finish_plan(inhabitant, "succeeded", event)

    def _finish_plan(self, inhabitant: Any, status: str, event: Event | None = None) -> None:
        plan = self._active_plans.pop(inhabitant.id, None)
        if plan is None:
            return
        completed = {
            **self._plan_view(plan, None, plan.get("source", "controller")),
            "status": status,
        }
        if plan.get("last_request") is not None:
            completed["request"] = plan["last_request"]
        if event is not None:
            completed.update({"completed_tick": event.tick, "result_event_sequence": event.sequence})
        inhabitant.current_plan = [completed]

    def _complete_intention(self, inhabitant: Any, event: Event) -> None:
        intention = self._active_intentions.get(inhabitant.id)
        if intention is None or intention["intention_id"] != event.payload.get("intention_id"):
            return
        if event.event_type not in {"action_succeeded", "message_delivered"}:
            self._finish_intention(
                inhabitant,
                "failed",
                event,
                event.payload.get("reason", "action_failed"),
            )
            return
        if intention["proposal"].intention_type == "move_to":
            if inhabitant.position == intention["proposal"].target:
                self._finish_intention(inhabitant, "succeeded", event, "target_reached")
            else:
                distance = inhabitant.position.distance_to(intention["proposal"].target)
                if distance < intention["best_distance"]:
                    intention["best_distance"] = distance
                    intention["no_progress_ticks"] = 0
                else:
                    intention["no_progress_ticks"] += 1
                if intention["no_progress_ticks"] >= 3:
                    self._finish_intention(inhabitant, "interrupted", event, "no_progress")
                    return
                inhabitant.current_intention = self._intention_view(intention, "active")
            return
        self._finish_intention(inhabitant, "succeeded", event, "action_succeeded")

    def _finish_intention(
        self,
        inhabitant: Any,
        status: str,
        event: Event | None = None,
        reason: str | None = None,
    ) -> None:
        intention = self._active_intentions.pop(inhabitant.id, None)
        if intention is None:
            return
        view = self._intention_view(intention, status)
        if event is not None:
            view.update({"completed_tick": event.tick, "result_event_sequence": event.sequence})
        if reason is not None:
            view["reason"] = reason
        inhabitant.current_intention = view
        event_type = {
            "succeeded": "intention_completed",
            "failed": "intention_failed",
            "interrupted": "intention_interrupted",
        }[status]
        self._record_intention_event(inhabitant.id, intention, event_type, reason)

    def _new_intention(
        self,
        inhabitant: Any,
        perception: dict[str, Any],
        proposal: IntentionProposal,
        source: str,
    ) -> dict[str, Any]:
        intention = {
            "intention_id": f"{inhabitant.id}:intention:{perception['tick']}",
            "source": source,
            "created_tick": perception["tick"],
            "proposal": proposal,
            "need_values": {
                "hunger": inhabitant.hunger,
                "thirst": inhabitant.thirst,
                "fatigue": inhabitant.fatigue,
            },
            "best_distance": (
                inhabitant.position.distance_to(proposal.target)
                if proposal.target is not None
                else 0
            ),
            "no_progress_ticks": 0,
        }
        inhabitant.current_intention = SimulationRunner._intention_view(intention, "active")
        self._record_intention_event(inhabitant.id, intention, "intention_started")
        return intention

    def _record_intention_event(
        self,
        inhabitant_id: str,
        intention: dict[str, Any],
        event_type: str,
        reason: str | None = None,
    ) -> None:
        self._intention_events.append({
            "tick": self.engine.world.tick,
            "event_type": event_type,
            "inhabitant_id": inhabitant_id,
            "intention_id": intention["intention_id"],
            "payload": {
                "goal": intention["proposal"].to_dict(),
                "reason": reason,
                "source": intention["source"],
            },
        })

    @staticmethod
    def _intention_view(intention: dict[str, Any], status: str) -> dict[str, Any]:
        return {
            "intention_id": intention["intention_id"],
            "source": intention["source"],
            "created_tick": intention["created_tick"],
            "status": status,
            "goal": intention["proposal"].to_dict(),
            "progress": {
                "best_distance": intention.get("best_distance", 0),
                "no_progress_ticks": intention.get("no_progress_ticks", 0),
            },
        }

    def _action_for_intention(
        self,
        inhabitant: Any,
        intention: dict[str, Any],
        source: str,
    ) -> ActionProposal | None:
        goal = intention["proposal"]
        action: ActionProposal | None = None
        if goal.intention_type == "move_to" and goal.target is not None:
            target = self._next_path_step(inhabitant, goal.target)
            if target is not None:
                action = ActionProposal.move(inhabitant.id, target)
        elif goal.intention_type == "consume":
            if goal.resource_type == "food":
                action = ActionProposal.eat(inhabitant.id)
            elif goal.resource_type == "water":
                action = ActionProposal.drink(inhabitant.id)
        elif goal.intention_type == "rest":
            action = ActionProposal.rest(inhabitant.id)
        elif goal.intention_type == "send_signal" and goal.recipient_id and goal.signal:
            action = ActionProposal.speak(inhabitant.id, goal.recipient_id, goal.signal)
        if action is None:
            return None
        return replace(
            action,
            decision_source=source,
            intention_id=intention["intention_id"],
        )

    def _next_path_step(self, inhabitant: Any, destination: Position) -> Position | None:
        if inhabitant.position == destination or not self.engine.world.contains(destination):
            return None
        occupied = {
            other.position
            for other in self.engine.world.inhabitants.values()
            if other.alive and other.id != inhabitant.id
        }
        candidates = []
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            target = Position(inhabitant.position.x + dx, inhabitant.position.y + dy)
            if not self.engine.world.contains(target):
                continue
            if target in self.engine.world.obstacles or target in occupied:
                continue
            memory = inhabitant.spatial_memory.get(self._location_key(target), {})
            candidates.append((
                target.distance_to(destination),
                memory.get("visit_count", 0),
                target.x,
                target.y,
                target,
            ))
        return min(candidates)[-1] if candidates else None

    @staticmethod
    def _intention_interruption_reason(intention: dict[str, Any], inhabitant: Any) -> str | None:
        previous = intention.get("need_values", {})
        for name, value in (
            ("hunger", inhabitant.hunger),
            ("thirst", inhabitant.thirst),
            ("fatigue", inhabitant.fatigue),
        ):
            if previous.get(name, 0) < 80 <= value:
                return f"critical_{name}"
        return None

    @staticmethod
    def _steps_from(decision: DecisionResult) -> list[ActionProposal]:
        if isinstance(decision, PlanProposal):
            return list(decision.steps[:8])
        if isinstance(decision, ActionProposal):
            return [decision]
        return []

    @staticmethod
    def _new_plan(
        inhabitant: Any,
        perception: dict[str, Any],
        steps: list[ActionProposal],
        source: str,
    ) -> dict[str, Any]:
        plan_id = f"{inhabitant.id}:{perception['tick']}"
        return {
            "plan_id": plan_id,
            "source": source,
            "created_tick": perception["tick"],
            "steps": [replace(step, decision_source=source, plan_id=plan_id) for step in steps],
            "observation_signature": SimulationRunner._observation_signature(perception),
            "need_values": {
                "hunger": inhabitant.hunger,
                "thirst": inhabitant.thirst,
                "fatigue": inhabitant.fatigue,
            },
        }

    @staticmethod
    def _next_proposal(plan: dict[str, Any] | None, source: str) -> ActionProposal | None:
        if plan is None or not plan["steps"]:
            return None
        return replace(plan["steps"][0], decision_source=source, plan_id=plan["plan_id"])

    @staticmethod
    def _plan_view(plan: dict[str, Any], proposal: ActionProposal | None, source: str) -> dict[str, Any]:
        return {
            "plan_id": plan["plan_id"],
            "source": source,
            "created_tick": plan["created_tick"],
            "status": "pending" if proposal is not None else "active",
            "request": proposal.to_dict() if proposal is not None else None,
            "steps_remaining": [step.to_dict() for step in plan["steps"]],
        }

    @classmethod
    def _plan_interrupted(cls, plan: dict[str, Any], perception: dict[str, Any], inhabitant: Any) -> bool:
        if plan.get("observation_signature") is not None and plan.get("observation_signature") != cls._observation_signature(perception):
            return True
        previous = plan.get("need_values", {})
        return any(
            previous.get(name, 0) < 80 <= value
            for name, value in (("hunger", inhabitant.hunger), ("thirst", inhabitant.thirst), ("fatigue", inhabitant.fatigue))
        )

    @staticmethod
    def _observation_signature(perception: dict[str, Any]) -> tuple[Any, ...]:
        return (
            tuple((item["position"]["x"], item["position"]["y"], item["quantity"]) for item in perception["visible_food"]),
            tuple((item["x"], item["y"]) for item in perception["visible_water"]),
            tuple((item["x"], item["y"]) for item in perception.get("visible_obstacles", [])),
            tuple((item["id"], item["position"]["x"], item["position"]["y"]) for item in perception["visible_inhabitants"]),
        )

    def _restore_plans(self) -> dict[str, dict[str, Any]]:
        plans = {}
        for inhabitant in self.engine.world.inhabitants.values():
            current = inhabitant.current_plan[-1] if inhabitant.current_plan else None
            if not current or current.get("status") != "active":
                continue
            steps = [self._action_from_dict(step) for step in current.get("steps_remaining", [])]
            if steps:
                plans[inhabitant.id] = {
                    "plan_id": current["plan_id"],
                    "source": current.get("source", "controller"),
                    "created_tick": current["created_tick"],
                    "steps": steps,
                    "observation_signature": None,
                    "need_values": {},
                }
        return plans

    def _restore_intentions(self) -> dict[str, dict[str, Any]]:
        intentions = {}
        for inhabitant in self.engine.world.inhabitants.values():
            current = inhabitant.current_intention
            if not current or current.get("status") != "active":
                continue
            goal = current.get("goal", {})
            target = goal.get("target")
            proposal = IntentionProposal(
                actor_id=inhabitant.id,
                intention_type=goal["intention_type"],
                target=Position(target["x"], target["y"]) if target else None,
                resource_type=goal.get("resource_type"),
                recipient_id=goal.get("recipient_id"),
                signal=goal.get("signal"),
            )
            intentions[inhabitant.id] = {
                "intention_id": current["intention_id"],
                "source": current.get("source", "controller"),
                "created_tick": current["created_tick"],
                "proposal": proposal,
                "need_values": {},
                "best_distance": current.get("progress", {}).get(
                    "best_distance",
                    inhabitant.position.distance_to(proposal.target) if proposal.target else 0,
                ),
                "no_progress_ticks": current.get("progress", {}).get("no_progress_ticks", 0),
            }
        return intentions

    @staticmethod
    def _action_from_dict(data: dict[str, Any]) -> ActionProposal:
        target = data.get("target")
        return ActionProposal(
            actor_id=data["actor_id"],
            action_type=data["action_type"],
            target=Position(target["x"], target["y"]) if target else None,
            recipient_id=data.get("recipient_id"),
            message=data.get("message"),
            decision_source=data.get("decision_source", "controller"),
            plan_id=data.get("plan_id"),
            intention_id=data.get("intention_id"),
        )

    @staticmethod
    def _learn_from_action(inhabitant: Any, event: Event) -> None:
        reason = event.payload.get("reason")
        action_type = event.payload.get("action_type")
        location = f"{inhabitant.position.x},{inhabitant.position.y}"
        memory = inhabitant.spatial_memory.setdefault(location, {
            "visit_count": 0,
            "last_observed_tick": event.tick,
        })
        memory["last_observed_tick"] = event.tick
        memory["confidence"] = 0.95
        memory["source"] = "failed_action"
        if reason == "no_food_here" and action_type == "eat":
            memory["food"] = {"present": False, "quantity": 0}
            SimulationRunner._update_belief(inhabitant, f"food_at:{inhabitant.position.x},{inhabitant.position.y}", False, .95, "failed_action", event.tick)
        if reason == "no_water_here" and action_type == "drink":
            memory["water"] = {"present": False}
            SimulationRunner._update_belief(inhabitant, f"water_at:{inhabitant.position.x},{inhabitant.position.y}", False, .95, "failed_action", event.tick)

    @staticmethod
    def _decision_record(
        inhabitant: Any,
        proposal: ActionProposal | None,
        context: dict[str, Any],
        intention: IntentionProposal | None = None,
    ) -> dict[str, Any]:
        return {
            "actor_id": inhabitant.id,
            "tick": context["tick"],
            "action_type": proposal.action_type if proposal is not None else "none",
            "proposal": proposal.to_dict() if proposal is not None else None,
            "intention": intention.to_dict() if intention is not None else None,
            "desires": dict(context["desires"]),
            "beliefs": dict(context["beliefs"]),
            "retrieved_memory_ids": [memory["id"] for memory in context["memories"]],
        }

    @staticmethod
    def _decision_context(inhabitant: Any, perception: dict[str, Any]) -> dict[str, Any]:
        return {
            "tick": perception["tick"],
            "desires": dict(inhabitant.desires),
            "instincts": dict(inhabitant.instincts),
            "motivations": SimulationRunner._motivations_for(inhabitant, perception),
            "need_priorities": SimulationRunner._need_priorities(inhabitant),
            "beliefs": dict(inhabitant.beliefs),
            "spatial_memory": dict(list(inhabitant.spatial_memory.items())[-20:]),
            "memories": SimulationRunner._retrieve_memories(inhabitant, perception),
            "recent_action_results": SimulationRunner._recent_action_results(inhabitant),
            "current_plan": list(inhabitant.current_plan),
            "current_intention": inhabitant.current_intention,
        }

    @staticmethod
    def _need_priorities(inhabitant: Any) -> list[dict[str, Any]]:
        needs = [("hunger", inhabitant.hunger), ("thirst", inhabitant.thirst), ("fatigue", inhabitant.fatigue)]
        return [
            {
                "need": name,
                "value": value,
                "urgency": SimulationRunner._urgency_for(value),
            }
            for name, value in sorted(needs, key=lambda item: (-item[1], item[0]))
        ]

    @staticmethod
    def _urgency_for(value: int) -> str:
        if value >= 80:
            return "critical"
        if value >= 50:
            return "high"
        if value >= 20:
            return "rising"
        return "low"

    @staticmethod
    def _recent_action_results(inhabitant: Any, limit: int = 5) -> list[dict[str, Any]]:
        results = []
        for memory in reversed(inhabitant.memories):
            if memory.get("type") != "action_result":
                continue
            content = memory.get("content", {})
            payload = content.get("payload", {})
            results.append({
                "tick": content.get("tick"),
                "action_type": payload.get("action_type"),
                "outcome": "failed" if content.get("event_type") == "action_failed" else "succeeded",
                "reason": payload.get("reason"),
            })
            if len(results) == limit:
                break
        return results

    @staticmethod
    def _action_rules(perception: dict[str, Any]) -> dict[str, Any]:
        occupied = [
            item["position"]
            for item in perception["visible_inhabitants"]
            if item["id"] != perception["self"]["id"]
        ]
        return {
            "need_scale": "Needs range from 0 to 100; reaching 100 causes death.",
            "move_to": "Choose any in-bounds destination. The runtime finds legal adjacent steps and the engine validates each one.",
            "consume": "Choose food or water; it succeeds only when that resource is at the current position.",
            "rest": "Reduces fatigue only; it does not reduce hunger or thirst.",
            "send_signal": "Emits an opaque signal only to a visible inhabitant within communication range; use sig- followed by invented characters.",
            "wait": "Changes nothing; needs continue to increase on the next tick.",
            "visible_occupied_positions": occupied,
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
        for message in inhabitant.received_messages[-5:]:
            signal = message.get("signal", message.get("content"))
            if signal:
                cls._update_belief(
                    inhabitant,
                    f"signal:{signal}",
                    {"meaning": None, "sender_id": message.get("sender_id")},
                    .1,
                    "received_signal",
                    tick,
                )

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
    def _desires_for(inhabitant: Any, perception: dict[str, Any]) -> dict[str, int]:
        visible_resource = bool(perception["visible_food"] or perception["visible_water"])
        return {
            "reduce_hunger": inhabitant.hunger,
            "reduce_thirst": inhabitant.thirst,
            "reduce_fatigue": inhabitant.fatigue,
            "explore_unknown": 0 if visible_resource else min(100, 10 + inhabitant.no_action_streak * 10),
            "avoid_danger": min(100, len(SimulationRunner._recent_action_results(inhabitant)) * 10),
            "social_curiosity": min(
                100,
                len(perception["visible_inhabitants"]) * 5 + len(inhabitant.received_messages) * 10,
            ),
        }

    @staticmethod
    def _motivations_for(inhabitant: Any, perception: dict[str, Any]) -> dict[str, Any]:
        recent_failures = [
            result for result in SimulationRunner._recent_action_results(inhabitant)
            if result["outcome"] == "failed"
        ]
        return {
            "homeostasis": {
                "hunger": inhabitant.hunger,
                "thirst": inhabitant.thirst,
                "fatigue": inhabitant.fatigue,
            },
            "exploration": {
                "pressure": inhabitant.desires["explore_unknown"],
                "resource_visible": bool(perception["visible_food"] or perception["visible_water"]),
                "no_action_streak": inhabitant.no_action_streak,
            },
            "danger_avoidance": {
                "pressure": inhabitant.desires["avoid_danger"],
                "recent_failures": recent_failures[-3:],
            },
            "persistence": {
                "pressure": inhabitant.instincts.get("persistence", 0.5),
                "current_plan": bool(inhabitant.current_plan),
            },
            "social_curiosity": {
                "pressure": inhabitant.desires["social_curiosity"],
                "visible_inhabitants": len(perception["visible_inhabitants"]),
                "received_signals": len(inhabitant.received_messages),
            },
        }

    def _innate_exploration(self, inhabitant: Any, perception: dict[str, Any]) -> ActionProposal | None:
        if inhabitant.no_action_streak < 1:
            return None
        if perception["visible_food"] or perception["visible_water"]:
            return None

        occupied = {
            (item["position"]["x"], item["position"]["y"])
            for item in perception["visible_inhabitants"]
            if item["id"] != inhabitant.id
        }
        obstacles = {
            (item["x"], item["y"])
            for item in perception.get("visible_obstacles", [])
        }
        directions = ((1, 0), (0, 1), (-1, 0), (0, -1))
        candidates = []
        for dx, dy in directions:
            target = Position(inhabitant.position.x + dx, inhabitant.position.y + dy)
            if not self.engine.world.contains(target):
                continue
            if (target.x, target.y) in occupied or (target.x, target.y) in obstacles:
                continue
            memory = inhabitant.spatial_memory.get(self._location_key(target), {})
            age = perception["tick"] - memory.get("last_observed_tick", perception["tick"])
            candidates.append((
                2 if not memory else 0,
                1 if age >= 10 else 0,
                -memory.get("visit_count", 0),
                target,
            ))
        if not candidates:
            return None
        return ActionProposal.move(inhabitant.id, max(candidates, key=lambda item: item[:3])[3])

    def _innate_homeostasis(self, inhabitant: Any, perception: dict[str, Any]) -> ActionProposal | None:
        hunger = inhabitant.hunger
        thirst = inhabitant.thirst
        food_here = any(item["position"] == {
            "x": inhabitant.position.x,
            "y": inhabitant.position.y,
        } for item in perception["visible_food"])
        water_here = any(
            item == {"x": inhabitant.position.x, "y": inhabitant.position.y}
            for item in perception["visible_water"]
        )
        if food_here and hunger >= thirst and hunger >= 20:
            return ActionProposal.eat(inhabitant.id)
        if water_here and thirst > hunger and thirst >= 20:
            return ActionProposal.drink(inhabitant.id)

        return None

    @staticmethod
    def _step_toward(origin: Position, target: Position) -> Position:
        x, y = origin.x, origin.y
        if target.x != x:
            x += 1 if target.x > x else -1
        elif target.y != y:
            y += 1 if target.y > y else -1
        return Position(x, y)

    def _legalize_first_step(
        self,
        inhabitant: Any,
        perception: dict[str, Any],
        proposal: ActionProposal,
    ) -> ActionProposal:
        if proposal.action_type != "move" or proposal.target is None:
            return proposal
        if inhabitant.position.distance_to(proposal.target) == 1:
            return proposal
        target = self._step_toward(inhabitant.position, proposal.target)
        return replace(proposal, target=target)

    @staticmethod
    def _location_key(position: Position) -> str:
        return f"{position.x},{position.y}"

    def _update_spatial_memory(self, inhabitant: Any, perception: dict[str, Any]) -> None:
        tick = perception["tick"]
        visible_food = {
            self._location_key(Position(item["position"]["x"], item["position"]["y"])): item["quantity"]
            for item in perception["visible_food"]
        }
        visible_water = {
            self._location_key(Position(item["x"], item["y"]))
            for item in perception["visible_water"]
        }
        visible_obstacles = {
            self._location_key(Position(item["x"], item["y"]))
            for item in perception.get("visible_obstacles", [])
        }
        positions = set()
        for x in range(inhabitant.position.x - 3, inhabitant.position.x + 4):
            for y in range(inhabitant.position.y - 3, inhabitant.position.y + 4):
                position = Position(x, y)
                if self.engine.world.contains(position) and inhabitant.position.distance_to(position) <= 3:
                    positions.add(self._location_key(position))
        positions.update(visible_food)
        positions.update(visible_water)
        positions.update(visible_obstacles)
        for item in perception["visible_inhabitants"]:
            positions.add(self._location_key(Position(item["position"]["x"], item["position"]["y"])))

        for location in positions:
            record = inhabitant.spatial_memory.setdefault(location, {
                "visit_count": 0,
                "last_observed_tick": tick,
            })
            x, y = (int(value) for value in location.split(","))
            if (x, y) == (inhabitant.position.x, inhabitant.position.y):
                record["visit_count"] = record.get("visit_count", 0) + 1
            record.update({
                "last_observed_tick": tick,
                "food": {"present": location in visible_food, "quantity": visible_food.get(location, 0)},
                "water": {"present": location in visible_water},
                "obstacle": location in visible_obstacles,
                "confidence": 0.9,
                "source": "perception",
            })

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
        max_decision_workers: int = 5,
    ) -> None:
        self._engine_factory = engine_factory
        self._controller_factory = controller_factory
        self._tick_interval = tick_interval
        self._on_tick = on_tick
        self._on_reset = on_reset
        self._max_decision_workers = max(1, max_decision_workers)
        self._lock = threading.RLock()
        self._simulation_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.engine = engine_factory()
        self._runner = SimulationRunner(
            self.engine,
            controller_factory(),
            self._report_progress,
            self._max_decision_workers,
        )
        self._status = "stopped"
        self._error: str | None = None
        self._generation = 0
        self._decision_progress = {"tick": 0, "completed": 0, "total": 0}
        self._published_world = self.engine.world.to_dict()
        self._published_events: list[dict[str, Any]] = []

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    @property
    def decision_progress(self) -> dict[str, int]:
        with self._lock:
            return dict(self._decision_progress)

    def observer_state(self, recent_event_limit: int = 100) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self._status,
                "error": self._error,
                "world": deepcopy(self._published_world),
                "events": deepcopy(self._published_events[-recent_event_limit:]),
                "decision_progress": dict(self._decision_progress),
            }

    def start(self) -> bool:
        with self._lock:
            if self._status == "running" or (self._thread is not None and self._thread.is_alive()):
                return False
            if self.engine.is_extinct:
                return False
            self._stop_event.clear()
            self._error = None
            self._decision_progress = {"tick": self.engine.world.tick, "completed": 0, "total": 0}
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
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join()
        with self._simulation_lock:
            with self._lock:
                self._generation += 1
                self.engine = self._engine_factory()
                self._runner = SimulationRunner(
                    self.engine,
                    self._controller_factory(),
                    self._report_progress,
                    self._max_decision_workers,
                )
                self._status = "stopped"
                self._error = None
                self._decision_progress = {"tick": 0, "completed": 0, "total": 0}
                self._published_world = self.engine.world.to_dict()
                self._published_events = []
                self._thread = None
                if self._on_reset is not None:
                    self._on_reset(self.engine)

    def _report_progress(self, tick: int, completed: int, total: int) -> None:
        with self._lock:
            self._decision_progress = {"tick": tick, "completed": completed, "total": total}

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                with self._lock:
                    if self._status != "running":
                        return
                    generation = self._generation
                    runner = self._runner
                with self._simulation_lock:
                    result = runner.run_tick()
                    with self._lock:
                        if generation != self._generation or self._status != "running":
                            return
                        if self._on_tick is not None:
                            self._on_tick(self.engine, result)
                        self._published_world = self.engine.world.to_dict()
                        self._published_events = [event.to_dict() for event in self.engine.events]
                        if any(call.get("outcome") == "transport_error" for call in result.model_calls):
                            self._error = "Ollama became unavailable during the decision barrier"
                            self._status = "error"
                            return
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

    decision_source = "scripted_decision"

    def decide(self, inhabitant_id: str, perception: dict[str, Any]) -> DecisionResult:
        return self._decisions.get(perception["tick"], {}).get(inhabitant_id)


@dataclass(frozen=True, slots=True)
class OllamaConfig:
    model: str = "gemma4:e2b"
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 30.0
    think: bool = False
    max_output_tokens: int = 128


class OllamaController:
    """Turns local Ollama JSON responses into persistent intentions."""

    def __init__(
        self,
        config: OllamaConfig | None = None,
        transport: Callable[[str, bytes, float], bytes] | None = None,
    ) -> None:
        self.config = config or OllamaConfig()
        self._transport = transport or self._post
        self._calls: list[dict[str, Any]] = []
        self._calls_lock = threading.Lock()
        self._infrastructure_failure = False

    decision_source = "model_decision"

    @property
    def infrastructure_failure(self) -> bool:
        return self._infrastructure_failure

    def decide(self, inhabitant_id: str, perception: dict[str, Any]) -> DecisionResult:
        payload = {
            "model": self.config.model,
            "stream": False,
            "think": self.config.think,
            "keep_alive": -1,
            "options": {
                "temperature": 0,
                "top_p": 0.95,
                "top_k": 64,
                "num_predict": self.config.max_output_tokens,
            },
            "format": {
                "type": "object",
                "properties": {
                    "intention": OllamaController._intention_schema(),
                },
                "required": ["intention"],
                "additionalProperties": False,
            },
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Choose one persistent intention: move_to, consume, rest, send_signal, or wait. "
                        "Return compact one-line JSON and no explanation. For move_to, choose the meaningful destination; "
                        "the runtime handles legal adjacent steps. "
                        "Send only an opaque signal such as sig-ka17; never use natural-language words. "
                        "Need values run from 0 to 100 and 100 causes death. Rest only reduces fatigue. "
                        "Consume requires the chosen resource at the current position. "
                        "When no needed resource is visible, movement can reveal new observations; doing nothing leaves needs rising. "
                        "Use exploration pressure to choose an in-bounds, currently unoccupied destination when no needed resource is visible. "
                        "Use memory and recent failures to avoid depleted or dangerous destinations."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "inhabitant_id": inhabitant_id,
                            "perception": self._compact_perception(perception),
                        },
                        separators=(",", ":"),
                    ),
                },
            ],
        }
        call = {
            "inhabitant_id": inhabitant_id,
            "tick": perception.get("tick"),
            "model": self.config.model,
            "request": payload,
        }
        try:
            response = self._transport(
                f"{self.config.base_url.rstrip('/')}/api/chat",
                json.dumps(payload).encode("utf-8"),
                self.config.timeout_seconds,
            )
            outer = json.loads(response)
            content = outer["message"]["content"]
            data = json.loads(content)
            result = self._decision_from_json(inhabitant_id, data)
            if isinstance(result, IntentionProposal):
                outcome = "wait" if result.intention_type == "wait" else "intention"
            else:
                outcome = "invalid_intention"
            call.update({"outcome": outcome, "response": outer})
            return result
        except OSError as error:
            self._infrastructure_failure = True
            call.update({"outcome": "transport_error", "error": str(error)})
            return None
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            call.update({"outcome": "invalid_response", "error": str(error)})
            return None
        finally:
            with self._calls_lock:
                self._calls.append(call)

    def drain_calls(self) -> tuple[dict[str, Any], ...]:
        with self._calls_lock:
            calls = tuple(self._calls)
            self._calls.clear()
        return calls

    @staticmethod
    def _intention_schema() -> dict[str, Any]:
        return {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "type": {"const": "move_to"},
                        "target_x": {"type": "integer"},
                        "target_y": {"type": "integer"},
                    },
                    "required": ["type", "target_x", "target_y"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "type": {"const": "consume"},
                        "resource": {"enum": ["food", "water"]},
                    },
                    "required": ["type", "resource"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {"type": {"enum": ["rest", "wait"]}},
                    "required": ["type"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "type": {"const": "send_signal"},
                        "recipient_id": {"type": "string"},
                        "signal": {"type": "string", "pattern": "^sig-[a-z0-9-]{2,24}$"},
                    },
                    "required": ["type", "recipient_id", "signal"],
                    "additionalProperties": False,
                },
            ]
        }

    @staticmethod
    def _compact_perception(perception: dict[str, Any]) -> dict[str, Any]:
        if "self" not in perception:
            return perception
        cognition = perception.get("cognition", {})
        compact_cognition = {
            "need_priorities": cognition.get("need_priorities", []),
            "instincts": cognition.get("instincts", {}),
            "motivations": cognition.get("motivations", {}),
            "beliefs": dict(list(cognition.get("beliefs", {}).items())[-8:]),
            "spatial_memory": dict(list(cognition.get("spatial_memory", {}).items())[-12:]),
            "recent_action_results": cognition.get("recent_action_results", [])[-3:],
            "current_intention": cognition.get("current_intention"),
        }
        compact_self = {
            key: perception["self"][key]
            for key in ("id", "position", "hunger", "thirst", "fatigue", "received_messages")
            if key in perception["self"]
        }
        compact_rules = {
            key: value
            for key, value in perception.get("action_rules", {}).items()
            if key in {"move_to", "consume", "rest", "send_signal", "wait", "visible_occupied_positions"}
        }
        return {
            "tick": perception["tick"],
            "bounds": perception.get("bounds"),
            "self": compact_self,
            "visible_inhabitants": [
                {"id": item["id"], "position": item["position"]}
                for item in perception.get("visible_inhabitants", [])
            ],
            "visible_food": perception.get("visible_food", []),
            "visible_water": perception.get("visible_water", []),
            "visible_obstacles": perception.get("visible_obstacles", []),
            "action_rules": compact_rules,
            "cognition": compact_cognition,
        }

    @staticmethod
    def _decision_from_json(inhabitant_id: str, data: dict[str, Any]) -> DecisionResult:
        intention = data.get("intention")
        if not isinstance(intention, dict):
            return None
        intention_type = intention.get("type")
        if intention_type == "move_to":
            if not isinstance(intention.get("target_x"), int) or not isinstance(intention.get("target_y"), int):
                return None
            return IntentionProposal(
                inhabitant_id,
                intention_type,
                target=Position(intention["target_x"], intention["target_y"]),
            )
        if intention_type == "consume" and intention.get("resource") in {"food", "water"}:
            return IntentionProposal(inhabitant_id, intention_type, resource_type=intention["resource"])
        if intention_type in {"rest", "wait"}:
            return IntentionProposal(inhabitant_id, intention_type)
        if intention_type == "send_signal":
            recipient_id = intention.get("recipient_id")
            signal = intention.get("signal")
            if isinstance(recipient_id, str) and isinstance(signal, str):
                return IntentionProposal(
                    inhabitant_id,
                    intention_type,
                    recipient_id=recipient_id,
                    signal=signal,
                )
        return None

    @staticmethod
    def _post(url: str, body: bytes, timeout: float) -> bytes:
        http_request = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with request.urlopen(http_request, timeout=timeout) as response:
            return response.read()
