"""Iron Man HUD stylesheet — command-center glass, weather-mood adaptive."""

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
    # Command-center clear — deep navy + cyan (matches reference dashboard)
    return {
        "accent": "#00e5ff",
        "accent2": "#0090a8",
        "void": "#050a18",
        "grad0": "#030712",
        "grad1": "#071428",
        "grad2": "#050a18",
        "panel": "rgba(8, 16, 36, 210)",
        "panel2": "rgba(4, 10, 24, 240)",
        "border": "rgba(0, 229, 255, 70)",
        "dim": "#6a8aa0",
        "white": "#e8f4ff",
        "label": "CLEAR",
        "glow": "rgba(0, 229, 255, 55)",
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
        background: qlineargradient(x1:0, y1:0, x2:0.55, y2:1,
            stop:0 {p["grad0"]}, stop:0.5 {p["grad1"]}, stop:1 {p["grad2"]});
    }}
    QLabel {{ background: transparent; color: {p["white"]}; }}
    QLabel#Brand {{
        color: {accent};
        font-size: 24px;
        font-weight: 800;
        letter-spacing: 6px;
        padding-bottom: 0px;
    }}
    QLabel#BrandSub {{
        color: {p["dim"]};
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 4px;
        padding-top: 2px;
    }}
    QLabel#SectionTitle {{
        color: {accent};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 3px;
    }}
    QLabel#Dim {{ color: {p["dim"]}; font-size: 11px; }}
    QLabel#StatusPill {{
        color: #3dff9a;
        background: rgba(61, 255, 154, 22);
        border: 1px solid rgba(61, 255, 154, 90);
        border-radius: 11px;
        padding: 5px 12px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 2px;
    }}
    QLabel#MicPill {{
        color: {accent};
        background: rgba(0, 229, 255, 16);
        border: 1px solid {p["border"]};
        border-radius: 11px;
        padding: 5px 12px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 2px;
    }}
    QFrame#HeaderBar, QWidget#HeaderBar {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(0, 229, 255, 18), stop:0.4 rgba(6, 14, 28, 170),
            stop:1 rgba(4, 10, 22, 50));
        border: 1px solid {p["border"]};
        border-radius: 12px;
        padding: 4px 8px;
    }}
    QFrame#TalkBar {{
        background: rgba(4, 12, 28, 220);
        border: 1px solid {p["border"]};
        border-radius: 22px;
        padding: 4px 8px;
    }}
    QFrame#GlassPanel, QWidget#GlassPanel {{
        background-color: {p["panel"]};
        border: 1px solid {p["border"]};
        border-radius: 12px;
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
        border-radius: 10px;
    }}
    QFrame#KpiCard {{
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 rgba(0, 28, 48, 170), stop:1 rgba(0, 10, 22, 200));
        border: 1px solid {p["border"]};
        border-left: 3px solid {accent};
        border-radius: 8px;
    }}
    QPushButton#StartBtn {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 rgba(0, 220, 255, 90), stop:1 rgba(0, 90, 130, 55));
        border: 1px solid {accent};
        border-radius: 8px;
        color: #f0ffff;
        padding: 9px 22px;
        font-size: 12px;
        font-weight: 800;
        letter-spacing: 3px;
        min-height: 36px;
    }}
    QPushButton#StartBtn:hover {{
        background: rgba(0, 220, 255, 120);
        color: #ffffff;
    }}
    QPushButton#StartBtn:pressed {{
        background: rgba(0, 240, 255, 160);
    }}
    QPushButton#TalkBtn {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 rgba(0, 229, 255, 100), stop:1 rgba(0, 120, 160, 70));
        border: 1px solid {accent};
        border-radius: 18px;
        color: #041018;
        padding: 10px 28px;
        font-size: 13px;
        font-weight: 800;
        letter-spacing: 2px;
        min-height: 38px;
        min-width: 180px;
    }}
    QPushButton#TalkBtn:hover {{
        background: rgba(0, 240, 255, 180);
    }}
    QPushButton#TalkBtn:pressed {{
        background: rgba(0, 245, 255, 210);
    }}
    QPushButton#GhostBtn {{
        background: rgba(0, 24, 42, 130);
        border: 1px solid rgba(0, 229, 255, 45);
        border-radius: 6px;
        color: {accent};
        padding: 4px 8px;
        font-size: 10px;
        font-weight: 650;
        letter-spacing: 0.8px;
        min-height: 28px;
    }}
    QPushButton#GhostBtn:hover {{
        background: rgba(0, 229, 255, 28);
        border-color: {accent};
        color: #f2ffff;
    }}
    QPushButton#GhostBtn:pressed {{
        background: rgba(0, 200, 255, 90);
    }}
    QPushButton#MediaBtn {{
        background: rgba(0, 22, 40, 120);
        border: 1px solid rgba(0, 229, 255, 40);
        border-radius: 6px;
        color: {accent};
        padding: 5px 7px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1px;
        min-height: 28px;
    }}
    QPushButton#MediaBtn:hover {{
        background: rgba(0, 229, 255, 28);
        border-color: {accent};
        color: #ffffff;
    }}
    QPushButton#MediaBtn:pressed {{
        background: rgba(0, 220, 255, 100);
    }}
    QPushButton#DangerBtn {{
        background: rgba(40, 12, 8, 140);
        border: 1px solid rgba(255, 107, 53, 90);
        border-radius: 6px;
        color: #ffb089;
        padding: 4px 7px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.8px;
        min-height: 28px;
    }}
    QPushButton#DangerBtn:hover {{
        background: rgba(255, 90, 40, 45);
        border-color: #ff6b35;
        color: #ffe8dc;
    }}
    QPushButton#DangerBtn:pressed {{
        background: rgba(255, 100, 50, 90);
    }}
    QLineEdit#CmdInput {{
        background: rgba(2, 8, 20, 230);
        border: 1px solid {p["border"]};
        border-radius: 18px;
        color: {p["white"]};
        padding: 11px 16px;
        font-family: {UI_SANS};
        font-size: 13px;
        selection-background-color: {accent};
        selection-color: #001018;
    }}
    QLineEdit#CmdInput:focus {{
        border: 1px solid {accent};
        background: rgba(0, 229, 255, 14);
    }}
    QTextEdit#Log {{
        background: {p["panel2"]};
        border: 1px solid {p["border"]};
        border-left: 3px solid {accent};
        border-radius: 4px;
        color: #9ec8d8;
        font-family: {UI_MONO};
        font-size: 10px;
        padding: 8px 10px;
        selection-background-color: {accent};
        selection-color: #001018;
    }}
    QPushButton#QuickToggle {{
        background: rgba(4, 14, 28, 200);
        border: 1px solid {p["border"]};
        border-radius: 4px;
        color: {p["dim"]};
        font-family: {UI_MONO};
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 1px;
        padding: 8px 4px;
        min-height: 40px;
    }}
    QPushButton#QuickToggle:hover {{
        border-color: {accent};
        color: {p["white"]};
        background: rgba(0, 229, 255, 18);
    }}
    QPushButton#QuickToggle[on="true"] {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
            stop:0 rgba(0, 229, 255, 55), stop:1 rgba(0, 80, 110, 40));
        border: 1px solid {accent};
        color: {accent};
    }}
    QProgressBar {{
        background: rgba(0,0,0,130);
        border: 1px solid {p["border"]};
        border-radius: 3px;
        max-height: 6px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 {accent}, stop:1 {p["accent2"]});
        border-radius: 2px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {p["border"]};
        min-height: 28px;
        border-radius: 3px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    """
