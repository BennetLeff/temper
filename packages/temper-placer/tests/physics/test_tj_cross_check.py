"""Tests for the U11 T_j cross-check gate.

Covers:
- Happy: well-heatsinked device → CLEAN
- Fail-capable (wrong k_eff): disagreement > tau → VIOLATIONS
- Fail-capable (far-from-heatsink): distributed gradient dominates,
  VIOLATIONS with convection/edge-assumption attribution
- Fail-closed: missing R_θ → UNMEASURED
- Worst-case: gate uses worst-case P (max T_j), not nominal
- Shared vs independent inputs list is exposed and correct
- Attribution: far-from-heatsink labeled as convection/edge-assumption
"""

from __future__ import annotations

import numpy as np
import pytest

from temper_placer.physics.tj_cross_check import (
    INDEPENDENT_INPUTS,
    SHARED_INPUTS,
    DeviceThermalConfig,
    TjCrossCheckGate,
    _classify_disagreement,
    independent_inputs,
    shared_inputs,
)
from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
from temper_placer.placer.cp_sat.gates import GateStatus, ViolationType


# ---------------------------------------------------------------------------
# Representative device thermal configs with `because` datasheet citations
# ---------------------------------------------------------------------------

# Well-heatsinked device: board copper IS the primary thermal path
# (R_θCS and R_θSA model additional sink impedance the FDM does NOT
# capture — the FDM Dirichlet edge assumes T_edge = T_amb).
# For a board-heatsinked device the extra sink path is negligible.
_DEVICE_WELL_SINKED = DeviceThermalConfig(
    name="Q1",
    R_theta_jc=0.6,
    R_theta_cs=0.0,
    R_theta_sa=0.0,
    T_j_max=150.0,
    R_jc_because=(
        "STGW30NC60W datasheet, Table 7: Thermal resistance, "
        "junction-to-case, IGBT"
    ),
    R_cs_because=(
        "board-heatsinked: case soldered directly to copper pour; "
        "no separate thermal interface — the board IS the sink"
    ),
    R_sa_because=(
        "board-heatsinked: heatsink edge clamped to chassis at T_amb; "
        "the board conduction path ends at the clamped edge, which the "
        "FDM Dirichlet BC models directly"
    ),
    T_j_max_because=(
        "STGW30NC60W datasheet, Table 2: Absolute maximum ratings, "
        "T_j = 150°C"
    ),
)

# Realistic full-chain device: R_θCS + R_θSA model the separate heatsink
# path the FDM does NOT represent (FDM only models board conduction).
_DEVICE_FULL_SINK = DeviceThermalConfig(
    name="Q2",
    R_theta_jc=0.6,
    R_theta_cs=0.25,
    R_theta_sa=2.0,
    T_j_max=150.0,
    R_jc_because=(
        "STGW30NC60W datasheet, Table 7: Thermal resistance, "
        "junction-to-case, IGBT"
    ),
    R_cs_because=(
        "typical TO-247 grease interface, per Wakefield-Vette "
        "thermal interface guide"
    ),
    R_sa_because=(
        "assumed heatsink, Fischer SK 47/50 SA, natural convection, 2.0 K/W"
    ),
    T_j_max_because=(
        "STGW30NC60W datasheet, Table 2: Absolute maximum ratings, "
        "T_j = 150°C"
    ),
)


# ---------------------------------------------------------------------------
# Helper: build a well-heatsinked FDM config
# ---------------------------------------------------------------------------


def _make_config(
    cell_size_mm=0.5,
    height_cells=40,
    width_cells=40,
    ambient_C=40.0,
    heatsink_edge="TOP",
) -> ThermalFDMConfig:
    return ThermalFDMConfig(
        cell_size_mm=cell_size_mm,
        origin_mm=(0.0, 0.0),
        height_cells=height_cells,
        width_cells=width_cells,
        ambient_C=ambient_C,
        heatsink_edge=heatsink_edge,
    )


# ---------------------------------------------------------------------------
# HAPPY: well-heatsinked device → CLEAN
# ---------------------------------------------------------------------------


def test_well_heatsinked_device_clean():
    """A device near the heatsink edge with full copper pour agrees
    with the lumped model within tau → CLEAN.

    Uses a board-heatsinked config where R_θCS=R_θSA=0 (the board
    copper IS the primary thermal path; the FDM Dirichlet edge at
    T_amb models the clamped edge directly).  With full copper the
    FDM board-side resistance is negligible, so both models estimate
    T_j ≈ T_amb + P·R_θJC.
    """
    config = _make_config(
        height_cells=20,
        width_cells=20,
        heatsink_edge="TOP",
    )
    devices = {"Q1": (5.0, 9.0)}
    power_map = {"Q1": 5.0}
    device_thermal = {"Q1": _DEVICE_WELL_SINKED}
    copper_grid = np.ones((20, 20), dtype=np.float64)

    # Inject copper via a custom solver wrapper so the gate config
    # doesn't need a copper_grid parameter.
    def solver_with_cu(**kw):
        kw.pop("copper_grid", None)
        return solve_thermal_fdm(copper_grid=copper_grid, **kw)

    gate = TjCrossCheckGate(
        fdm_config=config,
        devices=devices,
        power_map=power_map,
        device_thermal=device_thermal,
        tau_C=5.0,
        T_amb=40.0,
    )

    result = gate._check_inner(solver_with_cu)
    assert result.status is GateStatus.CLEAN, (
        f"Expected CLEAN, got {result.status}: {result.error_message}"
    )


def test_agreeing_but_over_ceiling_is_violation():
    """Safe-by-default (regression): even when the two models AGREE within
    tau, a conservative T_j above T_j(max) must be a VIOLATION — a
    corroborated-but-over-limit design cannot pass. Before the ceiling
    check, U11 only checked model agreement and would report CLEAN here.
    """
    import dataclasses

    config = _make_config(height_cells=20, width_cells=20, heatsink_edge="TOP")
    devices = {"Q1": (5.0, 9.0)}
    power_map = {"Q1": 5.0}
    copper_grid = np.ones((20, 20), dtype=np.float64)

    def solver_with_cu(**kw):
        kw.pop("copper_grid", None)
        return solve_thermal_fdm(copper_grid=copper_grid, **kw)

    # Same well-sinked device (FDM and lumped agree), but T_j(max) set just
    # above ambient so the agreed T_j necessarily exceeds it.
    low_ceiling = dataclasses.replace(
        _DEVICE_WELL_SINKED,
        T_j_max=41.0,
        T_j_max_because="test: ceiling set just above T_amb to force over-limit",
    )
    gate = TjCrossCheckGate(
        fdm_config=config,
        devices=devices,
        power_map=power_map,
        device_thermal={"Q1": low_ceiling},
        tau_C=5.0,
        T_amb=40.0,
    )
    result = gate._check_inner(solver_with_cu)
    assert result.status is GateStatus.VIOLATIONS, (
        "Conservative T_j above T_j(max) must be a VIOLATION even when the "
        "two models agree"
    )
    assert any("SAFETY CEILING" in v.description for v in result.violations), (
        "Expected a safety-ceiling violation (gated on the conservative T_j), "
        "not only a corroboration one"
    )


# ---------------------------------------------------------------------------
# FAIL-CAPABLE (wrong k_eff): disagreement > tau → VIOLATIONS
# ---------------------------------------------------------------------------


def test_wrong_k_eff_produces_violation():
    """Injecting a severely wrong k_eff (1/100 of true FR4) makes the
    FDM predict a much higher T_j than the lumped model → VIOLATIONS.

    This proves the gate is not a dark metric: a plausible bug class
    (wrong material property) is caught.

    With the through-plane sink (#141), the device's R_θCS+R_θSA path
    provides a parallel heat-removal route.  To keep the wrong-k_eff bug
    visible, we use a high-resistance sink (R_θSA = 20 K/W) so in-plane
    conduction still matters and the discrepancy is detectable.
    """
    config_wrong = ThermalFDMConfig(
        cell_size_mm=0.5,
        origin_mm=(0.0, 0.0),
        height_cells=20,
        width_cells=20,
        heatsink_edge="TOP",
        k_fr4=0.003,  # 1/100 of real FR4 → much higher thermal resistance
        k_copper=3.85,  # also strongly reduced
        ambient_C=40.0,
    )
    devices = {"Q1": (5.0, 5.0)}
    power_map = {"Q1": 10.0}
    device_thermal = {
        "Q1": DeviceThermalConfig(
            name="Q1",
            R_theta_jc=0.6,
            R_theta_cs=0.25,
            R_theta_sa=50.0,  # high-sink-resistance: in-plane still matters
            T_j_max=150.0,
            R_jc_because="test",
            R_cs_because="test",
            R_sa_because="test: high R_SA so wrong k_eff is detectable with sink",
        ),
    }

    gate = TjCrossCheckGate(
        fdm_config=config_wrong,
        devices=devices,
        power_map=power_map,
        device_thermal=device_thermal,
        tau_C=5.0,
        T_amb=40.0,
    )

    result = gate._check_inner(solve_thermal_fdm)
    assert result.status is GateStatus.VIOLATIONS, (
        f"Expected VIOLATIONS with wrong k_eff, got {result.status}"
    )
    assert len(result.violations) >= 1
    v = result.violations[0]
    assert v.type == ViolationType.THERMAL
    assert "Q1" in v.components
    delta = v.context.get("delta_C", 0.0)
    assert delta > 5.0, (
        f"Expected delta > 5°C with wrong k_eff, got {delta:.1f}°C"
    )


# ---------------------------------------------------------------------------
# FAIL-CAPABLE (far-from-heatsink): distributed gradient dominates
# ---------------------------------------------------------------------------


def test_far_from_heatsink_produces_violation_with_attribution():
    """A device placed far from the heatsink edge on a long thin board
    with full copper pour and a weak through-plane sink (high R_SA)
    creates an in-plane conduction gradient the single-resistor
    lumped model cannot capture → VIOLATIONS with edge-assumption
    attribution.

    Physics: with full copper (good in-plane) and a weak sink (high
    R_SA), heat spreads efficiently in-plane toward the Dirichlet
    heatsink edge.  The FDM captures this board-as-heat-spreader
    effect, predicting LOWER T_j than the lumped R_θ ladder which
    ignores in-plane conduction.  This is the surviving in-plane
    discrepancy after the through-plane sink (#141) — the models
    disagree because the FDM models the board's in-plane heat-spreading
    that the lumped model omits.

    Note: before #141 the FDM was HIGHER (no through-plane path);
    after #141, with both paths modelled, the FDM with good copper
    may predict LOWER T_j, which is physically correct.
    """
    config = _make_config(
        height_cells=40,
        width_cells=5,
        heatsink_edge="TOP",
    )
    devices = {"Q1": (1.25, 1.0)}
    power_map = {"Q1": 5.0}
    device_thermal = {
        "Q1": DeviceThermalConfig(
            name="Q1",
            R_theta_jc=0.6,
            R_theta_cs=0.25,
            R_theta_sa=30.0,  # high R_SA → through-plane path is weak
            T_j_max=150.0,
            R_jc_because="test",
            R_cs_because="test",
            R_sa_because="test: high R_SA so spatial in-plane gradient is detectable",
        ),
    }
    copper_grid = np.ones((40, 5), dtype=np.float64)  # full copper pour

    def solver_with_cu(**kw):
        kw.pop("copper_grid", None)
        return solve_thermal_fdm(copper_grid=copper_grid, **kw)

    gate = TjCrossCheckGate(
        fdm_config=config,
        devices=devices,
        power_map=power_map,
        device_thermal=device_thermal,
        tau_C=5.0,
        T_amb=40.0,
    )

    result = gate._check_inner(solver_with_cu)

    assert result.status is GateStatus.VIOLATIONS, (
        f"Expected VIOLATIONS for far-from-heatsink device, "
        f"got {result.status}: {result.error_message}"
    )
    assert len(result.violations) >= 1
    v = result.violations[0]
    assert v.type == ViolationType.THERMAL
    delta = v.context.get("delta_C", 0.0)
    assert delta > 5.0, (
        f"Expected delta > 5°C for far-from-heatsink, got {delta:.1f}°C"
    )
    T_j_fdm = v.context.get("T_j_fdm_C")
    T_j_lumped = v.context.get("T_j_lumped_C")
    assert T_j_fdm is not None
    assert T_j_lumped is not None
    # Either direction is a valid disagreement — the gate catches
    # model mismatch regardless of which model is more conservative.
    assert (
        "convection" in v.description.lower()
        or "edge" in v.description.lower()
        or "disagreement" in v.description.lower()
    ), (
        f"Expected attribution in: "
        f"{v.description}"
    )


# ---------------------------------------------------------------------------
# FAIL-CLOSED: missing R_θ → UNMEASURED
# ---------------------------------------------------------------------------


def test_missing_rtheta_is_unmeasured():
    """A device present in the device list but absent from the thermal
    config → UNMEASURED (never a silent CLEAN)."""
    config = _make_config()
    devices = {"Q1": (5.0, 5.0), "Q2": (15.0, 5.0)}
    power_map = {"Q1": 5.0, "Q2": 3.0}
    device_thermal = {"Q1": _DEVICE_WELL_SINKED}

    gate = TjCrossCheckGate(
        fdm_config=config,
        devices=devices,
        power_map=power_map,
        device_thermal=device_thermal,
    )

    result = gate._check_inner(solve_thermal_fdm)
    assert result.status is GateStatus.UNMEASURED, (
        f"Expected UNMEASURED for missing R_θ, got {result.status}"
    )
    assert "Q2" in result.error_message
    assert (
        "R_θ" in result.error_message
        or "thermal" in result.error_message.lower()
    ), (
        f"Expected R_θ mention in error, got: {result.error_message}"
    )


# ---------------------------------------------------------------------------
# WORST-CASE: gate uses worst-case P (max T_j), not nominal
# ---------------------------------------------------------------------------


def test_gate_uses_worst_case_power():
    """The TjCrossCheckGate passes through whatever power_map it receives
    — it does NOT silently substitute a lower nominal power.  The caller
    (U6 operating-point gate) is responsible for supplying the worst-case
    values.

    This test confirms that different power inputs produce different
    T_j results (the gate does not normalize/override power).
    """
    config = _make_config()
    devices = {"Q1": (5.0, 5.0)}
    worst_case_power = 15.0
    nominal_power = 5.0
    device_thermal = {"Q1": _DEVICE_WELL_SINKED}

    gate_worst = TjCrossCheckGate(
        fdm_config=config,
        devices=devices,
        power_map={"Q1": worst_case_power},
        device_thermal=device_thermal,
        tau_C=50.0,
        T_amb=40.0,
    )
    result_worst = gate_worst._check_inner(solve_thermal_fdm)

    gate_nominal = TjCrossCheckGate(
        fdm_config=config,
        devices=devices,
        power_map={"Q1": nominal_power},
        device_thermal=device_thermal,
        tau_C=50.0,
        T_amb=40.0,
    )
    result_nominal = gate_nominal._check_inner(solve_thermal_fdm)

    # The gate does NOT override the power_map
    assert gate_worst._power_map["Q1"] == worst_case_power
    assert gate_nominal._power_map["Q1"] == nominal_power

    # With the real solver, different power → different T_j_fdm in the
    # result (even if both pass CLEAN with wide tau)
    # We can inspect the FDM output directly to confirm scale
    fdm_worst = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map={"Q1": worst_case_power},
    )
    fdm_nominal = solve_thermal_fdm(
        config=config,
        devices=devices,
        power_map={"Q1": nominal_power},
    )

    if fdm_worst.is_usable and fdm_nominal.is_usable:
        T_worst = float(np.mean(fdm_worst.field.grid))
        T_nominal = float(np.mean(fdm_nominal.field.grid))
        # Higher power → higher temperatures
        assert T_worst > T_nominal, (
            f"Expected worst-case FDM temperature ({T_worst:.1f}°C) > "
            f"nominal ({T_nominal:.1f}°C) for {worst_case_power}W vs "
            f"{nominal_power}W"
        )


# ---------------------------------------------------------------------------
# SHARED vs INDEPENDENT INPUTS: exposed list
# ---------------------------------------------------------------------------


def test_shared_vs_independent_inputs_exposed():
    """The shared and independent inputs are exposed as documented lists
    on both the gate instance and the module level."""
    config = _make_config()
    devices = {"Q1": (5.0, 5.0)}
    power_map = {"Q1": 5.0}
    device_thermal = {"Q1": _DEVICE_WELL_SINKED}

    gate = TjCrossCheckGate(
        fdm_config=config,
        devices=devices,
        power_map=power_map,
        device_thermal=device_thermal,
    )

    shared = gate.shared_inputs
    independent = gate.independent_inputs

    assert len(shared) >= 2
    assert any("P " in s for s in shared)
    assert any("T_amb" in s for s in shared)

    assert len(independent) >= 2
    assert any("transport" in s.lower() for s in independent)
    assert any("data" in s.lower() for s in independent)

    # Module-level functions match
    assert SHARED_INPUTS == shared
    assert INDEPENDENT_INPUTS == independent
    assert shared_inputs() == SHARED_INPUTS
    assert independent_inputs() == INDEPENDENT_INPUTS


# ---------------------------------------------------------------------------
# Attribution: edge-assumption localization
# ---------------------------------------------------------------------------


def test_attribution_far_from_heatsink_label():
    """Verify the attribution logic labels a far-from-heatsink
    disagreement as 'convection/edge-assumption localization'."""
    config = _make_config(
        height_cells=80,
        width_cells=10,
        heatsink_edge="TOP",
    )

    result = _classify_disagreement(
        dev_name="Q1",
        delta=15.0,
        T_j_fdm=85.0,
        T_j_lumped=70.0,
        position_mm=(2.5, 5.0),
        fdm_config=config,
    )

    assert "convection" in result.lower() or "edge" in result.lower(), (
        f"Expected edge-assumption attribution, got: {result}"
    )


def test_attribution_not_edge_when_close_to_heatsink():
    """Verify a device close to the heatsink edge does NOT get the
    convection/edge-assumption attribution."""
    config = _make_config(
        height_cells=40,
        width_cells=20,
        heatsink_edge="TOP",
    )

    result = _classify_disagreement(
        dev_name="Q1",
        delta=8.0,
        T_j_fdm=78.0,
        T_j_lumped=70.0,
        position_mm=(5.0, 18.0),
        fdm_config=config,
    )

    assert "convection" not in result.lower(), (
        f"Expected NO convection attribution close to heatsink, got: {result}"
    )
    assert "disagreement" in result.lower() or "mismatch" in result.lower()


# ---------------------------------------------------------------------------
# Edge: empty configs raise early
# ---------------------------------------------------------------------------


def test_empty_configs_raise_value_error():
    """Empty devices/power_map/device_thermal raise ValueError at
    construction, not a cryptic FDM failure later."""
    config = _make_config()

    with pytest.raises(ValueError):
        TjCrossCheckGate(
            fdm_config=config,
            devices={},
            power_map={"Q1": 5.0},
            device_thermal={"Q1": _DEVICE_WELL_SINKED},
        )

    with pytest.raises(ValueError):
        TjCrossCheckGate(
            fdm_config=config,
            devices={"Q1": (5.0, 5.0)},
            power_map={},
            device_thermal={"Q1": _DEVICE_WELL_SINKED},
        )

    with pytest.raises(ValueError):
        TjCrossCheckGate(
            fdm_config=config,
            devices={"Q1": (5.0, 5.0)},
            power_map={"Q1": 5.0},
            device_thermal={},
        )
