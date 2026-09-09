"""Read-only local observer API and minimal browser map."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .engine import SimulationEngine
from .runtime import SimulationSession


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Artificial Ecology Observer</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #111827; color: #e5e7eb; }
    main { display: grid; grid-template-columns: minmax(420px, 1fr) 360px 280px; gap: 1rem; min-height: 100vh; padding: 1rem; box-sizing: border-box; }
    section { background: #1f2937; border: 1px solid #374151; border-radius: .6rem; padding: 1rem; }
    h1, h2 { margin-top: 0; }
    canvas { display: block; width: min(80vw, 720px); height: min(80vw, 720px); image-rendering: pixelated; background: #0f172a; border: 1px solid #4b5563; }
    pre { max-height: 55vh; overflow: auto; white-space: pre-wrap; font-size: .8rem; }
    .meta { color: #9ca3af; margin-bottom: 1rem; }
    .controls { display: flex; gap: .5rem; margin-bottom: 1rem; }
    button { background: #374151; color: #e5e7eb; border: 1px solid #6b7280; border-radius: .35rem; padding: .45rem .8rem; cursor: pointer; }
    button:hover { background: #4b5563; }
    label { display: block; margin: .75rem 0 .25rem; color: #9ca3af; font-size: .85rem; }
    select { width: 100%; background: #111827; color: #e5e7eb; border: 1px solid #4b5563; border-radius: .35rem; padding: .4rem; }
    .inspector { line-height: 1.6; }
    .selected { outline: 2px solid #fbbf24; }
    @media (max-width: 800px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main>
    <section>
      <h1>Artificial Ecology</h1>
      <div class="meta" id="meta">Loading…</div>
      <div class="controls">
        <button onclick="control('start')">Start</button>
        <button onclick="control('stop')">Stop</button>
        <button onclick="control('reset')">Reset</button>
      </div>
      <canvas id="map" width="600" height="600"></canvas>
    </section>
    <section>
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
    <section>
      <h2>Inhabitant</h2>
      <div class="inspector" id="inspector">Click an inhabitant to inspect them.</div>
    </section>
  </main>
  <script>
    const canvas = document.getElementById('map');
    const context = canvas.getContext('2d');
    const colors = { water: '#2563eb', food: '#16a34a', obstacle: '#4b5563', inhabitant: '#f59e0b' };
    let lastState = null;
    let selectedId = null;

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
      inspector.innerHTML = `<strong>${inhabitant.name}</strong><br>Status: ${inhabitant.alive ? 'alive' : 'dead'}<br>Position: (${inhabitant.position.x}, ${inhabitant.position.y})<br>Hunger: ${inhabitant.hunger}<br>Thirst: ${inhabitant.thirst}<br>Fatigue: ${inhabitant.fatigue}<br>Messages: ${inhabitant.received_messages.length}`;
    }

    function draw(state) {
      const world = state.world;
      const cell = Math.min(canvas.width / world.width, canvas.height / world.height);
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.strokeStyle = '#263244';
      for (let x = 0; x <= world.width; x++) {
        context.beginPath(); context.moveTo(x * cell, 0); context.lineTo(x * cell, world.height * cell); context.stroke();
      }
      for (let y = 0; y <= world.height; y++) {
        context.beginPath(); context.moveTo(0, y * cell); context.lineTo(world.width * cell, y * cell); context.stroke();
      }
      context.fillStyle = colors.obstacle;
      for (const position of world.obstacles) context.fillRect(position.x * cell, position.y * cell, cell, cell);
      context.fillStyle = colors.water;
      for (const position of world.water) context.fillRect(position.x * cell + cell * .2, position.y * cell + cell * .2, cell * .6, cell * .6);
      context.fillStyle = colors.food;
      for (const item of world.food) if (item.quantity > 0) context.fillRect(item.position.x * cell + cell * .3, item.position.y * cell + cell * .3, cell * .4, cell * .4);
      context.fillStyle = colors.inhabitant;
      for (const inhabitant of Object.values(world.inhabitants)) {
        if (!inhabitant.alive) continue;
        if (inhabitant.id === selectedId) context.fillStyle = '#fef08a';
        context.beginPath();
        context.arc((inhabitant.position.x + .5) * cell, (inhabitant.position.y + .5) * cell, cell * .3, 0, Math.PI * 2);
        context.fill();
        context.fillStyle = colors.inhabitant;
      }
      const alive = Object.values(world.inhabitants).filter(inhabitant => inhabitant.alive).length;
      const food = world.food.reduce((total, item) => total + item.quantity, 0);
      document.getElementById('meta').textContent = `Status: ${state.status} · Tick ${world.tick} · ${alive}/${Object.keys(world.inhabitants).length} alive · Food: ${food} · Water sources: ${world.water.length}`;
      updateFilters(state);
      const eventType = document.getElementById('event-filter').value;
      const inhabitantId = document.getElementById('inhabitant-filter').value;
      const events = state.events.filter(event => {
        const matchesType = eventType === 'all' || event.event_type === eventType;
        const actorId = event.payload.actor_id || event.payload.inhabitant_id;
        const matchesInhabitant = inhabitantId === 'all' || actorId === inhabitantId;
        return matchesType && matchesInhabitant;
      });
      document.getElementById('events').textContent = events.map(event => JSON.stringify(event)).join('\\n');
      drawInspector(state);
    }

    async function control(action) {
      await fetch('/api/control', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action}) });
      await refresh();
    }

    async function refresh() {
      const response = await fetch('/api/state');
      lastState = await response.json();
      draw(lastState);
    }
    canvas.addEventListener('click', event => {
      if (!lastState) return;
      const rect = canvas.getBoundingClientRect();
      const cell = Math.min(canvas.width / lastState.world.width, canvas.height / lastState.world.height);
      const x = Math.floor((event.clientX - rect.left) * canvas.width / rect.width / cell);
      const y = Math.floor((event.clientY - rect.top) * canvas.height / rect.height / cell);
      const inhabitant = Object.values(lastState.world.inhabitants).find(item => item.alive && item.position.x === x && item.position.y === y);
      selectedId = inhabitant ? inhabitant.id : null;
      draw(lastState);
    });
    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>"""


class ObserverView:
    def __init__(self, target: SimulationEngine | SimulationSession, recent_event_limit: int = 100) -> None:
        self.target = target
        self.recent_event_limit = recent_event_limit

    def state(self) -> dict[str, Any]:
        engine = self.target.engine if isinstance(self.target, SimulationSession) else self.target
        status = self.target.status if isinstance(self.target, SimulationSession) else ("extinct" if engine.is_extinct else "stopped")
        return {
            "status": status,
            "error": self.target.error if isinstance(self.target, SimulationSession) else None,
            "world": engine.world.to_dict(),
            "events": [event.to_dict() for event in engine.events[-self.recent_event_limit:]],
        }


def create_server(target: SimulationEngine | SimulationSession, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    view = ObserverView(target)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            path = urlparse(self.path).path
            if path == "/":
                self._send(HTTPStatus.OK, "text/html; charset=utf-8", INDEX_HTML.encode("utf-8"))
            elif path == "/api/state":
                payload = json.dumps(view.state(), sort_keys=True).encode("utf-8")
                self._send(HTTPStatus.OK, "application/json", payload)
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
