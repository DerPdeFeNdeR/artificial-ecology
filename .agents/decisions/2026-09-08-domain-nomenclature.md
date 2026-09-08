# ADR: Domain Nomenclature

- Date: 2026-09-08
- Status: accepted
- Area: terminology

## Decision

Use **inhabitant** for an autonomous being living inside the artificial ecology. Reserve **coding agent** or **development agent** for the AI assisting with construction of this project.

Use **entity** only as a broad technical term for anything represented in the world, including inhabitants, resources, terrain, structures, and environmental objects.

Use **inhabitant runtime** for the perception, memory, planning, communication, and decision subsystem associated with an inhabitant.

## Rationale

The word “agent” currently refers both to the coding assistant and to simulated beings. “Inhabitant” makes the in-world perspective clear without assigning a social role or implying a particular implementation model.

## Terminology mapping

```text
coding agent       → AI helping build the project
inhabitant         → autonomous being inside the simulation
inhabitant runtime → cognition and decision subsystem for an inhabitant
entity             → any represented world object
```

## Consequences

Future documentation and code should prefer “inhabitant” when referring to in-world beings. Existing uses of “agent” should be updated when the affected documents or modules are next revised.
