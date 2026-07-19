"""System control — telemetry, lock, shutdown, process kill."""

from __future__ import annotations

import ctypes
import subprocess
from dataclasses import dataclass

import psutil


@dataclass
class Telemetry:
    cpu: float
    memory: float
    battery: float | None
    battery_plugged: bool | None
    disk: float
    temp_c: float | None


class SystemControl:
    def telemetry(self) -> Telemetry:
        cpu = float(psutil.cpu_percent(interval=None))
        mem = float(psutil.virtual_memory().percent)
        bat = psutil.sensors_battery()
        try:
            disk = float(psutil.disk_usage("C:\\").percent)
        except Exception:
            disk = 0.0
        temp = None
        try:
            temps = psutil.sensors_temperatures()
            vals = [e.current for entries in temps.values() for e in entries if e.current]
            temp = max(vals) if vals else None
        except Exception:
            pass
        return Telemetry(
            cpu=cpu,
            memory=mem,
            battery=float(bat.percent) if bat else None,
            battery_plugged=bool(bat.power_plugged) if bat else None,
            disk=disk,
            temp_c=temp,
        )

    def disk_capacity(self) -> tuple[float, float]:
        """Return (total_gb, free_gb) for C:."""
        try:
            du = psutil.disk_usage("C:\\")
            return du.total / (1024**3), du.free / (1024**3)
        except Exception:
            return 0.0, 0.0

    def lock(self) -> str:
        ctypes.windll.user32.LockWorkStation()
        return "Workstation locked."

    def shutdown(self, confirm: bool = False) -> str:
        if not confirm:
            return "Say 'confirm shutdown' to power off."
        subprocess.Popen(["shutdown", "/s", "/t", "5"], shell=False)
        return "Shutting down in 5 seconds."

    def sleep(self) -> str:
        """Suspend to RAM — best state for clap → Wake-on-LAN."""
        # Avoid hybrid sleep / unexpected hibernate for WOL reliability
        subprocess.Popen(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0", "1", "0"],
            shell=False,
        )
        return "Standing by. Double-clap on your wake device to power me back on."

    def wol_status(self) -> str:
        from jarvis.core.wol import list_nics, primary_mac

        mac = primary_mac()
        nics = list_nics()
        if not mac:
            return "No network adapter MAC found. Plug in Ethernet or Wi-Fi and run setup_wol.bat."
        lines = [f"Primary MAC {mac}."]
        for n in nics[:4]:
            ip = n.ipv4 or "no-ip"
            lines.append(f"{n.name}: {n.mac} ({ip})")
        lines.append(
            "Say 'standby for clap' after setup_wol.bat — clap agent wakes over Wi-Fi and/or Bluetooth."
        )
        return " ".join(lines)

    def kill_named(self, names: list[str]) -> str:
        killed = []
        lowered = [n.lower() for n in names]
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info["name"] or "").lower()
                if any(n in name for n in lowered):
                    proc.kill()
                    killed.append(proc.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if not killed:
            return "No matching processes found."
        return "Closed: " + ", ".join(sorted(set(killed))[:8])
