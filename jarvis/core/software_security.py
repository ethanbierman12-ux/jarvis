"""Defensive software security — Windows Defender + process harden hooks.

Owner-PC only. Status checks, optional background Defender watch, and
user-initiated quick scans. No offensive tooling.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from typing import Any, Callable, Optional


class SoftwareSecurity:
    """Defensive endpoint checks (Defender status + ProcessHarden)."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        process_harden: Any = None,
        on_alert: Callable[[str], None] | None = None,
        poll_sec: float = 900.0,
    ) -> None:
        self.enabled = bool(enabled)
        self.process_harden = process_harden
        self.on_alert = on_alert
        self.poll_sec = max(120.0, float(poll_sec))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_alert = 0.0

    def start(self) -> None:
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="jarvis-software-security"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        # First check after a short settle; then periodic soft watch
        while not self._stop.wait(12.0 if self._last_alert == 0 else self.poll_sec):
            try:
                self._tick()
            except Exception as e:
                print(f"[software-security] {e}")

    def _tick(self) -> None:
        if not self.enabled or not self.on_alert:
            return
        st = self._query_defender()
        if not st.get("available"):
            return
        problems = []
        if st.get("realtime") is False:
            problems.append("real-time protection is OFF")
        if st.get("antivirus") is False:
            problems.append("antivirus is disabled")
        if not problems:
            return
        now = time.time()
        if now - self._last_alert < 6 * 3600:
            return
        self._last_alert = now
        msg = (
            "Software security warning: "
            + "; ".join(problems)
            + ". Open Windows Security or say defender status."
        )
        try:
            self.on_alert(msg)
        except Exception as e:
            print(f"[software-security] alert: {e}")

    def _query_defender(self) -> dict[str, Any]:
        ps = (
            "$ErrorActionPreference='Stop'; "
            "$s = Get-MpComputerStatus; "
            "@{"
            "Realtime=[bool]$s.RealTimeProtectionEnabled; "
            "AV=[bool]$s.AntivirusEnabled; "
            "AS=[bool]$s.AntispywareEnabled; "
            "SigAge=$s.AntivirusSignatureAge; "
            "LastQuick=($s.QuickScanEndTime | Out-String).Trim()"
            "} | ConvertTo-Json -Compress"
        )
        try:
            from jarvis.core.win_process import check_output_hidden

            out = check_output_hidden(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    ps,
                ],
                text=True,
                timeout=25,
            )
            data = json.loads((out or "").strip() or "{}")
            if not isinstance(data, dict):
                return {"available": False}
            data["available"] = True
            return data
        except Exception as e:
            return {"available": False, "error": str(e)}

    def defender_status(self) -> str:
        """Voice-friendly Windows Defender status string."""
        if not self.enabled:
            return "Software security module disabled in settings."
        st = self._query_defender()
        if not st.get("available"):
            err = st.get("error") or "unavailable"
            return (
                f"Windows Defender status soft-fail ({err}). "
                "Open Windows Security manually if needed."
            )
        bits = []
        if st.get("Realtime") is True:
            bits.append("real-time ON")
        elif st.get("Realtime") is False:
            bits.append("real-time OFF — enable in Windows Security")
        if st.get("AV") is True:
            bits.append("antivirus ON")
        elif st.get("AV") is False:
            bits.append("antivirus OFF")
        if st.get("AS") is False:
            bits.append("antispyware OFF")
        sig = st.get("SigAge")
        try:
            if sig is not None:
                bits.append(f"signatures ~{float(sig):.0f}h old")
        except (TypeError, ValueError):
            pass
        last = str(st.get("LastQuick") or "").strip()
        if last:
            bits.append(f"last quick scan {last[:40]}")
        body = "; ".join(bits) if bits else "Defender reachable"
        warn = ""
        if st.get("Realtime") is False or st.get("AV") is False:
            warn = " Soft warning: protection looks weak."
        return f"Software security: {body}.{warn}"

    def start_quick_scan(self) -> str:
        """User-initiated Defender quick scan (does not wait for completion)."""
        if not self.enabled:
            return "Software security disabled."
        try:
            from jarvis.core.win_process import run_hidden

            run_hidden(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    "Start-MpScan -ScanType QuickScan",
                ],
                timeout=20,
                check=False,
            )
            return (
                "Windows Defender quick scan started in the background. "
                "Check Windows Security for progress."
            )
        except Exception as e:
            try:
                subprocess.Popen(
                    ["cmd", "/c", "start", "ms-settings:windowsdefender"],
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return (
                    f"Could not start scan via API ({e}). "
                    "Opened Windows Security — run a quick scan there."
                )
            except Exception:
                return f"Defender quick scan failed: {e}"

    def harden_processes(self) -> str:
        """Run ProcessHarden speak_scan if available."""
        ph = self.process_harden
        if ph is None:
            return "Process harden offline."
        try:
            if hasattr(ph, "speak_scan"):
                return ph.speak_scan()
            return "Process harden has no speak_scan."
        except Exception as e:
            return f"Process harden soft-fail: {e}"

    def status(self) -> str:
        return (
            f"Software security {'ON' if self.enabled else 'OFF'} · "
            f"poll {self.poll_sec:.0f}s"
        )

    def full_report(self) -> str:
        return f"{self.defender_status()} · {self.harden_processes()}"
