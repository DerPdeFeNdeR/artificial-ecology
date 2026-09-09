"""Core simulation package for Artificial Ecology."""

from .domain import ActionProposal, Inhabitant, Position, World
from .analysis import summarize_intentions
from .engine import Event, SimulationEngine
from .runtime import IntentionProposal, OllamaConfig, OllamaController, PlanProposal, ScriptedController, SimulationRunner, SimulationSession, TickResult
from .observer import ObserverView, create_server
from .persistence import ReplayMismatch, SQLiteStore, verify_replay

__all__ = [
    "ActionProposal",
    "Event",
    "Inhabitant",
    "IntentionProposal",
    "OllamaConfig",
    "OllamaController",
    "PlanProposal",
    "ObserverView",
    "Position",
    "ReplayMismatch",
    "ScriptedController",
    "SQLiteStore",
    "SimulationEngine",
    "SimulationRunner",
    "SimulationSession",
    "TickResult",
    "World",
    "create_server",
    "summarize_intentions",
    "verify_replay",
]
