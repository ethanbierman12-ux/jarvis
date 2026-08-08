"""Windows audio endpoint control — volume + default output switching via pycaw."""

from __future__ import annotations

import subprocess
from ctypes import POINTER, cast
from typing import Any


class AudioRouter:
    """List / switch default playback device and set master volume (pycaw)."""

    def list_outputs(self) -> list[str]:
        try:
            from pycaw.pycaw import AudioUtilities

            names: list[str] = []
            for d in AudioUtilities.GetAllDevices():
                name = getattr(d, "FriendlyName", None) or str(d)
                if name and name not in names:
                    names.append(name)
            return names
        except Exception as e:
            print(f"[audio] list failed: {e}")
            return []

    def status(self) -> str:
        try:
            from pycaw.pycaw import AudioUtilities

            speakers = AudioUtilities.GetSpeakers()
            name = getattr(speakers, "FriendlyName", None) or "Default playback"
            vol = self.get_volume()
            outs = self.list_outputs()
            extra = f" ({len(outs)} endpoints)" if outs else ""
            return f"Output: {name}. Volume {vol}%{extra}."
        except Exception as e:
            return f"Audio router offline: {e}. pip install pycaw comtypes"

    def get_volume(self) -> int:
        try:
            endpoint = self._endpoint_volume()
            if endpoint is None:
                return -1
            level = float(endpoint.GetMasterVolumeLevelScalar())
            return int(round(level * 100))
        except Exception:
            return -1

    def set_volume(self, percent: int) -> str:
        percent = max(0, min(100, int(percent)))
        try:
            endpoint = self._endpoint_volume()
            if endpoint is None:
                return "Could not reach the Windows volume mixer."
            endpoint.SetMasterVolumeLevelScalar(percent / 100.0, None)
            if percent > 0:
                endpoint.SetMute(0, None)
            return f"Master volume set to {percent} percent."
        except Exception as e:
            return f"Volume change failed: {e}"

    def mute(self, muted: bool = True) -> str:
        try:
            endpoint = self._endpoint_volume()
            if endpoint is None:
                return "Could not reach the Windows volume mixer."
            endpoint.SetMute(1 if muted else 0, None)
            return "Muted." if muted else "Unmuted."
        except Exception as e:
            return f"Mute failed: {e}"

    def switch_output(self, name_query: str) -> str:
        """Set default playback device by friendly-name substring."""
        q = (name_query or "").strip().lower()
        if not q:
            return "Say which device — headphones, speakers, or a device name."

        aliases = {
            "headphones": ["headphone", "headset", "earphone", "buds", "airpods", "wg1"],
            "speakers": ["speaker", "desktop", "monitor", "realtek", "hdmi"],
            "emeet": ["emeet", "smartcam"],
            "wg1": ["wg1"],
        }
        needles = [q]
        for canon, alts in aliases.items():
            if q == canon or any(a in q for a in alts):
                needles = [canon, *alts]
                break

        try:
            from pycaw.pycaw import AudioUtilities

            devices = list(AudioUtilities.GetAllDevices())
        except Exception as e:
            return f"Device enumeration failed: {e}"

        match = None
        for d in devices:
            name = (getattr(d, "FriendlyName", None) or str(d)).lower()
            if any(n in name for n in needles if n):
                match = d
                break
        if match is None:
            known = ", ".join(self.list_outputs()[:8]) or "none found"
            return f"No output matching “{name_query}”. Known: {known}."

        friendly = getattr(match, "FriendlyName", None) or str(match)
        dev_id = getattr(match, "id", None) or getattr(match, "Id", None)
        if self._set_default_by_name(friendly, str(dev_id) if dev_id else ""):
            return f"Default audio output set to {friendly}."
        return (
            f"Located {friendly}, but could not switch the Windows default. "
            "Optional: Install-Module AudioDeviceCmdlets — then try again."
        )

    def switch_for_alexa_relay(self) -> tuple[str, str]:
        """
        Park audio on a room speaker/soundbar Echo can hear (not the headset).
        Returns (message, previous_hint) so we can restore WG1 after.
        """
        prefer = (
            "soundbar",
            "sceptre",
            "hdmi",
            "nvidia",
            "high definition audio device",
            "realtek",
            "speaker",
        )
        exclude = ("wg1", "headset", "headphone", "muz6017", "hands-free", "airpods", "buds")
        try:
            from pycaw.pycaw import AudioUtilities

            devices = list(AudioUtilities.GetAllDevices())
        except Exception as e:
            return f"relay switch failed: {e}", ""

        # Remember current default name if possible
        prev = ""
        try:
            speakers = AudioUtilities.GetSpeakers()
            prev = getattr(speakers, "FriendlyName", "") or ""
        except Exception:
            prev = "WG1"

        match = None
        match_score = -1
        for d in devices:
            name = (getattr(d, "FriendlyName", None) or str(d)).lower()
            if any(x in name for x in exclude):
                continue
            # Prefer playback-ish names
            if not any(k in name for k in ("speaker", "headphone", "hdmi", "soundbar", "nvidia", "realtek", "sceptre", "digital")):
                continue
            score = 0
            for i, p in enumerate(prefer):
                if p in name:
                    score = max(score, 100 - i)
            if "soundbar" in name:
                score += 40
            if score > match_score:
                match_score = score
                match = d
        if match is None:
            return "No room speakers found for Alexa relay.", prev
        friendly = getattr(match, "FriendlyName", None) or str(match)
        dev_id = getattr(match, "id", None) or getattr(match, "Id", None)
        ok = self._set_default_by_name(friendly, str(dev_id) if dev_id else "")
        if ok:
            return f"Relay via {friendly}", prev or "WG1"
        return f"Could not switch to {friendly}", prev

    def _endpoint_volume(self) -> Any:
        try:
            from pycaw.pycaw import AudioUtilities

            speakers = AudioUtilities.GetSpeakers()
            # Newer pycaw exposes EndpointVolume directly
            vol = getattr(speakers, "EndpointVolume", None)
            if vol is not None:
                return vol
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import IAudioEndpointVolume

            interface = speakers.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None
            )
            return cast(interface, POINTER(IAudioEndpointVolume))
        except Exception as e:
            print(f"[audio] endpoint volume: {e}")
            return None

    def _set_default_by_name(self, friendly: str, device_id: str) -> bool:
        # 1) AudioDeviceCmdlets (best)
        try:
            if device_id:
                r = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-WindowStyle",
                        "Hidden",
                        "-Command",
                        (
                            "if (Get-Module -ListAvailable -Name AudioDeviceCmdlets) {"
                            f" Set-AudioDevice -ID '{device_id}'; exit 0 "
                            "} else { exit 2 }"
                        ),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=12,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                )
                if r.returncode == 0:
                    return True
            safe = friendly.replace("'", "''")
            r = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    (
                        "if (Get-Module -ListAvailable -Name AudioDeviceCmdlets) {"
                        f" Get-AudioDevice -List | Where-Object Name -like '*{safe}*' "
                        "| Select-Object -First 1 | Set-AudioDevice; exit 0 "
                        "} else { exit 2 }"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=12,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            )
            if r.returncode == 0:
                return True
        except Exception as e:
            print(f"[audio] AudioDeviceCmdlets: {e}")

        # 2) PolicyConfig COM (best-effort)
        if not device_id:
            return False
        try:
            import comtypes.client

            policy = comtypes.client.CreateObject(
                "{870af99c-171d-4f9e-af0d-e63df40c2bc9}"
            )
            for role in (0, 1, 2):
                try:
                    policy.SetDefaultEndpoint(device_id, role)
                except Exception:
                    pass
            return True
        except Exception as e:
            print(f"[audio] PolicyConfig: {e}")
            return False
