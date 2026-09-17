"""The canary's logic, checked without a network.

Everything here runs in CI. The live invocation is `test_canary_live.py`, which is
collect-ignored unless explicitly opted into -- and the difference matters, because
the requirement this file carries is that an unkeyed canary must *fail* rather than
skip. A skip reports the same green verdict as a run, which is the failure mode the
whole evidence file exists to prevent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from temper_harness.canary import (
    CanaryReport,
    ProbeComparison,
    recorded_shapes,
    run_canary,
)
from temper_harness.canary.runner import probe_names
from temper_harness.provider.errors import CredentialMissing
from tests import corpus

CAPTURED = Path(corpus.CAPTURED)
EVIDENCE = Path(__file__).resolve().parent / "evidence" / "canary.json"

#: Anything shaped like a provider key. A shape, not the value: the test must fail on
#: a leaked key without the key being present in the repository.
CREDENTIAL_SHAPE = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")


# -- the blocked case --------------------------------------------------------


@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_the_canary_without_a_key_is_a_typed_blocked_error(api_key: str | None) -> None:
    """Not a skip, and not a clean verdict.

    R12's whole point is that the difference between "the instrument ran" and "the
    instrument did not run" must be visible. A canary that returned a green report
    without a key would make the recorded tier look anchored when nothing anchored it.
    """
    with pytest.raises(CredentialMissing) as caught:
        run_canary(api_key=api_key, recorded_dir=CAPTURED)
    assert caught.value.retryable is False
    assert caught.value.category == "credential_missing"


# -- coverage of the corpus --------------------------------------------------


def test_the_canary_covers_every_probe_in_the_set() -> None:
    """Anti-vacuity: a canary that probed a subset would report on a subset."""
    shapes = recorded_shapes(CAPTURED)
    assert set(probe_names()) == set(shapes)
    assert len(shapes) > 1


def test_the_recorded_shapes_include_both_response_kinds() -> None:
    kinds = {shape["kind"] for shape in recorded_shapes(CAPTURED).values()}
    assert {"completion", "stream", "error_body"} <= kinds


# -- the verdict -------------------------------------------------------------


def test_a_report_with_a_shape_change_is_not_ok() -> None:
    """Scenario: a live shape change from the recorded corpus fails the canary."""
    report = CanaryReport(
        captured_at="2026-09-17T00:00:00+00:00",
        harness_commit="deadbeef",
        account_models=("deepseek-flash",),
        comparisons=(
            ProbeComparison(
                name="plain",
                http_status=200,
                recorded_shape_digest="a" * 64,
                live_shape_digest="b" * 64,
                live_response_sha256="c" * 64,
                live_response_bytes=10,
            ),
            ProbeComparison(
                name="stream_plain",
                http_status=200,
                recorded_shape_digest="d" * 64,
                live_shape_digest="e" * 64,
                live_response_sha256="f" * 64,
                live_response_bytes=20,
                differences=("usage_on_final_event: recorded True, live False",),
            ),
        ),
    )
    assert report.ok is False
    assert report.changed == ("stream_plain",)
    assert "stale" in report.summary()
    assert report.to_evidence()["verdict"] == "shape_changed"


def test_a_report_with_no_probes_is_not_ok() -> None:
    """The vacuous case, which is the one most likely to be mistaken for a pass."""
    report = CanaryReport(
        captured_at="2026-09-17T00:00:00+00:00",
        harness_commit="deadbeef",
        account_models=(),
        comparisons=(),
    )
    assert report.ok is False
    assert "vacuous" in report.summary()


# -- the committed evidence --------------------------------------------------


def test_the_committed_evidence_exists_and_is_well_formed() -> None:
    """The DoD's requirement: the canary ran once and its evidence is committed."""
    assert EVIDENCE.exists(), (
        f"{EVIDENCE} is missing. Run the canary with TEMPER_HARNESS_CANARY=1 and "
        "TEMPER_HARNESS_WRITE_CANARY_EVIDENCE=1, then commit the result -- or report "
        "plainly that S0's fidelity claim rests on reproducibility alone."
    )
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["schema_version"] == "1.0"
    assert evidence["model"] == "deepseek-flash"
    assert evidence["endpoint_host"] == "api.deepseek.com"
    assert evidence["verdict"] in {"shape_stable", "shape_changed"}
    assert evidence["probes"], "an evidence file with no probes proves nothing"
    assert evidence["captured_at"]


def test_the_evidence_carries_no_body_and_no_credential() -> None:
    """Scenario: the canary's committed evidence contains no request body, no response
    body, and no key material.

    Checked by shape rather than by field list, because the thing that would leak is a
    field nobody thought to enumerate.
    """
    text = EVIDENCE.read_text(encoding="utf-8")
    assert CREDENTIAL_SHAPE.search(text) is None
    assert "authorization" not in text.lower()
    assert "reasoning_content" not in text

    evidence = json.loads(text)
    allowed_probe_fields = {
        "name",
        "http_status",
        "recorded_shape_digest",
        "live_shape_digest",
        "response_sha256",
        "response_bytes",
        "matched",
        "differences",
    }
    for probe in evidence["probes"]:
        assert set(probe) == allowed_probe_fields, probe["name"]
        assert len(probe["response_sha256"]) == 64
        assert isinstance(probe["response_bytes"], int)
        # A difference names keys and values from a closed vocabulary, never prose.
        for difference in probe["differences"]:
            assert len(difference) < 400


def test_a_stable_verdict_means_tier_a_is_anchored() -> None:
    """The evidence and the claim have to agree, or the file is decoration."""
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    every_probe_matched = all(probe["matched"] for probe in evidence["probes"])
    assert evidence["verdict"] == ("shape_stable" if every_probe_matched else "shape_changed")
