"""PC healer — find resource hogs and propose safe termination."""

from __future__ import annotations

import time
from dataclasses import dataclass

import psutil


@dataclass
class Hog:
    pid: int
    name: str
    cpu: float
    memory: float


# Never auto-kill these
_PROTECTED = {
    "system",
    "system idle process",
    "csrss.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "explorer.exe",
    "dwm.exe",
    "python.exe",
    "pythonw.exe",
    "jarvis",
    "cursor.exe",
    "code.exe",
}


class PcHealer:
    def __init__(self, *, cpu_threshold: float = 85.0, mem_threshold: float = 90.0) -> None:
        self.cpu_threshold = float(cpu_threshold)
        self.mem_threshold = float(mem_threshold)
        self._pending: Hog | None = None
        self._last_ask = 0.0

    def top_hogs(self, n: int = 5) -> list[Hog]:
        # Prime cpu_percent
        for p in psutil.process_iter(["pid", "name"]):
            try:
                p.cpu_percent(interval=None)
            except Exception:
                pass
        time.sleep(0.35)
        rows: list[Hog] = []
        for p in psutil.process_iter(["pid", "name", "memory_percent"]):
            try:
                info = p.info
                name = (info.get("name") or "unknown").strip()
                cpu = float(p.cpu_percent(interval=None) or 0)
                mem = float(info.get("memory_percent") or 0)
                if cpu < 1 and mem < 1:
                    continue
                rows.append(Hog(pid=int(info["pid"]), name=name, cpu=cpu, memory=mem))
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                continue
        rows.sort(key=lambda h: (h.cpu, h.memory), reverse=True)
        return rows[: max(1, n)]

    def status(self) -> str:
        hogs = self.top_hogs(5)
        if not hogs:
            return "Healer: no significant process load."
        bits = [f"{h.name} pid {h.pid} · CPU {h.cpu:.0f}% · RAM {h.memory:.0f}%" for h in hogs]
        return "Top processes: " + "; ".join(bits)

    def should_intervene(self, *, system_cpu: float, system_mem: float) -> Hog | None:
        if system_cpu < self.cpu_threshold and system_mem < self.mem_threshold:
            return None
        if time.time() - self._last_ask < 600:
            return None
        hogs = self.top_hogs(3)
        for h in hogs:
            if h.name.lower() in _PROTECTED or any(
                p in h.name.lower() for p in _PROTECTED
            ):
                continue
            if h.cpu >= 40 or (system_mem >= self.mem_threshold and h.memory >= 10):
                self._pending = h
                self._last_ask = time.time()
                return h
        return None

    def pending(self) -> Hog | None:
        return self._pending

    def clear_pending(self) -> None:
        self._pending = None

    def kill_hog(self, hog: Hog | None = None) -> str:
        target = hog or self._pending
        self._pending = None
        if not target:
            return "No process queued to terminate."
        low = target.name.lower()
        if low in _PROTECTED or any(p in low for p in ("python", "jarvis", "cursor")):
            return f"Refusing to kill protected process {target.name}."
        try:
            p = psutil.Process(target.pid)
            if (p.name() or "").lower() != low and target.name.lower() not in (
                p.name() or ""
            ).lower():
                # PID reused — fall back to name kill of that one pid only
                pass
            p.terminate()
            try:
                p.wait(timeout=3)
            except psutil.TimeoutExpired:
                p.kill()
            return f"Terminated {target.name} (pid {target.pid})."
        except psutil.NoSuchProcess:
            return f"{target.name} already exited."
        except psutil.AccessDenied:
            return f"Access denied killing {target.name} — try as admin."
        except Exception as e:
            return f"Could not kill {target.name}: {e}"

    def kill_top(self) -> str:
        hogs = self.top_hogs(1)
        if not hogs:
            return "No hog found."
        return self.kill_hog(hogs[0])
