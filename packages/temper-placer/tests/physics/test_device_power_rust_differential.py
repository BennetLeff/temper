"""Differential tests: temper-thermal Rust per-device power kernel vs the
pure-Python reference (temper_placer/physics/device_power.py, Wave 4
Phase A #2 — the canonical per-device power model, issue #140).

The pre-migration implementation is pinned here as an oracle (verbatim
semantics, including the exact f64 operation order: the DIODE
``I_avg = I_load_rms * 0.5`` → ``P_cond = I_avg * V_f`` →
``P_sw = E_rr * f_sw`` chain, the IGBT/MOSFET ``P_cond`` branch
(``I_load_rms**2 * R_ds_on`` — CPython ``**2`` is host-libm
``pow(x, 2.0)``, NOT ``x*x``; pinned bit-exactly below) vs
``I_load_rms * V_ce_sat``, the switching branch (``(E_on + E_off) * f_sw``
energy method vs the waveform fallback
``0.5 * V_bus * I_peak * f_sw * (t_rise + t_fall)`` with
``I_peak = I_load_rms * math.sqrt(2)`` — host-libm ``sqrt``), and the
final left-to-right ``P_cond + P_sw``).  Any change to the Rust kernel
(packages/temper-thermal/src/device_power.rs) or the Python delegation
that disagrees with the oracle fails here, bit-exactly.

The direct ``temper_thermal`` pins fail first (the crate is not yet
built with the new function); the module-level pins exercise the full
delegation path once wired.
"""

from __future__ import annotations

import math
import random
import struct

import pytest
import temper_thermal as _tt

from temper_placer.physics.device_power import (
    DeviceLossConfig,
    _compute_single_device_power,
    derive_power_map,
)

# ---------------------------------------------------------------------------
# Oracle (pre-migration implementation, verbatim)
# ---------------------------------------------------------------------------
# Do not edit these — they are the reference the migration is pinned to.
# They are a copy of the module's arithmetic AS COMMITTED before the Rust
# kernel existed.


def _oracle_single_device_power(
    V_bus,
    I_load_rms,
    f_sw,
    device,
    *,
    t_rise=50e-9,
    t_fall=50e-9,
):
    """Verbatim scalar core of the pre-migration per-device power model."""
    if device.device_type == "DIODE":
        I_avg = I_load_rms * 0.5
        P_cond = I_avg * device.V_f
        P_sw = device.E_rr * f_sw
        return P_cond + P_sw

    # IGBT or MOSFET
    if device.R_ds_on > 0:
        P_cond = I_load_rms**2 * device.R_ds_on
    else:
        P_cond = I_load_rms * device.V_ce_sat

    if device.E_on > 0 or device.E_off > 0:
        P_sw = (device.E_on + device.E_off) * f_sw
    else:
        I_peak = I_load_rms * math.sqrt(2)
        P_sw = 0.5 * V_bus * I_peak * f_sw * (t_rise + t_fall)

    return P_cond + P_sw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rust_call(device, V_bus, I_load_rms, f_sw, t_rise, t_fall):
    """Call the Rust kernel with the same scalar inputs the Python module
    will pass once wired."""
    return _tt.single_device_power_py(
        device.device_type,
        device.V_ce_sat,
        device.R_ds_on,
        device.E_on,
        device.E_off,
        device.V_f,
        device.E_rr,
        V_bus,
        I_load_rms,
        f_sw,
        t_rise,
        t_fall,
    )


def _bits(x: float) -> str:
    """Bit pattern of an f64, for precise mismatch reporting."""
    return struct.pack(">d", x).hex()


def _random_device(rng) -> DeviceLossConfig:
    """Random loss config covering DIODE / IGBT-energy / IGBT-waveform /
    MOSFET paths."""
    kind = rng.choice(["DIODE", "IGBT_ENERGY", "IGBT_WAVEFORM", "MOSFET"])
    if kind == "DIODE":
        return DeviceLossConfig(
            name="D1",
            device_type="DIODE",
            V_f=rng.uniform(0.1, 3.0),
            E_rr=rng.uniform(0.0, 5e-3),
            V_f_because="t",
            E_rr_because="t",
        )
    if kind == "IGBT_ENERGY":
        return DeviceLossConfig(
            name="Q1",
            device_type="IGBT",
            V_ce_sat=rng.uniform(0.5, 3.0),
            E_on=rng.uniform(0.0, 1e-3),
            E_off=rng.uniform(0.0, 1e-3),
            V_ce_sat_because="t",
            E_on_because="t",
            E_off_because="t",
        )
    if kind == "IGBT_WAVEFORM":
        return DeviceLossConfig(
            name="Q1",
            device_type="IGBT",
            V_ce_sat=rng.uniform(0.5, 3.0),
            E_on=0.0,
            E_off=0.0,
            V_ce_sat_because="t",
            E_on_because="t",
            E_off_because="t",
        )
    # MOSFET
    return DeviceLossConfig(
        name="Q1",
        device_type="IGBT",
        V_ce_sat=0.0,
        R_ds_on=rng.uniform(0.001, 1.0),
        E_on=0.0,
        E_off=0.0,
        V_ce_sat_because="t",
        E_on_because="t",
        E_off_because="t",
    )


def _random_op(rng):
    """Random operating-point scalars (V_bus, I_load_rms, f_sw, t_rise,
    t_fall) spanning realistic and adversarial magnitudes."""
    v_bus = rng.choice([100.0, 325.0, rng.uniform(10.0, 800.0)])
    i_rms = rng.choice([1.0, 16.0, rng.uniform(0.001, 100.0)])
    f_sw = rng.choice([0.0, 25000.0, rng.uniform(100.0, 200000.0)])
    t_rise = rng.choice([50e-9, rng.uniform(1e-9, 1e-6)])
    t_fall = rng.choice([50e-9, rng.uniform(1e-9, 1e-6)])
    return v_bus, i_rms, f_sw, t_rise, t_fall


# ---------------------------------------------------------------------------
# Direct Rust pins (bit-exact float equality)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(25))
def test_direct_single_device_power_bit_exact(seed):
    """Rust kernel == oracle, bit-exact, over random device configs and
    operating points (all four device paths)."""
    rng = random.Random(seed)
    for _ in range(40):
        device = _random_device(rng)
        v_bus, i_rms, f_sw, t_rise, t_fall = _random_op(rng)
        expected = _oracle_single_device_power(
            v_bus, i_rms, f_sw, device, t_rise=t_rise, t_fall=t_fall
        )
        got = _rust_call(device, v_bus, i_rms, f_sw, t_rise, t_fall)
        assert got == expected, (
            f"P mismatch on {device.device_type} "
            f"(V_ce_sat={device.V_ce_sat!r} R_ds_on={device.R_ds_on!r} "
            f"E_on={device.E_on!r} E_off={device.E_off!r} V_f={device.V_f!r} "
            f"E_rr={device.E_rr!r}) V_bus={v_bus!r} I={i_rms!r} "
            f"f_sw={f_sw!r} tr={t_rise!r} tf={t_fall!r}: "
            f"rust={got!r} ({_bits(got)}) oracle={expected!r} ({_bits(expected)})"
        )


def test_direct_single_device_power_known_values():
    """Hand-computed values (exact f64 in both implementations)."""
    # DIODE: I_avg = 8.0, P_cond = 8.0*1.05 = 8.4, P_sw = 0.06e-3*25000 = 1.5
    diode = DeviceLossConfig(
        name="D1", device_type="DIODE", V_f=1.05, E_rr=0.06e-3,
        V_f_because="t", E_rr_because="t",
    )
    assert _rust_call(diode, 325.0, 16.0, 25000.0, 50e-9, 50e-9) == 9.9
    # IGBT energy method: P_cond = 16*1.7 = 27.2; P_sw = (0.32e-3+0.21e-3)*25000
    # = 13.25; total 40.45
    igbt = DeviceLossConfig(
        name="Q1", device_type="IGBT", V_ce_sat=1.7, E_on=0.32e-3, E_off=0.21e-3,
        V_ce_sat_because="t", E_on_because="t", E_off_because="t",
    )
    assert _rust_call(igbt, 325.0, 16.0, 25000.0, 50e-9, 50e-9) == 40.45
    # Waveform fallback at f_sw=0: P_sw = 0, P = P_cond = 16*1.7 = 27.2
    wf = DeviceLossConfig(
        name="Q1", device_type="IGBT", V_ce_sat=1.7, E_on=0.0, E_off=0.0,
        V_ce_sat_because="t", E_on_because="t", E_off_because="t",
    )
    assert _rust_call(wf, 325.0, 16.0, 0.0, 50e-9, 50e-9) == 27.2


def test_direct_mosfet_pow2_semantics():
    """`I_load_rms**2` is host-libm pow(x, 2.0), NOT x*x — pin a value where
    the two differ (measured: ~0.14% of random floats) so the Rust kernel
    cannot silently regress to `x * x`."""
    # 974.5535622665931**2 differs from x*x (see migration record)
    x = 974.5535622665931
    assert x**2 != x * x, "test input must discriminate pow(x,2.0) from x*x"
    mos = DeviceLossConfig(
        name="Q1", device_type="IGBT", V_ce_sat=0.0, R_ds_on=3.0,
        E_on=0.0, E_off=0.0, V_ce_sat_because="t", E_on_because="t",
        E_off_because="t",
    )
    expected = _oracle_single_device_power(100.0, x, 0.0, mos, t_rise=50e-9, t_fall=50e-9)
    got = _rust_call(mos, 100.0, x, 0.0, 50e-9, 50e-9)
    assert got == expected, f"pow semantics broken: rust={got!r} oracle={expected!r}"


def test_direct_denormal_band_bit_exact():
    """B8 (denormal underflow): tiny inputs must NOT be flushed to zero —
    CPython IEEE preserves denormals; the Rust kernel must too.
    I_load_rms=1e-155 → pow(I, 2.0) ≈ 1e-310, inside the f64 denormal band
    (min normal ≈ 2.2e-308); with R_ds_on=1.0 the product stays denormal."""
    tiny = DeviceLossConfig(
        name="Q1", device_type="IGBT", V_ce_sat=0.0, R_ds_on=1.0,
        E_on=0.0, E_off=0.0, V_ce_sat_because="t", E_on_because="t",
        E_off_because="t",
    )
    expected = _oracle_single_device_power(100.0, 1e-155, 0.0, tiny, t_rise=50e-9, t_fall=50e-9)
    got = _rust_call(tiny, 100.0, 1e-155, 0.0, 50e-9, 50e-9)
    assert got == expected, f"denormal band: rust={got!r} oracle={expected!r}"
    assert 0.0 < got < 1e-300, "expected a denormal result, not 0.0"


def test_direct_nan_inf_semantics():
    """Non-finite parity: NaN and inf inputs follow the same branch rules
    in both implementations (NaN comparisons are false; arithmetic with NaN
    propagates)."""
    nan_dev = DeviceLossConfig(
        name="Q1", device_type="IGBT", V_ce_sat=2.0, E_on=1e-3, E_off=0.0,
        V_ce_sat_because="t", E_on_because="t", E_off_because="t",
    )
    exp = _oracle_single_device_power(100.0, float("nan"), 10000.0, nan_dev)
    got = _rust_call(nan_dev, 100.0, float("nan"), 10000.0, 50e-9, 50e-9)
    assert math.isnan(exp) and math.isnan(got), f"nan: rust={got!r} oracle={exp!r}"

    # inf I_load_rms on the waveform path: I_peak = inf, and the chain's
    # f_sw (0.0 here) makes 0.5*V_bus*I_peak*f_sw = inf*0.0 = NaN — the
    # SAME NaN in both implementations (parity is NaN-vs-NaN, not ==).
    inf_wf = DeviceLossConfig(
        name="Q1", device_type="IGBT", V_ce_sat=2.0, E_on=0.0, E_off=0.0,
        V_ce_sat_because="t", E_on_because="t", E_off_because="t",
    )
    exp = _oracle_single_device_power(100.0, float("inf"), 0.0, inf_wf)
    got = _rust_call(inf_wf, 100.0, float("inf"), 0.0, 50e-9, 50e-9)
    assert math.isnan(exp) and math.isnan(got), f"inf waveform: rust={got!r} oracle={exp!r}"

    # NaN R_ds_on selects the V_ce_sat branch in BOTH implementations
    nan_rdson = DeviceLossConfig(
        name="Q1", device_type="IGBT", V_ce_sat=2.0, R_ds_on=float("nan"),
        E_on=1e-3, E_off=0.0, V_ce_sat_because="t", E_on_because="t",
        E_off_because="t",
    )
    exp = _oracle_single_device_power(100.0, 10.0, 10000.0, nan_rdson)
    got = _rust_call(nan_rdson, 100.0, 10.0, 10000.0, 50e-9, 50e-9)
    assert got == exp, f"nan R_ds_on branch: rust={got!r} oracle={exp!r}"


def test_direct_zero_energy_edge():
    """E_on == E_off == 0.0 exactly is the waveform-fallback branch; a
    single epsilon-away value flips to the energy method (branch pin)."""
    dev_a = DeviceLossConfig(
        name="Q1", device_type="IGBT", V_ce_sat=2.0, E_on=0.0, E_off=0.0,
        V_ce_sat_because="t", E_on_because="t", E_off_because="t",
    )
    dev_b = DeviceLossConfig(
        name="Q1", device_type="IGBT", V_ce_sat=2.0, E_on=1e-300, E_off=0.0,
        V_ce_sat_because="t", E_on_because="t", E_off_because="t",
    )
    for v_bus, i_rms, f_sw in [(100.0, 10.0, 25000.0), (325.0, 16.0, 0.0)]:
        exp_a = _oracle_single_device_power(v_bus, i_rms, f_sw, dev_a)
        exp_b = _oracle_single_device_power(v_bus, i_rms, f_sw, dev_b)
        assert _rust_call(dev_a, v_bus, i_rms, f_sw, 50e-9, 50e-9) == exp_a
        assert _rust_call(dev_b, v_bus, i_rms, f_sw, 50e-9, 50e-9) == exp_b


# ---------------------------------------------------------------------------
# Module-level pins (full delegation path)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(10))
def test_module_level_single_device_power_bit_exact(seed):
    """_compute_single_device_power (delegating) == oracle, bit-exact."""
    rng = random.Random(2000 + seed)
    for _ in range(25):
        device = _random_device(rng)
        v_bus, i_rms, f_sw, t_rise, t_fall = _random_op(rng)
        expected = _oracle_single_device_power(
            v_bus, i_rms, f_sw, device, t_rise=t_rise, t_fall=t_fall
        )
        got = _compute_single_device_power(
            V_bus=v_bus,
            I_load_rms=i_rms,
            f_sw=f_sw,
            device=device,
            t_rise=t_rise,
            t_fall=t_fall,
        )
        assert got == expected, (
            f"delegation mismatch on {device.device_type}: rust={got!r} "
            f"oracle={expected!r}"
        )


def test_module_level_derive_power_map_bit_exact():
    """derive_power_map (multi-device, validation preserved in Python)
    agrees bit-exactly with the per-device oracle for every device."""
    rng = random.Random(0xD1CE)
    from temper_placer.physics.operating_point import _validate_config

    cfg = _validate_config(
        {
            "V_bus": 325.0,
            "V_BR": 600.0,
            "I_load_rms": 16.0,
            "L_coil": 100e-6,
            "L_leakage": 10e-6,
            "f_sw": 25000.0,
            "t_rise": 50e-9,
            "t_fall": 50e-9,
        }
    )
    configs = {f"D{i}": _random_device(rng) for i in range(8)}
    pm = derive_power_map(cfg, configs)
    for ref, dev in configs.items():
        expected = _oracle_single_device_power(
            cfg.V_bus, cfg.I_load_rms, cfg.f_sw, dev, t_rise=cfg.t_rise, t_fall=cfg.t_fall
        )
        assert pm[ref] == expected, (
            f"derive_power_map[{ref}] rust={pm[ref]!r} oracle={expected!r}"
        )


def test_module_level_diode_path_bit_exact():
    """Explicit DIODE parity at a realistic Temper operating point."""
    dev = DeviceLossConfig(
        name="D1", device_type="DIODE", V_f=1.05, E_rr=0.06e-3,
        V_f_because="t", E_rr_because="t",
    )
    expected = _oracle_single_device_power(325.0, 16.0, 25000.0, dev)
    got = _compute_single_device_power(
        V_bus=325.0, I_load_rms=16.0, f_sw=25000.0, device=dev
    )
    assert got == expected == 9.9
