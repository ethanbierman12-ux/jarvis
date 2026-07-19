"""3D map mode — MapLibre GL pitched view with biz options + cinematic intro."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
)

from jarvis.config import DATA_DIR

MAP_HTML = DATA_DIR / "map_3d.html"


def _geocode(place: str) -> tuple[float, float] | None:
    try:
        url = (
            "https://nominatim.openstreetmap.org/search?"
            + urllib.parse.urlencode({"q": place, "format": "json", "limit": 1})
        )
        req = urllib.request.Request(
            url, headers={"User-Agent": "JarvisMapView/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None


def write_map_html(
    *,
    lat: float = 39.9526,
    lon: float = -75.1652,
    place: str = "Philadelphia",
    markers: list[dict[str, Any]] | None = None,
    pitch: float = 62,
    zoom: float = 14.2,
    animate_intro: bool = True,
    scanning: bool = False,
) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    marks = markers or []
    marks_json = json.dumps(marks)
    place_js = json.dumps(place)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Jarvis · 3D Map</title>
<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet"/>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<style>
  html, body, #map {{ margin:0; height:100%; width:100%; background:#02050a; }}
  .hud {{
    position:absolute; z-index:5; left:16px; top:14px;
    pointer-events:none; font-family: Bahnschrift, Segoe UI, sans-serif;
  }}
  .hud h1 {{
    margin:0; color:#00e8ff; letter-spacing:6px; font-size:14px; font-weight:800;
    text-shadow: 0 0 18px rgba(0,232,255,.45);
  }}
  .hud p {{ margin:6px 0 0; color:#8aa4b8; font-size:12px; letter-spacing:1px; }}
  #scan {{
    position:absolute; z-index:6; left:50%; top:18%; transform:translateX(-50%);
    font-family: Bahnschrift, Segoe UI, sans-serif; letter-spacing:4px;
    color:#00e8ff; font-size:13px; text-shadow:0 0 20px rgba(0,232,255,.5);
    opacity:0; transition:opacity .4s ease; pointer-events:none;
  }}
  #scan.on {{ opacity:1; animation: pulse 1.2s ease-in-out infinite; }}
  @keyframes pulse {{ 0%,100% {{ opacity:.55; }} 50% {{ opacity:1; }} }}
  .maplibregl-ctrl-attrib {{ font-size:10px; }}
  .maplibregl-popup-content {{
    background:#041018; color:#eaf6ff; border:1px solid rgba(0,232,255,.4);
    border-radius:0; font-family: Bahnschrift, Segoe UI, sans-serif; max-width:220px;
  }}
  .maplibregl-popup-tip {{ border-top-color:#041018 !important; }}
  .pin {{
    width:26px; height:26px; border-radius:50%;
    background:rgba(0,232,255,.15); border:2px solid #00e8ff;
    box-shadow:0 0 14px rgba(0,232,255,.7); color:#eaf6ff;
    font:700 11px Bahnschrift,sans-serif; display:grid; place-items:center;
    cursor:pointer;
  }}
  .pin.hot {{ background:#00e8ff; color:#041018; transform:scale(1.15); }}
</style>
</head>
<body>
<div class="hud">
  <h1>TACTICAL MAP · 3D</h1>
  <p id="place">{place}</p>
</div>
<div id="scan" class="{'on' if scanning else ''}">{'SCANNING SECTOR…' if scanning else ''}</div>
<div id="map"></div>
<script>
const center = [{lon}, {lat}];
const markers = {marks_json};
const placeName = {place_js};
const animateIntro = {str(animate_intro).lower()};
const startScanning = {str(scanning).lower()};
let markerObjs = [];

const map = new maplibregl.Map({{
  container: 'map',
  style: 'https://tiles.openfreemap.org/styles/dark',
  center: center,
  zoom: animateIntro ? 3.2 : {zoom},
  pitch: animateIntro ? 0 : {pitch},
  bearing: animateIntro ? 0 : -18,
  antialias: true,
  attributionControl: true
}});
map.addControl(new maplibregl.NavigationControl({{visualizePitch:true}}), 'top-right');

function setScan(on, text) {{
  const el = document.getElementById('scan');
  if (!el) return;
  el.textContent = text || 'SCANNING SECTOR…';
  el.classList.toggle('on', !!on);
}}

function clearMarkers() {{
  markerObjs.forEach(m => m.remove());
  markerObjs = [];
}}

function addMarkers(list) {{
  clearMarkers();
  (list || []).forEach((m, i) => {{
    if (m.lon == null || m.lat == null) return;
    const el = document.createElement('div');
    el.className = 'pin';
    el.textContent = String(m.index || (i + 1));
    el.title = m.name || ('Option ' + (i + 1));
    el.onclick = () => {{
      document.querySelectorAll('.pin').forEach(p => p.classList.remove('hot'));
      el.classList.add('hot');
      map.flyTo({{
        center: [m.lon, m.lat],
        zoom: 15.2,
        pitch: {pitch},
        bearing: map.getBearing(),
        essential: true,
        duration: 1400
      }});
    }};
    const mk = new maplibregl.Marker({{element: el}})
      .setLngLat([m.lon, m.lat])
      .setPopup(new maplibregl.Popup({{offset: 16}}).setHTML(
        '<strong>' + (m.index || (i+1)) + '. ' + (m.name || ('Point ' + (i+1))) + '</strong><br/>' +
        '<span style="color:#8aa4b8">' + (m.address || m.category || '') + '</span>'
      ))
      .addTo(map);
    markerObjs.push(mk);
  }});
}}

map.on('load', () => {{
  try {{
    map.setFog({{
      color: 'rgb(2,8,16)',
      'high-color': 'rgb(0,40,60)',
      'horizon-blend': 0.08,
      'space-color': 'rgb(1,4,10)',
      'star-intensity': 0.15
    }});
  }} catch (e) {{}}

  const layers = map.getStyle().layers || [];
  const labelLayerId = layers.find(l => l.type === 'symbol' && l.layout && l.layout['text-field']);
  if (!map.getLayer('jarvis-3d-buildings')) {{
    try {{
      map.addLayer({{
        id: 'jarvis-3d-buildings',
        source: 'openmaptiles',
        'source-layer': 'building',
        type: 'fill-extrusion',
        minzoom: 13,
        paint: {{
          'fill-extrusion-color': '#0a3040',
          'fill-extrusion-height': ['coalesce', ['get', 'render_height'], ['get', 'height'], 12],
          'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
          'fill-extrusion-opacity': 0.82
        }}
      }}, labelLayerId && labelLayerId.id);
    }} catch (e) {{}}
  }}

  if (animateIntro) {{
    setScan(true, startScanning ? 'SCANNING SECTOR…' : 'ACQUIRING TARGET…');
    map.flyTo({{
      center: center,
      zoom: {zoom},
      pitch: {pitch},
      bearing: -18,
      essential: true,
      duration: 2800
    }});
    map.once('moveend', () => {{
      addMarkers(markers);
      if (!startScanning) setScan(false);
      // Slow cinematic orbit after settle
      let bearing = map.getBearing();
      function orbit() {{
        bearing = (bearing + 0.035) % 360;
        map.setBearing(bearing);
        requestAnimationFrame(orbit);
      }}
      requestAnimationFrame(orbit);
    }});
  }} else {{
    addMarkers(markers);
    let bearing = map.getBearing();
    function orbit() {{
      bearing = (bearing + 0.035) % 360;
      map.setBearing(bearing);
      requestAnimationFrame(orbit);
    }}
    requestAnimationFrame(orbit);
  }}
}});

window.jarvisFlyTo = function(lon, lat, place, zoom) {{
  document.getElementById('place').textContent = place || 'Target';
  map.flyTo({{
    center: [lon, lat],
    zoom: zoom || 14.5,
    pitch: {pitch},
    bearing: -12,
    essential: true,
    duration: 2200
  }});
}};

window.jarvisSetMarkers = function(list, scanning) {{
  addMarkers(list || []);
  setScan(!!scanning, scanning ? 'SCANNING SECTOR…' : '');
  if ((list || []).length) {{
    const bounds = new maplibregl.LngLatBounds();
    list.forEach(m => {{
      if (m.lon != null && m.lat != null) bounds.extend([m.lon, m.lat]);
    }});
    if (!bounds.isEmpty()) {{
      map.fitBounds(bounds, {{ padding: 80, pitch: {pitch}, duration: 1600, maxZoom: 15 }});
    }}
  }}
}};

window.jarvisFocusIndex = function(idx) {{
  const m = (markers || []).find(x => (x.index || 0) === idx) ||
            (markerObjs[idx - 1] && null);
  const list = window._jarvisMarks || markers;
  const hit = (list || []).find(x => Number(x.index) === Number(idx));
  if (!hit || hit.lon == null) return;
  document.querySelectorAll('.pin').forEach((p, i) => {{
    p.classList.toggle('hot', String(p.textContent) === String(idx));
  }});
  map.flyTo({{
    center: [hit.lon, hit.lat],
    zoom: 15.4,
    pitch: {pitch},
    essential: true,
    duration: 1200
  }});
}};

window._jarvisMarks = markers;
</script>
</body>
</html>
"""
    MAP_HTML.write_text(html, encoding="utf-8")
    return MAP_HTML


class MapView(QFrame):
    closed = pyqtSignal()
    option_selected = pyqtSignal(int)  # 1-based index
    build_requested = pyqtSignal(int)  # 1-based index

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self._city = "Philadelphia"
        self._web = None
        self._options: list[dict[str, Any]] = []
        self._markers: list[dict[str, Any]] = []

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Options rail ────────────────────────────────────────
        self.options_panel = QFrame()
        self.options_panel.setObjectName("GlassPanel")
        self.options_panel.setFixedWidth(280)
        self.options_panel.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(2,10,18,240);"
            " border-right: 1px solid rgba(0,232,255,90); }"
            "QListWidget { background: transparent; border: none; color:#d8ecf8;"
            " font-family: Consolas, monospace; font-size: 12px; outline: none; }"
            "QListWidget::item { padding: 10px 8px; border-bottom: 1px solid rgba(0,232,255,40); }"
            "QListWidget::item:selected { background: rgba(0,232,255,35); color:#00e8ff; }"
        )
        op = QVBoxLayout(self.options_panel)
        op.setContentsMargins(10, 10, 10, 10)
        op.setSpacing(8)
        self.options_title = QLabel("OPTIONS")
        self.options_title.setObjectName("SectionTitle")
        self.options_status = QLabel("Say find biz to scan…")
        self.options_status.setObjectName("Dim")
        self.options_status.setWordWrap(True)
        self.options_list = QListWidget()
        self.options_list.currentRowChanged.connect(self._on_row)
        self.build_btn = QPushButton("BUILD SITE FOR #")
        self.build_btn.setObjectName("GhostBtn")
        self.build_btn.setMinimumHeight(34)
        self.build_btn.setEnabled(False)
        self.build_btn.clicked.connect(self._on_build)
        op.addWidget(self.options_title)
        op.addWidget(self.options_status)
        op.addWidget(self.options_list, 1)
        op.addWidget(self.build_btn)
        root.addWidget(self.options_panel)

        # ── Map column ──────────────────────────────────────────
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        map_col = QWidget()
        map_col.setLayout(col)
        root.addWidget(map_col, 1)

        bar = QHBoxLayout()
        bar.setContentsMargins(12, 8, 12, 8)
        title = QLabel("TACTICAL MAP · 3D VIEW")
        title.setObjectName("SectionTitle")
        self.place_lab = QLabel("Standing by…")
        self.place_lab.setObjectName("Dim")
        close = QPushButton("CLOSE MAP")
        close.setObjectName("GhostBtn")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self._close)
        bar.addWidget(title)
        bar.addSpacing(12)
        bar.addWidget(self.place_lab, 1)
        bar.addWidget(close)
        bar_w = QWidget()
        bar_w.setLayout(bar)
        bar_w.setFixedHeight(48)
        col.addWidget(bar_w)

        self._host = QWidget()
        self._host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._host_lay = QVBoxLayout(self._host)
        self._host_lay.setContentsMargins(0, 0, 0, 0)
        col.addWidget(self._host, 1)

        self._fallback = QLabel(
            "Loading 3D map engine…\nIf this stays blank, check network for map tiles."
        )
        self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback.setStyleSheet(
            "color:#8aa4b8; font-size:14px; background:#02050a; padding:40px;"
        )
        self._host_lay.addWidget(self._fallback)

        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings

            self._web = QWebEngineView(self._host)
            settings = self._web.settings()
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptEnabled, True
            )
            self._host_lay.addWidget(self._web, 1)
            self._fallback.hide()
        except Exception as e:
            self._fallback.setText(
                f"3D map needs PyQt6-WebEngine.\n{e}\n"
                "Run: pip install PyQt6-WebEngine"
            )

    def open_map(
        self,
        *,
        city: str = "Philadelphia",
        place: str | None = None,
        markers: list[dict[str, Any]] | None = None,
        scanning: bool = False,
        query: str = "",
        options: list[dict[str, Any]] | None = None,
        animate: bool = True,
    ) -> str:
        target = (place or city or "Philadelphia").strip()
        self._city = city
        coords = _geocode(target) or _geocode(city)
        if not coords:
            lat, lon = 39.9526, -75.1652
            target = target or "Philadelphia"
        else:
            lat, lon = coords

        marks = self._normalize_markers(markers or [])
        self._markers = marks
        path = write_map_html(
            lat=lat,
            lon=lon,
            place=target,
            markers=marks,
            pitch=62,
            zoom=14.3,
            animate_intro=animate,
            scanning=scanning,
        )
        self.place_lab.setText(target.upper())
        if scanning:
            self.options_status.setText(
                f"Scanning for “{query or 'businesses'}”…"
            )
            self.options_list.clear()
            self.build_btn.setEnabled(False)
        if options is not None:
            self.set_options(options, query=query)
        self.show()

        if self._web is not None:
            self._web.load(QUrl.fromLocalFile(str(path.resolve())))
            verb = "scanning" if scanning else "focused on"
            return f"3D map online — {verb} {target}."

        try:
            from jarvis.core.displays import displays

            displays.open_url_on(path.resolve().as_uri(), "secondary")
            return f"Opened 3D map for {target} on your other monitor."
        except Exception:
            return f"Map HTML saved at {path}."

    def set_scanning(self, on: bool, query: str = "") -> None:
        if on:
            self.options_status.setText(f"Scanning for “{query or 'businesses'}”…")
            self.options_list.clear()
            self.build_btn.setEnabled(False)
        if self._web is not None:
            js = (
                f"if (window.jarvisSetMarkers) "
                f"jarvisSetMarkers({json.dumps(self._markers)}, {str(on).lower()});"
            )
            try:
                self._web.page().runJavaScript(js)
            except Exception:
                pass

    def set_options(
        self, options: list[dict[str, Any]], *, query: str = ""
    ) -> None:
        self._options = list(options or [])
        self.options_list.clear()
        if not self._options:
            self.options_status.setText("No options yet.")
            self.build_btn.setEnabled(False)
            return
        self.options_title.setText(f"OPTIONS · {len(self._options)}")
        self.options_status.setText(
            f"Pick one — or say build a website for number 1"
            + (f" · {query}" if query else "")
        )
        for opt in self._options:
            idx = int(opt.get("index") or 0)
            name = opt.get("name") or "Unknown"
            addr = opt.get("address") or opt.get("category") or ""
            site = " · has site" if opt.get("website") else " · no site"
            item = QListWidgetItem(f"{idx}. {name}\n   {addr}{site}")
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.options_list.addItem(item)
        self.build_btn.setEnabled(True)
        self.build_btn.setText("BUILD SITE FOR #1")
        self.options_list.setCurrentRow(0)

        # Push markers into live map if already loaded
        marks = self._normalize_markers(
            [
                {
                    "index": o.get("index"),
                    "name": o.get("name"),
                    "lat": o.get("lat"),
                    "lon": o.get("lon"),
                    "address": o.get("address"),
                    "category": o.get("category"),
                }
                for o in self._options
            ]
        )
        self._markers = marks
        if self._web is not None and marks:
            js = (
                f"window._jarvisMarks = {json.dumps(marks)};"
                f"if (window.jarvisSetMarkers) jarvisSetMarkers({json.dumps(marks)}, false);"
            )
            try:
                self._web.page().runJavaScript(js)
            except Exception:
                pass

    def fly_to(self, place: str) -> str:
        coords = _geocode(place)
        if not coords:
            return f"Could not locate {place}."
        lat, lon = coords
        self.place_lab.setText(place.upper())
        if self._web is not None:
            js = (
                f"if (window.jarvisFlyTo) jarvisFlyTo({lon}, {lat}, "
                f"{json.dumps(place)}, 14.5);"
            )
            self._web.page().runJavaScript(js)
            return f"Flying to {place}."
        return f"Located {place}."

    def focus_option(self, index: int) -> None:
        if self._web is not None:
            js = f"if (window.jarvisFocusIndex) jarvisFocusIndex({int(index)});"
            try:
                self._web.page().runJavaScript(js)
            except Exception:
                pass
        # Sync list selection
        for i in range(self.options_list.count()):
            item = self.options_list.item(i)
            if item and int(item.data(Qt.ItemDataRole.UserRole) or 0) == index:
                self.options_list.setCurrentRow(i)
                break

    def _normalize_markers(
        self, markers: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        out = []
        for i, m in enumerate(markers, 1):
            if m.get("lat") is None or m.get("lon") is None:
                continue
            out.append(
                {
                    "index": int(m.get("index") or i),
                    "name": m.get("name") or f"Point {i}",
                    "lat": float(m["lat"]),
                    "lon": float(m["lon"]),
                    "address": m.get("address") or "",
                    "category": m.get("category") or "",
                }
            )
        return out

    def _on_row(self, row: int) -> None:
        if row < 0:
            return
        item = self.options_list.item(row)
        if not item:
            return
        idx = int(item.data(Qt.ItemDataRole.UserRole) or (row + 1))
        self.build_btn.setText(f"BUILD SITE FOR #{idx}")
        self.focus_option(idx)
        self.option_selected.emit(idx)

    def _on_build(self) -> None:
        row = self.options_list.currentRow()
        if row < 0:
            return
        item = self.options_list.item(row)
        idx = int(item.data(Qt.ItemDataRole.UserRole) or (row + 1))
        self.build_requested.emit(idx)

    def _close(self) -> None:
        self.hide()
        self.closed.emit()
