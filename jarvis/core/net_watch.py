"""LAN cyber watch — announce unknown MAC / new Wi‑Fi joiners (Windows arp)."""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from jarvis.config import DATA_DIR

STATE_PATH = DATA_DIR / "net_watch.json"


@dataclass
class NetDevice:
    ip: str
    mac: str
    vendor: str = ""
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    last_alert: float = 0.0
    trusted: bool = False


class NetWatch:
    """Poll ARP table; alert on new / untrusted MACs."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        poll_sec: float = 45.0,
        on_alert: Callable[[str, NetDevice], None] | None = None,
    ) -> None:
        self.enabled = enabled
        self.poll_sec = max(15.0, float(poll_sec))
        self.on_alert = on_alert
        self._known: dict[str, NetDevice] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._load()

    def _load(self) -> None:
        try:
            if STATE_PATH.exists():
                raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                for mac, d in (raw.get("devices") or {}).items():
                    self._known[mac.lower()] = NetDevice(
                        ip=str(d.get("ip") or ""),
                        mac=mac.lower(),
                        vendor=str(d.get("vendor") or ""),
                        first_seen=float(d.get("first_seen") or time.time()),
                        last_seen=float(d.get("last_seen") or time.time()),
                        last_alert=float(d.get("last_alert") or 0),
                        trusted=bool(d.get("trusted")),
                    )
        except Exception:
            pass

    def save(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "devices": {
                    m: asdict(d) for m, d in self._known.items()
                }
            }
            STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def start(self) -> None:
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="jarvis-net-watch"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> str:
        n = len(self._known)
        trust = sum(1 for d in self._known.values() if d.trusted)
        return (
            f"Net watch {'ON' if self.enabled else 'OFF'} · "
            f"{n} MACs ({trust} trusted) · poll {self.poll_sec:.0f}s"
        )

    def trust_all_current(self) -> str:
        snap = self.scan_once()
        for d in snap:
            d.trusted = True
            self._known[d.mac] = d
        self.save()
        return f"Trusted {len(snap)} devices currently on the LAN."

    def scan_once(self) -> list[NetDevice]:
        devices: list[NetDevice] = []
        try:
            from jarvis.core.win_process import check_output_hidden

            out = check_output_hidden(
                ["arp", "-a"],
                text=True,
                timeout=8,
            )
        except Exception:
            return devices
        # 192.168.1.1           00-11-22-33-44-55     dynamic
        for line in out.splitlines():
            m = re.search(
                r"(\d+\.\d+\.\d+\.\d+)\s+([-0-9a-fA-F:]{11,17})\s+(\w+)",
                line,
            )
            if not m:
                continue
            ip, mac_raw, _kind = m.group(1), m.group(2), m.group(3)
            mac = mac_raw.replace("-", ":").lower()
            if mac in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"):
                continue
            if re.match(r"^224\.|^239\.", ip):
                continue
            devices.append(NetDevice(ip=ip, mac=mac))
        return devices

    def _loop(self) -> None:
        # First pass: learn without alerting
        first = True
        while not self._stop.wait(self.poll_sec if not first else 2.0):
            try:
                self._tick(alert=not first)
            except Exception as e:
                print(f"[net-watch] {e}")
            first = False

    def _tick(self, *, alert: bool) -> None:
        now = time.time()
        dirty = False
        for d in self.scan_once():
            prev = self._known.get(d.mac)
            if prev is None:
                d.first_seen = now
                d.last_seen = now
                d.last_alert = now if alert else 0.0
                self._known[d.mac] = d
                dirty = True
                if alert and self.on_alert:
                    self.on_alert(
                        f"Unknown device on Wi-Fi: {d.ip} · MAC {d.mac}",
                        d,
                    )
            else:
                if prev.ip != d.ip:
                    prev.ip = d.ip
                    dirty = True
                prev.last_seen = now
                if alert and not prev.trusted and self.on_alert:
                    last_alert = float(getattr(prev, "last_alert", 0) or 0)
                    if now - last_alert >= 6 * 3600:
                        prev.last_alert = now
                        dirty = True
                        self.on_alert(
                            f"Untrusted device still on Wi-Fi: {prev.ip} · MAC {prev.mac}",
                            prev,
                        )
        if dirty:
            self.save()
