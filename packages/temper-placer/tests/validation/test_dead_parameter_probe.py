"""Tests for the wire/unwire probe (plan 2026-08-02-019, U2).

Covers:
- happy path: a gate whose verdict flips under fail-forcing passes;
- fail path: a gate whose verdict is unchanged under a fail-forced declared
  metric fails, naming the dead input;
- edge case: a gate already FAIL at baseline is inconclusive, not dead;
- edge case: a metric whose fail-forcing value is not derivable is UNMEASURED;
- physics: perturbing k_fr4 / h_conv / ampacity moves the downstream output;
- source-level perturbation verified by a call-path test; unregistered
  parameters rejected;
- noise floor: stable floor on identical input; delta over floor;
- determinism: repeated measurements reproduce.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from temper_placer.validation.dead_parameter_probe import (
    DEAD,
    INCONCLUSIVE,
    LIVE,
    UNMEASURED,
    measure_noise_floor,
    probe_acceptance_inner_input,
    probe_is_pass,
    probe_named_parameter,
    probe_physics_parameter,
    run_all_gate_probes,
    run_all_physics_probes,
)
from temper_placer.validation.gate_input_registry import (
    GateInputRegistry,
    build_default_registry,
)


@pytest.fixture(scope="module")
def registry():
    return build_default_registry()


# --- U2 scenario 1: happy path — every acceptance-inner input flips -----------


@pytest.mark.parametrize(
    "input_name",
    ["positions_mm", "sizes_mm", "board_w_mm", "board_h_mm", "zones", "zone_components"],
)
def test_acceptance_inner_input_live(registry, input_name):
    rec = probe_acceptance_inner_input(registry, "acceptance_gate.inner", input_name)
    assert rec.disposition == LIVE, rec.detail
    assert rec.baseline_outcome is True
    assert rec.perturbed_outcome is False


def test_run_all_gate_probes_all_live(registry):
    records = run_all_gate_probes(registry)
    gate_records = [r for r in records if r.kind == "gate_input" and "UNMEASURED" not in r.disposition]
    assert gate_records, "expected at least the six covered inner-gate inputs"
    assert all(r.disposition == LIVE for r in gate_records), [
        (r.target, r.disposition, r.detail) for r in gate_records
    ]


# --- U2 scenario 2: fail path — injected dead input -----------------------------


def _dead_gate_registry() -> GateInputRegistry:
    """A registry whose declared input is silently unused by its consumer."""
    real = build_default_registry()

    def consume_ignoring_input(*_args):
        return True  # verdict never depends on the placement

    @dataclass(frozen=True)
    class DeadGate:
        name: str
        kind: str
        module: str
        declared_inputs: tuple
        build_baseline: object
        consume: object
        perturb: dict

    dead_input = real.gates[0].declared_inputs[0]
    return GateInputRegistry(
        gates=(
            DeadGate(
                name="dead_gate",
                kind="container",
                module="temper_placer.placer.cp_sat.gate",
                declared_inputs=(dead_input,),
                build_baseline=real.gates[0].build_baseline,
                consume=consume_ignoring_input,
                perturb=real.gates[0].perturb,
            ),
        ),
        physics_parameters=real.physics_parameters,
    )


def test_dead_input_fails_probe_naming_gate_and_input():
    rec = probe_acceptance_inner_input(_dead_gate_registry(), "dead_gate", "positions_mm")
    assert rec.disposition == DEAD
    assert "dead_gate" in rec.target and "positions_mm" in rec.target
    assert probe_is_pass(rec) is False


# --- U2 scenario 3: gate already FAIL at baseline is inconclusive ---------------


def _already_failing_gate_registry() -> GateInputRegistry:
    real = build_default_registry()

    def consume_always_fail(*_args):
        return False

    @dataclass(frozen=True)
    class FailGate:
        name: str
        kind: str
        module: str
        declared_inputs: tuple
        build_baseline: object
        consume: object
        perturb: dict

    return GateInputRegistry(
        gates=(
            FailGate(
                name="failing_gate",
                kind="container",
                module="temper_placer.placer.cp_sat.gate",
                declared_inputs=(real.gates[0].declared_inputs[0],),
                build_baseline=real.gates[0].build_baseline,
                consume=consume_always_fail,
                perturb=real.gates[0].perturb,
            ),
        ),
        physics_parameters=real.physics_parameters,
    )


def test_already_failing_gate_reported_inconclusive():
    rec = probe_acceptance_inner_input(
        _already_failing_gate_registry(), "failing_gate", "positions_mm"
    )
    assert rec.disposition == INCONCLUSIVE
    assert rec.baseline_outcome is False


# --- U2 scenario 4: no fail-forcing value -> UNMEASURED -------------------------


def test_unmeasurable_input_reported_not_skipped(registry):
    rec = probe_acceptance_inner_input(registry, "acceptance_gate.inner", "positions_mm")
    assert rec.disposition == LIVE  # covered input is measurable
    # A declared-but-uncovered input is UNMEASURED with a reason.
    rec2 = probe_acceptance_inner_input(registry, "acceptance_gate.inner", "rotations")
    assert rec2.disposition == UNMEASURED
    assert rec2.detail


# --- U2 scenario 5/6: physics parameters through the production path ------------


@pytest.mark.parametrize(
    "param_name",
    ["k_fr4", "k_copper", "H_CONV_BACKGROUND", "convection_weight", "ipc2152_temp_rise_c",
     "ipc2152_copper_weight_oz", "ipc2152_current_amps"],
)
def test_physics_parameter_live(registry, param_name):
    param = next(p for p in registry.physics_parameters if p.name == param_name)
    rec = probe_physics_parameter(param)
    assert rec.disposition == LIVE, f"{param_name}: {rec.detail}"
    assert rec.delta is not None and rec.noise_floor is not None
    assert rec.delta > rec.noise_floor


def test_h_conv_live_or_unmeasured_stale_extension(registry):
    """h_conv needs the thermal_scorer, which needs a fresh temper_thermal
    extension.  In CI the extension is rebuilt so the probe must be LIVE; in
    the shared dev venv a stale .so makes it UNMEASURED (never a crash)."""
    param = next(p for p in registry.physics_parameters if p.name == "h_conv")
    rec = probe_physics_parameter(param)
    if rec.disposition == LIVE:
        assert rec.delta > rec.noise_floor
    else:
        assert rec.disposition == UNMEASURED
        assert "temper_thermal" in rec.detail or "scorer" in rec.detail


def test_unregistered_parameter_rejected():
    with pytest.raises(KeyError):
        probe_named_parameter("ghost_param")


def test_call_path_perturbation_at_source(monkeypatch):
    """The perturbed parameter must reach the production function at its
    source — verified by spying on solve_thermal_fdm's config argument."""
    import temper_placer.physics.thermal_fdm as tfm

    captured_k_fr4: list[float] = []

    def spy(config, **kwargs):
        captured_k_fr4.append(config.k_fr4)
        from temper_placer.fields.field import CostField
        from temper_placer.fields.result import FieldResult
        from temper_placer.placer.cp_sat.gates import GateResult, GateStatus

        return FieldResult(
            gate_result=GateResult(status=GateStatus.CLEAN),
            field=CostField(
                grid=np.zeros((config.height_cells, config.width_cells)),
                cell_size_mm=config.cell_size_mm,
                origin_mm=config.origin_mm,
            ),
        )

    monkeypatch.setattr(tfm, "solve_thermal_fdm", spy)
    param = next(p for p in build_default_registry().physics_parameters if p.name == "k_fr4")
    probe_physics_parameter(param)
    # The perturbed value (default * (1 + delta)) must reach the production
    # function at its source config — not a copy.
    assert pytest.approx(param.default * 0.9) in captured_k_fr4


# --- U2 scenario 7/8: noise floor + determinism --------------------------------


def test_noise_floor_stable_for_deterministic_consumer():
    def deterministic_run():
        return 42.0

    floor = measure_noise_floor(deterministic_run, samples=5)
    assert floor == 0.0


def test_noise_floor_measures_spread():
    import itertools

    values = itertools.cycle([1.0, 3.0])
    floor = measure_noise_floor(lambda: next(values), samples=5)
    assert floor == pytest.approx(2.0)


def test_determinism_probe_repeatable(registry):
    param = next(p for p in registry.physics_parameters if p.name == "k_fr4")
    r1 = probe_physics_parameter(param)
    r2 = probe_physics_parameter(param)
    assert r1.delta == r2.delta
    assert r1.baseline_outcome == r2.baseline_outcome


def test_run_all_physics_probes_cover_every_registered_parameter(registry):
    records = run_all_physics_probes(registry.physics_parameters)
    assert {r.target for r in records} == {
        f"param:{p.name}" for p in registry.physics_parameters
    }
    # Every record has a disposition; dead fails the check.
    assert all(r.disposition in (LIVE, UNMEASURED) for r in records), [
        (r.target, r.disposition, r.detail) for r in records
    ]
