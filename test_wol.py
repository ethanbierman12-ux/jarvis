"""Send a one-shot wake over Wi-Fi and/or Bluetooth (for testing)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from jarvis.core.clap_wake import send_clap_wake  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Test clap-wake transports")
    p.add_argument("--mac", help="Wi-Fi / LAN MAC (AA:BB:CC:DD:EE:FF)")
    p.add_argument("--bt", help="Bluetooth MAC of the target PC")
    p.add_argument("--broadcast", default=None)
    p.add_argument("--port", type=int, default=9)
    p.add_argument(
        "--transport",
        choices=("wifi", "bluetooth", "both"),
        default="both",
    )
    args = p.parse_args()

    cfg: dict = {
        "transports": ["wifi", "bluetooth"] if args.transport == "both" else [args.transport],
        "port": args.port,
        "broadcast": args.broadcast or "255.255.255.255",
        "target_mac": args.mac or "",
        "bluetooth_mac": args.bt or "",
    }
    path = ROOT / "config" / "clap_wol.json"
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for k, v in raw.items():
                if k not in cfg or cfg[k] in ("", None, "255.255.255.255") and k == "broadcast":
                    if args.broadcast is None and k == "broadcast":
                        cfg["broadcast"] = v
                if k == "target_mac" and not cfg["target_mac"]:
                    cfg["target_mac"] = v
                if k == "wifi_mac" and not cfg["target_mac"]:
                    cfg["target_mac"] = v
                if k == "bluetooth_mac" and not cfg["bluetooth_mac"]:
                    cfg["bluetooth_mac"] = v
                if k == "port" and args.port == 9:
                    cfg["port"] = v
        except Exception:
            pass
    settings = ROOT / "config" / "settings.json"
    if settings.exists():
        try:
            s = json.loads(settings.read_text(encoding="utf-8"))
            if not cfg["target_mac"]:
                cfg["target_mac"] = s.get("wol_mac") or ""
            if not cfg["bluetooth_mac"]:
                cfg["bluetooth_mac"] = s.get("bluetooth_mac") or ""
            if args.broadcast is None and s.get("wol_broadcast"):
                cfg["broadcast"] = s["wol_broadcast"]
        except Exception:
            pass

    if args.transport in ("wifi", "both") and not cfg["target_mac"]:
        print("No Wi-Fi MAC. Pass --mac or run setup_wol.bat")
        return 1
    if args.transport in ("bluetooth", "both") and not cfg["bluetooth_mac"]:
        print("No Bluetooth MAC — Wi-Fi will still run if enabled. Pass --bt or run setup_wol.bat")

    for line in send_clap_wake(cfg):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
