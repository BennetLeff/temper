"""Tests for check_measurement_provenance.py.

Three groups:

1. `TestExtractRecords` -- the generic record walker over both supported
   artifact shapes (single top-level "provenance" object, and a list of
   dict records each with its own "provenance" key -- the drc_ceiling.json
   shape).
2. `TestEvaluate` -- `evaluate()`'s classification of fresh / stale /
   allowlisted / problem records, and its anti-vacuity fail-closed behavior
   (zero artifacts, zero records) -- all against synthetic tmp_path
   artifacts, entirely independent of the real repo.
3. `TestFalsifierDrcCeilingReconstruction` -- the task's own falsifier,
   reconstructed directly: a ceiling-shaped artifact whose recorded input
   hash no longer matches the board file on disk must FAIL (STALE, exit
   EXIT_GATE_ERROR); the same artifact, once its provenance is re-recorded
   against the board's current content, must PASS. No `git stash` is used
   anywhere -- both states are plain tmp_path fixtures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_measurement_provenance import (  # noqa: E402
    EXIT_GATE_ERROR,
    EXIT_OK,
    GateError,
    Record,
    _MISSING,
    evaluate,
    extract_records,
    load_records,
)
from _lib.measurement_provenance import build_provenance, sha256_file  # noqa: E402

VALID_SHA = "a" * 64
VALID_COMMIT = "b" * 40


def _valid_prov(sha: str, path: str = "pcb/board.kicad_pcb"):
    return {
        "measured_at_commit": VALID_COMMIT,
        "dirty": False,
        "inputs": [{"path": path, "sha256": sha}],
        "tool_versions": {"kicad-cli": "UNKNOWN"},
        "source": "backfilled-historical",
    }


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
