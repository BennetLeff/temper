"""The live canary: opt-in, hashed evidence, and not one byte of content.

KTD8 makes this on-demand rather than a CI gate, following the repo's precedent for
a live oracle (``scripts/check_pad_world_position_oracle.py --verify-live-oracle``):
it needs a production key, so it runs when a human asks and commits hashed evidence.
R12 makes the consequence explicit -- **until this has run, the recorded tier is a
reproducibility instrument and nothing more.** This module is what earns the
stronger word.

What it does *not* do is compare content. It re-issues the captured probe set and
compares redacted shape summaries, so the evidence it writes can be committed
without carrying a request body, a response body, or a credential. What it is
looking for is the class of change that would break the client silently: a renamed
usage field, usage moving off the final stream chunk, a field disappearing, or a
refusal becoming a success.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from temper_harness.canary.shapes import compare_shapes, shape_digest, shape_of_exchange
from temper_harness.provider.deepseek import (
    MODEL,
    PROVIDER,
    fetch_account_models,
    is_event_stream,
)
from temper_harness.provider.errors import CredentialMissing
from temper_harness.provider.interface import OFFICIAL_HOST
from temper_harness.provider.probe import PROBE_SET, run_probe_set

EVIDENCE_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class ProbeComparison:
    """One probe's recorded shape against its live shape."""

    name: str
    http_status: int
    recorded_shape_digest: str
    live_shape_digest: str
    live_response_sha256: str
    live_response_bytes: int
    differences: tuple[str, ...] = field(default=())

    @property
    def matched(self) -> bool:
        return not self.differences

    def to_evidence(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "http_status": self.http_status,
            "recorded_shape_digest": self.recorded_shape_digest,
            "live_shape_digest": self.live_shape_digest,
            "response_sha256": self.live_response_sha256,
            "response_bytes": self.live_response_bytes,
            "matched": self.matched,
            "differences": list(self.differences),
        }


@dataclass(frozen=True, slots=True)
class CanaryReport:
    """The live verdict. ``ok`` is a shape claim, and only a shape claim."""

    captured_at: str
    harness_commit: str
    account_models: tuple[str, ...]
    comparisons: tuple[ProbeComparison, ...]

    @property
    def ok(self) -> bool:
        if not self.comparisons:
            # A vacuous agreement -- everything matched over no probes -- is not a
            # verdict, and it is the single most likely way for this instrument to
            # report green while measuring nothing. Written as an early return rather
            # than `bool(...) and all(...)` so the guard is visible to
            # check_vacuous_gates, which is a syntactic gate and considers only the
            # `not <collection>` idiom a guard.
            return False
        return all(item.matched for item in self.comparisons)

    @property
    def changed(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.comparisons if not item.matched)

    def summary(self) -> str:
        if not self.comparisons:
            return "the canary issued no probes, so its verdict is vacuous"
        if self.ok:
            return (
                f"{len(self.comparisons)} probe(s) matched the recorded shapes for "
                f"{MODEL}; Tier A is anchored to a live observation on {self.captured_at}"
            )
        return f"shape change in {list(self.changed)}; Tier A's recorded shapes are stale"

    def to_evidence(self) -> dict[str, Any]:
        return {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "provider": PROVIDER,
            "model": MODEL,
            "endpoint_host": OFFICIAL_HOST,
            "captured_at": self.captured_at,
            "harness_commit": self.harness_commit,
            "account_models": list(self.account_models),
            "verdict": "shape_stable" if self.ok else "shape_changed",
            "probes": [item.to_evidence() for item in self.comparisons],
        }


def recorded_shapes(recorded_dir: Path) -> dict[str, dict[str, Any]]:
    """The recorded corpus reduced to shapes, keyed by probe name."""
    manifest = json.loads((recorded_dir / "manifest.json").read_text(encoding="utf-8"))
    shapes: dict[str, dict[str, Any]] = {}
    for entry in manifest["probes"]:
        name = entry["name"]
        suffix = "sse" if entry["stream"] else "json"
        raw = (recorded_dir / f"{name}.response.{suffix}").read_bytes()
        meta = json.loads((recorded_dir / f"{name}.meta.json").read_text(encoding="utf-8"))
        shapes[name] = shape_of_exchange(
            http_status=meta["http_status"],
            raw=raw,
            content_type=meta["headers"].get("content-type"),
        )
    return shapes


def run_canary(
    *,
    api_key: str | None,
    recorded_dir: Path,
    timeout: float = 120.0,
    harness_commit: str = "UNKNOWN",
    now: dt.datetime | None = None,
) -> CanaryReport:
    """Issue the probe set live and compare its shapes to the recorded corpus.

    Without a key this raises :class:`CredentialMissing` rather than returning a
    clean report. That is U6's stated requirement and it is the reason the check is
    here rather than in a caller: a canary that skipped would report the same green
    verdict as one that ran, and the whole point of the evidence file is that it
    says which of the two happened.
    """
    if not api_key or not api_key.strip():
        raise CredentialMissing(
            "the canary needs a provisioned credential; refusing to report a verdict "
            "it did not measure"
        )

    shapes = recorded_shapes(recorded_dir)
    captures = run_probe_set(api_key, timeout=timeout)

    comparisons: list[ProbeComparison] = []
    for capture in captures:
        recorded = shapes.get(capture.name)
        live = shape_of_exchange(
            http_status=capture.http_status,
            raw=capture.body,
            content_type=capture.headers.get("content-type"),
        )
        differences = (
            ("no recorded shape for this probe",)
            if recorded is None
            else tuple(compare_shapes(recorded, live))
        )
        comparisons.append(
            ProbeComparison(
                name=capture.name,
                http_status=capture.http_status,
                recorded_shape_digest=shape_digest(recorded) if recorded else "",
                live_shape_digest=shape_digest(live),
                live_response_sha256=str(live["response_sha256"]),
                live_response_bytes=int(live["response_bytes"]),
                differences=differences,
            )
        )

    moment = now or dt.datetime.now(dt.UTC)
    return CanaryReport(
        captured_at=moment.replace(microsecond=0).isoformat(),
        harness_commit=harness_commit,
        account_models=tuple(fetch_account_models(api_key, timeout=min(timeout, 30.0))),
        comparisons=tuple(comparisons),
    )


def write_evidence(report: CanaryReport, path: Path) -> None:
    """Write the hashed evidence. Bodies are not available to write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_evidence(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def event_stream_names(recorded_dir: Path) -> list[str]:
    """Which probes in the corpus are streamed, for a caller that wants to assert it."""
    manifest = json.loads((recorded_dir / "manifest.json").read_text(encoding="utf-8"))
    return sorted(entry["name"] for entry in manifest["probes"] if entry["stream"])


def probe_names() -> tuple[str, ...]:
    """The probe set's names, so a test can assert the canary covers all of them."""
    return tuple(probe.name for probe in PROBE_SET)


__all__ = [
    "CanaryReport",
    "ProbeComparison",
    "event_stream_names",
    "is_event_stream",
    "probe_names",
    "recorded_shapes",
    "run_canary",
    "shape_of_exchange",
    "write_evidence",
]
