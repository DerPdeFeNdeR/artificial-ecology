# ADR: Inhabitant Communication

- Date: 2026-09-08
- Status: accepted
- Area: inhabitant interaction

## Decision

Communication is an explicit engine-validated action and an authoritative event.

An inhabitant may propose communication, but the engine determines whether delivery is possible based on channel, range, timing, environmental conditions, and the inhabitant’s physical state. Delivered communication becomes an observation for the recipient, not guaranteed truth.

## Recorded information

The authoritative event records:

- sender
- intended recipient or audience
- location and timestamp
- channel
- message content or signal payload
- delivery result
- overhearing or partial-delivery information
- relevant environmental conditions

The recipient’s perception, interpretation, belief update, memory, and later decision are recorded separately. A message and what an inhabitant believes about that message must never be the same record.

## Initial behavior

The first communication channel is natural-language speech. Inhabitants may inform, ask, teach, bargain, threaten, persuade, lie, repeat, misunderstand, or refuse to communicate. Messages may later be extended with gestures, signals, writing, artifacts, and invented communication conventions.

## Rationale

Communication is central to cooperation, conflict, teaching, reputation, culture, and social coordination. Recording it is required for replay, causal analysis, and distinguishing information transfer from belief formation.

## Consequences

- Communication is not telepathic or automatically truthful.
- Messages consume inhabitant actions and may have physical constraints.
- The observer can compare what was said with what was understood.
- The engine must preserve message provenance and delivery conditions.
