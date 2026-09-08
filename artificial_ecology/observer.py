"""Read-only local observer API and minimal browser map."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .engine import SimulationEngine


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Artificial Ecology Observer</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #111827; color: #e5e7eb; }
    main { display: grid; grid-template-columns: minmax(420px, 1fr) 360px; gap: 1rem; min-height: 100vh; padding: 1rem; box-sizing: border-box; }
    section { background: #1f2937; border: 1px solid #374151; border-radius: .6rem; padding: 1rem; }
    h1, h2 { margin-top: 0; }
    canvas { display: block; width: min(80vw, 720px); height: min(80vw, 720px); image-rendering: pixelated; background: #0f172a; border: 1px solid #4b5563; }
    pre { max-height: 70vh; overflow: auto; white-space: pre-wrap; font-size: .8rem; }
    .meta { color: #9ca3af; margin-bottom: 1rem; }
    @media (max-width: 800px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main>
    <section>
      <h1>Artificial Ecology</h1>
      <div class="meta" id="meta">Loading…</div>
      <canvas id="map" width="600" height="600"></canvas>
    </section>
    <section>
      <h2>Recent events</h2>
      <pre id="events">Loading…</pre>
    </section>
  </main>
  <script>
    const canvas = document.getElementById('map');
    const context = canvas.getContext('2d');
    const colors = { water: '#2563eb', food: '#16a34a', obstacle: '#4b5563', inhabitant: '#f59e0b' };

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
        context.beginPath();
        context.arc((inhabitant.position.x + .5) * cell, (inhabitant.position.y + .5) * cell, cell * .3, 0, Math.PI * 2);
        context.fill();
      }
      document.getElementById('meta').textContent = `Tick ${world.tick} · ${Object.keys(world.inhabitants).length} inhabitants`;
      document.getElementById('events').textContent = state.events.map(event => JSON.stringify(event)).join('\\n');
    }

    async function refresh() {
      const response = await fetch('/api/state');
      draw(await response.json());
    }
    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>"""


class ObserverView:
    def __init__(self, engine: SimulationEngine, recent_event_limit: int = 100) -> None:
        self.engine = engine
        self.recent_event_limit = recent_event_limit

    def state(self) -> dict[str, Any]:
        return {
            "world": self.engine.world.to_dict(),
            "events": [event.to_dict() for event in self.engine.events[-self.recent_event_limit:]],
        }


def create_server(engine: SimulationEngine, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    view = ObserverView(engine)

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
