"""
Tests for U2: physics-U6 coupling-extreme bounding soundness (R5).

Test scenarios:
- Error (AE6/R5): non-monotone coupling where an interior ceiling breach
  occurs while endpoints are clear -> gate is NOT CLEAN.
- Happy: monotone benign range -> CLEAN via endpoints (interior check
  adds no violations).
- Property (PBT): sampled interior worst-case <= reported worst-case
  across generated L_coil / L_leakage / V_bus profiles.
"""

from __future__ import annotations

import math

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from temper_placer.physics.operating_point import (
    OperatingPointConfig,
    OperatingPointGate,
    _interior_bounding_soundness_check,
    _l_eff,
)
from temper_placer.placer.cp_sat.gates import (
    BoardState,
    GateStatus,
)

# ---------------------------------------------------------------------------
# Stub SPICE validator (same pattern as test_operating_point.py)
# ---------------------------------------------------------------------------


class _StubSpiceResult:
    def __init__(self, success=True, measurements=None, errors=None):
        self.success = success
        self.measurements = measurements or {}
        self.errors = errors or []


class StubNgspiceValidator:
    def __init__(self, available=True, measurements=None, sim_success=True):
        self._available = available
        self._measurements = measurements or {}
        self._sim_success = sim_success

    def check_ngspice(self):
        return self._available

    def run_template(self, template, parameters):
        if not self._sim_success:
            return _StubSpiceResult(success=False, errors=["Stub: simulation failed"])
        return _StubSpiceResult(
            success=True,
            measurements={k: type("_M", (), {"value": v})() for k, v in self._measurements.items()},
        )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


def _benign_config():
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


# ---------------------------------------------------------------------------
# Unit tests: L_eff monotonicity proof
# ---------------------------------------------------------------------------


class TestLEffMonotonicity:
    """Confirm L_eff(k) is monotone in k, so endpoints bound the interior."""

    def test_l_eff_endpoints_correct(self):
        """L_eff(0)=L_coil, L_eff(1)=L_leakage."""
        cfg = OperatingPointConfig(
            V_bus=325,
            V_BR=1200,
            I_load_rms=10,
            L_coil=100e-6,
            L_leakage=10e-6,
            f_sw=20000,
        )
        assert _l_eff(cfg, 0.0) == 100e-6
        assert _l_eff(cfg, 1.0) == 10e-6

    def test_l_eff_linear_monotone(self):
        """L_eff is linear and monotone between 0 and 1."""
        cfg = OperatingPointConfig(
            V_bus=325,
            V_BR=1200,
            I_load_rms=10,
            L_coil=100e-6,
            L_leakage=10e-6,
            f_sw=20000,
        )
        prev = _l_eff(cfg, 0.0)
        for k in (0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
            cur = _l_eff(cfg, k)
            # monotone decreasing when L_coil > L_leakage
            assert cur <= prev
            assert cur >= cfg.L_leakage
            prev = cur

    def test_l_eff_increasing_monotone(self):
        """L_eff is monotone increasing when L_leakage > L_coil."""
        cfg = OperatingPointConfig(
            V_bus=325,
            V_BR=1200,
            I_load_rms=10,
            L_coil=5e-6,
            L_leakage=50e-6,
            f_sw=20000,
        )
        prev = _l_eff(cfg, 0.0)
        for k in (0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
            cur = _l_eff(cfg, k)
            assert cur >= prev
            assert cur <= cfg.L_leakage
            prev = cur

    def test_di_dt_monotone_from_l_eff(self):
        """di/dt(k) = V_bus / L_eff(k) is monotone in k."""
        cfg = OperatingPointConfig(
            V_bus=325,
            V_BR=1200,
            I_load_rms=10,
            L_coil=100e-6,
            L_leakage=10e-6,
            f_sw=20000,
        )
        di_dt_0 = cfg.V_bus / _l_eff(cfg, 0.0)
        di_dt_1 = cfg.V_bus / _l_eff(cfg, 1.0)
        for k in (0.1, 0.25, 0.5, 0.75, 0.9):
            di_dt_k = cfg.V_bus / _l_eff(cfg, k)
            # Should be between the endpoint values (monotone)
            assert di_dt_0 <= di_dt_k <= di_dt_1 or di_dt_1 <= di_dt_k <= di_dt_0


# ---------------------------------------------------------------------------
# Unit tests: interior bounding soundness check
# ---------------------------------------------------------------------------


class TestInteriorBoundingSoundnessCheck:
    """Test _interior_bounding_soundness_check directly."""

    def test_monotone_model_returns_no_violations(self):
        """With the real monotone coupling model, interior never worse."""
        cfg = OperatingPointConfig(
            V_bus=325,
            V_BR=1200,
            I_load_rms=10,
            L_coil=100e-6,
            L_leakage=10e-6,
            f_sw=20000,
        )
        violations = _interior_bounding_soundness_check(cfg)
        assert len(violations) == 0, (
            f"Monotone model should have no interior violations, got: {violations}"
        )

    def test_non_monotone_model_breach_detected(self):
        """Non-monotone coupling with interior L_loop_max below threshold."""
        cfg = OperatingPointConfig(
            V_bus=325,
            V_BR=1200,
            I_load_rms=10,
            L_coil=100e-6,
            L_leakage=100e-6,
            f_sw=20000,
            min_feasible_L_loop=100e-9,  # 100 nH
        )

        # A non-monotone coupling model: L_eff dips to 50 nH in the middle,
        # causing di/dt to spike and L_loop_max to drop below 100 nH.
        def _non_monotone(k):
            # At k=0/1: 100uH. At k=0.5: 50nH.
            return 100e-6 - 50e-6 * math.sin(math.pi * k)

        violations = _interior_bounding_soundness_check(
            cfg,
            coupling_l_eff_fn=_non_monotone,
        )
        assert len(violations) > 0
        desc = " ".join(v.description for v in violations).lower()
        assert "interior" in desc
        assert "l_loop" in desc or "loop_inductance" in desc

    def test_non_monotone_without_breach_no_violations(self):
        """Non-monotone coupling where interior values are bounded by
        endpoints (endpoints are still the worst-case)."""
        cfg = OperatingPointConfig(
            V_bus=325,
            V_BR=1200,
            I_load_rms=10,
            L_coil=100e-6,
            L_leakage=100e-6,
            f_sw=20000,
            min_feasible_L_loop=0.1e-9,  # 0.1 nH — very forgiving
        )

        # Piecewise non-monotone: L_eff peaks in the middle, so di/dt
        # is worst at the endpoints.  Interior is strictly less severe.
        def _non_monotone(k):
            # k=0 -> 50uH (worst), k=0.5 -> 200uH (best), k=1 -> 100uH
            if k < 0.5:
                return 50e-6 + 300e-6 * k  # 50 -> 200 uH
            else:
                return 400e-6 - 300e-6 * k  # 200 -> 100 uH

        violations = _interior_bounding_soundness_check(
            cfg,
            coupling_l_eff_fn=_non_monotone,
        )
        assert len(violations) == 0, (
            f"Endpoints are worst-case; interior should have no violations. "
            f"Got: {[v.description for v in violations]}"
        )


# ---------------------------------------------------------------------------
# Gate-level error test (AE6/R5): interior breach -> gate NOT CLEAN
# ---------------------------------------------------------------------------


class TestOperatingPointGateInteriorBounding:
    """Gate-level tests for interior coupling breach detection."""

    def test_interior_breach_gate_violations_not_clean(self):
        """AE6/R5: when a non-monotone interior value breaches a ceiling
        but endpoints are clear, the gate must NOT return CLEAN."""
        cfg = {
            "V_bus": 325.0,
            "V_BR": 1200.0,
            "I_load_rms": 10.0,
            "L_coil": 100e-6,
            "L_leakage": 100e-6,
            "f_sw": 20000.0,
            "min_feasible_L_loop": 100e-9,  # 100 nH
        }

        # Non-monotone coupling: L_eff dips to 50 nH at k=0.5,
        # causing di/dt spike and L_loop_max << 100 nH.
        def _non_monotone_l_eff(k):
            return 100e-6 - 50e-6 * math.sin(math.pi * k)

        spice = StubNgspiceValidator(
            available=True,
            measurements={"di_dt_k0": 3.30e6},
        )
        gate = OperatingPointGate(
            cfg,
            spice_validator=spice,
            _coupling_l_eff_fn=_non_monotone_l_eff,
        )
        result = gate.check(BoardState())

        assert result.status != GateStatus.CLEAN, (
            "Gate must not be CLEAN when interior coupling breaches a ceiling"
        )
        assert result.status == GateStatus.VIOLATIONS, (
            f"Gate should be VIOLATIONS, got {result.status}"
        )
        assert len(result.violations) > 0
        # Should include the interior-specific violation
        interior_violations = [v for v in result.violations if "interior" in v.description.lower()]
        assert len(interior_violations) > 0, (
            "Should find an interior-specific violation description"
        )

    def test_monotone_benign_clean(self):
        """Happy: monotone benign range -> CLEAN via endpoints."""
        cfg = _benign_config()
        spice = StubNgspiceValidator(
            available=True,
            measurements={"di_dt_k0": 3.30e6},
        )
        gate = OperatingPointGate(cfg, spice_validator=spice)
        result = gate.check(BoardState())
        assert result.status == GateStatus.CLEAN
        assert len(result.violations) == 0


# ---------------------------------------------------------------------------
# PBT: sampled interior worst-case <= reported worst-case
# ---------------------------------------------------------------------------

_coupling_profile_strategy = st.fixed_dictionaries(
    {
        "V_bus": st.floats(100, 400),
        "L_coil": st.floats(10e-6, 500e-6),
        "L_leakage": st.floats(1e-6, 50e-6),
    }
)


def _worst_from_sampling(cfg: OperatingPointConfig, n_samples=101):
    """Compute the true worst-case across a fine interior grid."""
    worst_di_dt = -float("inf")
    worst_L_loop_max = float("inf")
    v_br_derated = cfg.V_BR * cfg.derate
    num = v_br_derated - cfg.V_bus
    for i in range(n_samples):
        k = i / (n_samples - 1)
        L_eff_val = _l_eff(cfg, k)
        if L_eff_val <= 0:
            continue
        di_dt_val = cfg.V_bus / L_eff_val
        l_loop_max = num / di_dt_val if num > 0 else 0.0
        if di_dt_val > worst_di_dt:
            worst_di_dt = di_dt_val
        if l_loop_max < worst_L_loop_max:
            worst_L_loop_max = l_loop_max
    return worst_di_dt, worst_L_loop_max


class TestInteriorBoundingPBT:
    """Property-based: interior worst-case <= reported (endpoint) worst-case."""

    @given(_coupling_profile_strategy)
    @settings(max_examples=200)
    def test_sampled_interior_bounded_by_endpoints(self, profile):
        """Across generated L_coil/L_leakage/V_bus profiles, the sampled
        interior worst-case di_dt and L_loop_max never exceed the endpoint
        worst-case (endpoints bound the interior)."""
        # Require L_leakage <= L_coil (physically typical: leakage <=
        # work-coil inductance).  The monotonicity proof covers both
        # orderings, but this keeps the strategy grounded.
        assume(profile["L_leakage"] <= profile["L_coil"])
        assume(profile["V_bus"] > 0)
        assume(profile["L_coil"] > 0)
        assume(profile["L_leakage"] > 0)

        cfg = OperatingPointConfig(
            V_bus=profile["V_bus"],
            V_BR=1200.0,
            I_load_rms=10.0,
            L_coil=profile["L_coil"],
            L_leakage=profile["L_leakage"],
            f_sw=20000.0,
        )

        # Endpoint worst (from compute_extremes pattern)
        v_br_derated = cfg.V_BR * cfg.derate
        num = v_br_derated - cfg.V_bus
        di_dt_k0 = cfg.V_bus / cfg.L_coil
        di_dt_k1 = cfg.V_bus / cfg.L_leakage
        endpoint_worst_di_dt = max(di_dt_k0, di_dt_k1)
        endpoint_worst_l_loop_max = min(
            num / di_dt_k0 if num > 0 else 0.0, num / di_dt_k1 if num > 0 else 0.0
        )

        sampled_worst_di_dt, sampled_worst_l_loop_max = _worst_from_sampling(cfg)

        # Monotonicity: interior must not beat endpoints
        assert sampled_worst_di_dt <= endpoint_worst_di_dt * (1.0 + 1e-12), (
            f"Interior di/dt {sampled_worst_di_dt:.3e} exceeds endpoint "
            f"worst {endpoint_worst_di_dt:.3e}"
        )
        assert sampled_worst_l_loop_max >= endpoint_worst_l_loop_max * (1.0 - 1e-12), (
            f"Interior L_loop_max {sampled_worst_l_loop_max:.3e} is worse than "
            f"endpoint worst {endpoint_worst_l_loop_max:.3e}"
        )
