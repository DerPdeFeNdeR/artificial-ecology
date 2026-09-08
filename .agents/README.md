# Coding Agent Project Library

This directory is for the coding agent working on Artificial Ecology. It is separate from the autonomous inhabitants that will exist inside the simulation.

## Responsibilities

Use this library to preserve project context across coding sessions:

- important project decisions and their rationale
- current implementation status and next steps
- constraints that must not be forgotten
- open questions and unresolved tradeoffs
- investigation notes and verified findings
- coding conventions and operational instructions

The agent’s working style is defined in [INSTRUCTIONS.md](INSTRUCTIONS.md).

The library should explain how to build the project. It must not be treated as a model of what simulated inhabitants know.

## Planned layout

```text
.agents/
  README.md
  context.md
  decisions/
    YYYY-MM-DD-short-title.md
  plans/
    current.md
  notes/
    topic.md
  templates/
    DECISION.md
    NOTE.md
```

Keep entries concise, dated when relevant, and explicit about whether something is a confirmed fact, a chosen direction, an assumption, or an open question.

## Three distinct knowledge domains

1. **Coding-agent knowledge** — this directory; project context used to modify the codebase.
2. **Project documentation** — [`docs/`](../docs/); stable human-readable design and research documentation.
3. **Inhabitant knowledge** — future runtime state; memories, beliefs, and learned procedures belonging to simulated inhabitants.

Only the third domain should contain the knowledge of artificial-ecology inhabitants. It should be designed later as part of the simulation engine, not confused with this project library.
