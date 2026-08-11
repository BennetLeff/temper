"""Tests for the R27 DRC-ceiling monotone contract (U1-U3).

Covers the three DrcRatchet methods that implement the contract:

  - ``find_ceiling_raises`` -- the single enumeration of "what raised"
    (every dimension: aggregate errors/warnings, per-type errors/warnings,
    including a category absent from the old record entirely).
  - ``validate_raise_evidence`` -- the measurement-evidence contract: a
    raise requires (a) a NEW non-empty ``_march`` entry naming the cause
    and (b) a fresh measured-live provenance record (source, resolvable
    commit, clean tree, recorded kicad-cli version, >= 120 samples for the
    nondeterministic clearance category, input hash still matching the
    board file). Every violation shape has a failing test here, so the
    contract is proven to bite (anti-vacuity discipline).
  - ``detect_ceiling_raise`` -- the approval trailer check, kept as the
    substring marker (raise detector); unchanged behavior is asserted so
    the refactor onto ``find_ceiling_raises`` cannot silently change the
    established contract.

No ``git stash`` is used anywhere. ``validate_raise_evidence`` now resolves
``measured_at_commit`` against real git history (see its module-level
``_verify_commits_exist``, reusing
``check_evidence_provenance.verify_commits_exist`` -- the pre-fix version
only checked SHA *shape*, which is exactly how ``drc_ceiling.json`` carried
an unresolvable ``measured_at_commit`` for weeks). Every "compliant" fixture
below therefore initializes a real, throwaway, tmp_path-local git repo and
commits the synthetic board into it (``_init_git_repo``/``_commit_all``,
mirroring ``scripts/tests/test_check_measurement_provenance.py``'s
``TestCommitResolvabilityAntiVacuity`` helpers) so its
``measured_at_commit`` is a genuine, resolvable git fact rather than a
shape-only fake -- no mocking of git itself anywhere. ``VALID_COMMIT``
(a well-formed but never-committed SHA) is kept for the opposite case: a
raise whose commit merely *looks* real must still fail.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from temper_placer.regression.drc_ratchet import DrcRatchet

VALID_COMMIT = "a" * 40
BOARD_CONTENT = b"board-content-v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _init_git_repo(path: Path) -> None:
    """Initialize a real, throwaway git repo at *path* so a
    ``measured_at_commit`` built from it is a genuine, resolvable git fact
    -- never mocked. Mirrors
    ``scripts/tests/test_check_measurement_provenance.py``'s
    ``TestCommitResolvabilityAntiVacuity`` helper (same incident, same fix
    pattern).
    """
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def _commit_all(path: Path, message: str) -> str:
    """Stage everything under *path* and commit; return the new commit's
    full 40-char SHA."""
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=path, check=True)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _base_ceiling() -> dict:
    """The origin/main-style base record: ceiling values, no _march, no
    provenance (a base record's provenance is never part of the evidence
    contract -- only the raised board's NEW record is validated).
    """
    return {
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


def _valid_provenance(board_sha: str, **overrides: object) -> dict:
    prov: dict = {
        "measured_at_commit": VALID_COMMIT,
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


def _write_board(tmp_path: Path, content: bytes = BOARD_CONTENT) -> str:
    board = tmp_path / "pcb" / "temper.kicad_pcb"
    board.parent.mkdir(parents=True, exist_ok=True)
    board.write_bytes(content)
    return _sha256(content)


def _compliant_new_ceiling(
    tmp_path: Path,
    base: dict | None = None,
    *,
    raise_error_ceiling: int = 10,
    march_entry: str = "2026-08-02",
    march_value: str = "attributed cause: U3 footprint corrected (commit abc123)",
) -> tuple[dict, Path]:
    """The compliant row of the contract matrix: a raise backed by a new
    non-empty ``_march`` entry and a fresh measured-live provenance record
    whose input hash matches the board file on disk AND whose
    ``measured_at_commit`` resolves in a real (throwaway, tmp_path-local)
    git repo. Returns (new_ceiling, board_file_path).
    """
    base = base or _base_ceiling()
    board_file = tmp_path / "pcb" / "temper.kicad_pcb"
    board_file.parent.mkdir(parents=True, exist_ok=True)
    board_file.write_bytes(BOARD_CONTENT)
    board_sha = _sha256(BOARD_CONTENT)

    _init_git_repo(tmp_path)
    commit_sha = _commit_all(tmp_path, "compliant board snapshot")

    new = json.loads(json.dumps(base))
    entry = new["boards"][0]
    entry["error_ceiling"] = entry["error_ceiling"] + raise_error_ceiling
    entry["nondeterministic_error_types"] = {
        "clearance": {"observed": [499, 500, 501], "samples": 120, "note": "only nondeterministic category"}
    }
    entry["provenance"] = _valid_provenance(board_sha, measured_at_commit=commit_sha)
    new["_march"] = {
        "2026-07-30": "prior entry (base state)",
        march_entry: march_value,
    }
    return new, board_file


class TestFindCeilingRaises:
    def test_no_change_yields_no_raises(self):
        base = _base_ceiling()
        ratchet = DrcRatchet(Path("dummy.json"))
        assert ratchet.find_ceiling_raises(base, json.loads(json.dumps(base))) == []

    def test_aggregate_error_raise_detected(self):
        old = _base_ceiling()
        new = json.loads(json.dumps(old))
        new["boards"][0]["error_ceiling"] = 1020
        raises = DrcRatchet(Path("dummy.json")).find_ceiling_raises(old, new)
        assert raises == [("temper", ["error_ceiling 1017 -> 1020"])]

    def test_aggregate_warning_raise_detected(self):
        old = _base_ceiling()
        new = json.loads(json.dumps(old))
        new["boards"][0]["warning_ceiling"] = 800
        raises = DrcRatchet(Path("dummy.json")).find_ceiling_raises(old, new)
        assert raises == [("temper", ["warning_ceiling 762 -> 800"])]

    def test_per_type_raise_detected(self):
        old = _base_ceiling()
        new = json.loads(json.dumps(old))
        new["boards"][0]["violations_by_type"]["clearance"] = 600
        raises = DrcRatchet(Path("dummy.json")).find_ceiling_raises(old, new)
        assert raises == [("temper", ["violations_by_type[clearance] 502 -> 600"])]

    def test_new_category_is_a_raise_from_implicit_zero(self):
        old = _base_ceiling()
        new = json.loads(json.dumps(old))
        new["boards"][0]["violations_by_type"]["shorting_items"] = 5
        raises = DrcRatchet(Path("dummy.json")).find_ceiling_raises(old, new)
        assert raises == [("temper", ["violations_by_type[shorting_items] 0 -> 5"])]

    def test_warning_category_raise_detected(self):
        old = _base_ceiling()
        new = json.loads(json.dumps(old))
        new["boards"][0]["warnings_by_type"]["silk_overlap"] = 300
        raises = DrcRatchet(Path("dummy.json")).find_ceiling_raises(old, new)
        assert raises == [("temper", ["warnings_by_type[silk_overlap] 119 -> 300"])]

    def test_aggregate_drop_does_not_mask_per_type_raise(self):
        old = _base_ceiling()
        new = json.loads(json.dumps(old))
        new["boards"][0]["error_ceiling"] = 900  # aggregate DROPPED
        new["boards"][0]["violations_by_type"]["clearance"] = 600
        raises = DrcRatchet(Path("dummy.json")).find_ceiling_raises(old, new)
        assert raises == [("temper", ["violations_by_type[clearance] 502 -> 600"])]

    def test_decrease_only_yields_no_raises(self):
        old = _base_ceiling()
        new = json.loads(json.dumps(old))
        new["boards"][0]["error_ceiling"] = 900
        new["boards"][0]["violations_by_type"]["clearance"] = 400
        assert DrcRatchet(Path("dummy.json")).find_ceiling_raises(old, new) == []

    def test_new_board_in_new_record_is_not_a_raise(self):
        """A board added for the first time has no old ceiling to raise --
        same "new file is not a raise" semantics the gate applies at the
        file level.
        """
        old = _base_ceiling()
        new = json.loads(json.dumps(old))
        new["boards"].append(
            {
                "board_id": "second",
                "path": "pcb/second.kicad_pcb",
                "error_ceiling": 5,
                "warning_ceiling": 5,
            }
        )
        raises = DrcRatchet(Path("dummy.json")).find_ceiling_raises(old, new)
        assert raises == []

    def test_multiple_boards_and_dimensions_are_all_enumerated(self):
        old = _base_ceiling()
        new = json.loads(json.dumps(old))
        entry = new["boards"][0]
        entry["error_ceiling"] = 1020
        entry["violations_by_type"]["clearance"] = 600
        new["boards"].append(
            {
                "board_id": "second",
                "path": "pcb/second.kicad_pcb",
                "error_ceiling": 1,
                "warning_ceiling": 1,
            }
        )
        second = new["boards"][1]
        # second existed in old with 1/1... no, it's new. Instead raise a
        # second real board by including it in old too.
        old["boards"].append(
            {
                "board_id": "second",
                "path": "pcb/second.kicad_pcb",
                "error_ceiling": 1,
                "warning_ceiling": 1,
            }
        )
        second["error_ceiling"] = 9
        raises = DrcRatchet(Path("dummy.json")).find_ceiling_raises(old, new)
        assert ("temper", ["error_ceiling 1017 -> 1020", "violations_by_type[clearance] 502 -> 600"]) in raises
        assert ("second", ["error_ceiling 1 -> 9"]) in raises


class TestValidateRaiseEvidence:
    """The contract-violation matrix: each row fails with the specific
    reason named, and the compliant row passes."""

    def test_compliant_raise_passes(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert problems == []

    def test_no_raise_needs_no_evidence(self, tmp_path):
        old = _base_ceiling()
        new = json.loads(json.dumps(old))  # byte-identical: no raise
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert problems == []

    def test_raise_without_new_march_entry_fails_naming_the_cause(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        # Same _march in old and new: no NEW entry.
        old["_march"] = dict(new["_march"])
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert len(problems) == 1
        assert "no attributed cause" in problems[0]
        assert "_march" in problems[0]

    def test_new_march_entry_must_be_non_empty(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(
            tmp_path, march_value="   \n  "  # whitespace only: not a cause
        )
        old["_march"] = {"2026-07-30": "prior entry (base state)"}
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("no attributed cause" in p for p in problems)

    def test_legacy_bare_trailer_without_cause_fails(self, tmp_path):
        """U1 scenario 2: the bare legacy string with valid provenance but
        no attributed cause still fails -- the _march entry is the cause
        authority, not the trailer.
        """
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        del new["_march"]  # trailer says Ceiling-Approval, _march says nothing
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("no attributed cause" in p for p in problems)

    def test_backfilled_provenance_fails(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(
            tmp_path, march_value="cause: resynced U3 footprint (commit abc123)"
        )
        new["boards"][0]["provenance"]["source"] = "backfilled-historical"
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("not 'measured-live'" in p for p in problems)

    def test_unresolvable_measured_at_commit_fails(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        new["boards"][0]["provenance"]["measured_at_commit"] = "UNKNOWN"
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("does not resolve to a commit" in p for p in problems)

    def test_shape_valid_but_never_committed_sha_fails(self, tmp_path):
        """The 2026-08-07 incident, reproduced directly: a well-formed
        40-char-hex SHA (``VALID_COMMIT``) that was never committed anywhere
        -- passes the old shape-only ``_SHA256_HEX_RE.fullmatch`` check but
        must fail now that the check actually asks git.

        ``_compliant_new_ceiling`` already committed a DIFFERENT, real
        commit into this tmp_path repo (so the repo is a genuine, non-empty
        git history, not just "any commit resolves because there are
        none to compare against") -- ``VALID_COMMIT`` specifically is not
        among its objects.
        """
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        new["boards"][0]["provenance"]["measured_at_commit"] = VALID_COMMIT
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any(
            f"measured_at_commit={VALID_COMMIT!r} does not resolve to a commit" in p
            for p in problems
        ), problems

    def test_dirty_tree_measurement_fails(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        new["boards"][0]["provenance"]["dirty"] = True
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("clean tree" in p for p in problems)

    def test_missing_kicad_cli_version_fails(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        del new["boards"][0]["provenance"]["tool_versions"]["kicad-cli"]
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("concrete kicad-cli" in p for p in problems)

    def test_unknown_kicad_cli_version_fails(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        new["boards"][0]["provenance"]["tool_versions"]["kicad-cli"] = "UNKNOWN"
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("concrete kicad-cli" in p for p in problems)

    def test_under_sampled_clearance_fails_naming_the_sample_count(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        new["boards"][0]["provenance"]["sample_count"] = 60
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("60" in p and "at least 120" in p for p in problems)

    def test_missing_sample_count_for_nondeterministic_clearance_fails(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        new["boards"][0]["provenance"].pop("sample_count", None)
        new["boards"][0]["provenance"]["measured_via"] = (
            "temper_placer.validation._drc_api.run_drc with --all-track-errors"
        )  # no sample count anywhere
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("at least 120 samples" in p for p in problems)

    def test_legacy_measured_via_prose_sample_count_passes(self, tmp_path):
        """The legacy default: records that predate the structured
        ``sample_count`` field carry the count in measured_via prose -- the
        current committed record's exact shape.
        """
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        prov = new["boards"][0]["provenance"]
        prov.pop("sample_count", None)
        prov["measured_via"] = (
            "temper_placer.validation._drc_api.run_drc with --all-track-errors "
            "(120 samples; see nondeterministic_error_types.clearance.samples)"
        )
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert problems == []

    def test_structured_sample_count_field_passes(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        prov = new["boards"][0]["provenance"]
        prov["sample_count"] = 120
        prov["measured_via"] = "temper_placer.validation._drc_api.run_drc with --all-track-errors"
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert problems == []

    def test_sample_count_not_required_when_clearance_is_deterministic(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        new["boards"][0].pop("nondeterministic_error_types", None)
        new["boards"][0]["provenance"].pop("sample_count", None)
        new["boards"][0]["provenance"]["measured_via"] = "single sample"
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert problems == []

    def test_under_sampled_creepage_only_raise_fails(self, tmp_path):
        """2026-08-11 fix: the sample-count check used to be hardcoded to
        ``"clearance" in nondet``, so a raise whose ONLY nondeterministic
        category was something else (e.g. ``creepage``, the category that
        has actually been chronically nondeterministic on this board since
        the #602 K3 swap) sailed through with zero samples required. This
        reproduces that exact shape -- a creepage-only nondeterministic
        block, undersampled -- and asserts it is now caught."""
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        new["boards"][0]["nondeterministic_error_types"] = {
            "creepage": {"observed": [182, 183, 184], "samples": 40, "note": "only nondeterministic category"}
        }
        new["boards"][0]["provenance"]["sample_count"] = 40
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("40" in p and "at least 120" in p and "creepage" in p for p in problems)

    def test_sufficiently_sampled_creepage_only_raise_passes(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        new["boards"][0]["nondeterministic_error_types"] = {
            "creepage": {"observed": [182, 183, 184], "samples": 134, "note": "only nondeterministic category"}
        }
        new["boards"][0]["provenance"]["sample_count"] = 134
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert problems == []

    def test_stale_input_hash_fails(self, tmp_path):
        old = _base_ceiling()
        new, board_file = _compliant_new_ceiling(tmp_path)
        board_file.write_bytes(b"board-content-v2")  # board moved after measurement
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("STALE measurement" in p for p in problems)

    def test_inputs_not_naming_board_fail(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        new["boards"][0]["provenance"]["inputs"] = [
            {"path": "pcb/other.kicad_pcb", "sha256": "b" * 64}
        ]
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("do not name the board file" in p for p in problems)

    def test_missing_board_file_fails_closed(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        (tmp_path / "pcb" / "temper.kicad_pcb").unlink()
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("cannot hash the board file" in p for p in problems)

    def test_missing_provenance_fails(self, tmp_path):
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        del new["boards"][0]["provenance"]
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("no measured sample" in p for p in problems)

    def test_evidence_checks_are_independent(self, tmp_path):
        """U2 scenario 5: valid provenance but no cause still fails, and a
        cause with stale provenance still fails -- the two requirements do
        not trade off against each other.
        """
        old = _base_ceiling()
        new, _board = _compliant_new_ceiling(tmp_path)
        old["_march"] = dict(new["_march"])  # remove the new cause entry
        new["boards"][0]["provenance"]["source"] = "backfilled-historical"
        problems = DrcRatchet(Path("dummy.json")).validate_raise_evidence(old, new, tmp_path)
        assert any("no attributed cause" in p for p in problems)
        assert any("not 'measured-live'" in p for p in problems)


class TestDetectCeilingRaiseBackwardCompat:
    """The substring marker contract is unchanged by the refactor: a raise
    without 'Ceiling-Approval:' fails, with it passes, no raise passes.
    """

    def test_raise_without_marker_fails(self):
        ratchet = DrcRatchet(Path("dummy.json"))
        old = _base_ceiling()
        new = json.loads(json.dumps(old))
        new["boards"][0]["error_ceiling"] = 1020
        result = ratchet.detect_ceiling_raise(old, new, commit_message="fix: update ceiling")
        assert result is not None
        assert result.exit_code == 2
        assert "error_ceiling 1017 -> 1020" in result.message
        assert "requires explicit approval" in result.message

    def test_raise_with_marker_passes(self):
        ratchet = DrcRatchet(Path("dummy.json"))
        old = _base_ceiling()
        new = json.loads(json.dumps(old))
        new["boards"][0]["error_ceiling"] = 1020
        result = ratchet.detect_ceiling_raise(
            old, new, commit_message="fix(drc): raise for noise\n\nCeiling-Approval: reviewer"
        )
        assert result is None

    def test_per_type_raise_without_marker_fails(self):
        ratchet = DrcRatchet(Path("dummy.json"))
        old = _base_ceiling()
        new = json.loads(json.dumps(old))
        new["boards"][0]["violations_by_type"]["clearance"] = 600
        result = ratchet.detect_ceiling_raise(old, new, commit_message="fix: whatever")
        assert result is not None
        assert "violations_by_type[clearance] 502 -> 600" in result.message

    def test_no_raise_passes(self):
        ratchet = DrcRatchet(Path("dummy.json"))
        old = _base_ceiling()
        new = json.loads(json.dumps(old))
        new["boards"][0]["error_ceiling"] = 900  # decrease only
        assert ratchet.detect_ceiling_raise(old, new, commit_message="fix: tighten") is None
