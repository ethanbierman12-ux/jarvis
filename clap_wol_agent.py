"""
Clap → wake agent (Wi-Fi and/or Bluetooth).

Run on a SECOND always-on device (phone/Termux, Pi, spare laptop) that can
hear you. The target PC cannot listen while powered off.

Transports (config/clap_wol.json → "transports"):
  wifi       — Wake-on-LAN magic packet over Wi-Fi/LAN
  bluetooth  — RFCOMM probe to the PC Bluetooth MAC (Wake-on-Bluetooth)
  both       — fire Wi-Fi and Bluetooth (default)

Mic (config → "mic"):
  auto       — prefer a Bluetooth headset mic if paired, else default
  bluetooth  — require a Bluetooth mic
  wifi       — use a normal/USB/onboard mic (non-Bluetooth)

Setup on the TARGET PC:
  1. Run setup_wol.bat as Admin
  2. BIOS: Wake on LAN + disable ErP deep sleep
  3. Say to Jarvis: standby for clap

On THIS device:
  python clap_wol_agent.py
  python clap_wol_agent.py --list-mics
  python clap_wol_agent.py --list-bt
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "clap_wol.json"


def _load_cfg() -> dict:
    defaults = {
        "transports": ["wifi", "bluetooth"],
        "target_mac": "",
        "wifi_mac": "",
        "broadcast": "255.255.255.255",
        "port": 9,
        "bluetooth_mac": "",
        "bluetooth_channel": 1,
        "mic": "auto",
        "mic_name": "",
        "claps_required": 2,
        "clap_window_sec": 1.2,
        "cooldown_sec": 10.0,
        "peak_threshold": 0.35,
        "min_gap_sec": 0.12,
        "sample_rate": 16000,
        "block_size": 1024,
    }
    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                defaults.update(raw)
        except Exception as e:
            print(f"[clap-wake] config read failed: {e}")
    settings = ROOT / "config" / "settings.json"
    if settings.exists():
        try:
            s = json.loads(settings.read_text(encoding="utf-8-sig"))
            if not defaults.get("target_mac") and s.get("wol_mac"):
                defaults["target_mac"] = s["wol_mac"]
            if not defaults.get("wifi_mac") and s.get("wol_mac"):
                defaults["wifi_mac"] = s["wol_mac"]
            if s.get("wol_broadcast"):
                defaults["broadcast"] = s["wol_broadcast"]
            if not defaults.get("bluetooth_mac") and s.get("bluetooth_mac"):
                defaults["bluetooth_mac"] = s["bluetooth_mac"]
        except Exception:
            pass
    # Keep wifi_mac / target_mac in sync
    if defaults.get("wifi_mac") and not defaults.get("target_mac"):
        defaults["target_mac"] = defaults["wifi_mac"]
    if defaults.get("target_mac") and not defaults.get("wifi_mac"):
        defaults["wifi_mac"] = defaults["target_mac"]
    return defaults


def _fire(cfg: dict) -> None:
    sys.path.insert(0, str(ROOT))
    from jarvis.core.clap_wake import send_clap_wake

    for line in send_clap_wake(cfg):
        print(f"[clap-wake] {line}")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    parser = argparse.ArgumentParser(description="Clap → Wi-Fi / Bluetooth wake")
    parser.add_argument("--list-mics", action="store_true", help="List input microphones")
    parser.add_argument("--list-bt", action="store_true", help="List Bluetooth adapters")
    parser.add_argument("--test", action="store_true", help="Send wake now (no clap)")
    parser.add_argument(
        "--transport",
        choices=("wifi", "bluetooth", "both"),
        help="Override transports for this run",
    )
    parser.add_argument(
        "--mic",
        choices=("auto", "bluetooth", "wifi"),
        help="Override mic preference for this run",
    )
    args = parser.parse_args()

    from jarvis.core.clap_wake import (
        find_mic_device,
        list_bluetooth_adapters,
        list_input_mics,
        parse_transports,
    )
    from jarvis.core.wol import normalize_mac

    if args.list_mics:
        lines = list_input_mics()
        print("[clap-wake] input devices:")
        print("\n".join(lines) if lines else "  (none — install sounddevice)")
        return 0

    if args.list_bt:
        adapters = list_bluetooth_adapters()
        print("[clap-wake] Bluetooth adapters:")
        if not adapters:
            print("  (none found)")
        for a in adapters:
            print(f"  {a['mac']}  {a['name']}  ({a['status']})")
        return 0

    cfg = _load_cfg()
    if args.transport:
        cfg["transports"] = (
            ["wifi", "bluetooth"] if args.transport == "both" else [args.transport]
        )
    if args.mic:
        cfg["mic"] = args.mic

    transports = parse_transports(cfg.get("transports") or cfg.get("transport"))
    need_wifi = "wifi" in transports
    need_bt = "bluetooth" in transports

    if need_wifi:
        mac = (cfg.get("target_mac") or cfg.get("wifi_mac") or "").strip()
        if not mac:
            print("[clap-wake] Wi-Fi enabled but no target_mac. Run setup_wol.bat on the PC.")
            return 1
        try:
            cfg["target_mac"] = normalize_mac(mac)
            cfg["wifi_mac"] = cfg["target_mac"]
        except ValueError as e:
            print(f"[clap-wake] {e}")
            return 1

    if need_bt:
        bt = (cfg.get("bluetooth_mac") or "").strip()
        if bt:
            try:
                cfg["bluetooth_mac"] = normalize_mac(bt)
            except ValueError as e:
                print(f"[clap-wake] bluetooth_mac: {e}")
                return 1
        else:
            print(
                "[clap-wake] Warning: bluetooth transport on, but bluetooth_mac empty — "
                "Wi-Fi will still work if enabled."
            )

    if args.test:
        _fire(cfg)
        return 0

    try:
        import numpy as np
        import sounddevice as sd
    except ImportError:
        print("[clap-wake] Need numpy + sounddevice:")
        print("  pip install numpy sounddevice")
        return 1

    needed = max(1, int(cfg.get("claps_required") or 2))
    window = float(cfg.get("clap_window_sec") or 1.2)
    cooldown = float(cfg.get("cooldown_sec") or 10.0)
    threshold = float(cfg.get("peak_threshold") or 0.35)
    min_gap = float(cfg.get("min_gap_sec") or 0.12)
    rate = int(cfg.get("sample_rate") or 16000)
    block = int(cfg.get("block_size") or 1024)
    mic_pref = str(cfg.get("mic") or "auto")
    mic_name = str(cfg.get("mic_name") or "")
    device = find_mic_device(prefer=mic_pref, name_substr=mic_name)

    if mic_pref == "bluetooth" and device is None:
        print("[clap-wake] No Bluetooth mic found. Pair a headset or set mic to auto/wifi.")
        print("  python clap_wol_agent.py --list-mics")
        return 1

    peaks: list[float] = []
    last_fire = 0.0
    last_peak = 0.0
    armed = True

    print("[clap-wake] armed")
    print(f"[clap-wake] transports  {', '.join(transports)}")
    if need_wifi:
        print(f"[clap-wake] wifi        {cfg.get('target_mac')} via {cfg.get('broadcast')}:{cfg.get('port')}")
    if need_bt:
        print(f"[clap-wake] bluetooth   {cfg.get('bluetooth_mac') or '(not set)'}")
    print(f"[clap-wake] mic         {mic_pref}" + (f" → device {device}" if device is not None else " → default"))
    print(f"[clap-wake] gesture     {needed} clap(s) within {window:.1f}s")
    print("[clap-wake] Ctrl+C to stop")

    def on_audio(indata, frames, time_info, status) -> None:  # noqa: ANN001
        nonlocal peaks, last_fire, last_peak, armed
        if status:
            return
        now = time.monotonic()
        if now - last_fire < cooldown:
            peaks.clear()
            return
        mono = np.asarray(indata, dtype=np.float32).reshape(-1)
        peak = float(np.max(np.abs(mono))) if mono.size else 0.0
        if peak < threshold:
            return
        if now - last_peak < min_gap:
            return
        last_peak = now
        peaks = [t for t in peaks if now - t <= window]
        peaks.append(now)
        print(f"[clap-wake] clap {len(peaks)}/{needed}  (level {peak:.2f})")
        if len(peaks) >= needed and armed:
            armed = False
            last_fire = now
            peaks.clear()
            try:
                _fire(cfg)
            except Exception as e:
                print(f"[clap-wake] send failed: {e}")
            armed = True

    stream_kwargs = dict(
        channels=1,
        samplerate=rate,
        blocksize=block,
        dtype="float32",
        callback=on_audio,
    )
    if device is not None:
        stream_kwargs["device"] = device

    try:
        with sd.InputStream(**stream_kwargs):
            while True:
                time.sleep(0.25)
    except KeyboardInterrupt:
        print("\n[clap-wake] stopped")
        return 0
    except Exception as e:
        print(f"[clap-wake] mic error: {e}")
        if device is not None:
            print("[clap-wake] Tip: try --mic wifi or --list-mics")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
