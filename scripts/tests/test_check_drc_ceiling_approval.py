"""Tests for check_drc_ceiling_approval.py.

The CI gate that wires ``DrcRatchet.detect_ceiling_raise`` (previously
exercised only by its own unit tests -- see
``packages/temper-placer/tests/regression/test_drc_ratchet.py``) into an
actual PR check. Each test builds a real, throwaway git repository under
``tmp_path`` -- a base commit (playing the role of ``origin/main``) and one
or more commits on top of it (playing the role of the PR branch) -- and
runs ``run_gate`` against it directly. No ``git stash`` is used anywhere;
every repo is a fresh ``tmp_path`` fixture.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "packages" / "temper-placer" / "src")
)

from check_drc_ceiling_approval import (  # noqa: E402
    EXIT_OK,
    EXIT_TOOL_ERROR,
    EXIT_UNAPPROVED_RAISE,
    run_gate,
)

CEILING_RELPATH = "power_pcb_dataset/drc_ceiling.json"

BASE_CEILING = {
    "boards": [
        {
            "board_id": "temper",
            "path": "pcb/temper.kicad_pcb",
            "error_ceiling": 1017,
            "warning_ceiling": 762,
            "violations_by_type": {"clearance": 502, "hole_clearance": 120},
            "warnings_by_type": {"silk_overlap": 119},
        }
    ]
}

BOARD_CONTENT_V1 = b"board-content-v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_pcb(repo: Path, content: bytes = BOARD_CONTENT_V1) -> str:
    """Write the board file the ceiling measures and return its hash --
    the measurement-evidence contract hashes the file on disk, so every
    compliant-raise fixture needs a real board to hash against.
    """
    pcb = repo / "pcb" / "temper.kicad_pcb"
    pcb.parent.mkdir(parents=True, exist_ok=True)
    pcb.write_bytes(content)
    return _sha256(content)


def _provenance(board_sha: str, **overrides: object) -> dict:
    """A valid measured-live provenance block (the real record's shape:
    sample count in measured_via prose, the legacy default)."""
    prov: dict = {
        "measured_at_commit": "a" * 40,
        "dirty": False,
        "inputs": [{"path": "pcb/temper.kicad_pcb", "sha256": board_sha}],
        "tool_versions": {"kicad-cli": "10.0.4"},
        "source": "measured-live",
        "measured_via": (
            "temper_placer.validation._drc_api.run_drc with --all-track-errors "
            "(120 samples; see nondeterministic_error_types.clearance.samples)"
        ),
    }
    prov.update(overrides)
    return prov


def _raised_compliant_ceiling(repo: Path, base: dict = BASE_CEILING) -> dict:
    """The compliant row of the contract matrix as a new ceiling: a raise
    (aggregate error_ceiling +3) backed by a new non-empty ``_march`` entry
    and a fresh measured-live provenance whose input hash matches the board
    file just written to disk. The merge-base record (BASE_CEILING) has no
    ``_march``, so both entries here count as new -- the contract only needs
    at least one non-empty one.
    """
    board_sha = _write_pcb(repo)
    raised = json.loads(json.dumps(base))
    entry = raised["boards"][0]
    entry["error_ceiling"] = entry["error_ceiling"] + 3
    entry["nondeterministic_error_types"] = {
        "clearance": {"observed": [499, 500, 501], "samples": 120, "note": "only nondeterministic category"}
    }
    entry["provenance"] = _provenance(board_sha)
    raised["_march"] = {
        "2026-07-30": "prior entry (base state)",
        "2026-08-02": "attributed cause: U3 footprint resync (commit abc123)",
    }
    return raised


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    _git(["init", "-q", "-b", "work"], tmp_path)
    _git(["config", "user.email", "test@example.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)
    _git(["config", "commit.gpgsign", "false"], tmp_path)
    return tmp_path


def _write_ceiling(repo: Path, ceiling: dict) -> None:
    ceiling_dir = repo / "power_pcb_dataset"
    ceiling_dir.mkdir(parents=True, exist_ok=True)
    (ceiling_dir / "drc_ceiling.json").write_text(json.dumps(ceiling, indent=2) + "\n")


def _commit(repo: Path, message: str) -> str:
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", message], repo)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _base_repo(tmp_path: Path, ceiling: dict = BASE_CEILING) -> Path:
    """A repo with one commit (the "origin/main" base state), an
    ``origin/main`` ref pointing at it, and HEAD still on that same commit
    -- callers add PR commits on top of this.
    """
    repo = _init_repo(tmp_path)
    _write_ceiling(repo, ceiling)
    (repo / "README.md").write_text("base\n")
    _commit(repo, "base: initial ceiling")
    _git(["branch", "origin/main"], repo)
    return repo


class TestRaiseWithoutTrailerFails:
    def test_aggregate_error_ceiling_raise_no_trailer_fails(self, tmp_path):
        repo = _base_repo(tmp_path)
        raised = json.loads(json.dumps(BASE_CEILING))
        raised["boards"][0]["error_ceiling"] = 1020
        _write_ceiling(repo, raised)
        _commit(repo, "measured DRC nondeterminism, ceiling raised")

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_UNAPPROVED_RAISE
        assert "error_ceiling 1017 -> 1020" in message
        assert "requires explicit approval" in message

    def test_per_type_error_ceiling_raise_no_trailer_fails(self, tmp_path):
        repo = _base_repo(tmp_path)
        raised = json.loads(json.dumps(BASE_CEILING))
        raised["boards"][0]["violations_by_type"]["clearance"] = 600
        _write_ceiling(repo, raised)
        _commit(repo, "fix: whatever")

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_UNAPPROVED_RAISE
        assert "violations_by_type[clearance] 502 -> 600" in message

    def test_approval_trailer_must_be_on_a_pr_commit_not_missing_entirely(self, tmp_path):
        repo = _base_repo(tmp_path)
        raised = json.loads(json.dumps(BASE_CEILING))
        raised["boards"][0]["error_ceiling"] = 1020
        _write_ceiling(repo, raised)
        _commit(repo, "raise ceiling, mention approval in prose only sort of")

        exit_code, _message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")
        assert exit_code == EXIT_UNAPPROVED_RAISE


class TestRaiseWithTrailerPasses:
    def test_aggregate_error_ceiling_raise_with_trailer_passes(self, tmp_path):
        repo = _base_repo(tmp_path)
        raised = _raised_compliant_ceiling(repo)
        _write_ceiling(repo, raised)
        _commit(
            repo,
            "fix(drc): raise error_ceiling for measured nondeterminism\n\n"
            "Ceiling-Approval: reviewer-id",
        )

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_OK
        assert "PASS" in message
        assert "satisfies the measurement-evidence contract" in message

    def test_trailer_on_an_earlier_pr_commit_still_counts(self, tmp_path):
        """The trailer just needs to be on *a* commit in the PR, not
        necessarily the last one that touches the ceiling file.
        """
        repo = _base_repo(tmp_path)
        (repo / "NOTES.md").write_text("unrelated prep work\n")
        _commit(repo, "prep: add notes\n\nCeiling-Approval: reviewer-id")

        raised = _raised_compliant_ceiling(repo)
        _write_ceiling(repo, raised)
        _commit(repo, "raise the ceiling")

        exit_code, _message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")
        assert exit_code == EXIT_OK


class TestRaiseWithTrailerButNoCauseFails:
    """U1 scenario 2 at the gate level: the bare legacy string
    ('Ceiling-Approval: reviewer-id') with a valid measurement but no new
    ``_march`` entry must fail, naming the missing cause -- the _march log
    is the single cause authority, not the trailer body."""

    def test_bare_legacy_trailer_without_march_entry_fails(self, tmp_path):
        repo = _base_repo(tmp_path)
        board_sha = _write_pcb(repo)
        raised = json.loads(json.dumps(BASE_CEILING))
        raised["boards"][0]["error_ceiling"] = 1020
        raised["boards"][0]["nondeterministic_error_types"] = {
            "clearance": {"samples": 120, "observed": [499, 500, 501]}
        }
        raised["boards"][0]["provenance"] = _provenance(board_sha)  # measurement is fine
        # no "_march" key at all -> no attributed cause
        _write_ceiling(repo, raised)
        _commit(
            repo,
            "fix(drc): raise ceiling for measured noise\n\nCeiling-Approval: reviewer-id",
        )

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_UNAPPROVED_RAISE
        assert "measurement-evidence contract" in message
        assert "no attributed cause" in message


class TestRaiseWithCauseButBadMeasurementEvidenceFails:
    """U2 corpus: a trailer plus a cause, but the raised board's provenance
    record fails one evidence dimension -- each shape fails with the
    specific reason named."""

    def _approved_raise(self, repo: Path, mutate) -> None:
        raised = _raised_compliant_ceiling(repo)
        mutate(raised["boards"][0])
        _write_ceiling(repo, raised)
        _commit(
            repo,
            "fix(drc): raise ceiling\n\nCeiling-Approval: reviewer-id",
        )

    def test_stale_input_hash_fails(self, tmp_path):
        repo = _base_repo(tmp_path)
        self._approved_raise(repo, lambda entry: None)
        # board moved after the measurement: the recorded hash no longer
        # matches the file on disk
        (repo / "pcb" / "temper.kicad_pcb").write_bytes(b"board-content-v2")

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_UNAPPROVED_RAISE
        assert "STALE measurement" in message

    def test_under_sampled_structured_field_fails_naming_sample_count(self, tmp_path):
        repo = _base_repo(tmp_path)
        self._approved_raise(
            repo,
            lambda entry: entry["provenance"].update({"sample_count": 60}),
        )

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_UNAPPROVED_RAISE
        assert "60" in message
        assert "at least 120 samples" in message

    def test_under_sampled_legacy_prose_fails(self, tmp_path):
        repo = _base_repo(tmp_path)
        self._approved_raise(
            repo,
            lambda entry: entry["provenance"].update(
                {
                    "sample_count": None,
                    "measured_via": "run_drc with --all-track-errors (60 samples)",
                }
            ),
        )

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_UNAPPROVED_RAISE
        assert "at least 120 samples" in message

    def test_backfilled_historical_source_fails(self, tmp_path):
        repo = _base_repo(tmp_path)
        self._approved_raise(
            repo,
            lambda entry: entry["provenance"].update({"source": "backfilled-historical"}),
        )

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_UNAPPROVED_RAISE
        assert "not 'measured-live'" in message

    def test_dirty_tree_measurement_fails(self, tmp_path):
        repo = _base_repo(tmp_path)
        self._approved_raise(
            repo,
            lambda entry: entry["provenance"].update({"dirty": True}),
        )

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_UNAPPROVED_RAISE
        assert "clean tree" in message

    def test_unresolvable_measured_at_commit_fails(self, tmp_path):
        repo = _base_repo(tmp_path)
        self._approved_raise(
            repo,
            lambda entry: entry["provenance"].update({"measured_at_commit": "UNKNOWN"}),
        )

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_UNAPPROVED_RAISE
        assert "does not resolve to a commit" in message

    def test_unrecorded_kicad_cli_version_fails(self, tmp_path):
        repo = _base_repo(tmp_path)
        self._approved_raise(
            repo,
            lambda entry: entry["provenance"]["tool_versions"].pop("kicad-cli"),
        )

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_UNAPPROVED_RAISE
        assert "concrete kicad-cli" in message

    def test_no_provenance_record_at_all_fails(self, tmp_path):
        repo = _base_repo(tmp_path)
        self._approved_raise(
            repo,
            lambda entry: entry.pop("provenance"),
        )

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_UNAPPROVED_RAISE
        assert "no measured sample" in message


class TestPerTypeRaiseCompliantPasses:
    def test_per_type_error_raise_with_full_evidence_passes(self, tmp_path):
        repo = _base_repo(tmp_path)
        raised = _raised_compliant_ceiling(repo)
        entry = raised["boards"][0]
        entry["error_ceiling"] = BASE_CEILING["boards"][0]["error_ceiling"]  # aggregate flat
        entry["violations_by_type"]["clearance"] = 600  # the raise
        _write_ceiling(repo, raised)
        _commit(
            repo,
            "fix(drc): raise clearance ceiling for measured noise\n\n"
            "Ceiling-Approval: reviewer-id",
        )

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_OK
        assert "violations_by_type[clearance] 502 -> 600" in message


class TestDecreasePasses:
    def test_aggregate_decrease_no_trailer_passes(self, tmp_path):
        repo = _base_repo(tmp_path)
        lowered = json.loads(json.dumps(BASE_CEILING))
        lowered["boards"][0]["error_ceiling"] = 900
        _write_ceiling(repo, lowered)
        _commit(repo, "fix: tighten ceiling, no approval needed")

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_OK
        assert "PASS" in message

    def test_per_type_decrease_no_trailer_passes(self, tmp_path):
        repo = _base_repo(tmp_path)
        lowered = json.loads(json.dumps(BASE_CEILING))
        lowered["boards"][0]["violations_by_type"]["clearance"] = 400
        _write_ceiling(repo, lowered)
        _commit(repo, "fix: tighten clearance ceiling")

        exit_code, _message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")
        assert exit_code == EXIT_OK


class TestNoChangePasses:
    def test_unrelated_commit_no_ceiling_change_passes(self, tmp_path):
        repo = _base_repo(tmp_path)
        (repo / "unrelated.txt").write_text("hello\n")
        _commit(repo, "chore: unrelated change")

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_OK
        assert "PASS" in message

    def test_head_even_with_base_passes(self, tmp_path):
        repo = _base_repo(tmp_path)

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_OK
        assert "nothing to check" in message

    def test_new_ceiling_file_not_present_at_base_passes(self, tmp_path):
        """The ceiling file is introduced for the first time in this PR --
        there is nothing to ratchet against, so this cannot be a raise.
        """
        repo = _init_repo(tmp_path)
        (repo / "README.md").write_text("base\n")
        _commit(repo, "base: no ceiling file yet")
        _git(["branch", "origin/main"], repo)

        _write_ceiling(repo, BASE_CEILING)
        _commit(repo, "add drc_ceiling.json for the first time")

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_OK
        assert "does not exist at merge-base" in message


class TestMalformedOrMissingFile:
    def test_missing_ceiling_file_at_head_fails_closed(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "README.md").write_text("no ceiling file at all\n")
        _commit(repo, "base: nothing")
        _git(["branch", "origin/main"], repo)
        (repo / "other.txt").write_text("x\n")
        _commit(repo, "still nothing")

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_TOOL_ERROR
        assert "not found" in message

    def test_malformed_json_at_head_fails_closed(self, tmp_path):
        repo = _base_repo(tmp_path)
        ceiling_file = repo / CEILING_RELPATH
        ceiling_file.write_text("{ not: valid json ]")
        _commit(repo, "oops: corrupted the ceiling file")

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_TOOL_ERROR
        assert "malformed" in message.lower()

    def test_malformed_json_at_merge_base_fails_closed(self, tmp_path):
        repo = _init_repo(tmp_path)
        ceiling_dir = repo / "power_pcb_dataset"
        ceiling_dir.mkdir(parents=True)
        (ceiling_dir / "drc_ceiling.json").write_text("{ not: valid json ]")
        (repo / "README.md").write_text("base\n")
        _commit(repo, "base: corrupted ceiling from the start")
        _git(["branch", "origin/main"], repo)

        _write_ceiling(repo, BASE_CEILING)
        _commit(repo, "fix: repair the ceiling file")

        exit_code, message = run_gate(repo, CEILING_RELPATH, base_ref="origin/main")

        assert exit_code == EXIT_TOOL_ERROR
        assert "malformed" in message.lower()
        assert "merge-base" in message.lower()

    def test_unresolvable_base_ref_fails_closed(self, tmp_path):
        repo = _base_repo(tmp_path)
        (repo / "unrelated.txt").write_text("hello\n")
        _commit(repo, "chore: unrelated change")

        exit_code, message = run_gate(
            repo, CEILING_RELPATH, base_ref="origin/does-not-exist"
        )

        assert exit_code == EXIT_TOOL_ERROR
        assert "could not resolve a merge-base" in message


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
