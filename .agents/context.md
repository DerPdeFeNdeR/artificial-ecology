# Current Project Context

## Project

Artificial Ecology is an open-ended artificial ecology for studying how autonomous inhabitants discover survival strategies, technologies, cultures, and social structures.

## Current stage

The deterministic engine, SQLite persistence, replay, browser observer, cognition records, and local Ollama adapter are implemented. The current focus is making model-assisted runs fast, observable, and reproducible before adding richer world mechanics.

Selected initial stack:

- Python simulation engine
- SQLite persistence
- Ollama with `gemma4:e2b` for inhabitant decisions. In WSL, the Windows Ollama server is reached through `http://172.30.96.1:11434`; override with `OLLAMA_BASE_URL` when needed.
- Browser observer, with Godot deferred

## Important distinction

The “agent” using this library is the coding agent helping build the project. It is not one of the autonomous inhabitants that will live in the artificial ecology.

## Source of truth

- Project design: [`docs/`](../docs/)
- Coding-agent working context: [`.agents/`](./)
- Coding-agent behavior and style: [`INSTRUCTIONS.md`](INSTRUCTIONS.md)
- Inhabitant memory and beliefs: future runtime state, not repository documentation
