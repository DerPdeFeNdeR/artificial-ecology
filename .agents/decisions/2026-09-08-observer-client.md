# Decision: Observer Client Progression

- Date: 2026-09-08
- Status: accepted
- Area: observer interface

## Decision

Start with a browser-based observer client and defer a Godot client until the simulation and observer protocol are mature.

The browser client will remain a separate read-oriented client rather than becoming part of the simulation engine. A future Godot client should consume the same state and event protocol.

## Rationale

- Browser tooling is faster to build and iterate during early development.
- It supports maps, inspection panels, timelines, metrics, and replay without requiring a game-engine workflow.
- Separating the client from the engine preserves the option to add Godot later without rewriting simulation rules or persistence.
- Early browser development will clarify which visual interactions are actually valuable before adding a richer 2D engine.

## Consequences

- The observer interface needs a stable state and event representation.
- The Python simulation remains authoritative.
- Godot is deferred, not excluded.
- The observer should avoid browser-specific assumptions in the underlying simulation protocol.

## Revisit when

Consider Godot when the project needs richer animation, spatial interaction, sound, or game-like presentation that the browser observer cannot provide efficiently.
