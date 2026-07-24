"""iPhone companion setup pack — zip with Safari link + instructions."""

from __future__ import annotations

import html
import zipfile
from datetime import datetime
from pathlib import Path

from jarvis.config import DATA_DIR, ROOT


def _tailscale_ip() -> str:
    try:
        import subprocess

        out = subprocess.check_output(
            ["tailscale", "ip", "-4"],
            text=True,
            timeout=3,
            stderr=subprocess.DEVNULL,
        ).strip().splitlines()
        return (out[0].strip() if out else "") or ""
    except Exception:
        return ""


def companion_url(*, token: str, port: int = 8766, host: str | None = None) -> tuple[str, str]:
    """Return (url, host_used)."""
    ts = (host or "").strip() or _tailscale_ip()
    host_used = ts or "YOUR-TAILSCALE-IP"
    url = f"http://{host_used}:{int(port)}/?token={token}"
    return url, host_used


def build_companion_setup_zip(
    *,
    token: str,
    port: int = 8766,
    user_name: str = "Sir",
    out_dir: Path | None = None,
) -> dict[str, str]:
    """
    Build a small zip the user can AirDrop / iCloud / USB to an iPhone,
    then open OPEN_IN_SAFARI.html in Safari (Files → Share → Safari).
    """
    token = (token or "").strip()
    if not token:
        raise ValueError("missing companion token")

    url, host = companion_url(token=token, port=port)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    exports = Path(out_dir or (DATA_DIR / "exports"))
    exports.mkdir(parents=True, exist_ok=True)
    zip_path = exports / f"jarvis_iphone_companion_{stamp}.zip"

    readme = f"""JARVIS · iPhone companion setup pack
====================================

For: {user_name}
Built: {datetime.now().strftime("%Y-%m-%d %H:%M")}

WHAT THIS IS
  A Safari setup pack for your iPhone 14 travel companion.
  Not Bluetooth — use Safari while Tailscale is Connected.

ON THE PC
  1. Install Tailscale and leave Jarvis running.
  2. Your Tailscale IP should look like 100.x.y.z
     (detected host in this pack: {host})

ON THE iPHONE 14
  1. Install Tailscale (same account as the PC) → Connected.
  2. Copy this zip to the iPhone (AirDrop, iCloud Drive, email, USB).
  3. Files app → unzip → open OPEN_IN_SAFARI.html
  4. Tap "Open Jarvis in Safari".
  5. Safari → Share → Add to Home Screen.

DIRECT LINK (Tailscale must be up)
  {url}

TOKEN (keep private)
  {token}

SAY ON THE DESK
  "open phone companion"
  "companion zip"
"""

    open_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <title>Open Jarvis</title>
  <style>
    :root {{
      --bg: #02080c; --cyan: #00e8ff; --text: #e8f4f8; --muted: #6a8a96;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; min-height: 100dvh; font-family: -apple-system, system-ui, sans-serif;
      background: radial-gradient(120% 80% at 50% -10%, #0a2230 0%, var(--bg) 55%);
      color: var(--text); padding: 2rem 1.25rem; display: flex; flex-direction: column;
      justify-content: center; gap: 1rem;
    }}
    h1 {{
      margin: 0; letter-spacing: 0.18em; text-transform: uppercase; color: var(--cyan);
      font-size: 1.5rem; font-weight: 650;
    }}
    p {{ color: var(--muted); line-height: 1.45; }}
    a.btn {{
      display: block; text-align: center; text-decoration: none; color: var(--bg);
      background: var(--cyan); font-weight: 700; letter-spacing: 0.06em;
      text-transform: uppercase; padding: 1rem 1.1rem; border: none;
    }}
    code {{
      display: block; margin-top: 0.75rem; padding: 0.75rem; background: #071218;
      border: 1px solid rgba(0,232,255,0.25); color: var(--cyan); font-size: 0.78rem;
      word-break: break-all;
    }}
    .steps {{ font-size: 0.92rem; color: var(--text); }}
  </style>
</head>
<body>
  <h1>Jarvis</h1>
  <p class="steps">Tailscale must be <strong>Connected</strong> on this iPhone. Then open the companion in Safari and Add to Home Screen.</p>
  <a class="btn" href="{html.escape(url)}">Open Jarvis in Safari</a>
  <p>If the button does nothing, copy this link into Safari:</p>
  <code>{html.escape(url)}</code>
  <p>Share → Add to Home Screen → Jarvis.</p>
</body>
</html>
"""

    url_txt = url + "\n"
    token_txt = token + "\n"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme)
        zf.writestr("OPEN_IN_SAFARI.html", open_html)
        zf.writestr("companion_url.txt", url_txt)
        zf.writestr("token.txt", token_txt)
        # Tiny pointer to full repo docs when pack stays on PC
        handover = ROOT / "docs" / "HANDOVER_COMPANION.md"
        if handover.is_file():
            zf.write(handover, arcname="HANDOVER_COMPANION.md")

    # Also drop a stable "latest" copy for easy finding
    latest = exports / "jarvis_iphone_companion_latest.zip"
    try:
        latest.write_bytes(zip_path.read_bytes())
    except Exception:
        pass

    # Desktop shortcut copy when possible
    desktop_copy = ""
    try:
        desk = Path.home() / "Desktop"
        if desk.is_dir():
            dest = desk / zip_path.name
            dest.write_bytes(zip_path.read_bytes())
            desktop_copy = str(dest)
    except Exception:
        desktop_copy = ""

    return {
        "zip": str(zip_path),
        "latest": str(latest),
        "desktop": desktop_copy,
        "url": url,
        "host": host,
        "token": token,
    }
