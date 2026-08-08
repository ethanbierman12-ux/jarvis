"""Phone Link / Link to Windows setup helper for Jarvis live comms."""

from __future__ import annotations

import subprocess
import webbrowser
from pathlib import Path


STORE_URL = "ms-windows-store://pdp/?ProductId=9NMPJ99VJBWV"
STORE_WEB = "https://apps.microsoft.com/detail/9nmpj99vjbwv"
IPHONE_APP = "https://apps.apple.com/app/link-to-windows/id1456181778"
PHONE_PROTOCOL = "ms-phone:"


def phone_link_installed() -> bool:
    """True if Phone Link / Your Phone package looks present."""
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-AppxPackage | Where-Object { "
                "$_.Name -match 'YourPhone|PhoneExperience|PhoneLink' }).Name",
            ],
            capture_output=True,
            text=True,
            timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (r.stdout or "").strip()
        if out:
            return True
    except Exception:
        pass
    # Common launch stubs
    apps = Path.home() / "AppData" / "Local" / "Microsoft" / "WindowsApps"
    for name in (
        "PhoneExperienceHost.exe",
        "YourPhone.exe",
        "Microsoft.YourPhone_*",
    ):
        if list(apps.glob(name)):
            return True
    return False


def install_phone_link() -> str:
    """Best-effort Store install via winget (non-blocking); always opens Store."""
    notes: list[str] = []
    try:
        subprocess.Popen(
            [
                "winget",
                "install",
                "--id",
                "9NMPJ99VJBWV",
                "--source",
                "msstore",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "-h",
            ],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        notes.append("Phone Link install kicked off in the background.")
    except Exception as e:
        notes.append(f"winget unavailable ({e}) — opening Store.")
    open_store()
    return " ".join(notes)


def open_store() -> None:
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", STORE_URL],
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        try:
            webbrowser.open(STORE_WEB)
        except Exception:
            pass


def open_phone_link() -> str:
    """Launch Phone Link app or Store page."""
    # Prefer protocol / explorer shell
    for cmd in (
        ["cmd", "/c", "start", "", PHONE_PROTOCOL],
        ["explorer.exe", "shell:AppsFolder\\Microsoft.YourPhone_8wekyb3d8bbwe!App"],
    ):
        try:
            subprocess.Popen(
                cmd,
                shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return "Opening Phone Link."
        except Exception:
            continue
    if not phone_link_installed():
        open_store()
        return "Phone Link not installed — opened Microsoft Store."
    open_store()
    return "Could not launch Phone Link — opened Store."


def open_iphone_link_app_page() -> None:
    try:
        webbrowser.open(IPHONE_APP)
    except Exception:
        pass


def open_notification_settings() -> None:
    """Windows notification settings — needed for toast watching."""
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", "ms-settings:notifications"],
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass


def setup_phone_link(*, ensure_install: bool = True) -> str:
    """
    Full PC-side setup:
      1) Install Phone Link if missing
      2) Launch Phone Link
      3) Open notification settings + iPhone Link to Windows App Store page
    """
    bits: list[str] = []
    installed = phone_link_installed()
    if not installed and ensure_install:
        bits.append(install_phone_link())
        # re-check lightly
        installed = phone_link_installed()
    bits.append(open_phone_link())
    open_notification_settings()
    open_iphone_link_app_page()
    bits.append(
        "On iPhone: install **Link to Windows**, sign in with the same Microsoft "
        "account, allow notifications. On PC: finish pairing in Phone Link, enable "
        "notifications (and Messages if offered). Note: iPhone Phone Link is "
        "notification-based — not full iMessage mirroring like Android SMS."
    )
    if installed:
        bits.insert(0, "Phone Link is installed.")
    return " ".join(bits)
