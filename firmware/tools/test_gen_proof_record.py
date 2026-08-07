"""Host pytest for gen_proof_record.py (U7).

Run: uv run python -m pytest firmware/tools/test_gen_proof_record.py -v
"""

from __future__ import annotations

from gen_proof_record import OUTPUT_PATH, build_proof_record, render


class TestProofRecord:
    """Scenario 1: the gate passes on the current manifest and regenerates
    an identical proof record (byte-stable under regeneration)."""

    def test_all_passed_on_current_manifest(self):
        record = build_proof_record()
        assert record["all_passed"] is True
        assert record["invariant_count"] == 5

    def test_byte_stable_under_regeneration(self):
        r1 = render(build_proof_record())
        r2 = render(build_proof_record())
        assert r1 == r2

    def test_committed_record_matches_fresh_regeneration(self):
        """The committed proof_record.json must not have drifted from what
        gen_proof_record.py would write right now (scripts/check_firmware_
        invariants.py enforces this same check in CI as a DRIFT failure,
        distinct from an invariant VIOLATION)."""
        assert OUTPUT_PATH.exists(), "run firmware/tools/gen_proof_record.py and commit its output"
        committed = OUTPUT_PATH.read_text()
        fresh = render(build_proof_record())
        assert committed == fresh, "proof_record.json is stale -- regenerate and commit"

    def test_record_has_no_violations(self):
        record = build_proof_record()
        for inv in record["invariants"]:
            assert inv["violations"] == [], f"{inv['id']} has unexpected violations"
