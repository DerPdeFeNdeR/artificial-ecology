# ADR: Overall Simulation Architecture

- Date: 2026-09-08
- Status: accepted
- Area: system architecture

## Context

Artificial Ecology needs to support open-ended behavior, deterministic replay, local LLM inference, experimentation, and later observer tooling. The design is still expected to evolve, so the initial structure should keep boundaries clear without introducing unnecessary deployment complexity.

## Decision

Build a modular monolith with a deterministic simulation engine, SQLite persistence, a replaceable local-model adapter, and a read-only observer layer.

The core authority boundary is:

```text
Inhabitant runtime → action proposal → engine validation → world event
```

The simulation engine owns authoritative world state and consequences. Inhabitant runtimes own perception, beliefs, desires, memory, planning, communication, and model interaction. The LLM cannot directly mutate world state.

The simulation loop will use explicit phases:

1. advance environmental processes
2. generate perceptions
3. retrieve relevant memories
4. request inhabitant decisions
5. validate action proposals
6. resolve consequences
7. emit events
8. update inhabitant memory and beliefs
9. persist state

SQLite will store events, snapshots, inhabitant state, memories, beliefs, conversations, lineage, experiment metadata, model versions, prompts, and decisions. LLM outputs will be recorded and reused during replay rather than regenerated.

## Rationale

- A modular monolith keeps development and deployment simple while the domain is changing.
- A deterministic engine protects physical rules and makes experiments reproducible.
- Explicit action proposals prevent the LLM from bypassing simulation mechanics.
- SQLite is sufficient for the initial scale and supports structured queries, transactions, snapshots, and replay.
- A model adapter allows Ollama and `gemma4:e2b` to be replaced without changing the simulation.
- A read-only observer prevents analysis tools from accidentally changing the world.

## Consequences

- The engine must not depend on the LLM provider.
- Inhabitant observations must be filtered rather than copied from full world state.
- Replay requires storing model inputs and outputs, not only final actions.
- The observer may use analytical labels that are not exposed to simulation inhabitants.
- Microservices, ECS, and game-engine dependencies are deferred until profiling or product requirements justify them.

## Revisit when

Reconsider this architecture if profiling shows that the modular monolith cannot meet experiment throughput, if persistence exceeds SQLite’s practical limits, or if observer and simulation workloads require independent scaling.
