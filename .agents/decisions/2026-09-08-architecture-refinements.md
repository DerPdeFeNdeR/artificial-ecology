# ADR: Architecture Refinements Before Implementation

- Date: 2026-09-08
- Status: accepted
- Area: reproducibility and experimental validity

## Decision

Refine the initial architecture with five rules:

1. The simulation pauses at each decision barrier until all scheduled inhabitant decisions are available or an explicit infrastructure failure is recorded.
2. Conflict resolution uses seeded per-tick ordering or an explicit system rule; model completion order never determines outcomes.
3. Replay distinguishes playback, verification, and branching. Checkpoints include memories, beliefs, active activities, pending messages, scheduler state, random-generator state, and model inputs and outputs.
4. Inhabitant prompts describe capabilities and observations, not hidden facts revealed by the current world state. The engine validates all proposals.
5. The first milestone uses scripted controllers and multiple seeds before relying on LLM behavior.

## Context

The project studies emergence while using a pretrained local model. LLM latency, prior knowledge, hidden information leaks, and non-reproducible replay could otherwise be mistaken for ecological or social effects.

## Rationale

These rules preserve a fixed simulated clock, keep physical authority in the engine, and make it possible to distinguish model priors from learning within the world.

## Consequences

- A slow or unavailable model can pause a run or produce an explicit failed experiment; it cannot silently alter simulated time.
- The first milestone has a smaller scope but stronger validation.
- Model quality and emergence claims require comparisons across controllers, conditions, and seeds.
- Prompt schemas and checkpoint schemas become versioned experiment inputs.
