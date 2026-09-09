"""Read-only local observer API and minimal browser map."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .engine import SimulationEngine
from .persistence import SQLiteStore
from .runtime import SimulationSession


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Artificial Ecology Observer</title>
  <style>
    :root { color-scheme: dark; font-family: "Courier New", monospace; }
    body { margin: 0; background: #0d120f; color: #c7d0c3; }
    main { display: grid; grid-template-columns: minmax(0, 1fr) minmax(320px, 380px); grid-template-rows: minmax(0, 1fr) minmax(220px, .65fr); gap: .75rem; height: calc(100vh - 1.5rem); min-height: 0; padding: .75rem; box-sizing: border-box; overflow: hidden; }
    section { min-width: 0; background: #18221b; border: 1px solid #4b5a4f; padding: .75rem; }
    .map-panel { grid-column: 1; grid-row: 1; min-height: 0; overflow: auto; }
    .sidebar { grid-column: 2; grid-row: 1; min-width: 0; min-height: 0; }
    h1, h2 { margin: 0 0 .6rem; font-size: 1rem; letter-spacing: .04em; text-transform: uppercase; }
    h1 { color: #9ccb9c; }
    canvas { display: block; width: min(80vw, 720px); height: auto; aspect-ratio: 1; image-rendering: pixelated; background: #0a110d; border: 1px solid #4b5a4f; }
    pre { max-height: none; flex: 1; min-height: 0; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: .78rem; line-height: 1.35; background: #0e1711; border: 1px solid #4b5a4f; padding: .5rem; }
    .meta { color: #aebcad; border-top: 1px solid #4b5a4f; border-bottom: 1px solid #4b5a4f; padding: .35rem 0; margin-bottom: .6rem; font-size: .78rem; overflow-wrap: anywhere; }
    .controls { display: flex; flex-wrap: wrap; gap: .35rem; margin-bottom: .6rem; }
    button { background: #18221b; color: #c7d0c3; border: 1px solid #718271; border-radius: 0; padding: .35rem .6rem; font: inherit; cursor: pointer; }
    button:hover, button:focus { background: #2a3a2d; }
    label { display: block; margin: .6rem 0 .2rem; color: #aebcad; font-size: .75rem; text-transform: uppercase; }
    select { width: 100%; background: #0e1711; color: #c7d0c3; border: 1px solid #4b5a4f; border-radius: 0; padding: .35rem; font: inherit; }
    input[type="range"] { width: 100%; accent-color: #9ccb70; }
    .inspector { min-width: 0; line-height: 1.45; overflow-wrap: anywhere; word-break: break-word; }
    .inspector table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    .inspector th, .inspector td { border-bottom: 1px solid #3f4d43; padding: .25rem .15rem; text-align: left; vertical-align: top; overflow-wrap: anywhere; word-break: break-word; }
    .inspector th { width: 36%; color: #aebcad; font-weight: normal; }
    .inspector code { display: block; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; }
    .inspector-tabs { display: flex; flex-wrap: wrap; gap: .25rem; margin-bottom: .5rem; }
    .inspector-tabs button { font-size: .72rem; padding: .25rem .45rem; }
    .inspector-tabs button.active { background: #2a3a2d; color: #9ccb70; }
    .legend { display: flex; flex-wrap: wrap; gap: .7rem; margin-top: .55rem; color: #aebcad; font-size: .72rem; }
    .legend span::before { content: ""; display: inline-block; width: .7rem; height: .7rem; margin-right: .25rem; vertical-align: -.05rem; border: 1px solid #718271; background: var(--swatch); }
    .sidebar > section { height: 100%; min-height: 0; overflow: auto; }
    .events-panel { grid-column: 1 / -1; grid-row: 2; display: flex; flex-direction: column; min-height: 0; }
    @media (max-width: 900px) {
      main { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(360px, 1fr) minmax(260px, auto); height: auto; min-height: calc(100vh - 1.5rem); overflow: visible; }
      .map-panel { grid-column: 1; grid-row: 1; }
      .sidebar { grid-column: 1; grid-row: 2; }
      .events-panel { grid-column: 1; grid-row: 3; }
    }
    @media (max-width: 650px) {
      main { display: flex; flex-direction: column; height: auto; min-height: 0; overflow: visible; }
      .map-panel { order: 1; }
      .sidebar { order: 2; min-height: 360px; }
      .events-panel { order: 3; min-height: 320px; }
    }
  </style>
</head>
<body>
  <main>
    <section class="map-panel">
      <h1>Artificial Ecology</h1>
      <div class="meta" id="meta">Loading…</div>
      <div class="controls">
        <button onclick="control('start')">Start</button>
        <button onclick="control('stop')">Stop</button>
        <button onclick="control('reset')">Reset</button>
      </div>
      <div class="legend">
        <span style="--swatch:#275b4c">inhabitant</span>
        <span style="--swatch:#8a9fbd">water</span>
        <span style="--swatch:#87965a">food</span>
        <span style="--swatch:#777b73">obstacle</span>
      </div>
      <label for="run-select">Recorded run</label>
      <select id="run-select" onchange="selectRun(this.value)">
        <option value="live">Live simulation</option>
      </select>
      <div id="replay-controls" hidden>
        <label for="tick-slider">Replay tick</label>
        <input id="tick-slider" type="range" min="0" max="0" value="0" oninput="selectTick(this.value)">
        <span id="tick-label"></span>
      </div>
      <canvas id="map" width="600" height="600"></canvas>
    </section>
    <aside class="sidebar">
    <section>
      <h2>Inhabitant</h2>
      <div class="inspector-tabs" role="tablist">
        <button class="active" data-inspector-view="summary" role="tab">Summary</button>
        <button data-inspector-view="memories" role="tab">Memories</button>
        <button data-inspector-view="beliefs" role="tab">Beliefs</button>
        <button data-inspector-view="decisions" role="tab">Decisions</button>
      </div>
      <div class="inspector" id="inspector">Click an inhabitant to inspect them.</div>
    </section>
    </aside>
    <section class="events-panel">
      <h2>Recent events</h2>
      <label for="event-filter">Event type</label>
      <select id="event-filter" onchange="draw(lastState)">
        <option value="all">All events</option>
      </select>
      <label for="inhabitant-filter">Inhabitant</label>
      <select id="inhabitant-filter" onchange="draw(lastState)">
        <option value="all">All inhabitants</option>
      </select>
      <pre id="events">Loading…</pre>
    </section>
  </main>
  <script>
    const canvas = document.getElementById('map');
    const context = canvas.getContext('2d');
    const colors = { water: '#547fa7', food: '#849b58', obstacle: '#4f5a51', inhabitant: '#9ccb70' };
    let lastState = null;
    let selectedId = null;
    let inspectorView = 'summary';
    let selectedRun = 'live';
    let selectedTick = 0;

    function updateFilters(state) {
      const eventFilter = document.getElementById('event-filter');
      const currentEvent = eventFilter.value;
      const eventTypes = [...new Set(state.events.map(event => event.event_type))].sort();
      eventFilter.innerHTML = '<option value="all">All events</option>' + eventTypes.map(type => `<option value="${type}">${type}</option>`).join('');
      eventFilter.value = eventTypes.includes(currentEvent) ? currentEvent : 'all';

      const inhabitantFilter = document.getElementById('inhabitant-filter');
      const currentInhabitant = inhabitantFilter.value;
      const inhabitants = Object.values(state.world.inhabitants).sort((a, b) => a.id.localeCompare(b.id));
      inhabitantFilter.innerHTML = '<option value="all">All inhabitants</option>' + inhabitants.map(inhabitant => `<option value="${inhabitant.id}">${inhabitant.name}</option>`).join('');
      inhabitantFilter.value = inhabitants.some(inhabitant => inhabitant.id === currentInhabitant) ? currentInhabitant : 'all';
    }

    function drawInspector(state) {
      const inhabitant = state.world.inhabitants[selectedId];
      const inspector = document.getElementById('inspector');
      if (!inhabitant) {
        inspector.textContent = 'Click an inhabitant to inspect them.';
        return;
      }
      if (inspectorView === 'summary') {
        inspector.innerHTML = `<table><tr><th>NAME</th><td>${inhabitant.name}</td></tr><tr><th>ID</th><td>${inhabitant.id}</td></tr><tr><th>STATUS</th><td>${inhabitant.alive ? 'alive' : 'dead'}</td></tr><tr><th>POSITION</th><td>(${inhabitant.position.x}, ${inhabitant.position.y})</td></tr><tr><th>HUNGER</th><td>${inhabitant.hunger}</td></tr><tr><th>THIRST</th><td>${inhabitant.thirst}</td></tr><tr><th>FATIGUE</th><td>${inhabitant.fatigue}</td></tr><tr><th>MESSAGES</th><td>${inhabitant.received_messages.length}</td></tr><tr><th>MEMORIES</th><td>${inhabitant.memories.length}</td></tr><tr><th>BELIEFS</th><td>${Object.keys(inhabitant.beliefs).length}</td></tr></table>`;
      } else if (inspectorView === 'memories') {
        inspector.innerHTML = `<code>${JSON.stringify(inhabitant.memories, null, 2) || 'No memories recorded.'}</code>`;
      } else if (inspectorView === 'beliefs') {
        inspector.innerHTML = Object.keys(inhabitant.beliefs).length
          ? `<code>${JSON.stringify(inhabitant.beliefs, null, 2)}</code>`
          : 'No beliefs recorded.';
      } else {
        inspector.innerHTML = `<table><tr><th>DESIRES</th><td><code>${JSON.stringify(inhabitant.desires, null, 2)}</code></td></tr><tr><th>PLAN</th><td><code>${JSON.stringify(inhabitant.current_plan, null, 2)}</code></td></tr><tr><th>LAST DECISION</th><td><code>${JSON.stringify(inhabitant.last_decision, null, 2)}</code></td></tr></table>`;
      }
      document.querySelectorAll('[data-inspector-view]').forEach(button => button.classList.toggle('active', button.dataset.inspectorView === inspectorView));
    }

    function draw(state) {
      const world = state.world;
      const cell = Math.min(canvas.width / world.width, canvas.height / world.height);
      const offsetX = (canvas.width - world.width * cell) / 2;
      const offsetY = (canvas.height - world.height * cell) / 2;
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.strokeStyle = '#263244';
      for (let x = 0; x <= world.width; x++) {
        context.beginPath(); context.moveTo(offsetX + x * cell, offsetY); context.lineTo(offsetX + x * cell, offsetY + world.height * cell); context.stroke();
      }
      for (let y = 0; y <= world.height; y++) {
        context.beginPath(); context.moveTo(offsetX, offsetY + y * cell); context.lineTo(offsetX + world.width * cell, offsetY + y * cell); context.stroke();
      }
      context.fillStyle = colors.obstacle;
      for (const position of world.obstacles) context.fillRect(offsetX + position.x * cell, offsetY + position.y * cell, cell, cell);
      context.fillStyle = colors.water;
      for (const position of world.water) context.fillRect(offsetX + position.x * cell + cell * .2, offsetY + position.y * cell + cell * .2, cell * .6, cell * .6);
      context.fillStyle = colors.food;
      for (const item of world.food) if (item.quantity > 0) context.fillRect(offsetX + item.position.x * cell + cell * .3, offsetY + item.position.y * cell + cell * .3, cell * .4, cell * .4);
      context.fillStyle = colors.inhabitant;
      for (const inhabitant of Object.values(world.inhabitants)) {
        if (!inhabitant.alive) continue;
        if (inhabitant.id === selectedId) context.fillStyle = '#fef08a';
        context.beginPath();
        context.arc(offsetX + (inhabitant.position.x + .5) * cell, offsetY + (inhabitant.position.y + .5) * cell, cell * .3, 0, Math.PI * 2);
        context.fill();
        context.fillStyle = colors.inhabitant;
      }
      const alive = Object.values(world.inhabitants).filter(inhabitant => inhabitant.alive).length;
      const food = world.food.reduce((total, item) => total + item.quantity, 0);
      const progress = state.decision_progress && state.decision_progress.total
        ? ` | DECISIONS ${state.decision_progress.completed}/${state.decision_progress.total}`
        : '';
      const error = state.error ? ` | ERROR ${state.error}` : '';
      document.getElementById('meta').textContent = `RUN ${state.run_id || 'live'} | STATUS ${state.status} | TICK ${world.tick} | ALIVE ${alive}/${Object.keys(world.inhabitants).length} | FOOD ${food} | WATER ${world.water.length}${progress}${error}`;
      updateFilters(state);
      const eventType = document.getElementById('event-filter').value;
      const inhabitantId = document.getElementById('inhabitant-filter').value;
      const events = state.events.filter(event => {
        const matchesType = eventType === 'all' || event.event_type === eventType;
        const actorId = event.payload.actor_id || event.payload.inhabitant_id;
        const matchesInhabitant = inhabitantId === 'all' || actorId === inhabitantId;
        return matchesType && matchesInhabitant;
      });
      document.getElementById('events').textContent = events.map(formatEvent).join('\\n');
      drawInspector(state);
    }

    function formatEvent(event) {
      const payload = Object.entries(event.payload).map(([key, value]) => `${key}=${typeof value === 'object' ? JSON.stringify(value) : value}`).join(' ');
      return `[${String(event.sequence).padStart(6, '0')}] TICK ${String(event.tick).padStart(4, '0')} ${event.event_type.toUpperCase()}\\n  ${payload}`;
    }

    async function control(action) {
      await fetch('/api/control', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action}) });
      await refresh();
    }

    async function loadRuns() {
      const response = await fetch('/api/runs');
      const runs = await response.json();
      const select = document.getElementById('run-select');
      const current = select.value;
      select.innerHTML = '<option value="live">Live simulation</option>' + runs.map(run => `<option value="${run.run_id}">${run.run_id} · ${run.event_count} events</option>`).join('');
      select.value = runs.some(run => run.run_id === current) ? current : 'live';
      updateReplayControls(runs);
    }

    function updateReplayControls(runs) {
      const controls = document.getElementById('replay-controls');
      const run = runs.find(item => item.run_id === selectedRun);
      controls.hidden = !run;
      if (run) {
        const slider = document.getElementById('tick-slider');
        slider.min = run.first_tick;
        slider.max = run.last_tick;
        slider.value = Math.min(Math.max(selectedTick, run.first_tick), run.last_tick);
        document.getElementById('tick-label').textContent = `Tick ${slider.value} of ${run.last_tick}`;
      }
    }

    async function selectRun(runId) {
      selectedRun = runId;
      selectedTick = 0;
      await loadRuns();
      await refresh();
    }

    async function selectTick(tick) {
      selectedTick = Number(tick);
      document.getElementById('tick-label').textContent = `Tick ${selectedTick}`;
      await refresh();
    }

    async function refresh() {
      const url = selectedRun === 'live' ? '/api/state' : `/api/replay?run_id=${encodeURIComponent(selectedRun)}&tick=${selectedTick}`;
      const response = await fetch(url);
      lastState = await response.json();
      draw(lastState);
    }
    canvas.addEventListener('click', event => {
      if (!lastState) return;
      const rect = canvas.getBoundingClientRect();
      const cell = Math.min(canvas.width / lastState.world.width, canvas.height / lastState.world.height);
      const offsetX = (canvas.width - lastState.world.width * cell) / 2;
      const offsetY = (canvas.height - lastState.world.height * cell) / 2;
      const canvasX = (event.clientX - rect.left) * canvas.width / rect.width - offsetX;
      const canvasY = (event.clientY - rect.top) * canvas.height / rect.height - offsetY;
      const x = Math.floor(canvasX / cell);
      const y = Math.floor(canvasY / cell);
      const inhabitant = Object.values(lastState.world.inhabitants).find(item => item.alive && item.position.x === x && item.position.y === y);
      selectedId = inhabitant ? inhabitant.id : null;
      draw(lastState);
    });
    document.querySelectorAll('[data-inspector-view]').forEach(button => {
      button.addEventListener('click', () => {
        if (!lastState) return;
        inspectorView = button.dataset.inspectorView;
        draw(lastState);
      });
    });
    loadRuns();
    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>"""


class ObserverView:
    def __init__(
        self,
        target: SimulationEngine | SimulationSession,
        store: SQLiteStore | None = None,
        current_run_id: Callable[[], str | None] | None = None,
        recent_event_limit: int = 100,
    ) -> None:
        self.target = target
        self.store = store
        self.current_run_id = current_run_id
        self.recent_event_limit = recent_event_limit

    def state(self) -> dict[str, Any]:
        if isinstance(self.target, SimulationSession):
            state = self.target.observer_state(self.recent_event_limit)
            state["run_id"] = self.current_run_id() if self.current_run_id is not None else None
            return state
        engine = self.target.engine if isinstance(self.target, SimulationSession) else self.target
        status = self.target.status if isinstance(self.target, SimulationSession) else ("extinct" if engine.is_extinct else "stopped")
        return {
            "run_id": self.current_run_id() if self.current_run_id is not None else None,
            "status": status,
            "error": self.target.error if isinstance(self.target, SimulationSession) else None,
            "world": engine.world.to_dict(),
            "events": [event.to_dict() for event in engine.events[-self.recent_event_limit:]],
            "decision_progress": {"tick": engine.world.tick, "completed": 0, "total": 0},
        }

    def runs(self) -> list[dict[str, Any]]:
        return self.store.run_summaries() if self.store is not None else []

    def replay(self, run_id: str, tick: int) -> dict[str, Any] | None:
        if self.store is None:
            return None
        snapshot = self.store.snapshot_at(run_id, tick)
        if snapshot is None:
            return None
        events = [event.to_dict() for event in self.store.events_for_run(run_id) if event.tick <= tick]
        return {"run_id": run_id, "status": "replay", "error": None, "world": snapshot["world"], "events": events}


def create_server(
    target: SimulationEngine | SimulationSession,
    host: str = "127.0.0.1",
    port: int = 8000,
    store: SQLiteStore | None = None,
    current_run_id: Callable[[], str | None] | None = None,
) -> ThreadingHTTPServer:
    view = ObserverView(target, store=store, current_run_id=current_run_id)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            path = urlparse(self.path).path
            if path == "/":
                self._send(HTTPStatus.OK, "text/html; charset=utf-8", INDEX_HTML.encode("utf-8"))
            elif path == "/api/state":
                payload = json.dumps(view.state(), sort_keys=True).encode("utf-8")
                self._send(HTTPStatus.OK, "application/json", payload)
            elif path == "/api/runs":
                payload = json.dumps(view.runs(), sort_keys=True).encode("utf-8")
                self._send(HTTPStatus.OK, "application/json", payload)
            elif path == "/api/replay":
                query = parse_qs(urlparse(self.path).query)
                run_id = query.get("run_id", [""])[0]
                try:
                    tick = int(query.get("tick", ["0"])[0])
                except ValueError:
                    tick = -1
                replay = view.replay(run_id, tick)
                if replay is None:
                    self._send(HTTPStatus.NOT_FOUND, "application/json", b'{"error":"replay not found"}')
                else:
                    self._send(HTTPStatus.OK, "application/json", json.dumps(replay, sort_keys=True).encode("utf-8"))
            else:
                self._send(HTTPStatus.NOT_FOUND, "application/json", b'{"error":"not found"}')

        def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            if urlparse(self.path).path != "/api/control" or not isinstance(target, SimulationSession):
                self._send(HTTPStatus.NOT_FOUND, "application/json", b'{"error":"not found"}')
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                action = json.loads(self.rfile.read(length)).get("action")
                if action == "start":
                    changed = target.start()
                elif action == "stop":
                    changed = target.stop()
                elif action == "reset":
                    target.reset()
                    changed = True
                else:
                    self._send(HTTPStatus.BAD_REQUEST, "application/json", b'{"error":"unknown action"}')
                    return
            except (TypeError, ValueError, json.JSONDecodeError):
                self._send(HTTPStatus.BAD_REQUEST, "application/json", b'{"error":"invalid request"}')
                return
            payload = json.dumps({"changed": changed, "status": target.status}).encode("utf-8")
            self._send(HTTPStatus.OK, "application/json", payload)

        def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def serve(engine: SimulationEngine, host: str = "127.0.0.1", port: int = 8000) -> None:
    server = create_server(engine, host, port)
    print(f"Observer available at http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
