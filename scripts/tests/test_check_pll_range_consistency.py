"""Tests for check_pll_range_consistency.py.

Every scenario here builds small, hand-written synthetic
``pll_control.h``/``main.ato`` fixtures under ``tmp_path`` rather than
depending on the real repo files (matching the convention in
``test_check_domain_partition.py`` and ``test_check_stale_extensions.py``)
-- the real files are exercised directly by running the gate itself
(``docs/evidence/2026-07-28-pll-defaults-and-range-gate.md``).

Five groups:

1. ``TestParsing`` -- ``parse_firmware_header``/``parse_main_ato``/
   ``parse_ato_physics``/``parse_modules_tank_capacitors`` find the right
   named constants, handle unit conversion (Hz/kHz/MHz, H/uH/nH,
   F/uF/nF/pF), and ignore unrelated ``#define``/declaration noise.
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
    derive_zvs_floor,
    parse_ato_physics,
    parse_firmware_header,
    parse_main_ato,
    parse_modules_tank_capacitors,
    run,
    run_checks,
)

# Derived-floor arithmetic for the as-committed declarations, recomputed
# by hand here rather than imported, so a bug in the gate's own formula
# cannot make these tests agree with it:
#   L_loaded(worst) = 150uH * (1 - 0.10) * 0.399 = 53.865uH
#   f_res           = 1/(2*pi*sqrt(53.865uH * 300nF)) = 39.59kHz
#   required floor  = 1.05 * 39.59kHz = 41.57kHz
EXPECTED_FLOOR_HZ = 41571.0


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
    l_tank: str | None = "150uH",
    c_tank: str | None = "300nF",
    loaded_ratio: str | None = "0.399",
    tolerance: str | None = "0.10",
) -> Path:
    """Synthetic main.ato. Any of the four derived-floor physics quantities
    can be passed ``None`` to omit it, or a raw string to declare a bad
    one -- both must make the gate fail closed, never skip.
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
    return _write(tmp_path / "elec" / "src" / "main.ato", "\n".join(lines) + "\n")


def _modules_ato(
    tmp_path: Path,
    *,
    c_tank1: str | None = "150nF",
    c_tank2: str | None = "150nF",
) -> Path:
    lines = [
        "module ResonantTank:",
        "    c_bypass = new Capacitor",
        "    c_bypass.value = 100nF  # unrelated decoy",
    ]
    for name, value in (("c_tank1", c_tank1), ("c_tank2", c_tank2)):
        if value is not None:
            lines.append(f"    {name} = new Capacitor")
            lines.append(f"    {name}.value = {value}")
    return _write(tmp_path / "elec" / "src" / "modules.ato", "\n".join(lines) + "\n")


def _repo(tmp_path: Path, **kwargs) -> Path:
    """Write all three source files a full ``run()`` needs."""
    fw = {k: v for k, v in kwargs.items() if k in ("min_hz", "max_hz", "default_hz")}
    mods = {k: v for k, v in kwargs.items() if k in ("c_tank1", "c_tank2")}
    ato = {k: v for k, v in kwargs.items() if k not in fw and k not in mods}
    _firmware_header(tmp_path, **fw)
    _main_ato(tmp_path, **ato)
    _modules_ato(tmp_path, **mods)
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

    def test_parses_all_four_physics_quantities(self, tmp_path: Path) -> None:
        found = parse_ato_physics(_main_ato(tmp_path))
        assert set(found) == {
            "l_tank_assumed",
            "c_tank_total",
            "l_pan_loaded_ratio",
            "l_tank_tolerance",
        }
        assert found["l_tank_assumed"].value == pytest.approx(150e-6)
        assert found["c_tank_total"].value == pytest.approx(300e-9)
        assert found["l_pan_loaded_ratio"].value == pytest.approx(0.399)
        assert found["l_tank_tolerance"].value == pytest.approx(0.10)

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
        assert found["l_tank_assumed"].value == pytest.approx(150e-6)

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
        assert floor.l_loaded_worst_case_h == pytest.approx(53.865e-6)
        assert floor.f_res_worst_case_hz == pytest.approx(39592.0, rel=1e-4)
        assert floor.f_res_nominal_hz == pytest.approx(37560.0, rel=1e-4)
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
        ["l_tank", "c_tank", "loaded_ratio", "tolerance"],
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
        ],
    )
    def test_out_of_band_physics_input_fails_closed(self, tmp_path: Path, kwargs) -> None:
        """A nonsensical input must be a GATE ERROR, never a softer floor.
        ``l_pan_loaded_ratio = 0`` or ``l_tank_tolerance = 1.0`` would
        otherwise drive the derived floor toward infinity or the division
        toward zero -- both silently."""
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
        assert len(report.ato_physics) == 4
        assert len(report.modules_caps) == 2
        assert len(report.checks) == 6
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
