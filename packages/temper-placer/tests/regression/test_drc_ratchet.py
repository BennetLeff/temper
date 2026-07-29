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
