"""Windows unlock — wake logon UI and type vault PIN (best-effort).

Full Win+L secure desktop often blocks SendInput from user-session apps.
Works best when the screen is on the password field / after a Wake and focus.
PIN is never spoken or logged.
"""

from __future__ import annotations

import time


def _type_unicode(text: str) -> None:
    """Send Unicode keystrokes via SendInput (handles $, letters, numbers)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        )

    class INPUT(ctypes.Structure):
        class _I(ctypes.Union):
            _fields_ = (("ki", KEYBDINPUT),)

        _anonymous_ = ("i",)
        _fields_ = (("type", wintypes.DWORD), ("i", _I))

    extra = ctypes.pointer(ctypes.c_ulong(0))
    for ch in text:
        down = INPUT(type=INPUT_KEYBOARD)
        down.ki = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE, 0, extra)
        up = INPUT(type=INPUT_KEYBOARD)
        up.ki = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, extra)
        user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
        user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
        time.sleep(0.012)


def _press_vk(vk: int) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        )

    class INPUT(ctypes.Structure):
        class _I(ctypes.Union):
            _fields_ = (("ki", KEYBDINPUT),)

        _anonymous_ = ("i",)
        _fields_ = (("type", wintypes.DWORD), ("i", _I))

    extra = ctypes.pointer(ctypes.c_ulong(0))
    down = INPUT(type=1)
    down.ki = KEYBDINPUT(vk, 0, 0, 0, extra)
    up = INPUT(type=1)
    up.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, extra)
    user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
    time.sleep(0.03)
    user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))


def unlock_with_stored_pin(*, delay_sec: float = 0.6) -> str:
    """
    Wake login field → type vault unlock_pin → Enter.
    Returns a speakable status string that never includes the PIN.
    """
    try:
        from jarvis.core.secrets_vault import get_vault

        pin = (get_vault().get("unlock_pin") or "").strip()
    except Exception as e:
        return f"Unlock vault unavailable: {e}"

    if not pin:
        return (
            "No unlock PIN stored. Say set unlock pin then tell me the PIN once, "
            "or store it in the DPAPI vault as unlock_pin."
        )

    try:
        import ctypes

        # Nudge mouse / ctrl so the password box can take focus after wake
        user32 = ctypes.windll.user32
        user32.SetCursorPos(200, 200)
        time.sleep(0.05)
        _press_vk(0x11)  # CTRL tap often wakes lock UI
        time.sleep(max(0.2, float(delay_sec)))
        # Ensure field clear-ish: Ctrl+A then type (login field usually empty)
        _type_unicode(pin)
        time.sleep(0.15)
        _press_vk(0x0D)  # Enter
        return "Unlock sequence sent. If Windows blocked the lock screen, tap the password box and say unlock again."
    except Exception as e:
        return f"Unlock failed: {e}"


def store_unlock_pin(pin: str) -> str:
    pin = (pin or "").strip()
    if len(pin) < 4:
        return "PIN too short."
    try:
        from jarvis.core.secrets_vault import get_vault

        get_vault().set("unlock_pin", pin)
        return "Unlock PIN saved encrypted in your DPAPI vault. I will never speak it."
    except Exception as e:
        return f"Could not store PIN: {e}"
