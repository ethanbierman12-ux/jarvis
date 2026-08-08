"""LAN cyber watch — announce unknown MAC / new Wi‑Fi joiners (Windows arp).

Also: owner-LAN device list + optional IP-camera port presence check
(ports 80 / 554 / 8554 only — report open hosts, never exploit).
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from jarvis.config import DATA_DIR

STATE_PATH = DATA_DIR / "net_watch.json"

# Common IP camera / NVR listen ports — presence only, no auth/exploit
_CAM_PORTS = (80, 554, 8554)


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

    def list_devices(self, *, limit: int = 24) -> list[NetDevice]:
        """Merge live ARP with known table; prefer freshest IP per MAC."""
        live = {d.mac: d for d in self.scan_once()}
        now = time.time()
        for mac, d in live.items():
            prev = self._known.get(mac)
            if prev is None:
                d.first_seen = now
                d.last_seen = now
                self._known[mac] = d
            else:
                prev.ip = d.ip or prev.ip
                prev.last_seen = now
        # Prefer currently visible, then known
        ordered: list[NetDevice] = []
        seen: set[str] = set()
        for d in live.values():
            known = self._known.get(d.mac, d)
            ordered.append(known)
            seen.add(d.mac)
        for mac, d in sorted(
            self._known.items(),
            key=lambda kv: kv[1].last_seen,
            reverse=True,
        ):
            if mac in seen:
                continue
            ordered.append(d)
            seen.add(mac)
            if len(ordered) >= limit:
                break
        return ordered[:limit]

    def speak_lan_status(self) -> str:
        """Voice-friendly LAN / security status (owner network only)."""
        try:
            devices = self.list_devices(limit=20)
        except Exception as e:
            return f"LAN status soft-fail: {e}"
        untrusted = [d for d in devices if not d.trusted]
        bits = [
            self.status(),
            f"{len(devices)} devices listed",
            f"{len(untrusted)} untrusted",
        ]
        if devices:
            sample = ", ".join(
                f"{d.ip or '?'} ({d.mac[-8:]})" for d in devices[:6]
            )
            bits.append(f"sample: {sample}")
        bits.append("Owner LAN only — say scan local network for camera-port presence.")
        return " · ".join(bits)

    @staticmethod
    def _local_ipv4() -> str:
        """Best-effort primary IPv4 on the owner's machine."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            finally:
                s.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        try:
            host = socket.gethostname()
            for info in socket.getaddrinfo(host, None, socket.AF_INET):
                ip = info[4][0]
                if ip and not ip.startswith("127."):
                    return ip
        except Exception:
            pass
        return ""

    @staticmethod
    def _is_private_lan(ip: str) -> bool:
        try:
            parts = [int(x) for x in ip.split(".")]
            if len(parts) != 4:
                return False
            a, b = parts[0], parts[1]
            if a == 10:
                return True
            if a == 192 and b == 168:
                return True
            if a == 172 and 16 <= b <= 31:
                return True
            return False
        except Exception:
            return False

    def _candidate_hosts(self, *, max_hosts: int = 48) -> list[str]:
        """ARP-known hosts + small /24 sweep around this PC (private LAN only)."""
        local = self._local_ipv4()
        if not local or not self._is_private_lan(local):
            # Still allow ARP-known private IPs if local detect fails
            hosts = []
            for d in self.scan_once():
                if self._is_private_lan(d.ip):
                    hosts.append(d.ip)
            return hosts[:max_hosts]

        prefix = ".".join(local.split(".")[:3])
        known = {d.ip for d in self.scan_once() if d.ip.startswith(prefix + ".")}
        known.add(local)
        # Limited sweep — owner /24 only, capped
        sweep = [f"{prefix}.{i}" for i in range(1, 255)]
        # Prioritize ARP-known, then nearby addresses
        ordered: list[str] = []
        for ip in sorted(known):
            if ip not in ordered:
                ordered.append(ip)
        try:
            base = int(local.split(".")[-1])
        except Exception:
            base = 1
        near = sorted(range(1, 255), key=lambda i: abs(i - base))
        for i in near:
            ip = f"{prefix}.{i}"
            if ip not in ordered:
                ordered.append(ip)
            if len(ordered) >= max_hosts:
                break
        return ordered[:max_hosts]

    @staticmethod
    def _port_open(ip: str, port: int, timeout: float) -> bool:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except Exception:
            return False

    def scan_camera_ports(
        self,
        *,
        timeout: float = 0.30,
        max_hosts: int = 40,
    ) -> list[dict]:
        """Owner-LAN only: hosts with common IP-cam ports open (report only)."""
        hosts = self._candidate_hosts(max_hosts=max_hosts)
        if not hosts:
            return []
        found: list[dict] = []
        lock = threading.Lock()

        def _probe(ip: str) -> None:
            open_ports = [
                p for p in _CAM_PORTS if self._port_open(ip, p, timeout)
            ]
            if not open_ports:
                return
            with lock:
                found.append({"ip": ip, "ports": open_ports})

        try:
            with ThreadPoolExecutor(max_workers=24) as pool:
                futs = [pool.submit(_probe, ip) for ip in hosts]
                for f in as_completed(futs):
                    try:
                        f.result()
                    except Exception:
                        pass
        except Exception as e:
            print(f"[net-watch] cam-port scan: {e}")
        found.sort(key=lambda r: r["ip"])
        return found

    def speak_local_network_scan(self) -> str:
        """Voice: ARP devices + optional camera-port presence on owner LAN."""
        try:
            devices = self.list_devices(limit=16)
        except Exception:
            devices = []
        try:
            cams = self.scan_camera_ports()
        except Exception as e:
            return (
                f"{self.status()}. Device list ok, camera-port scan soft-fail: {e}. "
                "Owner LAN only — no exploit."
            )
        bits = [
            self.status(),
            f"{len(devices)} ARP/known devices",
        ]
        if cams:
            cam_bits = ", ".join(
                f"{c['ip']} ports {','.join(str(p) for p in c['ports'])}"
                for c in cams[:8]
            )
            bits.append(f"possible IP-cam listeners: {cam_bits}")
        else:
            bits.append("no common IP-cam ports (80/554/8554) open on probed LAN hosts")
        bits.append(
            "Owner local network only — presence report, not an attack. "
            "Say trust network to whitelist current MACs."
        )
        return " · ".join(bits)

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
