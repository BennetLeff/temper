"""Tests for scripts/known_failure_pins.py.

Three behaviours are load-bearing for this mechanism (see the module
docstring and docs/solutions/best-practices/pin-known-failure-reasons-
2026-07-30.md for the full rationale -- the PR #460 near-miss this exists to
prevent):

1. A failure signature that matches a declared pin is reported as KNOWN.
2. A failure signature that differs from a declared pin -- even by one
   extra entry -- is reported LOUDLY as a changed reason, distinguishable
   from the known-reason message.
3. A test with no pin at all gets its failure message back completely
   unchanged: the mechanism cannot be used to silence an undeclared failure.

The registry-validation gate (``main``) is tested separately: it must reject
a dangling issue link, an expired pin, a pin whose lifetime exceeds the cap,
an orphaned nodeid, and a registry over the live-pin cap -- the anti-
suppression ratchet.

Signatures below deliberately mirror the shape ``test_golden_board_drc_
regression`` actually produces (``dict(sorted(fixable_counts.items()))``),
using the PR #460 scenario concretely: a pinned rotation-writer defect
(1 shorting_items + 1 solder_mask_bridge) versus that same signature plus one
EXTRA, unrelated shorting_items entry -- standing in for the destructive
DC_BUS+/SW_NODE short PR #460 introduced. The point of this mechanism is
exactly that these two must not be mistakable for each other.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from known_failure_pins import (  # noqa: E402
    KnownFailurePin,
    PinRegistryError,
    annotate_failure,
    check_signature,
    load_pins,
    main,
)

NODEID = "packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_golden_board_drc_regression"

# The "reason A" signature: the rotation-writer defect (docs/evidence/
# 2026-07-30-placement-writer-rotation.md Sec 3.2) -- 1 shorting_items,
# 1 solder_mask_bridge.
ROTATION_WRITER_SIGNATURE = {"shorting_items": 1, "solder_mask_bridge": 1}

# The "reason B" signature: the same defect PLUS one extra shorting_items
# entry that was never part of the pin -- standing in for PR #460's
# DC_BUS+/SW_NODE short. Same shape, genuinely different failure.
HV_SHORT_SIGNATURE = {"shorting_items": 2, "solder_mask_bridge": 1}


def _pin(
    *,
    signature: dict = ROTATION_WRITER_SIGNATURE,
    issue: str = "docs/evidence/2026-07-30-placement-writer-rotation.md",
    declared: str = "2026-07-30",
    expires: str = "2026-08-13",
    reason: str = "Writer drops solved rotation, producing intra-net shorts.",
) -> dict[str, KnownFailurePin]:
    return {
        NODEID: KnownFailurePin(
            nodeid=NODEID,
            issue=issue,
            declared=dt.date.fromisoformat(declared),
            expires=dt.date.fromisoformat(expires),
            reason=reason,
            signature=dict(signature),
        )
    }


TODAY = dt.date(2026, 8, 1)


class TestKnownReasonRecognised:
    def test_matching_signature_is_known(self):
        verdict = check_signature(NODEID, ROTATION_WRITER_SIGNATURE, pins=_pin(), today=TODAY)
        assert verdict.status == "known"
        assert "KNOWN-FAILURE, pinned" in verdict.message
        assert "docs/evidence/2026-07-30-placement-writer-rotation.md" in verdict.message
        assert str(ROTATION_WRITER_SIGNATURE) in verdict.message

    def test_annotate_failure_prefixes_base_message(self):
        base = "AssertionError: Expected 0 fixable shorting_items, got 1."
        annotated = annotate_failure(NODEID, ROTATION_WRITER_SIGNATURE, base, pins=_pin(), today=TODAY)
        assert "[KNOWN-FAILURE, pinned]" in annotated
        assert base in annotated  # original message is preserved, not replaced


class TestChangedReasonIsLoud:
    def test_extra_violation_is_reported_as_changed(self):
        verdict = check_signature(NODEID, HV_SHORT_SIGNATURE, pins=_pin(), today=TODAY)
        assert verdict.status == "changed"
        assert "PIN MISMATCH" in verdict.message
        # Both signatures must be visible, so a reader can see exactly what moved.
        assert str(ROTATION_WRITER_SIGNATURE) in verdict.message
        assert str(HV_SHORT_SIGNATURE) in verdict.message

    def test_changed_message_is_distinguishable_from_known_message(self):
        known = check_signature(NODEID, ROTATION_WRITER_SIGNATURE, pins=_pin(), today=TODAY).message
        changed = check_signature(NODEID, HV_SHORT_SIGNATURE, pins=_pin(), today=TODAY).message
        assert known != changed
        assert "PIN MISMATCH" in changed and "PIN MISMATCH" not in known
        assert "Do NOT assume this is the pinned issue" in changed

    def test_annotate_failure_surfaces_mismatch_in_raised_message(self):
        base = "AssertionError: Expected 0 fixable shorting_items, got 2."
        annotated = annotate_failure(NODEID, HV_SHORT_SIGNATURE, base, pins=_pin(), today=TODAY)
        assert "KNOWN-FAILURE PIN MISMATCH" in annotated
        assert base in annotated

    def test_single_extra_key_also_counts_as_changed(self):
        # A signature that is a superset of the pin (new violation TYPE, not
        # just a new count) must not be mistaken for a match either.
        superset = dict(ROTATION_WRITER_SIGNATURE, copper_edge_clearance=1)
        verdict = check_signature(NODEID, superset, pins=_pin(), today=TODAY)
        assert verdict.status == "changed"


class TestUndeclaredFailureIsNeverSilenced:
    def test_no_pin_returns_unpinned(self):
        verdict = check_signature("some/other/test.py::test_unrelated", {"shorting_items": 5}, pins=_pin(), today=TODAY)
        assert verdict.status == "unpinned"
        assert verdict.message == ""

    def test_annotate_failure_is_identity_for_unpinned_test(self):
        base = "AssertionError: Expected 0 fixable shorting_items, got 5."
        annotated = annotate_failure(
            "some/other/test.py::test_unrelated", {"shorting_items": 5}, base, pins=_pin(), today=TODAY
        )
        assert annotated == base

    def test_empty_registry_never_intercepts_anything(self):
        base = "AssertionError: something failed."
        annotated = annotate_failure(NODEID, HV_SHORT_SIGNATURE, base, pins={}, today=TODAY)
        assert annotated == base


class TestExpiryDegradesToUnpinned:
    def test_expired_pin_is_reported_expired_not_known(self):
        pins = _pin(expires="2026-07-31")
        verdict = check_signature(NODEID, ROTATION_WRITER_SIGNATURE, pins=pins, today=dt.date(2026, 8, 1))
        assert verdict.status == "expired"
        assert "PIN EXPIRED" in verdict.message

    def test_expired_pin_does_not_match_even_the_pinned_signature(self):
        # An expired pin matching its own signature must NOT report "known" --
        # otherwise expiry would be decorative rather than enforced.
        pins = _pin(expires="2026-07-31")
        verdict = check_signature(NODEID, ROTATION_WRITER_SIGNATURE, pins=pins, today=dt.date(2026, 8, 1))
        assert verdict.status != "known"


class TestLoadPinsValidation:
    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert load_pins(tmp_path / "nonexistent.yaml") == {}

    def test_valid_registry_round_trips(self, tmp_path: Path):
        reg = tmp_path / "known-failure-pins.yaml"
        reg.write_text(
            f"""
{NODEID}:
  issue: docs/evidence/2026-07-30-placement-writer-rotation.md
  declared: "2026-07-30"
  expires: "2026-08-13"
  reason: "Writer drops solved rotation."
  signature:
    shorting_items: 1
    solder_mask_bridge: 1
"""
        )
        pins = load_pins(reg)
        assert NODEID in pins
        assert pins[NODEID].signature == ROTATION_WRITER_SIGNATURE

    @pytest.mark.parametrize(
        "body,expected_fragment",
        [
            ("- not a mapping\n", "must be a mapping"),
            (f"{NODEID}:\n  issue: x\n", "missing required field"),
            (
                f"{NODEID}:\n  issue: x\n  declared: '2026-07-30'\n  expires: '2026-08-13'\n"
                "  reason: r\n  signature: {}\n",
                "signature must be a non-empty mapping",
            ),
            (
                f"{NODEID}:\n  issue: x\n  declared: not-a-date\n  expires: '2026-08-13'\n"
                "  reason: r\n  signature: {shorting_items: 1}\n",
                "not an ISO date",
            ),
        ],
    )
    def test_malformed_registry_raises(self, tmp_path: Path, body: str, expected_fragment: str):
        reg = tmp_path / "known-failure-pins.yaml"
        reg.write_text(body)
        with pytest.raises(PinRegistryError, match=expected_fragment):
            load_pins(reg)


class TestGateIsARatchetNotASuppressionList:
    """Exercises main() -- the CI-facing registry validator."""

    def _write(self, tmp_path: Path, body: str) -> Path:
        reg = tmp_path / "known-failure-pins.yaml"
        reg.write_text(body)
        return reg

    def test_empty_registry_passes(self, tmp_path: Path):
        reg = self._write(tmp_path, "# nothing pinned\n")
        assert main(["--registry", str(reg)]) == 0

    def test_dangling_issue_link_fails(self, tmp_path: Path, capsys):
        reg = self._write(
            tmp_path,
            f"""
{NODEID}:
  issue: docs/evidence/does-not-exist-2026-07-30.md
  declared: "2026-07-30"
  expires: "2026-08-13"
  reason: "r"
  signature:
    shorting_items: 1
""",
        )
        assert main(["--registry", str(reg)]) == 1
        assert "ORPHAN_ISSUE_LINK" in capsys.readouterr().out

    def test_expired_pin_fails_the_gate(self, tmp_path: Path, capsys):
        # A real, existing evidence doc so only expiry trips the gate.
        reg = self._write(
            tmp_path,
            """
packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_golden_board_drc_regression:
  issue: docs/evidence/2026-07-30-placement-writer-rotation.md
  declared: "2026-01-01"
  expires: "2026-01-15"
  reason: "r"
  signature:
    shorting_items: 1
""",
        )
        assert main(["--registry", str(reg)]) == 1
        assert "EXPIRED_PIN" in capsys.readouterr().out

    def test_lifetime_exceeding_cap_fails(self, tmp_path: Path, capsys):
        reg = self._write(
            tmp_path,
            """
packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_golden_board_drc_regression:
  issue: docs/evidence/2026-07-30-placement-writer-rotation.md
  declared: "2026-07-01"
  expires: "2026-12-01"
  reason: "r"
  signature:
    shorting_items: 1
""",
        )
        assert main(["--registry", str(reg)]) == 1
        assert "PIN_LIFETIME_OUT_OF_RANGE" in capsys.readouterr().out

    def test_orphan_nodeid_fails(self, tmp_path: Path, capsys):
        reg = self._write(
            tmp_path,
            """
packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_this_test_does_not_exist:
  issue: docs/evidence/2026-07-30-placement-writer-rotation.md
  declared: "2026-07-30"
  expires: "2026-08-13"
  reason: "r"
  signature:
    shorting_items: 1
""",
        )
        assert main(["--registry", str(reg)]) == 1
        assert "ORPHAN_PIN" in capsys.readouterr().out

    def test_too_many_live_pins_fails(self, tmp_path: Path, capsys):
        entries = "\n".join(
            f"""
some/fake/test_module_{i}.py::test_fake_{i}:
  issue: docs/evidence/2026-07-30-placement-writer-rotation.md
  declared: "2026-07-30"
  expires: "2026-08-13"
  reason: "r"
  signature:
    shorting_items: {i}
"""
            for i in range(5)
        )
        reg = self._write(tmp_path, entries)
        assert main(["--registry", str(reg)]) == 1
        assert "TOO_MANY_PINS" in capsys.readouterr().out

    def test_valid_single_pin_passes(self, tmp_path: Path, capsys):
        # Uses the real, currently-red-free test and a real evidence doc so
        # every other check (issue link, orphan nodeid) legitimately passes;
        # only the ratchet's structural checks are exercised elsewhere above.
        future_expiry = (dt.date.today() + dt.timedelta(days=10)).isoformat()
        reg = self._write(
            tmp_path,
            f"""
{NODEID}:
  issue: docs/evidence/2026-07-30-placement-writer-rotation.md
  declared: "{dt.date.today().isoformat()}"
  expires: "{future_expiry}"
  reason: "r"
  signature:
    shorting_items: 1
""",
        )
        assert main(["--registry", str(reg)]) == 0
        assert "KNOWN-FAILURE-PINS OK" in capsys.readouterr().out
