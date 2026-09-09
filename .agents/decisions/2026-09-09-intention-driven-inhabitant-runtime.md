# ADR: Intention-Driven Inhabitant Runtime

- Status: Accepted
- Date: 2026-09-09
- Area: inhabitant cognition, model integration, and performance

## Decision

The local model selects one persistent intention rather than a sequence of primitive physical actions. The initial intention vocabulary is:

- `move_to` a destination;
- `consume` food or water at the current location;
- `rest`;
- `send_signal` to a nearby inhabitant; and
- `wait`.

The inhabitant runtime stores the intention and translates it into at most one legal primitive action per tick. A movement intention may therefore continue across several ticks without another model call. Every generated action remains subject to normal engine validation.

An intention completes when its goal is reached, fails when its action fails, and is interrupted when a need crosses the critical threshold. Completion, failure, and interruption cause the runtime to request a new model decision. Scripted controllers may continue to submit primitive actions or bounded plans for deterministic scenarios and tests.

## Context

The primitive-action model contract performed poorly with `gemma4:e2b`. The model frequently returned no action and sometimes treated distant resource coordinates as if they were legal one-cell moves. Asking the model to perform path mechanics consumed inference time while duplicating deterministic work the runtime can perform more reliably.

The model is more useful for selecting priorities and destinations than for repeatedly choosing adjacent coordinates. Persistent intentions also reduce model calls without allowing the model to bypass physical rules.

## Boundaries

- The model chooses the goal; the runtime chooses mechanical steps; the engine decides what actually happens.
- Runtime path selection may use only information available to the inhabitant plus public movement constraints. It must not reveal hidden resources or hazards.
- Immediate eating or drinking when standing on a needed resource remains an innate homeostatic reflex. The runtime does not automatically navigate to resources on the model's behalf.
- Every action generated from an intention records the same `intention_id` and identifies whether it began a model intention or continued one.
- Active intentions are included in snapshots so replay and restoration preserve decision state.

## Consequences

- Inference frequency depends on meaningful reconsideration rather than simulation ticks.
- Distant model goals become valid multi-tick behavior instead of repeated invalid actions.
- Observer and analysis tools can distinguish intention selection from runtime execution and engine outcome.
- The runtime now contains simple path mechanics. More advanced navigation should remain replaceable and must not become a hidden survival policy.

## Falsifiable evaluation

Compare the intention controller against the primitive-action controller on identical seeds. Record model calls per tick, wall-clock inference time, invalid actions, destinations reached, resources consumed, survival time, intention duration, and interruption reasons. Keep the change only if it improves throughput and coherent behavior without erasing meaningful differences between model decisions.

Intention lifecycle events are persisted separately from authoritative physical events so cognition analysis cannot alter deterministic engine replay. The controlled evaluation command provides fixed cases for fatigue, immediate consumption, resource-directed movement, occupied destinations, and exploration.
