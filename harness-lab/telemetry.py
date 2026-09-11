"""Optional OTLP/HTTP JSON export, strictly after authoritative finalization.

No telemetry SDK/runtime is required. Point this at an OTLP JSON collector;
its normal exporter can forward to LangSmith. Direct SaaS delivery is unverified.
The subprocess receives finalized trace data and export credentials only, never
a receipt path or authority to change a trial. It performs one bounded HTTP
request. API credentials are transport-only and never enter span data.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

DEFAULT_CONFIG = Path(__file__).resolve().parent / "runs/langsmith-local/config.json"
LANGSMITH_ENDPOINT = "https://api.smith.langchain.com/otel/v1/traces"
KEYCHAIN_SERVICE = "com.temper.harness.langsmith"
KEYCHAIN_ACCOUNT = "temper-harness"

SCHEMA_VERSION = 2
MAX_BYTES = 4 * 1024 * 1024
MAX_EVENTS = 1024
MAX_VALUE_BYTES = 4 * 1024 * 1024
ATTRIBUTES = {
    "run_id",
    "attempt_id",
    "phase",
    "condition",
    "revision_sha256",
    "model",
    "tool",
    "classification",
    "duration_ms",
    "operation",
    "request_sha256",
    "response_status",
    "mutation_committed",
    "native_verdict",
    "measurement_ref",
    "successful_mutations",
    "history_count",
    "refinement_count",
    "resume_count",
    "returncode",
    "error_category",
}


def _json_value(value: object) -> str | None:
    """Serialize complete trace values without silently truncating content."""
    try:
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None
    return encoded if len(encoded.encode()) <= MAX_VALUE_BYTES else None


def endpoint_from_env(env: dict[str, str]) -> str | None:
    return env.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or (
        env["OTEL_EXPORTER_OTLP_ENDPOINT"].rstrip("/") + "/v1/traces"
        if env.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        else None
    )


def local_destination(deadline: float) -> tuple[str, dict[str, str]]:
    """Resolve the explicitly configured LangSmith destination without logging secrets."""
    if not DEFAULT_CONFIG.is_file():
        raise ValueError("tracing destination is not configured")
    config = json.loads(DEFAULT_CONFIG.read_text())
    if (
        not isinstance(config, dict)
        or set(config) != {"endpoint", "project", "credential"}
        or config["endpoint"] != LANGSMITH_ENDPOINT
        or config["credential"] != "macos-keychain"
        or not isinstance(config["project"], str)
        or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", config["project"])
    ):
        raise ValueError("invalid local tracing configuration")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("tracing deadline expired")
    result = subprocess.run(
        [
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            KEYCHAIN_ACCOUNT,
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
        ],
        capture_output=True,
        text=True,
        timeout=min(2.0, remaining),
        check=False,
    )
    key = result.stdout.strip()
    if result.returncode or not key or "\n" in key or "\r" in key:
        raise ValueError("tracing credential unavailable")
    return config["endpoint"], {
        "x-api-key": key,
        "Langsmith-Project": config["project"],
    }


def packet(
    events: list[dict],
    receipt_digest: str,
    *,
    inputs: dict | None = None,
    outputs: dict | None = None,
    trace_name: str = "temper.harness",
) -> dict:
    if len(events) > MAX_EVENTS:
        raise ValueError("too many spans")
    spans = []
    root_span_id = hashlib.sha256(f"{receipt_digest}:root".encode()).hexdigest()[:16]
    for index, event in enumerate(events):
        start, end = event["started_unix_ns"], event["ended_unix_ns"]
        if type(start) is not int or type(end) is not int or not 0 <= start <= end < 2**64:
            raise ValueError("invalid span time")
        attributes = []
        for key in sorted(ATTRIBUTES & event.keys()):
            value = event[key]
            if (
                isinstance(value, str)
                and len(value) <= 256
                and re.fullmatch(r"[a-zA-Z0-9_./: -]*", value)
            ):
                attributes.append({"key": "temper." + key, "value": {"stringValue": value}})
            elif (
                key == "duration_ms"
                and type(value) in (int, float)
                and math.isfinite(value)
                and value >= 0
            ):
                attributes.append({"key": "temper.duration_ms", "value": {"doubleValue": value}})
        for field, key in (("input", "input.value"), ("output", "output.value")):
            value = _json_value(event[field]) if field in event else None
            if value is not None:
                attributes.append({"key": key, "value": {"stringValue": value}})
        if event.get("error_category"):
            attributes.append(
                {
                    "key": "error.type",
                    "value": {"stringValue": str(event["error_category"])[:128]},
                }
            )
        spans.append(
            {
                "traceId": receipt_digest[:32],
                "spanId": event.get("span_id")
                or hashlib.sha256(f"{receipt_digest}:{index}".encode()).hexdigest()[:16],
                "parentSpanId": event.get("parent_span_id") or root_span_id,
                "name": event.get("span_name", "temper.harness"),
                "kind": event.get("span_kind", 1),
                "startTimeUnixNano": str(start),
                "endTimeUnixNano": str(end),
                "attributes": attributes,
            }
        )
    root_attributes = [
        {"key": "langsmith.trace.name", "value": {"stringValue": trace_name}},
        {"key": "langsmith.span.kind", "value": {"stringValue": "chain"}},
    ]
    for field, key in (("input", "input.value"), ("output", "output.value")):
        source = inputs if field == "input" else outputs
        value = _json_value(source) if source is not None else None
        if value is not None:
            root_attributes.append({"key": key, "value": {"stringValue": value}})
    root = {
        "traceId": receipt_digest[:32],
        "spanId": root_span_id,
        "name": trace_name,
        "kind": 1,
        "startTimeUnixNano": str(events[0]["started_unix_ns"] if events else 0),
        "endTimeUnixNano": str(events[-1]["ended_unix_ns"] if events else 0),
        "attributes": root_attributes,
    }
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": "temper-harness"},
                        }
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "temper.harness",
                            "version": str(SCHEMA_VERSION),
                        },
                        "spans": [root, *spans],
                    }
                ],
            }
        ]
    }


def export(
    receipt: Path,
    events: list[dict],
    *,
    enabled: bool = False,
    endpoint: str | None = None,
    timeout: float = 5.0,
    inputs: dict | None = None,
    outputs: dict | None = None,
    trace_name: str = "temper.harness",
) -> dict:
    if not enabled:
        return {"status": "disabled"}
    endpoint = endpoint or endpoint_from_env(os.environ)
    try:
        if not math.isfinite(timeout) or not 0 < timeout <= 5:
            raise ValueError("export timeout must be within five seconds")
        deadline = time.monotonic() + timeout
        digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
        body = json.dumps(
            packet(
                events,
                digest,
                inputs=inputs,
                outputs=outputs,
                trace_name=trace_name,
            ),
            allow_nan=False,
            separators=(",", ":"),
        )
        if len(body.encode()) > MAX_BYTES:
            return {"status": "dropped", "reason": "payload_limit"}
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "dropped", "reason": "invalid_metadata"}
    headers = {}
    # Explicit OTLP headers or the configured tracing Keychain item only;
    # never read ambient model or unrelated service credentials.
    raw = os.environ.get(
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
        os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", ""),
    )
    for pair in raw.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            if key.strip().lower() in {
                "x-api-key",
                "langsmith-project",
                "authorization",
            }:
                headers[key.strip()] = unquote(value.strip())
    if not endpoint:
        try:
            endpoint, headers = local_destination(deadline)
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            return {
                "status": "unavailable",
                "reason": "configuration_or_credential_unavailable",
            }
    # Explicit endpoint overrides never receive the local Keychain credential.
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return {"status": "unavailable", "reason": "export_timeout"}
    payload = json.dumps(
        {"endpoint": endpoint, "body": body, "headers": headers, "timeout": remaining}
    )
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--send"],
            input=payload,
            text=True,
            capture_output=True,
            timeout=remaining,
            env={"PATH": "/usr/bin:/bin"},
            check=False,
        )
        if result.returncode == 0:
            return {"status": "exported", "span_count": len(events)}
        return {"status": "unavailable", "reason": "export_failed"}
    except (OSError, subprocess.SubprocessError):
        return {"status": "unavailable", "reason": "export_failed"}


def _send(payload: dict) -> None:
    target = urlsplit(payload["endpoint"])
    if (
        target.scheme not in {"http", "https"}
        or not target.hostname
        or target.username
        or target.password
        or target.fragment
    ):
        raise ValueError("invalid OTLP endpoint")
    if target.scheme == "http" and target.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError("remote collector requires HTTPS")
    cls = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
    connection = cls(target.hostname, port=target.port, timeout=payload["timeout"])
    try:
        connection.request(
            "POST",
            (target.path or "/") + ("?" + target.query if target.query else ""),
            body=payload["body"].encode(),
            headers={**payload["headers"], "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("collector rejected export")
        body = response.read(4097)
        if len(body) > 4096:
            raise ValueError("collector response too large")
        result = json.loads(body or b"{}")
        partial = result.get("partialSuccess", {})
        if int(partial.get("rejectedSpans", 0)) or partial.get("errorMessage"):
            raise ValueError("partial export")
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        if sys.argv[1:] != ["--send"]:
            raise ValueError("internal exporter invocation required")
        _send(json.loads(sys.stdin.read(MAX_BYTES * 2)))
    except Exception:
        # Never emit endpoint, headers, body, or exception messages containing them.
        raise SystemExit(1) from None
