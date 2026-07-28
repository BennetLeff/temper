"""Tests for DRC ratchet."""

import json
from pathlib import Path

from temper_placer.regression.drc_ratchet import DrcRatchet, DrcRatchetResult


class TestDrcRatchet:
    def test_load_ceiling(self, tmp_path: Path):
        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(
            json.dumps(
                {
                    "boards": [
                        {
                            "board_id": "temper_routed",
                            "path": "pcb/temper_routed.kicad_pcb",
                            "error_ceiling": 3042,
                            "warning_ceiling": 0,
                        }
                    ]
                }
            )
        )
        ratchet = DrcRatchet(ceiling_path)
        ratchet.load()
        assert "temper_routed" in ratchet.entries
        entry = ratchet.entries["temper_routed"]
        assert entry.error_ceiling == 3042
        assert entry.warning_ceiling == 0

    def test_check_missing_pcb(self, tmp_path: Path):
        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(
            json.dumps(
                {
                    "boards": [
                        {
                            "board_id": "missing",
                            "path": "pcb/missing.kicad_pcb",
                            "error_ceiling": 10,
                            "warning_ceiling": 0,
                        }
                    ]
                }
            )
        )
        ratchet = DrcRatchet(ceiling_path)
        ratchet.load()
        results = ratchet.check(tmp_path)
        assert len(results) == 1
        assert not results[0].passed
        assert results[0].exit_code == 1

    def test_detect_ceiling_raise_not_approved(self):
        ratchet = DrcRatchet(Path("dummy.json"))

        old = {"boards": [{"board_id": "b1", "error_ceiling": 100, "warning_ceiling": 0}]}
        new = {"boards": [{"board_id": "b1", "error_ceiling": 200, "warning_ceiling": 0}]}

        result = ratchet.detect_ceiling_raise(old, new, commit_message="fix: update ceiling")
        assert result is not None
        assert result.exit_code == 2
        assert "requires explicit approval" in result.message

    def test_detect_ceiling_raise_approved(self):
        ratchet = DrcRatchet(Path("dummy.json"))

        old = {"boards": [{"board_id": "b1", "error_ceiling": 100, "warning_ceiling": 0}]}
        new = {"boards": [{"board_id": "b1", "error_ceiling": 200, "warning_ceiling": 0}]}

        result = ratchet.detect_ceiling_raise(
            old, new, commit_message="Ceiling-Approval: reviewer-id\nfix: update ceiling"
        )
        assert result is None

    def test_detect_no_raise(self):
        ratchet = DrcRatchet(Path("dummy.json"))

        old = {"boards": [{"board_id": "b1", "error_ceiling": 100, "warning_ceiling": 0}]}
        new = {"boards": [{"board_id": "b1", "error_ceiling": 50, "warning_ceiling": 0}]}

        result = ratchet.detect_ceiling_raise(old, new, commit_message="fix: lowered ceiling")
        assert result is None


class TestDrcRatchetResult:
    def test_pass_result(self):
        result = DrcRatchetResult(passed=True, board_id="b1", message="ok")
        assert result.passed
        assert result.exit_code == 0

    def test_fail_result(self):
        result = DrcRatchetResult(
            passed=False, board_id="b1", message="ceiling exceeded", exit_code=1
        )
        assert not result.passed
        assert result.exit_code == 1

    def test_ceiling_raise_result(self):
        result = DrcRatchetResult(
            passed=False, board_id="b1", message="requires approval", exit_code=2
        )
        assert result.exit_code == 2


class TestPerTypeCeilings:
    """`violations_by_type` is enforced, not just parsed.

    It was previously loaded into DrcCeilingEntry and never read, so the only
    thing standing between the board and a new violation class was the
    aggregate error_ceiling -- coarse enough on this board to hide HighVoltage
    netclass pairs at 0.336mm against a 2.0mm requirement.
    """

    @staticmethod
    def _entry(tmp_path: Path, by_type: dict, error_ceiling: int = 100):
        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(
            json.dumps(
                {
                    "boards": [
                        {
                            "board_id": "b",
                            "path": "pcb/b.kicad_pcb",
                            "error_ceiling": error_ceiling,
                            "warning_ceiling": 1000,
                            "violations_by_type": by_type,
                        }
                    ]
                }
            )
        )
        ratchet = DrcRatchet(ceiling_path, backend="kicad-cli")
        ratchet.load()
        return ratchet, ratchet.entries["b"]

    def _check(self, tmp_path, by_type, current, monkeypatch, error_ceiling=100):
        """Drive _check_board with a stubbed kicad-cli backend."""
        import temper_placer.validation._drc_api as drc_api

        ratchet, entry = self._entry(tmp_path, by_type, error_ceiling)
        errors = [
            type("E", (), {"rule": rule})()
            for rule, n in current.items()
            for _ in range(n)
        ]
        result_obj = type(
            "R",
            (),
            {"error_count": len(errors), "warning_count": 0, "errors": errors},
        )()
        monkeypatch.setattr(drc_api, "run_drc", lambda _p: result_obj)
        pcb = tmp_path / "b.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        return ratchet._check_board("b", pcb, entry)

    def test_within_per_type_ceilings_passes(self, tmp_path, monkeypatch):
        r = self._check(tmp_path, {"clearance": 10}, {"clearance": 10}, monkeypatch)
        assert r.passed, r.message

    def test_category_over_its_ceiling_fails(self, tmp_path, monkeypatch):
        r = self._check(tmp_path, {"clearance": 10}, {"clearance": 11}, monkeypatch)
        assert not r.passed
        assert "clearance 11 > 10" in r.message

    def test_new_category_has_implicit_zero_ceiling(self, tmp_path, monkeypatch):
        """A violation class absent from the record must not arrive for free."""
        r = self._check(
            tmp_path,
            {"clearance": 10},
            {"clearance": 10, "hole_to_hole": 1},
            monkeypatch,
        )
        assert not r.passed
        assert "hole_to_hole 1 > 0" in r.message

    def test_per_type_fails_even_when_aggregate_has_room(self, tmp_path, monkeypatch):
        """The whole point: the aggregate ceiling must not mask a category."""
        r = self._check(
            tmp_path,
            {"clearance": 10},
            {"clearance": 20},
            monkeypatch,
            error_ceiling=100,
        )
        assert not r.passed, "aggregate slack masked a per-category regression"

    def test_slack_is_reported_so_the_ceiling_gets_ratcheted(
        self, tmp_path, monkeypatch
    ):
        r = self._check(
            tmp_path, {"clearance": 5}, {"clearance": 5}, monkeypatch, error_ceiling=90
        )
        assert r.passed
        assert "85 error(s) of unratcheted slack" in r.message


class TestAggregateAndPerTypeEnumeration(TestPerTypeCeilings):
    """Fixing the early-return: the aggregate check must not short-circuit
    the per-type breakdown.

    This is the exact defect documented in
    docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md: on the real
    board, ``current_errors > entry.error_ceiling`` returned before the
    per-type loop ever ran, so six violation categories with an implicit
    ceiling of zero were completely invisible in the gate's output. These
    tests reproduce that shape on a synthetic board and would have failed
    against the pre-fix ``_check_board`` (which returned immediately on the
    aggregate-error check, before the per-type categories below it were
    ever compared).
    """

    def test_aggregate_and_per_type_both_reported(self, tmp_path, monkeypatch):
        """A board exceeding BOTH the aggregate and several per-type
        ceilings must report all of them -- not just the aggregate.
        """
        r = self._check(
            tmp_path,
            by_type={"clearance": 9, "shorting_items": 33},
            current={
                "clearance": 340,  # regressed, present in ceiling file
                "shorting_items": 152,  # regressed, present in ceiling file
                "annular_width": 4,  # new category, implicit ceiling 0
                "hole_to_hole": 1,  # new category, implicit ceiling 0
            },
            monkeypatch=monkeypatch,
            error_ceiling=85,
        )
        assert not r.passed
        assert r.exit_code == 1

        # The aggregate line must still be present...
        assert "errors 497 exceeds ceiling 85" in r.message
        # ...AND every per-type category must be individually named. Before
        # the fix, none of the four lines below could ever appear together
        # with the aggregate line -- the early return meant only one of
        # "aggregate" or "per-type" was ever reported, never both.
        assert "clearance 340 > 9" in r.message
        assert "shorting_items 152 > 33" in r.message
        assert "annular_width 4 > 0" in r.message
        assert "hole_to_hole 1 > 0" in r.message

        # Structured fields carry the same information without needing to
        # re-parse the message.
        assert r.aggregate_error_delta == 497 - 85
        by_rule = {c.rule: c for c in r.category_failures}
        assert set(by_rule) == {"clearance", "shorting_items", "annular_width", "hole_to_hole"}
        assert by_rule["clearance"].is_new is False
        assert by_rule["shorting_items"].is_new is False
        assert by_rule["annular_width"].is_new is True
        assert by_rule["hole_to_hole"].is_new is True
        assert r.violation_deltas["clearance"] == 340 - 9
        assert r.violation_deltas["annular_width"] == 4

    def test_new_categories_are_labeled_distinctly_from_regressions(
        self, tmp_path, monkeypatch
    ):
        """A category absent from violations_by_type must be called out as
        NEW, not folded silently into the regressed-category list.
        """
        r = self._check(
            tmp_path,
            by_type={"clearance": 9},
            current={"clearance": 9, "via_diameter": 4},
            monkeypatch=monkeypatch,
            error_ceiling=200,
        )
        assert not r.passed
        assert "1 new, 0 regressed" in r.message
        assert "[NEW] via_diameter 4 > 0" in r.message
        (failure,) = r.category_failures
        assert failure.rule == "via_diameter"
        assert failure.is_new is True
        assert failure.delta == 4

    def test_aggregate_warning_ceiling_reported_alongside_errors(
        self, tmp_path, monkeypatch
    ):
        """The warning-ceiling check must not be skipped or short-circuit
        the per-type report either.
        """
        import temper_placer.validation._drc_api as drc_api

        ratchet, entry = self._entry(tmp_path, {"clearance": 9}, error_ceiling=200)
        entry.warning_ceiling = 10
        errors = [type("E", (), {"rule": "clearance"})() for _ in range(9)]
        result_obj = type(
            "R", (), {"error_count": len(errors), "warning_count": 50, "errors": errors}
        )()
        monkeypatch.setattr(drc_api, "run_drc", lambda _p: result_obj)
        pcb = tmp_path / "b.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        r = ratchet._check_board("b", pcb, entry)

        assert not r.passed
        assert "warnings 50 exceeds ceiling" in r.message
        assert r.aggregate_warning_delta > 0
