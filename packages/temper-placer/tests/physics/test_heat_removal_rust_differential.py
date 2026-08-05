"""Differential tests: temper-thermal Rust vertical-sink field kernel
vs the pure-Python reference (temper_placer/physics/heat_removal.py,
Wave 4 Phase 4).

The pre-migration implementation is pinned here as an oracle (verbatim
semantics, including the exact f64 operation order: ``cell_area_m2 =
(cs * 1e-3) ** 2`` via CPython pow, ``h_bg = (10.0 * cell_area_m2) /
(cs * cs)``, the footprint bbox via ``max(0, int(np.floor(...)))`` /
``min(w, int(np.ceil(...)))``, ``n_cells = max(1, (row_max - row_min) *
(col_max - col_min))`` from the RAW post-clamp values, ``h_cell = g_dev
/ (n_cells * cs * cs)``, and the per-cell ``+= h_cell`` accumulation in
device iteration order — INCLUDING the numpy negative-slice-stop wrap
(``a[:, 0:-3]`` on a width-4 grid covers columns [0, 1)) when a
footprint's ``col_max``/``row_max`` goes negative).  Any change to the
Rust kernel (packages/temper-thermal/src/heat_removal.rs) or the Python
delegation that disagrees with the oracle fails here, bit-exactly.

Bit-exactness notes (Wave 4 catalog):

- **B1 (host libm via dlsym):** ``(cs * 1e-3) ** 2`` is CPython
  ``float.__pow__`` → host libm ``pow(x, 2.0)``.
- **B7 (f64 operation order):** ``h_bg`` and ``h_cell`` chains keep the
  oracle's exact op count, grouping, and left-to-right order.
- **Iteration order:** devices accumulate in the caller's dict
  iteration order; overlapping footprints add their ``h_cell`` in that
  same order on both sides.
- **numpy slice semantics:** a negative ``col_max``/``row_max`` (device
  footprint outside the grid) wraps as ``dim + stop`` exactly like
  numpy; ``n_cells`` is computed from the raw pre-wrap values.
"""

from __future__ import annotations

import random

import numpy as np
import pytest
import temper_thermal as _tt

from temper_placer.physics.heat_removal import H_CONV_BACKGROUND, build_h_field
from temper_placer.physics.thermal_fdm import ThermalFDMConfig
from temper_placer.physics.tj_cross_check import DeviceThermalConfig

# ---------------------------------------------------------------------------
# Oracle (pre-migration implementation, verbatim)
# ---------------------------------------------------------------------------
# Do not edit these — they are the reference the migration is pinned to.


def _oracle_build_h_field(
    config: ThermalFDMConfig,
    devices: dict[str, tuple[float, float]],
    device_thermal: dict[str, DeviceThermalConfig],
) -> np.ndarray:
    """Verbatim pre-migration per-cell vertical conductance builder."""
    h = config.height_cells
    w = config.width_cells
    cs = config.cell_size_mm  # mm
    ox, oy = config.origin_mm

    # --- Background convection (weak, uniform) ---
    cell_area_m2 = (cs * 1e-3) ** 2  # m²
    h_bg = H_CONV_BACKGROUND * cell_area_m2 / (cs * cs)

    h_field = np.full((h, w), h_bg, dtype=np.float64)

    if not devices:
        return h_field

    if not device_thermal:
        missing = [d for d in devices if d not in device_thermal]
        if missing:
            raise ValueError(
                f"{len(missing)} device(s) have no DeviceThermalConfig: "
                f"{', '.join(sorted(missing))}. "
                f"Provide a DeviceThermalConfig with R_θCS + R_θSA "
                f"and 'because' citations."
            )
        return h_field

    # --- Device footprint sinks ---
    half_f = 5.0 / 2.0

    for dev_name, (dx_mm, dy_mm) in devices.items():
        if dev_name not in device_thermal:
            raise ValueError(
                f"Device '{dev_name}' has no DeviceThermalConfig — "
                f"cannot compute through-plane sink. "
                f"Provide a DeviceThermalConfig with R_θCS + R_θSA "
                f"and 'because' citations, or remove the device."
            )

        dev_th = device_thermal[dev_name]
        R_vert = dev_th.R_theta_cs + dev_th.R_theta_sa

        if R_vert <= 0.0:
            continue

        g_dev = 1.0 / R_vert

        col_min = max(0, int(np.floor((dx_mm - half_f - ox) / cs)))
        col_max = min(w, int(np.ceil((dx_mm + half_f - ox) / cs)))
        row_min = max(0, int(np.floor((dy_mm - half_f - oy) / cs)))
        row_max = min(h, int(np.ceil((dy_mm + half_f - oy) / cs)))

        n_cells = max(1, (row_max - row_min) * (col_max - col_min))
        h_cell = g_dev / (n_cells * cs * cs)

        h_field[row_min:row_max, col_min:col_max] += h_cell

    return h_field


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dev_cfg(name: str, r_cs: float, r_sa: float) -> DeviceThermalConfig:
    return DeviceThermalConfig(
        name=name,
        R_theta_jc=0.6,
        R_theta_cs=r_cs,
        R_theta_sa=r_sa,
        T_j_max=150.0,
        R_jc_because="test",
        R_cs_because="test",
        R_sa_because="test",
    )


def _cfg(h: int, w: int, cs: float, ox: float = 0.0, oy: float = 0.0) -> ThermalFDMConfig:
    return ThermalFDMConfig(
        cell_size_mm=cs,
        origin_mm=(ox, oy),
        height_cells=h,
        width_cells=w,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )


def _assert_field_eq(got: np.ndarray, want: np.ndarray, label: str) -> None:
    assert got.dtype == want.dtype and got.shape == want.shape, f"{label}: {got.shape}/{got.dtype} vs {want.shape}/{want.dtype}"
    if not np.array_equal(got, want):
        # Locate the first mismatch for a useful message.
        idx = np.argwhere(got != want)
        r, c = idx[0]
        raise AssertionError(
            f"{label}: first mismatch at ({r},{c}): rust={got[r, c]!r} "
            f"({got[r, c].tobytes().hex()}) oracle={want[r, c]!r} "
            f"({want[r, c].tobytes().hex()})"
        )


def _direct(cfg, devices, device_thermal, label) -> None:
    """Compare the direct Rust kernel against the oracle."""
    xs = [devices[k][0] for k in devices]
    ys = [devices[k][1] for k in devices]
    r_cs = [device_thermal[k].R_theta_cs for k in devices]
    r_sa = [device_thermal[k].R_theta_sa for k in devices]
    raw = _tt.build_h_field_py(
        cfg.cell_size_mm, cfg.origin_mm[0], cfg.origin_mm[1],
        cfg.height_cells, cfg.width_cells, xs, ys, r_cs, r_sa,
    )
    got = np.frombuffer(raw, dtype=np.float64).reshape((cfg.height_cells, cfg.width_cells)).copy()
    want = _oracle_build_h_field(cfg, devices, device_thermal)
    _assert_field_eq(got, want, label)


# ---------------------------------------------------------------------------
# Direct kernel pins (bit-exact)
# ---------------------------------------------------------------------------


def test_direct_background_only() -> None:
    cfg = _cfg(4, 4, 1.0)
    devices: dict[str, tuple[float, float]] = {}
    device_thermal: dict[str, DeviceThermalConfig] = {}
    _direct(cfg, devices, device_thermal, "background-only")
    # h_bg = 10.0 * pow(1e-3, 2.0) / (1.0*1.0) ≈ 1e-5 (NOT exactly 1e-5
    # in f64 — 9.999999999999999e-06; the kernel matches the oracle bit-
    # for-bit, which the array_equal inside _direct already asserted).
    want = _oracle_build_h_field(cfg, devices, device_thermal)
    assert float(want[0, 0]) != 1e-5  # sanity: the f64 value is not exactly 1e-5
    assert abs(float(want[0, 0]) - 1e-5) < 1e-11


def test_direct_background_pow_vs_mul_discriminator() -> None:
    # `(cs * 1e-3) ** 2` must be host-libm pow, never x*x: at this cs
    # the two differ by 1 ulp in the h_bg value (measured 2026-08-04),
    # so a mul-mutant shifts every cell and fails this pin.
    cs = 66.24771326355554
    cfg = _cfg(2, 2, cs)
    devices: dict[str, tuple[float, float]] = {}
    device_thermal: dict[str, DeviceThermalConfig] = {}
    x = cs * 1e-3
    assert (x**2).hex() != (x * x).hex()  # the case genuinely discriminates
    _direct(cfg, devices, device_thermal, "bg-pow-vs-mul")


def test_direct_single_device() -> None:
    cfg = _cfg(10, 10, 1.0)
    devices = {"Q1": (5.0, 5.0)}
    device_thermal = {"Q1": _dev_cfg("Q1", 0.25, 1.0)}
    _direct(cfg, devices, device_thermal, "single-device")


def test_direct_multiple_devices_overlap() -> None:
    # Two devices whose 5 mm footprints overlap the same cells — the
    # accumulation ORDER matters (dict order) for bit-parity.
    cfg = _cfg(6, 6, 1.0)
    devices = {"Q1": (2.5, 2.5), "Q2": (3.5, 3.5), "Q3": (1.0, 1.0)}
    device_thermal = {
        "Q1": _dev_cfg("Q1", 0.25, 1.0),
        "Q2": _dev_cfg("Q2", 0.5, 0.5),
        "Q3": _dev_cfg("Q3", 0.1, 0.2),
    }
    _direct(cfg, devices, device_thermal, "overlapping-devices")


def test_direct_board_heatsinked_skip() -> None:
    cfg = _cfg(5, 5, 1.0)
    devices = {"Q1": (2.5, 2.5), "Q2": (4.0, 4.0)}
    device_thermal = {
        "Q1": _dev_cfg("Q1", 0.0, 0.0),  # R_vert = 0 → skipped
        "Q2": _dev_cfg("Q2", 0.25, 1.0),
    }
    _direct(cfg, devices, device_thermal, "board-heatsinked-skip")


@pytest.mark.parametrize("seed", range(8))
def test_direct_randomized(seed: int) -> None:
    rng = random.Random(seed)
    h = rng.randint(3, 12)
    w = rng.randint(3, 12)
    cs = rng.choice([0.5, 1.0, 2.0, 0.25])
    ox = rng.choice([0.0, -3.0, 1.5])
    oy = rng.choice([0.0, -2.0])
    cfg = _cfg(h, w, cs, ox, oy)
    n_dev = rng.randint(1, 5)
    devices = {}
    device_thermal = {}
    for i in range(n_dev):
        name = f"Q{i + 1}"
        # Mix of in-grid, edge, and off-grid (incl. far-left/far-below
        # positions that make the numpy slice stop go negative).
        x = rng.choice([rng.uniform(ox - 8.0, ox + w * cs + 8.0), ox - 10.0, -100.0, rng.uniform(0.0, w * cs)])
        y = rng.choice([rng.uniform(oy - 8.0, oy + h * cs + 8.0), oy - 10.0, -100.0, rng.uniform(0.0, h * cs)])
        devices[name] = (x, y)
        if rng.random() < 0.2:
            device_thermal[name] = _dev_cfg(name, 0.0, 0.0)  # skip arm
        else:
            device_thermal[name] = _dev_cfg(name, rng.uniform(0.05, 1.0), rng.uniform(0.1, 2.0))
    _direct(cfg, devices, device_thermal, f"randomized-seed-{seed}")


def test_direct_negative_slice_wrap() -> None:
    # Footprint far LEFT of the grid: int(np.ceil(...)) goes negative,
    # and numpy's `a[:, 0:-3]` wraps to columns [0, W-3).  The kernel
    # must reproduce the wrap exactly (verified by this pin).
    cfg = _cfg(4, 4, 1.0)
    devices = {"Q1": (-10.0, 2.0)}  # dx + 2.5 < 0 → col_max negative
    device_thermal = {"Q1": _dev_cfg("Q1", 0.25, 1.0)}
    _direct(cfg, devices, device_thermal, "negative-slice-wrap")


def test_direct_negative_slice_both_axes() -> None:
    # Far-left AND far-below: both slice stops go negative.
    cfg = _cfg(4, 4, 1.0)
    devices = {"Q1": (-10.0, -10.0)}
    device_thermal = {"Q1": _dev_cfg("Q1", 0.25, 1.0)}
    _direct(cfg, devices, device_thermal, "negative-slice-both")


def test_direct_denormal_band() -> None:
    # Tiny g_dev (huge R) puts h_cell in the denormal band; default IEEE
    # semantics must not flush it.
    cfg = _cfg(3, 3, 1.0)
    devices = {"Q1": (1.5, 1.5)}
    device_thermal = {"Q1": _dev_cfg("Q1", 1e-300, 1e-300)}
    _direct(cfg, devices, device_thermal, "denormal-band")


# ---------------------------------------------------------------------------
# Module-level delegation pins
# ---------------------------------------------------------------------------


def test_module_delegation_known() -> None:
    cfg = _cfg(6, 6, 1.0)
    devices = {"Q1": (2.5, 2.5), "Q2": (4.0, 1.0)}
    device_thermal = {"Q1": _dev_cfg("Q1", 0.25, 1.0), "Q2": _dev_cfg("Q2", 0.5, 1.5)}
    got = build_h_field(cfg, devices, device_thermal)
    want = _oracle_build_h_field(cfg, devices, device_thermal)
    _assert_field_eq(got, want, "module-delegation")


def test_module_delegation_randomized() -> None:
    rng = random.Random(21)
    for _ in range(10):
        cfg = _cfg(rng.randint(3, 8), rng.randint(3, 8), rng.choice([0.5, 1.0, 2.0]))
        devices = {f"Q{i}": (rng.uniform(-2.0, 20.0), rng.uniform(-2.0, 20.0)) for i in range(rng.randint(1, 4))}
        device_thermal = {
            k: _dev_cfg(k, rng.uniform(0.05, 1.0), rng.uniform(0.1, 2.0)) for k in devices
        }
        got = build_h_field(cfg, devices, device_thermal)
        want = _oracle_build_h_field(cfg, devices, device_thermal)
        _assert_field_eq(got, want, "module-delegation-randomized")


def test_module_empty_devices() -> None:
    cfg = _cfg(4, 4, 1.0)
    got = build_h_field(cfg, {}, {})
    want = _oracle_build_h_field(cfg, {}, {})
    _assert_field_eq(got, want, "empty-devices")


def test_module_missing_config_raises() -> None:
    cfg = _cfg(4, 4, 1.0)
    devices = {"Q1": (1.0, 1.0)}
    # device_thermal empty → aggregate ValueError (sorted names).
    with pytest.raises(ValueError, match="device\\(s\\) have no DeviceThermalConfig"):
        build_h_field(cfg, devices, {})
    # device_thermal non-empty but missing a device → per-device ValueError.
    with pytest.raises(ValueError, match="Device 'Q1' has no DeviceThermalConfig"):
        build_h_field(cfg, devices, {"Q2": _dev_cfg("Q2", 0.25, 1.0)})


# ---------------------------------------------------------------------------
# Degenerate-input error parity (NaN/inf coordinates, NaN origin, cs=0.0)
# ---------------------------------------------------------------------------
# The reference's `int(np.floor(x))` / `int(np.ceil(x))` raise on
# degenerate floats: ValueError on NaN ("cannot convert float NaN to
# integer"), OverflowError on ±inf ("cannot convert float infinity to
# integer").  Rust's `as i64` cast silently saturates (NaN→0, ±inf→
# i64::MAX/MIN), and the shim validates device_thermal presence but NOT
# coordinates/cs — so NaN/inf centroids and cs=0.0 are reachable through
# the public API.  These pins force the Rust side to raise the same
# errors as the reference (the pyo3 bridge maps the checked conversion
# to ValueError/OverflowError/ZeroDivisionError).  Written RED first:
# against the saturating kernel the Rust arm returned a field instead of
# raising.


def test_degenerate_nan_coord_raises_value_error() -> None:
    cfg = _cfg(4, 4, 1.0)
    devices = {"Q1": (float("nan"), 1.0)}
    device_thermal = {"Q1": _dev_cfg("Q1", 0.25, 1.0)}
    with pytest.raises(ValueError, match="cannot convert float NaN to integer"):
        _oracle_build_h_field(cfg, devices, device_thermal)
    with pytest.raises(ValueError, match="cannot convert float NaN to integer"):
        build_h_field(cfg, devices, device_thermal)


def test_degenerate_nan_y_coord_raises_value_error() -> None:
    cfg = _cfg(4, 4, 1.0)
    devices = {"Q1": (1.0, float("nan"))}
    device_thermal = {"Q1": _dev_cfg("Q1", 0.25, 1.0)}
    with pytest.raises(ValueError, match="cannot convert float NaN to integer"):
        _oracle_build_h_field(cfg, devices, device_thermal)
    with pytest.raises(ValueError, match="cannot convert float NaN to integer"):
        build_h_field(cfg, devices, device_thermal)


def test_degenerate_nan_origin_raises_value_error() -> None:
    # NaN origin poisons the bbox numerators the same way a NaN centroid
    # does: (dx - half_f - NaN)/cs is NaN → int(np.floor(NaN)) raises.
    cfg = _cfg(4, 4, 1.0, ox=float("nan"))
    devices = {"Q1": (1.0, 1.0)}
    device_thermal = {"Q1": _dev_cfg("Q1", 0.25, 1.0)}
    with pytest.raises(ValueError, match="cannot convert float NaN to integer"):
        _oracle_build_h_field(cfg, devices, device_thermal)
    with pytest.raises(ValueError, match="cannot convert float NaN to integer"):
        build_h_field(cfg, devices, device_thermal)


def test_degenerate_inf_coord_raises_overflow_error() -> None:
    cfg = _cfg(4, 4, 1.0)
    devices = {"Q1": (float("inf"), 1.0)}
    device_thermal = {"Q1": _dev_cfg("Q1", 0.25, 1.0)}
    with pytest.raises(OverflowError, match="cannot convert float infinity to integer"):
        _oracle_build_h_field(cfg, devices, device_thermal)
    with pytest.raises(OverflowError, match="cannot convert float infinity to integer"):
        build_h_field(cfg, devices, device_thermal)


def test_degenerate_neg_inf_coord_raises_overflow_error() -> None:
    cfg = _cfg(4, 4, 1.0)
    devices = {"Q1": (1.0, float("-inf"))}
    device_thermal = {"Q1": _dev_cfg("Q1", 0.25, 1.0)}
    with pytest.raises(OverflowError, match="cannot convert float infinity to integer"):
        _oracle_build_h_field(cfg, devices, device_thermal)
    with pytest.raises(OverflowError, match="cannot convert float infinity to integer"):
        build_h_field(cfg, devices, device_thermal)


def test_degenerate_zero_cs_raises_zero_division() -> None:
    # The reference computes `10.0 * (cs*1e-3)**2 / (cs*cs)` FIRST — with
    # cs=0.0 that is 0.0/0.0 → ZeroDivisionError before any device
    # arithmetic, even with no devices at all.
    cfg = _cfg(4, 4, 0.0)
    with pytest.raises(ZeroDivisionError, match="float division by zero"):
        _oracle_build_h_field(cfg, {}, {})
    with pytest.raises(ZeroDivisionError, match="float division by zero"):
        build_h_field(cfg, {}, {})


def test_degenerate_zero_cs_with_device_raises_zero_division() -> None:
    cfg = _cfg(4, 4, 0.0)
    devices = {"Q1": (1.0, 1.0)}
    device_thermal = {"Q1": _dev_cfg("Q1", 0.25, 1.0)}
    with pytest.raises(ZeroDivisionError, match="float division by zero"):
        _oracle_build_h_field(cfg, devices, device_thermal)
    with pytest.raises(ZeroDivisionError, match="float division by zero"):
        build_h_field(cfg, devices, device_thermal)


@pytest.mark.parametrize("cs", [5e-324, 1e-200, 1e-162])
def test_degenerate_subnormal_cs_raises_zero_division(cs: float) -> None:
    # Pass 2 P1: the reference computes `10.0 * (cs*1e-3)**2 / (cs*cs)`
    # FIRST — for the subnormal underflow band `cs*cs` rounds to 0.0
    # and the division is 0.0/0.0 → ZeroDivisionError, even with no
    # devices.  Pass 1's kernel guard caught only the exact `cs == 0.0`;
    # the all-NaN field it returned instead poisoned the downstream FDM.
    # Written RED first: the shim returned an all-NaN field here.
    cfg = _cfg(4, 4, cs)
    with pytest.raises(ZeroDivisionError, match="float division by zero"):
        _oracle_build_h_field(cfg, {}, {})
    with pytest.raises(ZeroDivisionError, match="float division by zero"):
        build_h_field(cfg, {}, {})


@pytest.mark.parametrize("cs", [5e-324, 1e-200, 1e-162])
def test_degenerate_subnormal_cs_with_device_raises_zero_division(cs: float) -> None:
    # Same band with a device present: the reference's h_bg division
    # still raises FIRST (before any per-device arithmetic).
    cfg = _cfg(4, 4, cs)
    devices = {"Q1": (1.0, 1.0)}
    device_thermal = {"Q1": _dev_cfg("Q1", 0.25, 1.0)}
    with pytest.raises(ZeroDivisionError, match="float division by zero"):
        _oracle_build_h_field(cfg, devices, device_thermal)
    with pytest.raises(ZeroDivisionError, match="float division by zero"):
        build_h_field(cfg, devices, device_thermal)


def test_degenerate_zero_cs_raise_order_beats_missing_config() -> None:
    # Pass 2 P1 (raise-order inversion): the reference computes h_bg
    # BEFORE the device_thermal validation, so with cs=0.0 the geometry
    # ZeroDivisionError wins regardless of config state.  The shim used
    # to validate device_thermal first and raised ValueError instead —
    # a caller catching ZeroDivisionError (geometry) vs ValueError
    # (config) misclassified.  Written RED first: shim ValueError,
    # oracle ZeroDivisionError.
    cfg = _cfg(4, 4, 0.0)
    devices = {"Q1": (1.0, 1.0)}
    # Empty device_thermal → aggregate ValueError arm — ZeroDivisionError
    # must still win.
    with pytest.raises(ZeroDivisionError, match="float division by zero"):
        _oracle_build_h_field(cfg, devices, {})
    with pytest.raises(ZeroDivisionError, match="float division by zero"):
        build_h_field(cfg, devices, {})
    # Partial device_thermal (Q2 present, Q1 missing) → per-device
    # ValueError arm — same precedence.
    device_thermal = {"Q2": _dev_cfg("Q2", 0.25, 1.0)}
    with pytest.raises(ZeroDivisionError, match="float division by zero"):
        _oracle_build_h_field(cfg, devices, device_thermal)
    with pytest.raises(ZeroDivisionError, match="float division by zero"):
        build_h_field(cfg, devices, device_thermal)
