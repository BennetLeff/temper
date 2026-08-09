"""Tests for validation.gate_input_registry module."""
import dataclasses

import pytest

from temper_placer.validation.gate_input_registry import (
    CiScriptSpec,
    GateInputRegistry,
    InputSpec,
    PhysicsParameterSpec,
    TrackedFinding,
    resolve_container,
    resolve_dotted,
)


class TestInputSpec:
    """Tests for InputSpec."""

    def test_create_valid(self):
        spec = InputSpec(
            name="positions_mm",
            container="temper_placer.placer.cp_sat.audit:Placement",
            field="positions_mm",
            kind="field",
            fail_forcing="set to nan",
            covered=True,
        )
        assert spec.name == "positions_mm"
        assert spec.covered is True

    def test_create_file_input(self):
        spec = InputSpec(
            name="pcb_path",
            container="pathlib:Path",
            field="",
            kind="file",
            covered=False,
            reason="needs real board",
        )
        assert spec.kind == "file"
        assert spec.covered is False

    def test_uncovered_without_reason_raises(self):
        with pytest.raises(ValueError, match="no reason"):
            InputSpec(
                name="x",
                container="m:C",
                field="f",
                covered=False,
            )


class TestCiScriptSpec:
    """Tests for CiScriptSpec."""

    def test_create(self):
        spec = CiScriptSpec(
            script="scripts/check_drc.py",
            declared_input="pcb/temper.kicad_pcb",
            reason="probe disabled",
        )
        assert spec.script == "scripts/check_drc.py"
        assert spec.declared_input == "pcb/temper.kicad_pcb"

    def test_defaults(self):
        spec = CiScriptSpec(script="scripts/foo.py")
        assert spec.declared_input == ""
        assert spec.reason == ""


class TestTrackedFinding:
    """Tests for TrackedFinding."""

    def test_create(self):
        f = TrackedFinding(
            id="R37",
            title="Phantom required metrics",
            status="open",
            remediation_unit="U5",
        )
        assert f.id == "R37"
        assert f.status == "open"


class TestPhysicsParameterSpec:
    """Tests for PhysicsParameterSpec."""

    def test_create(self):
        spec = PhysicsParameterSpec(
            name="k_copper",
            source="temper_placer.physics.thermal_fdm:ThermalFDMConfig.k_copper",
            default=385.0,
            perturbation={"mode": "relative", "delta": 0.1},
            scenario="conductivity_sweep",
            consumers=("thermal_fdm.solve_thermal_fdm",),
        )
        assert spec.name == "k_copper"
        assert spec.default == 385.0
        assert len(spec.consumers) == 1


class TestGateInputRegistry:
    """Tests for GateInputRegistry."""

    def test_empty_registry(self):
        reg = GateInputRegistry()
        assert reg.gates == ()
        assert reg.ci_scripts == ()
        assert reg.tracked_findings == ()

    def test_with_entries(self):
        finding = TrackedFinding(id="R1", title="test", status="open", remediation_unit="U1")
        reg = GateInputRegistry(tracked_findings=(finding,))
        assert len(reg.tracked_findings) == 1


class TestResolveContainer:
    """Tests for resolve_container."""

    def test_resolve_dataclasses_module(self):
        """Resolve a well-known container: dataclasses."""
        cls = resolve_container("dataclasses:Field")
        assert cls is dataclasses.Field

    def test_resolve_bad_module(self):
        with pytest.raises(ImportError):
            resolve_container("nonexistent.module:Foo")

    def test_resolve_bad_class(self):
        with pytest.raises(AttributeError):
            resolve_container("dataclasses:NonExistentClass")

    def test_resolve_no_colon(self):
        with pytest.raises(ValueError, match="no ':' separator"):
            resolve_container("no_colon")


class TestResolveDotted:
    """Tests for resolve_dotted."""

    def test_single_level(self):
        module = dataclasses
        result = resolve_dotted(module, "Field")
        assert result is dataclasses.Field

    def test_multi_level(self):
        class A:
            class B:
                x = 42
        result = resolve_dotted(A, "B.x")
        assert result == 42

    def test_attribute_error(self):
        with pytest.raises(AttributeError):
            resolve_dotted(dataclasses, "Field.NonExistent")


class TestPhysicsMapPath:
    """Tests for physics_map_path."""

    def test_path_ends_with_correct_file(self):
        from temper_placer.validation.gate_input_registry import physics_map_path
        p = physics_map_path()
        assert p.name == "physics_parameter_map.yaml"


class TestValidateDeclaredInputs:
    """Tests for validate_declared_inputs."""

    def test_empty_registry(self):
        from temper_placer.validation.gate_input_registry import validate_declared_inputs
        reg = GateInputRegistry()
        errors = validate_declared_inputs(reg)
        assert errors == []


class TestRepoRoot:
    """Smoke test for _repo_root."""

    def test_returns_path(self):
        from temper_placer.validation.gate_input_registry import _repo_root
        root = _repo_root()
        assert root.is_dir()
        assert (root / "power_pcb_dataset").is_dir()
