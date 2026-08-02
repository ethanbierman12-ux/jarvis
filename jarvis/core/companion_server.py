"""iPhone companion — authenticated Tailscale-reachable PWA + chat API."""

from __future__ import annotations

import json
import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from jarvis.config import ROOT

COMPANION_WEB = ROOT / "jarvis" / "web" / "companion"
SPATIAL_WEB = ROOT / "jarvis" / "web" / "spatial"


def make_token() -> str:
    return secrets.token_urlsafe(24)


class CompanionServer:
    """
    Mobile web companion for iPhone (Safari → Add to Home Screen).

    Reachable on your Tailscale IP when bound to 0.0.0.0:
      http://100.x.y.z:8766/?token=...

    POST /api/chat  {"text":"weather"}  Authorization: Bearer <token>
    """

    def __init__(
        self,
        on_chat: Callable[[str], str],
        *,
        token: str,
        host: str = "0.0.0.0",
        port: int = 8766,
        web_root: Path | None = None,
        on_status: Callable[[], dict] | None = None,
        on_state: Callable[[], dict] | None = None,
        on_handoff: Callable[[dict], dict] | None = None,
        spatial_root: Path | None = None,
        spatial_enabled: bool = True,
    ) -> None:
        self.on_chat = on_chat
        self.on_status = on_status
        self.on_state = on_state
        self.on_handoff = on_handoff
        self.token = (token or "").strip()
        self.host = host
        self.port = int(port)
        self.web_root = Path(web_root or COMPANION_WEB)
        self.spatial_root = Path(spatial_root or SPATIAL_WEB)
        self.spatial_enabled = bool(spatial_enabled)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.last_reply: str = ""
        self.last_heard: str = ""
        self.handoff_note: str = ""

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not self.token:
            print("[companion] no token — refusing to start")
            return
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:  # noqa: A003
                return

            def _cors(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

            def _json(self, code: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._cors()
                self.end_headers()
                self.wfile.write(body)

            def _auth_ok(self) -> bool:
                auth = (self.headers.get("Authorization") or "").strip()
                if auth.lower().startswith("bearer "):
                    got = auth[7:].strip()
                    if secrets.compare_digest(got, server.token):
                        return True
                # Query / cookie for first load + Safari home-screen
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query)
                qtok = (qs.get("token") or [""])[0].strip()
                if qtok and secrets.compare_digest(qtok, server.token):
                    return True
                cookie = self.headers.get("Cookie") or ""
                for part in cookie.split(";"):
                    part = part.strip()
                    if part.startswith("jarvis_token="):
                        got = part.split("=", 1)[1].strip()
                        if got and secrets.compare_digest(got, server.token):
                            return True
                return False

            def do_OPTIONS(self) -> None:  # noqa: N802
                self.send_response(204)
                self._cors()
                self.end_headers()

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path or "/"

                if path in ("/api/health", "/health"):
                    self._json(
                        200,
                        {
                            "ok": True,
                            "service": "jarvis-companion",
                            "auth": self._auth_ok(),
                        },
                    )
                    return

                if path == "/api/status":
                    if not self._auth_ok():
                        self._json(401, {"ok": False, "error": "unauthorized"})
                        return
                    extra = {}
                    if server.on_status:
                        try:
                            extra = server.on_status() or {}
                        except Exception as e:
                            extra = {"status_error": str(e)}
                    self._json(
                        200,
                        {
                            "ok": True,
                            "last_heard": server.last_heard,
                            "last_reply": server.last_reply,
                            **extra,
                        },
                    )
                    return

                if path == "/api/state":
                    if not self._auth_ok():
                        self._json(401, {"ok": False, "error": "unauthorized"})
                        return
                    try:
                        state = server.on_state() if server.on_state else {}
                        self._json(200, {"ok": True, "state": state or {}})
                    except Exception as e:
                        self._json(500, {"ok": False, "error": str(e)})
                    return

                if path.startswith("/api/"):
                    self._json(404, {"ok": False, "error": "not found"})
                    return

                # Static PWAs — index needs token on first paint (or cookie).
                if path == "/spatial" or path.startswith("/spatial/"):
                    if not server.spatial_enabled:
                        self._json(404, {"ok": False, "error": "spatial HUD disabled"})
                        return
                    rel = path[len("/spatial") :].lstrip("/") or "index.html"
                    self._serve_static(rel, root=server.spatial_root)
                else:
                    self._serve_static(path)

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path or "/"
                if path not in ("/api/chat", "/api/handoff"):
                    self._json(404, {"ok": False, "error": "not found"})
                    return
                if not self._auth_ok():
                    self._json(401, {"ok": False, "error": "unauthorized"})
                    return
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(max(0, min(length, 64_000))) if length else b"{}"
                try:
                    data = json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    data = {}

                if path == "/api/handoff":
                    try:
                        payload = server.on_handoff(data) if server.on_handoff else {
                            "ok": True,
                            "note": "handoff accepted (no handler)",
                        }
                        if not isinstance(payload, dict):
                            payload = {"ok": True, "reply": str(payload)}
                        self._json(200, {"ok": True, **payload})
                    except Exception as e:
                        self._json(500, {"ok": False, "error": str(e)})
                    return

                text = str(
                    data.get("text") or data.get("cmd") or data.get("message") or ""
                ).strip()
                if not text:
                    self._json(400, {"ok": False, "error": "missing text"})
                    return
                if len(text) > 2000:
                    self._json(400, {"ok": False, "error": "text too long"})
                    return
                try:
                    server.last_heard = text
                    reply = server.on_chat(text) or "Done."
                    server.last_reply = reply
                    self._json(200, {"ok": True, "text": text, "reply": reply})
                except Exception as e:
                    self._json(500, {"ok": False, "error": str(e)})

            def _serve_static(self, path: str, *, root: Path | None = None) -> None:
                static_root = Path(root or server.web_root)
                if path in ("/", "", "/index.html"):
                    rel = "index.html"
                else:
                    rel = path.lstrip("/").replace("..", "")
                target = (static_root / rel).resolve()
                try:
                    target.relative_to(static_root.resolve())
                except ValueError:
                    self._json(403, {"ok": False, "error": "forbidden"})
                    return
                if not target.is_file():
                    self.send_response(404)
                    self.end_headers()
                    return
                mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                if target.suffix == ".webmanifest":
                    mime = "application/manifest+json"
                data = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                # Seed cookie when token is in the URL so later API calls work
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query)
                qtok = (qs.get("token") or [""])[0].strip()
                if qtok and secrets.compare_digest(qtok, server.token):
                    self.send_header(
                        "Set-Cookie",
                        f"jarvis_token={server.token}; Path=/; SameSite=Lax; HttpOnly",
                    )
                self._cors()
                self.end_headers()
                self.wfile.write(data)

        try:
            self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError as e:
            print(f"[companion] bind failed on {self.host}:{self.port}: {e}")
            return
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            daemon=True,
            name="jarvis-companion",
        )
        self._thread.start()
        print(
            f"[companion] iPhone PWA on http://{self.host}:{self.port}/ "
            f"(Tailscale → this PC:{self.port})"
        )

    def stop(self) -> None:
        if self._httpd:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            self._httpd = None
