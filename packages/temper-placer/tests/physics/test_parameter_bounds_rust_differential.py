"""Differential tests: temper-thermal Rust parameter-bound kernels vs
the pure-Python reference (temper_placer/physics/parameter_bounds.py,
Wave 4 Phase 4).

The pre-migration implementations are pinned here as oracles (verbatim
semantics, including: the keyword monotonicity classification of a
swept parameter name into +1 / −1 / 0 with its exact `because`
citation strings — including the double spaces after sentence periods —
and `ParameterBound.worst_case_value`'s mono > 0 → max / mono < 0 →
min / else max selection).  Any change to the Rust kernels
(packages/temper-thermal/src/parameter_bounds.rs) or the Python
delegation that disagrees with the oracle fails here, string- and
bit-exactly.

Boundary notes:

- `build_thermal_parameter_bounds` keeps its prereg / FDM-config
  introspection and the literal ambient_C / h_sink_min bounds in
  Python; the keyword classification delegates.
- `compute_thermal_soundness` stays Python (it drives the FDM corner
  solve — the KTD9-style boundary — and builds the detail messages).
- `monotonicity_proof()` stays Python (returns the docstring).
"""

from __future__ import annotations

import random

import pytest
import temper_thermal as _tt

from temper_placer.physics.parameter_bounds import (
    ParameterBound,
    build_thermal_parameter_bounds,
    worst_case_corner,
)

# ---------------------------------------------------------------------------
# Oracles (pre-migration implementation, verbatim)
# ---------------------------------------------------------------------------


def _oracle_classify(parameter: str, because: str):
    """Verbatim pre-migration classification (the keyword branches of
    build_thermal_parameter_bounds)."""
    param_lower = parameter.lower()

    if "power" in param_lower or "dissipation" in param_lower or "P_loss" in param_lower:
        return (
            +1,
            because,
            (
                "b = Q_vec + h*T_amb; A unchanged.  A^{-1} >= 0 "
                "(M-matrix property), so T = A^{-1} b increases "
                "monotonically in Q component-wise.  -> "
                f"T_j INCREASING in {parameter}"
            ),
        )

    elif (
        "junction_to_case" in param_lower
        or "r_theta" in param_lower
        or "thermal_resistance" in param_lower
    ):
        return (
            +1,
            because,
            (
                "R_theta = 1/h for through-plane sink.  "
                "d T / d h_i = A^{-1} e_i (T_amb - T_i) <= 0 "
                "when T_i >= T_amb (M-matrix inverse non-negativity).  "
                "Higher R_theta -> lower h -> higher T_j.  "
                f"-> T_j INCREASING in {parameter}"
            ),
        )

    elif "heatspread" in param_lower or "spread" in param_lower or "copper" in param_lower:
        return (
            -1,
            because,
            (
                "Larger heatspread -> more copper coverage -> higher "
                "effective k_eff -> lower thermal resistance -> lower "
                "T_j.  Scaling k_field by alpha > 1 gives A(alpha) >= "
                "A(1) component-wise (M-matrix ordering), so "
                "A(alpha)^{-1} <= A(1)^{-1}, b unchanged, hence "
                f"T(alpha) <= T.  -> T_j DECREASING in {parameter}"
            ),
        )

    else:
        return (
            0,
            "unknown",
            (
                f"No monotonicity proof for '{parameter}'; "
                "corner-bound is NOT a guarantee for this parameter."
            ),
        )


def _oracle_worst_case_value(b: ParameterBound) -> float:
    """Verbatim pre-migration worst_case_value property."""
    if b.monotonicity > 0:
        return b.max
    if b.monotonicity < 0:
        return b.min
    return b.max


# ---------------------------------------------------------------------------
# Direct kernel pins
# ---------------------------------------------------------------------------


_NAMES = [
    "power_dissipation_w",
    "P_loss_total",
    "dissipation_factor",
    "junction_to_case_c_per_w",
    "r_theta_cs_k_per_w",
    "thermal_resistance_sink",
    "max_heatspread_mm",
    "copper_fraction",
    "heat_spread_angle",
    "wind_speed",
    "power_heatspread_mm",  # power family FIRST (precedence)
    "thermal_resistance_spread",  # r_theta family before heatspread
    "P_LOSS_W",
    "Junction_To_Case_C_Per_W",
    "",
]


@pytest.mark.parametrize("name", _NAMES)
def test_direct_classify_bit_exact(name):
    src = f"because for {name}"
    mono, unit, because = _tt.classify_parameter_py(name, src)
    w_mono, w_unit, w_because = _oracle_classify(name, src)
    assert mono == w_mono, f"{name}: mono {mono} vs {w_mono}"
    assert unit == w_unit, f"{name}: unit {unit!r} vs {w_unit!r}"
    assert because == w_because, f"{name}: because differs\n  rust: {because!r}\n  py:   {w_because!r}"


@pytest.mark.parametrize("seed", range(6))
def test_direct_classify_randomized(seed):
    rng = random.Random(seed)
    for _ in range(100):
        name = rng.choice(_NAMES) + str(rng.randint(0, 9))
        src = f"src-{rng.randint(0, 100)}"
        mono, unit, because = _tt.classify_parameter_py(name, src)
        w_mono, w_unit, w_because = _oracle_classify(name, src)
        assert (mono, unit, because) == (w_mono, w_unit, w_because), name


@pytest.mark.parametrize("bad", [None, 123, 45.0, [1, 2], object()])
def test_direct_classify_non_str_raises_attribute_error(bad):
    # Pass 2 P2: the reference's `parameter.lower()` raises AttributeError
    # for ANY non-str — CPython's "'NoneType' object has no attribute
    # 'lower'" — NOT the TypeError a pyo3 `String` extraction produced.
    # The bridge replicates the reference's class AND message (via the
    # object's type name).  Written RED first: TypeError.
    with pytest.raises(AttributeError, match="object has no attribute 'lower'"):
        _oracle_classify(bad, "src")
    with pytest.raises(AttributeError, match="object has no attribute 'lower'"):
        _tt.classify_parameter_py(bad, "src")


def test_direct_worst_case_values():
    mins = [1.0, 2.0, 3.0, 4.0]
    maxs = [10.0, 20.0, 30.0, 40.0]
    monos = [1, -1, 0, -1]
    got = _tt.worst_case_values_py(mins, maxs, monos)
    assert got == [10.0, 2.0, 30.0, 4.0]


def test_direct_worst_case_values_coerces_numeric_monos():
    # Pass 2 P2: the reference's `b.monotonicity > 0` accepts ANY
    # comparable — floats, bools and numpy scalars coerce (1.5 > 0 →
    # max).  The Vec<i64> bridge rejected a float monotonicity with
    # TypeError where the oracle arithmetic accepted it.  Vec<f64>
    # matches.  Written RED first: TypeError for 1.5.
    mins = [1.0, 2.0, 3.0, 4.0]
    maxs = [10.0, 20.0, 30.0, 40.0]
    got = _tt.worst_case_values_py(mins, maxs, [1.5, -0.5, 0.0, True])
    # oracle selection: 1.5 > 0 → max; -0.5 < 0 → min; 0.0 → max;
    # True > 0 → max.
    assert got == [10.0, 2.0, 30.0, 40.0]
    # None still raises TypeError on BOTH arms (class parity).
    with pytest.raises(TypeError):
        _tt.worst_case_values_py([1.0], [10.0], [None])


@pytest.mark.parametrize("seed", range(6))
def test_direct_worst_case_values_randomized(seed):
    rng = random.Random(seed)
    for _ in range(50):
        n = rng.randint(1, 8)
        mins = [rng.uniform(0.0, 10.0) for _ in range(n)]
        maxs = [m + rng.uniform(1.0, 100.0) for m in mins]
        monos = [rng.choice([-1, 0, 1]) for _ in range(n)]
        got = _tt.worst_case_values_py(mins, maxs, monos)
        want = [maxs[i] if monos[i] >= 0 else mins[i] for i in range(n)]
        assert got == want


# ---------------------------------------------------------------------------
# Module-level delegation pins
# ---------------------------------------------------------------------------


def test_module_build_bounds_classification():
    from temper_placer.validation.prereg.schema import FieldPreregistration

    prereg = FieldPreregistration.model_validate(
        {
            "field_name": "thermal",
            "independent_instrument": "physics_oracle",
            "cheap_baseline": {
                "name": "baseline",
                "description": "b",
                "metric": "thermal_score",
                "target_value": 0.0,
                "because": "b",
            },
            "parametric_ranges": [
                {"parameter": "power_dissipation_w", "min": 5.0, "max": 180.0, "because": "Power sweep range"},
                {"parameter": "junction_to_case_c_per_w", "min": 0.5, "max": 3.5, "because": "R_theta sweep"},
                {"parameter": "max_heatspread_mm", "min": 5.0, "max": 40.0, "because": "Heatspread range"},
                {"parameter": "fan_speed_rpm", "min": 0.0, "max": 5000.0, "because": "Unknown"},
            ],
            "structural_bounding_cases": [
                {"case_name": "single_igbt", "description": "Min config", "because": "Required"},
            ],
            "pass_bar": {
                "margin_gain": {"value": 0.1, "because": "b"},
                "beat_cheap_baseline_by": {"value": 0.05, "because": "b"},
                "across_perturbations": {"value": 5, "because": "b"},
            },
            "kill_criterion": {"description": "x", "because": "b"},
            "cost_budget": {
                "max_total_battery_seconds": 3600,
                "max_rounds_budget": 20,
                "field_convergence_round_limit": 5,
                "thermal_grid_cells_max": 10000,
                "target_solve_time_ms_per_field": 5000,
            },
        }
    )
    bounds = build_thermal_parameter_bounds(prereg)
    assert [b.parameter for b in bounds] == [
        "power_dissipation_w",
        "junction_to_case_c_per_w",
        "max_heatspread_mm",
        "fan_speed_rpm",
        "h_sink_min",
    ]
    monos = [b.monotonicity for b in bounds]
    assert monos == [1, 1, -1, 0, -1]
    # because strings must match the oracle classification verbatim for
    # the CLASSIFIED parameters (h_sink_min is a literal Python-built
    # bound with its own fixed citation — checked by the monos list).
    for b in bounds:
        if b.parameter == "h_sink_min":
            continue
        w_mono, w_unit, w_because = _oracle_classify(b.parameter, b.unit if b.unit != "unknown" else "x")
        assert b.because == w_because or b.unit == "unknown", f"{b.parameter}: because drift"


def test_module_worst_case_corner():
    bounds = [
        ParameterBound("p", 1.0, 10.0, 1, "deg", "because"),
        ParameterBound("q", 2.0, 20.0, -1, "deg", "because"),
        ParameterBound("r", 3.0, 30.0, 0, "deg", "because"),
    ]
    corner = worst_case_corner(bounds)
    assert corner == {"p": 10.0, "q": 2.0, "r": 30.0}
    for b in bounds:
        assert corner[b.parameter] == _oracle_worst_case_value(b)
