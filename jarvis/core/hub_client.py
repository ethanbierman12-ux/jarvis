"""Bridge from PyQt Jarvis HUD → Hub & Spoke Node API (Sarah / Tom / Admin)."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from jarvis.config import ROOT

HUB_DIR = ROOT / "hub"
DEFAULT_URL = "http://127.0.0.1:8787"


class HubClient:
    """HTTP client + optional auto-start of the Hub API process."""

    def __init__(
        self,
        base_url: str = DEFAULT_URL,
        *,
        enabled: bool = True,
        auto_start: bool = True,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        self.base_url = (base_url or DEFAULT_URL).rstrip("/")
        self.enabled = enabled
        self.auto_start = auto_start
        self.on_log = on_log
        self.session_id: str | None = None
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def _log(self, msg: str) -> None:
        if self.on_log:
            try:
                self.on_log(msg)
            except Exception:
                pass
        print(f"[hub] {msg}")

    def health(self) -> dict[str, Any] | None:
        try:
            with urllib.request.urlopen(f"{self.base_url}/health", timeout=1.2) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            return None

    def ensure_running(self, wait_sec: float = 8.0) -> bool:
        if not self.enabled:
            return False
        if self.health():
            return True
        if not self.auto_start:
            return False
        with self._lock:
            if self.health():
                return True
            if self._proc and self._proc.poll() is None:
                # already starting
                pass
            else:
                self._spawn()
        deadline = time.time() + wait_sec
        while time.time() < deadline:
            if self.health():
                self._log("Hub online")
                return True
            time.sleep(0.35)
        self._log("Hub did not become ready in time")
        return False

    def _spawn(self) -> None:
        if not HUB_DIR.exists():
            self._log(f"Hub folder missing: {HUB_DIR}")
            return
        env = os.environ.copy()
        env.setdefault("MOCK_LLM", "true")
        # Parse port from base_url
        port = "8787"
        try:
            from urllib.parse import urlparse

            p = urlparse(self.base_url)
            if p.port:
                port = str(p.port)
        except Exception:
            pass
        env["JARVIS_PORT"] = port
        try:
            # Use npm script when available — more reliable than raw npx on Windows
            npm_cmd = ["npm", "run", "dev:server", "--silent"]
            kwargs: dict = {
                "cwd": str(HUB_DIR),
                "env": env,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if os.name == "nt":
                kwargs["creationflags"] = (
                    subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
                )
                kwargs["shell"] = True
            self._proc = subprocess.Popen(npm_cmd, **kwargs)
            self._log(f"Started Hub process pid={getattr(self._proc, 'pid', '?')}")
        except Exception as e:
            self._log(f"Failed to start Hub: {e}")
            try:
                self._proc = subprocess.Popen(
                    ["npx", "--yes", "tsx", "src/api/server.ts"],
                    cwd=str(HUB_DIR),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=(os.name == "nt"),
                )
            except Exception as e2:
                self._log(f"Hub fallback spawn failed: {e2}")

    def chat(self, text: str, *, speak: bool = False) -> dict[str, Any]:
        if not self.ensure_running():
            return {
                "ok": False,
                "reply": (
                    "Hub is offline. From the hub folder run: npm run dev:server "
                    "(or enable hub_auto_start)."
                ),
                "halted": False,
                "results": [],
            }
        payload = {
            "text": text,
            "sessionId": self.session_id,
            "speak": speak,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            return {"ok": False, "reply": f"Hub error {e.code}: {body[:200]}", "results": []}
        except Exception as e:
            return {"ok": False, "reply": f"Hub request failed: {e}", "results": []}

        if out.get("sessionId"):
            self.session_id = str(out["sessionId"])
        out["ok"] = True
        return out

    def halt(self) -> str:
        if not self.session_id:
            # still try global standby text
            out = self.chat("standby")
            return str(out.get("reply") or "Hub standby requested.")
        payload = json.dumps({"sessionId": self.session_id}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/v1/halt",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5).read()
        except Exception:
            pass
        return "Hub agents standing by."

    def resume(self) -> str:
        if not self.session_id:
            return "No Hub session yet."
        payload = json.dumps({"sessionId": self.session_id}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/v1/resume",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5).read()
        except Exception as e:
            return f"Hub resume failed: {e}"
        return "Hub session resumed."

    @staticmethod
    def wants_hub(text: str) -> bool:
        """True when the utterance should go to Hub & Spoke agents."""
        t = (text or "").lower().strip()
        if not t:
            return False
        # Explicit hub / spoke commands
        if re_search(
            t,
            r"\b(hub|sarah|tom|admin|ask tom|ask sarah|ask admin|"
            r"agent tom|agent sarah|agent admin|"
            r"support ticket|customer support|escalat(e|ion)|"
            r"open (a )?pr|pull request|mock pr|"
            r"multi[- ]?agent|spoke|"
            r"research|code review|refactor)\b",
        ):
            return True
        # Classic multi-agent example
        if re_search(
            t,
            r"schedule (a )?meeting with .*(complain|support|ticket|client who)",
        ) or re_search(t, r"(client|customer) who complain"):
            return True
        if re_search(t, r"\b(draft (a )?reply|support inbox|triage tickets?)\b"):
            return True
        if re_search(t, r"\b(investigate (the )?checkout|fix (the )?checkout bug)\b"):
            return True
        if re_search(t, r"\b(hub standby|stop agents|abort agents|resume hub)\b"):
            return True
        return False


def re_search(text: str, pattern: str) -> bool:
    import re

    return bool(re.search(pattern, text, re.I))
