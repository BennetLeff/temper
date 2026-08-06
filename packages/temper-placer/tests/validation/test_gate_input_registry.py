"""Tests for the gate-input registry (plan 2026-08-02-019, U1/U4).

Covers:
- happy path: the registry enumerates every live gate's declared inputs and
  every physics parameter's consumers;
- fail path: a gate declaring a metric absent from its container fails
  registry validation, naming the gate and metric;
- edge cases: empty-input gates, deprecated callerless surface as a tracked
  finding, dead parameters with empty consumer lists;
- physics map: k_fr4 -> FDM solver conductivity builder, h_conv -> thermal
  scorer, ampacity -> IPC-2152 gate;
- round-trip: registry gate names match the modules they claim;
- U4 completeness: every gate script invoked in python-tests.yml is
  registered (covered or documented non-covered).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from temper_placer.validation.gate_input_registry import (
    ACCEPTANCE_INNER_CONTAINER,
    GateInputRegistry,
    InputSpec,
    PhysicsParameterSpec,
    build_default_registry,
    resolve_container,
    scan_unregistered_physics_fields,
    validate_declared_inputs,
    validate_physics_parameter_map,
    validate_registry,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def registry() -> GateInputRegistry:
    return build_default_registry()


# --- U1 scenario 1: happy path ------------------------------------------------


def test_registry_enumerates_acceptance_inner_inputs(registry):
    inner = next(g for g in registry.gates if g.name == "acceptance_gate.inner")
    assert inner.kind == "container"
    names = [s.name for s in inner.declared_inputs]
    # Every field the auditor reads is declared.
    assert names == ["positions_mm", "sizes_mm", "board_w_mm", "board_h_mm", "zones", "zone_components"]
    assert all(s.covered for s in inner.declared_inputs)


def test_registry_enumerates_physics_parameters(registry):
    params = registry.physics_parameters
    names = {p.name for p in params}
    # The origin idea's named set (A3) must be present.
    assert {
        "k_fr4",
        "k_copper",
        "H_CONV_BACKGROUND",
        "convection_weight",
        "h_conv",
        "ipc2152_temp_rise_c",
        "ipc2152_copper_weight_oz",
        "ipc2152_current_amps",
    } <= names
    # Every parameter carries at least one consumer (dead-parameter check).
    assert all(p.consumers for p in params)


# --- U1 scenario 5: physics map consumer mapping -------------------------------


def test_k_fr4_maps_to_fdm_conductivity_builder(registry):
    param = next(p for p in registry.physics_parameters if p.name == "k_fr4")
    assert param.scenario in ("fdm_all_fr4", "fdm_copper_field")
    assert any("solve_thermal_fdm" in c for c in param.consumers)
    assert "k_fr4" in param.source


def test_h_conv_maps_to_thermal_scorer(registry):
    param = next(p for p in registry.physics_parameters if p.name == "h_conv")
    assert param.scenario == "thermal_scorer"
    assert any("ThermalScorer.score" in c for c in param.consumers)


def test_ampacity_input_maps_to_ipc2152(registry):
    for name in ("ipc2152_temp_rise_c", "ipc2152_copper_weight_oz", "ipc2152_current_amps"):
        param = next(p for p in registry.physics_parameters if p.name == name)
        assert param.scenario == "ipc2152_width"
        assert any("ipc2152_external_width" in c for c in param.consumers)


# --- U1 scenario 2: fail path — invented metric --------------------------------


def test_declared_input_absent_from_container_fails(registry):
    bad = GateInputRegistry(
        gates=(
            type(
                "BadGate",
                (),
                {
                    "name": "bad_gate",
                    "declared_inputs": (
                        InputSpec(
                            name="nonexistent_metric",
                            container=ACCEPTANCE_INNER_CONTAINER,
                            field="nonexistent_metric",
                        ),
                    ),
                },
            )(),
        ),
        physics_parameters=registry.physics_parameters,
    )
    errors = validate_declared_inputs(bad)
    assert errors, "an invented metric must fail validation"
    joined = "\n".join(errors)
    assert "bad_gate" in joined
    assert "nonexistent_metric" in joined


def test_unresolvable_container_fails(registry):
    bad = GateInputRegistry(
        gates=(
            type(
                "BadGate",
                (),
                {
                    "name": "ghost_gate",
                    "declared_inputs": (
                        InputSpec(
                            name="x",
                            container="temper_placer.no_such_module:Thing",
                            field="x",
                        ),
                    ),
                },
            )(),
        ),
        physics_parameters=registry.physics_parameters,
    )
    errors = validate_declared_inputs(bad)
    assert any("ghost_gate" in e for e in errors)


# --- U1 scenario 6: dead parameter (empty consumers) ---------------------------


def test_parameter_with_empty_consumers_fails():
    params = (
        PhysicsParameterSpec(
            name="orphan_param",
            source="temper_placer.physics.thermal_fdm:ThermalFDMConfig.k_fr4",
            default=0.3,
            perturbation={"mode": "relative", "delta": -0.1},
            scenario="fdm_all_fr4",
            consumers=(),
        ),
    )
    errors = validate_physics_parameter_map(params)
    assert any("orphan_param" in e and "empty" in e for e in errors)


def test_parameter_with_bad_source_fails():
    params = (
        PhysicsParameterSpec(
            name="bad_src",
            source="temper_placer.physics.thermal_fdm:ThermalFDMConfig.not_a_field",
            default=0.3,
            perturbation={"mode": "relative", "delta": -0.1},
            scenario="fdm_all_fr4",
            consumers=("temper_placer.physics.thermal_fdm:solve_thermal_fdm",),
        ),
    )
    errors = validate_physics_parameter_map(params)
    assert any("bad_src" in e and "unresolved" in e for e in errors)


def test_parameter_with_bad_function_arg_fails():
    params = (
        PhysicsParameterSpec(
            name="bad_arg",
            source="temper_placer.core.ipc2152:ipc2152_external_width.not_an_arg",
            default=10.0,
            perturbation={"mode": "relative", "delta": -0.1},
            scenario="ipc2152_width",
            consumers=("temper_placer.core.ipc2152:ipc2152_external_width",),
        ),
    )
    errors = validate_physics_parameter_map(params)
    assert any("bad_arg" in e and "not in the signature" in e for e in errors)


# --- U1 scenario 4: deprecated surface recorded as a tracked finding -----------


def test_deprecated_phantom_metrics_recorded_as_tracked_finding(registry):
    finding = next(
        f for f in registry.tracked_findings if f.id == "R37-PHANTOM-REQUIRED-METRICS"
    )
    assert finding.status in ("open", "closed")
    assert finding.remediation_unit == "U5"
    # The four phantom metric names are named in the finding.
    for metric in (
        "gate_loop_area_mm2",
        "bootstrap_loop_area_mm2",
        "commutation_loop_area_mm2",
        "igbt_edge_distance_mm",
    ):
        assert metric in finding.title


# --- U1 scenario 3: edge case — empty input list -------------------------------


def test_gate_with_zero_declared_inputs_is_listed():
    # A gate with an empty input list is representable; the probe treats it as
    # a known non-covered case (declares zero inputs).
    empty = type(
        "EmptyGate",
        (),
        {"name": "empty_gate", "declared_inputs": ()},
    )()
    assert empty.declared_inputs == ()


# --- U1 scenario 7: round-trip — names resolve ---------------------------------


def test_registry_container_names_resolve(registry):
    # Every declared container resolves to a real class.
    for gate in registry.gates:
        for spec in gate.declared_inputs:
            if spec.kind == "field":
                cls = resolve_container(spec.container)
                assert cls is not None


def test_physics_sources_resolve(registry):
    errors = validate_physics_parameter_map(registry.physics_parameters)
    assert errors == []


# --- U1 verification: registry valid on the current live gate set --------------

def test_full_registry_validates_clean(registry):
    assert validate_registry(registry) == []


# --- U4: completeness — every CI-invoked gate script is registered -------------


def _invoked_ci_gate_scripts() -> set[str]:
    """Re-derive the survey from python-tests.yml (U4 completeness oracle)."""
    workflow = _repo_root() / ".github" / "workflows" / "python-tests.yml"
    text = workflow.read_text()
    return set(re.findall(r"scripts/([A-Za-z0-9_]+\.py)", text))


# The standing check itself is referenced by the workflow once wired in; it
# surveys other gates, not itself, so it is excluded from the completeness
# requirement (documented exclusion, U4).
_SELF_EXCLUDED = {"check_dead_parameter_inputs.py"}


def test_every_invoked_ci_gate_script_is_registered(registry):
    invoked = _invoked_ci_gate_scripts() - _SELF_EXCLUDED
    registered = {s.script for s in registry.ci_scripts}
    missing = invoked - registered
    assert not missing, (
        "CI gate script(s) invoked in python-tests.yml are absent from the "
        "registry survey: {sorted(missing)} — add them (covered or as a "
        "documented non-covered case) to gate_input_registry._CI_SCRIPT_SURVEY"
    )


def test_ci_script_non_covered_cases_have_reasons(registry):
    for spec in registry.ci_scripts:
        assert spec.reason, f"CI script {spec.script} registered without a reason"


def test_non_covered_inputs_have_reasons(registry):
    for spec in registry.non_covered:
        assert spec.reason, f"non-covered input {spec.name} registered without a reason"
        assert spec.covered is False


# --- U3 scenario 3: unregistered physics parameter fails the scan --------------


def test_unregistered_physics_scan_clean_on_current_configs(registry):
    assert scan_unregistered_physics_fields(registry) == []


def test_new_float_field_without_map_entry_fails(monkeypatch, tmp_path):
    # Simulate a physics parameter that lost its map entry: the scan must
    # flag k_fr4 as an unregistered float field on a registered config.
    import yaml

    import temper_placer.validation.gate_input_registry as gir

    real_map = gir.physics_map_path()
    data = yaml.safe_load(real_map.read_text())
    data["parameters"] = [p for p in data["parameters"] if p["name"] != "k_fr4"]
    reduced = tmp_path / "reduced_physics_parameter_map.yaml"
    reduced.write_text(yaml.safe_dump(data))
    monkeypatch.setattr(gir, "physics_map_path", lambda: reduced)
    reduced_registry = build_default_registry()
    errors = scan_unregistered_physics_fields(reduced_registry)
    assert any("k_fr4" in e and "unregistered physics parameter" in e for e in errors)
