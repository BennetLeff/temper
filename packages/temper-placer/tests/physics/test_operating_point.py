"""
Tests for U6: OperatingPointGate — coupled-load operating-point cross-check.

Test scenarios:
- Benign load range → ceilings feasible across both extremes → CLEAN
- Infeasible load range → VIOLATIONS naming the physical knob
- SPICE unavailable → UNMEASURED (never a silent pass)
- Shared-assumption flag recorded when SPICE and analytic models overlap
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from temper_placer.physics.operating_point import (
    OperatingPointConfig,
    OperatingPointGate,
    SpiceCrossCheckInfo,
    _validate_config,
    compute_extremes,
)
from temper_placer.placer.cp_sat.gates import (
    BoardState,
    GateResult,
    GateStatus,
    ViolationType,
)


# ---------------------------------------------------------------------------
# Stub SPICE validator (deterministic, no ngspice install required)
# ---------------------------------------------------------------------------


@dataclass
class _StubSpiceResult:
    success: bool = True
    measurements: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class StubNgspiceValidator:
    """Deterministic stub that lets tests control SPICE availability and
    measurement output without installing ngspice."""

    def __init__(
        self,
        available: bool = True,
        measurements: dict[str, float] | None = None,
        sim_success: bool = True,
    ):
        self._available = available
        self._measurements = measurements or {}
        self._sim_success = sim_success

    def check_ngspice(self) -> bool:
        return self._available

    def run_template(
        self, template: str, parameters: dict[str, str]
    ) -> _StubSpiceResult:
        if not self._sim_success:
            return _StubSpiceResult(
                success=False,
                errors=["Stub: simulation failed"],
            )
        return _StubSpiceResult(
            success=True,
            measurements={
                k: type("_M", (), {"value": v})()
                for k, v in self._measurements.items()
            },
        )


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------


def _benign_config() -> dict[str, Any]:
    """Parameters that produce a feasible operating point at both extremes."""
    return {
        "V_bus": 325.0,
        "V_BR": 1200.0,
        "I_load_rms": 10.0,
        "L_coil": 100e-6,
        "L_leakage": 10e-6,
        "f_sw": 20000.0,
        "T_amb": 40.0,
        "T_j_max": 150.0,
        "R_theta_jc": 0.6,
        "R_theta_cs": 0.25,
        "R_theta_sa": 1.0,
        "t_rise": 50e-9,
        "t_fall": 50e-9,
        "V_ce_sat": 1.7,
        "derate": 0.80,
    }


def _infeasible_config() -> dict[str, Any]:
    """Parameters where L_loop_max falls below the feasible minimum at
    ideal coupling (k=1) but zero-coupling (k=0) is still feasible."""
    return {
        "V_bus": 500.0,
        "V_BR": 650.0,
        "I_load_rms": 5.0,
        "L_coil": 100e-6,
        "L_leakage": 0.1e-6,  # 100 nH — very tight coupling
        "f_sw": 20000.0,
        "T_amb": 40.0,
        "T_j_max": 150.0,
        "R_theta_jc": 0.5,
        "R_theta_cs": 0.2,
        "R_theta_sa": 1.5,
        "t_rise": 50e-9,
        "t_fall": 50e-9,
        "V_ce_sat": 1.5,
        "derate": 0.80,
    }


# ---------------------------------------------------------------------------
# Tests: config validation
# ---------------------------------------------------------------------------


class TestConfigValidation:
    def test_benign_config_passes(self):
        cfg = _validate_config(_benign_config())
        assert cfg.V_bus == 325.0

    def test_missing_required_key_raises(self):
        bad = dict(_benign_config())
        del bad["V_bus"]
        with pytest.raises(TypeError, match="missing required keys"):
            _validate_config(bad)

    def test_negative_V_bus_raises(self):
        bad = dict(_benign_config())
        bad["V_bus"] = -1
        with pytest.raises(ValueError, match="V_bus must be"):
            _validate_config(bad)

    def test_derate_out_of_range_raises(self):
        bad = dict(_benign_config())
        bad["derate"] = 1.5
        with pytest.raises(ValueError, match="derate must be"):
            _validate_config(bad)


# ---------------------------------------------------------------------------
# Tests: analytic extremes
# ---------------------------------------------------------------------------


class TestComputeExtremes:
    def test_benign_both_extremes_feasible(self):
        cfg = _validate_config(_benign_config())
        k0, k1 = compute_extremes(cfg)
        assert k0.feasible
        assert k1.feasible
        assert k0.di_dt < k1.di_dt  # ideal-coupling slew rate is higher
        assert k0.L_loop_max >= cfg.min_feasible_L_loop
        assert k1.L_loop_max >= cfg.min_feasible_L_loop
        assert k0.T_j <= cfg.T_j_max
        assert k1.T_j <= cfg.T_j_max

    def test_infeasible_ideal_coupling(self):
        cfg = _validate_config(_infeasible_config())
        k0, k1 = compute_extremes(cfg)
        # At k=0 (L_coil=100uH) it should still be feasible
        assert k0.feasible, f"k0 should be feasible, got L_loop_max={k0.L_loop_max:.2e}"
        # At k=1 (L_leakage=100nH, di/dt ~ 5e9 A/s) L_loop_max < 5nH
        assert not k1.feasible, f"k1 should be infeasible, got L_loop_max={k1.L_loop_max:.2e}"
        assert k1.L_loop_max < cfg.min_feasible_L_loop


# ---------------------------------------------------------------------------
# Tests: gate (happy path)
# ---------------------------------------------------------------------------


class TestOperatingPointGateHappy:
    def test_benign_load_range_clean(self):
        """Benign params → CLEAN when SPICE is available and matches."""
        cfg = _benign_config()
        # Provide SPICE measurements that roughly match analytic di/dt at k0
        spice = StubNgspiceValidator(
            available=True,
            measurements={"di_dt_k0": 3.30e6},  # close to 3.25e6
        )
        gate = OperatingPointGate(cfg, spice_validator=spice, tolerance=0.20)
        state = BoardState()
        result = gate.check(state)

        assert result.status == GateStatus.CLEAN
        assert len(result.violations) == 0

    def test_shared_assumptions_recorded(self):
        """Cross-check info records transformer coupling + no-eddy-loss."""
        cfg = _benign_config()
        spice = StubNgspiceValidator(
            available=True,
            measurements={"di_dt_k0": 3.30e6},
        )
        gate = OperatingPointGate(cfg, spice_validator=spice)
        gate.check(BoardState())

        cc = gate.last_cross_check
        assert cc is not None
        assert cc.circularity_risk is True
        assert "transformer_coupling_model" in cc.shared_assumptions
        assert "no_eddy_current_losses" in cc.shared_assumptions


# ---------------------------------------------------------------------------
# Tests: gate (error path → VIOLATIONS)
# ---------------------------------------------------------------------------


class TestOperatingPointGateViolations:
    def test_infeasible_at_ideal_coupling_violations(self):
        """Infeasible → VIOLATIONS with physical knob named in description."""
        cfg = _infeasible_config()
        spice = StubNgspiceValidator(
            available=True,
            measurements={},
        )
        gate = OperatingPointGate(cfg, spice_validator=spice)
        state = BoardState()
        result = gate.check(state)

        assert result.status == GateStatus.VIOLATIONS
        assert len(result.violations) > 0

        # At least one violation should reference the physical knob
        descriptions = " ".join(v.description for v in result.violations)
        assert any(
            kw in descriptions.lower()
            for kw in ("snubber", "slower gate", "part swap", "higher-v_br")
        )

        # The violation should be LOOP_INDUCTANCE type (L_loop ceiling)
        loop_types = [v for v in result.violations if v.type == ViolationType.LOOP_INDUCTANCE]
        assert len(loop_types) > 0

    def test_thermal_violation_named(self):
        """T_j > T_j_max produces a THERMAL violation naming the resistor."""
        cfg = dict(_benign_config())
        cfg["T_j_max"] = 80.0  # below the benign T_j
        cfg["R_theta_jc"] = 5.0  # huge thermal resistance
        spice = StubNgspiceValidator(available=True, measurements={})
        gate = OperatingPointGate(cfg, spice_validator=spice)
        result = gate.check(BoardState())

        assert result.status == GateStatus.VIOLATIONS
        thermal_violations = [
            v for v in result.violations if v.type == ViolationType.THERMAL
        ]
        assert len(thermal_violations) > 0
        thermal_desc = thermal_violations[0].description.lower()
        assert any(kw in thermal_desc for kw in ("r_θ", "heatsink", "heatsink", "f_sw", "part swap"))


# ---------------------------------------------------------------------------
# Tests: gate (edge — UNMEASURED)
# ---------------------------------------------------------------------------


class TestOperatingPointGateUnmeasured:
    def test_spice_unavailable_returns_unmeasured(self):
        """When ngspice is missing, the gate returns UNMEASURED never CLEAN."""
        cfg = _benign_config()
        spice = StubNgspiceValidator(available=False)
        gate = OperatingPointGate(cfg, spice_validator=spice)
        result = gate.check(BoardState())

        assert result.status == GateStatus.UNMEASURED
        assert result.error_message != ""
        assert "ngspice" in result.error_message.lower()

    def test_spice_unavailable_is_not_a_silent_pass(self):
        """UNMEASURED is distinct from CLEAN even when analytic bounds pass."""
        cfg = _benign_config()
        spice = StubNgspiceValidator(available=False)
        gate = OperatingPointGate(cfg, spice_validator=spice)
        result = gate.check(BoardState())

        # Proves the gate does NOT fall through to CLEAN
        assert result.status != GateStatus.CLEAN
        assert result.status == GateStatus.UNMEASURED


# ---------------------------------------------------------------------------
# Tests: SPICE cross-check metadata
# ---------------------------------------------------------------------------


class TestSpiceCrossCheckInfo:
    def test_circularity_risk_when_assumptions_present(self):
        info = SpiceCrossCheckInfo(
            available=True,
            ran=True,
            success=True,
            measurements={"di_dt_k0": 1e6},
            analytic_match=True,
            shared_assumptions=("transformer_coupling_model",),
        )
        assert info.circularity_risk is True

    def test_no_circularity_risk_when_no_assumptions(self):
        info = SpiceCrossCheckInfo(
            shared_assumptions=(),
        )
        assert info.circularity_risk is False
