"""Physics-side assertions for the intentionally unmaterialized U9 fixture."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
QUAL = ROOT / "power_pcb_dataset/qualification/isolation_joint"


def test_joint_candidate_has_no_geometry_or_timing_result_without_real_inputs() -> None:
    candidate = json.loads((QUAL / "combined_candidate.json").read_text(encoding="utf-8"))
    decision = json.loads((QUAL / "decision.json").read_text(encoding="utf-8"))
    assert candidate["status"] == "not-materialized"
    assert candidate["board"]["sha256"] is None
    assert candidate["captures"] == []
    assert decision["verdict"] == "stopped-indeterminate"
    assert decision["partial_result"] is None
    assert all(
        field not in decision
        for field in ("decomposed_total_ns", "direct_total_ns", "timing_pass")
    )
