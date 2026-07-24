"""Silent macro / Stream Deck gateway — HTTP control without speaking."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse


class MacroGateway:
    """
    Local HTTP pad for Stream Deck / Elgato / curl.
    GET  http://127.0.0.1:8765/macro?cmd=stop
    POST http://127.0.0.1:8765/macro  {"cmd":"lock"}
    """

    def __init__(
        self,
        on_command: Callable[[str], str],
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        self.on_command = on_command
        self.host = host
        self.port = int(port)
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:  # noqa: A003
                return

            def _reply(self, code: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path in ("/", "/health"):
                    self._reply(200, {"ok": True, "service": "jarvis-macro"})
                    return
                if parsed.path != "/macro":
                    self._reply(404, {"ok": False, "error": "not found"})
                    return
                qs = parse_qs(parsed.query)
                cmd = (qs.get("cmd") or qs.get("c") or [""])[0].strip()
                if not cmd:
                    self._reply(
                        400,
                        {
                            "ok": False,
                            "error": "missing cmd",
                            "examples": [
                                "stop",
                                "lock",
                                "camera",
                                "mute",
                                "brief",
                                "go offline",
                            ],
                        },
                    )
                    return
                try:
                    result = gateway.on_command(cmd)
                    self._reply(200, {"ok": True, "cmd": cmd, "result": result})
                except Exception as e:
                    self._reply(500, {"ok": False, "error": str(e)})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    data = json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    data = {}
                cmd = str(data.get("cmd") or data.get("command") or "").strip()
                if not cmd:
                    self._reply(400, {"ok": False, "error": "missing cmd"})
                    return
                try:
                    result = gateway.on_command(cmd)
                    self._reply(200, {"ok": True, "cmd": cmd, "result": result})
                except Exception as e:
                    self._reply(500, {"ok": False, "error": str(e)})

        try:
            self._httpd = HTTPServer((self.host, self.port), Handler)
        except OSError as e:
            print(f"[macro] bind failed on {self.host}:{self.port}: {e}")
            return
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            daemon=True,
            name="jarvis-macro",
        )
        self._thread.start()
        print(f"[macro] Stream Deck gateway on http://{self.host}:{self.port}/macro")

    def stop(self) -> None:
        if self._httpd:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            self._httpd = None
