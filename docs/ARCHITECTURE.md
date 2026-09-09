# Architecture

The system is divided by authority. This boundary is more important than the choice of programming language.

## Simulation engine

The engine owns the authoritative world state and enforces all consequences:

- time and deterministic ordering
- terrain, resources, hazards, and changing conditions
- bodies, needs, injuries, death, and movement constraints
- interaction rules, communication delivery, and action legality
- later: gathering, crafting, construction, combat, reproduction, and ecology

The engine accepts validated action requests and emits immutable events. It never accepts an explanation from an inhabitant as proof that an action happened.

## Inhabitant runtime

An inhabitant runtime turns limited observations into possible action requests. Its conceptual stages are:

1. Perception filters authoritative state into what the inhabitant can notice.
2. Interpretation updates beliefs, with uncertainty and possible error.
3. Needs and desires create competing priorities.
4. Memory retrieves relevant experiences and knowledge.
5. Planning selects a persistent intention or a deterministic controller proposes actions.
6. The runtime translates an intention into one primitive action for the current tick.
7. Validation asks the engine whether a request is currently legal.
8. Consequences become new observations and memories.

The runtime may use rules, learned models, or an LLM. None of these are authoritative. The local model selects goals such as moving to a destination, consuming a resource, resting, signaling, or waiting. The runtime stores that intention and performs mechanical translation into at most one primitive action per tick. It requests another model decision only after completion, failure, or interruption.

## Canonical tick execution

Each tick follows one fixed sequence:

1. Apply scheduled effects and environmental changes.
2. Update needs and body conditions.
3. Generate each inhabitant’s bounded perception.
4. Retrieve memories and assemble decision contexts.
5. Wait for all scheduled decisions or record an explicit infrastructure failure.
6. Resolve all action proposals against the same world version.
7. Emit events and apply consequences.
8. Update perceptions, beliefs, memories, and decision records.
9. Persist the tick and advance the simulation.

The engine does not advance while scheduled model decisions are pending. A slow model makes the run slower; it does not give that inhabitant a different amount of simulated time.

Action proposals are resolved with a seeded, per-tick ordering or an explicit system rule. Request completion order never determines who wins a conflict.

The initial model adapter uses Ollama and `gemma4:e2b`. The runtime uses one shared loaded model with separate inhabitant contexts and may request independent inhabitant decisions concurrently at the decision barrier.

The LLM receives a compact physical observation, selected memories, active desires, the current intention, recent action results, and descriptions of the inhabitant’s capabilities. Private cognition is supplied through the decision context rather than duplicated inside the physical self-observation. It chooses a structured intention, not executable code or a state mutation. Runtime navigation uses only available knowledge and public movement constraints. The engine validates every translated action against authoritative state and exposes results through later observations.

The initial cognition runtime records these distinctions explicitly:

- beliefs are keyed claims with a value, confidence, source, and observation ticks;
- memories have stable run-local identifiers and retrieval is bounded to recent records;
- plans contain a requested action, lifecycle status, creation tick, and result event;
- intentions contain a model-selected goal, lifecycle status, creation tick, and stable provenance identifier;
- decisions retain desires, beliefs, and retrieved memory identifiers as decision context;
- failed actions can revise a local belief without changing world truth.

Ollama calls are recorded with the model name, complete request context, response or error, and outcome. The initial local controller disables thinking and bounds output because the inhabitant decision is a small structured intention. Transport failures pause the session and remain explicit records; they are not silently represented as successful decisions. The observer publishes the last completed world state and decision progress while inference is running. The observer demo uses the scripted controller by default and can be run with `AE_CONTROLLER=ollama` for a local-model experiment. In WSL, it uses the Windows Ollama endpoint at `http://172.30.96.1:11434` unless `OLLAMA_BASE_URL` overrides it.

These are baseline structures, not claims that inhabitants reason correctly. Later work should add noisy recall, belief revision, richer retrieval, and multi-step plans while preserving the distinction between interpretation and authoritative state.

## Persistence and replay

Persist at least:

- world snapshots at known event offsets
- the ordered event log
- inhabitant perceptions, beliefs, memories, desires, and decisions
- lineage and inherited traits
- experiment configuration, random seeds, and software version
- scheduler state, pending activities, pending messages, and random-generator state
- model identifier, settings, prompt inputs, and recorded model outputs

Replay has three distinct modes:

- **Playback** applies recorded results without rerunning model or decision logic.
- **Verification** reruns the engine with recorded proposals and compares state and events.
- **Branching** restores a complete checkpoint and begins a new history with a parent reference.

Snapshots and the events that advance from them are committed together. Event and snapshot schemas are versioned.

## Observer layer

Observer tools may use concepts that inhabitants do not know. They should expose world truth beside inhabitant interpretation, including:

- map, resources, population, and event timeline
- inhabitant needs, desires, plans, decisions, conversations, memories, and beliefs
- relationships, lineage, and material dependencies
- replay, branching, and “why did this happen?” traces

Observer analysis must distinguish direct evidence from an interpretation imposed after the run.
