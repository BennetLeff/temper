"""Unit + integration tests for the full-board DRC oracle differential.

Covers U1 (harness) and U2 (mapping + bands) of
docs/plans/2026-08-02-008-feat-full-board-drc-oracle-plan.md.

The slow-marked tests exercise real ``kicad-cli`` and the committed
``temper_drc_rs`` engine and are deselected by the invariant-tests CI job
(``-m "not slow"``), which installs without ``temper-drc-rs``; the
non-slow tests are pure unit tests over the normalization / matching /
verdict machinery and run everywhere.

Fixtures (tests/fixtures/):
- ``drc_differential_clean.kicad_pcb`` — components spread with wide
  margins: both engines report zero mapped violations.
- ``drc_differential_touching.kicad_pcb`` — R1/R2 courtyards overlap:
  both engines report at least one courtyard violation on the same pair.
- ``drc_differential_courtyard_falsifier.kicad_pcb`` — D3/C4 re-encoding
  of the incident pair (an ``fp_circle`` courtyard offset from origin and
  an ``fp_line`` rectangle courtyard): the internal bbox model reports
  ZERO courtyard violations while real kicad-cli DRC reports
  ``courtyards_overlap`` — the "model says zero, real DRC says N" class.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from temper_placer.validation import drc_differential as dd

_TESTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _TESTS_DIR.parent.parent.parent
_BOARD_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_CEILING_PATH = _REPO_ROOT / "power_pcb_dataset" / "drc_ceiling.json"


def _fixture(name: str) -> Path:
    return _TESTS_DIR / "fixtures" / name


def _kicad_available() -> bool:
    from temper_placer.validation._drc_api import is_kicad_cli_available

    return is_kicad_cli_available()


def _internal_available() -> bool:
    try:
        import temper_drc_rs  # noqa: F401

        return True
    except ImportError:
        return False


def _load_ceiling() -> dict:
    with open(_CEILING_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# U1 — harness
# ---------------------------------------------------------------------------


class TestMappingCoverage:
    """U2 test 1: mapping completeness against the ceiling record."""

    def test_every_ceiling_type_has_exactly_one_outcome(self):
        """For every type key in the ceiling record's violations_by_type and
        warnings_by_type, the mapping table yields exactly one outcome: a
        mapped check or an exclusion with cause."""
        ceiling = _load_ceiling()
        board = ceiling["boards"][0]
        all_types = set(board["violations_by_type"]) | set(board["warnings_by_type"])
        assert all_types, "ceiling record must carry per-type keys"

        for vtype in sorted(all_types):
            mapped = vtype in dd.KICAD_TYPE_TO_CLASS
            excluded = vtype in dd.EXCLUDED_KICAD_TYPES
            assert mapped != excluded, (
                f"kicad type {vtype!r} must be mapped XOR excluded, "
                f"got mapped={mapped} excluded={excluded}"
            )
            if excluded:
                assert dd.EXCLUDED_KICAD_TYPES[vtype].strip(), (
                    f"excluded type {vtype!r} must carry an attributed cause"
                )

    def test_mapped_types_resolve_to_real_internal_checks(self):
        """Every canonical class must map to at least one internal check_name
        that the Rust registry actually emits."""
        for cls in dd.KICAD_TYPE_TO_CLASS.values():
            internal_checks = {
                check
                for check, cls2 in dd.INTERNAL_CHECK_TO_CLASS.items()
                if cls2 == cls
            }
            assert internal_checks, f"class {cls!r} has no internal check"
            assert cls in dd.DELTA_BANDS, f"class {cls!r} missing from DELTA_BANDS"


class TestNormalization:
    def test_normalize_internal_violation(self):
        rec = dd.normalize_internal_violation(
            {
                "severity": "CRITICAL",
                "code": "DRC_CLR_001",
                "message": "Clearance violation: C1 to R7",
                "check_name": "drc_clearance",
                "affected_items": ["C1", "R7"],
                "location": {"x": 143.73, "y": 251.815, "layer": None},
            }
        )
        assert rec.rule_class == "clearance"
        assert rec.severity == "critical"
        assert rec.component_pair == frozenset({"C1", "R7"})
        assert rec.location == (143.73, 251.815)

    def test_normalize_internal_unmapped_check_is_none_class(self):
        rec = dd.normalize_internal_violation(
            {"check_name": "routing_parallel_run", "affected_items": ["C1", "C2"]}
        )
        assert rec.rule_class is None

    def test_normalize_kicad_violation(self):
        rec = dd.normalize_kicad_violation(
            "courtyards_overlap", "error", ["D3", "C4"], (101.0, 100.0)
        )
        assert rec.rule_class == "courtyard"
        assert rec.component_pair == frozenset({"C4", "D3"})
        assert rec.location == (101.0, 100.0)
        assert rec.kicad_type == "courtyards_overlap"

    def test_pair_from_items_requires_two(self):
        assert dd._pair_from_items(["C1"]) is None
        assert dd._pair_from_items([]) is None
        assert dd._pair_from_items(["C1", "R7"]) == frozenset({"C1", "R7"})

    def test_location_from_dict_edge_cases(self):
        assert dd._location_from_dict(None) is None
        assert dd._location_from_dict({"x": 1.0}) is None
        assert dd._location_from_dict({"x": "bad", "y": 2.0}) is None
        assert dd._location_from_dict({"x": 1.0, "y": 2.0}) == (1.0, 2.0)


class TestMissingBoard:
    def test_run_differential_missing_board_raises(self):
        with pytest.raises(FileNotFoundError):
            dd.run_differential(_fixture("does_not_exist.kicad_pcb"))

    def test_measure_delta_bands_missing_board_raises(self):
        with pytest.raises(FileNotFoundError):
            dd.measure_delta_bands(_fixture("does_not_exist.kicad_pcb"))


class TestMatching:
    def test_match_records_on_class_and_pair(self):
        internal = [
            dd.ViolationRecord("courtyard", "warning", frozenset({"R1", "R2"}), (100.5, 100.0)),
            dd.ViolationRecord("courtyard", "warning", frozenset({"R3", "R4"}), (200.0, 200.0)),
        ]
        kicad = [
            dd.ViolationRecord("courtyard", "error", frozenset({"R2", "R1"}), (100.6, 100.1)),
        ]
        matched, unmatched_k, unmatched_i = dd.match_records(kicad, internal)
        assert matched == 1
        assert len(unmatched_k) == 0
        assert len(unmatched_i) == 1

    def test_location_out_of_tolerance_does_not_match(self):
        internal = [
            dd.ViolationRecord("clearance", "warning", frozenset({"C1", "C2"}), (100.0, 100.0))
        ]
        kicad = [
            dd.ViolationRecord("clearance", "error", frozenset({"C1", "C2"}), (300.0, 100.0))
        ]
        matched, unmatched_k, _ = dd.match_records(kicad, internal, location_tolerance_mm=5.0)
        assert matched == 0
        assert len(unmatched_k) == 1

    def test_locationless_records_match_on_pair(self):
        internal = [dd.ViolationRecord("courtyard", "warning", frozenset({"A", "B"}), None)]
        kicad = [dd.ViolationRecord("courtyard", "error", frozenset({"A", "B"}), None)]
        matched, _, _ = dd.match_records(kicad, internal)
        assert matched == 1


class TestVerdict:
    """U2 tests 3-5: verdict semantics (unit level, no engines)."""

    def _records(self, cls: str, count: int, prefix: str = "C") -> list[dd.ViolationRecord]:
        return [
            dd.ViolationRecord(cls, "error", frozenset({f"{prefix}{2 * i}", f"{prefix}{2 * i + 1}"}), None)
            for i in range(count)
        ]

    def test_within_band_delta_passes(self):
        """U2 test 3: a delta exactly at the observed max is within band."""
        bands = {"courtyard": {"band": 2}}
        verdict = dd.build_verdict(
            self._records("courtyard", 5),
            self._records("courtyard", 3),
            delta_bands=bands,
        )
        assert verdict.passed is True
        (cd,) = verdict.per_class
        assert cd.delta == 2 and cd.within_band is True

    def test_beyond_band_delta_fails(self):
        """U2 test 4: a delta one past the band fails the verdict."""
        bands = {"courtyard": {"band": 2}}
        verdict = dd.build_verdict(
            self._records("courtyard", 6),
            self._records("courtyard", 3),
            delta_bands=bands,
        )
        assert verdict.passed is False
        (cd,) = verdict.per_class
        assert cd.delta == 3 and cd.within_band is False

    def test_excluded_types_ignored(self):
        """U2 test 5: excluded kicad types never count toward any class and
        the verdict is computed over mapped classes only."""
        kicad = self._records("clearance", 1)
        kicad += [
            dd.ViolationRecord(None, "error", frozenset({"T1", "T2"}), None, kicad_type="tracks_crossing"),
            dd.ViolationRecord(None, "error", frozenset({"V1", "V2"}), None, kicad_type="via_diameter"),
        ]
        internal = self._records("clearance", 1)
        bands = {"clearance": {"band": 0}, "courtyard": {"band": 0}}
        verdict = dd.build_verdict(kicad, internal, delta_bands=bands)
        assert verdict.passed is True
        classes = {cd.rule_class for cd in verdict.per_class}
        assert classes == {"clearance", "courtyard"}
        assert set(verdict.excluded_types_seen) == {"tracks_crossing", "via_diameter"}

    def test_beyond_band_class_identified(self):
        bands = {"courtyard": {"band": 0}, "clearance": {"band": 0}}
        verdict = dd.build_verdict(
            self._records("courtyard", 1),
            [],
            delta_bands=bands,
        )
        failing = [cd.rule_class for cd in verdict.per_class if not cd.within_band]
        assert failing == ["courtyard"]


# ---------------------------------------------------------------------------
# U1 — integration (real engines, committed board + fixtures)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestDifferentialIntegration:
    def test_same_board_both_engines_run(self):
        """U1 test 1: on the committed board both engines complete and the
        report has one row per emitted mapped rule class."""
        if not (_kicad_available() and _internal_available()):
            pytest.skip("kicad-cli and/or temper_drc_rs not available")
        assert _BOARD_PATH.exists(), f"board not found: {_BOARD_PATH}"
        verdict = dd.run_differential(_BOARD_PATH)
        assert verdict.skipped is False, verdict.skip_reason
        assert len(verdict.per_class) == len(dd.DELTA_BANDS)
        assert {cd.rule_class for cd in verdict.per_class} == set(dd.DELTA_BANDS)

    def test_clean_fixture_passes(self):
        """U1 test 2: a synthetic clean placement reports zero mapped
        violations on both engines; the differential verdict is PASS."""
        if not (_kicad_available() and _internal_available()):
            pytest.skip("kicad-cli and/or temper_drc_rs not available")
        verdict = dd.run_differential(_fixture("drc_differential_clean.kicad_pcb"))
        assert verdict.skipped is False, verdict.skip_reason
        assert verdict.passed is True
        for cd in verdict.per_class:
            assert cd.internal_count == 0, cd
            assert cd.kicad_count == 0, cd

    def test_touching_pair_records_match(self):
        """U1 test 3: a synthetic overlap pair fires the internal
        CourtyardCheck AND kicad courtyards_overlap; the records match on
        (rule class, component pair)."""
        if not (_kicad_available() and _internal_available()):
            pytest.skip("kicad-cli and/or temper_drc_rs not available")
        verdict = dd.run_differential(_fixture("drc_differential_touching.kicad_pcb"))
        assert verdict.skipped is False, verdict.skip_reason
        (courtyard,) = [cd for cd in verdict.per_class if cd.rule_class == "courtyard"]
        assert courtyard.internal_count >= 1
        assert courtyard.kicad_count >= 1
        assert courtyard.matched_records >= 1

    def test_falsifier_fails_beyond_band(self):
        """U1 test 4 + U2 test 4 (end-to-end): the D3/C4 fixture — an
        fp_circle courtyard offset from origin and an fp_line rectangle
        courtyard — reproduces the incident class: the internal model
        reports zero courtyard violations while kicad-cli reports
        courtyards_overlap; the verdict is FAIL with a beyond-band delta."""
        if not (_kicad_available() and _internal_available()):
            pytest.skip("kicad-cli and/or temper_drc_rs not available")
        verdict = dd.run_differential(_fixture("drc_differential_courtyard_falsifier.kicad_pcb"))
        assert verdict.skipped is False, verdict.skip_reason
        assert verdict.passed is False
        (courtyard,) = [cd for cd in verdict.per_class if cd.rule_class == "courtyard"]
        assert courtyard.internal_count == 0, "internal model must be blind to the real overlap"
        assert courtyard.kicad_count >= 1
        assert courtyard.delta >= 1
        assert courtyard.within_band is False, "falsifier must stay BEYOND the band"

    def test_committed_board_within_band(self):
        """U2 test 3 (integration): the committed board's per-class deltas
        are within their measured bands — the gate passes on current state."""
        if not (_kicad_available() and _internal_available()):
            pytest.skip("kicad-cli and/or temper_drc_rs not available")
        verdict = dd.run_differential(_BOARD_PATH)
        assert verdict.skipped is False, verdict.skip_reason
        assert verdict.passed is True, [
            f"{cd.rule_class}: delta {cd.delta} > band {cd.band}" for cd in verdict.per_class if not cd.within_band
        ]

    def test_kicad_cli_unavailable_skips(self, monkeypatch: pytest.MonkeyPatch):
        """U1 test 5: with kicad-cli hidden, the harness reports
        SKIPPED-with-cause and never emits PASS."""
        monkeypatch.setattr(
            "temper_placer.validation._drc_api.is_kicad_cli_available",
            lambda: False,
        )
        verdict = dd.run_differential(_fixture("drc_differential_clean.kicad_pcb"))
        assert verdict.skipped is True
        assert verdict.passed is False
        assert "kicad-cli" in (verdict.skip_reason or "")

    def test_is_kicad_cli_unavailable_reflects_binary(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "temper_placer.validation._drc_api.is_kicad_cli_available",
            lambda: False,
        )
        assert dd.is_kicad_cli_unavailable() is True

    def test_internal_engine_unavailable_skips(self, monkeypatch: pytest.MonkeyPatch):
        """A missing internal engine (temper_drc_rs) also yields
        SKIPPED-with-cause — never a silent pass."""
        monkeypatch.setattr(
            dd, "run_internal_engine", lambda pcb: (_ for _ in ()).throw(ImportError("no temper_drc_rs"))
        )
        verdict = dd.run_differential(_fixture("drc_differential_clean.kicad_pcb"))
        assert verdict.skipped is True
        assert verdict.passed is False
        assert "temper_drc_rs" in (verdict.skip_reason or "")


# ---------------------------------------------------------------------------
# U2 — band derivation (two-engine delta distribution)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestBandDerivation:
    def test_measurement_equals_or_under_committed_bands(self):
        """U2 test 2: N paired samples of BOTH engines on the committed board
        produce per-class observed delta maxima that the committed bands
        cover. The band is the measured two-engine delta spread — not the
        ceiling file's kicad-only ranges."""
        if not (_kicad_available() and _internal_available()):
            pytest.skip("kicad-cli and/or temper_drc_rs not available")
        measured = dd.measure_delta_bands(_BOARD_PATH, n_samples=5)
        for cls, spec in measured.items():
            committed = dd.DELTA_BANDS[cls]
            assert spec["band"] == max(spec["observed_max"] + 1, 0), cls
            assert spec["band"] <= committed["band"], (
                f"{cls}: fresh measurement band {spec['band']} exceeds the "
                f"committed band {committed['band']}"
            )
            assert spec["internal_count"] == committed["internal_count"], cls

    def test_band_data_covers_ceiling_kicad_variance(self):
        """The committed band data's kicad-observed component must cover the
        ceiling record's documented *observed* bare-path values: the
        nondeterministic_error_types range for clearance, and the
        deterministic per-type counts (whose recorded value IS the observed
        count).  Two documented exceptions:
        - ``courtyards_overlap`` + ``pth_inside_courtyard`` group into the
          single ``courtyard`` class;
        - ``creepage`` is measured via the DRU-regenerating path
          (ci_check_drc), not bare ``_drc_api.run_drc`` — the differential
          (bare path) cannot see it, so the band records 0 and the ceiling
          ratchet remains its only governor."""
        ceiling = _load_ceiling()
        board = ceiling["boards"][0]
        nondet = board["nondeterministic_error_types"]
        violations = board["violations_by_type"]
        warnings = board["warnings_by_type"]

        # clearance — the ceiling's only nondeterministic category — must be
        # inside the band data's kicad_observed spread.
        clearance_observed = nondet["clearance"]["observed"]
        clearance_band = dd.DELTA_BANDS["clearance"]["kicad_observed"]
        assert min(clearance_observed) >= min(clearance_band)
        assert max(clearance_observed) <= max(clearance_band)

        for cls, kicad_ceiling in violations.items():
            if cls not in dd.KICAD_TYPE_TO_CLASS:
                continue
            canonical = dd.KICAD_TYPE_TO_CLASS[cls]
            if canonical == "courtyard":
                # courtyard class = courtyards_overlap + pth_inside_courtyard
                total = violations.get("courtyards_overlap", 0) + warnings.get(
                    "pth_inside_courtyard", 0
                )
                assert total <= max(dd.DELTA_BANDS[canonical]["kicad_observed"])
            elif cls == "clearance":
                # covered above via nondeterministic_error_types (499-501);
                # the 502 per-type ceiling is observed max + 1 headroom.
                continue
            else:
                # deterministic classes: ceiling value == observed count.
                assert kicad_ceiling <= max(dd.DELTA_BANDS[canonical]["kicad_observed"]), cls

    def test_measurement_matches_committed_internal_counts(self):
        """Internal counts are deterministic: a fresh single run reproduces
        the committed internal_count for every mapped class."""
        if not _internal_available():
            pytest.skip("temper_drc_rs not available")
        internal = dd.run_internal_engine(_BOARD_PATH)
        from collections import Counter

        counts = Counter(r.rule_class for r in internal if r.rule_class)
        for cls, spec in dd.DELTA_BANDS.items():
            assert counts.get(cls, 0) == spec["internal_count"], cls
