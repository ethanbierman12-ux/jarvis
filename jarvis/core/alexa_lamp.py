"""Alexa / smart lamp control — HA, IFTTT, webhooks, Echo voice relay (best default)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable


class AlexaLamp:
    """
    Control a lamp that lives in the Alexa app.

    Best zero-setup path: voice relay — briefly play through room speakers so a
    nearby Echo hears “Alexa, turn on the Lamp”, then restore your headset.
    """

    def __init__(
        self,
        *,
        device_name: str = "Lamp",
        ha: Any = None,
        ha_entity: str = "light.lamp",
        ifttt_key: str = "",
        ifttt_on_event: str = "jarvis_lamp_on",
        ifttt_off_event: str = "jarvis_lamp_off",
        on_webhook: str = "",
        off_webhook: str = "",
        voice_relay: bool = True,
        audio: Any = None,
        say_wait: Callable[[str], None] | None = None,
        restore_output: str = "WG1",
    ) -> None:
        self.device_name = (device_name or "Lamp").strip() or "Lamp"
        self.ha = ha
        self.ha_entity = (ha_entity or "light.lamp").strip()
        self.ifttt_key = (ifttt_key or "").strip()
        self.ifttt_on_event = (ifttt_on_event or "jarvis_lamp_on").strip()
        self.ifttt_off_event = (ifttt_off_event or "jarvis_lamp_off").strip()
        self.on_webhook = (on_webhook or "").strip()
        self.off_webhook = (off_webhook or "").strip()
        self.voice_relay = bool(voice_relay)
        self.audio = audio
        self._say_wait = say_wait
        self.restore_output = (restore_output or "WG1").strip() or "WG1"
        self._on = False

    def status(self) -> str:
        paths = []
        if self.ha is not None and getattr(self.ha, "enabled", False) and self.ha_entity:
            paths.append(f"HA {self.ha_entity}")
        if self.ifttt_key:
            paths.append("IFTTT")
        if self.on_webhook or self.off_webhook:
            paths.append("webhook")
        if self.voice_relay:
            paths.append("Echo voice relay")
        if not paths:
            return f"Lamp “{self.device_name}” has no control path configured."
        state = "on" if self._on else "off (last commanded)"
        return f"Lamp “{self.device_name}” via {', '.join(paths)}. Last: {state}."

    def turn_on(self) -> str:
        return self._set(True)

    def turn_off(self) -> str:
        return self._set(False)

    def toggle(self) -> str:
        return self._set(not self._on)

    def brightness(self, percent: int) -> str:
        pct = max(0, min(100, int(percent)))
        if pct <= 0:
            return self.turn_off()
        errors: list[str] = []
        if self.ha is not None and getattr(self.ha, "enabled", False) and self.ha_entity:
            try:
                bri = max(1, min(255, int(round(pct * 2.55))))
                self.ha.call_service(
                    "light",
                    "turn_on",
                    {"entity_id": self.ha_entity, "brightness": bri},
                )
                self._on = True
                return f"{self.device_name} brightness set to {pct} percent."
            except Exception as e:
                errors.append(f"HA: {e}")
        # Brightness via Alexa voice relay
        if self.voice_relay and self._say_wait:
            try:
                msg = self._relay_phrase(
                    f"Alexa, set the {self.device_name} to {pct} percent"
                )
                self._on = True
                return msg
            except Exception as e:
                errors.append(f"relay: {e}")
        try:
            if self.on_webhook:
                self._post_url(self.on_webhook, {"state": "on", "brightness": pct})
                self._on = True
                return f"Sent {pct}% brightness to lamp webhook."
            if self.ifttt_key:
                self._ifttt(self.ifttt_on_event, value1=str(pct))
                self._on = True
                return f"IFTTT: {self.device_name} → {pct}%."
        except Exception as e:
            errors.append(str(e))
        msg = self.turn_on()
        if errors:
            return f"{msg} (brightness limited: {'; '.join(errors)})"
        return msg

    def _set(self, on: bool) -> str:
        errors: list[str] = []

        # Prefer silent APIs when configured
        if self.ha is not None and getattr(self.ha, "enabled", False) and self.ha_entity:
            try:
                domain = self.ha_entity.split(".", 1)[0]
                service = "turn_on" if on else "turn_off"
                self.ha.call_service(domain, service, {"entity_id": self.ha_entity})
                self._on = on
                return f"{self.device_name} {'on' if on else 'off'}."
            except Exception as e:
                errors.append(f"HA: {e}")

        if self.ifttt_key:
            try:
                event = self.ifttt_on_event if on else self.ifttt_off_event
                self._ifttt(event, value1=self.device_name)
                self._on = on
                return f"Alexa lamp {'on' if on else 'off'} via IFTTT ({self.device_name})."
            except Exception as e:
                errors.append(f"IFTTT: {e}")

        url = self.on_webhook if on else self.off_webhook
        if url:
            try:
                self._post_url(
                    url, {"state": "on" if on else "off", "device": self.device_name}
                )
                self._on = on
                return f"Lamp webhook fired — {self.device_name} {'on' if on else 'off'}."
            except Exception as e:
                errors.append(f"webhook: {e}")

        # Best default with only an Alexa + bulb: talk to the Echo
        if self.voice_relay and self._say_wait:
            try:
                phrase = f"Alexa, turn {'on' if on else 'off'} the {self.device_name}"
                msg = self._relay_phrase(phrase)
                self._on = on
                return msg
            except Exception as e:
                errors.append(f"voice relay: {e}")

        tip = (
            "Put an Echo within earshot of your PC speakers, or set alexa_ifttt_key / "
            "Home Assistant in settings."
        )
        if errors:
            return f"Could not reach {self.device_name} ({'; '.join(errors)}). {tip}"
        return tip

    def _relay_phrase(self, phrase: str) -> str:
        restore = self.restore_output
        switched = ""
        if self.audio is not None and hasattr(self.audio, "switch_for_alexa_relay"):
            switched, prev = self.audio.switch_for_alexa_relay()
            if prev:
                restore = prev
            time.sleep(0.45)  # let Windows commit the endpoint
        try:
            # Clear delivery — Alexa needs to hear the wake word from room speakers
            self._say_wait(phrase)
            time.sleep(0.35)
        finally:
            if self.audio is not None:
                try:
                    # Prefer explicit WG1 headset restore
                    self.audio.switch_output(self.restore_output or restore or "WG1")
                except Exception:
                    pass
        via = switched or "speakers"
        return f"Asked Alexa ({via}): {phrase}."

    def _ifttt(self, event: str, value1: str = "", value2: str = "", value3: str = "") -> None:
        url = f"https://maker.ifttt.com/trigger/{event}/with/key/{self.ifttt_key}"
        body = json.dumps(
            {"value1": value1, "value2": value2, "value3": value3}
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()

    def _post_url(self, url: str, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=raw,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}") from e
