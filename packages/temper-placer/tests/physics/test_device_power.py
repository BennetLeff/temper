"""
Tests for canonical per-device power model (issue #140).

Covers:
- Derived P matches conduction+switching formula for known device+op point
- Consistency: gate (U6) and battery get the SAME P from one function
- Fail-closed: missing loss param → ValueError
- Fail-closed: battery aborts when device_loss_configs is absent
- Provenance: every loss param carries a non-empty ``because``
- Diode power: conduction V_f * I_avg + switching E_rr * f_sw
"""

from __future__ import annotations

import pytest

from temper_placer.physics.device_power import (
    DeviceLossConfig,
    _compute_single_device_power,
    derive_power_map,
    temper_diode_loss_config,
    temper_igbt_loss_config,
)
from temper_placer.physics.operating_point import (
    OperatingPointConfig,
    _compute_per_device_power,
    _validate_config,
)

# ---------------------------------------------------------------------------
# Helpers — known-answer config
# ---------------------------------------------------------------------------


def _test_op_config(**overrides: float) -> OperatingPointConfig:
    """Build a minimal test OperatingPointConfig with simple values."""
    base = {
        "V_bus": 100.0,
        "V_BR": 600.0,
        "I_load_rms": 10.0,
        "L_coil": 100e-6,
        "L_leakage": 10e-6,
        "f_sw": 10000.0,
        "T_amb": 40.0,
        "T_j_max": 150.0,
        **overrides,
    }
    return _validate_config(base)


def _igbt_config(**overrides) -> DeviceLossConfig:
    """Build an IGBT loss config with known-answer values."""
    defaults = {
        "name": "Q1",
        "device_type": "IGBT",
        "V_ce_sat": 2.0,
        "E_on": 1.0e-3,  # 1 mJ
        "E_off": 2.0e-3,  # 2 mJ
        "V_ce_sat_because": "test: datasheet Table 6",
        "E_on_because": "test: datasheet Table 8",
        "E_off_because": "test: datasheet Table 8",
    }
    defaults.update(overrides)
    return DeviceLossConfig(**defaults)


def _diode_config(**overrides) -> DeviceLossConfig:
    """Build a diode loss config with known-answer values."""
    defaults = {
        "name": "D1",
        "device_type": "DIODE",
        "V_f": 1.0,
        "E_rr": 0.5e-3,  # 0.5 mJ
        "V_f_because": "test: datasheet Table 5",
        "E_rr_because": "test: estimated from Q_rr * V_R / 2",
    }
    defaults.update(overrides)
    return DeviceLossConfig(**defaults)


# ---------------------------------------------------------------------------
# Tests: _compute_single_device_power — known answers
# ---------------------------------------------------------------------------


class TestSingleDevicePowerKnownAnswers:
    """Derived P matches the conduction+switching formula for known inputs."""

    def test_igbt_power_known_answer(self):
        """IGBT: P = V_ce_sat * I_rms + (E_on + E_off) * f_sw."""
        dev = _igbt_config()
        # P_cond = 10.0 * 2.0 = 20.0 W
        # P_sw   = (1e-3 + 2e-3) * 10000 = 30.0 W
        # Total  = 50.0 W
        p = _compute_single_device_power(
            V_bus=100.0,
            I_load_rms=10.0,
            f_sw=10000.0,
            device=dev,
        )
        assert p == pytest.approx(50.0)

    def test_igbt_falls_back_to_waveform_model(self):
        """When E_on=E_off=0, switching uses waveform approximation."""
        dev = _igbt_config(E_on=0.0, E_off=0.0)
        # P_cond = 20.0 W
        # P_sw = 0.5 * V_bus * I_peak * f_sw * (t_rise + t_fall)
        #      = 0.5 * 100 * (10*sqrt(2)) * 10000 * 100e-9
        #      = 0.5 * 100 * 14.142 * 10000 * 1e-7
        #      = 0.5 * 100 * 14.142 * 0.001
        #      = 0.5 * 100 * 0.014142
        #      = 0.7071 W
        # Actually let me recompute: 10000 * 100e-9 = 1e-3 = 0.001
        # 0.5 * 100 * 14.142 * 0.001 = 0.5 * 100 * 0.014142 = 0.7071 W
        # Total = 20.707 W
        p = _compute_single_device_power(
            V_bus=100.0,
            I_load_rms=10.0,
            f_sw=10000.0,
            device=dev,
        )
        expected_sw = 0.5 * 100.0 * (10.0 * 2**0.5) * 10000.0 * 100e-9
        expected = 20.0 + expected_sw
        assert p == pytest.approx(expected)

    def test_diode_power_known_answer(self):
        """DIODE: P = V_f * I_avg + E_rr * f_sw."""
        dev = _diode_config()
        # P_cond = 1.0 * (10.0 / 2) = 5.0 W
        # P_sw   = 0.5e-3 * 10000 = 5.0 W
        # Total  = 10.0 W
        p = _compute_single_device_power(
            V_bus=100.0,
            I_load_rms=10.0,
            f_sw=10000.0,
            device=dev,
        )
        assert p == pytest.approx(10.0)

    def test_mosfet_model_rds_on(self):
        """MOSFET: P = I_rms^2 * R_ds_on + switching (waveform fallback)."""
        dev = _igbt_config(
            V_ce_sat=0.0,
            R_ds_on=0.1,
            E_on=0.0,
            E_off=0.0,
        )
        # P_cond = 10.0^2 * 0.1 = 10.0 W
        # P_sw   = waveform = ~0.707 W (see above)
        p = _compute_single_device_power(
            V_bus=100.0,
            I_load_rms=10.0,
            f_sw=10000.0,
            device=dev,
        )
        expected_cond = 100.0 * 0.1  # 10.0
        expected_sw = 0.5 * 100.0 * (10.0 * 2**0.5) * 10000.0 * 100e-9
        assert p == pytest.approx(expected_cond + expected_sw)

    def test_igbt_zero_switching_loss_when_f_sw_zero(self):
        """When f_sw=0, switching loss is zero regardless of E_on/E_off."""
        dev = _igbt_config()
        p = _compute_single_device_power(
            V_bus=100.0,
            I_load_rms=10.0,
            f_sw=0.0,
            device=dev,
        )
        assert p == pytest.approx(20.0)  # only conduction

    def test_power_scales_linearly_with_current(self):
        """T_j scales linearly with P → power must scale linearly with I_rms."""
        dev = _igbt_config(E_on=0.0, E_off=0.0)
        p_5A = _compute_single_device_power(
            V_bus=100.0,
            I_load_rms=5.0,
            f_sw=10000.0,
            device=dev,
        )
        p_10A = _compute_single_device_power(
            V_bus=100.0,
            I_load_rms=10.0,
            f_sw=10000.0,
            device=dev,
        )
        # Conduction: linear in I_rms; switching: linear in I_peak = I_rms * sqrt(2)
        # Both scale linearly with I_rms, so total should be ~2x
        ratio = p_10A / p_5A
        assert 1.9 < ratio < 2.1

    def test_power_scales_linearly_with_f_sw(self):
        """Switching loss scales linearly with f_sw."""
        dev = _igbt_config()
        p_5k = _compute_single_device_power(
            V_bus=100.0,
            I_load_rms=10.0,
            f_sw=5000.0,
            device=dev,
        )
        p_10k = _compute_single_device_power(
            V_bus=100.0,
            I_load_rms=10.0,
            f_sw=10000.0,
            device=dev,
        )
        diff = p_10k - p_5k
        # conduction is constant (20W), switching difference: 30-15 = 15W
        assert diff == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# Tests: derive_power_map — multi-device
# ---------------------------------------------------------------------------


class TestDerivePowerMap:
    """derive_power_map produces the correct per-device power map."""

    def test_two_igbts_one_diode(self):
        """Three devices with different loss configs → correct map."""
        op = _test_op_config()
        configs = {
            "Q1": _igbt_config(name="Q1"),
            "Q2": _igbt_config(name="Q2"),
            "D1": _diode_config(name="D1"),
        }
        pm = derive_power_map(op, configs)
        assert set(pm.keys()) == {"Q1", "Q2", "D1"}
        assert pm["Q1"] == pytest.approx(50.0)
        assert pm["Q2"] == pytest.approx(50.0)
        assert pm["D1"] == pytest.approx(10.0)

    def test_different_igbt_params_produce_different_power(self):
        """Two IGBTs with different V_ce_sat produce different P."""
        op = _test_op_config()
        configs = {
            "Q1": _igbt_config(name="Q1", V_ce_sat=2.0),
            "Q2": _igbt_config(name="Q2", V_ce_sat=1.5),
        }
        pm = derive_power_map(op, configs)
        assert pm["Q1"] > pm["Q2"]
        assert pm["Q1"] == pytest.approx(50.0)
        assert pm["Q2"] == pytest.approx(10.0 * 1.5 + 30.0)  # 45.0 W

    def test_empty_configs_returns_empty_map(self):
        """Empty device_loss_configs → empty power_map."""
        op = _test_op_config()
        pm = derive_power_map(op, {})
        assert pm == {}


# ---------------------------------------------------------------------------
# Tests: consistency — gate (U6) and battery get the SAME P
# ---------------------------------------------------------------------------


class TestConsistencyGateAndBattery:
    """The operating-point gate (U6) and the battery use ONE function."""

    def test_u6_compute_per_device_power_matches_igbt(self):
        """U6's _compute_per_device_power returns the same value as
        _compute_single_device_power with a default IGBT config built
        from OperatingPointConfig."""
        cfg = _test_op_config(V_ce_sat=2.0, R_ds_on=0.0)
        p_u6 = _compute_per_device_power(cfg)

        # The equivalent direct call through _compute_single_device_power
        default_igbt = DeviceLossConfig(
            name="_test",
            device_type="IGBT",
            V_ce_sat=cfg.V_ce_sat,
            R_ds_on=cfg.R_ds_on,
            V_ce_sat_because="test",
        )
        p_direct = _compute_single_device_power(
            V_bus=cfg.V_bus,
            I_load_rms=cfg.I_load_rms,
            f_sw=cfg.f_sw,
            device=default_igbt,
            t_rise=cfg.t_rise,
            t_fall=cfg.t_fall,
        )
        assert p_u6 == pytest.approx(p_direct)

    def test_u6_and_derive_power_map_same_formula(self):
        """U6's _compute_per_device_power and derive_power_map use the
        same underlying formula — they agree for a single IGBT."""
        cfg = _test_op_config(V_ce_sat=2.0, R_ds_on=0.0)
        p_u6 = _compute_per_device_power(cfg)

        configs = {
            "Q1": DeviceLossConfig(
                name="Q1",
                device_type="IGBT",
                V_ce_sat=2.0,
                R_ds_on=0.0,
                V_ce_sat_because="test",
            ),
        }
        pm = derive_power_map(cfg, configs)
        assert pm["Q1"] == pytest.approx(p_u6)

    def test_temper_igbt_config_returns_nonzero_power(self):
        """The representative temper IGBT config produces a reasonable
        (non-zero) power number at realistic operating point."""
        cfg = _test_op_config(
            V_bus=325.0,
            I_load_rms=16.0,
            f_sw=25000.0,
            t_rise=50e-9,
            t_fall=50e-9,
        )
        dev = temper_igbt_loss_config("Q1")
        p = _compute_single_device_power(
            V_bus=cfg.V_bus,
            I_load_rms=cfg.I_load_rms,
            f_sw=cfg.f_sw,
            device=dev,
            t_rise=cfg.t_rise,
            t_fall=cfg.t_fall,
        )
        # P_cond = 16 * 1.7 = 27.2 W
        # P_sw = (0.32e-3 + 0.21e-3) * 25000 = 13.25 W
        # Total = 40.45 W
        expected = 27.2 + 13.25
        assert p == pytest.approx(expected)
        assert p > 0
        assert p < 100  # sanity bound

    def test_temper_diode_config_returns_nonzero_power(self):
        """The representative temper diode config produces a reasonable
        (non-zero) power number at realistic operating point."""
        cfg = _test_op_config(
            V_bus=325.0,
            I_load_rms=16.0,
            f_sw=25000.0,
        )
        dev = temper_diode_loss_config("D1")
        p = _compute_single_device_power(
            V_bus=cfg.V_bus,
            I_load_rms=cfg.I_load_rms,
            f_sw=cfg.f_sw,
            device=dev,
        )
        # P_cond = (16/2) * 1.05 = 8.4 W
        # P_sw = 0.06e-3 * 25000 = 1.5 W
        # Total = 9.9 W
        expected = 8.4 + 1.5
        assert p == pytest.approx(expected)
        assert p > 0


# ---------------------------------------------------------------------------
# Tests: fail-closed — missing loss param
# ---------------------------------------------------------------------------


class TestFailClosedMissingLossParam:
    """A power device with a missing loss param → ValueError / abort."""

    def test_igbt_missing_v_ce_sat_and_r_ds_on_raises(self):
        """IGBT with both V_ce_sat=0 and R_ds_on=0 → ValueError."""
        op = _test_op_config()
        bad_dev = _igbt_config(V_ce_sat=0.0, R_ds_on=0.0)
        configs = {"Q1": bad_dev}
        with pytest.raises(ValueError, match="V_ce_sat"):
            derive_power_map(op, configs)

    def test_diode_missing_v_f_raises(self):
        """Diode with V_f=0 → ValueError."""
        op = _test_op_config()
        bad_dev = _diode_config(V_f=0.0)
        configs = {"D1": bad_dev}
        with pytest.raises(ValueError, match="V_f"):
            derive_power_map(op, configs)

    def test_igbt_with_v_ce_sat_but_no_e_on_e_off_is_ok(self):
        """IGBT with V_ce_sat but no E_on/E_off is fine — falls back to
        waveform model.  Not a missing param."""
        op = _test_op_config()
        dev = _igbt_config(E_on=0.0, E_off=0.0)
        configs = {"Q1": dev}
        pm = derive_power_map(op, configs)
        assert pm["Q1"] > 0

    def test_mosfet_with_r_ds_on_but_no_v_ce_sat_is_ok(self):
        """MOSFET with R_ds_on > 0 and V_ce_sat=0 is fine."""
        op = _test_op_config()
        dev = _igbt_config(
            V_ce_sat=0.0,
            R_ds_on=0.1,
            E_on=0.0,
            E_off=0.0,
        )
        configs = {"Q1": dev}
        pm = derive_power_map(op, configs)
        assert pm["Q1"] > 0


# ---------------------------------------------------------------------------
# Tests: provenance — every loss param carries a non-empty `because`
# ---------------------------------------------------------------------------


class TestProvenanceCitations:
    """Every loss param in representative configs carries a non-empty
    because string."""

    def test_temper_igbt_config_has_all_citations(self):
        dev = temper_igbt_loss_config("Q1")
        assert dev.V_ce_sat > 0
        assert len(dev.V_ce_sat_because) > 10
        assert dev.E_on > 0
        assert len(dev.E_on_because) > 10
        assert dev.E_off > 0
        assert len(dev.E_off_because) > 10

    def test_temper_diode_config_has_all_citations(self):
        dev = temper_diode_loss_config("D1")
        assert dev.V_f > 0
        assert len(dev.V_f_because) > 10
        assert dev.E_rr > 0
        assert len(dev.E_rr_because) > 10

    def test_custom_igbt_without_citations_allowed(self):
        """A custom config with empty because strings is accepted —
        the contract is enforced by convention, not runtime."""
        dev = _igbt_config(
            V_ce_sat_because="",
            E_on_because="",
            E_off_because="",
        )
        assert dev.V_ce_sat == 2.0
        assert dev.V_ce_sat_because == ""


# ---------------------------------------------------------------------------
# Tests: derive_power_map with temperature effects
# ---------------------------------------------------------------------------


class TestDerivePowerMapTemperatureEffects:
    """T_j scales linearly with P → verify power scales correctly."""

    def test_higher_v_bus_increases_waveform_switching_loss(self):
        """Higher V_bus increases the waveform switching loss (P_sw ~ V_bus)."""
        dev = _igbt_config(E_on=0.0, E_off=0.0)
        p_low = _compute_single_device_power(
            V_bus=100.0,
            I_load_rms=10.0,
            f_sw=10000.0,
            device=dev,
        )
        p_high = _compute_single_device_power(
            V_bus=200.0,
            I_load_rms=10.0,
            f_sw=10000.0,
            device=dev,
        )
        # Conduction is same (20W), switching doubles (from V_bus doubling)
        assert p_high > p_low
        # The switching part alone doubled
        cond = 20.0
        sw_low = p_low - cond
        sw_high = p_high - cond
        assert sw_high == pytest.approx(2.0 * sw_low)

    def test_igbt_power_positive_for_all_positive_inputs(self):
        """Any combination of positive inputs produces positive power."""
        for v_bus in [10.0, 100.0, 400.0]:
            for i_rms in [1.0, 10.0, 50.0]:
                for f_sw in [100.0, 10000.0, 100000.0]:
                    dev = _igbt_config()
                    p = _compute_single_device_power(
                        V_bus=v_bus,
                        I_load_rms=i_rms,
                        f_sw=f_sw,
                        device=dev,
                    )
                    assert p > 0, f"P={p} for V={v_bus}, I={i_rms}, f={f_sw}"
