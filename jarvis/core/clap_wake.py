"""Clap-wake transports — Wi-Fi (Wake-on-LAN) and Bluetooth probe."""

from __future__ import annotations

import json
import re
import socket
import subprocess
from typing import Any

from jarvis.core.wol import is_valid_mac, normalize_mac, send_magic_packet


def parse_transports(raw: Any) -> list[str]:
    """Normalize transport config to ['wifi'] and/or ['bluetooth']."""
    if raw is None:
        return ["wifi", "bluetooth"]
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = ["wifi", "bluetooth"]
    out: list[str] = []
    for item in items:
        t = str(item).strip().lower()
        if t in ("wifi", "wi-fi", "wlan", "wol", "lan"):
            if "wifi" not in out:
                out.append("wifi")
        elif t in ("bluetooth", "bt", "ble"):
            if "bluetooth" not in out:
                out.append("bluetooth")
        elif t in ("both", "all"):
            return ["wifi", "bluetooth"]
    return out or ["wifi", "bluetooth"]


def send_wifi_wake(
    mac: str,
    broadcast: str = "255.255.255.255",
    port: int = 9,
) -> str:
    """Wake over Wi-Fi / LAN via magic packet (also hits Ethernet if present)."""
    msgs = [send_magic_packet(mac, broadcast=broadcast, port=port)]
    # Extra global broadcast helps when subnet broadcast is filtered
    if broadcast not in ("255.255.255.255", ""):
        try:
            msgs.append(send_magic_packet(mac, broadcast="255.255.255.255", port=port))
        except Exception:
            pass
    return msgs[0]


def send_bluetooth_wake(bt_mac: str, channel: int = 1) -> str:
    """
    Probe the PC's Bluetooth radio (RFCOMM). On machines with Wake-on-Bluetooth
    enabled, the page/connect traffic can bring the system out of sleep.
    """
    mac = normalize_mac(bt_mac)
    if not hasattr(socket, "AF_BTH"):
        return (
            "Bluetooth wake skipped — this OS/Python build has no AF_BTH "
            "(use a Windows clap device, or rely on Wi-Fi)."
        )
    try:
        sock = socket.socket(socket.AF_BTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        sock.settimeout(2.5)
        try:
            sock.connect((mac, int(channel)))
            try:
                sock.send(b"JARVIS_CLAP_WAKE\n")
            except Exception:
                pass
            return f"Bluetooth wake connected to {mac} (channel {channel})."
        finally:
            try:
                sock.close()
            except Exception:
                pass
    except OSError as e:
        # Timeout / refused still often generates wake-capable radio activity
        return f"Bluetooth wake probed {mac} ({e})."
    except Exception as e:
        return f"Bluetooth wake failed: {e}"


def send_clap_wake(cfg: dict[str, Any]) -> list[str]:
    """Fire configured transports; returns human-readable status lines."""
    transports = parse_transports(cfg.get("transports") or cfg.get("transport"))
    lines: list[str] = []

    if "wifi" in transports:
        mac = (cfg.get("target_mac") or cfg.get("wifi_mac") or "").strip()
        if not mac:
            lines.append("Wi-Fi wake skipped — no target_mac / wifi_mac.")
        else:
            try:
                lines.append(
                    send_wifi_wake(
                        mac,
                        broadcast=str(cfg.get("broadcast") or "255.255.255.255"),
                        port=int(cfg.get("port") or 9),
                    )
                )
            except Exception as e:
                lines.append(f"Wi-Fi wake failed: {e}")

    if "bluetooth" in transports:
        bt = (cfg.get("bluetooth_mac") or cfg.get("bt_mac") or "").strip()
        if not bt:
            lines.append(
                "Bluetooth wake skipped — set bluetooth_mac in config/clap_wol.json "
                "(run setup_wol.bat on the PC)."
            )
        else:
            try:
                lines.append(
                    send_bluetooth_wake(bt, channel=int(cfg.get("bluetooth_channel") or 1))
                )
            except Exception as e:
                lines.append(f"Bluetooth wake failed: {e}")

    return lines or ["No wake transports configured."]


def list_bluetooth_adapters() -> list[dict[str, str]]:
    """Best-effort Bluetooth adapter MACs on Windows."""
    found: list[dict[str, str]] = []
    try:
        ps = (
            "Get-NetAdapter | Where-Object { $_.Name -match 'Bluetooth' -and $_.MacAddress } | "
            "ForEach-Object { [PSCustomObject]@{ Name=$_.Name; Mac=$_.MacAddress; Status=$_.Status } } | "
            "ConvertTo-Json -Compress"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", ps],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            stdin=subprocess.DEVNULL,
        ).strip()
        if not out:
            return found
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        for row in data:
            mac = str(row.get("Mac") or "").replace("-", ":")
            if is_valid_mac(mac):
                found.append(
                    {
                        "name": str(row.get("Name") or "Bluetooth"),
                        "mac": normalize_mac(mac),
                        "status": str(row.get("Status") or ""),
                    }
                )
    except Exception:
        pass
    return found


def primary_bluetooth_mac() -> str | None:
    adapters = list_bluetooth_adapters()
    return adapters[0]["mac"] if adapters else None


def find_mic_device(prefer: str = "auto", name_substr: str = "") -> int | None:
    """
    Pick a sounddevice input index.
    prefer: auto | bluetooth | wifi | default
    (wifi = non-bluetooth default / USB / onboard — anything not BT)
    """
    try:
        import sounddevice as sd
    except ImportError:
        return None

    prefer = (prefer or "auto").strip().lower()
    needle = (name_substr or "").strip().lower()
    devices = sd.query_devices()
    inputs: list[tuple[int, str]] = []
    for i, d in enumerate(devices):
        if int(d.get("max_input_channels") or 0) <= 0:
            continue
        inputs.append((i, str(d.get("name") or "")))

    def is_bt(name: str) -> bool:
        n = name.lower()
        return any(k in n for k in ("bluetooth", "headset", "hands-free", "airpods", "buds"))

    if needle:
        for i, name in inputs:
            if needle in name.lower():
                return i

    if prefer in ("bluetooth", "bt"):
        for i, name in inputs:
            if is_bt(name):
                return i
        return None

    if prefer in ("wifi", "wired", "usb", "default"):
        for i, name in inputs:
            if not is_bt(name):
                return i
        return sd.default.device[0] if sd.default.device else None

    # auto: prefer bluetooth mic if present, else system default
    for i, name in inputs:
        if is_bt(name):
            return i
    try:
        return int(sd.default.device[0])  # type: ignore[index]
    except Exception:
        return inputs[0][0] if inputs else None


def list_input_mics() -> list[str]:
    try:
        import sounddevice as sd
    except ImportError:
        return []
    lines: list[str] = []
    for i, d in enumerate(sd.query_devices()):
        if int(d.get("max_input_channels") or 0) <= 0:
            continue
        name = str(d.get("name") or f"#{i}")
        tag = " [bluetooth]" if re.search(r"bluetooth|headset|hands-free", name, re.I) else ""
        lines.append(f"  [{i}] {name}{tag}")
    return lines
