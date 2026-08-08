"""Keyboard / mouse RGB via OpenRGB (universal peripheral lighting).

Voice examples:
  set keyboard to cyan · mouse red · rgb jarvis · rgb off · rgb status

Requires OpenRGB running once so devices are detected:
  winget install OpenRGB.OpenRGB
Then open OpenRGB → enable SDK Server (or Jarvis starts CLI color sets).
"""

from __future__ import annotations

import os
import shutil
import socket
import struct
import subprocess
import threading
from pathlib import Path
from typing import Any


# OpenRGB controllers we never paint for desk / Jarvis ambient sync
_SKIP_NAME = (
    "dualsense",
    "dualshock",
    "playstation",
    "xbox",
    "gamepad",
    "controller",
    "joy-con",
    "switch pro",
)
_SKIP_TYPE = ("gamepad", "controller", "unknown")
_PREF_TYPE = (
    "keyboard",
    "mouse",
    "mousemat",
    "led strip",
    "ledstrip",
    "motherboard",
    "dram",
    "gpu",
    "cooler",
    "headset",
    "headphones",
)


COLOR_NAMES: dict[str, tuple[int, int, int]] = {
    "jarvis": (0, 240, 255),
    "cyan": (0, 240, 255),
    "arwes": (0, 240, 255),
    "magenta": (255, 43, 214),
    "pink": (255, 43, 214),
    "red": (255, 40, 40),
    "green": (40, 255, 120),
    "blue": (40, 120, 255),
    "purple": (160, 60, 255),
    "orange": (255, 140, 40),
    "gold": (255, 196, 72),
    "amber": (255, 158, 42),
    "white": (255, 255, 255),
    "warm": (255, 180, 100),
    "cool": (180, 220, 255),
    "off": (0, 0, 0),
    "black": (0, 0, 0),
}


def parse_color(text: str) -> tuple[int, int, int] | None:
    t = (text or "").strip().lower()
    if not t:
        return None
    if t in COLOR_NAMES:
        return COLOR_NAMES[t]
    # #RRGGBB or RRGGBB
    hexpart = t.lstrip("#")
    if len(hexpart) == 6 and all(c in "0123456789abcdef" for c in hexpart):
        return (
            int(hexpart[0:2], 16),
            int(hexpart[2:4], 16),
            int(hexpart[4:6], 16),
        )
    # rgb r g b / r,g,b
    import re

    m = re.search(r"(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})", t)
    if m:
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        if max(r, g, b) <= 255:
            return (r, g, b)
    return None


def _find_openrgb() -> str | None:
    env = (os.environ.get("OPENRGB_PATH") or "").strip()
    if env and Path(env).is_file():
        return env
    which = shutil.which("OpenRGB") or shutil.which("openrgb")
    if which:
        return which
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "OpenRGB" / "OpenRGB.exe",
        Path(os.environ.get("ProgramFiles", "")) / "OpenRGB" / "OpenRGB.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "OpenRGB" / "OpenRGB.exe",
        Path.home() / "AppData" / "Local" / "OpenRGB" / "OpenRGB.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


class RgbPeripherals:
    """Drive keyboard + mouse RGB through OpenRGB CLI / SDK."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        host: str = "127.0.0.1",
        port: int = 6742,
        openrgb_path: str = "",
    ) -> None:
        self.enabled = bool(enabled)
        self.host = (host or "127.0.0.1").strip()
        self.port = int(port or 6742)
        self.openrgb_path = (openrgb_path or "").strip() or _find_openrgb()
        self.last_color: tuple[int, int, int] = (0, 240, 255)
        self.last_target: str = "all"
        self._lock = threading.Lock()

    def status(self) -> str:
        exe = self.openrgb_path or _find_openrgb()
        self.openrgb_path = exe
        if not self.enabled:
            return "Peripheral RGB is disabled in settings."
        if not exe:
            return (
                "OpenRGB not installed. In PowerShell run: "
                "winget install OpenRGB.OpenRGB — then say rgb status again."
            )
        sdk = self._sdk_ping()
        return (
            f"OpenRGB at {exe}. SDK {'online' if sdk else 'offline (CLI mode OK)'}. "
            f"Last color RGB{self.last_color} on {self.last_target}."
        )

    def set_color(
        self,
        color: str | tuple[int, int, int],
        *,
        target: str = "all",
    ) -> str:
        if not self.enabled:
            return "Peripheral RGB disabled — enable openrgb_enabled in settings."
        rgb = parse_color(color) if isinstance(color, str) else color
        if rgb is None:
            names = ", ".join(sorted(k for k in COLOR_NAMES if k not in ("black",)))
            return f"Unknown color. Try: {names}, or #00F0FF."
        target = (target or "all").lower().strip()
        if target in ("kb", "keys", "keyboards"):
            target = "keyboard"
        if target in ("mice", "mice"):
            target = "mouse"
        if target not in ("all", "keyboard", "mouse"):
            target = "all"

        with self._lock:
            self.last_color = rgb
            self.last_target = target
            # Prefer CLI — reliable on Windows without keeping SDK open
            ok, detail = self._set_via_cli(rgb, target=target)
            if ok:
                return detail
            ok2, detail2 = self._set_via_sdk(rgb, target=target)
            if ok2:
                return detail2
            if not (self.openrgb_path or _find_openrgb()):
                return (
                    "OpenRGB is required to paint your keyboard and mouse. "
                    "Run: winget install OpenRGB.OpenRGB — open it once, "
                    "then say set keyboard to cyan."
                )
            return f"Could not set RGB ({detail}; {detail2}). Open OpenRGB once so devices load."

    def set_keyboard(self, color: str | tuple[int, int, int]) -> str:
        return self.set_color(color, target="keyboard")

    def set_mouse(self, color: str | tuple[int, int, int]) -> str:
        return self.set_color(color, target="mouse")

    def off(self, target: str = "all") -> str:
        return self.set_color("off", target=target)

    def sync_jarvis(self) -> str:
        return self.set_color("jarvis", target="all")

    # ── OpenRGB CLI ─────────────────────────────────────────────
    def _set_via_cli(
        self, rgb: tuple[int, int, int], *, target: str
    ) -> tuple[bool, str]:
        exe = self.openrgb_path or _find_openrgb()
        self.openrgb_path = exe
        if not exe:
            return False, "no OpenRGB.exe"
        hexcol = f"{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
        try:
            devices = self._list_devices_cli(exe)
        except Exception as e:
            devices = []
            print(f"[rgb] list: {e}")

        idxs = self._match_device_indexes(devices, target)
        if not idxs and target in ("keyboard", "mouse"):
            # Never fall back to gamepads / DualSense — that causes mode errors
            return False, f"no {target} device in OpenRGB (TeckNet USB keyboards are usually Fn-only)"

        cmds: list[list[str]] = []
        if idxs:
            for i in idxs:
                mode = self._mode_for_device(devices, i)
                cmd = [exe, "--noautoconnect", "--device", str(i)]
                if mode:
                    cmd.extend(["--mode", mode])
                cmd.extend(["--color", hexcol])
                cmds.append(cmd)
        else:
            # No paintable desk devices (e.g. DualSense-only) — don't blast all controllers
            return False, "no keyboard/mouse/LED devices in OpenRGB"

        errors: list[str] = []
        for cmd in cmds:
            try:
                r = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=12,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if r.returncode != 0:
                    err = (r.stderr or r.stdout or "").strip()[:160]
                    errors.append(err or f"exit {r.returncode}")
            except Exception as e:
                errors.append(str(e))
        if errors and len(errors) == len(cmds):
            return False, "; ".join(errors)[:200]
        label = target if target != "all" else "desk peripherals"
        return True, f"RGB {label} -> #{hexcol} (OpenRGB)."

    def _mode_for_device(self, devices: list[dict[str, Any]], index: int) -> str | None:
        """Pick a color-capable mode; DualSense has Direct modes, not static."""
        for d in devices:
            if int(d.get("index", -1)) != index:
                continue
            modes = [m.strip() for m in (d.get("modes") or []) if str(m).strip()]
            lower = [m.lower() for m in modes]
            for want in ("static", "direct", "mic off (direct)"):
                for i, m in enumerate(lower):
                    if m == want or want in m:
                        return modes[i]
            # Prefer any mode containing Direct / Static
            for i, m in enumerate(lower):
                if "static" in m or "direct" in m:
                    return modes[i]
            return modes[0] if modes else "static"
        return "static"

    def _list_devices_cli(self, exe: str) -> list[dict[str, Any]]:
        r = subprocess.run(
            [exe, "--noautoconnect", "--list-devices"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        devices: list[dict[str, Any]] = []
        cur: dict[str, Any] | None = None
        import re

        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^\[?(\d+)\]?\s*[:.-]\s*(.+)$", line)
            if m:
                cur = {
                    "index": int(m.group(1)),
                    "name": m.group(2).strip(),
                    "type": "",
                    "modes": [],
                }
                devices.append(cur)
                continue
            if not cur:
                continue
            low = line.lower()
            if low.startswith("type"):
                cur["type"] = line.split(":", 1)[-1].strip().lower()
            elif low.startswith("modes"):
                # Modes: [Direct] 'Mic Off (Direct)' 'Mic Pulse (Direct)'
                body = line.split(":", 1)[-1]
                quoted = re.findall(r"'([^']+)'|\"([^\"]+)\"", body)
                modes = [a or b for a, b in quoted]
                if not modes:
                    # bracket tokens without quotes
                    modes = [
                        t.strip("[]'\" ")
                        for t in re.split(r"[,\s]+", body)
                        if t.strip("[]'\" ") and t.strip("[]'\" ").lower() not in ("modes",)
                    ]
                cur["modes"] = modes
        for d in devices:
            name = (d.get("name") or "").lower()
            typ = (d.get("type") or "").lower()
            if not typ:
                if any(k in name for k in ("keyboard", "keypad", "board")):
                    d["type"] = "keyboard"
                elif any(k in name for k in ("mouse", "mice", "glove")):
                    d["type"] = "mouse"
                elif any(k in name for k in _SKIP_NAME):
                    d["type"] = "gamepad"
                else:
                    d["type"] = "other"
            elif any(k in name for k in _SKIP_NAME):
                d["type"] = "gamepad"
        return devices

    def _is_skipped(self, d: dict[str, Any]) -> bool:
        name = (d.get("name") or "").lower()
        typ = (d.get("type") or "").lower()
        if any(k in name for k in _SKIP_NAME):
            return True
        if any(k in typ for k in _SKIP_TYPE):
            return True
        return False

    def _match_device_indexes(
        self, devices: list[dict[str, Any]], target: str
    ) -> list[int]:
        if not devices:
            return []
        usable = [d for d in devices if not self._is_skipped(d)]
        if target == "all":
            preferred = [
                d
                for d in usable
                if any(p in (d.get("type") or "").lower() for p in _PREF_TYPE)
                or any(
                    p in (d.get("name") or "").lower()
                    for p in (
                        "keyboard",
                        "mouse",
                        "led",
                        "strip",
                        "razer",
                        "corsair",
                        "logitech",
                        "tecknet",
                        "teckmet",
                    )
                )
            ]
            pool = preferred or usable
            return [int(d["index"]) for d in pool]
        out = []
        for d in usable:
            typ = (d.get("type") or "").lower()
            name = (d.get("name") or "").lower()
            if target == "keyboard" and (
                "keyboard" in typ or "keyboard" in name or "keypad" in name
            ):
                out.append(int(d["index"]))
            elif target == "mouse" and ("mouse" in typ or "mouse" in name):
                out.append(int(d["index"]))
        return out

    # ── Minimal OpenRGB SDK (set client color on all / filtered) ─
    def _sdk_ping(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=0.4):
                return True
        except Exception:
            return False

    def _set_via_sdk(
        self, rgb: tuple[int, int, int], *, target: str
    ) -> tuple[bool, str]:
        """Best-effort: use openrgb-python if installed."""
        try:
            from openrgb import OpenRGBClient
            from openrgb.utils import RGBColor, DeviceType
        except Exception:
            return False, "SDK python client not installed"

        try:
            client = OpenRGBClient(self.host, self.port, "Jarvis")
            color = RGBColor(rgb[0], rgb[1], rgb[2])
            skip_types = set()
            try:
                skip_types.add(DeviceType.GAMEPAD)
            except Exception:
                pass
            if target == "keyboard":
                for d in client.get_devices_by_type(DeviceType.KEYBOARD):
                    d.set_color(color)
            elif target == "mouse":
                for d in client.get_devices_by_type(DeviceType.MOUSE):
                    d.set_color(color)
            else:
                painted = 0
                for d in client.devices:
                    name = (getattr(d, "name", "") or "").lower()
                    typ = getattr(d, "type", None)
                    if any(k in name for k in _SKIP_NAME):
                        continue
                    if typ in skip_types:
                        continue
                    try:
                        d.set_color(color)
                        painted += 1
                    except Exception:
                        continue
                if painted == 0:
                    return False, "no keyboard/mouse/LED devices in OpenRGB SDK"
            return True, f"RGB {target} -> {rgb} via OpenRGB SDK."
        except Exception as e:
            return False, str(e)[:160]
