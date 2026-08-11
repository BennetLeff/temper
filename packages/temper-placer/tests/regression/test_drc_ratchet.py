"""Tests for DRC ratchet."""

import json
from pathlib import Path

from temper_placer.regression.drc_ratchet import (
    DrcRatchet,
    DrcRatchetResult,
    check_noise_headroom,
)


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


class TestPerTypeWarningCeilings:
    """`warnings_by_type` is enforced with the exact same semantics as
    `violations_by_type` on the error side (see `TestPerTypeCeilings`).

    The aggregate `warning_ceiling` is coarse enough that 517 of 696
    measured warnings on the real board are cosmetic silkscreen findings
    (silk_edge_clearance, silk_over_copper, silk_overlap, ...) pooling
    together with structural findings like `missing_courtyard` and
    `pth_inside_courtyard` -- exactly the failure mode the per-type ERROR
    ceilings were added to prevent. This class mirrors that fix for
    warnings.
    """

    @staticmethod
    def _entry(tmp_path: Path, warnings_by_type: dict, warning_ceiling: int = 1000):
        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(
            json.dumps(
                {
                    "boards": [
                        {
                            "board_id": "b",
                            "path": "pcb/b.kicad_pcb",
                            "error_ceiling": 100,
                            "warning_ceiling": warning_ceiling,
                            "warnings_by_type": warnings_by_type,
                        }
                    ]
                }
            )
        )
        ratchet = DrcRatchet(ceiling_path, backend="kicad-cli")
        ratchet.load()
        return ratchet, ratchet.entries["b"]

    def _check(self, tmp_path, warnings_by_type, current, monkeypatch, warning_ceiling=1000):
        """Drive _check_board with a stubbed kicad-cli backend returning
        zero errors and a warnings breakdown by rule.
        """
        import temper_placer.validation._drc_api as drc_api

        ratchet, entry = self._entry(tmp_path, warnings_by_type, warning_ceiling)
        warnings = [
            type("W", (), {"rule": rule})()
            for rule, n in current.items()
            for _ in range(n)
        ]
        result_obj = type(
            "R",
            (),
            {
                "error_count": 0,
                "warning_count": len(warnings),
                "errors": [],
                "warnings": warnings,
            },
        )()
        monkeypatch.setattr(drc_api, "run_drc", lambda _p: result_obj)
        pcb = tmp_path / "b.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        return ratchet._check_board("b", pcb, entry)

    def test_within_per_type_ceilings_passes(self, tmp_path, monkeypatch):
        r = self._check(tmp_path, {"silk_overlap": 119}, {"silk_overlap": 119}, monkeypatch)
        assert r.passed, r.message

    def test_category_over_its_ceiling_fails(self, tmp_path, monkeypatch):
        r = self._check(tmp_path, {"silk_overlap": 119}, {"silk_overlap": 120}, monkeypatch)
        assert not r.passed
        assert "silk_overlap 120 > 119" in r.message

    def test_new_category_has_implicit_zero_ceiling(self, tmp_path, monkeypatch):
        """A warning class absent from the record must not arrive for free."""
        r = self._check(
            tmp_path,
            {"silk_overlap": 119},
            {"silk_overlap": 119, "missing_courtyard": 1},
            monkeypatch,
        )
        assert not r.passed
        assert "missing_courtyard 1 > 0" in r.message

    def test_per_type_fails_even_when_aggregate_has_room(self, tmp_path, monkeypatch):
        """The whole point: the aggregate warning_ceiling must not mask a
        per-category regression, exactly like the error side.
        """
        r = self._check(
            tmp_path,
            {"silk_overlap": 119},
            {"silk_overlap": 200},
            monkeypatch,
            warning_ceiling=1000,  # aggregate has tons of room
        )
        assert not r.passed, "aggregate warning slack masked a per-category regression"

    def test_backend_cannot_break_down_does_not_read_as_clean(self, tmp_path, monkeypatch):
        """When the backend can't supply a warnings breakdown (the rust
        backend never can), the per-type warning check must be skipped --
        never silently treated as '0 categories, so nothing regressed'.
        The aggregate check must still run and still catch a real
        regression; this is what stops "can't verify per-type" from ever
        reading as "verified clean".
        """
        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(
            json.dumps(
                {
                    "boards": [
                        {
                            "board_id": "b",
                            "path": "pcb/b.kicad_pcb",
                            "error_ceiling": 100,
                            "warning_ceiling": 5,
                            "warnings_by_type": {"silk_overlap": 0},
                        }
                    ]
                }
            )
        )
        ratchet = DrcRatchet(ceiling_path, backend="rust")
        ratchet.load()
        entry = ratchet.entries["b"]

        # Stub the rust path directly -- it only ever returns aggregate
        # counts, never a per-type breakdown.
        monkeypatch.setattr(ratchet, "_run_rust_drc", lambda _p: (0, 50))
        pcb = tmp_path / "b.kicad_pcb"
        pcb.write_text("(kicad_pcb)")

        r = ratchet._check_board("b", pcb, entry)

        assert not r.passed
        assert "warnings 50 exceeds ceiling 5" in r.message
        # No per-type warning category can be fabricated when the backend
        # supplied no breakdown -- this dimension was genuinely never
        # checked, and must not masquerade as having been.
        assert not any(c.kind == "warning" for c in r.category_failures)


class TestPerTypeCeilingRaiseDetection:
    """`detect_ceiling_raise` must catch a raise hidden inside
    `warnings_by_type` even when the aggregate `warning_ceiling` itself
    does not increase (or even decreases) -- otherwise the per-type
    ceiling enforced by `_check_board` could be silently inflated in the
    committed JSON, bypassing approval entirely.
    """

    def test_new_warning_category_raise_requires_approval(self):
        ratchet = DrcRatchet(Path("dummy.json"))
        old = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 500,
                    "warnings_by_type": {"silk_overlap": 119},
                }
            ]
        }
        new = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 500,
                    "warnings_by_type": {"silk_overlap": 119, "missing_courtyard": 5},
                }
            ]
        }
        result = ratchet.detect_ceiling_raise(old, new, commit_message="fix: whatever")
        assert result is not None
        assert result.exit_code == 2
        assert "requires explicit approval" in result.message

    def test_warning_category_raise_requires_approval_even_if_aggregate_drops(self):
        """The whole point mirrored for the ceiling-raise detector: an
        aggregate decrease must not mask a per-category increase.
        """
        ratchet = DrcRatchet(Path("dummy.json"))
        old = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 500,
                    "warnings_by_type": {"silk_overlap": 119, "silk_edge_clearance": 199},
                }
            ]
        }
        new = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 400,  # aggregate DROPPED
                    "warnings_by_type": {"silk_overlap": 300, "silk_edge_clearance": 100},
                }
            ]
        }
        result = ratchet.detect_ceiling_raise(old, new, commit_message="fix: whatever")
        assert result is not None
        assert result.exit_code == 2

    def test_warning_category_raise_approved_with_trailer(self):
        ratchet = DrcRatchet(Path("dummy.json"))
        old = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 500,
                    "warnings_by_type": {"silk_overlap": 119},
                }
            ]
        }
        new = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 500,
                    "warnings_by_type": {"silk_overlap": 200},
                }
            ]
        }
        result = ratchet.detect_ceiling_raise(
            old, new, commit_message="Ceiling-Approval: reviewer-id\nfix: raise silk_overlap"
        )
        assert result is None

    def test_warning_category_lowered_needs_no_approval(self):
        ratchet = DrcRatchet(Path("dummy.json"))
        old = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 500,
                    "warnings_by_type": {"silk_overlap": 200},
                }
            ]
        }
        new = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 500,
                    "warnings_by_type": {"silk_overlap": 100},
                }
            ]
        }
        result = ratchet.detect_ceiling_raise(old, new, commit_message="fix: lower ceiling")
        assert result is None


class TestPerTypeErrorCeilingRaiseDetection:
    """Mirrors `TestPerTypeCeilingRaiseDetection` for `violations_by_type`
    (the error side) rather than `warnings_by_type`.

    Before this coverage existed, `detect_ceiling_raise` only inspected
    `warnings_by_type` for a per-category raise -- a per-type *error*
    ceiling (e.g. `clearance`, `hole_clearance`) could be raised directly in
    the committed JSON with no `Ceiling-Approval:` trailer and this
    detector would say nothing, even though `_check_board` enforces that
    exact ceiling at runtime. That is precisely the same class of gap the
    `warnings_by_type` tests above exist to prevent, just on the other
    exhaustive record.
    """

    def test_new_violation_category_raise_requires_approval(self):
        ratchet = DrcRatchet(Path("dummy.json"))
        old = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 500,
                    "violations_by_type": {"clearance": 9},
                }
            ]
        }
        new = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 500,
                    "violations_by_type": {"clearance": 9, "hole_to_hole": 1},
                }
            ]
        }
        result = ratchet.detect_ceiling_raise(old, new, commit_message="fix: whatever")
        assert result is not None
        assert result.exit_code == 2
        assert "requires explicit approval" in result.message
        assert "violations_by_type[hole_to_hole] 0 -> 1" in result.message

    def test_violation_category_raise_requires_approval_even_if_aggregate_drops(self):
        """An aggregate error_ceiling decrease must not mask a per-category
        increase hidden in violations_by_type.
        """
        ratchet = DrcRatchet(Path("dummy.json"))
        old = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 1017,
                    "warning_ceiling": 762,
                    "violations_by_type": {"clearance": 502, "shorting_items": 199},
                }
            ]
        }
        new = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 900,  # aggregate DROPPED
                    "warning_ceiling": 762,
                    "violations_by_type": {"clearance": 600, "shorting_items": 150},
                }
            ]
        }
        result = ratchet.detect_ceiling_raise(old, new, commit_message="fix: whatever")
        assert result is not None
        assert result.exit_code == 2
        assert "violations_by_type[clearance] 502 -> 600" in result.message

    def test_violation_category_raise_approved_with_trailer(self):
        ratchet = DrcRatchet(Path("dummy.json"))
        old = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 500,
                    "violations_by_type": {"clearance": 9},
                }
            ]
        }
        new = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 500,
                    "violations_by_type": {"clearance": 20},
                }
            ]
        }
        result = ratchet.detect_ceiling_raise(
            old, new, commit_message="Ceiling-Approval: reviewer-id\nfix: raise clearance"
        )
        assert result is None

    def test_violation_category_lowered_needs_no_approval(self):
        ratchet = DrcRatchet(Path("dummy.json"))
        old = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 500,
                    "violations_by_type": {"clearance": 200},
                }
            ]
        }
        new = {
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 100,
                    "warning_ceiling": 500,
                    "violations_by_type": {"clearance": 100},
                }
            ]
        }
        result = ratchet.detect_ceiling_raise(old, new, commit_message="fix: lower ceiling")
        assert result is None


class TestKicadCliVersionPin:
    """`drc_ceiling.json` records the kicad-cli version a board was
    measured with (``provenance.tool_versions.kicad-cli``), but nothing
    previously compared it against the version actually running the gate --
    a CI image bump or a different local install could silently measure
    with a different DRC engine and the gate would never say so. See the
    task's own falsifier: two patch versions (10.0.4 vs 10.0.5) were shown
    to agree on this board within noise (docs/evidence/
    2026-07-27-drc-truth-gate-discrepancy.md section 2), so a mismatch must
    be reported loudly rather than hard-failing the whole gate -- but it
    must never again go unmentioned.
    """

    @staticmethod
    def _entry(tmp_path: Path, recorded_version: str | None, error_ceiling: int = 100):
        board: dict = {
            "board_id": "b",
            "path": "pcb/b.kicad_pcb",
            "error_ceiling": error_ceiling,
            "warning_ceiling": 1000,
        }
        if recorded_version is not None:
            board["provenance"] = {"tool_versions": {"kicad-cli": recorded_version}}
        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(json.dumps({"boards": [board]}))
        ratchet = DrcRatchet(ceiling_path, backend="kicad-cli")
        ratchet.load()
        return ratchet, ratchet.entries["b"]

    def _check(self, tmp_path, recorded_version, running_version, monkeypatch, error_ceiling=100):
        import temper_placer.validation._drc_api as drc_api

        ratchet, entry = self._entry(tmp_path, recorded_version, error_ceiling)
        result_obj = type("R", (), {"error_count": 0, "warning_count": 0, "errors": []})()
        monkeypatch.setattr(drc_api, "run_drc", lambda _p: result_obj)
        monkeypatch.setattr(drc_api, "get_kicad_cli_version", lambda: running_version)
        pcb = tmp_path / "b.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        return ratchet._check_board("b", pcb, entry)

    def test_loaded_entry_carries_recorded_version(self, tmp_path):
        _ratchet, entry = self._entry(tmp_path, "10.0.4")
        assert entry.tool_versions == {"kicad-cli": "10.0.4"}

    def test_matching_version_is_silent(self, tmp_path, monkeypatch):
        r = self._check(tmp_path, "10.0.4", "10.0.4", monkeypatch)
        assert r.passed
        assert not r.kicad_cli_version_mismatch
        assert "mismatch" not in r.message.lower()

    def test_mismatched_version_reported_prominently_on_pass(self, tmp_path, monkeypatch):
        """Even a passing run must not silently measure with a different
        engine than the one the ceiling was calibrated against."""
        r = self._check(tmp_path, "10.0.4", "10.0.5", monkeypatch)
        assert r.passed  # a version bump alone does not fail the gate
        assert r.kicad_cli_version_mismatch
        assert r.kicad_cli_version_running == "10.0.5"
        assert r.kicad_cli_version_expected == "10.0.4"
        assert "kicad-cli version mismatch" in r.message.lower()
        assert "10.0.4" in r.message
        assert "10.0.5" in r.message

    def test_mismatched_version_reported_prominently_on_fail(self, tmp_path, monkeypatch):
        """The mismatch note must also surface on a FAIL result -- not just
        the pass path -- since a red gate is exactly when a reader most
        needs to know the measuring instrument changed."""
        r = self._check(tmp_path, "10.0.4", "10.0.5", monkeypatch, error_ceiling=-1)
        assert not r.passed
        assert r.kicad_cli_version_mismatch
        assert "kicad-cli version mismatch" in r.message.lower()

    def test_missing_recorded_version_does_not_fabricate_a_mismatch(self, tmp_path, monkeypatch):
        """An older ceiling entry with no provenance block at all must not
        be treated as a mismatch -- there is nothing to compare against."""
        r = self._check(tmp_path, None, "10.0.5", monkeypatch)
        assert r.passed
        assert not r.kicad_cli_version_mismatch


class TestCategorySourceLabeling:
    """`violations_by_type`/`warnings_by_type` in the ceiling file, and the
    per-type failures the ratchet reports at runtime, can come from
    different DRC engines (kicad-cli's native rule checker vs.
    ``temper_drc_rs``'s own safety checks, e.g. its ``creepage`` rule --
    not a KiCad DRC violation type at all). Mixing them without saying
    which produced which number lets a reader mistake one engine's finding
    for the other's -- this is what closes that gap.
    """

    def test_ceiling_category_source_is_loaded(self, tmp_path):
        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(
            json.dumps(
                {
                    "boards": [
                        {
                            "board_id": "b",
                            "path": "pcb/b.kicad_pcb",
                            "error_ceiling": 100,
                            "warning_ceiling": 1000,
                            "category_source": "kicad-cli",
                            "violations_by_type": {"clearance": 10},
                        }
                    ]
                }
            )
        )
        ratchet = DrcRatchet(ceiling_path, backend="kicad-cli")
        ratchet.load()
        assert ratchet.entries["b"].category_source == "kicad-cli"

    def test_category_failure_records_its_source(self, tmp_path, monkeypatch):
        """Every DrcCategoryFailure produced by the kicad-cli backend must
        say so -- it is the only backend that currently supplies a
        per-type breakdown at all (see _run_rust_drc, which returns only
        an aggregate (errors, warnings) tuple)."""
        import temper_placer.validation._drc_api as drc_api

        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(
            json.dumps(
                {
                    "boards": [
                        {
                            "board_id": "b",
                            "path": "pcb/b.kicad_pcb",
                            "error_ceiling": 100,
                            "warning_ceiling": 1000,
                            "violations_by_type": {"clearance": 9},
                        }
                    ]
                }
            )
        )
        ratchet = DrcRatchet(ceiling_path, backend="kicad-cli")
        ratchet.load()
        entry = ratchet.entries["b"]

        errors = [type("E", (), {"rule": "clearance"})() for _ in range(10)]
        result_obj = type(
            "R", (), {"error_count": len(errors), "warning_count": 0, "errors": errors}
        )()
        monkeypatch.setattr(drc_api, "run_drc", lambda _p: result_obj)
        pcb = tmp_path / "b.kicad_pcb"
        pcb.write_text("(kicad_pcb)")

        r = ratchet._check_board("b", pcb, entry)
        assert not r.passed
        (failure,) = r.category_failures
        assert failure.source == "kicad-cli"
        assert "source: kicad-cli" in r.message


class TestNoiseHeadroomGuard:
    """`_check_board` runs `run_drc` exactly ONCE per CI invocation and
    compares that lone sample straight against the ceiling. That is only
    safe if the ceiling's headroom above the historical max (``ceiling -
    max(observed)``) is at least as wide as a category's own measured
    run-to-run spread (``max(observed) - min(observed)``) -- otherwise a
    single fresh sample can land outside the previously-observed range
    from noise alone, failing a board that never regressed.
    ``check_noise_headroom`` checks that invariant against the ceiling
    file's own committed ``nondeterministic_error_types`` data (the
    120-sample characterization ``AGENTS.md``'s protocol already
    requires) instead of assuming it holds.
    """

    @staticmethod
    def _entry(tmp_path, nondet, by_type, error_ceiling=1000):
        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(
            json.dumps(
                {
                    "boards": [
                        {
                            "board_id": "b",
                            "path": "pcb/b.kicad_pcb",
                            "error_ceiling": error_ceiling,
                            "warning_ceiling": 0,
                            "violations_by_type": by_type,
                            "nondeterministic_error_types": nondet,
                        }
                    ]
                }
            )
        )
        ratchet = DrcRatchet(ceiling_path, backend="kicad-cli")
        ratchet.load()
        return ratchet, ratchet.entries["b"]

    def test_max_plus_one_headroom_passes_when_spread_is_one(self, tmp_path):
        """The file's own ``max + 1`` convention on a two-valued category
        (e.g. this board's real ``clearance``/``shorting_items`` records):
        headroom == spread == 1, exactly at the boundary -- safe."""
        ratchet, entry = self._entry(
            tmp_path,
            nondet={"clearance": {"observed": [377, 378], "samples": 120}},
            by_type={"clearance": 379},
        )
        assert check_noise_headroom("b", entry) == []

    def test_headroom_smaller_than_spread_fails_loudly(self, tmp_path):
        """Anti-vacuity: reproduces this board's real recorded ``creepage``
        category verbatim (3 distinct observed values over 120 samples,
        spread 2) sitting behind a ``max + 1`` ceiling (headroom 1). The
        guard must flag this rather than silently pass it -- and it does,
        on this repo's actual committed drc_ceiling.json, not just in this
        synthetic fixture (verified separately; see the PR description)."""
        ratchet, entry = self._entry(
            tmp_path,
            nondet={"creepage": {"observed": [185, 186, 187], "samples": 120}},
            by_type={"creepage": 188},
        )
        violations = check_noise_headroom("b", entry)
        assert len(violations) == 1
        v = violations[0]
        assert v.board_id == "b"
        assert v.category == "creepage"
        assert v.spread == 2
        assert v.headroom == 1
        assert v.ceiling == 188
        assert "creepage" in v.message
        assert "188" in v.message

    def test_headroom_wider_than_spread_passes(self, tmp_path):
        ratchet, entry = self._entry(
            tmp_path,
            nondet={"shorting_items": {"observed": [199, 200], "samples": 120}},
            by_type={"shorting_items": 205},  # generous +5 headroom vs. spread 1
        )
        assert check_noise_headroom("b", entry) == []

    def test_category_missing_from_violations_by_type_is_skipped(self, tmp_path):
        """A category the nondeterministic block names but with no
        corresponding per-type ceiling (yet) has nothing to compare
        headroom against -- must not crash or be misreported."""
        ratchet, entry = self._entry(
            tmp_path,
            nondet={"creepage": {"observed": [185, 186, 187], "samples": 120}},
            by_type={},
        )
        assert check_noise_headroom("b", entry) == []

    def test_single_observed_value_is_skipped(self, tmp_path):
        """A category recorded with only one distinct observed value has no
        spread to compare -- must not raise and must not be reported."""
        ratchet, entry = self._entry(
            tmp_path,
            nondet={"clearance": {"observed": [378], "samples": 120}},
            by_type={"clearance": 379},
        )
        assert check_noise_headroom("b", entry) == []

    def test_no_nondeterministic_block_returns_empty(self, tmp_path):
        ratchet, entry = self._entry(tmp_path, nondet={}, by_type={"clearance": 379})
        assert check_noise_headroom("b", entry) == []

    def test_missing_samples_field_does_not_crash(self, tmp_path):
        ratchet, entry = self._entry(
            tmp_path,
            nondet={"creepage": {"observed": [185, 186, 187]}},  # no "samples" key
            by_type={"creepage": 188},
        )
        violations = check_noise_headroom("b", entry)
        assert len(violations) == 1
        assert violations[0].samples is None
        assert "unrecorded sample count" in violations[0].message

    def test_ratchet_method_aggregates_across_boards(self, tmp_path):
        """``DrcRatchet.check_noise_headroom`` must report a board_id per
        violation and must not flag a safe board just because another
        board in the same file is unsafe."""
        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(
            json.dumps(
                {
                    "boards": [
                        {
                            "board_id": "safe_board",
                            "path": "pcb/a.kicad_pcb",
                            "error_ceiling": 1000,
                            "warning_ceiling": 0,
                            "violations_by_type": {"clearance": 379},
                            "nondeterministic_error_types": {
                                "clearance": {"observed": [377, 378], "samples": 120}
                            },
                        },
                        {
                            "board_id": "unsafe_board",
                            "path": "pcb/b.kicad_pcb",
                            "error_ceiling": 1000,
                            "warning_ceiling": 0,
                            "violations_by_type": {"creepage": 188},
                            "nondeterministic_error_types": {
                                "creepage": {"observed": [185, 186, 187], "samples": 120}
                            },
                        },
                    ]
                }
            )
        )
        ratchet = DrcRatchet(ceiling_path, backend="kicad-cli")
        ratchet.load()
        violations = ratchet.check_noise_headroom()
        assert len(violations) == 1
        assert violations[0].board_id == "unsafe_board"
        assert violations[0].category == "creepage"


class TestNoiseHeadroomAntiVacuity:
    """Demonstrates, by driving ``_check_board`` directly against a
    synthetic noisy oracle (never a real kicad-cli run), that insufficient
    ceiling headroom produces REAL spurious FAILs on an unchanged board --
    and that widening headroom to at least the measured spread (the
    guard's own remedy) eliminates them. This is the
    ``TestFailBeforePassAfter`` pattern from
    ``scripts/tests/test_check_isolation_keepout.py`` applied to
    ``check_noise_headroom``'s predicate itself: the static "headroom <
    spread => unsafe" verdict must correspond to an actual single-sample
    failure mode, not just a plausible-sounding inequality.

    The oracle's TRUE support (185..189, 5 values) is deliberately WIDER
    than the 3 values (185-187) an earlier/smaller sample happened to
    observe -- modelling exactly the risk the guard exists to catch: a
    sample too small to have seen the full range yet, with a ceiling set
    from what it did see.
    """

    TRUE_SUPPORT = [185, 186, 187, 188, 189]

    def _stub_cycling_run_drc(self, monkeypatch):
        """Deterministically cycles through TRUE_SUPPORT on each call --
        no randomness, so the test is not flaky, while still exercising
        every value in the true (wider-than-observed) range repeatedly."""
        import temper_placer.validation._drc_api as drc_api

        state = {"i": 0}

        def _run(_pcb_path):
            n = self.TRUE_SUPPORT[state["i"] % len(self.TRUE_SUPPORT)]
            state["i"] += 1
            errors = [type("E", (), {"rule": "creepage"})() for _ in range(n)]
            return type(
                "R", (), {"error_count": len(errors), "warning_count": 0, "errors": errors}
            )()

        monkeypatch.setattr(drc_api, "run_drc", _run)

    def _entry(self, tmp_path, ceiling):
        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(
            json.dumps(
                {
                    "boards": [
                        {
                            "board_id": "b",
                            "path": "pcb/b.kicad_pcb",
                            "error_ceiling": 1000,
                            "warning_ceiling": 0,
                            "violations_by_type": {"creepage": ceiling},
                        }
                    ]
                }
            )
        )
        ratchet = DrcRatchet(ceiling_path, backend="kicad-cli")
        ratchet.load()
        pcb = tmp_path / "b.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        return ratchet, ratchet.entries["b"], pcb

    def test_before_undersized_headroom_spuriously_fails(self, tmp_path, monkeypatch):
        """ceiling = 188 -- this board's REAL recorded creepage ceiling
        (observed-max-187 + 1), which ``check_noise_headroom`` already
        flags as unsafe (spread 2 > headroom 1) in
        ``TestNoiseHeadroomGuard.test_headroom_smaller_than_spread_fails_loudly``.
        Run against the wider TRUE oracle: every 5th sample (the 189 draw)
        must FAIL even though nothing about the board changed between
        calls -- proving the flagged risk is real, not hypothetical."""
        ratchet, entry, pcb = self._entry(tmp_path, ceiling=188)
        self._stub_cycling_run_drc(monkeypatch)

        results = [ratchet._check_board("b", pcb, entry) for _ in range(25)]

        failures = [r for r in results if not r.passed]
        assert len(failures) == 5, "expected exactly the five 189-draws (1 in 5) to fail"
        for r in failures:
            assert any(f.rule == "creepage" and f.count == 189 for f in r.category_failures)
        # And the complementary case: the same unchanged board also PASSED
        # on other draws -- this is genuinely flaky pass/fail on noise
        # alone, not a consistent regression.
        assert len(results) - len(failures) == 20

    def test_after_widened_headroom_eliminates_spurious_fails(self, tmp_path, monkeypatch):
        """Same TRUE oracle, ceiling widened per the guard's own remedy --
        headroom >= measured spread, i.e. 187 (the old observed max) + 2
        (the old observed spread) = 189 -- happens to exactly cover this
        oracle's true max. Zero draws fail across a full cycle."""
        ratchet, entry, pcb = self._entry(tmp_path, ceiling=189)
        self._stub_cycling_run_drc(monkeypatch)

        results = [ratchet._check_board("b", pcb, entry) for _ in range(25)]

        failures = [r for r in results if not r.passed]
        assert failures == []

    def test_guard_predicate_matches_the_empirical_before_after_outcome(self, tmp_path):
        """Ties the two demonstrations above back to the static guard:
        given the SAME recorded 120-sample characterization (observed
        185-187, unchanged -- widening the ceiling does not by itself
        mean anyone re-measured), the guard says UNSAFE for the ceiling
        that empirically failed above (188) and SAFE for the ceiling that
        empirically held above (189)."""
        _, unsafe_entry = TestNoiseHeadroomGuard._entry(
            tmp_path,
            nondet={"creepage": {"observed": [185, 186, 187], "samples": 120}},
            by_type={"creepage": 188},
        )
        assert len(check_noise_headroom("b", unsafe_entry)) == 1

        _, safe_entry = TestNoiseHeadroomGuard._entry(
            tmp_path,
            nondet={"creepage": {"observed": [185, 186, 187], "samples": 120}},
            by_type={"creepage": 189},
        )
        assert check_noise_headroom("b", safe_entry) == []


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    while not (p / ".git").exists() and p != p.parent:
        p = p.parent
    return p


class TestRealCeilingFileNoiseHeadroom:
    """Regression test against the ACTUAL committed
    ``power_pcb_dataset/drc_ceiling.json`` -- every other test in this
    module drives ``check_noise_headroom`` against synthetic fixtures.
    This one loads the real file so a future re-measurement that
    reintroduces the 2026-08-11 bug (a nondeterministic category's ceiling
    headroom copied forward as ``max + 1`` without checking it against its
    own measured spread -- the mistake every creepage record made from the
    #602 K3 swap through 2026-08-11) fails an existing test immediately,
    rather than only being caught by CI's separate ``ci_check_drc.py``
    invocation (which additionally requires a live kicad-cli).

    Before the 2026-08-11 fix, this test failed for real: creepage's
    committed ceiling was 185 (observed max 184 + 1), against a measured
    spread of 2 (observed [182, 183, 184]) -- headroom 1 < spread 2.
    """

    def test_committed_ceiling_file_has_no_noise_headroom_violations(self):
        repo_root = _repo_root()
        ceiling_path = repo_root / "power_pcb_dataset" / "drc_ceiling.json"
        assert ceiling_path.exists(), f"expected {ceiling_path} to exist"

        ratchet = DrcRatchet(ceiling_path, backend="kicad-cli")
        ratchet.load()
        assert ratchet.entries, "expected at least one board entry"

        violations = ratchet.check_noise_headroom()
        assert violations == [], (
            "the committed drc_ceiling.json has a nondeterministic category "
            "whose ceiling headroom is smaller than its own measured spread "
            f"-- scripts/ci_check_drc.py would FAIL on this: {[v.message for v in violations]}"
        )
