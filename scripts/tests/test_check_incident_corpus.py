"""Tests for scripts/check_incident_corpus.py -- the shared runner.

Covers the U1 schema/resolution contract and the U2 verdict semantics of
docs/plans/2026-08-02-032-feat-incident-corpus-oracle-plan.md: PASS when the
seed is rejected and the pristine passes, FAIL naming which half broke
(regression: seed no longer rejected; over-broad: pristine now rejected),
UNVERIFIED for a gate error on the seed or a declared pristine-pending entry,
fail-closed on an empty corpus/canary set, and the per-phase liveness rules.

Every test builds a tiny synthetic repo under ``tmp_path`` with a synthetic
gate script and hand-written manifests, so the suite exercises the runner
mechanism itself rather than the real (growing) corpus.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_incident_corpus import (  # noqa: E402
    check_coverage,
    extract_ci_gate_inventory,
    load_manifest,
    run_corpus,
)

GATE = textwrap.dedent(
    """\
    import pathlib, sys
    args = sys.argv[1:]
    if args and args[0] == "--dir":
        target = pathlib.Path(args[1])
    else:
        target = pathlib.Path(args[0])
    if target.is_dir():
        text = "\\n".join(
            p.read_text() for p in sorted(target.rglob("*")) if p.is_file()
        )
    else:
        text = target.read_text()
    sys.exit(1 if "BAD" in text else 0)
    """
)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _mk_repo(tmp_path: Path, gate_body: str = GATE) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "scripts" / "fake_gate.py", gate_body)
    _write(repo / "docs" / "evidence" / "placeholder.md", "# evidence\n")
    return repo


def _incident(
    iid: str, cls: str, seed: str, pristine: str, gate: str = "scripts/fake_gate.py", **extra
) -> dict:
    entry = {
        "id": iid,
        "class": cls,
        "seed": seed,
        "pristine": pristine,
        "gate": gate,
        "flags": ["{seed}"],
        "seed_exit_codes": [1],
        "evidence": "docs/evidence/placeholder.md",
    }
    entry.update(extra)
    return entry


def _write_manifest(repo: Path, phase: int, entries: list[dict]) -> Path:
    key = "incidents" if phase == 1 else "canaries"
    body = [f"phase: {phase}", f"{key}:"]
    for e in entries:
        body.append("  - " + "\n    ".join(f"{k}: {v!r}" for k, v in e.items()))
    return _write(repo / ("incidents.yaml" if phase == 1 else "canaries.yaml"), "\n".join(body) + "\n")


# ---------------------------------------------------------------------------
# U2 scenarios 1-4: the four verdict classes on a synthetic gate
# ---------------------------------------------------------------------------


class TestVerdictSemantics:
    def _happy_repo(self, tmp_path, gate_body=GATE) -> tuple[Path, Path]:
        repo = _mk_repo(tmp_path, gate_body)
        _write(repo / "seed.txt", "GOOD\n")  # will be replaced by BAD below
        _write(repo / "pristine.txt", "GOOD\n")
        return repo, _write_manifest(
            repo,
            1,
            [
                _incident(
                    "inc-x",
                    "test",
                    "seed.txt",
                    "pristine.txt",
                )
            ],
        )

    def test_happy_path_reports_pass(self, tmp_path):
        repo, manifest = self._happy_repo(tmp_path)
        _write(repo / "seed.txt", "BAD\n")  # seed contains the marker
        assert run_corpus(manifest, repo) == 0

    def test_regression_seed_no_longer_rejected(self, tmp_path):
        # The gate is weakened: it now accepts the seeded bad file.
        weakened = GATE.replace('sys.exit(1 if "BAD" in text else 0)', "sys.exit(0)")
        repo, manifest = self._happy_repo(tmp_path, gate_body=weakened)
        _write(repo / "seed.txt", "BAD\n")
        assert run_corpus(manifest, repo) == 1

    def test_over_broad_gate_rejects_pristine(self, tmp_path):
        overbroad = GATE.replace('sys.exit(1 if "BAD" in text else 0)', "sys.exit(1)")
        repo, manifest = self._happy_repo(tmp_path, gate_body=overbroad)
        _write(repo / "seed.txt", "BAD\n")
        assert run_corpus(manifest, repo) == 1

    def test_gate_crash_on_seed_is_unverified_not_pass(self, tmp_path):
        # Gate exits 2 (not a recorded rejection code): a gate error, which
        # must NOT be mistaken for a rejection -- computed UNVERIFIED, which
        # fails the Phase 1 run (the fixture is broken).
        crashing = GATE.replace('sys.exit(1 if "BAD" in text else 0)', "sys.exit(2)")
        repo, manifest = self._happy_repo(tmp_path, gate_body=crashing)
        _write(repo / "seed.txt", "BAD\n")
        assert run_corpus(manifest, repo) == 1


# ---------------------------------------------------------------------------
# U1 schema + resolution + U2 fail-closed-on-empty
# ---------------------------------------------------------------------------


class TestSchemaAndFailClosed:
    def test_empty_corpus_fails_closed(self, tmp_path):
        repo = _mk_repo(tmp_path)
        manifest = _write_manifest(repo, 1, [])
        assert run_corpus(manifest, repo) == 1

    def test_missing_expected_gate_field_is_named_failure(self, tmp_path):
        repo = _mk_repo(tmp_path)
        _write(repo / "seed.txt", "BAD\n")
        _write(repo / "pristine.txt", "GOOD\n")
        entry = _incident("inc-no-gate", "test", "seed.txt", "pristine.txt")
        del entry["gate"]
        manifest = _write_manifest(repo, 1, [entry])
        assert run_corpus(manifest, repo) == 1

    def test_unresolvable_seed_path_is_named_failure(self, tmp_path):
        repo = _mk_repo(tmp_path)
        _write(repo / "pristine.txt", "GOOD\n")
        manifest = _write_manifest(
            repo, 1, [_incident("inc-missing-seed", "test", "does/not/exist.txt", "pristine.txt")]
        )
        assert run_corpus(manifest, repo) == 1

    def test_duplicate_incident_id_is_named_failure(self, tmp_path):
        repo = _mk_repo(tmp_path)
        _write(repo / "seed.txt", "BAD\n")
        _write(repo / "pristine.txt", "GOOD\n")
        a = _incident("dup", "test", "seed.txt", "pristine.txt")
        manifest = _write_manifest(repo, 1, [a, dict(a)])
        assert run_corpus(manifest, repo) == 1

    def test_missing_phase_is_named_failure(self, tmp_path):
        repo = _mk_repo(tmp_path)
        manifest = _write(repo / "bad.yaml", "incidents: []\n")
        assert run_corpus(manifest, repo) == 1

    def test_well_formed_entry_validates_and_resolves(self, tmp_path):
        repo = _mk_repo(tmp_path)
        _write(repo / "seed.txt", "BAD\n")
        _write(repo / "pristine.txt", "GOOD\n")
        _write(repo / "docs" / "evidence" / "placeholder.md", "# ev\n")
        manifest = _write_manifest(
            repo, 1, [_incident("inc-ok", "test", "seed.txt", "pristine.txt")]
        )
        doc = load_manifest(manifest, repo)
        assert doc["phase"] == 1
        assert len(doc["incidents"]) == 1
        assert run_corpus(manifest, repo) == 0


# ---------------------------------------------------------------------------
# U1 scenario 6 / U2 scenario 7: directory-scanning entries (KTD7)
# ---------------------------------------------------------------------------


class TestDirectoryScanningEntries:
    def test_materialized_seed_dir_flips_gate_and_pristine_passes(self, tmp_path):
        """A directory-scanning gate: the recorded flags drive the invocation,
        the seed directory tree is materialized and the pristine directory
        passes."""
        repo = _mk_repo(tmp_path)
        _write(repo / "seed" / "scripts" / "bad.py", "# BAD marker\n")
        _write(repo / "seed" / "packages" / "demo" / "src" / "clean.py", "x = 1\n")
        _write(repo / "pristine" / "scripts" / "good.py", "# clean\n")
        _write(repo / "pristine" / "packages" / "demo" / "src" / "clean.py", "x = 1\n")
        manifest = _write_manifest(
            repo,
            1,
            [
                _incident(
                    "inc-dir",
                    "test",
                    "seed",
                    "pristine",
                    flags=["--dir", "{seed}"],
                    layout="directory",
                )
            ],
        )
        assert run_corpus(manifest, repo) == 0


# ---------------------------------------------------------------------------
# U2 scenarios 8-10 + U4 scenarios 1-2, 5: Phase 2 liveness and coverage
# ---------------------------------------------------------------------------


class TestPhase2LivenessAndCoverage:
    def _canary(self, seed: str, pristine: str, **extra) -> dict:
        entry = {
            "gate": "scripts/fake_gate.py",
            "kind": "canary",
            "seed": seed,
            "pristine": pristine,
            "flags": ["{seed}"],
            "seed_exit_codes": [1],
            "status": "fail-closed",
            "evidence": "docs/evidence/placeholder.md",
        }
        entry.update(extra)
        return entry

    def test_phase2_canary_whose_gate_accepts_seed_fails_as_regression(self, tmp_path):
        weakened = GATE.replace('sys.exit(1 if "BAD" in text else 0)', "sys.exit(0)")
        repo = _mk_repo(tmp_path, gate_body=weakened)
        _write(repo / "seed.txt", "BAD\n")
        _write(repo / "pristine.txt", "GOOD\n")
        _write(repo / "scripts" / "manifest.yaml", "scripts: []\n")  # empty inventory for the coverage side
        manifest = _write_manifest(repo, 2, [self._canary("seed.txt", "pristine.txt")])
        # Phase 2: any non-PASS fails -- regression FAIL here.
        assert run_corpus(manifest, repo) == 1

    def test_phase1_pristine_pending_passes_with_reason(self, tmp_path):
        repo = _mk_repo(tmp_path)
        _write(repo / "seed.txt", "BAD\n")
        _write(repo / "docs" / "evidence" / "placeholder.md", "# ev\n")
        entry = _incident(
            "inc-pending",
            "board",
            "seed.txt",
            "pending",
            pristine_pending_reason="defect still on main; pristine lands with the fix",
        )
        manifest = _write_manifest(repo, 1, [entry])
        assert run_corpus(manifest, repo) == 0

    def test_phase2_pristine_pending_fails(self, tmp_path):
        repo = _mk_repo(tmp_path)
        _write(repo / "seed.txt", "BAD\n")
        _write(repo / "docs" / "evidence" / "placeholder.md", "# ev\n")
        _write(repo / "scripts" / "manifest.yaml", "scripts: []\n")
        entry = self._canary("seed.txt", "pending", pristine_pending_reason="n/a")
        manifest = _write_manifest(repo, 2, [entry])
        assert run_corpus(manifest, repo) == 1

    def test_empty_canary_set_fails_closed(self, tmp_path):
        repo = _mk_repo(tmp_path)
        manifest = _write_manifest(repo, 2, [])
        assert run_corpus(manifest, repo) == 1

    def test_all_triage_canaries_fail_closed_zero_executable(self, tmp_path):
        repo = _mk_repo(tmp_path)
        _write(repo / "scripts" / "manifest.yaml", "scripts: []\n")
        triage = {
            "gate": "scripts/fake_gate.py",
            "kind": "triage",
            "triage_reason": "not a detector gate -- no fail case to seed",
            "status": "fail-closed",
        }
        manifest = _write_manifest(repo, 2, [triage])
        assert run_corpus(manifest, repo) == 1

    def test_coverage_missing_gate_fails_and_removal_from_manifest_relaxes(self, tmp_path):
        repo = _mk_repo(tmp_path)
        _write(repo / "seed.txt", "BAD\n")
        _write(repo / "pristine.txt", "GOOD\n")
        # Two ci-gates in the inventory; canaries.yaml covers only one.
        _write(
            repo / "scripts" / "manifest.yaml",
            "scripts:\n"
            "  - path: scripts/fake_gate.py\n    disposition: ci-gate\n"
            "  - path: scripts/other_gate.py\n    disposition: ci-gate\n",
        )
        manifest = _write_manifest(repo, 2, [self._canary("seed.txt", "pristine.txt")])
        assert run_corpus(manifest, repo) == 1

        # Once the second gate's disposition is relaxed to utility, it is no
        # longer required to carry a canary (documented intended relaxation).
        _write(
            repo / "scripts" / "manifest.yaml",
            "scripts:\n"
            "  - path: scripts/fake_gate.py\n    disposition: ci-gate\n"
            "  - path: scripts/other_gate.py\n    disposition: utility\n",
        )
        assert run_corpus(manifest, repo) == 0

    def test_extract_inventory_filters_disposition(self, tmp_path):
        manifest = _write(
            tmp_path / "manifest.yaml",
            "scripts:\n"
            "  - path: a.py\n    disposition: ci-gate\n"
            "  - path: b.py\n    disposition: utility\n"
            "  - path: packages/x/scripts/c.py\n    disposition: ci-gate\n",
        )
        # Bare manifest filenames normalize to scripts/<name>; nested paths
        # pass through unchanged.
        assert extract_ci_gate_inventory(manifest) == [
            "packages/x/scripts/c.py",
            "scripts/a.py",
        ]

    def test_check_coverage_reports_missing_and_stale(self, tmp_path):
        violations = check_coverage(["a.py", "b.py"], ["a.py", "c.py"])
        assert any("b.py" in v for v in violations)
        assert any("c.py" in v for v in violations)
