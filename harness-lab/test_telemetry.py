"""Real local OTLP/HTTP delivery and failure isolation."""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import telemetry


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "config.json"
        patcher = patch.object(telemetry, "DEFAULT_CONFIG", self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.receipt = Path(self.temp.name) / "results.json"
        self.original = b'{"status":"fail"}\n'
        self.receipt.write_bytes(self.original)
        self.received = []
        received = self.received

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                received.append(
                    (
                        self.path,
                        dict(self.headers),
                        json.loads(
                            self.rfile.read(int(self.headers["Content-Length"]))
                        ),
                    )
                )
                if self.path == "/slow":
                    time.sleep(0.6)
                self.send_response(200)
                self.end_headers()
                try:
                    self.wfile.write(b"{}")
                except BrokenPipeError:
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.events = [
            {
                "name": "attempt",
                "run_id": "control-1",
                "attempt_id": "a",
                "phase": "development",
                "classification": "record_failed",
                "started_unix_ns": 1000000000,
                "ended_unix_ns": 2000000000,
                "prompt": "secret prompt",
                "authorization": "secret token",
                "skills_source": "secret code",
            }
        ]

    def test_disabled_ignores_ambient_credentials(self):
        with patch.dict(
            "os.environ",
            {
                "LANGSMITH_API_KEY": "ambient-secret",
                "OTEL_EXPORTER_OTLP_ENDPOINT": self.url,
            },
        ):
            result = telemetry.export(self.receipt, self.events)
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(self.received, [])
        self.assertEqual(self.receipt.read_bytes(), self.original)

    def test_collector_receives_otlp_allowlisted_metadata(self):
        result = telemetry.export(
            self.receipt, self.events, enabled=True, endpoint=self.url + "/v1/traces"
        )
        self.assertEqual(result["status"], "exported", result)
        path, headers, packet = self.received[0]
        self.assertEqual(path, "/v1/traces")
        self.assertEqual(headers["Content-Type"], "application/json")
        span = packet["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        self.assertEqual(len(span["traceId"]), 32)
        self.assertEqual(len(span["spanId"]), 16)
        self.assertEqual(span["startTimeUnixNano"], "1000000000")
        self.assertNotIn("secret", json.dumps(packet))
        self.assertEqual(self.receipt.read_bytes(), self.original)

    def test_timeout_and_bad_endpoint_preserve_receipt(self):
        for endpoint in (self.url + "/slow", "http://127.0.0.1:1/v1/traces"):
            result = telemetry.export(
                self.receipt, self.events, enabled=True, endpoint=endpoint, timeout=0.15
            )
            self.assertEqual(result["status"], "unavailable", result)
            self.assertEqual(self.receipt.read_bytes(), self.original)

    def test_missing_config_oversize_and_invalid_events(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                telemetry.export(self.receipt, self.events, enabled=True)["status"],
                "unavailable",
            )
        self.assertEqual(
            telemetry.export(
                self.receipt, self.events * 2000, enabled=True, endpoint=self.url
            )["status"],
            "dropped",
        )
        invalid = [{**self.events[0], "started_unix_ns": float("nan")}]
        self.assertEqual(
            telemetry.export(self.receipt, invalid, enabled=True, endpoint=self.url)[
                "status"
            ],
            "dropped",
        )
        self.assertEqual(self.received, [])

    def test_local_keychain_configuration_is_bounded_and_not_logged(self):
        self.config.write_text(
            json.dumps(
                {
                    "endpoint": telemetry.LANGSMITH_ENDPOINT,
                    "project": "temper-harness",
                    "credential": "macos-keychain",
                }
            )
        )
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(
                telemetry.subprocess,
                "run",
                side_effect=[
                    subprocess.CompletedProcess([], 0, stdout="test-key\n", stderr=""),
                    subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                ],
            ) as execute,
        ):
            result = telemetry.export(self.receipt, self.events, enabled=True)
        self.assertEqual(result["status"], "exported")
        lookup, export = execute.call_args_list
        self.assertLessEqual(lookup.kwargs["timeout"], 2)
        self.assertLessEqual(export.kwargs["timeout"], 5)
        payload = json.loads(export.kwargs["input"])
        self.assertEqual(payload["headers"]["x-api-key"], "test-key")
        self.assertNotIn("test-key", payload["body"])
        self.assertNotIn("test-key", json.dumps(result))
        self.assertEqual(self.receipt.read_bytes(), self.original)

    def test_opt_out_never_reads_configuration_or_keychain(self):
        self.config.write_text("invalid config")
        with patch.object(telemetry.subprocess, "run") as execute:
            result = telemetry.export(self.receipt, self.events, enabled=False)
        execute.assert_not_called()
        self.assertEqual(result["status"], "disabled")

    def test_custom_endpoint_never_receives_keychain_credential(self):
        self.config.write_text(
            json.dumps(
                {
                    "endpoint": telemetry.LANGSMITH_ENDPOINT,
                    "project": "temper-harness",
                    "credential": "macos-keychain",
                }
            )
        )
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(
                telemetry,
                "local_destination",
                side_effect=AssertionError("must not read Keychain"),
            ),
        ):
            result = telemetry.export(
                self.receipt,
                self.events,
                enabled=True,
                endpoint=self.url + "/v1/traces",
            )
        self.assertEqual(result["status"], "exported")
        self.assertNotIn("x-api-key", {k.lower() for k in self.received[0][1]})

    def test_invalid_local_destination_does_not_read_credential(self):
        self.config.write_text(
            json.dumps(
                {
                    "endpoint": "https://other.example/v1/traces",
                    "project": "temper-harness",
                    "credential": "macos-keychain",
                }
            )
        )
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(telemetry.subprocess, "run") as execute,
        ):
            result = telemetry.export(self.receipt, self.events, enabled=True)
        execute.assert_not_called()
        self.assertEqual(result["status"], "unavailable")

    def test_keychain_timeout_preserves_receipt_without_export(self):
        self.config.write_text(
            json.dumps(
                {
                    "endpoint": telemetry.LANGSMITH_ENDPOINT,
                    "project": "temper-harness",
                    "credential": "macos-keychain",
                }
            )
        )
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(
                telemetry.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("security", 2),
            ) as execute,
        ):
            result = telemetry.export(self.receipt, self.events, enabled=True)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(self.receipt.read_bytes(), self.original)

    def test_endpoint_resolution(self):
        self.assertEqual(
            telemetry.endpoint_from_env(
                {"OTEL_EXPORTER_OTLP_ENDPOINT": "https://collector/otel"}
            ),
            "https://collector/otel/v1/traces",
        )
        self.assertEqual(
            telemetry.endpoint_from_env(
                {
                    "OTEL_EXPORTER_OTLP_ENDPOINT": "https://collector/otel",
                    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "https://collector/custom",
                }
            ),
            "https://collector/custom",
        )
