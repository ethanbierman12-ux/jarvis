from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from jarvis.core.audit_ledger import AuditLedger
from jarvis.core.audio_isolation import pick_isolated_mic_index, rank_mic_candidates
from jarvis.core.companion_server import CompanionServer
from jarvis.core.exec_backend import ExecBackend
from jarvis.core.state_bus import StateBus


class StateBusTests(unittest.TestCase):
    def test_snapshot_tracks_ui_events_without_mqtt(self) -> None:
        @dataclass
        class Telemetry:
            cpu_percent: float
            ram_percent: float

        bus = StateBus(enabled=False)
        bus.publish_ui_event("reactor_activity", "speak")
        bus.publish_ui_event("mic_level", 1.7)
        bus.publish_ui_event("speaking", 1)
        bus.publish_ui_event("telemetry", Telemetry(44.44444, 55.55555))
        snapshot = bus.snapshot()

        self.assertEqual(snapshot["reactor"], "speak")
        self.assertEqual(snapshot["mic"], 1.0)
        self.assertTrue(snapshot["speaking"])
        self.assertEqual(snapshot["telemetry"]["cpu_percent"], 44.4444)
        self.assertTrue(snapshot["transport"]["http_fallback"])

        snapshot["telemetry"]["cpu_percent"] = 0
        self.assertEqual(bus.snapshot()["telemetry"]["cpu_percent"], 44.4444)


class AuditLedgerTests(unittest.TestCase):
    def test_chain_verifies_and_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chain.jsonl"
            ledger = AuditLedger(path)
            ledger.append(
                actor="test",
                op="memory.remember",
                resource="memory",
                payload={"text": "private value"},
                sensitivity="personal",
            )
            ledger.append(
                actor="test",
                op="instruction.append",
                resource="instructions",
                payload="be concise",
                sensitivity="work",
            )
            ok, detail = ledger.verify()
            self.assertTrue(ok, detail)
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("private value", raw)

            records = [json.loads(line) for line in raw.splitlines()]
            records[0]["op"] = "memory.changed"
            path.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )
            ok, _detail = ledger.verify()
            self.assertFalse(ok)


class AudioIsolationTests(unittest.TestCase):
    def test_respeaker_beats_virtual_and_camera_devices(self) -> None:
        names = [
            "Voicemeeter Output (VB-Audio)",
            "Microphone (EMEET SmartCam)",
            "ReSpeaker 4 Mic Array (USB)",
        ]
        index, reason = pick_isolated_mic_index(names)
        self.assertEqual(index, 2)
        self.assertIn("ReSpeaker", reason)
        self.assertEqual(rank_mic_candidates(names)[0][0], 2)

    def test_explicit_preference_wins(self) -> None:
        names = ["ReSpeaker 4 Mic Array (USB)", "Microphone (Yeti)"]
        index, _reason = pick_isolated_mic_index(names, prefer="Yeti")
        self.assertEqual(index, 1)


class ExecBackendTests(unittest.TestCase):
    def test_host_isolated_backend_runs_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "task.py"
            script.write_text("print(6 * 7)\n", encoding="utf-8")
            backend = ExecBackend(mode="host", host_fallback=True)
            result = backend.run_python(script, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "42")
            self.assertEqual(result.backend, "host-isolated")


class CompanionStateApiTests(unittest.TestCase):
    def test_authenticated_state_and_spatial_static(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            companion = root / "companion"
            spatial = root / "spatial"
            companion.mkdir()
            spatial.mkdir()
            (companion / "index.html").write_text("phone", encoding="utf-8")
            (spatial / "index.html").write_text("spatial", encoding="utf-8")
            server = CompanionServer(
                lambda text: text,
                token="unit-token",
                host="127.0.0.1",
                port=0,
                web_root=companion,
                spatial_root=spatial,
                on_state=lambda: {"reactor": "idle"},
            )
            server.start()
            self.addCleanup(server.stop)
            self.assertIsNotNone(server._httpd)
            port = server._httpd.server_port  # type: ignore[union-attr]

            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=2)
            self.assertEqual(denied.exception.code, 401)

            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/state",
                headers={"Authorization": "Bearer unit-token"},
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                body = json.loads(response.read().decode("utf-8"))
            self.assertEqual(body["state"]["reactor"], "idle")

            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/spatial?token=unit-token", timeout=2
            ) as response:
                self.assertEqual(response.read().decode("utf-8"), "spatial")


if __name__ == "__main__":
    unittest.main()
