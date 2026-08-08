"""Jarvis HUD — Stark-lab chrome (cyan glow / deep void / slate).

Design tokens (keep HUD + vibe templates aligned):
  Primary cyan:  #00E5FF / #00F0FF
  Deep void:     #020813 / #0A0F1D
  Warning:       #FF3B30 / #FF9500
  Secondary text:#708090
"""

from __future__ import annotations

from jarvis.config import Theme

# Prefer geometric / mono stacks; fall back to Windows system fonts
UI_SANS = '"Rajdhani", "Orbitron", "Bahnschrift", "Segoe UI Variable Display", "Segoe UI"'
UI_MONO = '"Share Tech Mono", "Roboto Mono", "Cascadia Mono", "Consolas", "Courier New"'

# Canonical Stark palette
CYAN = "#00E5FF"
CYAN_HOT = "#00F0FF"
VOID = "#020813"
VOID_PANEL = "#0A0F1D"
WARN = "#FF3B30"
WARN_AMBER = "#FF9500"
SLATE = "#708090"
OK = "#39FF14"


def weather_mood(condition: str) -> str:
    """Map condition text → clear | rain | storm | cloudy."""
    c = (condition or "").lower()
    if any(k in c for k in ("thunder", "storm", "lightning")):
        return "storm"
    if any(k in c for k in ("rain", "drizzle", "shower", "precip", "sleet")):
        return "rain"
    if any(k in c for k in ("snow", "blizzard", "flurr")):
        return "rain"
    if any(k in c for k in ("cloud", "overcast", "fog", "mist", "haze")):
        return "cloudy"
    return "clear"


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    h = (hex_color or CYAN_HOT).lstrip("#")
    if len(h) != 6:
        return 0, 229, 255
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgba(hex_color: str, alpha: int) -> str:
    r, g, b = _hex_rgb(hex_color)
    return f"rgba({r}, {g}, {b}, {alpha})"


def mood_palette(mood: str) -> dict[str, str]:
    """Same family as pc_poweron secure boot — cyan rails, deep void."""
    if mood == "storm":
        return {
            "accent": "#7ec8ff",
            "accent2": "#3a9fd4",
            "void": "#010208",
            "grad0": "#000106",
            "grad1": "#0a1428",
            "grad2": "#040814",
            "panel": "rgba(10, 15, 29, 210)",
            "panel2": "rgba(2, 8, 19, 235)",
            "border": "rgba(126, 200, 255, 100)",
            "dim": SLATE,
            "white": "#e8f4ff",
            "label": "STORM",
            "glow": "rgba(126, 200, 255, 55)",
            "warn": WARN,
        }
    if mood == "rain":
        return {
            "accent": "#4de8ff",
            "accent2": "#2a90d4",
            "void": VOID,
            "grad0": "#01040a",
            "grad1": "#071624",
            "grad2": "#040c14",
            "panel": "rgba(10, 15, 29, 205)",
            "panel2": "rgba(2, 8, 19, 230)",
            "border": "rgba(70, 210, 255, 100)",
            "dim": SLATE,
            "white": "#d8f4ff",
            "label": "RAIN",
            "glow": "rgba(70, 210, 255, 55)",
            "warn": WARN_AMBER,
        }
    if mood == "cloudy":
        return {
            "accent": "#8ab4c8",
            "accent2": "#00d2e6",
            "void": "#05070a",
            "grad0": "#030508",
            "grad1": "#0c1218",
            "grad2": "#080b10",
            "panel": "rgba(10, 15, 29, 200)",
            "panel2": "rgba(4, 8, 12, 230)",
            "border": "rgba(140, 180, 200, 85)",
            "dim": SLATE,
            "white": "#e0e8f0",
            "label": "OVERCAST",
            "glow": "rgba(140, 180, 200, 45)",
            "warn": WARN_AMBER,
        }
    # Clear — lockstep with secure boot hologram + Stark tokens
    return {
        "accent": CYAN_HOT,
        "accent2": CYAN,
        "void": VOID,
        "grad0": "#01040c",
        "grad1": VOID_PANEL,
        "grad2": "#030a14",
        "panel": "rgba(10, 15, 29, 200)",
        "panel2": "rgba(2, 8, 19, 235)",
        "border": "rgba(0, 229, 255, 95)",
        "dim": SLATE,
        "white": "#e8f4ff",
        "label": "CLEAR",
        "glow": "rgba(0, 229, 255, 70)",
        "warn": WARN,
    }


def stylesheet(theme: Theme, mood: str = "clear") -> str:
    p = mood_palette(mood)
    accent = p["accent"]
    accent2 = p["accent2"]
    warn = p.get("warn", WARN)
    a14 = _rgba(accent, 14)
    a22 = _rgba(accent, 22)
    a32 = _rgba(accent, 32)
    a55 = _rgba(accent, 55)
    a100 = _rgba(accent, 100)
    a120 = _rgba(accent, 120)
    a160 = _rgba(accent, 160)
    a190 = _rgba(accent, 190)
    a2_40 = _rgba(accent2, 40)
    a2_80 = _rgba(accent2, 80)
    return f"""
    QMainWindow, QWidget#Root {{
        background-color: {p["void"]};
        color: {p["white"]};
        font-family: {UI_SANS};
    }}
    QWidget#Root {{
        background: qlineargradient(x1:0, y1:0, x2:0.65, y2:1,
            stop:0 {p["grad0"]}, stop:0.45 {p["grad1"]}, stop:1 {p["grad2"]});
    }}
    QLabel {{ background: transparent; color: {p["white"]}; }}
    QLabel#Brand {{
        color: {accent};
        font-size: 26px;
        font-weight: 800;
        letter-spacing: 8px;
        padding-bottom: 0px;
    }}
    QLabel#BrandSub {{
        color: {p["dim"]};
        font-family: {UI_MONO};
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 3px;
        padding-top: 4px;
    }}
    QLabel#SectionTitle {{
        color: {accent};
        font-family: {UI_MONO};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 4px;
    }}
    QLabel#Dim {{ color: {p["dim"]}; font-size: 11px; }}
    QLabel#MicroLabel {{
        color: {p["dim"]};
        font-family: {UI_MONO};
        font-size: 8px;
        letter-spacing: 2px;
    }}
    QLabel#StatusPill {{
        color: {OK};
        background: rgba(57, 255, 20, 18);
        border: 1px solid rgba(57, 255, 20, 110);
        border-radius: 2px;
        padding: 5px 12px;
        font-family: {UI_MONO};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 2px;
        max-width: 220px;
    }}
    QLabel#MicPill {{
        color: {accent};
        background: {a14};
        border: 1px solid {p["border"]};
        border-radius: 2px;
        padding: 5px 12px;
        font-family: {UI_MONO};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 2px;
        max-width: 160px;
    }}
    QFrame#HeaderBar, QWidget#HeaderBar {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {a22}, stop:0.4 rgba(10, 15, 29, 180),
            stop:0.85 {a2_40}, stop:1 rgba(2, 8, 19, 40));
        border: 1px solid {p["border"]};
        border-left: 3px solid {accent};
        border-right: 3px solid {accent2};
        border-radius: 2px;
        padding: 6px 10px;
    }}
    QFrame#TalkBar {{
        background: rgba(10, 15, 29, 230);
        border: 1px solid {p["border"]};
        border-radius: 2px;
        padding: 6px 10px;
    }}
    QFrame#GlassPanel, QWidget#GlassPanel {{
        background-color: {p["panel"]};
        border: 1px solid {p["border"]};
        border-top: 1px solid {_rgba(accent, 140)};
        border-radius: 4px;
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget {{
        background: transparent;
    }}
    QFrame#KpiCard {{
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 rgba(0, 40, 56, 180), stop:1 rgba(2, 8, 19, 210));
        border: 1px solid {p["border"]};
        border-left: 3px solid {accent};
        border-radius: 4px;
    }}
    QPushButton#StartBtn {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 {a100}, stop:1 {a2_80});
        border: 1px solid {accent};
        border-radius: 2px;
        color: #041018;
        padding: 9px 22px;
        font-size: 12px;
        font-weight: 800;
        letter-spacing: 3px;
        min-height: 36px;
    }}
    QPushButton#StartBtn:hover {{
        background: {a160};
        color: #02080c;
        border-color: {accent2};
        padding: 9px 24px;
    }}
    QPushButton#StartBtn:pressed {{
        background: {_rgba(accent2, 140)};
        color: #fff;
    }}
    QPushButton#TalkBtn {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 {a120}, stop:1 {_rgba(accent2, 70)});
        border: 1px solid {accent};
        border-radius: 2px;
        color: #021018;
        padding: 10px 28px;
        font-size: 13px;
        font-weight: 800;
        letter-spacing: 2px;
        min-height: 38px;
        min-width: 180px;
    }}
    QPushButton#TalkBtn:hover {{
        background: {a190};
        border-color: {accent2};
        padding: 10px 30px;
    }}
    QPushButton#TalkBtn:pressed {{
        background: {_rgba(accent2, 150)};
        color: #fff;
    }}
    QPushButton#GhostBtn {{
        background: rgba(10, 15, 29, 150);
        border: 1px solid {a55};
        border-radius: 2px;
        color: {accent};
        padding: 4px 8px;
        font-family: {UI_MONO};
        font-size: 10px;
        font-weight: 650;
        letter-spacing: 1px;
        min-height: 28px;
    }}
    QPushButton#GhostBtn:hover {{
        background: {a32};
        border-color: {accent};
        color: #f2ffff;
        border-bottom: 2px solid {accent2};
        padding: 4px 10px;
    }}
    QPushButton#GhostBtn:pressed {{
        background: {_rgba(accent2, 70)};
        color: #fff;
    }}
    QPushButton#MediaBtn {{
        background: rgba(10, 15, 29, 130);
        border: 1px solid {a55};
        border-radius: 2px;
        color: {accent};
        padding: 5px 7px;
        font-family: {UI_MONO};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1px;
        min-height: 28px;
    }}
    QPushButton#MediaBtn:hover {{
        background: {a32};
        border-color: {accent};
        color: #ffffff;
        padding: 5px 9px;
    }}
    QPushButton#MediaBtn:pressed {{
        background: {a100};
    }}
    QPushButton#DangerBtn {{
        background: rgba(40, 8, 8, 150);
        border: 1px solid {_rgba(warn, 140)};
        border-radius: 2px;
        color: #ffc8a8;
        padding: 4px 7px;
        font-family: {UI_MONO};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.8px;
        min-height: 28px;
    }}
    QPushButton#DangerBtn:hover {{
        background: {_rgba(warn, 55)};
        border-color: {warn};
        color: #ffe8d8;
    }}
    QLineEdit {{
        background: rgba(10, 15, 29, 220);
        border: 1px solid {p["border"]};
        border-radius: 2px;
        padding: 10px 14px;
        color: {p["white"]};
        selection-background-color: {_rgba(accent, 120)};
        font-size: 13px;
    }}
    QLineEdit:focus {{
        border: 1px solid {accent};
    }}
    QLineEdit#CmdInput {{
        background: rgba(10, 15, 29, 220);
        border: 1px solid {p["border"]};
        border-radius: 2px;
        padding: 10px 14px;
        color: {p["white"]};
        font-size: 13px;
    }}
    QTextEdit, QPlainTextEdit {{
        background: rgba(10, 15, 29, 210);
        border: 1px solid {p["border"]};
        border-radius: 2px;
        color: {p["white"]};
        selection-background-color: {_rgba(accent, 90)};
        font-family: {UI_MONO};
        font-size: 11px;
        padding: 8px;
    }}
    QTextEdit#Log {{
        background: rgba(10, 15, 29, 210);
        border: 1px solid {p["border"]};
        border-top: 1px solid {_rgba(accent, 90)};
        color: #8fd0e0;
        font-family: {UI_MONO};
        font-size: 11px;
        padding: 8px 10px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {_rgba(accent, 70)};
        border-radius: 3px;
        min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QListWidget {{
        background: rgba(10, 15, 29, 180);
        border: 1px solid {p["border"]};
        border-radius: 2px;
        color: {p["white"]};
        outline: none;
    }}
    QListWidget::item:selected {{
        background: {_rgba(accent, 40)};
        color: {accent};
    }}
    QProgressBar {{
        background: rgba(10, 15, 29, 200);
        border: 1px solid {p["border"]};
        border-radius: 2px;
        text-align: center;
        color: {p["dim"]};
        font-family: {UI_MONO};
        font-size: 9px;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 {accent}, stop:1 {accent2});
    }}
    QPushButton#QuickToggle {{
        background: rgba(10, 15, 29, 190);
        border: 1px solid {_rgba(accent, 55)};
        border-radius: 2px;
        color: {p["dim"]};
        padding: 4px 6px;
        font-family: {UI_MONO};
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 1.5px;
        min-height: 30px;
    }}
    QPushButton#QuickToggle:hover {{
        color: {accent};
        border-color: {_rgba(accent, 120)};
        background: {_rgba(accent, 22)};
    }}
    QPushButton#QuickToggle[on="true"] {{
        color: {accent};
        background: {_rgba(accent, 32)};
        border: 1px solid {_rgba(accent, 140)};
        border-left: 3px solid {accent};
    }}
    QScrollArea#LeftRail {{
        background: transparent;
        border: none;
        border-right: 1px solid {_rgba(accent, 35)};
    }}
    """
