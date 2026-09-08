# Artificial Ecology Documentation

This directory contains human-authored project documentation. It describes what the simulation is intended to make possible, what it must not secretly assume, and how observations should be turned into testable understanding.

This is not the knowledge library for the coding agent. The coding agent’s context, decisions, and implementation notes live in [`.agents/`](../.agents/README.md). The simulation’s own inhabitant memories and beliefs are a separate runtime concern and are not stored in either documentation area.

The documents are design proposals, not implementation commitments. When the implementation begins, decisions that constrain behavior should be recorded here with their rationale and expected consequences.

## Document conventions

- **Principle**: a constraint on the design.
- **Mechanism**: a capability provided by the simulation.
- **Emergent phenomenon**: a pattern inhabitants may discover; it is not a built-in feature.
- **Experiment**: a repeatable scenario with a measurable question.
- **Decision record**: a dated explanation of a consequential design choice.

Do not add human concepts to the simulation merely because they are useful labels for analysis. Labels such as “government” or “profession” belong in observer analysis unless inhabitants independently develop behavior that warrants the label.
