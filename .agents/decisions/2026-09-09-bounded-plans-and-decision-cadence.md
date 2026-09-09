# ADR: Bounded Plans and Decision Cadence

- Date: 2026-09-09
- Status: superseded for local-model decisions by `2026-09-09-intention-driven-inhabitant-runtime.md`; retained for scripted controllers
- Area: inhabitant runtime performance and observability

## Decision

Inhabitants may receive a bounded plan containing up to eight primitive action requests. The engine executes at most one request per simulation tick and remains authoritative over legality and consequences.

The runtime requests a new model decision when a plan finishes or is interrupted by a failed action, a relevant observed change, or a need crossing the critical threshold. A continuing plan does not receive hidden world information and does not bypass perception or validation.

The observer demo supports a fast mode that removes the presentation delay between completed ticks. Simulation time remains tick based and every executed action remains recorded.

Every action records its decision source, such as a model decision, a continuing plan, or a scripted decision. Replay and analysis can therefore distinguish newly generated decisions from plan execution.

## Context

The initial Ollama run made one model request per inhabitant per tick. The optimized run made 495 requests, spent approximately 280 seconds in inference, and selected rest 314 times. Requiring a fresh model response for every primitive action made the simulation slow without providing a new decision at every tick.

## Rationale

Bounded plans reduce repeated inference while keeping action consequences visible and interruptible. One primitive action per tick preserves the engine’s deterministic authority and gives the world opportunities to invalidate a plan. Decision-source records preserve the evidence needed to explain and replay behavior.

The plan horizon is deliberately bounded. Long autonomous scripts could hide cognition, reduce responsiveness to danger, and make the model’s prior knowledge harder to distinguish from learning. The initial horizon is eight actions; experiments should compare shorter horizons before treating the value as settled.

## Interruption rules

- An action failure ends the plan.
- A relevant change in visible resources, obstacles, or inhabitants ends the plan.
- A need crossing from below 80 to 80 or higher ends the plan.
- A completed plan requests a new decision.

## Consequences

- Model-call frequency becomes an experimental variable.
- Plan continuation is visible in inhabitant decisions and event provenance.
- Fast mode changes wall-clock pacing, not simulated time or physical rules.
- The system can later replace repeated model plans with learned procedures while preserving the same engine boundary.
- Plans may still be poor, repetitive, or lethal. Performance improvements do not establish better survival behavior.
- Independent decisions use a bounded five-worker pool by default. Additional inhabitants wait for a decision slot.
- Ollama requests use action-specific JSON, compact cognition context, and a 128-token output cap.

## Measurements

Compare one-action, four-action, and eight-action horizons across the same seeds and scenario conditions. Record inference time, model calls, plan interruptions, exploration, resource use, failed actions, survival, communication, and final population.
