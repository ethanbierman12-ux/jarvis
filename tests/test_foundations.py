from __future__ import annotations

import json
import http.cookiejar
import tempfile
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

from jarvis.config import Settings
from jarvis.core.audit_ledger import AuditLedger
from jarvis.core.agent_crew import MemoryAgent
from jarvis.core.audio_isolation import pick_isolated_mic_index, rank_mic_candidates
from jarvis.core.companion_server import CompanionServer
from jarvis.core.exec_backend import ExecBackend
from jarvis.core.state_bus import StateBus
from jarvis.core.secrets_vault import SecretsVault


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

        bus.publish_ui_event("heard", "private conversation")
        self.assertNotIn("last_heard", bus._mqtt_snapshot())


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
            with self.assertRaises(RuntimeError):
                ledger.append(
                    actor="test",
                    op="must.refuse",
                    resource="memory",
                    payload="new write",
                )

    def test_separate_instances_serialize_concurrent_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chain.jsonl"

            def write(index: int) -> None:
                AuditLedger(path).append(
                    actor="thread",
                    op="write",
                    resource="test",
                    payload=index,
                )

            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(write, range(12)))
            ledger = AuditLedger(path)
            ok, detail = ledger.verify()
            self.assertTrue(ok, detail)
            self.assertEqual(ledger.status()["records"], 12)


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


class MemoryPrivacyTests(unittest.TestCase):
    def test_personal_memory_stays_out_of_remote_prompts(self) -> None:
        class Store:
            available = True

            def recall_records(self, _query, n=4):
                return [
                    {"text": "private fact", "sensitivity": "personal"},
                    {"text": "work fact", "sensitivity": "work"},
                ][:n]

        memory = MemoryAgent(Store())
        with (
            mock.patch("jarvis.core.agent_crew.backend_name", return_value="anthropic"),
            mock.patch(
                "jarvis.core.agent_crew.remote_backends_configured", return_value=True
            ),
        ):
            recalled = memory.recall("fact")
        self.assertNotIn("private fact", recalled)
        self.assertIn("work fact", recalled)


class ExecBackendTests(unittest.TestCase):
    def test_host_fallback_is_opt_in(self) -> None:
        self.assertFalse(ExecBackend().host_fallback)

    def test_host_isolated_backend_runs_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "task.py"
            script.write_text("print(6 * 7)\n", encoding="utf-8")
            backend = ExecBackend(mode="host", host_fallback=True)
            result = backend.run_python(script, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "42")
            self.assertEqual(result.backend, "host-isolated")


class SecretPersistenceTests(unittest.TestCase):
    def test_settings_stay_redacted_when_secure_vault_fails(self) -> None:
        class BrokenVault:
            _cache: dict[str, str] = {}

            def load(self):
                return {}

            def save(self):
                raise RuntimeError("secure store offline")

            def merge_into(self, _settings):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            mirror_path = Path(tmp) / "config.json"
            with (
                mock.patch(
                    "jarvis.core.secrets_vault.get_vault", return_value=BrokenVault()
                ),
                mock.patch("jarvis.config.CONFIG_JSON", mirror_path),
                mock.patch("jarvis.core.audit_ledger.get_audit_ledger"),
            ):
                Settings(openai_api_key="never-write-me").save(settings_path)
            raw = settings_path.read_text(encoding="utf-8")
            self.assertNotIn("never-write-me", raw)
            self.assertEqual(json.loads(raw)["openai_api_key"], "")

    def test_vault_refuses_plaintext_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vault.json"
            vault = SecretsVault(path)
            with mock.patch(
                "jarvis.core.secrets_vault._dpapi_protect",
                side_effect=OSError("unsupported"),
            ):
                with self.assertRaises(RuntimeError):
                    vault.save({"openai_api_key": "secret"})
            self.assertFalse(path.with_suffix(".local.json").exists())


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

            jar = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            with opener.open(
                f"http://127.0.0.1:{port}/spatial?token=unit-token", timeout=2
            ) as response:
                self.assertEqual(response.read().decode("utf-8"), "spatial")
                self.assertNotIn("token=", response.geturl())
            cookies = list(jar)
            self.assertEqual([cookie.name for cookie in cookies], ["jarvis_session"])
            self.assertNotEqual(cookies[0].value, "unit-token")
            with opener.open(f"http://127.0.0.1:{port}/api/state", timeout=2) as response:
                body = json.loads(response.read().decode("utf-8"))
            self.assertEqual(body["state"]["reactor"], "idle")


if __name__ == "__main__":
    unittest.main()
