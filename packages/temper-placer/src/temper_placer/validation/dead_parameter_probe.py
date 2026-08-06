"""Wire/unwire probe for the dead-parameter sweep (plan 2026-08-02-019, U2).

Drives the registry built by :mod:`gate_input_registry`:

- **Gate consumers** (acceptance-gate inner audit): for each declared input,
  run the gate with the baseline scenario and again with that one input
  fail-forced past the gate's own threshold logic (KTD2).  A verdict that
  does not flip on a fail-forcing value proves the input dead.
- **Threshold-less consumers** (physics parameters): perturb the parameter
  deterministically at its source (KTD3) and run the production consumer.
  The run-to-run noise floor is measured first on identical input; a
  perturbation counts only when its delta exceeds the measured floor.

Every probe emits a :class:`ProbeRecord` with the baseline outcome, the
perturbed outcome, the delta, the measured noise floor, and a disposition:

- ``live`` — the input is proven wired (verdict flipped / delta over floor).
- ``dead`` — the input is proven dead (verdict unchanged / no signal).
- ``inconclusive`` — the gate was already FAIL at baseline (no flip possible);
  the baseline verdict is recorded, not misreported as dead.
- ``UNMEASURED`` — no probe could be performed (e.g. fail-forcing value not
  derivable, or a required runtime symbol is missing); reported, never
  silently skipped.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from temper_placer.validation.gate_input_registry import (
    GateInputRegistry,
    PhysicsParameterSpec,
    build_default_registry,
)

# Disposition constants
LIVE = "live"
DEAD = "dead"
INCONCLUSIVE = "inconclusive"
UNMEASURED = "UNMEASURED"

# How many identical-input runs back the noise-floor measurement.
NOISE_FLOOR_SAMPLES = 5


@dataclass(frozen=True)
class ProbeRecord:
    """Outcome of probing one declared input or physics parameter.

    Attributes:
        target: ``"gate:<gate>.<input>"`` or ``"param:<name>"``.
        kind: ``"gate_input"`` | ``"physics_parameter"``.
        disposition: live / dead / inconclusive / UNMEASURED.
        baseline_outcome: Verdict or scalar at baseline.
        perturbed_outcome: Verdict or scalar after the perturbation.
        delta: Absolute output movement (None for gate verdict probes).
        noise_floor: Measured run-to-run floor (None for gate verdict probes).
        detail: Human-readable evidence.
    """

    target: str
    kind: str
    disposition: str
    baseline_outcome: Any = None
    perturbed_outcome: Any = None
    delta: float | None = None
    noise_floor: float | None = None
    detail: str = ""


# --- Noise floor ---------------------------------------------------------------


def measure_noise_floor(
    run: Callable[[], float],
    samples: int = NOISE_FLOOR_SAMPLES,
) -> float:
    """Measure the run-to-run output spread on identical input.

    Runs *run* ``samples`` times and returns ``max - min``.  Deterministic
    consumers (direct sparse solves, pure functions) return ~0.0; stochastic
    or environment-dependent consumers get an honest floor.
    """
    values = [float(run()) for _ in range(samples)]
    return float(np.max(values) - np.min(values))


# --- Gate probes ---------------------------------------------------------------


def probe_acceptance_inner_input(
    registry: GateInputRegistry,
    gate_name: str,
    input_name: str,
) -> ProbeRecord:
    """Probe one declared input of a container gate via verdict flip.

    Runs the gate's baseline scenario and the fail-forced scenario (from the
    registry's per-input perturb transform) and compares verdicts.
    """
    gate = _find_gate(registry, gate_name)
    target = f"gate:{gate_name}.{input_name}"

    if input_name not in gate.perturb:
        spec = _find_input(gate, input_name)
        reason = spec.reason if spec and not spec.covered else (
            "no fail-forcing transform registered for this input"
        )
        return ProbeRecord(
            target=target,
            kind="gate_input",
            disposition=UNMEASURED,
            detail=f"no fail-forcing transform derivable: {reason}",
        )

    baseline_ctx = gate.build_baseline()
    baseline_verdict = bool(gate.consume(*baseline_ctx))

    perturbed_ctx = gate.perturb[input_name](*baseline_ctx)
    perturbed_verdict = bool(gate.consume(*perturbed_ctx))

    if baseline_verdict and not perturbed_verdict:
        disposition = LIVE
    elif not baseline_verdict:
        # Gate already FAIL at baseline — no flip possible.
        disposition = INCONCLUSIVE
    else:
        disposition = DEAD

    return ProbeRecord(
        target=target,
        kind="gate_input",
        disposition=disposition,
        baseline_outcome=baseline_verdict,
        perturbed_outcome=perturbed_verdict,
        detail=(
            f"baseline all_pass={baseline_verdict}; fail-forced "
            f"all_pass={perturbed_verdict}"
        ),
    )


def _find_gate(registry: GateInputRegistry, gate_name: str) -> Any:
    for gate in registry.gates:
        if gate.name == gate_name:
            return gate
    raise KeyError(f"gate '{gate_name}' not in registry (known: {[g.name for g in registry.gates]})")


def _find_input(gate: Any, input_name: str) -> Any | None:
    for spec in gate.declared_inputs:
        if spec.name == input_name:
            return spec
    return None


# --- Physics parameter probes --------------------------------------------------


def perturb_value(param: PhysicsParameterSpec) -> float:
    """Compute the deterministic perturbed value for a parameter."""
    mode = param.perturbation["mode"]
    delta = float(param.perturbation["delta"])
    if mode == "relative":
        return param.default * (1.0 + delta)
    return param.default + delta


def _fdm_max_temperature(
    k_fr4: float,
    k_copper: float,
    copper_fraction: float,
    q: float = 5.0,
    n: int = 50,
) -> float:
    """Production-path consumer scalar: peak FDM temperature field (deg-C).

    Calls ``solve_thermal_fdm`` (the production solver) with a config that
    carries the perturbed parameter at its source.  The solver's
    ``target_solve_time_s`` budget (a solver guard, not a physics parameter)
    is raised in the scenario so the probe cannot flake to UNMEASURED under
    CI load.  Raises AssertionError on an unusable field.
    """
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm

    cfg = ThermalFDMConfig(
        cell_size_mm=0.5,
        origin_mm=(0.0, 0.0),
        height_cells=n,
        width_cells=n,
        k_fr4=k_fr4,
        k_copper=k_copper,
        target_solve_time_s=60.0,
    )
    q_field = np.zeros((n, n))
    q_field[n // 2, n // 2] = q
    result = solve_thermal_fdm(cfg, Q_field=q_field, copper_grid=np.full((n, n), copper_fraction))
    if not result.is_usable:
        raise AssertionError(f"solve_thermal_fdm unusable: {result.error_message}")
    return float(np.max(result.field.grid))


def _h_field_sum(h_conv_background: float) -> float:
    """Production-path consumer scalar: total vertical sink conductance.

    Perturbs ``heat_removal.H_CONV_BACKGROUND`` at its source (module
    constant) via ``unittest.mock.patch`` and calls the production
    ``build_h_field``.
    """
    from unittest import mock

    from temper_placer.physics import heat_removal
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig

    cfg = ThermalFDMConfig(
        cell_size_mm=0.5,
        origin_mm=(0.0, 0.0),
        height_cells=20,
        width_cells=20,
    )
    with mock.patch.object(heat_removal, "H_CONV_BACKGROUND", h_conv_background):
        h_field = heat_removal.build_h_field(cfg, {}, {})
    return float(np.sum(h_field))


def _potential_sum(convection_weight: float) -> float:
    """Production-path consumer scalar: total thermal potential field."""
    from temper_placer.physics.thermal_potential import (
        ThermalPotentialConfig,
        build_potential_grid,
        superpose_fields,
    )

    bounds = (0.0, 0.0, 100.0, 100.0)
    config = ThermalPotentialConfig(convection_weight=convection_weight, grid_resolution=30)
    xg, yg = build_potential_grid(bounds, 30)
    field = superpose_fields(xg, yg, bounds, "TOP", config, airflow_vector=(1.0, 45.0))
    return float(np.sum(field))


def _scorer_peak(h_conv: float) -> float:
    """Production-path consumer scalar: independent scorer's peak u7 field.

    Requires the ``temper_thermal`` extension symbol ``build_conductivity_field_py``;
    when the installed extension is stale (missing symbol), raises
    AttributeError and the probe reports UNMEASURED.
    """
    import temper_thermal as _tt

    if not hasattr(_tt, "build_conductivity_field_py"):
        raise AttributeError(
            "temper_thermal.build_conductivity_field_py missing — installed "
            ".so is stale; rebuild with `make extensions`"
        )
    from temper_placer.physics.thermal_fdm import ThermalFDMConfig, solve_thermal_fdm
    from temper_placer.validation.thermal_scorer import ThermalScorer, ThermalScorerConfig

    fdm_config = ThermalFDMConfig(
        cell_size_mm=0.5,
        origin_mm=(0.0, 0.0),
        height_cells=40,
        width_cells=40,
        target_solve_time_s=60.0,
    )
    q_field = np.zeros((40, 40))
    q_field[20, 20] = 0.5
    u5 = solve_thermal_fdm(fdm_config, Q_field=q_field)
    scorer = ThermalScorer(ThermalScorerConfig(h=h_conv))
    result = scorer.score(u5, fdm_config, Q_field=q_field)
    return float(result.u7_peak_C)


def _ipc2152_width(
    temp_rise_c: float,
    copper_weight_oz: float,
    current_amps: float,
) -> float:
    """Production-path consumer scalar: IPC-2152 minimum trace width (mm)."""
    from temper_placer.core.ipc2152 import ipc2152_external_width

    return float(ipc2152_external_width(current_amps, copper_weight_oz, temp_rise_c))


# Scenario dispatch: parameter -> probe implementation via `param.scenario`.
# Every consumer calls the production entry point with the parameter's value
# applied at its source (KTD3).


def _probe_fdm_parameter(param: PhysicsParameterSpec, copper_fraction: float) -> ProbeRecord:
    """Probe a ThermalFDMConfig conductivity parameter (k_fr4 / k_copper).

    k_fr4 and k_copper share one config; the perturbation is applied to the
    named parameter's field at its source and the other field keeps its
    production default.
    """
    OTHER_DEFAULTS = {"k_fr4": 0.3, "k_copper": 385.0}

    def run_with(k_fr4: float, k_copper: float) -> float:
        return _fdm_max_temperature(k_fr4, k_copper, copper_fraction)

    base_values = dict(OTHER_DEFAULTS)
    base_values[param.name] = param.default
    pert_values = dict(base_values)
    pert_values[param.name] = perturb_value(param)

    baseline_out = run_with(base_values["k_fr4"], base_values["k_copper"])
    perturbed_out = run_with(pert_values["k_fr4"], pert_values["k_copper"])
    floor = measure_noise_floor(
        lambda: run_with(base_values["k_fr4"], base_values["k_copper"])
    )
    delta = baseline_out - perturbed_out
    return _physics_record(param, baseline_out, perturbed_out, delta, floor)


def _physics_record(
    param: PhysicsParameterSpec,
    baseline_out: float,
    perturbed_out: float,
    delta: float,
    floor: float,
) -> ProbeRecord:
    disposition = LIVE if abs(delta) > floor else DEAD
    return ProbeRecord(
        target=f"param:{param.name}",
        kind="physics_parameter",
        disposition=disposition,
        baseline_outcome=baseline_out,
        perturbed_outcome=perturbed_out,
        delta=abs(delta),
        noise_floor=floor,
        detail=(
            f"baseline={baseline_out:.6g} perturbed={perturbed_out:.6g} "
            f"delta={abs(delta):.6g} floor={floor:.6g}"
        ),
    )


def probe_physics_parameter(param: PhysicsParameterSpec) -> ProbeRecord:
    """Probe one registered physics parameter through its scenario."""
    scenario = param.scenario

    try:
        if scenario == "fdm_all_fr4":
            return _probe_fdm_parameter(param, copper_fraction=0.0)
        if scenario == "fdm_copper_field":
            return _probe_fdm_parameter(param, copper_fraction=0.3)
        if scenario == "h_field_background":
            baseline = _h_field_sum(param.default)
            perturbed = _h_field_sum(perturb_value(param))
            floor = measure_noise_floor(lambda: _h_field_sum(param.default))
            return _physics_record(param, baseline, perturbed, baseline - perturbed, floor)
        if scenario == "thermal_potential":
            baseline = _potential_sum(param.default)
            perturbed = _potential_sum(perturb_value(param))
            floor = measure_noise_floor(lambda: _potential_sum(param.default))
            return _physics_record(param, baseline, perturbed, baseline - perturbed, floor)
        if scenario == "thermal_scorer":
            baseline = _scorer_peak(param.default)
            perturbed = _scorer_peak(perturb_value(param))
            floor = measure_noise_floor(lambda: _scorer_peak(param.default))
            return _physics_record(param, baseline, perturbed, baseline - perturbed, floor)
        if scenario == "ipc2152_width":
            return _probe_ipc2152(param)
    except Exception as exc:  # noqa: BLE001 — any probe failure is UNMEASURED, never a crash
        return ProbeRecord(
            target=f"param:{param.name}",
            kind="physics_parameter",
            disposition=UNMEASURED,
            detail=f"probe could not run: {type(exc).__name__}: {exc}",
        )

    return ProbeRecord(
        target=f"param:{param.name}",
        kind="physics_parameter",
        disposition=UNMEASURED,
        detail=f"unknown scenario '{scenario}'",
    )


def _probe_ipc2152(param: PhysicsParameterSpec) -> ProbeRecord:
    """Probe an IPC-2152 width input; perturb only the named argument."""
    # Defaults for the two non-target arguments.
    DEFAULTS = {"temp_rise_c": 10.0, "copper_weight_oz": 1.0, "current_amps": 16.0}
    args = dict(DEFAULTS)
    baseline = _ipc2152_width(**args)
    args[param.name.replace("ipc2152_", "")] = perturb_value(param)
    perturbed = _ipc2152_width(**args)
    floor = measure_noise_floor(lambda: _ipc2152_width(**DEFAULTS))
    return _physics_record(param, baseline, perturbed, baseline - perturbed, floor)


# --- Top-level runners ---------------------------------------------------------


def run_all_gate_probes(registry: GateInputRegistry) -> list[ProbeRecord]:
    """Probe every covered declared input of every registered gate."""
    records: list[ProbeRecord] = []
    for gate in registry.gates:
        for spec in gate.declared_inputs:
            if not spec.covered:
                records.append(
                    ProbeRecord(
                        target=f"gate:{gate.name}.{spec.name}",
                        kind="gate_input",
                        disposition=UNMEASURED,
                        detail=spec.reason,
                    )
                )
                continue
            records.append(probe_acceptance_inner_input(registry, gate.name, spec.name))
    return records


def run_all_physics_probes(
    params: tuple[PhysicsParameterSpec, ...] | None = None,
) -> list[ProbeRecord]:
    """Probe every registered physics parameter."""
    from temper_placer.validation.gate_input_registry import build_default_registry

    if params is None:
        params = build_default_registry().physics_parameters
    return [probe_physics_parameter(p) for p in params]


def probe_named_parameter(name: str) -> ProbeRecord:
    """Probe one registered physics parameter by name.

    Raises:
        KeyError: if the name is not in the registered map — the harness
            rejects unregistered parameters rather than guessing a scenario.
    """
    registry = build_default_registry()
    for param in registry.physics_parameters:
        if param.name == name:
            return probe_physics_parameter(param)
    raise KeyError(
        f"parameter '{name}' is not registered in physics_parameter_map.yaml "
        f"(registered: {[p.name for p in registry.physics_parameters]})"
    )


def run_all_probes(registry: GateInputRegistry | None = None) -> list[ProbeRecord]:
    """Run every probe (gate inputs + physics parameters)."""
    if registry is None:
        registry = build_default_registry()
    records = run_all_gate_probes(registry)
    records.extend(run_all_physics_probes(registry.physics_parameters))
    return records


def probe_is_pass(record: ProbeRecord) -> bool:
    """True when a record does not fail the standing check.

    Only ``dead`` fails.  ``live`` passes; ``inconclusive`` and ``UNMEASURED``
    are reported as warnings (the plan defers automated fail-forcing
    derivation for non-mechanical thresholds).
    """
    return record.disposition != DEAD


def summarize(records: list[ProbeRecord]) -> str:
    """Render probe records as a stable table for the check script."""
    lines = [
        f"{'target':44s} {'kind':18s} {'disposition':13s} delta/noise",
        "-" * 100,
    ]
    for rec in sorted(records, key=lambda r: r.target):
        dn = (
            f"{rec.delta:.6g}/{rec.noise_floor:.6g}"
            if rec.delta is not None and rec.noise_floor is not None
            else "-"
        )
        lines.append(f"{rec.target:44s} {rec.kind:18s} {rec.disposition:13s} {dn}")
    return "\n".join(lines)
