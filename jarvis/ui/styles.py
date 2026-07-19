"""Iron Man HUD stylesheet — weather-mood adaptive, premium glass chrome."""

from __future__ import annotations

from jarvis.config import Theme

# Prefer cinematic geometric faces when installed; fall back cleanly on stock Windows.
UI_SANS = '"Bahnschrift", "Segoe UI Variable Display", "Segoe UI"'
UI_MONO = '"Cascadia Mono", "Consolas", "Courier New"'


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


def mood_palette(mood: str) -> dict[str, str]:
    if mood == "storm":
        return {
            "accent": "#9eb7ff",
            "accent2": "#6b7cff",
            "void": "#02040a",
            "grad0": "#010208",
            "grad1": "#0a1028",
            "grad2": "#050814",
            "panel": "rgba(8, 12, 28, 200)",
            "panel2": "rgba(4, 8, 22, 230)",
            "border": "rgba(120, 150, 255, 85)",
            "dim": "#6a7a9a",
            "white": "#dce6ff",
            "label": "STORM",
            "glow": "rgba(110, 140, 255, 55)",
        }
    if mood == "rain":
        return {
            "accent": "#6ec8ff",
            "accent2": "#3a8fd4",
            "void": "#040812",
            "grad0": "#03060e",
            "grad1": "#0a1524",
            "grad2": "#061018",
            "panel": "rgba(6, 14, 28, 195)",
            "panel2": "rgba(3, 10, 22, 230)",
            "border": "rgba(80, 180, 255, 80)",
            "dim": "#5a7a90",
            "white": "#d8eefc",
            "label": "RAIN",
            "glow": "rgba(80, 180, 255, 50)",
        }
    if mood == "cloudy":
        return {
            "accent": "#8aa4b8",
            "accent2": "#5a7288",
            "void": "#07090c",
            "grad0": "#05070a",
            "grad1": "#0c1218",
            "grad2": "#080b10",
            "panel": "rgba(10, 14, 18, 190)",
            "panel2": "rgba(6, 10, 14, 230)",
            "border": "rgba(140, 160, 180, 65)",
            "dim": "#6a7888",
            "white": "#e0e8f0",
            "label": "OVERCAST",
            "glow": "rgba(140, 160, 180, 40)",
        }
    return {
        "accent": "#00e8ff",
        "accent2": "#007a99",
        "void": "#02050a",
        "grad0": "#02050a",
        "grad1": "#061018",
        "grad2": "#030810",
        "panel": "rgba(3, 12, 22, 200)",
        "panel2": "rgba(1, 8, 16, 235)",
        "border": "rgba(0, 232, 255, 55)",
        "dim": "#5a7388",
        "white": "#eaf6ff",
        "label": "CLEAR",
        "glow": "rgba(0, 232, 255, 45)",
    }


def stylesheet(theme: Theme, mood: str = "clear") -> str:
    p = mood_palette(mood)
    accent = p["accent"]
    return f"""
    QMainWindow, QWidget#Root {{
        background-color: {p["void"]};
        color: {p["white"]};
        font-family: {UI_SANS};
    }}
    QWidget#Root {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p["grad0"]}, stop:0.45 {p["grad1"]}, stop:1 {p["grad2"]});
    }}
    QLabel {{ background: transparent; color: {p["white"]}; }}
    QLabel#Brand {{
        color: {accent};
        font-size: 26px;
        font-weight: 700;
        letter-spacing: 10px;
        padding-bottom: 2px;
    }}
    QLabel#BrandSub {{
        color: {p["dim"]};
        font-size: 9px;
        font-weight: 600;
        letter-spacing: 3px;
    }}
    QLabel#SectionTitle {{
        color: {accent};
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 3px;
        padding-top: 2px;
    }}
    QLabel#Dim {{ color: {p["dim"]}; font-size: 11px; }}
    QLabel#StatusPill {{
        color: {accent};
        background: {p["glow"]};
        border: 1px solid {p["border"]};
        padding: 5px 12px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.4px;
    }}
    QLabel#MicPill {{
        color: {p["dim"]};
        border: 1px solid {p["border"]};
        padding: 5px 10px;
        font-size: 10px;
        letter-spacing: 1.2px;
    }}
    QFrame#GlassPanel, QWidget#GlassPanel {{
        background-color: {p["panel"]};
        border: 1px solid {p["border"]};
        border-radius: 0px;
    }}
    QFrame#HeaderBar, QWidget#HeaderBar {{
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 {p["panel2"]}, stop:1 {p["void"]});
        border: none;
        border-bottom: 1px solid {p["border"]};
        padding-bottom: 4px;
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget {{
        background: transparent;
    }}
    QScrollArea > QWidget > QWidget {{
        background-color: {p["panel"]};
    }}
    QFrame#KpiCard {{
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 rgba(0, 28, 42, 160), stop:1 rgba(0, 10, 18, 190));
        border: 1px solid {p["border"]};
        border-left: 2px solid {accent};
    }}
    QPushButton#StartBtn {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 rgba(0, 200, 255, 70), stop:1 rgba(0, 80, 120, 45));
        border: 1px solid {accent};
        color: #f0ffff;
        padding: 9px 22px;
        font-size: 13px;
        font-weight: 800;
        letter-spacing: 4px;
        min-height: 36px;
    }}
    QPushButton#StartBtn:hover {{
        background: rgba(0, 220, 255, 110);
        color: #ffffff;
    }}
    QPushButton#StartBtn:pressed {{
        background: rgba(0, 240, 255, 160);
    }}
    QPushButton#GhostBtn {{
        background: rgba(0, 36, 52, 140);
        border: 1px solid {p["border"]};
        color: {accent};
        padding: 5px 8px;
        font-size: 10px;
        font-weight: 650;
        letter-spacing: 0.6px;
        min-height: 30px;
    }}
    QPushButton#GhostBtn:hover {{
        background: {p["glow"]};
        border-color: {accent};
        color: #f2ffff;
    }}
    QPushButton#GhostBtn:pressed {{
        background: rgba(0, 200, 255, 100);
    }}
    QPushButton#MediaBtn {{
        background: rgba(0, 28, 42, 120);
        border: 1px solid {p["border"]};
        color: {accent};
        padding: 6px 8px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1px;
        min-height: 30px;
    }}
    QPushButton#MediaBtn:hover {{
        background: {p["glow"]};
        border-color: {accent};
        color: #ffffff;
    }}
    QPushButton#MediaBtn:pressed {{
        background: rgba(0, 220, 255, 120);
    }}
    QPushButton#DangerBtn {{
        background: rgba(48, 14, 8, 150);
        border: 1px solid rgba(255, 107, 53, 110);
        color: #ffb089;
        padding: 5px 8px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.6px;
        min-height: 30px;
    }}
    QPushButton#DangerBtn:hover {{
        background: rgba(255, 90, 40, 50);
        border-color: #ff6b35;
        color: #ffe8dc;
    }}
    QPushButton#DangerBtn:pressed {{
        background: rgba(255, 100, 50, 100);
    }}
    QLineEdit#CmdInput {{
        background: {p["panel2"]};
        border: 1px solid {p["border"]};
        border-left: 3px solid {accent};
        color: {p["white"]};
        padding: 11px 14px;
        font-family: {UI_MONO};
        font-size: 12px;
        selection-background-color: {accent};
        selection-color: #001018;
    }}
    QLineEdit#CmdInput:focus {{
        border: 1px solid {accent};
        border-left: 3px solid {accent};
        background: rgba(0, 16, 28, 240);
    }}
    QTextEdit#Log {{
        background: {p["panel2"]};
        border: 1px solid {p["border"]};
        color: {p["dim"]};
        font-family: {UI_MONO};
        font-size: 10px;
        padding: 8px;
        selection-background-color: {accent};
        selection-color: #001018;
    }}
    QProgressBar {{
        background: rgba(0,0,0,130);
        border: 1px solid {p["border"]};
        max-height: 6px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 {accent}, stop:1 {p["accent2"]});
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {p["border"]};
        min-height: 28px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    """
