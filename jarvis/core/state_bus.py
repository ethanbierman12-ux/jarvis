"""Thread-safe Jarvis state fan-out with optional MQTT transport."""

from __future__ import annotations

import copy
import dataclasses
import json
import threading
import time
from typing import Any


def _json_safe(value: Any) -> Any:
    """Convert dataclasses and arbitrary telemetry objects to JSON-safe values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    elif hasattr(value, "_asdict"):
        value = value._asdict()
    elif not isinstance(value, (dict, list, tuple, str, int, float, bool, type(None))):
        try:
            value = vars(value)
        except TypeError:
            return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float):
        return round(value, 4)
    return value


class StateBus:
    """Mirror selected UI events into a snapshot and retained MQTT topics.

    UI callbacks remain authoritative. MQTT is an additive, best-effort
    transport, while :meth:`snapshot` powers the authenticated HTTP fallback.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        host: str = "127.0.0.1",
        port: int = 1883,
        username: str = "",
        password: str = "",
        client_id: str = "jarvis-hud",
        topic_prefix: str = "jarvis",
        mic_publish_hz: float = 10.0,
    ) -> None:
        self.enabled = bool(enabled)
        self.host = host or "127.0.0.1"
        self.port = int(port or 1883)
        self.username = username or ""
        self.password = password or ""
        self.client_id = client_id or "jarvis-hud"
        self.topic_prefix = (topic_prefix or "jarvis").strip().strip("/")
        self.mic_publish_interval = 1.0 / max(1.0, float(mic_publish_hz or 10.0))

        self._lock = threading.RLock()
        self._client: Any | None = None
        self._connected = False
        self._started = False
        self._last_error = ""
        self._last_mic_publish = 0.0
        self._state: dict[str, Any] = {
            "seq": 0,
            "ts": time.time(),
            "reactor": "idle",
            "mic": 0.0,
            "speaking": False,
            "listening": False,
            "fetching": False,
            "telemetry": {},
            "stats": {},
            "last_heard": "",
            "last_spoken": "",
        }

    def start(self) -> None:
        """Start the MQTT network loop without blocking Jarvis boot."""
        with self._lock:
            if self._started:
                return
            self._started = True
        if not self.enabled:
            return
        client = None
        try:
            import paho.mqtt.client as mqtt

            try:
                client = mqtt.Client(
                    mqtt.CallbackAPIVersion.VERSION2,
                    client_id=self.client_id,
                    protocol=mqtt.MQTTv311,
                )
            except (AttributeError, TypeError):
                client = mqtt.Client(client_id=self.client_id, protocol=mqtt.MQTTv311)
            if self.username:
                client.username_pw_set(self.username, self.password or None)
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.reconnect_delay_set(min_delay=1, max_delay=30)
            self._client = client
            client.connect_async(self.host, self.port, keepalive=30)
            client.loop_start()
        except Exception as exc:
            if client is not None:
                try:
                    client.loop_stop()
                except Exception:
                    pass
            with self._lock:
                self._client = None
                self._started = False
            self._set_error(f"MQTT unavailable: {exc}")

    def stop(self) -> None:
        """Stop MQTT cleanly; safe to call when it never connected."""
        with self._lock:
            client, self._client = self._client, None
            self._connected = False
            self._started = False
        if client is None:
            return
        try:
            client.disconnect()
        except Exception:
            pass
        try:
            client.loop_stop()
        except Exception:
            pass

    def publish_ui_event(self, key: str, payload: Any) -> None:
        """Update the shared snapshot and fan selected events to MQTT."""
        now = time.time()
        value = _json_safe(payload)
        field = {
            "reactor_activity": "reactor",
            "mic_level": "mic",
            "speaking": "speaking",
            "listening": "listening",
            "fetching": "fetching",
            "telemetry": "telemetry",
            "stats": "stats",
            "heard": "last_heard",
            "speak": "last_spoken",
            "speak_ui": "last_spoken",
        }.get(key)
        if field is None:
            return

        if field == "mic":
            try:
                value = max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                value = 0.0
        elif field in ("speaking", "listening", "fetching"):
            value = bool(value)
        elif field in ("last_heard", "last_spoken"):
            value = str(value or "")[:500]

        with self._lock:
            self._state[field] = value
            self._state["seq"] = int(self._state["seq"]) + 1
            self._state["ts"] = now
            seq = self._state["seq"]

        topic = {
            "reactor": "reactor",
            "mic": "mic",
            "speaking": "speak",
        }.get(field)
        if field == "mic":
            with self._lock:
                if now - self._last_mic_publish < self.mic_publish_interval:
                    return
                self._last_mic_publish = now
        if topic:
            body_key = {"reactor": "mode", "mic": "level", "speaking": "active"}[field]
            self._publish(topic, {body_key: value, "seq": seq, "ts": now}, retain=True)
        self._publish("state", self._mqtt_snapshot(), retain=True)

    def snapshot(self, *, include_transport: bool = True) -> dict[str, Any]:
        """Return an isolated JSON-safe state snapshot."""
        with self._lock:
            state = copy.deepcopy(self._state)
            if include_transport:
                state["transport"] = {
                    "mqtt_enabled": self.enabled,
                    "mqtt_connected": self._connected,
                    "mqtt_host": self.host if self.enabled else "",
                    "mqtt_port": self.port if self.enabled else 0,
                    "topic_prefix": self.topic_prefix,
                    "last_error": self._last_error,
                    "http_fallback": True,
                }
        return state

    def status(self) -> str:
        with self._lock:
            if not self.enabled:
                return "State bus online via HTTP fallback; MQTT disabled."
            if self._connected:
                return (
                    f"State bus online — MQTT {self.host}:{self.port}/"
                    f"{self.topic_prefix} plus HTTP fallback."
                )
            detail = f" ({self._last_error})" if self._last_error else ""
            return f"State bus using HTTP fallback; MQTT disconnected{detail}."

    def _mqtt_snapshot(self) -> dict[str, Any]:
        """MQTT is local telemetry only; conversation text stays off the broker."""
        state = self.snapshot(include_transport=False)
        state.pop("last_heard", None)
        state.pop("last_spoken", None)
        return state

    def _publish(self, suffix: str, payload: dict[str, Any], *, retain: bool) -> None:
        with self._lock:
            client = self._client
            connected = self._connected
        if not client or not connected:
            return
        try:
            info = client.publish(
                f"{self.topic_prefix}/{suffix}",
                json.dumps(payload, separators=(",", ":"), sort_keys=True),
                qos=0,
                retain=retain,
            )
            rc = getattr(info, "rc", 0)
            if rc:
                self._set_error(f"publish rc={rc}")
        except Exception as exc:
            self._set_error(f"publish failed: {exc}")

    def _on_connect(self, _client, _userdata, _flags, reason_code=0, _properties=None) -> None:
        try:
            ok = int(reason_code) == 0
        except (TypeError, ValueError):
            ok = str(reason_code).lower() in ("0", "success")
        with self._lock:
            self._connected = ok
            self._last_error = "" if ok else f"connect rejected: {reason_code}"
        if ok:
            self._publish("state", self._mqtt_snapshot(), retain=True)

    def _on_disconnect(self, _client, _userdata, *args) -> None:
        # Callback API v1: (client, userdata, rc)
        # Callback API v2: (client, userdata, flags, reason_code, properties)
        reason_code = args[0] if len(args) == 1 else args[1] if len(args) >= 2 else 0
        with self._lock:
            self._connected = False
            if reason_code:
                self._last_error = f"disconnected: {reason_code}"

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._last_error = str(message)[:240]
            self._connected = False
        print(f"[state-bus] {message}")
