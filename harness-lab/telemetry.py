"""Optional OTLP/HTTP JSON export, strictly after authoritative finalization.

No telemetry SDK/runtime is required. Point this at an OTLP JSON collector;
its normal exporter can forward to LangSmith. Direct SaaS delivery is unverified.
The subprocess receives metadata and export credentials only, never a receipt
path or authority to change a trial. It performs one bounded HTTP request.
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
from pathlib import Path
from urllib.parse import unquote, urlsplit

MAX_BYTES = 128 * 1024
MAX_EVENTS = 1024
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
}


def endpoint_from_env(env: dict[str, str]) -> str | None:
    return env.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or (
        env["OTEL_EXPORTER_OTLP_ENDPOINT"].rstrip("/") + "/v1/traces"
        if env.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        else None
    )


def packet(events: list[dict], receipt_digest: str) -> dict:
    if len(events) > MAX_EVENTS:
        raise ValueError("too many spans")
    spans = []
    for index, event in enumerate(events):
        start, end = event["started_unix_ns"], event["ended_unix_ns"]
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start <= end < 2**64
        ):
            raise ValueError("invalid span time")
        attributes = []
        for key in sorted(ATTRIBUTES & event.keys()):
            value = event[key]
            if (
                isinstance(value, str)
                and len(value) <= 256
                and re.fullmatch(r"[a-zA-Z0-9_./: -]*", value)
            ):
                attributes.append(
                    {"key": "temper." + key, "value": {"stringValue": value}}
                )
            elif (
                key == "duration_ms"
                and type(value) in (int, float)
                and math.isfinite(value)
                and value >= 0
            ):
                attributes.append(
                    {"key": "temper.duration_ms", "value": {"doubleValue": value}}
                )
        # Untrusted event names, prompts, tool payloads and code are never sent.
        spans.append(
            {
                "traceId": receipt_digest[:32],
                "spanId": hashlib.sha256(
                    f"{receipt_digest}:{index}".encode()
                ).hexdigest()[:16],
                "name": "temper.harness",
                "kind": 1,
                "startTimeUnixNano": str(start),
                "endTimeUnixNano": str(end),
                "attributes": attributes,
            }
        )
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
                        "scope": {"name": "temper.harness", "version": "1"},
                        "spans": spans,
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
) -> dict:
    if not enabled:
        return {"status": "disabled"}
    endpoint = endpoint or endpoint_from_env(os.environ)
    if not endpoint:
        return {"status": "unavailable", "reason": "endpoint_missing"}
    try:
        if not math.isfinite(timeout) or not 0 < timeout <= 5:
            raise ValueError("export timeout must be within five seconds")
        digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
        body = json.dumps(
            packet(events, digest), allow_nan=False, separators=(",", ":")
        )
        if len(body.encode()) > MAX_BYTES:
            return {"status": "dropped", "reason": "payload_limit"}
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "dropped", "reason": "invalid_metadata"}
    headers = {}
    # Only explicit OTLP headers, never ambient service or model credentials.
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
    payload = json.dumps(
        {"endpoint": endpoint, "body": body, "headers": headers, "timeout": timeout}
    )
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--send"],
            input=payload,
            text=True,
            capture_output=True,
            timeout=timeout,
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
    cls = (
        http.client.HTTPSConnection
        if target.scheme == "https"
        else http.client.HTTPConnection
    )
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
        raise SystemExit(1)
