"""Boundary checks; recorded native action-chain coverage remains in qualify.py."""

import copy
import http.client
import json
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import harness
from run_zen_trials import MODEL, Recorder, normalize, validate_request, verify_wire


class ZenBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = {
            "model": MODEL,
            "store": False,
            "input": [],
            "tools": [
                {
                    "type": "function",
                    "name": "pcb_" + t["name"],
                    "parameters": t["inputSchema"],
                    "description": t["description"],
                }
                for t in harness.TOOLS
            ],
        }

    def test_exact_catalog_is_admitted(self) -> None:
        validate_request(self.packet)

    def test_model_fallback_is_rejected(self) -> None:
        self.packet["model"] = "muse-spark-1.3"
        with self.assertRaises(ValueError):
            validate_request(self.packet)

    def test_extra_or_missing_tools_are_rejected(self) -> None:
        for tools in (
            self.packet["tools"][:-1],
            self.packet["tools"] + [{"type": "web_search"}],
            self.packet["tools"] + [{"type": "function", "name": "bash"}],
        ):
            with self.subTest(tools=tools), self.assertRaises(ValueError):
                validate_request({**self.packet, "tools": tools})

    def test_changed_tool_schema_is_rejected(self) -> None:
        packet = copy.deepcopy(self.packet)
        packet["tools"][1]["parameters"]["properties"]["reference"] = {"type": "string"}
        with self.assertRaises(ValueError):
            validate_request(packet)

    def test_stateful_references_are_rejected(self) -> None:
        self.packet["input"] = [{"type": "item_reference", "id": "missing"}]
        with self.assertRaises(ValueError):
            validate_request(self.packet)

    def test_only_completed_admitted_calls_are_normalized(self) -> None:
        event = {
            "type": "tool_use",
            "part": {
                "tool": "pcb_inspect",
                "state": {
                    "status": "completed",
                    "input": {},
                    "output": '{"status":"fail"}',
                },
            },
        }
        self.assertEqual(normalize([event])[0]["item"]["arguments"], {})
        event["part"]["tool"] = "bash"
        with self.assertRaises(ValueError):
            normalize([event])
        with self.assertRaises(ValueError):
            normalize([{"type": "error"}])

    def test_wire_matches_calls_and_rejects_tampered_observation(self) -> None:
        call = {
            "type": "function_call",
            "name": "pcb_inspect",
            "call_id": "call1",
            "arguments": "{}",
        }
        observation = {"status": "fail", "sequence": 1}
        events = [
            {
                "type": "tool_use",
                "part": {
                    "tool": "pcb_inspect",
                    "callID": "call1",
                    "state": {
                        "status": "completed",
                        "input": {},
                        "output": json.dumps(observation),
                    },
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            packets = [
                self.packet,
                {
                    **self.packet,
                    "input": [
                        call,
                        {
                            "type": "function_call_output",
                            "call_id": "call1",
                            "output": json.dumps(observation),
                        },
                    ],
                },
            ]
            for index, packet in enumerate(packets, 1):
                prefix = directory / f"wire-{index:03}"
                prefix.with_suffix(".request.json").write_text(json.dumps(packet))
                prefix.with_suffix(".status.json").write_text('{"status":200}')
                prefix.with_suffix(".response.txt").write_text(
                    "data: "
                    + json.dumps(
                        {
                            "type": "response.completed",
                            "response": {
                                "model": MODEL,
                                "output": [call] if index == 1 else [],
                            },
                        }
                    )
                    + "\n"
                )
            self.assertEqual(verify_wire(directory, events)["request_count"], 2)
            packets[1]["input"][1]["output"] = '{"status":"pass"}'
            (directory / "wire-002.request.json").write_text(json.dumps(packets[1]))
            with self.assertRaises(ValueError):
                verify_wire(directory, events)


class ZenStreamTests(unittest.TestCase):
    setUp = ZenBoundaryTests.setUp

    # Real localhost sockets; only the upstream destination is substituted.
    @contextmanager
    def relay(self, *, delay=0, complete=True, status=200, budget=90):
        calls = []

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                calls.append(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(status)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Retry-After", "17")
                self.send_header("X-RateLimit-Remaining-Requests", "0")
                self.send_header("Set-Cookie", "private-test-cookie")
                self.end_headers()
                try:
                    self.wfile.write(b'data: {"type":"response.in_progress"}\n\n')
                    self.wfile.flush()
                    time.sleep(delay)
                    if complete:
                        self.wfile.write(b'data: {"type":"response.completed"}\n\n')
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
            recorder = Recorder(directory)
            recorder.deadline = time.monotonic() + budget
            threads = [
                threading.Thread(target=s.serve_forever) for s in (upstream, recorder)
            ]
            for thread in threads:
                thread.start()
            with patch(
                "run_zen_trials.http.client.HTTPSConnection",
                side_effect=lambda host, timeout: http.client.HTTPConnection(
                    "127.0.0.1", upstream.server_port, timeout=timeout
                ),
            ):
                try:
                    yield recorder, directory, calls
                finally:
                    for server in (recorder, upstream):
                        server.shutdown()
                        server.server_close()
                    for thread in threads:
                        thread.join()

    def request(self, recorder):
        connection = http.client.HTTPConnection(
            "127.0.0.1", recorder.server_port, timeout=95
        )
        try:
            connection.request("POST", "/responses", json.dumps(self.packet))
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_reasoning_silence_beyond_60_seconds_can_complete(self):
        with self.relay(delay=61) as (recorder, directory, calls):
            status, body = self.request(recorder)
            self.assertEqual(status, 200)
            self.assertIn(b"response.completed", body)
            self.assertFalse(list(directory.glob("*.error.json")))
            self.assertEqual(len(calls), 1)

    def test_incomplete_response_blocks_upstream_retry(self):
        with self.relay(complete=False) as (recorder, directory, calls):
            self.request(recorder)
            self.request(recorder)
            self.assertEqual(len(calls), 1)
            self.assertTrue(list(directory.glob("*.error.json")))

    def test_rate_limit_headers_are_recorded_without_cookies(self):
        with self.relay(status=429, complete=False) as (recorder, directory, calls):
            self.assertEqual(self.request(recorder)[0], 429)
            self.request(recorder)
            self.assertEqual(len(calls), 1)
            record = json.loads((directory / "wire-001.status.json").read_text())
            self.assertEqual(record["headers"]["retry-after"], "17")
            self.assertEqual(record["headers"]["x-ratelimit-remaining-requests"], "0")
            self.assertNotIn("private-test-cookie", json.dumps(record))

    def test_trial_deadline_interrupts_silent_stream(self):
        with self.relay(delay=0.5, budget=0.15) as (recorder, directory, calls):
            _, body = self.request(recorder)
            self.assertNotIn(b"response.completed", body)
            self.assertTrue(list(directory.glob("*.error.json")))
            self.request(recorder)
            self.assertEqual(len(calls), 1)

    def test_concurrent_request_never_reaches_upstream(self):
        with self.relay(delay=0.3) as (recorder, directory, calls):
            first = threading.Thread(target=self.request, args=(recorder,))
            first.start()
            limit = time.monotonic() + 2
            while not calls and time.monotonic() < limit:
                time.sleep(0.005)
            self.request(recorder)
            first.join()
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
