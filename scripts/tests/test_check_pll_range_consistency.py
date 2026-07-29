"""Tests for check_pll_range_consistency.py.

Every scenario here builds small, hand-written synthetic
``pll_control.h``/``main.ato`` fixtures under ``tmp_path`` rather than
depending on the real repo files (matching the convention in
``test_check_domain_partition.py`` and ``test_check_stale_extensions.py``)
-- the real files are exercised directly by running the gate itself
(``docs/evidence/2026-07-28-pll-defaults-and-range-gate.md``).

Six groups:

1. ``TestParsing`` -- ``parse_firmware_header``/``parse_main_ato``/
   ``parse_ato_physics``/``parse_modules_tank_capacitors``/
   ``parse_modules_tank_coil`` find the right named constants, handle unit
   conversion (Hz/kHz/MHz, H/uH/nH, F/uF/nF/pF), and ignore unrelated
   ``#define``/declaration noise.
2. ``TestChecks`` -- ``run_checks()``'s comparisons, each independently
   falsifiable.
3. ``TestDerivedZvsFloor`` -- the 2026-07-29 addition: the floor is
   *derived* from main.ato's L/C/coupling/tolerance rather than compared,
   it keys off worst-case (minimum) L, and it fails CLOSED -- not skipped,
   not defaulted -- when an input is missing, mistyped, unparseable, or
   outside its sanity band.
4. ``TestAntiVacuity`` -- ``run()`` fails closed on missing files, missing
   individual constants (partial discovery), and the zero-discovery case.
5. ``TestHistoricalRegression`` -- reconstructs the actual 2026-07-28
   defect shapes (PLL_DEFAULT_FREQ_HZ=35000 while main.ato already declared
   f_switching=47kHz; main.ato declaring no tracking-range constants at
   all) as controlled fixtures, and proves the gate catches both, then
   proves the real fix (as committed) passes -- a fail-before/pass-after
   demonstration for the gate itself, since the gate is new and has no
   prior git history to diff against. It also carries the 2026-07-29
   defect shape: the *2026-07-28 fix itself* -- 30kHz agreed on both
   sides -- passes all four original checks and fails the derived floor,
   because both files agreed on a frequency 7.6kHz below resonance.
6. ``TestMatchedPairCancellation`` -- the 2026-07-29 coil specification:
   ``l_tank_assumed`` and ``l_pan_loaded_ratio`` are a matched pair whose
   PRODUCT is the physics, so replacing 150uH x 0.399 with 88uH x 0.68
   moves the derived floor by 3.5Hz. Pins both the cancellation and the
   gate's deliberate asymmetry about half-fixes (it catches the
   hard-switching direction, it cannot catch the other one).
7. ``TestCapacitorToleranceWorstCase`` -- the SAME-DAY follow-up defect:
   the floor was worst-cased for L but not for C, so a capacitor at the
   bottom of its own tolerance band raised f_res without the floor moving
   to cover it. Pins that ``c_tank_tolerance`` is now a required physics
   input, that it raises the derived floor exactly as arithmetic predicts,
   and -- the sharpest regression test -- that a PLL_MIN_FREQ_HZ which
   passed under the L-only (nominal-C) derivation FAILS once the real
   capacitor tolerance is honored.
8. ``TestCoilAcceptanceThresholdMirror`` -- check 8: the gate inverts its
   own floor derivation into a minimum LOADED coil inductance and fails
   the build if ``docs/hardware/TANK_COIL_SPECIFICATION.md``'s stated
   acceptance threshold (parsed from its own prose) disagrees.

Fixture note: ``_repo()`` (and the underlying ``_main_ato()``) default
``c_tank_tolerance`` to ``"0.0"`` -- NOT the real repo's committed 0.05 --
so every pre-existing floor/derivation test above keeps its original,
hand-verified expected numbers unchanged; capacitor-tolerance behaviour is
exercised by explicitly passing ``c_tank_tolerance="0.05"`` (or another
value) in the new test classes. ``_repo()`` also now auto-writes a
``docs/hardware/TANK_COIL_SPECIFICATION.md`` fixture whose acceptance
sentence is computed from the SAME physics/firmware values it was just
given (via the gate's own ``derive_zvs_floor``/``coil_acceptance_l_loaded_
min_h``), so every existing ``run()``-based test keeps passing check 8
without having to hand-compute a matching threshold; tests that want to
exercise check 8 itself pass ``doc_threshold_uh=`` to override it.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_pll_range_consistency import (  # noqa: E402
    EXIT_GATE_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    ZVS_MARGIN_MIN,
    GateError,
    coil_acceptance_l_loaded_min_h,
    derive_zvs_floor,
    parse_ato_physics,
    parse_firmware_header,
    parse_main_ato,
    parse_modules_tank_capacitors,
    parse_modules_tank_coil,
    parse_tank_coil_spec_threshold,
    run,
    run_checks,
)

# Derived-floor arithmetic for the as-committed declarations, recomputed
# by hand here rather than imported, so a bug in the gate's own formula
# cannot make these tests agree with it. This one is L-ONLY worst-cased
# (c_tank_tolerance = 0, which is the fixture DEFAULT below -- see
# TestCapacitorToleranceWorstCase for the c_tank_tolerance=0.05 figures):
#   L_loaded(worst) = 88uH * (1 - 0.10) * 0.68 = 53.856uH
#   f_res           = 1/(2*pi*sqrt(53.856uH * 300nF)) = 39.595kHz
#   required floor  = 1.05 * 39.595kHz = 41.575kHz
#
# Was 41571.0 (150uH * 0.399 = 53.865uH) until 2026-07-29, when the coil
# was specified at 88uH and the pan ratio moved to 0.68 with it. The floor
# moved 3.5Hz. That is the whole point of the change and is pinned as a
# test in TestMatchedPairCancellation below.
EXPECTED_FLOOR_HZ = 41575.0

# The SAME arithmetic, now also worst-casing the tank capacitor at its
# real committed tolerance (+/-5%, WIMA FKP 1 per c_tank1/c_tank2's MPN --
# see docs/hardware/TANK_COIL_SPECIFICATION.md and elec/src/main.ato's
# c_tank_tolerance comment):
#   C_worst        = 300nF * (1 - 0.05) = 285nF
#   f_res          = 1/(2*pi*sqrt(53.856uH * 285nF)) = 40.624kHz
#   required floor = 1.05 * 40.624kHz = 42.655kHz
# The real, as-committed PLL_MIN_FREQ_HZ is 43000 (smallest round kHz
# above this), not 42000 -- see TestCapacitorToleranceWorstCase.
EXPECTED_FLOOR_HZ_WORST_C = 42655.0


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


def _firmware_header(
    tmp_path: Path,
    *,
    min_hz: int = 42000,
    max_hz: int = 50000,
    default_hz: int = 47000,
) -> Path:
    return _write(
        tmp_path / "firmware" / "components" / "control" / "pll_control.h",
        f"""\
        #ifndef PLL_CONTROL_H
        #define PLL_CONTROL_H
        /* unrelated decoy -- must not be picked up by the targeted regex */
        #define FREQ_HYSTERESIS_HZ 10.0f
        #define PLL_MIN_FREQ_HZ     {min_hz}   /**< Minimum switching frequency */
        #define PLL_MAX_FREQ_HZ     {max_hz}   /**< Maximum switching frequency */
        #define PLL_DEFAULT_FREQ_HZ {default_hz}
        #endif
        """,
    )


def _main_ato(
    tmp_path: Path,
    *,
    switching: str = "47kHz",
    tracking_min: str | None = "42kHz",
    tracking_max: str | None = "50kHz",
    l_tank: str | None = "88uH",
    c_tank: str | None = "300nF",
    loaded_ratio: str | None = "0.68",
    tolerance: str | None = "0.10",
    c_tank_tolerance: str | None = "0.0",
) -> Path:
    """Synthetic main.ato. Any of the five derived-floor physics quantities
    can be passed ``None`` to omit it, or a raw string to declare a bad
    one -- both must make the gate fail closed, never skip.

    ``c_tank_tolerance`` defaults to ``"0.0"`` (NOT the real repo's
    committed 0.05) so that every pre-existing test's hand-verified
    L-only-worst-case numbers (``EXPECTED_FLOOR_HZ`` etc.) stay correct
    without editing them; capacitor-tolerance behaviour is exercised by
    passing ``c_tank_tolerance="0.05"`` explicitly.
    """
    lines = [
        "module Top:",
        "    f_line: frequency = 60Hz  # unrelated decoy",
        f"    f_switching: frequency = {switching}",
        "    assert f_switching within 20kHz to 100kHz  # LC tank theoretical bound",
    ]
    if tracking_min is not None:
        lines.append(f"    f_pll_tracking_min: frequency = {tracking_min}")
    if tracking_max is not None:
        lines.append(f"    f_pll_tracking_max: frequency = {tracking_max}")
    # Decoys for the physics parser: right name, wrong type keyword; and
    # right type keyword, wrong name.
    lines.append("    l_tank_assumed_old: inductance = 999uH  # unrelated decoy")
    lines.append("    v_bus_nominal: voltage = 340V  # unrelated decoy")
    if l_tank is not None:
        lines.append(f"    l_tank_assumed: inductance = {l_tank}")
    if c_tank is not None:
        lines.append(f"    c_tank_total: capacitance = {c_tank}")
    if loaded_ratio is not None:
        lines.append(f"    l_pan_loaded_ratio: dimensionless = {loaded_ratio}")
    if tolerance is not None:
        lines.append(f"    l_tank_tolerance: dimensionless = {tolerance}")
    if c_tank_tolerance is not None:
        lines.append(f"    c_tank_tolerance: dimensionless = {c_tank_tolerance}")
    return _write(tmp_path / "elec" / "src" / "main.ato", "\n".join(lines) + "\n")


def _modules_ato(
    tmp_path: Path,
    *,
    c_tank1: str | None = "150nF",
    c_tank2: str | None = "150nF",
    coil: str | None = "88uH +/- 10%",
) -> Path:
    lines = [
        "module ResonantTank:",
        "    c_bypass = new Capacitor",
        "    c_bypass.value = 100nF  # unrelated decoy",
        "    l_filter = new Inductor",
        "    l_filter.value = 999uH  # unrelated decoy",
    ]
    for name, value in (("c_tank1", c_tank1), ("c_tank2", c_tank2)):
        if value is not None:
            lines.append(f"    {name} = new Capacitor")
            lines.append(f"    {name}.value = {value}")
    if coil is not None:
        lines.append("    inductor_conn = new Inductor")
        lines.append(f"    inductor_conn.value = {coil}")
    return _write(tmp_path / "elec" / "src" / "modules.ato", "\n".join(lines) + "\n")


def _tank_coil_spec(
    tmp_path: Path,
    *,
    threshold_uh: float | str | None,
    include_anchor: bool = True,
) -> Path:
    """Synthetic ``docs/hardware/TANK_COIL_SPECIFICATION.md``, carrying only
    the one sentence check 8 actually parses: a backtick-quoted
    ``L_loaded >= <value> uH`` immediately followed by "is requirement #3".

    ``include_anchor=False`` omits that sentence entirely (surrounding prose
    still present), to test the "anchor not found" gate-error path.
    """
    if include_anchor:
        body = (
            "# Tank Coil -- Specification and Incoming Acceptance Test\n\n"
            "Some unrelated prose mentioning L_loaded 999 uH so a naive "
            "any-number-near-L_loaded match would pick up the wrong value.\n\n"
            f"**`L_loaded ≥ {threshold_uh} µH` is requirement #3.** "
            "Requirement #3b is a secondary screen.\n"
        )
    else:
        body = (
            "# Tank Coil -- Specification and Incoming Acceptance Test\n\n"
            "This fixture deliberately omits the anchor sentence check 8 "
            "requires, to test the gate-error path.\n"
        )
    return _write(tmp_path / "docs" / "hardware" / "TANK_COIL_SPECIFICATION.md", body)


def _repo(tmp_path: Path, **kwargs) -> Path:
    """Write all four source files a full ``run()`` needs.

    By default this also writes ``TANK_COIL_SPECIFICATION.md`` with an
    acceptance threshold computed from the SAME physics/firmware values
    just written (via the gate's own ``derive_zvs_floor``/
    ``coil_acceptance_l_loaded_min_h``), so check 8 passes automatically
    and every pre-existing ``run()``-based test does not need to know
    about it. Pass ``doc_threshold_uh=<value>`` to override with an
    explicit (e.g. deliberately wrong, or stale) number instead, or
    ``write_doc=False`` to omit the file entirely.
    """
    doc_threshold_uh = kwargs.pop("doc_threshold_uh", None)
    write_doc = kwargs.pop("write_doc", True)
    fw = {k: v for k, v in kwargs.items() if k in ("min_hz", "max_hz", "default_hz")}
    mods = {k: v for k, v in kwargs.items() if k in ("c_tank1", "c_tank2", "coil")}
    ato = {k: v for k, v in kwargs.items() if k not in fw and k not in mods}
    _firmware_header(tmp_path, **fw)
    ato_path = _main_ato(tmp_path, **ato)
    _modules_ato(tmp_path, **mods)

    if write_doc:
        if doc_threshold_uh is not None:
            threshold = doc_threshold_uh
        else:
            # Auto-derive the matching threshold from what was just
            # written, using the gate's OWN functions -- this is fixture
            # plumbing (making unrelated tests not have to know check 8
            # exists), not a test of check 8 itself. Tests of check 8
            # pass doc_threshold_uh explicitly instead. If the physics are
            # deliberately missing/invalid (some tests do this on purpose,
            # to exercise GateError paths), this raises the SAME GateError
            # run() would -- which is fine, since callers wrap the whole
            # `run(_repo(...))` expression in `pytest.raises`.
            physics = parse_ato_physics(ato_path)
            floor = derive_zvs_floor(physics)
            pll_min_hz = float(fw.get("min_hz", 42000))
            threshold = coil_acceptance_l_loaded_min_h(floor, pll_min_hz) * 1e6
        _tank_coil_spec(tmp_path, threshold_uh=threshold)

    return tmp_path


# ---------------------------------------------------------------------------
# TestParsing
# ---------------------------------------------------------------------------


class TestParsing:
    def test_parses_all_three_firmware_constants(self, tmp_path: Path) -> None:
        header = _firmware_header(tmp_path)
        found = parse_firmware_header(header)
        assert set(found) == {"PLL_MIN_FREQ_HZ", "PLL_MAX_FREQ_HZ", "PLL_DEFAULT_FREQ_HZ"}
        assert found["PLL_MIN_FREQ_HZ"].value_hz == 42000.0
        assert found["PLL_MAX_FREQ_HZ"].value_hz == 50000.0
        assert found["PLL_DEFAULT_FREQ_HZ"].value_hz == 47000.0

    def test_firmware_decoy_define_not_picked_up(self, tmp_path: Path) -> None:
        header = _firmware_header(tmp_path)
        found = parse_firmware_header(header)
        assert "FREQ_HYSTERESIS_HZ" not in found

    def test_missing_firmware_header_raises(self, tmp_path: Path) -> None:
        with pytest.raises(GateError):
            parse_firmware_header(tmp_path / "does_not_exist.h")

    def test_parses_all_three_ato_declarations(self, tmp_path: Path) -> None:
        ato = _main_ato(tmp_path)
        found = parse_main_ato(ato)
        assert set(found) == {"f_switching", "f_pll_tracking_min", "f_pll_tracking_max"}
        assert found["f_switching"].value_hz == 47000.0
        assert found["f_pll_tracking_min"].value_hz == 42000.0
        assert found["f_pll_tracking_max"].value_hz == 50000.0

    def test_ato_decoy_declaration_not_picked_up(self, tmp_path: Path) -> None:
        ato = _main_ato(tmp_path)
        found = parse_main_ato(ato)
        assert "f_line" not in found

    def test_parses_all_five_physics_quantities(self, tmp_path: Path) -> None:
        found = parse_ato_physics(_main_ato(tmp_path))
        assert set(found) == {
            "l_tank_assumed",
            "c_tank_total",
            "l_pan_loaded_ratio",
            "l_tank_tolerance",
            "c_tank_tolerance",
        }
        assert found["l_tank_assumed"].value == pytest.approx(88e-6)
        assert found["c_tank_total"].value == pytest.approx(300e-9)
        assert found["l_pan_loaded_ratio"].value == pytest.approx(0.68)
        assert found["l_tank_tolerance"].value == pytest.approx(0.10)
        assert found["c_tank_tolerance"].value == pytest.approx(0.0)

    def test_physics_units_normalize_to_si(self, tmp_path: Path) -> None:
        found = parse_ato_physics(_main_ato(tmp_path, l_tank="0.15mH", c_tank="0.3uF"))
        assert found["l_tank_assumed"].value == pytest.approx(150e-6)
        assert found["c_tank_total"].value == pytest.approx(300e-9)

    def test_physics_decoys_not_picked_up(self, tmp_path: Path) -> None:
        """A similarly-named declaration (`l_tank_assumed_old`) and a
        same-shaped declaration of another kind (`v_bus_nominal: voltage`)
        must not be consumed as derived-floor inputs."""
        found = parse_ato_physics(_main_ato(tmp_path))
        assert "l_tank_assumed_old" not in found
        assert "v_bus_nominal" not in found
        assert found["l_tank_assumed"].value == pytest.approx(88e-6)

    def test_physics_quantity_with_wrong_type_keyword_is_not_found(
        self, tmp_path: Path
    ) -> None:
        """A retyped (not just renamed) quantity is a MISS, so the caller
        fails closed, rather than being read under the wrong unit table."""
        ato = _write(
            tmp_path / "elec" / "src" / "main.ato",
            """\
            module Top:
                l_tank_assumed: frequency = 150kHz
                c_tank_total: capacitance = 300nF
                l_pan_loaded_ratio: dimensionless = 0.399
                l_tank_tolerance: dimensionless = 0.10
            """,
        )
        assert "l_tank_assumed" not in parse_ato_physics(ato)

    def test_parses_both_modules_tank_capacitors(self, tmp_path: Path) -> None:
        found = parse_modules_tank_capacitors(_modules_ato(tmp_path))
        assert set(found) == {"c_tank1", "c_tank2"}
        assert found["c_tank1"].value == pytest.approx(150e-9)
        assert "c_bypass" not in found

    def test_missing_modules_ato_raises(self, tmp_path: Path) -> None:
        with pytest.raises(GateError):
            parse_modules_tank_capacitors(tmp_path / "does_not_exist.ato")

    def test_unit_conversion_hz_and_mhz(self, tmp_path: Path) -> None:
        ato = _write(
            tmp_path / "elec" / "src" / "main.ato",
            """\
            module Top:
                f_switching: frequency = 47000Hz
                f_pll_tracking_min: frequency = 0.03MHz
                f_pll_tracking_max: frequency = 50kHz
            """,
        )
        found = parse_main_ato(ato)
        assert found["f_switching"].value_hz == 47000.0
        assert found["f_pll_tracking_min"].value_hz == 30000.0
        assert found["f_pll_tracking_max"].value_hz == 50000.0

    def test_missing_main_ato_raises(self, tmp_path: Path) -> None:
        with pytest.raises(GateError):
            parse_main_ato(tmp_path / "does_not_exist.ato")


# ---------------------------------------------------------------------------
# TestChecks
# ---------------------------------------------------------------------------


class TestChecks:
    def _agreeing_sets(self, tmp_path: Path):
        firmware = parse_firmware_header(_firmware_header(tmp_path))
        ato = parse_main_ato(_main_ato(tmp_path))
        return firmware, ato

    def test_all_pass_when_everything_agrees(self, tmp_path: Path) -> None:
        firmware, ato = self._agreeing_sets(tmp_path)
        results = run_checks(firmware, ato)
        assert len(results) == 4
        assert all(r.passed for r in results)

    def test_tracking_min_mismatch_fails_only_that_check(self, tmp_path: Path) -> None:
        firmware = parse_firmware_header(_firmware_header(tmp_path))
        ato = parse_main_ato(_main_ato(tmp_path, tracking_min="20kHz"))
        results = {r.name: r.passed for r in run_checks(firmware, ato)}
        assert results["declared tracking min matches firmware PLL_MIN_FREQ_HZ"] is False
        assert results["declared tracking max matches firmware PLL_MAX_FREQ_HZ"] is True

    def test_tracking_max_mismatch_is_the_5x_overstatement_shape(self, tmp_path: Path) -> None:
        """Direct reconstruction of the actual 2026-07-28 defect: main.ato's
        upper bound overstating the firmware's real ceiling by 5x."""
        firmware = parse_firmware_header(_firmware_header(tmp_path, max_hz=50000))
        ato = parse_main_ato(_main_ato(tmp_path, tracking_max="100kHz"))
        results = {r.name: r.passed for r in run_checks(firmware, ato)}
        assert results["declared tracking max matches firmware PLL_MAX_FREQ_HZ"] is False

    def test_switching_outside_firmware_range_fails(self, tmp_path: Path) -> None:
        firmware = parse_firmware_header(_firmware_header(tmp_path, min_hz=30000, max_hz=50000))
        ato = parse_main_ato(_main_ato(tmp_path, switching="83kHz"))
        results = {r.name: r.passed for r in run_checks(firmware, ato)}
        assert results["f_switching within firmware's achievable range"] is False

    def test_switching_at_exact_boundary_passes(self, tmp_path: Path) -> None:
        """Boundary check: exactly at PLL_MAX_FREQ_HZ must be inside, not
        outside, the achievable range (inclusive bounds)."""
        firmware = parse_firmware_header(_firmware_header(tmp_path, max_hz=50000))
        ato = parse_main_ato(_main_ato(tmp_path, switching="50kHz"))
        results = {r.name: r.passed for r in run_checks(firmware, ato)}
        assert results["f_switching within firmware's achievable range"] is True

    def test_default_freq_mismatch_fails(self, tmp_path: Path) -> None:
        firmware = parse_firmware_header(_firmware_header(tmp_path, default_hz=35000))
        ato = parse_main_ato(_main_ato(tmp_path, switching="47kHz"))
        results = {r.name: r.passed for r in run_checks(firmware, ato)}
        assert results["PLL_DEFAULT_FREQ_HZ matches f_switching"] is False


# ---------------------------------------------------------------------------
# TestDerivedZvsFloor -- the 2026-07-29 addition
# ---------------------------------------------------------------------------


class TestDerivedZvsFloor:
    """The floor is DERIVED, not compared.

    Checks 1-4 compare declarations against each other, so they are blind
    to both files agreeing on a wrong number -- which is exactly what
    happened: 30kHz on both sides, 7.6kHz below the tank's loaded
    resonance, hence a hard-switching regime declared legal. These tests
    pin the derivation, its worst-case-L keying, and its fail-closed
    behaviour.
    """

    def test_derives_the_committed_floor(self, tmp_path: Path) -> None:
        floor = derive_zvs_floor(parse_ato_physics(_main_ato(tmp_path)))
        assert floor.l_loaded_worst_case_h == pytest.approx(53.856e-6)
        assert floor.f_res_worst_case_hz == pytest.approx(39595.0, rel=1e-4)
        assert floor.f_res_nominal_hz == pytest.approx(37563.0, rel=1e-4)
        assert floor.required_floor_hz == pytest.approx(EXPECTED_FLOOR_HZ, rel=1e-4)

    def test_floor_keys_off_worst_case_not_nominal_L(self, tmp_path: Path) -> None:
        """f_res ~ 1/sqrt(L), so the minimum-L unit resonates highest and
        needs the highest floor. A guard derived at nominal L would be
        ~5% too low -- and 5% is the entire ZVS margin."""
        floor = derive_zvs_floor(parse_ato_physics(_main_ato(tmp_path)))
        assert floor.f_res_worst_case_hz > floor.f_res_nominal_hz
        assert floor.required_floor_hz > ZVS_MARGIN_MIN * floor.f_res_nominal_hz
        # Deriving at nominal would have blessed a floor this far too low:
        assert ZVS_MARGIN_MIN * floor.f_res_nominal_hz < 40000.0

    def test_committed_min_freq_passes_the_floor_check(self, tmp_path: Path) -> None:
        report = run(_repo(tmp_path, min_hz=42000, tracking_min="42kHz"))
        by_name = {c.name: c.passed for c in report.checks}
        assert by_name["PLL_MIN_FREQ_HZ above the derived ZVS floor"] is True
        assert all(c.passed for c in report.checks)

    def test_too_low_floor_is_a_violation_not_a_pass(self, tmp_path: Path) -> None:
        """The defect itself: 30kHz declared consistently on BOTH sides.
        Checks 1-4 are satisfied; check 5 must fail."""
        report = run(_repo(tmp_path, min_hz=30000, tracking_min="30kHz"))
        by_name = {c.name: c.passed for c in report.checks}
        assert by_name["PLL_MIN_FREQ_HZ above the derived ZVS floor"] is False
        assert by_name["declared tracking min matches firmware PLL_MIN_FREQ_HZ"] is True

    def test_floor_boundary_is_inclusive(self, tmp_path: Path) -> None:
        """Exactly at the derived floor passes; one hertz below fails.
        Pins the comparison direction, not just its rough behaviour."""
        physics = parse_ato_physics(_main_ato(tmp_path))
        required = derive_zvs_floor(physics).required_floor_hz
        at = int(required) + 1
        below = int(required) - 1
        for value, expected in ((at, True), (below, False)):
            report = run(_repo(tmp_path, min_hz=value, tracking_min=f"{value}Hz"))
            by_name = {c.name: c.passed for c in report.checks}
            assert by_name["PLL_MIN_FREQ_HZ above the derived ZVS floor"] is expected

    def test_floor_tracks_declared_physics_rather_than_a_constant(
        self, tmp_path: Path
    ) -> None:
        """Halving C raises f_res by sqrt(2), so a 42kHz floor that passes
        at 300nF must FAIL at 150nF. This is what "derived, not hand-set"
        buys: the guard follows the tank."""
        report = run(
            _repo(
                tmp_path,
                min_hz=42000,
                tracking_min="42kHz",
                c_tank="150nF",
                c_tank1="75nF",
                c_tank2="75nF",
            )
        )
        by_name = {c.name: c.passed for c in report.checks}
        assert by_name["PLL_MIN_FREQ_HZ above the derived ZVS floor"] is False

    @pytest.mark.parametrize(
        "omitted",
        ["l_tank", "c_tank", "loaded_ratio", "tolerance", "c_tank_tolerance"],
    )
    def test_missing_physics_input_fails_closed(self, tmp_path: Path, omitted: str) -> None:
        """Each derived-floor input, omitted one at a time, must produce a
        GATE ERROR. Not a skipped check 5, not a fallback floor -- the
        whole point is that an unevaluatable guard is a failure."""
        with pytest.raises(GateError, match="cannot derive the ZVS floor"):
            run(_repo(tmp_path, **{omitted: None}))

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"l_tank": "0uH"},
            {"c_tank": "0nF"},
            {"loaded_ratio": "0.0"},
            {"loaded_ratio": "1.5"},
            {"tolerance": "1.0"},
            {"c_tank_tolerance": "1.0"},
        ],
    )
    def test_out_of_band_physics_input_fails_closed(self, tmp_path: Path, kwargs) -> None:
        """A nonsensical input must be a GATE ERROR, never a softer floor.
        ``l_pan_loaded_ratio = 0`` or ``l_tank_tolerance = 1.0`` (or now
        ``c_tank_tolerance = 1.0``) would otherwise drive the derived floor
        toward infinity or the division toward zero -- both silently."""
        with pytest.raises(GateError, match="sanity band"):
            run(_repo(tmp_path, **kwargs))

    def test_zero_tolerance_is_allowed_but_derives_the_nominal_floor(
        self, tmp_path: Path
    ) -> None:
        """0 tolerance is a legitimate (if optimistic) declaration -- a
        measured, binned coil -- so it is in band. Recorded explicitly so
        that "tolerance can be set to 0" is a visible, deliberate property
        rather than an accidental hole."""
        floor = derive_zvs_floor(parse_ato_physics(_main_ato(tmp_path, tolerance="0.0")))
        assert floor.f_res_worst_case_hz == pytest.approx(floor.f_res_nominal_hz)

    def test_unparseable_physics_input_fails_closed(self, tmp_path: Path) -> None:
        """Right name, right type keyword, value the regex cannot read --
        a miss, therefore a gate error, therefore never a silent pass."""
        with pytest.raises(GateError, match="cannot derive the ZVS floor"):
            run(_repo(tmp_path, l_tank="TBD"))

    def test_ctank_mirror_mismatch_is_a_violation(self, tmp_path: Path) -> None:
        """main.ato's c_tank_total is a mirror of two real parts. If it
        drifts, the derived floor is computed from a capacitance the board
        does not have -- caught as a violation, not trusted."""
        report = run(_repo(tmp_path, c_tank="470nF"))
        by_name = {c.name: c.passed for c in report.checks}
        assert by_name["main.ato c_tank_total mirrors modules.ato's parallel tank caps"] is False

    def test_missing_modules_capacitor_fails_closed(self, tmp_path: Path) -> None:
        with pytest.raises(GateError, match="missing tank capacitor"):
            run(_repo(tmp_path, c_tank2=None))

    def test_missing_modules_ato_is_gate_error(self, tmp_path: Path) -> None:
        _firmware_header(tmp_path)
        _main_ato(tmp_path)
        with pytest.raises(GateError, match="modules.ato not found"):
            run(tmp_path)

    def test_coil_mirror_mismatch_is_a_violation(self, tmp_path: Path) -> None:
        """Check 7. main.ato's l_tank_assumed and modules.ato's
        inductor_conn.value are two declarations of one coil. Before
        2026-07-29 the coil was a valueless `new Resistor` and there was
        nothing to compare; now a drift between them is a violation."""
        report = run(_repo(tmp_path, coil="150uH +/- 10%"))
        by_name = {c.name: c.passed for c in report.checks}
        assert by_name["main.ato l_tank_assumed mirrors modules.ato's tank coil"] is False
        # ...and ONLY that check -- the floor is derived from main.ato, so
        # a modules.ato-side drift must not be mistaken for a floor problem.
        assert by_name["PLL_MIN_FREQ_HZ above the derived ZVS floor"] is True

    def test_coil_mirror_ignores_the_declared_tolerance(self, tmp_path: Path) -> None:
        """`88uH +/- 10%` and a bare `88uH` are the same nominal value.
        The tolerance the floor derives against is main.ato's own
        l_tank_tolerance, not this suffix."""
        report = run(_repo(tmp_path, coil="88uH"))
        by_name = {c.name: c.passed for c in report.checks}
        assert by_name["main.ato l_tank_assumed mirrors modules.ato's tank coil"] is True

    def test_missing_modules_coil_fails_closed(self, tmp_path: Path) -> None:
        """The pre-2026-07-29 state -- a coil with no inductance in
        elec/src at all -- is now a GATE ERROR, not a skipped check."""
        with pytest.raises(GateError, match="no `inductor_conn.value"):
            run(_repo(tmp_path, coil=None))

    def test_coil_parser_ignores_other_inductors(self, tmp_path: Path) -> None:
        """The fixture carries an unrelated 999uH `l_filter` inductor. The
        parser is keyed on the name, not on "any inductance in the file"."""
        found = parse_modules_tank_coil(_modules_ato(tmp_path))
        assert found is not None
        assert found.name == "inductor_conn"
        assert found.value == pytest.approx(88e-6)

    def test_coil_parser_returns_none_when_absent(self, tmp_path: Path) -> None:
        assert parse_modules_tank_coil(_modules_ato(tmp_path, coil=None)) is None


# ---------------------------------------------------------------------------
# TestMatchedPairCancellation
# ---------------------------------------------------------------------------


class TestMatchedPairCancellation:
    """Only the LOADED inductance resonates, so l_tank_assumed and
    l_pan_loaded_ratio are a matched pair (docs/solutions/design-patterns/
    resonant-tank-only-loaded-inductance-resonates-2026-07-28.md).

    These tests pin what the gate can and cannot see about that pairing.
    The asymmetry is deliberate and is documented in the gate's docstring;
    it is pinned here so it stays a known property rather than becoming a
    surprise.
    """

    def test_the_two_declared_pairs_derive_the_same_floor(self, tmp_path: Path) -> None:
        """150uH x 0.399 (declared until 2026-07-29) and 88uH x 0.68
        (declared now) are 1.7x apart on each factor and agree on the
        product, hence on the floor, to better than 0.01%."""
        old = derive_zvs_floor(
            parse_ato_physics(_main_ato(tmp_path, l_tank="150uH", loaded_ratio="0.399"))
        )
        new = derive_zvs_floor(parse_ato_physics(_main_ato(tmp_path)))
        assert old.required_floor_hz == pytest.approx(41571.0, rel=1e-4)
        assert new.required_floor_hz == pytest.approx(41575.0, rel=1e-4)
        assert new.required_floor_hz == pytest.approx(old.required_floor_hz, rel=1e-4)

    def test_changing_L_alone_fails_the_floor_check(self, tmp_path: Path) -> None:
        """The hazardous half-fix: a smaller coil with the old, too-strong
        coupling ratio puts the worst-case loaded resonance at ~51.7kHz,
        so the derived floor (~54.3kHz) rises above PLL_MIN_FREQ_HZ and
        check 5 fails. The gate DOES see this direction."""
        report = run(
            _repo(
                tmp_path,
                min_hz=42000,
                tracking_min="42kHz",
                l_tank="88uH",
                loaded_ratio="0.399",
            )
        )
        by_name = {c.name: c.passed for c in report.checks}
        assert by_name["PLL_MIN_FREQ_HZ above the derived ZVS floor"] is False

    def test_changing_the_ratio_alone_is_NOT_caught(self, tmp_path: Path) -> None:
        """The other half-fix, recorded as a known blind spot rather than
        claimed as coverage: keeping 150uH while adopting the in-band 0.68
        ratio drops the loaded resonance to ~28.8kHz and the floor to
        ~31.8kHz, which is BELOW PLL_MIN_FREQ_HZ, so every check passes.
        The design would be wrong -- f_sw at ratio 1.63, well off the
        1800W point -- in a way that is a power defect, not a
        hard-switching one. No gate adjudicates the pairing; the solutions
        doc is the control."""
        report = run(
            _repo(
                tmp_path,
                min_hz=42000,
                tracking_min="42kHz",
                l_tank="150uH",
                loaded_ratio="0.68",
                coil="150uH +/- 10%",
            )
        )
        assert all(c.passed for c in report.checks)
        floor = report.floor
        assert floor is not None
        assert floor.f_res_nominal_hz == pytest.approx(28771.0, rel=1e-3)


# ---------------------------------------------------------------------------
# TestCapacitorToleranceWorstCase -- 2026-07-29 (same-day) addition
# ---------------------------------------------------------------------------


class TestCapacitorToleranceWorstCase:
    """The floor was worst-cased for L but not for C: ``c_tank_total`` was
    read at NOMINAL, so a capacitor at the bottom of its own tolerance band
    raised f_res without the floor moving to cover it. These tests pin the
    corrected arithmetic and, sharpest of all, prove the gate now catches
    the exact regression shape: a PLL_MIN_FREQ_HZ that was sufficient
    under the L-only (nominal-C) derivation but is NOT sufficient once the
    real capacitor tolerance is honored.
    """

    def test_capacitor_tolerance_raises_the_required_floor(self, tmp_path: Path) -> None:
        """Same L, same everything else; only c_tank_tolerance changes from
        0 to 0.05. The floor must move from EXPECTED_FLOOR_HZ to
        EXPECTED_FLOOR_HZ_WORST_C -- not stay put."""
        floor_nominal_c = derive_zvs_floor(
            parse_ato_physics(_main_ato(tmp_path, c_tank_tolerance="0.0"))
        )
        floor_worst_c = derive_zvs_floor(
            parse_ato_physics(_main_ato(tmp_path, c_tank_tolerance="0.05"))
        )
        assert floor_nominal_c.required_floor_hz == pytest.approx(EXPECTED_FLOOR_HZ, rel=1e-4)
        assert floor_worst_c.required_floor_hz == pytest.approx(
            EXPECTED_FLOOR_HZ_WORST_C, rel=1e-4
        )
        assert floor_worst_c.required_floor_hz > floor_nominal_c.required_floor_hz
        assert floor_worst_c.c_worst_case_farads == pytest.approx(285e-9)
        assert floor_worst_c.c_worst_case_farads < floor_worst_c.c_nominal_farads

    def test_zero_capacitor_tolerance_reduces_to_the_old_l_only_floor(
        self, tmp_path: Path
    ) -> None:
        """c_tank_tolerance = 0 must be numerically identical to the
        pre-2026-07-29 (L-only) derivation -- confirms the new term is
        additive/multiplicative, not a hidden behaviour change at the
        boundary."""
        floor = derive_zvs_floor(parse_ato_physics(_main_ato(tmp_path, c_tank_tolerance="0.0")))
        assert floor.required_floor_hz == pytest.approx(EXPECTED_FLOOR_HZ, rel=1e-4)
        assert floor.c_worst_case_farads == pytest.approx(floor.c_nominal_farads)

    def test_regression_to_nominal_c_is_caught_by_the_floor_check(self, tmp_path: Path) -> None:
        """THE regression test the task requires: PLL_MIN_FREQ_HZ=42000
        was sufficient when the gate derived the floor at nominal C
        (41575Hz < 42000Hz). With the real capacitor tolerance (+/-5%)
        honored, the required floor is 42655Hz > 42000Hz, so the SAME
        PLL_MIN_FREQ_HZ must now be a VIOLATION. If a future edit ever
        reverted the gate to ignoring c_tank_tolerance (i.e. always
        deriving at nominal C), this is exactly the case that would start
        passing again -- silently re-opening the defect this PR fixes."""
        report = run(
            _repo(
                tmp_path,
                min_hz=42000,
                tracking_min="42kHz",
                c_tank_tolerance="0.05",
            )
        )
        by_name = {c.name: c.passed for c in report.checks}
        assert by_name["PLL_MIN_FREQ_HZ above the derived ZVS floor"] is False

    def test_the_real_committed_floor_43000_passes_with_capacitor_tolerance(
        self, tmp_path: Path
    ) -> None:
        """The actual fix: raising PLL_MIN_FREQ_HZ to 43000 (smallest round
        kHz above 42655Hz) passes once c_tank_tolerance=0.05 is honored."""
        report = run(
            _repo(
                tmp_path,
                min_hz=43000,
                tracking_min="43kHz",
                c_tank_tolerance="0.05",
            )
        )
        by_name = {c.name: c.passed for c in report.checks}
        assert by_name["PLL_MIN_FREQ_HZ above the derived ZVS floor"] is True
        assert all(c.passed for c in report.checks)

    def test_capacitor_tolerance_alone_does_not_affect_nominal_resonance(
        self, tmp_path: Path
    ) -> None:
        """f_res_nominal_hz is computed at NOMINAL L and NOMINAL C (the
        design's target operating point), so it must be unaffected by
        c_tank_tolerance -- only the WORST-CASE figures move."""
        floor_a = derive_zvs_floor(
            parse_ato_physics(_main_ato(tmp_path, c_tank_tolerance="0.0"))
        )
        floor_b = derive_zvs_floor(
            parse_ato_physics(_main_ato(tmp_path, c_tank_tolerance="0.05"))
        )
        assert floor_a.f_res_nominal_hz == pytest.approx(floor_b.f_res_nominal_hz)


# ---------------------------------------------------------------------------
# TestCoilAcceptanceThresholdMirror -- check 8, 2026-07-29
# ---------------------------------------------------------------------------


class TestCoilAcceptanceThresholdMirror:
    """Check 8: the gate inverts its own derived floor into a minimum
    LOADED coil inductance and fails the build if
    ``docs/hardware/TANK_COIL_SPECIFICATION.md``'s stated acceptance
    threshold disagrees -- the untethered-mirror shape checks 6/7 close for
    the capacitance/inductance declarations, applied to a threshold.
    """

    def test_coil_acceptance_min_matches_hand_derivation(self, tmp_path: Path) -> None:
        """f_res_max_guarded = 43000/1.05 = 40952.4Hz;
        L_loaded_min = 1/((2*pi*40952.4)^2 * 285nF) = 52.995uH."""
        floor = derive_zvs_floor(
            parse_ato_physics(_main_ato(tmp_path, c_tank_tolerance="0.05"))
        )
        l_loaded_min = coil_acceptance_l_loaded_min_h(floor, pll_min_hz=43000.0)
        assert l_loaded_min * 1e6 == pytest.approx(52.995, rel=1e-3)

    def test_coil_acceptance_min_moves_with_pll_min(self, tmp_path: Path) -> None:
        """The property this check exists to guarantee: the threshold is
        NOT a constant -- it moves automatically with PLL_MIN_FREQ_HZ.
        Direction: a HIGHER PLL_MIN_FREQ_HZ guards a higher resonance
        (f_res_max_guarded = PLL_MIN/ZVS_MARGIN_MIN rises), so a coil is
        allowed to resonate higher too, i.e. L_loaded_min is LOWER, not
        higher -- L_loaded_min ~ 1/PLL_MIN^2."""
        floor = derive_zvs_floor(
            parse_ato_physics(_main_ato(tmp_path, c_tank_tolerance="0.05"))
        )
        at_43000 = coil_acceptance_l_loaded_min_h(floor, pll_min_hz=43000.0)
        at_44000 = coil_acceptance_l_loaded_min_h(floor, pll_min_hz=44000.0)
        assert at_44000 < at_43000

    def test_doc_threshold_matching_derivation_passes(self, tmp_path: Path) -> None:
        """_repo()'s default auto-computed doc threshold matches exactly,
        so check 8 passes (this is what every other run()-based test in
        this file implicitly relies on)."""
        report = run(
            _repo(tmp_path, min_hz=43000, tracking_min="43kHz", c_tank_tolerance="0.05")
        )
        by_name = {c.name: c.passed for c in report.checks}
        assert (
            by_name[
                "TANK_COIL_SPECIFICATION.md's L_loaded acceptance threshold "
                "matches the gate-derived value"
            ]
            is True
        )

    def test_doc_threshold_mismatch_is_a_violation(self, tmp_path: Path) -> None:
        """The exact scenario the task named: TANK_COIL_SPECIFICATION.md
        still states the OLD (pre-capacitor-tolerance) value, 52.77uH,
        while the gate now derives 53.00uH. That drift must be caught, not
        silently tolerated."""
        report = run(
            _repo(
                tmp_path,
                min_hz=43000,
                tracking_min="43kHz",
                c_tank_tolerance="0.05",
                doc_threshold_uh=52.77,
            )
        )
        by_name = {c.name: c.passed for c in report.checks}
        assert (
            by_name[
                "TANK_COIL_SPECIFICATION.md's L_loaded acceptance threshold "
                "matches the gate-derived value"
            ]
            is False
        )
        # ...and ONLY that check -- a stale doc number must not be mistaken
        # for a firmware/main.ato disagreement.
        assert by_name["PLL_MIN_FREQ_HZ above the derived ZVS floor"] is True

    def test_doc_threshold_small_rounding_is_tolerated(self, tmp_path: Path) -> None:
        """The doc is allowed to state a sensibly-ROUNDED value (e.g.
        53.00 for an exact 52.9953) without failing -- the check has a
        small allowance for that, not bit-for-bit equality."""
        floor = derive_zvs_floor(
            parse_ato_physics(_main_ato(tmp_path, c_tank_tolerance="0.05"))
        )
        exact_uh = coil_acceptance_l_loaded_min_h(floor, pll_min_hz=43000.0) * 1e6
        assert exact_uh == pytest.approx(52.995, abs=0.01)
        report = run(
            _repo(
                tmp_path,
                min_hz=43000,
                tracking_min="43kHz",
                c_tank_tolerance="0.05",
                doc_threshold_uh=round(exact_uh, 2),
            )
        )
        by_name = {c.name: c.passed for c in report.checks}
        assert (
            by_name[
                "TANK_COIL_SPECIFICATION.md's L_loaded acceptance threshold "
                "matches the gate-derived value"
            ]
            is True
        )

    def test_missing_doc_anchor_sentence_is_gate_error(self, tmp_path: Path) -> None:
        """The document existing but lacking the one sentence check 8
        parses must fail closed -- never silently skip check 8."""
        _firmware_header(tmp_path, min_hz=43000)
        _main_ato(tmp_path, tracking_min="43kHz", c_tank_tolerance="0.05")
        _modules_ato(tmp_path)
        _tank_coil_spec(tmp_path, threshold_uh=None, include_anchor=False)
        with pytest.raises(GateError, match="requirement #3"):
            run(tmp_path)

    def test_missing_doc_file_is_gate_error(self, tmp_path: Path) -> None:
        """The document missing entirely (never written) must fail closed,
        same as any other of this gate's four required source files."""
        _firmware_header(tmp_path, min_hz=43000)
        _main_ato(tmp_path, tracking_min="43kHz", c_tank_tolerance="0.05")
        _modules_ato(tmp_path)
        with pytest.raises(GateError, match="TANK_COIL_SPECIFICATION"):
            run(tmp_path)

    def test_parse_tank_coil_spec_threshold_ignores_unrelated_numbers(
        self, tmp_path: Path
    ) -> None:
        """The fixture's own decoy (an unrelated '999 uH' near 'L_loaded')
        must not be picked up -- only the anchored sentence counts."""
        path = _tank_coil_spec(tmp_path, threshold_uh=53.0)
        found = parse_tank_coil_spec_threshold(path)
        assert found is not None
        assert found.value == pytest.approx(53.0e-6)


# ---------------------------------------------------------------------------
# TestAntiVacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_missing_firmware_header_is_gate_error(self, tmp_path: Path) -> None:
        _main_ato(tmp_path)
        _modules_ato(tmp_path)
        with pytest.raises(GateError):
            run(tmp_path)

    def test_missing_main_ato_is_gate_error(self, tmp_path: Path) -> None:
        _firmware_header(tmp_path)
        _modules_ato(tmp_path)
        with pytest.raises(GateError):
            run(tmp_path)

    def test_missing_tracking_range_declarations_is_gate_error(self, tmp_path: Path) -> None:
        """The historical shape: main.ato declares f_switching but never
        declared f_pll_tracking_min/max at all -- must fail closed, not
        silently skip the two comparisons that need them."""
        repo = _repo(tmp_path, tracking_min=None, tracking_max=None)
        with pytest.raises(GateError, match="missing"):
            run(repo)

    def test_missing_one_firmware_constant_is_gate_error(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "firmware" / "components" / "control" / "pll_control.h",
            """\
            #define PLL_MIN_FREQ_HZ 42000
            #define PLL_MAX_FREQ_HZ 50000
            /* PLL_DEFAULT_FREQ_HZ intentionally absent */
            """,
        )
        _main_ato(tmp_path)
        _modules_ato(tmp_path)
        with pytest.raises(GateError, match="missing"):
            run(tmp_path)

    def test_run_all_agree_passes_with_full_denominators(self, tmp_path: Path) -> None:
        report = run(_repo(tmp_path))
        assert len(report.firmware_constants) == 3
        assert len(report.ato_constants) == 3
        assert len(report.ato_physics) == 5
        assert len(report.modules_caps) == 2
        assert report.modules_coil is not None
        assert report.doc_threshold is not None
        assert len(report.checks) == 8
        assert all(c.passed for c in report.checks)


# ---------------------------------------------------------------------------
# TestHistoricalRegression -- fail-before/pass-after for the gate itself
# ---------------------------------------------------------------------------


class TestHistoricalRegression:
    """The gate is new, so there is no prior git revision of the *gate* to
    diff against. Instead this reconstructs the actual historical defect
    shapes documented in docs/evidence/2026-07-28-pll-ratio-tracking-
    check.md as controlled fixtures and proves the gate would have caught
    each one (fails), then proves the real fix (mirrored here) passes.
    """

    def test_before_default_freq_mismatch_35000_vs_47000_is_violation_end_to_end(
        self, tmp_path: Path
    ) -> None:
        """Reconstructs the pre-fix firmware state (PLL_DEFAULT_FREQ_HZ=
        35000 -- the condemned frequency, 100.7% ZVS margin lost per
        docs/evidence/2026-07-27-zvs-operating-point.md) against an
        otherwise-fixed main.ato (f_switching=47kHz, tracking range
        declared and agreeing with firmware min/max) -- isolating check 4
        end-to-end through run(), not just the pure run_checks() function."""
        report = run(_repo(tmp_path, default_hz=35000, switching="47kHz"))
        failed = {c.name for c in report.checks if not c.passed}
        assert "PLL_DEFAULT_FREQ_HZ matches f_switching" in failed

    def test_before_default_freq_mismatch_with_tracking_range_present_is_violation(
        self, tmp_path: Path
    ) -> None:
        """Same defect, but isolating check 4 specifically: with the
        tracking-range declarations present and agreeing, PLL_DEFAULT_FREQ_HZ
        still disagreeing with f_switching must be a VIOLATION, not a pass."""
        firmware = parse_firmware_header(_firmware_header(tmp_path, default_hz=35000))
        ato = parse_main_ato(_main_ato(tmp_path, switching="47kHz"))
        results = run_checks(firmware, ato)
        assert any(not r.passed for r in results)

    def test_before_overstated_tracking_range_is_gate_error(self, tmp_path: Path) -> None:
        """Reconstructs the exact pre-fix main.ato comment defect: no
        f_pll_tracking_min/max declared at all, only the 20-100kHz LC-tank
        assertion -- must fail closed rather than silently pass because
        "nothing to compare" was never a legitimate state."""
        _repo(tmp_path, tracking_min=None, tracking_max=None)
        with pytest.raises(GateError):
            run(tmp_path)

    def test_the_2026_07_28_fix_itself_fails_the_derived_floor(self, tmp_path: Path) -> None:
        """FAIL-BEFORE for the 2026-07-29 change, and the sharpest
        statement of why cross-checking alone was not enough.

        The 2026-07-28 fix made both files agree on 30-50kHz. Under checks
        1-4 that is a clean pass -- and it was wrong: 30kHz is 7.6kHz below
        the tank's loaded resonance, i.e. the firmware declared a
        hard-switching regime legal on a 1200V IGBT half-bridge at 1800W.
        Consistency between two declarations says nothing about whether
        either is physical. Only the derived check catches it."""
        report = run(
            _repo(
                tmp_path,
                min_hz=30000,
                max_hz=50000,
                default_hz=47000,
                switching="47kHz",
                tracking_min="30kHz",
                tracking_max="50kHz",
            )
        )
        by_name = {c.name: c.passed for c in report.checks}
        assert by_name["declared tracking min matches firmware PLL_MIN_FREQ_HZ"] is True
        assert by_name["declared tracking max matches firmware PLL_MAX_FREQ_HZ"] is True
        assert by_name["f_switching within firmware's achievable range"] is True
        assert by_name["PLL_DEFAULT_FREQ_HZ matches f_switching"] is True
        assert by_name["PLL_MIN_FREQ_HZ above the derived ZVS floor"] is False

    def test_after_fix_shape_passes(self, tmp_path: Path) -> None:
        """PASS-AFTER: the real, as-committed 2026-07-29 state --
        PLL_DEFAULT_FREQ_HZ=47000, f_switching=47kHz, and main.ato
        declaring f_pll_tracking_min/max equal to the firmware's real
        PLL_MIN/MAX_FREQ_HZ (42/50kHz), with the floor now above the
        derived worst-case resonance."""
        report = run(
            _repo(
                tmp_path,
                min_hz=42000,
                max_hz=50000,
                default_hz=47000,
                switching="47kHz",
                tracking_min="42kHz",
                tracking_max="50kHz",
            )
        )
        assert all(c.passed for c in report.checks)

    def test_widening_firmware_to_match_unvalidated_range_would_still_be_caught(
        self, tmp_path: Path
    ) -> None:
        """Falsifier check (task Part 4): if someone tried to resolve
        disagreement by raising PLL_MAX_FREQ_HZ toward the ratio-tracking
        mitigation's 83kHz requirement instead of declaring the firmware's
        real capability, THIS gate alone would pass (it only checks
        firmware-vs-main.ato agreement, by design -- see module docstring
        "Checks performed" item 3's note on scope). This test exists to
        make that scope boundary explicit and not silently assumed: the
        prohibition on widening PLL_MAX_FREQ_HZ is a hardware-validation
        concern this gate does not and cannot enforce from source text
        alone, recorded instead as a human-facing OPEN QUESTION at the
        main.ato declaration site and in the evidence doc.

        NOTE (2026-07-29): the FLOOR is no longer in that category -- it is
        now derived, so lowering PLL_MIN_FREQ_HZ below resonance is caught
        (see TestDerivedZvsFloor). Only the CEILING remains a
        text-indistinguishable hardware judgement, and this test is
        narrowed to it accordingly.
        """
        _repo(
            tmp_path,
            min_hz=42000,
            max_hz=83000,
            default_hz=47000,
            switching="47kHz",
            tracking_min="42kHz",
            tracking_max="83kHz",
        )
        report = run(tmp_path)
        assert all(c.passed for c in report.checks), (
            "this gate correctly cannot distinguish a truthful capability "
            "declaration from an unvalidated widening of the CEILING by source "
            "text alone -- that is a hardware decision, not a text-consistency "
            "check. The floor, by contrast, is now derived and is enforced."
        )


# ---------------------------------------------------------------------------
# Exit-code smoke test against the real repo files
# ---------------------------------------------------------------------------


def test_exit_codes_are_distinct() -> None:
    assert EXIT_OK == 0
    assert EXIT_VIOLATION == 3
    assert EXIT_GATE_ERROR == 5
