"""Tests for the Phase 2 canary registry + gate inventory extraction (U4).

The gate inventory is derived from ``scripts/manifest.yaml`` (entries with
``disposition: ci-gate``) -- never a hand-maintained list (KTD6) -- and
cross-referenced against ``ci-corpus/canaries.yaml``. These tests cover the
U4 scenarios of docs/plans/2026-08-02-032-feat-incident-corpus-oracle-plan.md:

1. every manifest ci-gate entry present in canaries.yaml -> N gates, covered;
2. a gate removed from canaries.yaml -> coverage violation, exit non-zero;
3. a disposition relaxed to utility -> no longer required;
4. an advisory gate registered with ``status: advisory`` does not trip the
   fail-closed requirement;
5. an empty canaries.yaml -> fail-closed, exit non-zero;
6. a non-detector ci-gate carries an explicit triage record; the extraction
   output names the coverage gap rather than treating it as covered.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_incident_corpus import (  # noqa: E402
    check_coverage,
    extract_ci_gate_inventory,
    run_corpus,
)

GATE = textwrap.dedent(
    """\
    import pathlib, sys
    target = pathlib.Path(sys.argv[1])
    text = target.read_text() if target.is_file() else ""
    sys.exit(1 if "BAD" in text else 0)
    """
)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _manifest_yaml(path: Path, gates: list[tuple[str, str]]) -> None:
    """gates: [(path, disposition), ...]"""
    lines = ["scripts:"]
    for p, disposition in gates:
        lines.append(f"  - path: {p}")
        lines.append(f"    disposition: {disposition}")
    _write(path, "\n".join(lines) + "\n")


def _canary(gate: str, **extra) -> dict:
    entry = {
        "gate": gate,
        "kind": "canary",
        "seed": "seed.txt",
        "pristine": "pristine.txt",
        "flags": ["{seed}"],
        "seed_exit_codes": [1],
        "status": "fail-closed",
        "evidence": "docs/evidence/placeholder.md",
    }
    entry.update(extra)
    return entry


def _canaries_yaml(repo: Path, entries: list[dict]) -> Path:
    body = ["phase: 2", "canaries:"]
    for e in entries:
        body.append("  - " + "\n    ".join(f"{k}: {v!r}" for k, v in e.items()))
    return _write(repo / "canaries.yaml", "\n".join(body) + "\n")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "scripts" / "gate_a.py", GATE)
    _write(repo / "scripts" / "gate_b.py", GATE)
    _write(repo / "seed.txt", "BAD\n")
    _write(repo / "pristine.txt", "GOOD\n")
    _write(repo / "docs" / "evidence" / "placeholder.md", "# ev\n")
    return repo


class TestInventoryExtraction:
    def test_extracts_only_ci_gate_disposition(self, tmp_path):
        manifest = tmp_path / "manifest.yaml"
        _manifest_yaml(
            manifest,
            [
                ("scripts/a.py", "ci-gate"),
                ("scripts/b.py", "utility"),
                ("scripts/c.py", "ci-gate"),
            ],
        )
        assert extract_ci_gate_inventory(manifest) == ["scripts/a.py", "scripts/c.py"]

    def test_snapshot_fully_present_reports_all_covered(self, tmp_path):
        repo = _repo(tmp_path)
        _manifest_yaml(repo / "scripts" / "manifest.yaml", [("scripts/gate_a.py", "ci-gate")])
        canaries = _canaries_yaml(repo, [_canary("scripts/gate_a.py")])
        inventory = extract_ci_gate_inventory(repo / "scripts" / "manifest.yaml")
        assert inventory == ["scripts/gate_a.py"]
        assert check_coverage(inventory, ["scripts/gate_a.py"]) == []
        assert run_corpus(canaries, repo) == 0

    def test_gate_removed_from_canaries_is_coverage_violation(self, tmp_path):
        repo = _repo(tmp_path)
        _manifest_yaml(
            repo / "scripts" / "manifest.yaml",
            [("scripts/gate_a.py", "ci-gate"), ("scripts/gate_b.py", "ci-gate")],
        )
        canaries = _canaries_yaml(repo, [_canary("scripts/gate_a.py")])
        assert run_corpus(canaries, repo) == 1

    def test_disposition_relaxed_to_utility_drops_requirement(self, tmp_path):
        repo = _repo(tmp_path)
        _manifest_yaml(
            repo / "scripts" / "manifest.yaml",
            [("scripts/gate_a.py", "ci-gate"), ("scripts/gate_b.py", "utility")],
        )
        canaries = _canaries_yaml(repo, [_canary("scripts/gate_a.py")])
        assert run_corpus(canaries, repo) == 0

    def test_advisory_gate_does_not_trip_fail_closed(self, tmp_path):
        repo = _repo(tmp_path)
        _manifest_yaml(repo / "scripts" / "manifest.yaml", [("scripts/gate_a.py", "ci-gate")])
        # Advisory: recorded from the workflow continue-on-error state (KTD11);
        # the must-bite requirement applies to fail-closed gates. An advisory
        # canary that fails to demonstrate bite is a named gap, not a failure.
        canaries = _canaries_yaml(
            repo,
            [
                _canary("scripts/gate_a.py", status="advisory"),
            ],
        )
        # With a working seed the advisory canary still PASSes.
        assert run_corpus(canaries, repo) == 0

    def test_empty_canaries_fails_closed(self, tmp_path):
        repo = _repo(tmp_path)
        _manifest_yaml(repo / "scripts" / "manifest.yaml", [("scripts/gate_a.py", "ci-gate")])
        canaries = _canaries_yaml(repo, [])
        assert run_corpus(canaries, repo) == 1

    def test_triage_record_names_the_gap(self, tmp_path):
        repo = _repo(tmp_path)
        _manifest_yaml(repo / "scripts" / "manifest.yaml", [("scripts/gate_a.py", "ci-gate")])
        canaries = _canaries_yaml(
            repo,
            [
                {
                    "gate": "scripts/gate_a.py",
                    "kind": "triage",
                    "triage_reason": "metrics recorder, not a detector gate -- "
                    "no failing case exists to seed; revisit when it gains a "
                    "fail-closed verdict",
                    "status": "fail-closed",
                }
            ],
        )
        # Triage records the coverage gap but do not demonstrate bite, so an
        # all-triage registry fails closed (zero executable canaries).
        assert run_corpus(canaries, repo) == 1

    def test_stale_canary_for_non_gate_is_reported(self, tmp_path):
        repo = _repo(tmp_path)
        _manifest_yaml(repo / "scripts" / "manifest.yaml", [("scripts/gate_a.py", "ci-gate")])
        canaries = _canaries_yaml(
            repo,
            [
                _canary("scripts/gate_a.py"),
                _canary("scripts/former_gate.py", status="advisory"),
            ],
        )
        assert run_corpus(canaries, repo) == 1
