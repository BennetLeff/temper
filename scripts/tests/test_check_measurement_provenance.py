"""Tests for check_measurement_provenance.py.

Four groups:

1. `TestExtractRecords` -- the generic record walker over both supported
   artifact shapes (single top-level "provenance" object, and a list of
   dict records each with its own "provenance" key -- the drc_ceiling.json
   shape).
2. `TestEvaluate` -- `evaluate()`'s classification of fresh / stale /
   allowlisted / problem records, and its anti-vacuity fail-closed behavior
   (zero artifacts, zero records) -- all against synthetic tmp_path
   artifacts, entirely independent of the real repo. These use
   `measured_at_commit: "UNKNOWN"` throughout (via `_valid_prov`) so they
   exercise freshness/allowlist logic without needing a real git repo --
   commit *resolvability* is a distinct concern with its own group below.
3. `TestFalsifierDrcCeilingReconstruction` -- the task's own falsifier,
   reconstructed directly: a ceiling-shaped artifact whose recorded input
   hash no longer matches the board file on disk must FAIL (STALE, exit
   EXIT_GATE_ERROR); the same artifact, once its provenance is re-recorded
   against the board's current content, must PASS. No `git stash` is used
   anywhere -- both states are plain tmp_path fixtures.
4. `TestCommitResolvabilityAntiVacuity` -- reproduces the 2026-08-07
   dangling-SHA incident directly: `measured_at_commit` values are checked
   against a real (throwaway, tmp_path-local) git repo, so "resolves" and
   "does not resolve" are genuine git facts, not mocked. Covers the three
   FAIL conditions the incident's fix must catch (unresolvable commit,
   stale content hash, dirty=true) and the one PASS condition (a clean
   record with everything true) -- the `TestAntiVacuity` /
   `TestFailBeforePassAfter` pattern from test_check_isolation_keepout.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib.measurement_provenance import (  # noqa: E402
    build_provenance,
    get_sample_count,
    sha256_file,
    validate_provenance_shape,
)
from check_measurement_provenance import (  # noqa: E402
    _MISSING,
    EXIT_GATE_ERROR,
    EXIT_OK,
    GateError,
    Record,
    evaluate,
    extract_records,
    load_records,
)

VALID_SHA = "a" * 64
VALID_COMMIT = "b" * 40


def _valid_prov(sha: str, path: str = "pcb/board.kicad_pcb"):
    # measured_at_commit: "UNKNOWN" deliberately -- this helper backs the
    # freshness/allowlist tests below, which run against tmp_path
    # directories that are NOT git repositories. A well-formed-but-fake SHA
    # here would now (correctly) fail the commit-resolvability check added
    # for the dangling-SHA incident; "UNKNOWN" is the honest, git-independent
    # value and exercises a different, deliberately-tolerated code path.
    # Tests that specifically need a resolvable (or unresolvable) commit
    # build a real tmp_path git repo -- see TestCommitResolvabilityAntiVacuity.
    return {
        "measured_at_commit": "UNKNOWN",
        "dirty": False,
        "inputs": [{"path": path, "sha256": sha}],
        "tool_versions": {"kicad-cli": "UNKNOWN"},
        "source": "backfilled-historical",
    }


def _init_git_repo(path: Path) -> None:
    """Initialize a real, throwaway, non-shallow git repo at *path* -- used
    only by TestCommitResolvabilityAntiVacuity so "resolves to a commit
    object" is a genuine git fact, never mocked."""
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


# ---------------------------------------------------------------------------
# TestExtractRecords
# ---------------------------------------------------------------------------


class TestExtractRecords:
    def test_top_level_provenance_key(self):
        data = {"provenance": {"measured_at_commit": VALID_COMMIT}}
        records = extract_records(data)
        assert records == [("<root>", {"measured_at_commit": VALID_COMMIT})]

    def test_top_level_missing_provenance_key_is_not_a_record(self):
        # No "provenance" key anywhere and no list of dict records -> zero
        # records, not a record with _MISSING (there is nothing shaped like
        # a measurement record here at all).
        assert extract_records({"error_ceiling": 85}) == []

    def test_boards_list_shape_drc_ceiling_style(self):
        data = {
            "boards": [
                {"board_id": "temper", "path": "pcb/temper.kicad_pcb", "provenance": {"x": 1}},
                {"board_id": "other", "path": "pcb/other.kicad_pcb"},  # no provenance key
            ]
        }
        records = extract_records(data)
        assert ("boards.temper", {"x": 1}) in records
        assert ("boards.other", _MISSING) in records
        assert len(records) == 2

    def test_non_dict_items_in_list_are_skipped(self):
        data = {"boards": ["not-a-dict", 42, {"board_id": "ok", "provenance": {}}]}
        records = extract_records(data)
        assert records == [("boards.ok", {})]

    def test_non_dict_top_level_returns_no_records(self):
        assert extract_records(["a", "b"]) == []
        assert extract_records("just a string") == []

    def test_falls_back_to_index_when_no_id_field(self):
        data = {"items": [{"provenance": {}}]}
        records = extract_records(data)
        assert records == [("items.0", {})]


# ---------------------------------------------------------------------------
# TestEvaluate
# ---------------------------------------------------------------------------


class TestEvaluate:
    def _write_artifact(self, tmp_path: Path, name: str, data: dict) -> Path:
        p = tmp_path / name
        p.write_text(json.dumps(data))
        return p

    def test_fresh_record_passes(self, tmp_path):
        board = tmp_path / "board.txt"
        board.write_text("v1")
        artifact = self._write_artifact(
            tmp_path,
            "ceiling.json",
            {"boards": [{"board_id": "b1", "provenance": _valid_prov(sha256_file(board), "board.txt")}]},
        )
        outcome = evaluate(tmp_path, [artifact], allowlist={})
        assert outcome.fresh == [f"{artifact.name}#boards.b1"]
        assert outcome.stale == []
        assert outcome.problems == []

    def test_stale_record_is_reported_not_raised(self, tmp_path):
        board = tmp_path / "board.txt"
        board.write_text("v1")
        recorded = sha256_file(board)
        board.write_text("v2 -- routed")  # moved after "measurement"
        artifact = self._write_artifact(
            tmp_path,
            "ceiling.json",
            {"boards": [{"board_id": "b1", "provenance": _valid_prov(recorded, "board.txt")}]},
        )
        outcome = evaluate(tmp_path, [artifact], allowlist={})
        assert outcome.fresh == []
        assert len(outcome.stale) == 1
        key, mismatches = outcome.stale[0]
        assert key == f"{artifact.name}#boards.b1"
        assert len(mismatches) == 1

    def test_missing_provenance_unallowlisted_is_a_problem(self, tmp_path):
        artifact = self._write_artifact(
            tmp_path, "ceiling.json", {"boards": [{"board_id": "b1", "path": "board.txt"}]}
        )
        outcome = evaluate(tmp_path, [artifact], allowlist={})
        assert outcome.problems
        key, reason = outcome.problems[0]
        assert key == f"{artifact.name}#boards.b1"
        assert "not allowlisted" in reason

    def test_missing_provenance_allowlisted_is_tolerated(self, tmp_path):
        artifact = self._write_artifact(
            tmp_path, "ceiling.json", {"boards": [{"board_id": "b1", "path": "board.txt"}]}
        )
        key = f"{artifact.name}#boards.b1"
        outcome = evaluate(tmp_path, [artifact], allowlist={key: "TODO: temper-999"})
        assert outcome.allowlisted == [key]
        assert outcome.problems == []

    def test_malformed_provenance_is_never_allowlist_eligible(self, tmp_path):
        # provenance key present but not an object -- this is "wrong", not
        # "unknown", and must be a problem regardless of the allowlist.
        artifact = self._write_artifact(
            tmp_path, "ceiling.json", {"boards": [{"board_id": "b1", "provenance": "oops"}]}
        )
        key = f"{artifact.name}#boards.b1"
        outcome = evaluate(tmp_path, [artifact], allowlist={key: "TODO: temper-999"})
        assert outcome.problems
        assert outcome.problems[0][0] == key

    def test_malformed_provenance_shape_is_a_problem(self, tmp_path):
        artifact = self._write_artifact(
            tmp_path,
            "ceiling.json",
            {"boards": [{"board_id": "b1", "provenance": {"measured_at_commit": "nope"}}]},
        )
        outcome = evaluate(tmp_path, [artifact], allowlist={})
        assert outcome.problems
        assert "malformed provenance" in outcome.problems[0][1]

    def test_zero_artifacts_registered_raises_gate_error(self, tmp_path):
        with pytest.raises(GateError, match="zero measurement artifacts registered"):
            evaluate(tmp_path, [], allowlist={})

    def test_zero_records_found_raises_gate_error(self, tmp_path):
        artifact = self._write_artifact(tmp_path, "ceiling.json", {"error_ceiling": 85})
        with pytest.raises(GateError, match="zero provenance-bearing records"):
            evaluate(tmp_path, [artifact], allowlist={})

    def test_missing_artifact_file_raises_gate_error(self, tmp_path):
        with pytest.raises(GateError, match="not found"):
            evaluate(tmp_path, [tmp_path / "does-not-exist.json"], allowlist={})

    def test_malformed_json_raises_gate_error(self, tmp_path):
        artifact = tmp_path / "ceiling.json"
        artifact.write_text("{not valid json")
        with pytest.raises(GateError, match="malformed JSON"):
            evaluate(tmp_path, [artifact], allowlist={})

    def test_allowlist_entry_without_ticket_is_a_problem(self, tmp_path):
        board = tmp_path / "board.txt"
        board.write_text("v1")
        artifact = self._write_artifact(
            tmp_path,
            "ceiling.json",
            {"boards": [{"board_id": "b1", "provenance": _valid_prov(sha256_file(board), "board.txt")}]},
        )
        outcome = evaluate(tmp_path, [artifact], allowlist={"some/other#key": "no ticket here"})
        assert any("missing ticket reference" in reason for _, reason in outcome.problems)


# ---------------------------------------------------------------------------
# TestFalsifierDrcCeilingReconstruction
# ---------------------------------------------------------------------------


class TestFalsifierDrcCeilingReconstruction:
    """Directly reconstructs the task's falsifier: a ceiling whose recorded
    board hash no longer matches must FAIL; once re-measured, it must PASS.
    Uses tmp_path fixtures throughout -- no git stash, no mutation of the
    real repo's drc_ceiling.json.
    """

    def test_stale_board_fails_then_passes_once_remeasured(self, tmp_path):
        board = tmp_path / "pcb" / "temper.kicad_pcb"
        board.parent.mkdir()
        board.write_text("(kicad_pcb (version old-route))")

        old_hash = sha256_file(board)
        ceiling = tmp_path / "drc_ceiling.json"
        ceiling.write_text(
            json.dumps(
                {
                    "boards": [
                        {
                            "board_id": "temper",
                            "path": "pcb/temper.kicad_pcb",
                            "error_ceiling": 85,
                            "provenance": _valid_prov(old_hash, "pcb/temper.kicad_pcb"),
                        }
                    ]
                }
            )
        )

        # Simulate "three commits landed on the board" (c6b1b463,
        # 556ccf4f, 65bd0159 in the real incident) -- the ceiling file
        # itself is untouched, exactly as the real drc_ceiling.json was
        # byte-identical across those commits.
        board.write_text("(kicad_pcb (version new-route, 51/96 nets routed))")

        outcome = evaluate(tmp_path, [ceiling], allowlist={})
        assert outcome.stale, "gate must report the moved board as STALE"
        assert outcome.fresh == []
        key, mismatches = outcome.stale[0]
        assert key == "drc_ceiling.json#boards.temper"
        assert mismatches[0].recorded_sha256 == old_hash
        assert mismatches[0].current_sha256 == sha256_file(board)
        assert mismatches[0].current_sha256 != old_hash

        # --- PASS state: re-measure (build_provenance against the CURRENT
        # board content) and confirm the gate now clears it. ---
        new_prov = build_provenance(tmp_path, ["pcb/temper.kicad_pcb"], source="measured-live")
        data = json.loads(ceiling.read_text())
        data["boards"][0]["provenance"] = new_prov
        ceiling.write_text(json.dumps(data))

        outcome2 = evaluate(tmp_path, [ceiling], allowlist={})
        assert outcome2.stale == []
        assert outcome2.fresh == ["drc_ceiling.json#boards.temper"]

    def test_second_artifact_hash_moved_generalizes_beyond_drc(self, tmp_path):
        """Case-2 shape: a measurement record citing an artifact hash that
        has since moved (e.g. a routing baseline citing a router binary/
        source snapshot) -- the same mechanism, a differently-named input.
        """
        router_src = tmp_path / "router_snapshot.rs"
        router_src.write_text("// router v1 -- June 29 snapshot\n")
        old_hash = sha256_file(router_src)

        baseline = tmp_path / "routing_baseline.json"
        baseline.write_text(
            json.dumps({"provenance": _valid_prov(old_hash, "router_snapshot.rs")})
        )

        # Source moved (rebuilt/edited) 28 days later, per the real
        # temper_rust_router incident -- baseline file untouched.
        router_src.write_text("// router v2 -- July 27, cap_infos.get(orig_idx) fix\n")

        outcome = evaluate(tmp_path, [baseline], allowlist={})
        assert outcome.stale
        assert outcome.stale[0][0] == "routing_baseline.json#<root>"

    def test_gate_exit_code_matches_stale_state(self, tmp_path):
        """decide the exit code the same way main() does, without going
        through argv/sys.exit -- STALE must map to EXIT_GATE_ERROR, never
        EXIT_OK."""
        board = tmp_path / "board.txt"
        board.write_text("v1")
        old_hash = sha256_file(board)
        board.write_text("v2")
        artifact = tmp_path / "ceiling.json"
        artifact.write_text(
            json.dumps({"boards": [{"board_id": "b1", "provenance": _valid_prov(old_hash, "board.txt")}]})
        )

        outcome = evaluate(tmp_path, [artifact], allowlist={})
        exit_code = EXIT_GATE_ERROR if (outcome.stale or outcome.problems) else EXIT_OK
        assert exit_code == EXIT_GATE_ERROR


# ---------------------------------------------------------------------------
# TestCommitResolvabilityAntiVacuity -- reproduces the 2026-08-07 dangling-
# commit incident (drc_ceiling.json's measured_at_commit,
# 3410ee4e1fe8c3a5cce13b9262585016a06fce8d, orphaned by a squash-merged/
# rebased PR branch and never caught because neither existing check called
# git at all). Anti-vacuity requirement (goal-set R9/R10): demonstrate the
# check FAILS on each of the three conditions the fix must catch, and
# PASSES on a clean record, all in one place.
# ---------------------------------------------------------------------------


class TestCommitResolvabilityAntiVacuity:
    def _write_ceiling(self, tmp_path: Path, prov: dict) -> Path:
        artifact = tmp_path / "ceiling.json"
        artifact.write_text(json.dumps({"boards": [{"board_id": "b1", "provenance": prov}]}))
        return artifact

    def test_fails_on_unresolvable_measured_at_commit(self, tmp_path):
        """(a) A well-formed (40 lowercase hex) but never-committed SHA --
        exactly the shape of the incident's dangling SHA from this
        checker's point of view: format-valid, resolves to nothing."""
        _init_git_repo(tmp_path)
        board = tmp_path / "board.txt"
        board.write_text("v1")
        _commit_all(tmp_path, "add board")  # a real commit exists in this repo...

        prov = _valid_prov(sha256_file(board), "board.txt")
        prov["measured_at_commit"] = "f" * 40  # ...but this SHA is not it
        artifact = self._write_ceiling(tmp_path, prov)

        outcome = evaluate(tmp_path, [artifact], allowlist={})
        assert outcome.fresh == [], "an unresolvable commit must never be reported fresh"
        assert outcome.stale == []
        assert len(outcome.problems) == 1
        key, reason = outcome.problems[0]
        assert key == f"{artifact.name}#boards.b1"
        assert "does not resolve" in reason

    def test_fails_on_content_hash_not_matching_current_board(self, tmp_path):
        """(b) The pre-existing STALE mechanism, reproduced here with a
        real resolvable commit alongside it -- a moved input must still
        fail even when the commit anchor itself is perfectly valid."""
        _init_git_repo(tmp_path)
        board = tmp_path / "board.txt"
        board.write_text("v1")
        real_commit = _commit_all(tmp_path, "add board")
        recorded_hash = sha256_file(board)
        board.write_text("v2 -- routed after measurement")  # input moved

        prov = _valid_prov(recorded_hash, "board.txt")
        prov["measured_at_commit"] = real_commit
        artifact = self._write_ceiling(tmp_path, prov)

        outcome = evaluate(tmp_path, [artifact], allowlist={})
        assert outcome.fresh == []
        assert outcome.problems == [], "a moved input is STALE, not a 'problem'"
        assert len(outcome.stale) == 1
        assert outcome.stale[0][0] == f"{artifact.name}#boards.b1"

    def test_fails_on_dirty_true(self, tmp_path):
        """(c) dirty=true must fail even with a resolvable commit and a
        matching content hash -- an unnamed uncommitted change could have
        influenced the measurement without appearing in 'inputs'."""
        _init_git_repo(tmp_path)
        board = tmp_path / "board.txt"
        board.write_text("v1")
        real_commit = _commit_all(tmp_path, "add board")

        prov = _valid_prov(sha256_file(board), "board.txt")
        prov["measured_at_commit"] = real_commit
        prov["dirty"] = True
        artifact = self._write_ceiling(tmp_path, prov)

        outcome = evaluate(tmp_path, [artifact], allowlist={})
        assert outcome.fresh == []
        assert outcome.stale == []
        assert len(outcome.problems) == 1
        key, reason = outcome.problems[0]
        assert key == f"{artifact.name}#boards.b1"
        assert "dirty=true" in reason

    def test_passes_on_a_clean_record(self, tmp_path):
        """Control: a resolvable commit, a clean tree, and a matching
        content hash together must PASS -- the fix must not be so eager it
        fails everything (the anti-vacuity check needs a real PASS case,
        not just three FAIL cases, per TestFailBeforePassAfter convention)."""
        _init_git_repo(tmp_path)
        board = tmp_path / "board.txt"
        board.write_text("v1")
        real_commit = _commit_all(tmp_path, "add board")

        prov = _valid_prov(sha256_file(board), "board.txt")
        prov["measured_at_commit"] = real_commit
        artifact = self._write_ceiling(tmp_path, prov)

        outcome = evaluate(tmp_path, [artifact], allowlist={})
        assert outcome.problems == []
        assert outcome.stale == []
        assert outcome.fresh == [f"{artifact.name}#boards.b1"]

    def test_unknown_commit_is_not_penalized_by_the_resolvability_check(self, tmp_path):
        """measured_at_commit='UNKNOWN' is the honest escape hatch (backfilled
        records, or a measurement whose commit genuinely can't be
        reconstructed) -- it must never be required to resolve, and must
        not even trigger a git subprocess (asserted indirectly: this repo
        root is not a git repository at all, so any git invocation would
        raise, and this test must still pass)."""
        board = tmp_path / "board.txt"
        board.write_text("v1")
        prov = _valid_prov(sha256_file(board), "board.txt")  # commit == "UNKNOWN"
        artifact = self._write_ceiling(tmp_path, prov)

        outcome = evaluate(tmp_path, [artifact], allowlist={})
        assert outcome.problems == []
        assert outcome.fresh == [f"{artifact.name}#boards.b1"]

    def test_multiple_records_batch_verified_in_one_git_call(self, tmp_path, monkeypatch):
        """Two records, two different commits (one resolvable, one not) --
        must still be a single git subprocess for the whole scan, not one
        per record (mirrors verify_commits_exist's own batching contract)."""
        import check_evidence_provenance as cep

        _init_git_repo(tmp_path)
        board = tmp_path / "board.txt"
        board.write_text("v1")
        real_commit = _commit_all(tmp_path, "add board")

        good_prov = _valid_prov(sha256_file(board), "board.txt")
        good_prov["measured_at_commit"] = real_commit
        bad_prov = _valid_prov(sha256_file(board), "board.txt")
        bad_prov["measured_at_commit"] = "e" * 40

        artifact = tmp_path / "ceiling.json"
        artifact.write_text(
            json.dumps(
                {
                    "boards": [
                        {"board_id": "good", "provenance": good_prov},
                        {"board_id": "bad", "provenance": bad_prov},
                    ]
                }
            )
        )

        call_count = 0
        real_run = subprocess.run

        def _counting_run(cmd, *args, **kwargs):
            nonlocal call_count
            if isinstance(cmd, list) and "cat-file" in cmd:
                call_count += 1
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(cep.subprocess, "run", _counting_run)

        outcome = evaluate(tmp_path, [artifact], allowlist={})
        assert call_count == 1, "expected exactly one batched git cat-file call"
        assert outcome.fresh == [f"{artifact.name}#boards.good"]
        assert len(outcome.problems) == 1
        assert outcome.problems[0][0] == f"{artifact.name}#boards.bad"


# ---------------------------------------------------------------------------
# load_records / Record.key
# ---------------------------------------------------------------------------


def test_record_key_is_artifact_relative(tmp_path):
    artifact = tmp_path / "sub" / "ceiling.json"
    artifact.parent.mkdir()
    artifact.write_text(json.dumps({"boards": [{"board_id": "b1", "provenance": {}}]}))
    records = load_records(artifact)
    assert len(records) == 1
    assert isinstance(records[0], Record)
    # key uses REPO_ROOT-relative path in the real gate; here we only
    # confirm record_id plumbing, since REPO_ROOT is the real repo root
    # inside this process and tmp_path is not under it.
    assert records[0].record_id == "boards.b1"
    assert records[0].provenance == {}


# ---------------------------------------------------------------------------
# TestSampleCountSchema -- the R27 structured sample_count field (and its
# legacy measured_via-prose default) added to the provenance schema.
# ---------------------------------------------------------------------------


class TestSampleCountSchema:
    def test_structured_field_wins(self):
        prov = {
            "sample_count": 120,
            "measured_via": "(5 samples; stale prose that must lose)",
        }
        assert get_sample_count(prov) == 120

    def test_legacy_measured_via_prose_default(self):
        # The current committed drc_ceiling.json record's exact shape: no
        # structured field, count carried in measured_via prose.
        prov = {
            "measured_via": (
                "temper_placer.validation._drc_api.run_drc with --all-track-errors "
                "(120 samples; see nondeterministic_error_types.clearance.samples)"
            )
        }
        assert get_sample_count(prov) == 120

    def test_measured_via_prose_other_phrasings(self):
        assert get_sample_count({"measured_via": "ran 8 samples of run_drc"}) == 8
        assert get_sample_count({"measured_via": "8 samples; 3 warnings"}) == 8

    def test_missing_sample_count_returns_none(self):
        assert get_sample_count({}) is None
        assert get_sample_count({"measured_via": "no count mentioned"}) is None

    def test_boolean_sample_count_is_rejected_not_counted(self):
        # bool is an int subclass; True must not read as 1 sample.
        assert get_sample_count({"sample_count": True}) is None
        assert get_sample_count({"sample_count": False}) is None

    def test_non_positive_structured_count_is_rejected(self):
        assert get_sample_count({"sample_count": 0}) is None
        assert get_sample_count({"sample_count": -5}) is None

    def test_validate_shape_accepts_positive_sample_count(self):
        prov = _valid_prov("a" * 64)
        prov["sample_count"] = 120
        assert validate_provenance_shape(prov) is None

    def test_validate_shape_rejects_invalid_sample_count(self):
        for bad in (0, -1, True, "120", 1.5):
            prov = _valid_prov("a" * 64)
            prov["sample_count"] = bad
            err = validate_provenance_shape(prov)
            assert err is not None and "sample_count" in err, bad

    def test_validate_shape_allows_absent_sample_count(self):
        # Legacy records predate the field; absence must stay valid.
        assert validate_provenance_shape(_valid_prov("a" * 64)) is None

    def test_build_provenance_records_sample_count(self, tmp_path):
        board = tmp_path / "board.txt"
        board.write_text("v1")
        prov = build_provenance(
            tmp_path, ["board.txt"], source="measured-live", sample_count=120
        )
        assert prov["sample_count"] == 120

    def test_build_provenance_omits_sample_count_when_none(self, tmp_path):
        board = tmp_path / "board.txt"
        board.write_text("v1")
        prov = build_provenance(tmp_path, ["board.txt"], source="measured-live")
        assert "sample_count" not in prov


# ---------------------------------------------------------------------------
# TestYamlArtifactSupport -- the second anchored record
# (temper_constraints.references.yaml) is YAML, not JSON. load_records()
# must parse it via the same extract_records() walker, not a parallel
# YAML-only checker.
# ---------------------------------------------------------------------------


class TestYamlArtifactSupport:
    def test_yaml_artifact_with_top_level_provenance_is_loaded(self, tmp_path):
        artifact = tmp_path / "manifest.references.yaml"
        artifact.write_text(
            "schema_version: 1\n"
            "authority:\n"
            "  measured_at_commit: " + VALID_COMMIT + "\n"
            "component_aliases:\n"
            "  FOO: BAR\n"
            "provenance:\n"
            "  measured_at_commit: " + VALID_COMMIT + "\n"
            "  dirty: false\n"
            "  inputs:\n"
            "    - path: some/input.json\n"
            "      sha256: " + ("a" * 64) + "\n"
            "  tool_versions: {}\n"
            "  source: backfilled-historical\n"
        )
        records = load_records(artifact)
        assert len(records) == 1
        assert records[0].record_id == "<root>"
        assert records[0].provenance["measured_at_commit"] == VALID_COMMIT
        assert records[0].provenance["inputs"] == [{"path": "some/input.json", "sha256": "a" * 64}]

    def test_yml_suffix_also_dispatches_to_yaml_parser(self, tmp_path):
        artifact = tmp_path / "manifest.yml"
        artifact.write_text("provenance:\n  measured_at_commit: UNKNOWN\n")
        records = load_records(artifact)
        assert len(records) == 1
        assert records[0].provenance == {"measured_at_commit": "UNKNOWN"}

    def test_malformed_yaml_raises_gate_error(self, tmp_path):
        artifact = tmp_path / "broken.yaml"
        artifact.write_text("provenance: [unterminated\n  - this: is not valid yaml::::\n")
        with pytest.raises(GateError, match="malformed YAML"):
            load_records(artifact)

    def test_stale_yaml_artifact_is_reported_stale_not_silently_fresh(self, tmp_path):
        """Reconstructs the exact shape of the real
        temper_constraints.references.yaml finding: a YAML artifact whose
        pinned input hash no longer matches the file on disk must fail
        STALE through the normal evaluate() path -- not a YAML-specific
        carve-out."""
        board = tmp_path / "pcb" / "temper.kicad_pcb"
        board.parent.mkdir()
        board.write_text("(kicad_pcb (version at-reconciliation-time))")
        old_hash = sha256_file(board)

        artifact = tmp_path / "temper_constraints.references.yaml"
        artifact.write_text(
            "schema_version: 1\n"
            "component_aliases:\n"
            "  FOO: BAR\n"
            "provenance:\n"
            f"  measured_at_commit: {VALID_COMMIT}\n"
            "  dirty: UNKNOWN\n"
            "  inputs:\n"
            "    - path: pcb/temper.kicad_pcb\n"
            f"      sha256: {old_hash}\n"
            "  tool_versions: {}\n"
            "  source: backfilled-historical\n"
        )

        # Board drifts after the reconciliation was measured -- the YAML
        # artifact itself is untouched, exactly like the real incident.
        board.write_text("(kicad_pcb (version after board changed))")

        outcome = evaluate(tmp_path, [artifact], allowlist={})
        assert outcome.stale, "a drifted input behind a YAML artifact must be caught, not skipped"
        assert outcome.fresh == []
        key, mismatches = outcome.stale[0]
        assert key == "temper_constraints.references.yaml#<root>"
        assert mismatches[0].path == "pcb/temper.kicad_pcb"


def test_real_references_yaml_artifact_is_registered_and_provenanced():
    """The real repo file, not a synthetic fixture: confirms
    packages/temper-placer/configs/temper_constraints.references.yaml is
    both registered in MEASURED_ARTIFACTS and carries a shape-valid
    provenance block -- the two steps the module docstring says are both
    required for a provenance block to actually be checked ('a provenance
    block nobody points this gate at is exactly as unchecked as no
    provenance at all')."""
    from check_measurement_provenance import MEASURED_ARTIFACTS, REPO_ROOT

    target = (
        REPO_ROOT / "packages" / "temper-placer" / "configs" / "temper_constraints.references.yaml"
    )
    assert target in MEASURED_ARTIFACTS
    records = load_records(target)
    assert len(records) == 1
    assert records[0].provenance is not _MISSING
    err = validate_provenance_shape(records[0].provenance)
    assert err is None, err
