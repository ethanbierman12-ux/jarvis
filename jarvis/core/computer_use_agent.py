"""Computer-use / browser-agent loop — screenshot → LLM → click/type → repeat.

Providers (pluggable):
  - ollama / local — free local path (Ollama + Playwright JSON action loop)
  - anthropic  — Claude Computer Use API (working when anthropic_api_key in vault)
  - openai     — vision + structured actions (working when openai_api_key in vault)
  - browser_use — optional open-source Agent (cloud key or local ChatOllama)
  - gemini / skyvern / openinterpreter — registered stubs (documented)

Desktop actions reuse pyautogui (same stack as jarvis.core.computer_use).
Browser actions prefer Playwright when installed; otherwise desktop + system browser.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import threading
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class ProviderId(str, Enum):
    AUTO = "auto"
    OLLAMA = "ollama"  # free/local — aliases: local, free
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    BROWSER_USE = "browser_use"
    DESKTOP = "desktop"  # local OCR/macro only — no cloud vision loop
    GEMINI = "gemini"
    SKYVERN = "skyvern"
    OPENINTERPRETER = "openinterpreter"


# Preferred Ollama vision tags (first installed match wins unless settings override)
VISION_MODEL_HINTS = (
    "llava",
    "llama3.2-vision",
    "llama3.2vision",
    "qwen2.5vl",
    "qwen2-vl",
    "qwen2vl",
    "minicpm-v",
    "minicpm",
    "moondream",
    "bakllava",
    "pixtral",
    "granite3.2-vision",
    "gemma3",
    "vision",
)
RECOMMENDED_VISION_PULL = "llava"
RECOMMENDED_TEXT_PULL = "llama3.2"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"


@dataclass
class AgentStatus:
    running: bool = False
    provider: str = ""
    step: int = 0
    max_steps: int = 0
    goal: str = ""
    last_action: str = ""
    last_error: str = ""
    cancelled: bool = False
    finished: bool = False
    result: str = ""


@dataclass
class ProviderInfo:
    id: str
    label: str
    status: str  # live | stub | optional
    note: str = ""


PROVIDERS: dict[str, ProviderInfo] = {
    ProviderId.OLLAMA.value: ProviderInfo(
        "ollama",
        "Ollama local (free)",
        "live",
        "No API credits — needs Ollama running + model (vision preferred)",
    ),
    ProviderId.ANTHROPIC.value: ProviderInfo(
        "anthropic",
        "Anthropic Claude Computer Use",
        "live",
        "Requires anthropic_api_key + display control (pyautogui)",
    ),
    ProviderId.OPENAI.value: ProviderInfo(
        "openai",
        "OpenAI vision + actions",
        "live",
        "Requires openai_api_key; Playwright preferred for browser tasks",
    ),
    ProviderId.BROWSER_USE.value: ProviderInfo(
        "browser_use",
        "browser-use (open source)",
        "optional",
        "pip install browser-use playwright; cloud key or local Ollama",
    ),
    ProviderId.DESKTOP.value: ProviderInfo(
        "desktop",
        "Local desktop macros",
        "live",
        "OCR/pyautogui only — no autonomous vision loop",
    ),
    ProviderId.GEMINI.value: ProviderInfo(
        "gemini",
        "Google Gemini computer use",
        "stub",
        "Future — see docs/HANDOVER_COMPUTER_USE.md",
    ),
    ProviderId.SKYVERN.value: ProviderInfo(
        "skyvern",
        "Skyvern",
        "stub",
        "Future — self-hosted browser agent",
    ),
    ProviderId.OPENINTERPRETER.value: ProviderInfo(
        "openinterpreter",
        "Open Interpreter",
        "stub",
        "Future — local code+computer agent",
    ),
}


# ---------------------------------------------------------------------------
# Surfaces (where clicks land)
# ---------------------------------------------------------------------------


class ActionSurface:
    """Minimal screen/browser surface the agent can drive."""

    kind: str = "base"

    def size(self) -> tuple[int, int]:
        raise NotImplementedError

    def screenshot_png(self) -> bytes:
        raise NotImplementedError

    def click(self, x: int, y: int, *, button: str = "left", clicks: int = 1) -> str:
        raise NotImplementedError

    def move(self, x: int, y: int) -> str:
        raise NotImplementedError

    def type_text(self, text: str) -> str:
        raise NotImplementedError

    def key(self, *keys: str) -> str:
        raise NotImplementedError

    def scroll(self, *, clicks: int = -3, x: int | None = None, y: int | None = None) -> str:
        raise NotImplementedError

    def goto(self, url: str) -> str:
        return "goto not supported on this surface."

    def close(self) -> None:
        pass


class DesktopSurface(ActionSurface):
    """Full desktop via pyautogui (Anthropic computer-use friendly)."""

    kind = "desktop"

    def __init__(self) -> None:
        import pyautogui

        pyautogui.FAILSAFE = True
        self._pg = pyautogui

    def size(self) -> tuple[int, int]:
        w, h = self._pg.size()
        return int(w), int(h)

    def screenshot_png(self) -> bytes:
        from io import BytesIO

        shot = self._pg.screenshot()
        buf = BytesIO()
        shot.save(buf, format="PNG")
        return buf.getvalue()

    def click(self, x: int, y: int, *, button: str = "left", clicks: int = 1) -> str:
        btn = "right" if button == "right" else "middle" if button == "middle" else "left"
        self._pg.moveTo(int(x), int(y), duration=0.15)
        self._pg.click(button=btn, clicks=max(1, int(clicks)))
        return f"clicked {btn} at {x},{y}"

    def move(self, x: int, y: int) -> str:
        self._pg.moveTo(int(x), int(y), duration=0.12)
        return f"moved to {x},{y}"

    def type_text(self, text: str) -> str:
        # Prefer clipboard paste for unicode; fall back to typewrite
        try:
            import pyperclip

            prev = ""
            try:
                prev = pyperclip.paste()
            except Exception:
                prev = ""
            pyperclip.copy(text)
            self._pg.hotkey("ctrl", "v")
            time.sleep(0.05)
            try:
                pyperclip.copy(prev)
            except Exception:
                pass
            return f"typed {len(text)} chars"
        except Exception:
            self._pg.typewrite(text, interval=0.02)
            return f"typed {len(text)} chars (ascii)"

    def key(self, *keys: str) -> str:
        mapped = []
        for k in keys:
            kk = (k or "").strip().lower().replace("control", "ctrl").replace("escape", "esc")
            if kk:
                mapped.append(kk)
        if not mapped:
            return "no key"
        if len(mapped) == 1:
            self._pg.press(mapped[0])
        else:
            self._pg.hotkey(*mapped)
        return f"key {'+'.join(mapped)}"

    def scroll(self, *, clicks: int = -3, x: int | None = None, y: int | None = None) -> str:
        if x is not None and y is not None:
            self._pg.moveTo(int(x), int(y), duration=0.08)
        self._pg.scroll(int(clicks))
        return f"scroll {clicks}"

    def goto(self, url: str) -> str:
        import webbrowser

        webbrowser.open(url)
        time.sleep(1.2)
        return f"opened {url} in system browser"


class PlaywrightSurface(ActionSurface):
    """Real Chromium window via Playwright (optional dependency)."""

    kind = "playwright"

    def __init__(self, *, headless: bool = False, start_url: str = "about:blank") -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            ) from e

        self._pw_cm = sync_playwright()
        self._pw = self._pw_cm.__enter__()
        self._browser = self._pw.chromium.launch(headless=bool(headless))
        self._page = self._browser.new_page(viewport={"width": 1280, "height": 800})
        if start_url:
            try:
                self._page.goto(start_url, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                pass

    def size(self) -> tuple[int, int]:
        vp = self._page.viewport_size or {"width": 1280, "height": 800}
        return int(vp["width"]), int(vp["height"])

    def screenshot_png(self) -> bytes:
        return self._page.screenshot(type="png", full_page=False)

    def click(self, x: int, y: int, *, button: str = "left", clicks: int = 1) -> str:
        btn = button if button in ("left", "right", "middle") else "left"
        self._page.mouse.click(float(x), float(y), button=btn, click_count=max(1, int(clicks)))
        return f"clicked {btn} at {x},{y}"

    def move(self, x: int, y: int) -> str:
        self._page.mouse.move(float(x), float(y))
        return f"moved to {x},{y}"

    def type_text(self, text: str) -> str:
        self._page.keyboard.type(text, delay=20)
        return f"typed {len(text)} chars"

    def key(self, *keys: str) -> str:
        # Playwright uses names like Control+KeyA or sequential presses
        mapped = []
        for k in keys:
            kk = (k or "").strip().lower().replace("control", "control").replace("ctrl", "Control")
            kk = kk.replace("alt", "Alt").replace("shift", "Shift").replace("win", "Meta")
            kk = kk.replace("cmd", "Meta").replace("enter", "Enter").replace("esc", "Escape")
            kk = kk.replace("tab", "Tab").replace("backspace", "Backspace")
            if len(kk) == 1:
                kk = kk.upper()
            mapped.append(kk)
        if not mapped:
            return "no key"
        if len(mapped) == 1:
            self._page.keyboard.press(mapped[0])
        else:
            combo = "+".join(mapped)
            self._page.keyboard.press(combo)
        return f"key {'+'.join(mapped)}"

    def scroll(self, *, clicks: int = -3, x: int | None = None, y: int | None = None) -> str:
        if x is not None and y is not None:
            self._page.mouse.move(float(x), float(y))
        # Playwright wheel: positive y scrolls down
        dy = -int(clicks) * 80
        self._page.mouse.wheel(0, dy)
        return f"scroll wheel {dy}"

    def goto(self, url: str) -> str:
        u = (url or "").strip()
        if not u:
            return "empty url"
        if not re.match(r"^https?://", u, re.I):
            u = "https://" + u
        self._page.goto(u, wait_until="domcontentloaded", timeout=60000)
        return f"navigated to {u}"

    def close(self) -> None:
        try:
            self._browser.close()
        except Exception:
            pass
        try:
            self._pw_cm.__exit__(None, None, None)
        except Exception:
            pass


def open_surface(
    *,
    prefer_browser: bool = True,
    headless: bool = False,
    start_url: str = "about:blank",
) -> ActionSurface:
    if prefer_browser:
        try:
            return PlaywrightSurface(headless=headless, start_url=start_url)
        except Exception as e:
            print(f"[computer-use] Playwright unavailable ({e}); using desktop surface")
    return DesktopSurface()


# ---------------------------------------------------------------------------
# Action execution (shared)
# ---------------------------------------------------------------------------


def apply_action(surface: ActionSurface, action: dict[str, Any]) -> str:
    """Execute one action dict from Anthropic/OpenAI schemas."""
    if not isinstance(action, dict):
        return "skipped non-dict action"
    act = str(action.get("action") or action.get("type") or "").strip().lower()
    if not act:
        return "empty action"

    if act in ("screenshot", "wait"):
        dur = float(action.get("duration") or action.get("seconds") or 0.6)
        time.sleep(max(0.1, min(dur, 8.0)))
        return f"waited {dur:.1f}s" if act == "wait" else "screenshot"

    if act in ("left_click", "click", "left_click_xy"):
        coord = action.get("coordinate") or action.get("coords") or [action.get("x"), action.get("y")]
        if not coord or coord[0] is None:
            return "click missing coordinates"
        clicks = 2 if act == "double_click" else int(action.get("clicks") or 1)
        return surface.click(int(coord[0]), int(coord[1]), clicks=clicks)

    if act in ("double_click", "triple_click"):
        coord = action.get("coordinate") or [action.get("x"), action.get("y")]
        n = 3 if act == "triple_click" else 2
        return surface.click(int(coord[0]), int(coord[1]), clicks=n)

    if act in ("right_click", "middle_click"):
        coord = action.get("coordinate") or [action.get("x"), action.get("y")]
        btn = "right" if "right" in act else "middle"
        return surface.click(int(coord[0]), int(coord[1]), button=btn)

    if act in ("mouse_move", "move", "move_mouse"):
        coord = action.get("coordinate") or [action.get("x"), action.get("y")]
        return surface.move(int(coord[0]), int(coord[1]))

    if act in ("type", "type_text", "insert_text"):
        text = str(action.get("text") or action.get("content") or "")
        return surface.type_text(text)

    if act in ("key", "hotkey", "press"):
        raw = action.get("text") or action.get("key") or action.get("keys") or ""
        if isinstance(raw, list):
            keys = [str(k) for k in raw]
        else:
            keys = re.split(r"[\s+]+", str(raw).strip())
        return surface.key(*[k for k in keys if k])

    if act == "scroll":
        # Anthropic: coordinate + scroll_direction + scroll_amount
        direction = str(action.get("scroll_direction") or action.get("direction") or "down").lower()
        amount = int(action.get("scroll_amount") or action.get("amount") or 3)
        clicks = amount if direction in ("up", "left") else -amount
        if direction in ("left", "right"):
            # approximate horizontal with vertical for desktop
            clicks = amount if direction == "left" else -amount
        coord = action.get("coordinate")
        x = y = None
        if isinstance(coord, (list, tuple)) and len(coord) >= 2:
            x, y = int(coord[0]), int(coord[1])
        return surface.scroll(clicks=clicks, x=x, y=y)

    if act in ("goto", "navigate", "open_url"):
        return surface.goto(str(action.get("url") or action.get("text") or ""))

    if act in ("left_click_drag", "drag"):
        start = action.get("start_coordinate") or action.get("from") or action.get("coordinate")
        end = action.get("coordinate") if action.get("start_coordinate") else action.get("to")
        if not start or not end:
            return "drag missing coords"
        surface.move(int(start[0]), int(start[1]))
        try:
            import pyautogui

            pyautogui.dragTo(int(end[0]), int(end[1]), duration=0.35, button="left")
            return f"dragged to {end[0]},{end[1]}"
        except Exception:
            surface.click(int(start[0]), int(start[1]))
            surface.move(int(end[0]), int(end[1]))
            return "drag approximated"

    if act in ("done", "finish", "success", "complete"):
        return "done"

    return f"unknown action: {act}"


def apply_anthropic_tool(name: str, inp: dict[str, Any], surface: ActionSurface) -> str:
    """Dispatch computer / bash / text_editor tool_use blocks."""
    n = (name or "computer").strip().lower()
    if n in ("computer", "computer_20250124"):
        return apply_action(surface, inp)

    if n in ("bash", "bash_20250124"):
        cmd = str(inp.get("command") or inp.get("cmd") or "").strip()
        if not cmd:
            return "bash: empty command"
        # Hard deny destructive patterns
        low = cmd.lower()
        if any(
            x in low
            for x in (
                "rm -rf /",
                "format ",
                "mkfs",
                "del /s",
                "rd /s",
                "force push",
                "shutdown",
                "remove-item -recurse",
            )
        ):
            return "bash blocked: destructive command refused"
        try:
            import subprocess

            p = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=45,
            )
            out = ((p.stdout or "") + (p.stderr or ""))[-4000:]
            return f"exit {p.returncode}\n{out}" or f"exit {p.returncode}"
        except Exception as e:
            return f"bash error: {e}"

    if n in ("str_replace_editor", "text_editor", "str_replace_based_edit_tool"):
        cmd = str(inp.get("command") or "").strip().lower()
        path = str(inp.get("path") or "").strip()
        if not path:
            return "editor: missing path"
        # Confine to home / jarvis trees
        try:
            from pathlib import Path

            p = Path(path).expanduser().resolve()
            home = Path.home().resolve()
            root = Path(__file__).resolve().parents[2]
            if not (str(p).startswith(str(home)) or str(p).startswith(str(root))):
                return "editor blocked: path outside home/jarvis"
            if cmd in ("view", "read"):
                if not p.exists():
                    return f"editor: missing {p}"
                data = p.read_text(encoding="utf-8", errors="replace")
                return data[:8000]
            if cmd in ("create",):
                file_text = str(inp.get("file_text") or "")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(file_text, encoding="utf-8")
                return f"created {p}"
            if cmd in ("str_replace", "replace"):
                old = str(inp.get("old_str") or "")
                new = str(inp.get("new_str") or "")
                raw = p.read_text(encoding="utf-8", errors="replace")
                if old not in raw:
                    return "editor: old_str not found"
                p.write_text(raw.replace(old, new, 1), encoding="utf-8")
                return f"replaced in {p}"
            if cmd in ("insert",):
                insert = str(inp.get("new_str") or inp.get("insert_text") or "")
                line = int(inp.get("insert_line") or 1)
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines(True)
                idx = max(0, min(len(lines), line - 1))
                lines.insert(idx, insert if insert.endswith("\n") else insert + "\n")
                p.write_text("".join(lines), encoding="utf-8")
                return f"inserted at line {line} in {p}"
            return f"editor: unsupported command {cmd}"
        except Exception as e:
            return f"editor error: {e}"

    return f"unknown tool: {name}"


# ---------------------------------------------------------------------------
# HTTP helpers (no hard deps on anthropic/openai SDKs)
# ---------------------------------------------------------------------------


def sanitize_api_key(value: str) -> str:
    """Strip wrappers/whitespace; prefer shared vault sanitizer when available."""
    try:
        from jarvis.core.secrets_vault import sanitize_secret

        return sanitize_secret(value)
    except Exception:
        return (value or "").strip().strip("\"'")


def normalize_provider_name(name: str) -> str:
    """Map voice aliases (local/free) onto canonical provider ids."""
    n = (name or "").strip().lower().replace("-", "_")
    if n in ("local", "free", "ollama_local", "offline"):
        return ProviderId.OLLAMA.value
    if n in ("browseruse", "browser_use"):
        return ProviderId.BROWSER_USE.value
    return n


def ollama_host_url(host: str = "") -> str:
    h = (host or DEFAULT_OLLAMA_HOST).strip().rstrip("/")
    if not h.startswith("http"):
        h = "http://" + h
    return h


def ollama_bin_present() -> bool:
    if shutil.which("ollama"):
        return True
    for p in (
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        r"C:\Program Files\Ollama\ollama.exe",
    ):
        if p and os.path.isfile(p):
            return True
    return False


def _model_is_vision(name: str) -> bool:
    n = (name or "").lower()
    return any(k in n for k in VISION_MODEL_HINTS)


def list_ollama_models(host: str = "", *, timeout: float = 2.0) -> tuple[str, list[str], str]:
    """
    Probe Ollama tags endpoint.
    Returns (state, model_names, detail) where state is:
      ready | not_running | not_installed | error
    """
    base = ollama_host_url(host)
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
        names = [
            str(m.get("name") or "").strip()
            for m in (data.get("models") or [])
            if isinstance(m, dict) and m.get("name")
        ]
        if not names:
            return "ready", [], "Ollama is running but no models are installed"
        return "ready", names, "ok"
    except Exception as e:
        if ollama_bin_present():
            return (
                "not_running",
                [],
                "Ollama is installed but not running — start it from the Start menu "
                "or run: ollama serve",
            )
        return (
            "not_installed",
            [],
            "Ollama not found — install from https://ollama.com/download then restart Jarvis",
        )


def pick_ollama_model(
    models: list[str],
    *,
    preferred: str = "",
    want_vision: bool = True,
) -> tuple[str, bool]:
    """
    Choose a model name. Returns (model, is_vision).
    Empty model means nothing usable.
    """
    pref = (preferred or "").strip()
    if pref:
        # Exact or prefix match against installed tags
        for m in models:
            if m == pref or m.startswith(pref + ":") or pref in m:
                return m, _model_is_vision(m)
        # User forced a name even if not listed yet (pull in progress) — still try
        if ":" in pref or pref:
            return pref, _model_is_vision(pref) or want_vision

    vision = [m for m in models if _model_is_vision(m)]
    if want_vision and vision:
        # Prefer known strong tags in hint order
        for hint in VISION_MODEL_HINTS:
            for m in vision:
                if hint in m.lower():
                    return m, True
        return vision[0], True
    if models:
        return models[0], False
    return "", False


def ollama_setup_hint(*, has_vision: bool = False, model: str = "") -> str:
    if has_vision and model:
        return f"Vision model ready ({model})"
    if model:
        return (
            f"Text model only ({model}) — URL/type workflows work; "
            f"for screenshot clicks run: ollama pull {RECOMMENDED_VISION_PULL}"
        )
    return (
        f"Pull a model: ollama pull {RECOMMENDED_VISION_PULL} "
        f"(vision) or ollama pull {RECOMMENDED_TEXT_PULL} (text-only)"
    )


def _prepare_ollama_image(png: bytes, *, max_side: int = 1024) -> tuple[str, int, int]:
    """Return (base64_jpeg_or_png, width, height) for Ollama images[]."""
    try:
        from io import BytesIO

        from PIL import Image

        im = Image.open(BytesIO(png)).convert("RGB")
        w, h = im.size
        if max(w, h) > max_side:
            scale = max_side / max(w, h)
            w, h = max(1, int(w * scale)), max(1, int(h * scale))
            im = im.resize((w, h))
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=72)
        return base64.standard_b64encode(buf.getvalue()).decode("ascii"), w, h
    except Exception:
        return _b64_png(png), 1280, 800


def _ollama_chat(
    host: str,
    *,
    model: str,
    messages: list[dict[str, Any]],
    timeout: float = 180.0,
    num_predict: int = 900,
) -> str:
    base = ollama_host_url(host)
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": int(num_predict)},
    }
    data = _http_json(
        f"{base}/api/chat",
        headers={"content-type": "application/json"},
        body=body,
        timeout=timeout,
    )
    msg = data.get("message") or {}
    if isinstance(msg, dict):
        return str(msg.get("content") or "")
    return str(data.get("response") or "")


def _http_json(
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float = 120.0,
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"HTTP {e.code}: {err_body}") from e


def _b64_png(png: bytes) -> str:
    return base64.standard_b64encode(png).decode("ascii")


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class BaseProvider:
    id: str = "base"
    label: str = "base"

    def available(self) -> tuple[bool, str]:
        return False, "not implemented"

    def run(
        self,
        goal: str,
        *,
        surface: ActionSurface,
        max_steps: int,
        should_stop: Callable[[], bool],
        on_step: Callable[[int, str], None] | None = None,
    ) -> str:
        raise NotImplementedError


class AnthropicComputerUseProvider(BaseProvider):
    """Claude computer-use tool loop (Messages API + beta header)."""

    id = ProviderId.ANTHROPIC.value
    label = "Anthropic Claude Computer Use"

    def __init__(
        self,
        api_key: str = "",
        *,
        model: str = "claude-sonnet-4-5",
        beta: str = "computer-use-2025-01-24",
        tool_type: str = "computer_20250124",
    ) -> None:
        self.api_key = sanitize_api_key(api_key)
        self.model = (model or "claude-sonnet-4-5").strip()
        self.beta = (beta or "computer-use-2025-01-24").strip()
        self.tool_type = (tool_type or "computer_20250124").strip()

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "Missing anthropic_api_key — say set anthropic key to YOUR_KEY"
        if self.api_key.startswith("sk-") and not self.api_key.startswith("sk-ant-"):
            return (
                False,
                "anthropic_api_key looks like an OpenAI key — need sk-ant-… from console.anthropic.com",
            )
        return True, "ready"

    def run(
        self,
        goal: str,
        *,
        surface: ActionSurface,
        max_steps: int,
        should_stop: Callable[[], bool],
        on_step: Callable[[int, str], None] | None = None,
    ) -> str:
        ok, why = self.available()
        if not ok:
            return why

        w, h = surface.size()
        # Cap resolution for token cost; scale coords if needed
        max_w, max_h = 1280, 800
        scale = 1.0
        if w > max_w or h > max_h:
            scale = min(max_w / w, max_h / h)

        disp_w = int(w * scale) if scale < 1 else w
        disp_h = int(h * scale) if scale < 1 else h
        tools = [
            {
                "type": self.tool_type,
                "name": "computer",
                "display_width_px": disp_w,
                "display_height_px": disp_h,
                "display_number": 1,
            },
            # Anthropic computer-use suite parity (desktop maps these carefully)
            {
                "type": "text_editor_20250124",
                "name": "str_replace_editor",
            },
            {
                "type": "bash_20250124",
                "name": "bash",
            },
        ]
        system = (
            "You are Jarvis computer-use with full Anthropic tool parity "
            "(computer + text editor + bash). Drive the real display to complete the goal. "
            "Use the computer tool for GUI; str_replace_editor for local file edits under the "
            "user project; bash for read-only diagnostics and careful scripted commands. "
            "Never destroy data, never force-push, never spend money. "
            "Finish with a short text summary when done."
        )
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": goal.strip()},
        ]
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": self.beta,
        }
        last_text = ""

        for step in range(1, max_steps + 1):
            if should_stop():
                return f"Cancelled at step {step}."
            if on_step:
                on_step(step, "thinking")

            body = {
                "model": self.model,
                "max_tokens": 4096,
                "system": system,
                "tools": tools,
                "messages": messages,
            }
            data = _http_json(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                body=body,
            )
            content = data.get("content") or []
            stop = data.get("stop_reason") or ""
            messages.append({"role": "assistant", "content": content})

            tool_uses = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
            texts = [
                str(b.get("text") or "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            if texts:
                last_text = " ".join(texts).strip()

            if not tool_uses:
                if on_step:
                    on_step(step, last_text[:80] or stop or "done")
                return last_text or f"Completed after {step} steps ({stop})."

            results: list[dict[str, Any]] = []
            for tu in tool_uses:
                if should_stop():
                    return f"Cancelled at step {step}."
                name = tu.get("name") or "computer"
                inp = tu.get("input") or {}
                if not isinstance(inp, dict):
                    inp = {}
                # Scale model coords back to real display if we downscaled tool dims
                inp = dict(inp)
                for key in ("coordinate", "start_coordinate"):
                    if key in inp and isinstance(inp[key], (list, tuple)) and scale < 1:
                        inp[key] = [int(inp[key][0] / scale), int(inp[key][1] / scale)]
                note = apply_anthropic_tool(str(name), inp, surface)
                if on_step:
                    on_step(step, f"{name}: {note[:70]}")
                content_blocks: list[dict[str, Any]] = [{"type": "text", "text": note}]
                # Screenshot after GUI tools; text-only for bash/editor
                if str(name).lower() in ("computer", "computer_20250124"):
                    png = surface.screenshot_png()
                    if scale < 1:
                        png = _resize_png(png, int(w * scale), int(h * scale))
                    content_blocks.insert(
                        0,
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": _b64_png(png),
                            },
                        },
                    )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.get("id"),
                        "content": content_blocks,
                    }
                )
                if str(inp.get("action") or "").lower() in ("done", "finish", "complete"):
                    return last_text or note

            messages.append({"role": "user", "content": results})
            if stop == "end_turn" and not tool_uses:
                break

        return last_text or f"Reached max steps ({max_steps})."


class OpenAIVisionProvider(BaseProvider):
    """Operator-style: screenshot → GPT vision → JSON action list."""

    id = ProviderId.OPENAI.value
    label = "OpenAI vision + actions"

    def __init__(
        self,
        api_key: str = "",
        *,
        model: str = "gpt-4.1",
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = sanitize_api_key(api_key)
        self.model = (model or "gpt-4.1").strip()
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "Missing openai_api_key — say set openai key to YOUR_KEY"
        return True, "ready"

    def run(
        self,
        goal: str,
        *,
        surface: ActionSurface,
        max_steps: int,
        should_stop: Callable[[], bool],
        on_step: Callable[[int, str], None] | None = None,
    ) -> str:
        ok, why = self.available()
        if not ok:
            return why

        w, h = surface.size()
        schema_hint = (
            "Respond with ONLY JSON: "
            '{"done": false, "summary": "", "actions": [{"action": "click|type|key|scroll|goto|wait|done", '
            '"x": 0, "y": 0, "text": "", "url": "", "keys": "ctrl+l", "clicks": -3, "seconds": 1}]}. '
            f"Screen size is {w}x{h}. Coordinates are absolute pixels. "
            "Use goto for URLs when the surface supports it. Set done=true when the goal is finished."
        )
        history: list[str] = []

        for step in range(1, max_steps + 1):
            if should_stop():
                return f"Cancelled at step {step}."
            if on_step:
                on_step(step, "seeing")

            png = surface.screenshot_png()
            user_text = (
                f"Goal: {goal}\n"
                f"Step {step}/{max_steps}. Recent: {'; '.join(history[-5:]) or 'start'}\n"
                f"{schema_hint}"
            )
            body = {
                "model": self.model,
                "max_tokens": 1200,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a careful computer-use agent. Plan one short burst of UI actions. "
                            "Never invent credentials. Do not complete purchases."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{_b64_png(png)}",
                                },
                            },
                        ],
                    },
                ],
            }
            data = _http_json(
                f"{self.base_url}/chat/completions",
                headers={
                    "content-type": "application/json",
                    "authorization": f"Bearer {self.api_key}",
                },
                body=body,
            )
            raw = ""
            try:
                raw = data["choices"][0]["message"]["content"] or ""
            except Exception:
                raw = json.dumps(data)[:400]
            parsed = _parse_json_blob(raw)
            if not parsed:
                history.append("parse_fail")
                if on_step:
                    on_step(step, "parse fail")
                continue

            if parsed.get("done") or str(parsed.get("summary") or "").lower().startswith("done"):
                summary = str(parsed.get("summary") or "Done.").strip()
                if on_step:
                    on_step(step, summary[:80])
                return summary

            actions = parsed.get("actions") or []
            if isinstance(actions, dict):
                actions = [actions]
            if not actions:
                # allow single action at top level
                if parsed.get("action"):
                    actions = [parsed]
            notes: list[str] = []
            for act in actions[:6]:
                if should_stop():
                    return f"Cancelled at step {step}."
                if not isinstance(act, dict):
                    continue
                # normalize x,y into coordinate
                if "coordinate" not in act and act.get("x") is not None:
                    act = {**act, "coordinate": [act.get("x"), act.get("y")]}
                if act.get("keys") and not act.get("text") and str(act.get("action")).lower() in (
                    "key",
                    "hotkey",
                    "press",
                ):
                    act = {**act, "text": act.get("keys")}
                note = apply_action(surface, act)
                notes.append(note)
                if str(act.get("action") or "").lower() in ("done", "finish", "complete"):
                    summary = str(parsed.get("summary") or note)
                    return summary
                time.sleep(0.25)
            burst = "; ".join(notes) if notes else "no-op"
            history.append(burst[:120])
            if on_step:
                on_step(step, burst[:80])
            if parsed.get("done"):
                return str(parsed.get("summary") or burst)

        return f"Reached max steps ({max_steps}). Last: {history[-1] if history else '—'}"


class OllamaComputerUseProvider(BaseProvider):
    """Free/local: Ollama → JSON actions → Playwright/desktop. Vision preferred."""

    id = ProviderId.OLLAMA.value
    label = "Ollama local (free)"

    def __init__(
        self,
        *,
        host: str = DEFAULT_OLLAMA_HOST,
        model: str = "",
    ) -> None:
        self.host = ollama_host_url(host)
        self.model_pref = (model or "").strip()
        self._resolved_model = ""
        self._vision = False
        self._last_detail = ""

    def _refresh(self) -> tuple[bool, str]:
        state, models, detail = list_ollama_models(self.host)
        self._last_detail = detail
        if state == "not_installed":
            return False, detail
        if state == "not_running":
            return False, detail
        if state != "ready":
            return False, detail or "Ollama probe failed"
        if not models and not self.model_pref:
            return (
                False,
                f"Ollama is running but has no models. {ollama_setup_hint()}",
            )
        if self.model_pref:
            matched = any(
                m == self.model_pref
                or m.startswith(self.model_pref + ":")
                or self.model_pref in m
                for m in models
            )
            if not matched:
                return (
                    False,
                    f"Ollama model '{self.model_pref}' not installed — run: ollama pull {self.model_pref}",
                )
        model, is_vision = pick_ollama_model(
            models, preferred=self.model_pref, want_vision=True
        )
        if not model:
            return False, f"No usable Ollama model. {ollama_setup_hint()}"
        self._resolved_model = model
        self._vision = is_vision
        hint = ollama_setup_hint(has_vision=is_vision, model=model)
        mode = "vision" if is_vision else "text-only"
        return True, f"ready · {model} · {mode} · {hint}"

    def available(self) -> tuple[bool, str]:
        return self._refresh()

    def run(
        self,
        goal: str,
        *,
        surface: ActionSurface,
        max_steps: int,
        should_stop: Callable[[], bool],
        on_step: Callable[[int, str], None] | None = None,
    ) -> str:
        ok, why = self.available()
        if not ok:
            return why

        model = self._resolved_model
        vision = self._vision
        w, h = surface.size()
        schema = (
            '{"done": false, "summary": "", "actions": ['
            '{"action": "click|type|key|scroll|goto|wait|done", '
            '"x": 0, "y": 0, "text": "", "url": "", "keys": "ctrl+l", '
            '"clicks": -3, "seconds": 1}]}'
        )
        if vision:
            system = (
                "You are a careful computer-use agent running fully offline via Ollama. "
                "Look at the screenshot and return ONLY JSON matching the schema. "
                "Plan a short burst of UI actions. Never invent credentials. "
                "Do not complete purchases or send messages."
            )
        else:
            system = (
                "You are a careful computer-use agent running fully offline via Ollama. "
                "No screenshot vision is available — use URL-first workflows only: "
                "goto/navigate, type, key, wait, done. Do NOT emit click with coordinates. "
                "Return ONLY JSON. Prefer direct URLs (Google Maps, search pages). "
                "Never invent credentials. Do not complete purchases."
            )

        history: list[str] = []
        if not vision:
            history.append(
                f"note: text-only mode — pull vision with: ollama pull {RECOMMENDED_VISION_PULL}"
            )

        for step in range(1, max_steps + 1):
            if should_stop():
                return f"Cancelled at step {step}."
            if on_step:
                on_step(step, "seeing" if vision else "planning")

            schema_hint = (
                f"Respond with ONLY JSON: {schema}. "
                f"Viewport is {w}x{h} pixels. Coordinates are absolute. "
                "Use goto for URLs. Set done=true when finished."
            )
            user_text = (
                f"Goal: {goal}\n"
                f"Step {step}/{max_steps}. Recent: {'; '.join(history[-5:]) or 'start'}\n"
                f"{schema_hint}"
            )
            messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
            if vision:
                png = surface.screenshot_png()
                b64, iw, ih = _prepare_ollama_image(png)
                user_text = (
                    f"Goal: {goal}\n"
                    f"Step {step}/{max_steps}. Recent: {'; '.join(history[-5:]) or 'start'}\n"
                    f"Image size is {iw}x{ih} (map clicks to these coordinates).\n"
                    f"{schema_hint}"
                )
                messages.append(
                    {
                        "role": "user",
                        "content": user_text,
                        "images": [b64],
                    }
                )
                # Scale model coords from image space → surface space
                scale_x = (w / iw) if iw else 1.0
                scale_y = (h / ih) if ih else 1.0
            else:
                messages.append({"role": "user", "content": user_text})
                scale_x = scale_y = 1.0

            try:
                raw = _ollama_chat(
                    self.host,
                    model=model,
                    messages=messages,
                    timeout=180.0,
                )
            except Exception as e:
                err = str(e)
                if "not found" in err.lower() or "404" in err:
                    return (
                        f"Ollama model '{model}' missing — run: ollama pull {model} "
                        f"(vision: ollama pull {RECOMMENDED_VISION_PULL})"
                    )
                return f"Ollama request failed: {err}"

            parsed = _parse_json_blob(raw)
            if not parsed:
                history.append("parse_fail")
                if on_step:
                    on_step(step, "parse fail")
                continue

            if parsed.get("done") or str(parsed.get("summary") or "").lower().startswith("done"):
                summary = str(parsed.get("summary") or "Done.").strip()
                if on_step:
                    on_step(step, summary[:80])
                if not vision:
                    summary = (
                        f"{summary} (text-only Ollama — "
                        f"ollama pull {RECOMMENDED_VISION_PULL} for screenshot clicks)"
                    )
                return summary

            actions = parsed.get("actions") or []
            if isinstance(actions, dict):
                actions = [actions]
            if not actions and parsed.get("action"):
                actions = [parsed]

            notes: list[str] = []
            for act in actions[:6]:
                if should_stop():
                    return f"Cancelled at step {step}."
                if not isinstance(act, dict):
                    continue
                act = dict(act)
                # In text-only mode, drop coordinate clicks
                a_name = str(act.get("action") or act.get("type") or "").lower()
                if not vision and a_name in (
                    "click",
                    "left_click",
                    "double_click",
                    "right_click",
                    "middle_click",
                    "mouse_move",
                    "move",
                    "scroll",
                ):
                    notes.append(f"skipped {a_name} (need vision model)")
                    continue
                if "coordinate" not in act and act.get("x") is not None:
                    try:
                        x = int(float(act["x"]) * scale_x)
                        y = int(float(act.get("y") or 0) * scale_y)
                        act["coordinate"] = [x, y]
                    except Exception:
                        pass
                elif vision and isinstance(act.get("coordinate"), (list, tuple)):
                    try:
                        c = act["coordinate"]
                        act["coordinate"] = [
                            int(float(c[0]) * scale_x),
                            int(float(c[1]) * scale_y),
                        ]
                    except Exception:
                        pass
                if act.get("keys") and not act.get("text") and a_name in (
                    "key",
                    "hotkey",
                    "press",
                ):
                    act["text"] = act.get("keys")
                note = apply_action(surface, act)
                notes.append(note)
                if a_name in ("done", "finish", "complete"):
                    return str(parsed.get("summary") or note)
                time.sleep(0.25)

            burst = "; ".join(notes) if notes else "no-op"
            history.append(burst[:120])
            if on_step:
                on_step(step, burst[:80])
            if parsed.get("done"):
                return str(parsed.get("summary") or burst)

        return f"Reached max steps ({max_steps}). Last: {history[-1] if history else '—'}"


class BrowserUseProvider(BaseProvider):
    """Optional browser-use package (cloud LLM or local ChatOllama)."""

    id = ProviderId.BROWSER_USE.value
    label = "browser-use"

    def __init__(
        self,
        api_key: str = "",
        *,
        openai_key: str = "",
        anthropic_key: str = "",
        ollama_host: str = DEFAULT_OLLAMA_HOST,
        ollama_model: str = "",
        allow_ollama: bool = True,
    ) -> None:
        self.api_key = (api_key or openai_key or anthropic_key or "").strip()
        self.openai_key = (openai_key or "").strip()
        self.anthropic_key = (anthropic_key or "").strip()
        self.ollama_host = ollama_host_url(ollama_host)
        self.ollama_model = (ollama_model or "").strip()
        self.allow_ollama = bool(allow_ollama)
        self._ollama_pick = ""

    def available(self) -> tuple[bool, str]:
        try:
            import browser_use  # noqa: F401
        except Exception:
            return (
                False,
                "browser-use not installed — pip install browser-use && playwright install chromium",
            )
        if self.openai_key or self.anthropic_key or self.api_key:
            return True, "ready"
        if self.allow_ollama:
            state, models, detail = list_ollama_models(self.ollama_host)
            if state == "ready":
                model, _ = pick_ollama_model(
                    models, preferred=self.ollama_model, want_vision=False
                )
                if model:
                    self._ollama_pick = model
                    return True, f"ready via Ollama ({model})"
                return False, f"browser-use needs a model. {ollama_setup_hint()}"
            return False, detail
        return False, "Need openai_api_key, anthropic_api_key, or running Ollama for browser-use"

    def run(
        self,
        goal: str,
        *,
        surface: ActionSurface,
        max_steps: int,
        should_stop: Callable[[], bool],
        on_step: Callable[[int, str], None] | None = None,
    ) -> str:
        ok, why = self.available()
        if not ok:
            return why
        # Close our surface — browser-use owns its own browser
        try:
            surface.close()
        except Exception:
            pass
        try:
            from browser_use import Agent

            llm = None
            try:
                if self.openai_key:
                    from browser_use.llm import ChatOpenAI

                    llm = ChatOpenAI(model="gpt-4.1", api_key=self.openai_key)
                elif self.anthropic_key:
                    from browser_use.llm import ChatAnthropic

                    llm = ChatAnthropic(model="claude-sonnet-4-5", api_key=self.anthropic_key)
                elif self.allow_ollama:
                    from browser_use.llm import ChatOllama

                    model = self._ollama_pick or self.ollama_model
                    if not model:
                        state, models, _ = list_ollama_models(self.ollama_host)
                        if state == "ready":
                            model, _ = pick_ollama_model(
                                models, preferred=self.ollama_model, want_vision=False
                            )
                    if not model:
                        return f"No Ollama model for browser-use. {ollama_setup_hint()}"
                    llm = ChatOllama(model=model, host=self.ollama_host, timeout=180.0)
            except Exception as e:
                llm = None
                adapter_err = str(e)
            else:
                adapter_err = ""

            if llm is None:
                return (
                    "browser-use installed but LLM adapter failed. "
                    + (adapter_err or "Ensure browser-use + ollama package, or a cloud API key.")
                )

            if on_step:
                on_step(1, "browser-use starting")
            agent = Agent(task=goal, llm=llm, max_actions_per_step=5)
            import asyncio

            async def _go() -> Any:
                return await agent.run(max_steps=max_steps)

            try:
                result = asyncio.run(_go())
            except RuntimeError:
                # nested loop — best effort
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(_go())
                finally:
                    loop.close()
            if should_stop():
                return "Cancelled during browser-use."
            return str(result)[:500] if result is not None else "browser-use finished."
        except Exception as e:
            return f"browser-use failed: {e}"


class StubProvider(BaseProvider):
    def __init__(self, pid: str, label: str, note: str) -> None:
        self.id = pid
        self.label = label
        self.note = note

    def available(self) -> tuple[bool, str]:
        return False, f"{self.label} is a stub — {self.note}"

    def run(self, goal: str, **kwargs: Any) -> str:
        return self.available()[1]


class DesktopMacroProvider(BaseProvider):
    """No LLM loop — only reports that autonomous mode needs a local or cloud brain."""

    id = ProviderId.DESKTOP.value
    label = "Desktop macros"

    def available(self) -> tuple[bool, str]:
        return True, "local click/type only (no vision loop)"

    def run(
        self,
        goal: str,
        *,
        surface: ActionSurface,
        max_steps: int,
        should_stop: Callable[[], bool],
        on_step: Callable[[int, str], None] | None = None,
    ) -> str:
        return (
            "Desktop provider has no autonomous vision loop. "
            "Free path: say computer use provider local, install Ollama, "
            f"ollama pull {RECOMMENDED_VISION_PULL}, then retry. "
            "Or set anthropic/openai key for cloud."
        )


def _parse_json_blob(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
    if not t:
        return None
    # strip markdown fences
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
    if m:
        t = m.group(1).strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", t)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _resize_png(png: bytes, width: int, height: int) -> bytes:
    try:
        from io import BytesIO

        from PIL import Image

        im = Image.open(BytesIO(png))
        im = im.resize((max(1, width), max(1, height)))
        buf = BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return png


# ---------------------------------------------------------------------------
# Agent orchestrator
# ---------------------------------------------------------------------------


@dataclass
class ComputerUseAgent:
    """Session manager for computer-use runs (thread-safe cancel/status)."""

    enabled: bool = True
    provider_name: str = "auto"
    max_steps: int = 40
    headless: bool = False
    confirm_long_runs: bool = True
    confirm_steps: int = 8
    prefer_local: bool = True
    ollama_host: str = DEFAULT_OLLAMA_HOST
    ollama_model: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    openai_model: str = "gpt-4.1"
    on_status: Callable[[AgentStatus], None] | None = None

    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)
    status: AgentStatus = field(default_factory=AgentStatus)

    def configure_from_settings(self, settings: Any) -> None:
        self.enabled = bool(getattr(settings, "computer_use_enabled", True))
        self.provider_name = normalize_provider_name(
            str(getattr(settings, "computer_use_provider", "auto") or "auto")
        )
        self.max_steps = int(getattr(settings, "computer_use_max_steps", 40) or 40)
        self.headless = bool(getattr(settings, "computer_use_headless", False))
        self.confirm_long_runs = bool(getattr(settings, "computer_use_confirm_long_runs", True))
        self.confirm_steps = int(getattr(settings, "computer_use_confirm_steps", 8) or 8)
        self.prefer_local = bool(getattr(settings, "computer_use_prefer_local", True))
        self.ollama_host = ollama_host_url(
            str(getattr(settings, "computer_use_ollama_host", "") or DEFAULT_OLLAMA_HOST)
        )
        self.ollama_model = str(getattr(settings, "computer_use_ollama_model", "") or "").strip()
        self.anthropic_api_key = sanitize_api_key(
            str(getattr(settings, "anthropic_api_key", "") or "")
        )
        self.openai_api_key = sanitize_api_key(
            str(getattr(settings, "openai_api_key", "") or "")
        )
        self.anthropic_model = str(
            getattr(settings, "computer_use_anthropic_model", "") or "claude-sonnet-4-5"
        )
        self.openai_model = str(
            getattr(settings, "computer_use_openai_model", "") or "gpt-4.1"
        )

    def providers_blurb(self) -> str:
        bits = []
        for p in PROVIDERS.values():
            bits.append(f"{p.id}[{p.status}]")
        return " · ".join(bits)

    def resolve_provider(self, name: str = "") -> BaseProvider:
        want = normalize_provider_name(name or self.provider_name or "auto")
        ollama = OllamaComputerUseProvider(
            host=self.ollama_host, model=self.ollama_model
        )
        anthropic = AnthropicComputerUseProvider(
            self.anthropic_api_key, model=self.anthropic_model
        )
        openai = OpenAIVisionProvider(self.openai_api_key, model=self.openai_model)
        browser_use = BrowserUseProvider(
            openai_key=self.openai_api_key,
            anthropic_key=self.anthropic_api_key,
            ollama_host=self.ollama_host,
            ollama_model=self.ollama_model,
            allow_ollama=True,
        )
        desktop = DesktopMacroProvider()
        stubs = {
            ProviderId.GEMINI.value: StubProvider(
                "gemini", "Gemini computer use", "not wired yet — see handover doc"
            ),
            ProviderId.SKYVERN.value: StubProvider(
                "skyvern", "Skyvern", "not wired yet — see handover doc"
            ),
            ProviderId.OPENINTERPRETER.value: StubProvider(
                "openinterpreter",
                "Open Interpreter",
                "not wired yet — see handover doc",
            ),
        }

        if want == "auto":
            cloud_ready = anthropic.available()[0] or openai.available()[0]
            # Prefer free/local when asked, or when no cloud keys work
            local_first = bool(self.prefer_local) or not cloud_ready
            if local_first:
                order = (ollama, browser_use, anthropic, openai)
            else:
                order = (anthropic, openai, browser_use, ollama)
            for p in order:
                ok, _ = p.available()
                if ok:
                    return p
            return desktop
        if want == ProviderId.OLLAMA.value:
            return ollama
        if want == ProviderId.ANTHROPIC.value:
            return anthropic
        if want == ProviderId.OPENAI.value:
            return openai
        if want == ProviderId.BROWSER_USE.value:
            return browser_use
        if want == ProviderId.DESKTOP.value:
            return desktop
        if want in stubs:
            return stubs[want]
        # Unknown name — prefer local if configured, else cloud
        if self.prefer_local and ollama.available()[0]:
            return ollama
        return anthropic if anthropic.available()[0] else openai

    def readiness(self) -> str:
        if not self.enabled:
            return "Computer use is disabled in settings (computer_use_enabled=false)."
        p = self.resolve_provider()
        ok, why = p.available()
        pw = _playwright_hint()
        # Auto falling through to desktop-only is not a full agent
        if p.id == ProviderId.DESKTOP.value and (self.provider_name or "auto") == "auto":
            state, _, detail = list_ollama_models(self.ollama_host)
            if state != "ready":
                return f"Computer use needs a brain — {detail} · {pw}"
            return (
                f"Computer use needs a model — {ollama_setup_hint()} · {pw} "
                "(or set anthropic/openai key for cloud)"
            )
        if ok:
            note = ""
            if p.id == ProviderId.OLLAMA.value:
                try:
                    vision = bool(getattr(p, "_vision", False))
                    model = str(getattr(p, "_resolved_model", "") or "")
                    if model and not vision:
                        note = (
                            f" · text-only ({model}) — "
                            f"ollama pull {RECOMMENDED_VISION_PULL} for screenshot clicks"
                        )
                    elif model:
                        note = f" · vision ({model})"
                except Exception:
                    note = ""
            return (
                f"Computer use ready · provider {p.id} · max {self.max_steps} steps"
                f"{note} · {pw}"
            )
        return f"Computer use blocked · provider {p.id}: {why} · {pw}"

    def missing_guidance(self) -> str:
        """
        Short actionable 'what's missing' line for voice / upgrade check.
        Still returns a ready blurb when fully ready.
        """
        if not self.enabled:
            return "Enable computer_use_enabled in settings, then say setup computer use."
        want = normalize_provider_name(self.provider_name or "auto")
        p = self.resolve_provider()
        ok, why = p.available()
        pw_missing = "Playwright optional" in _playwright_hint()

        if ok and p.id != ProviderId.DESKTOP.value:
            bits = [f"CU ready ({p.id})"]
            if p.id == ProviderId.OLLAMA.value and not getattr(p, "_vision", False):
                bits.append(f"pull {RECOMMENDED_VISION_PULL} for clicks")
            if pw_missing:
                bits.append("optional: playwright install chromium")
            return " · ".join(bits)

        # Prefer local/free diagnosis when auto or ollama
        if want in ("auto", ProviderId.OLLAMA.value, "local", "free"):
            state, models, detail = list_ollama_models(self.ollama_host)
            if state == "not_installed":
                return (
                    "CU needs Ollama — install from ollama.com/download, "
                    f"then ollama pull {RECOMMENDED_VISION_PULL}, "
                    "say computer use provider local"
                )
            if state == "not_running":
                return (
                    "CU needs Ollama running — start Ollama, "
                    f"then ollama pull {RECOMMENDED_VISION_PULL} if needed"
                )
            if state == "ready" and not models:
                return f"CU needs a model — {ollama_setup_hint()}"
            if state == "ready":
                model, vision = pick_ollama_model(
                    models, preferred=self.ollama_model, want_vision=True
                )
                if model and not vision:
                    return (
                        f"CU has text model {model} — "
                        f"ollama pull {RECOMMENDED_VISION_PULL} for screenshot clicks"
                    )
            return f"CU blocked — {why or detail}"

        return f"CU blocked ({want or p.id}) — {why}"

    def status_line(self) -> str:
        with self._lock:
            s = self.status
            if s.running:
                return (
                    f"Computer use running · {s.provider} · step {s.step}/{s.max_steps} · "
                    f"{s.last_action or '…'}"
                )
            if s.cancelled:
                return f"Computer use cancelled · {s.result or s.last_action}"
            if s.finished:
                return f"Computer use idle · last: {(s.result or 'done')[:140]}"
            try:
                ready = self.readiness()
                if "blocked" in ready.lower() or "needs" in ready.lower():
                    miss = self.missing_guidance()
                    if miss:
                        return miss
                return ready
            except Exception:
                return self.readiness()

    def cancel(self) -> str:
        self._cancel.set()
        with self._lock:
            self.status.cancelled = True
            if self.status.running:
                return "Stopping computer use — hang on a moment."
            return "No computer-use session is running."

    def needs_confirm(self, max_steps: int | None = None) -> bool:
        if not self.confirm_long_runs:
            return False
        steps = int(max_steps if max_steps is not None else self.max_steps)
        return steps >= max(3, int(self.confirm_steps))

    def start(
        self,
        goal: str,
        *,
        provider: str = "",
        max_steps: int | None = None,
        prefer_browser: bool | None = None,
        start_url: str = "about:blank",
    ) -> str:
        goal = (goal or "").strip()
        if not goal:
            return "Give me a goal — for example: computer use find a cafe nearby and draft a site on lovable."
        if not self.enabled:
            return "Computer use is disabled in settings."
        with self._lock:
            if self.status.running:
                return (
                    f"Already running ({self.status.provider} step "
                    f"{self.status.step}/{self.status.max_steps}). "
                    "Say stop computer use first."
                )

        prov = self.resolve_provider(provider)
        ok, why = prov.available()
        if not ok:
            try:
                tip = self.missing_guidance()
                if tip and tip != why:
                    return f"{why} — {tip}"
            except Exception:
                pass
            return why
        # Don't silently "run" the desktop stub when user asked for an agent
        if prov.id == ProviderId.DESKTOP.value and (provider or self.provider_name or "auto") in (
            "",
            "auto",
            "desktop",
        ):
            if (provider or self.provider_name or "auto") != "desktop":
                try:
                    tip = self.missing_guidance()
                    if tip:
                        return tip
                except Exception:
                    pass
                return (
                    "No computer-use provider is ready. "
                    "Free path: start Ollama, then ollama pull llava — "
                    "say computer use provider local. "
                    "Or set anthropic/openai key for cloud. "
                    "Optional: pip install playwright && playwright install chromium."
                )

        steps = int(max_steps if max_steps is not None else self.max_steps)
        steps = max(1, min(steps, 120))
        browserish = prefer_browser
        if browserish is None:
            browserish = bool(
                re.search(
                    r"\b(browser|maps?|google|lovable|website|site|url|web)\b",
                    goal,
                    re.I,
                )
            )
        # Anthropic computer-use expects desktop coordinates
        if prov.id == ProviderId.ANTHROPIC.value:
            browserish = False
        if prov.id in (ProviderId.BROWSER_USE.value, ProviderId.OLLAMA.value):
            browserish = True

        self._cancel.clear()
        with self._lock:
            self.status = AgentStatus(
                running=True,
                provider=prov.id,
                step=0,
                max_steps=steps,
                goal=goal[:200],
            )

        def _job() -> None:
            surface: ActionSurface | None = None
            try:
                surface = open_surface(
                    prefer_browser=bool(browserish),
                    headless=self.headless,
                    start_url=start_url if browserish else "about:blank",
                )
                def on_step(n: int, note: str) -> None:
                    with self._lock:
                        self.status.step = n
                        self.status.last_action = note[:160]
                    if self.on_status:
                        try:
                            self.on_status(self.status)
                        except Exception:
                            pass

                result = prov.run(
                    goal,
                    surface=surface,
                    max_steps=steps,
                    should_stop=lambda: self._cancel.is_set(),
                    on_step=on_step,
                )
                with self._lock:
                    self.status.finished = True
                    self.status.running = False
                    self.status.result = (result or "")[:500]
                    if self._cancel.is_set():
                        self.status.cancelled = True
                if self.on_status:
                    try:
                        self.on_status(self.status)
                    except Exception:
                        pass
            except Exception as e:
                err = f"{e}"
                print(f"[computer-use] agent error: {err}\n{traceback.format_exc()}")
                with self._lock:
                    self.status.running = False
                    self.status.finished = True
                    self.status.last_error = err[:300]
                    self.status.result = f"Failed: {err}"
                if self.on_status:
                    try:
                        self.on_status(self.status)
                    except Exception:
                        pass
            finally:
                if surface is not None:
                    try:
                        surface.close()
                    except Exception:
                        pass

        self._thread = threading.Thread(target=_job, daemon=True, name="computer-use-agent")
        self._thread.start()
        return (
            f"Computer use engaged · {prov.label} · up to {steps} steps. "
            "I'll drive the screen — say stop computer use to abort."
        )


def _playwright_hint() -> str:
    try:
        import playwright  # noqa: F401

        return "Playwright OK"
    except Exception:
        return "Playwright optional (pip install playwright && playwright install chromium)"


def looks_like_computer_use_goal(text: str) -> bool:
    """Heuristic for 'build a site for …' style prompts that should use the agent."""
    t = (text or "").strip().lower()
    if not t:
        return False
    if re.search(
        r"\b(computer\s*use|browser\s*agent|operator\s*:|operator\s+)\b",
        t,
    ):
        return True
    if re.search(r"\bbuild\s+(a\s+)?(site|website)\s+for\b", t):
        return True
    return False
