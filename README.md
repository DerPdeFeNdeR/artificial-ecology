# Artificial Ecology

An open-ended artificial ecology for studying emergent behavior in autonomous inhabitants.

Inhabitants begin with primitive needs, bodies, perception, memory, communication, and the ability to interact with a malleable world. They must discover survival strategies, technologies, cultures, and social structures themselves.

The simulation should make governments, professions, economies, traditions, alliances, and conflicts possible without making them explicit mechanics.

## Project documentation

The project direction and design constraints live in [`docs/`](docs/README.md). The coding agent’s working context and decision library live separately in [`.agents/`](.agents/README.md).

- [Project charter](docs/PROJECT_CHARTER.md) — purpose, principles, and boundaries
- [Architecture](docs/ARCHITECTURE.md) — responsibilities and information flow
- [Roadmap](docs/ROADMAP.md) — staged development plan
- [Experiments](docs/EXPERIMENTS.md) — how to evaluate emergence without scripting conclusions

## Run the core demo

From WSL:

```bash
python3 -m unittest discover -v
python3 -m artificial_ecology.demo
```

Open `http://127.0.0.1:8000` in a browser to view the live deterministic demo. The Ollama controller uses the Windows Ollama API at `http://localhost:11434`.

The demo records each run in `runs/demo.sqlite3` (ignored by Git), including the initial snapshot, per-tick snapshots, events, and scripted decisions.
