"""Core simulation package for Artificial Ecology."""

from .domain import ActionProposal, Inhabitant, Position, World
from .engine import Event, SimulationEngine
from .runtime import OllamaConfig, OllamaController, ScriptedController, SimulationRunner, TickResult
from .observer import ObserverView, create_server
from .persistence import ReplayMismatch, SQLiteStore, verify_replay

__all__ = [
    "ActionProposal",
    "Event",
    "Inhabitant",
    "OllamaConfig",
    "OllamaController",
    "ObserverView",
    "Position",
    "ReplayMismatch",
    "ScriptedController",
    "SQLiteStore",
    "SimulationEngine",
    "SimulationRunner",
    "TickResult",
    "World",
    "create_server",
    "verify_replay",
]
