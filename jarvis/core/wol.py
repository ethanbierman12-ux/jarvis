"""Wake-on-LAN helpers — magic packet + local NIC discovery."""

from __future__ import annotations

import re
import socket
import subprocess
from dataclasses import dataclass


@dataclass
class NicInfo:
    name: str
    mac: str
    ipv4: str | None = None


def normalize_mac(mac: str) -> str:
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", (mac or "").strip())
    if len(cleaned) != 12:
        raise ValueError(f"Invalid MAC address: {mac!r}")
    return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2)).upper()


def is_valid_mac(mac: str) -> bool:
    try:
        normalize_mac(mac)
        return True
    except ValueError:
        return False


def magic_packet(mac: str) -> bytes:
    """Build a standard WOL magic packet (6×FF + 16×MAC)."""
    raw = bytes.fromhex(normalize_mac(mac).replace(":", ""))
    return b"\xff" * 6 + raw * 16


def send_magic_packet(
    mac: str,
    broadcast: str = "255.255.255.255",
    port: int = 9,
    repeats: int = 3,
) -> str:
    """Send a magic packet to wake a PC. Safe no-op if the target is already on."""
    pkt = magic_packet(mac)
    addr = (broadcast, int(port))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for _ in range(max(1, repeats)):
            sock.sendto(pkt, addr)
    return f"Wake packet sent to {normalize_mac(mac)} via {broadcast}:{port}."


def list_nics() -> list[NicInfo]:
    """Best-effort NIC list on Windows (falls back to empty on failure)."""
    nics: list[NicInfo] = []
    try:
        ps = (
            "Get-NetAdapter | Where-Object { $_.MacAddress -and $_.Status -ne 'Disabled' } | "
            "ForEach-Object { "
            "$ip = (Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 "
            "-ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty IPAddress); "
            "[PSCustomObject]@{ Name=$_.Name; Mac=$_.MacAddress; IPv4=$ip } "
            "} | ConvertTo-Json -Compress"
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
            return nics
        import json

        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        for row in data:
            mac = str(row.get("Mac") or "").replace("-", ":")
            if not is_valid_mac(mac):
                continue
            nics.append(
                NicInfo(
                    name=str(row.get("Name") or "NIC"),
                    mac=normalize_mac(mac),
                    ipv4=(str(row["IPv4"]) if row.get("IPv4") else None),
                )
            )
    except Exception:
        pass
    return nics


def primary_mac() -> str | None:
    """Prefer a real LAN link (non-APIPA), Ethernet first, then Wi-Fi."""
    nics = list_nics()
    if not nics:
        return None

    def real_ip(n: NicInfo) -> bool:
        return bool(n.ipv4) and not n.ipv4.startswith("169.254.")

    for n in nics:
        if "ethernet" in n.name.lower() and real_ip(n):
            return n.mac
    for n in nics:
        if real_ip(n):
            return n.mac
    for n in nics:
        if "ethernet" in n.name.lower():
            return n.mac
    return nics[0].mac


def guess_broadcast(ipv4: str | None = None) -> str:
    """Rough /24 broadcast from an IPv4, else global broadcast."""
    if not ipv4:
        for n in list_nics():
            if n.ipv4 and not n.ipv4.startswith("169.254."):
                ipv4 = n.ipv4
                break
    if not ipv4:
        return "255.255.255.255"
    parts = ipv4.split(".")
    if len(parts) != 4:
        return "255.255.255.255"
    return f"{parts[0]}.{parts[1]}.{parts[2]}.255"


def local_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None
