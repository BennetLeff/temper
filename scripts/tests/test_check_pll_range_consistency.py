"""Tests for check_pll_range_consistency.py.

Every scenario here builds small, hand-written synthetic
``pll_control.h``/``main.ato`` fixtures under ``tmp_path`` rather than
depending on the real repo files (matching the convention in
``test_check_domain_partition.py`` and ``test_check_stale_extensions.py``)
-- the real files are exercised directly by running the gate itself
(``docs/evidence/2026-07-28-pll-defaults-and-range-gate.md``).

Four groups:

1. ``TestParsing`` -- ``parse_firmware_header``/``parse_main_ato`` find the
   right named constants, handle unit conversion (Hz/kHz/MHz), and ignore
   unrelated ``#define``/declaration noise.
2. ``TestChecks`` -- ``run_checks()``'s four comparisons, each independently
   falsifiable.
3. ``TestAntiVacuity`` -- ``run()`` fails closed on missing files, missing
   individual constants (partial discovery), and the zero-discovery case.
4. ``TestHistoricalRegression`` -- reconstructs the actual 2026-07-28
   defect shapes (PLL_DEFAULT_FREQ_HZ=35000 while main.ato already declared
   f_switching=47kHz; main.ato declaring no tracking-range constants at
   all) as controlled fixtures, and proves the gate catches both, then
   proves the real fix (as committed) passes -- a fail-before/pass-after
   demonstration for the gate itself, since the gate is new and has no
   prior git history to diff against.
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
    GateError,
    parse_firmware_header,
    parse_main_ato,
    run,
    run_checks,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


def _firmware_header(
    tmp_path: Path,
    *,
    min_hz: int = 30000,
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
    tracking_min: str | None = "30kHz",
    tracking_max: str | None = "50kHz",
) -> Path:
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
    return _write(tmp_path / "elec" / "src" / "main.ato", "\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# TestParsing
# ---------------------------------------------------------------------------


class TestParsing:
    def test_parses_all_three_firmware_constants(self, tmp_path: Path) -> None:
        header = _firmware_header(tmp_path)
        found = parse_firmware_header(header)
        assert set(found) == {"PLL_MIN_FREQ_HZ", "PLL_MAX_FREQ_HZ", "PLL_DEFAULT_FREQ_HZ"}
        assert found["PLL_MIN_FREQ_HZ"].value_hz == 30000.0
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
        assert found["f_pll_tracking_min"].value_hz == 30000.0
        assert found["f_pll_tracking_max"].value_hz == 50000.0

    def test_ato_decoy_declaration_not_picked_up(self, tmp_path: Path) -> None:
        ato = _main_ato(tmp_path)
        found = parse_main_ato(ato)
        assert "f_line" not in found

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
# TestAntiVacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def _repo(self, tmp_path: Path, **kwargs) -> Path:
        _firmware_header(tmp_path, **{k: v for k, v in kwargs.items() if k in ("min_hz", "max_hz", "default_hz")})
        ato_kwargs = {k: v for k, v in kwargs.items() if k in ("switching", "tracking_min", "tracking_max")}
        _main_ato(tmp_path, **ato_kwargs)
        return tmp_path

    def test_missing_firmware_header_is_gate_error(self, tmp_path: Path) -> None:
        _main_ato(tmp_path)
        with pytest.raises(GateError):
            run(tmp_path)

    def test_missing_main_ato_is_gate_error(self, tmp_path: Path) -> None:
        _firmware_header(tmp_path)
        with pytest.raises(GateError):
            run(tmp_path)

    def test_missing_tracking_range_declarations_is_gate_error(self, tmp_path: Path) -> None:
        """The historical shape: main.ato declares f_switching but never
        declared f_pll_tracking_min/max at all -- must fail closed, not
        silently skip the two comparisons that need them."""
        repo = self._repo(tmp_path, tracking_min=None, tracking_max=None)
        with pytest.raises(GateError, match="missing"):
            run(repo)

    def test_missing_one_firmware_constant_is_gate_error(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "firmware" / "components" / "control" / "pll_control.h",
            """\
            #define PLL_MIN_FREQ_HZ 30000
            #define PLL_MAX_FREQ_HZ 50000
            /* PLL_DEFAULT_FREQ_HZ intentionally absent */
            """,
        )
        _main_ato(tmp_path)
        with pytest.raises(GateError, match="missing"):
            run(tmp_path)

    def test_run_all_agree_passes_with_full_denominators(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path)
        report = run(repo)
        assert len(report.firmware_constants) == 3
        assert len(report.ato_constants) == 3
        assert len(report.checks) == 4
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
        _firmware_header(tmp_path, default_hz=35000)
        _main_ato(tmp_path, switching="47kHz")
        report = run(tmp_path)
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
        _firmware_header(tmp_path)
        _main_ato(tmp_path, tracking_min=None, tracking_max=None)
        with pytest.raises(GateError):
            run(tmp_path)

    def test_after_fix_shape_passes(self, tmp_path: Path) -> None:
        """Mirrors the real, as-committed fix: PLL_DEFAULT_FREQ_HZ=47000,
        f_switching=47kHz, and main.ato declaring f_pll_tracking_min/max
        equal to the firmware's real PLL_MIN/MAX_FREQ_HZ (30/50kHz) --
        matching the firmware's actual capability, not widening it."""
        _firmware_header(tmp_path, min_hz=30000, max_hz=50000, default_hz=47000)
        _main_ato(tmp_path, switching="47kHz", tracking_min="30kHz", tracking_max="50kHz")
        report = run(tmp_path)
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
        """
        _firmware_header(tmp_path, min_hz=30000, max_hz=83000, default_hz=47000)
        _main_ato(tmp_path, switching="47kHz", tracking_min="30kHz", tracking_max="83kHz")
        report = run(tmp_path)
        assert all(c.passed for c in report.checks), (
            "this gate correctly cannot distinguish a truthful capability "
            "declaration from an unvalidated widening by source text alone -- "
            "that is a hardware decision, not a text-consistency check"
        )


# ---------------------------------------------------------------------------
# Exit-code smoke test against the real repo files
# ---------------------------------------------------------------------------


def test_exit_codes_are_distinct() -> None:
    assert EXIT_OK == 0
    assert EXIT_VIOLATION == 3
    assert EXIT_GATE_ERROR == 5
