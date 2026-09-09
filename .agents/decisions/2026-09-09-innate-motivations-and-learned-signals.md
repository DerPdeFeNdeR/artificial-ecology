# ADR: Innate Motivations and Learned Signals

- Date: 2026-09-09
- Status: accepted
- Area: inhabitant cognition and communication

## Decision

Inhabitants receive primitive motivational pressures rather than roles or prescribed solutions. Initial pressures cover homeostasis, exploration, danger avoidance, persistence, and social curiosity. Reproduction drive remains deferred until reproduction and inheritance are implemented.

The runtime exposes these pressures, relevant beliefs, failed-action history, and observations to the decision controller. The controller still selects actions. The engine only validates actions and applies physical consequences.

Communication uses opaque signals matching sig-..., not unrestricted natural-language speech. Signals are directed, range-limited, recorded as raw observations, and initially have no known meaning. Inhabitants can form uncertain beliefs about signals through repeated observations and context. Signal vocabularies may diverge between groups.

## Rationale

The motivation layer gives small local models enough primitive pressure to explore and avoid repeatedly doing nothing without installing professions, institutions, or survival strategies. Signals prevent the shared language capability of the model from creating a universal human language at initialization.

## Consequences

- Instinct strengths are serialized with inhabitants and can later become heritable traits.
- Homeostatic need values remain distinct from beliefs, desires, plans, and world truth.
- Repeated no-action decisions increase exploration pressure; the model normally remains responsible for choosing whether and where to move.
- After one repeated no-action decision, the runtime may propose a safe exploratory move when no resource is visible. This is recorded as innate_exploration and remains subject to engine validation.
- Failed actions remain evidence for danger avoidance rather than hidden prohibitions.
- Raw signals, senders, recipients, interpretations, and confidence are observable and replayable.
- Natural-language speech proposals are rejected by the authoritative engine.
- Each inhabitant maintains spatial memory with visited locations, observed resource presence or absence, confidence, source, and observation age. Old observations become eligible for reconsideration.
- Homeostatic reflexes may eat or drink when a matching resource is at the current location. They do not navigate to resources on the model's behalf.
- A model-selected distant movement target becomes a persistent intention. The runtime translates it into one adjacent primitive step per tick until completion, failure, or interruption.

## Falsifiable experiments

- Inhabitants with no visible resources explore more as no-action streaks increase.
- Inhabitants stop exploring when resources become visible.
- Recent failures reduce repeated invalid proposals.
- Signal meanings remain uncertain initially and become more stable with repeated contextual evidence.
- Different inherited instinct strengths produce different exploration and communication patterns.
- Inhabitants avoid recently confirmed empty locations when an unknown or stale alternative exists.
