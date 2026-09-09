"""Run E00 through isolated OpenCode; record and constrain the Zen wire boundary."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import harness
import routing_host
from run_trials import INSTRUCTIONS, PREFLIGHT_PROMPT, PROMPT, audit, require

MODEL = "muse-spark-1.3-contributor-free"
TOOL_NAMES = {"pcb_" + tool["name"] for tool in harness.TOOLS}
PREFLIGHT_INSTRUCTIONS = """This is an inspection-only runtime preflight, not a board editing task.
Call pcb_inspect exactly once, then list the available PCB tool names and stop.
Do not solve the task. Do not call any other tool. Those operations are
disabled by the preflight host even though their schemas are visible.
"""


def validate_request(packet: dict, tools: list = harness.TOOLS) -> None:
    tool_names = {"pcb_" + t["name"] for t in tools}
    require(packet.get("model") == MODEL, "Unapproved model")
    require(packet.get("store") is False, "Stateless conversation required")
    require(
        not any(
            item.get("type") == "item_reference" for item in packet.get("input", [])
        ),
        "Unresolvable server-side reference",
    )
    names = []
    for tool in packet.get("tools", []):
        require(tool.get("type") == "function", "Unapproved provider tool")
        require(tool.get("name") in tool_names, "Unapproved function")
        expected = next(t for t in tools if "pcb_" + t["name"] == tool["name"])
        require(
            tool.get("parameters") == expected["inputSchema"], "Tool schema changed"
        )
        require(
            tool.get("description") == expected["description"],
            "Tool description changed",
        )
        names.append(tool["name"])
    require(
        set(names) == tool_names and len(names) == len(tools), "Tool catalog differs"
    )


class Recorder(ThreadingHTTPServer):
    """Local relay: fixed upstream, no persisted auth headers, complete wire evidence."""

    daemon_threads = False

    def __init__(self, directory: Path, tools: list = harness.TOOLS):
        super().__init__(("127.0.0.1", 0), Relay)
        self.directory = directory
        self.tools = tools
        self.sequence = 0
        self.lock = threading.Lock()
        self.deadline = time.monotonic() + 300
        self.busy = False
        self.failed = False
        self.upstream_socket = None

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Trial deadline reached")
        return remaining

    def server_close(self) -> None:
        # Release a silent upstream before joining handlers and auditing files.
        with self.lock:
            self.failed = True
            if self.upstream_socket is not None:
                try:
                    self.upstream_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        super().server_close()


class Relay(BaseHTTPRequestHandler):
    server: Recorder

    def log_message(self, *_: object) -> None:
        pass

    def do_POST(self) -> None:
        with self.server.lock:
            self.server.sequence += 1
            prefix = self.server.directory / f"wire-{self.server.sequence:03}"
        connection = None
        admitted = False
        sent_headers = False
        started = last_chunk = time.monotonic()
        maximum_gap = 0.0
        telemetry = {"started_unix_s": time.time(), "upstream_attempted": False}
        try:
            require(self.path == "/responses", "Unexpected endpoint")
            self.connection.settimeout(self.server.remaining())
            length = int(self.headers.get("Content-Length", "0"))
            require(0 < length <= 2_000_000, "Invalid request size")
            body = self.rfile.read(length)
            packet = json.loads(body)
            prefix.with_suffix(".request.json").write_bytes(body)
            validate_request(packet, self.server.tools)
            with self.server.lock:
                require(
                    not self.server.failed,
                    "Trial transport already failed; retry blocked",
                )
                require(not self.server.busy, "Concurrent upstream request blocked")
                self.server.remaining()
                self.server.busy = admitted = True
            connection = http.client.HTTPSConnection(
                "opencode.ai", timeout=self.server.remaining()
            )
            connection.connect()
            upstream_socket = connection.sock
            with self.server.lock:
                require(not self.server.failed, "Trial transport closed")
                self.server.upstream_socket = upstream_socket
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() not in {"host", "connection", "accept-encoding"}
            }
            headers["Accept-Encoding"] = "identity"
            upstream_socket.settimeout(self.server.remaining())
            telemetry["upstream_attempted"] = True
            connection.request("POST", "/zen/v1/responses", body, headers)
            upstream_socket.settimeout(self.server.remaining())
            response = connection.getresponse()
            prefix.with_suffix(".status.json").write_text(
                json.dumps(
                    {
                        "status": response.status,
                        "headers": {
                            key.lower(): value
                            for key, value in response.getheaders()
                            if key.lower()
                            in {
                                "content-type",
                                "date",
                                "retry-after",
                                "x-request-id",
                                "x-ratelimit-limit-requests",
                                "x-ratelimit-remaining-requests",
                                "x-ratelimit-reset-requests",
                                "x-ratelimit-limit-tokens",
                                "x-ratelimit-remaining-tokens",
                                "x-ratelimit-reset-tokens",
                            }
                        },
                    }
                )
            )
            self.send_response(response.status)
            self.send_header("Content-Type", response.getheader("Content-Type"))
            self.send_header("Connection", "close")
            self.end_headers()
            sent_headers = True
            with prefix.with_suffix(".response.txt").open("wb") as evidence:
                while not response.isclosed():
                    upstream_socket.settimeout(self.server.remaining())
                    chunk = response.read1(65536)
                    now = time.monotonic()
                    maximum_gap = max(maximum_gap, now - last_chunk)
                    last_chunk = now
                    if not chunk:
                        break
                    evidence.write(chunk)
                    evidence.flush()
                    self.connection.settimeout(self.server.remaining())
                    self.wfile.write(chunk)
                    self.wfile.flush()
            require(response.status == 200, "Provider request failed")
            require(
                any(
                    json.loads(line[6:]).get("type") == "response.completed"
                    for line in prefix.with_suffix(".response.txt")
                    .read_text()
                    .splitlines()
                    if line.startswith("data: ") and line != "data: [DONE]"
                ),
                "Incomplete provider response; retry blocked",
            )
        except Exception as error:
            with self.server.lock:
                self.server.failed = True
            prefix.with_suffix(".error.json").write_text(
                json.dumps({"error": f"{type(error).__name__}: {error}"})
            )
            # No upstream request is made if admission fails.
            if not sent_headers:
                self.send_error(400, "Request rejected by experiment boundary")
        finally:
            if connection is not None:
                connection.close()
            telemetry.update(
                {
                    "elapsed_s": time.monotonic() - started,
                    "maximum_read_gap_s": max(
                        maximum_gap, time.monotonic() - last_chunk
                    ),
                }
            )
            prefix.with_suffix(".timing.json").write_text(json.dumps(telemetry))
            with self.server.lock:
                if admitted:
                    self.server.upstream_socket = None
                    self.server.busy = False
            self.close_connection = True


def configuration(
    directory: Path,
    port: int,
    deadline: float,
    preflight: bool = False,
    routing: bool = False,
    routing_fixture: str = "e00r",
) -> dict:
    model = "opencode/" + MODEL
    tools = routing_host.TOOLS if routing else harness.TOOLS
    host = (
        (
            [str(routing_host.ROOT / "routing_host.py"), "--fixture", routing_fixture]
            + (["--inspect-only"] if preflight else [])
        )
        if routing
        else (
            [str(Path(__file__).resolve()), "--serve-inspection"]
            if preflight
            else [str(harness.ROOT / "harness.py")]
        )
    )
    instructions = routing_host.INSTRUCTIONS if routing else INSTRUCTIONS
    return {
        "model": model,
        "small_model": model,
        "enabled_providers": ["opencode"],
        "share": "disabled",
        "autoupdate": False,
        "snapshot": False,
        "plugin": [],
        "instructions": [],
        "compaction": {"auto": False},
        "permission": {
            "*": "deny",
            **{name: "allow" for name in sorted("pcb_" + t["name"] for t in tools)},
        },
        "agent": {
            "pcb": {
                "mode": "primary",
                "prompt": PREFLIGHT_INSTRUCTIONS if preflight else instructions,
                "model": model,
            },
            "title": {"disable": True},
            "summary": {"disable": True},
        },
        "provider": {
            "opencode": {
                "npm": "@ai-sdk/openai",
                "options": {"baseURL": f"http://127.0.0.1:{port}", "maxRetries": 0},
                "models": {
                    MODEL: {
                        "name": "Muse Spark 1.3 Contributor Free",
                        "options": {"store": False},
                        "limit": {"context": 1048576, "output": 131072},
                        "cost": {"input": 0, "output": 0},
                    }
                },
            }
        },
        "mcp": {
            "pcb": {
                "type": "local",
                "command": [
                    sys.executable,
                    *host,
                    str(directory),
                    "--deadline",
                    str(deadline),
                ],
                "enabled": True,
                "timeout": 60000,
            }
        },
    }


def environment(private: Path, config: dict) -> dict[str, str]:
    # Preserve HOME's meaning; isolate XDG state and omit unrelated credentials.
    env = {
        key: os.environ[key] for key in ("HOME", "PATH", "TMPDIR") if key in os.environ
    }
    for kind in ("CONFIG", "DATA", "CACHE", "STATE"):
        env[f"XDG_{kind}_HOME"] = str(private / kind.lower())
    for flag in (
        "CLAUDE_CODE",
        "EXTERNAL_SKILLS",
        "DEFAULT_PLUGINS",
        "PROJECT_CONFIG",
        "AUTOUPDATE",
        "SHARE",
        "AUTOCOMPACT",
        "LSP_DOWNLOAD",
    ):
        env["OPENCODE_DISABLE_" + flag] = "1"
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(config)
    return env


def normalize(events: list[dict], tools: list = harness.TOOLS) -> list[dict]:
    """Adapt OpenCode events to the existing, qualified action/snapshot audit."""
    tool_names = {"pcb_" + t["name"] for t in tools}
    result = []
    for event in events:
        kind, part = event["type"], event.get("part", {})
        if kind == "tool_use":
            name, state = part["tool"], part["state"]
            require(name in tool_names, "Unexpected executed tool")
            require(state["status"] == "completed", "Uncompleted tool call")
            result.append(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "pcb",
                        "tool": name.removeprefix("pcb_"),
                        "arguments": state["input"],
                        "result": {
                            "content": [{"type": "text", "text": state["output"]}]
                        },
                    },
                }
            )
        elif kind == "step_finish" and part.get("reason") == "stop":
            result.append({"type": "turn.completed", "usage": part.get("tokens")})
        else:
            require(
                kind in {"text", "reasoning", "step_start", "step_finish"},
                f"Unexpected OpenCode event: {kind}",
            )
    return result


def verify_wire(
    directory: Path, events: list[dict], tools: list = harness.TOOLS
) -> dict:
    requests = sorted(directory.glob("wire-*.request.json"))
    require(bool(requests), "No recorded model requests")
    require(not list(directory.glob("wire-*.error.json")), "Wire boundary error")
    served = set()
    provider_calls = []
    shown_outputs = {}
    for path in requests:
        packet = json.loads(path.read_text())
        validate_request(packet, tools)
        for item in packet["input"]:
            if item.get("type") == "function_call_output":
                call_id = item["call_id"]
                output = json.loads(item["output"])
                require(
                    call_id not in shown_outputs or shown_outputs[call_id] == output,
                    "Replayed output changed",
                )
                shown_outputs[call_id] = output
        prefix = path.name.removesuffix(".request.json")
        status = json.loads((directory / f"{prefix}.status.json").read_text())
        require(status["status"] == 200, "Provider request failed")
        completed = False
        for line in (directory / f"{prefix}.response.txt").read_text().splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            event = json.loads(line[6:])
            if event.get("type") == "response.completed":
                completed = True
                served.add(event["response"]["model"])
                provider_calls.extend(
                    item
                    for item in event["response"]["output"]
                    if item["type"] == "function_call"
                )
        require(completed, "No complete provider response")
    require(served == {MODEL}, "Provider reported a different model")
    client_calls = [event["part"] for event in events if event["type"] == "tool_use"]
    require(
        len(provider_calls) == len(client_calls),
        "Provider and client call counts differ",
    )
    require(
        set(shown_outputs) == {part["callID"] for part in client_calls},
        "Missing or extra model observations",
    )
    for requested, executed in zip(provider_calls, client_calls):
        require(
            requested["call_id"] == executed["callID"],
            "Provider/client call ID mismatch",
        )
        require(
            requested["name"] == executed["tool"]
            and json.loads(requested["arguments"]) == executed["state"]["input"],
            "Executed call differs from provider request",
        )
        require(
            shown_outputs[executed["callID"]]
            == json.loads(executed["state"]["output"]),
            "Wire observation differs from client result",
        )
    return {
        "request_count": len(requests),
        "served_models": sorted(served),
        "tool_catalog": sorted("pcb_" + t["name"] for t in tools),
    }


def run(
    output: Path,
    qualification: Path,
    preflight: bool,
    preflight_receipt: Path | None,
    routing: bool = False,
    routing_fixture: str = "e00r",
) -> None:
    task = routing_host if routing else harness
    contract_path = (
        routing_host.CONTRACTS[routing_fixture]
        if routing
        else harness.ROOT / "fixtures/contract.json"
    )
    instructions = routing_host.INSTRUCTIONS if routing else INSTRUCTIONS
    prompt = routing_host.PROMPT if routing else PROMPT
    receipt = json.loads(qualification.read_text())
    contract = json.loads(contract_path.read_text())
    require(receipt["status"] == "qualified", "Unqualified apparatus")
    require(
        receipt["contract_sha256"] == harness.file_hash(contract_path),
        "Changed contract",
    )
    for name, digest in receipt["source_sha256"].items():
        require(harness.file_hash(harness.ROOT / name) == digest, f"Requalify {name}")
    require(
        harness.file_hash(harness.JUDGE) == receipt["evaluator_sha256"],
        "Changed evaluator",
    )
    runner_hash = harness.file_hash(Path(__file__))
    if not preflight:
        require(preflight_receipt is not None, "Successful preflight receipt required")
        previous = json.loads(preflight_receipt.read_text())
        require(previous["status"] == "preflight_pass", "Preflight did not pass")
        require(
            previous["runner_sha256"] == runner_hash, "Runner changed since preflight"
        )
    executable = shutil.which("opencode")
    require(executable is not None, "OpenCode unavailable")
    if not preflight:
        prior_manifest = json.loads(
            (preflight_receipt.parent / "manifest.json").read_text()
        )
        require(
            prior_manifest["opencode_sha256"] == harness.file_hash(Path(executable)),
            "OpenCode changed since preflight",
        )
        require(
            prior_manifest["qualification_sha256"] == harness.file_hash(qualification),
            "Qualification changed since preflight",
        )
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "model": "opencode/" + MODEL,
        "runner_sha256": runner_hash,
        "qualification_sha256": harness.file_hash(qualification),
        "opencode_sha256": harness.file_hash(Path(executable)),
        "opencode_version": subprocess.check_output(
            [executable, "--version"], text=True
        ).strip(),
        "preflight": preflight,
        "experiment": contract["experiment"],
        "instructions": PREFLIGHT_INSTRUCTIONS if preflight else instructions,
        "prompt": PREFLIGHT_PROMPT if preflight else prompt,
        "data_use": "User approved Zen/Meta Contributor training terms on 2026-09-09",
        "contract": contract,
        "transport_policy": {
            "trial_budget_s": 300,
            "read_timeout": "remaining trial budget",
            "max_concurrent_upstream_requests": 1,
            "after_incomplete_or_failed_response": "block all further upstream requests",
            "headers": "fixed response-header allowlist; no persisted auth or cookies",
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    results = []
    for index, start in enumerate(
        contract["starts"][:1] if preflight else contract["starts"], 1
    ):
        directory = output / f"trial-{index}"
        if routing:
            task.prepare(directory, start, fixture=routing_fixture)
        else:
            task.prepare(directory, start)
        recorder = Recorder(directory, task.TOOLS)
        thread = threading.Thread(target=recorder.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix="temper-e00-zen-") as tmp:
                private = Path(tmp)
                empty = private / "workspace"
                empty.mkdir()
                recorder.deadline = time.monotonic() + 300
                config = configuration(
                    directory,
                    recorder.server_port,
                    time.time() + 300,
                    preflight,
                    routing,
                    routing_fixture,
                )
                (directory / "config.json").write_text(json.dumps(config, indent=2))
                command = [
                    executable,
                    "run",
                    "--format",
                    "json",
                    "--agent",
                    "pcb",
                    "--model",
                    "opencode/" + MODEL,
                    "--title",
                    "Temper E00",
                    manifest["prompt"],
                ]
                (directory / "invocation.json").write_text(
                    json.dumps(command, indent=2)
                )
                started = time.monotonic()
                with (
                    (directory / "model.jsonl").open("w") as out,
                    (directory / "model.stderr").open("w") as err,
                ):
                    process = subprocess.Popen(
                        command,
                        cwd=empty,
                        env=environment(private, config),
                        stdout=out,
                        stderr=err,
                        start_new_session=True,
                    )
                    try:
                        returncode = process.wait(
                            timeout=max(0, recorder.deadline - time.monotonic())
                        )
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()
                        returncode = 124
                elapsed = time.monotonic() - started
        finally:
            recorder.shutdown()
            recorder.server_close()
            thread.join(timeout=5)
        try:
            events = [
                json.loads(line)
                for line in (directory / "model.jsonl").read_text().splitlines()
                if line.strip()
            ]
            normalized = normalize(events, task.TOOLS)
            wire = verify_wire(directory, events, task.TOOLS)
            checked = audit(
                directory,
                normalized,
                elapsed,
                returncode,
                contract,
                edit_operations=("route", "remove_route") if routing else ("place",),
            )
            if routing:
                checked["routing_edits"] = checked.pop("placement_edits")
            if preflight:
                calls = [e for e in normalized if e["type"] == "item.completed"]
                require(returncode == 0 and elapsed <= 300, "Preflight runtime failed")
                require(
                    len(calls) == 1 and calls[0]["item"]["tool"] == "inspect",
                    "Preflight must inspect exactly once",
                )
                require(
                    checked["final_check"]["status"] != "indeterminate",
                    "Inspection failed",
                )
                require(
                    any(e["type"] == "turn.completed" for e in normalized),
                    "No final response",
                )
                checked["status"] = "preflight_pass"
            else:
                verification = task.evaluate(
                    directory, contract, directory / "host-final-check"
                )
                checked["independent_host_check"] = verification
                if routing and "repair_cases" in contract:
                    checked["repair"] = routing_host.audit_repair(
                        directory, start, contract
                    )
                if verification["status"] != "pass":
                    checked["status"] = "fail"
            checked["wire"] = wire
            checked["usage"] = [
                e["part"].get("tokens") for e in events if e["type"] == "step_finish"
            ]
            checked["cost_usd"] = sum(
                e["part"]["cost"] for e in events if e["type"] == "step_finish"
            )
            checked["cost_note"] = (
                "OpenCode reported cost; free Contributor model, not a billing receipt"
            )
            result = checked
        except Exception as error:
            result = {
                "status": "indeterminate",
                "error": f"{type(error).__name__}: {error}",
                "returncode": returncode,
                "elapsed_s": elapsed,
            }
        shutil.copyfile(
            directory / "candidate.kicad_pcb", directory / "final.kicad_pcb"
        )
        (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        results.append(result)
        print(
            json.dumps(
                {
                    "trial": index,
                    "status": result["status"],
                    "elapsed_s": elapsed,
                    "edits": result.get(
                        "routing_edits" if routing else "placement_edits"
                    ),
                    "error": result.get("error"),
                }
            ),
            flush=True,
        )
    expected = "preflight_pass" if preflight else "pass"
    (output / "results.json").write_text(
        json.dumps(
            {
                "status": expected
                if all(r["status"] == expected for r in results)
                else "fail",
                "runner_sha256": runner_hash,
                "trials": results,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--serve-inspection":

        class InspectionSession(harness.Session):
            def call(self, name: str, arguments: dict) -> dict:
                # Unknown operations fail closed in the qualified host before editing.
                return super().call(
                    name if name == "inspect" else "disabled_in_preflight", arguments
                )

        inspection_parser = argparse.ArgumentParser()
        inspection_parser.add_argument("--serve-inspection", type=Path)
        inspection_parser.add_argument("--deadline", type=float, required=True)
        inspection_args = inspection_parser.parse_args()
        inspection_contract = json.loads(
            (harness.ROOT / "fixtures/contract.json").read_text()
        )
        harness.serve(
            InspectionSession(
                inspection_args.serve_inspection,
                inspection_contract,
                inspection_args.deadline,
            )
        )
        sys.exit(0)
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--routing", action="store_true")
    parser.add_argument(
        "--routing-fixture", choices=sorted(routing_host.CONTRACTS), default="e00r"
    )
    parser.add_argument("--preflight-receipt", type=Path)
    args = parser.parse_args()
    if args.routing_fixture != "e00r" and not args.routing:
        parser.error("--routing-fixture requires --routing")
    run(
        args.output.resolve(),
        args.qualification.resolve(),
        args.preflight,
        args.preflight_receipt,
        args.routing,
        args.routing_fixture,
    )
