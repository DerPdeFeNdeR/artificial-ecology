# Decision: Initial Local Inhabitant Model

- Date: 2026-09-08
- Status: accepted
- Area: artificial-ecology inhabitant runtime

## Decision

Use `gemma4:e2b` through Ollama as the initial local language model for artificial-ecology inhabitants.

## Context

The development machine has an NVIDIA RTX 4070 Laptop GPU with 8 GB of dedicated VRAM. The project prioritizes fast local inference and the ability to run multiple inhabitants.

## Rationale

The E2B variant is more suitable for the available hardware and expected concurrency than larger Gemma 4 variants. Larger models may spill into shared system memory and reduce throughput.

## Consequences

- The inhabitant runtime must treat the model as replaceable.
- Prompts and context should remain compact.
- The model should make bounded action proposals rather than control world state.
- Model quality should be evaluated with repeatable scenarios before considering a larger model.

## Revisit when

Reconsider after profiling inference speed, memory use, decision quality, and multi-inhabitant behavior. A larger or different model should require evidence that it improves the simulation enough to justify its resource cost.
