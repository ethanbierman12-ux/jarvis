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


def _geocode_detail(place: str) -> dict[str, Any] | None:
    """Nominatim lookup with type + zoom hint for city/country framing."""
    q = (place or "").strip()
    if not q:
        return None
    return _nominatim_search(q)


def _nominatim_search(q: str) -> dict[str, Any] | None:
    try:
        url = (
            "https://nominatim.openstreetmap.org/search?"
            + urllib.parse.urlencode(
                {
                    "q": q,
                    "format": "json",
                    "limit": 1,
                    "addressdetails": 1,
                    "namedetails": 1,
                }
            )
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "JarvisMapView/1.0",
                "Accept-Language": "en",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data:
            return None
        row = data[0]
        lat = float(row["lat"])
        lon = float(row["lon"])
        cls = (row.get("class") or "").lower()
        typ = (row.get("type") or "").lower()
        addr = row.get("address") or {}
        nd = row.get("namedetails") or {}
        en_name = (nd.get("name:en") or nd.get("name") or "").strip()
        display = (row.get("display_name") or q).split(",")
        parts = [p.strip() for p in display if p.strip()]
        if en_name:
            # Keep one geographic qualifier when useful (e.g. Tokyo, Japan)
            qual = ""
            if addr.get("country") and addr.get("country").lower() not in en_name.lower():
                # For countries alone, skip qualifier
                if not (
                    cls == "boundary"
                    and typ == "administrative"
                    and addr.get("country")
                    and not any(
                        addr.get(k)
                        for k in ("city", "town", "state", "province", "region", "county")
                    )
                ):
                    if addr.get("country"):
                        qual = f", {addr['country']}"
            short = f"{en_name}{qual}"
        else:
            short = ", ".join(parts[:3]) if parts else q
        zoom = _zoom_for_place(cls, typ, addr)
        kind = _kind_label(cls, typ, addr)
        # Prefecture/metro named like the query (Tokyo) → city frame; US states stay region
        ql = q.lower()
        prov = (addr.get("province") or "").lower()
        state = (addr.get("state") or "").lower()
        city_l = (
            addr.get("city")
            or addr.get("town")
            or addr.get("municipality")
            or ""
        ).lower()
        if city_l == ql or (prov == ql and prov and prov != state):
            kind = "city"
            zoom = max(float(zoom), 10.8)
        elif state == ql and not city_l:
            kind = "region"
            zoom = max(float(zoom), 6.8)
        return {
            "lat": lat,
            "lon": lon,
            "query": q,
            "name": short or q,
            "kind": kind,
            "zoom": zoom,
            "class": cls,
            "type": typ,
            "country": (addr.get("country") or "").strip(),
            "state": (
                addr.get("state") or addr.get("region") or addr.get("province") or ""
            ).strip(),
            "city": (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("municipality")
                or ""
            ).strip(),
        }
    except Exception:
        return None


def _zoom_for_place(cls: str, typ: str, addr: dict[str, Any] | None = None) -> float:
    """Country → wide, city → street-level-ish pitched view."""
    typ = (typ or "").lower()
    cls = (cls or "").lower()
    addr = addr or {}
    has_settlement = any(
        addr.get(k) for k in ("city", "town", "village", "municipality", "suburb")
    )
    has_state = bool(
        addr.get("state") or addr.get("region") or addr.get("province") or addr.get("county")
    )
    has_country = bool(addr.get("country"))

    if typ in ("country", "nation"):
        return 4.6
    if cls == "boundary" and typ == "administrative":
        if has_country and not has_settlement and not has_state:
            return 4.6
        if has_state and not has_settlement:
            # Prefecture / state frame (Tokyo-as-province, California, etc.)
            return 8.2
    if typ in ("state", "province", "region", "county"):
        return 7.4
    if typ in ("city", "town", "municipality", "borough"):
        return 11.4
    if typ in ("village", "hamlet", "suburb", "neighbourhood", "neighborhood"):
        return 13.2
    if cls == "place":
        if typ == "country":
            return 4.6
        if typ in ("state", "region", "province"):
            return 7.4
        if typ in ("city", "town"):
            return 11.4
    if has_settlement:
        return 11.6
    if has_state and not has_settlement:
        return 8.2
    if has_country and not has_settlement and not has_state:
        return 4.6
    return 13.8


def _kind_label(cls: str, typ: str, addr: dict[str, Any] | None = None) -> str:
    typ = (typ or "").lower()
    cls = (cls or "").lower()
    addr = addr or {}
    has_settlement = any(
        addr.get(k) for k in ("city", "town", "village", "municipality", "suburb")
    )
    has_state = bool(addr.get("state") or addr.get("region") or addr.get("province"))
    if typ in ("country", "nation") or (
        cls == "boundary"
        and typ == "administrative"
        and addr.get("country")
        and not has_settlement
        and not has_state
    ):
        return "country"
    if typ in ("state", "province", "region") or (
        has_state and not has_settlement and typ == "administrative"
    ):
        return "region"
    if typ in ("city", "town", "municipality", "borough"):
        return "city"
    if typ in ("village", "hamlet", "suburb", "neighbourhood", "neighborhood"):
        return "district"
    if has_settlement:
        return "city"
    if typ:
        return typ.replace("_", " ")
    return "location"


def _brief_for(hit: dict[str, Any]) -> str:
    """One tight spoken line about the target."""
    name = hit.get("name") or hit.get("query") or "target"
    kind = hit.get("kind") or "location"
    lat = float(hit["lat"])
    lon = float(hit["lon"])
    ns = "north" if lat >= 0 else "south"
    ew = "east" if lon >= 0 else "west"
    coords = f"{abs(lat):.1f} {ns}, {abs(lon):.1f} {ew}"
    country = hit.get("country") or ""
    extra = ""
    if country and country.lower() not in name.lower() and kind != "country":
        extra = f", {country}"
    return f"{name}{extra} - {kind}. {coords}."


def _geocode(place: str) -> tuple[float, float] | None:
    hit = _geocode_detail(place)
    if not hit:
        return None
    return float(hit["lat"]), float(hit["lon"])


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
  zoom: animateIntro ? 2.15 : {zoom},
  pitch: animateIntro ? 0 : {pitch},
  bearing: animateIntro ? 0 : -18,
  antialias: true,
  attributionControl: true
}});
window.map = map;
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
      speed: 0.55,
      curve: 1.7,
      essential: true,
      duration: 3200
    }});
    map.once('moveend', () => {{
      addMarkers(markers);
      if (!startScanning) setScan(false);
      window._jarvisOrbiting = true;
      let bearing = map.getBearing();
      function orbit() {{
        if (!window._jarvisOrbiting) return;
        bearing = (bearing + 0.035) % 360;
        try {{ map.setBearing(bearing); }} catch (e) {{}}
        window._jarvisOrbitRAF = requestAnimationFrame(orbit);
      }}
      window._jarvisOrbitRAF = requestAnimationFrame(orbit);
    }});
  }} else {{
    addMarkers(markers);
    window._jarvisOrbiting = true;
    let bearing = map.getBearing();
    function orbit() {{
      if (!window._jarvisOrbiting) return;
      bearing = (bearing + 0.035) % 360;
      try {{ map.setBearing(bearing); }} catch (e) {{}}
      window._jarvisOrbitRAF = requestAnimationFrame(orbit);
    }}
    window._jarvisOrbitRAF = requestAnimationFrame(orbit);
  }}
  window._jarvisMapReady = true;
}});

window._jarvisOrbiting = false;
window._jarvisOrbitRAF = null;
window._jarvisFlying = false;
window._jarvisMapReady = false;

window.jarvisZoomBy = function(delta) {{
  try {{
    const m = window.map || map;
    if (!m) return;
    window._jarvisOrbiting = false;
    if (window._jarvisOrbitRAF) {{
      try {{ cancelAnimationFrame(window._jarvisOrbitRAF); }} catch (e) {{}}
      window._jarvisOrbitRAF = null;
    }}
    const d = Number(delta) || 0;
    const next = Math.max(1.2, Math.min(18.5, m.getZoom() + d));
    setScan(true, d >= 0 ? 'ZOOMING IN…' : 'PULLING BACK…');
    m.easeTo({{
      zoom: next,
      pitch: {pitch},
      duration: 1400,
      essential: true
    }});
    m.once('moveend', () => {{
      setScan(false);
      window._jarvisOrbiting = true;
      let bearing = m.getBearing();
      function orbit() {{
        if (!window._jarvisOrbiting) return;
        bearing = (bearing + 0.035) % 360;
        try {{ m.setBearing(bearing); }} catch (e) {{}}
        window._jarvisOrbitRAF = requestAnimationFrame(orbit);
      }}
      window._jarvisOrbitRAF = requestAnimationFrame(orbit);
    }});
  }} catch (e) {{}}
}};

window.jarvisFlyTo = function(lon, lat, place, zoom) {{
  const m = window.map || map;
  if (!m) return;
  const targetZoom = (zoom == null || zoom === undefined) ? 14.5 : Number(zoom);
  const el = document.getElementById('place');
  if (el) el.textContent = place || 'Target';
  setScan(true, 'ZOOMING IN…');
  window._jarvisOrbiting = false;
  window._jarvisFlying = true;
  if (window._jarvisOrbitRAF) {{
    try {{ cancelAnimationFrame(window._jarvisOrbitRAF); }} catch (e) {{}}
    window._jarvisOrbitRAF = null;
  }}

  const curZoom = m.getZoom();
  const curCenter = m.getCenter();
  // Pull back for a clear zoom-in read, then dive to target
  const pullBack = Math.max(2.4, Math.min(curZoom, targetZoom) - 3.2);

  function dive() {{
    m.flyTo({{
      center: [lon, lat],
      zoom: targetZoom,
      pitch: {pitch},
      bearing: -18,
      speed: 0.45,
      curve: 1.85,
      essential: true,
      duration: Math.max(2400, Math.min(4800, 900 + Math.abs(curZoom - targetZoom) * 420))
    }});
    m.once('moveend', () => {{
      window._jarvisFlying = false;
      setScan(false);
      window._jarvisOrbiting = true;
      let bearing = m.getBearing();
      function orbit() {{
        if (!window._jarvisOrbiting) return;
        bearing = (bearing + 0.035) % 360;
        try {{ m.setBearing(bearing); }} catch (e) {{}}
        window._jarvisOrbitRAF = requestAnimationFrame(orbit);
      }}
      window._jarvisOrbitRAF = requestAnimationFrame(orbit);
    }});
  }}

  // Stage 1: ease toward target while pulling altitude for drama
  m.easeTo({{
    center: [
      curCenter.lng + (lon - curCenter.lng) * 0.35,
      curCenter.lat + (lat - curCenter.lat) * 0.35
    ],
    zoom: pullBack,
    pitch: Math.max(28, {pitch} - 20),
    bearing: m.getBearing() + 25,
    duration: 1100,
    essential: true
  }});
  m.once('moveend', dive);
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
        lat: float | None = None,
        lon: float | None = None,
        zoom: float | None = None,
        label: str | None = None,
        brief: str | None = None,
    ) -> str:
        target = (label or place or city or "Philadelphia").strip()
        self._city = city
        if lat is not None and lon is not None:
            zoom_lvl = float(zoom if zoom is not None else 11.4)
            brief_txt = (brief or "").strip()
        else:
            detail = _geocode_detail(target) or _geocode_detail(city)
            if not detail:
                lat, lon = 39.9526, -75.1652
                target = target or "Philadelphia"
                zoom_lvl = 14.3
                brief_txt = ""
            else:
                lat, lon = float(detail["lat"]), float(detail["lon"])
                target = str(detail.get("name") or target)
                zoom_lvl = float(zoom if zoom is not None else detail.get("zoom") or 14.3)
                brief_txt = brief or _brief_for(detail)

        marks = self._normalize_markers(markers or [])
        self._markers = marks
        path = write_map_html(
            lat=float(lat),
            lon=float(lon),
            place=target,
            markers=marks,
            pitch=62,
            zoom=zoom_lvl,
            animate_intro=animate,
            scanning=scanning,
        )
        self.place_lab.setText(target.upper())
        if brief_txt and not scanning:
            self.options_status.setText(brief_txt)
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

    def fly_to(
        self,
        place: str,
        *,
        lat: float | None = None,
        lon: float | None = None,
        zoom: float | None = None,
        label: str | None = None,
        brief: str | None = None,
    ) -> str:
        hit = None
        if lat is None or lon is None:
            hit = _geocode_detail(place)
            if not hit:
                return f"Could not locate {place}."
            lat = float(hit["lat"])
            lon = float(hit["lon"])
            zoom = float(hit.get("zoom") or 14.5)
            label = str(hit.get("name") or place)
            brief = _brief_for(hit)
        else:
            zoom = float(zoom if zoom is not None else 14.5)
            label = (label or place or "Target").strip()
            brief = (brief or f"{label}.").strip()

        self.place_lab.setText(label.upper())
        self.options_status.setText(brief)
        if self._web is not None:
            # Call page jarvisFlyTo (window.map exposed). Retry until engine ready.
            lab_js = json.dumps(label)
            js = f"""
(function tryFly(n) {{
  try {{
    if (window.jarvisFlyTo && (window.map || window._jarvisMapReady)) {{
      jarvisFlyTo({float(lon)}, {float(lat)}, {lab_js}, {float(zoom)});
      return;
    }}
  }} catch (e) {{}}
  if (n < 25) setTimeout(function() {{ tryFly(n + 1); }}, 200);
}})(0);
"""
            try:
                self._web.page().runJavaScript(js)
            except Exception:
                pass
            return f"Zooming to {label}. {brief}"
        return f"Located {label}. {brief}"

    def zoom_by(self, delta: float) -> str:
        """Relative cinematic zoom in (+) / out (−) on the live map."""
        d = float(delta or 0)
        if self._web is not None:
            js = f"""
(function tryZoom(n) {{
  try {{
    if (window.jarvisZoomBy && (window.map || window._jarvisMapReady)) {{
      jarvisZoomBy({d});
      return;
    }}
  }} catch (e) {{}}
  if (n < 25) setTimeout(function() {{ tryZoom(n + 1); }}, 200);
}})(0);
"""
            try:
                self._web.page().runJavaScript(js)
            except Exception:
                pass
            return "Zooming in." if d >= 0 else "Pulling back."
        return "Map engine offline."

    def lookup_brief(self, place: str) -> tuple[str, dict[str, Any] | None]:
        """Geocode + brief without flying (for brain when opening map cold)."""
        hit = _geocode_detail(place)
        if not hit:
            return f"Could not locate {place}.", None
        return _brief_for(hit), hit

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
