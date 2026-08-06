"""Tests for scripts/check_dead_parameter_inputs.py (plan 2026-08-02-019, U3).

Covers:
- integration: a clean run exits 0 with every registered input live;
- fail path: a dead input makes the check exit non-zero, naming the input;
- fail path: an unregistered physics parameter fails the check;
- stability: re-running on unchanged code reproduces the verdict;
- list-registry mode renders the registry and exits 0.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_dead_parameter_inputs.py"
SRC = REPO_ROOT / "packages" / "temper-placer" / "src"


def _load_check_module():
    """Import scripts/check_dead_parameter_inputs.py as a module (not __main__)."""
    spec = importlib.util.spec_from_file_location("check_dead_parameter_inputs", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def check_module(monkeypatch):
    sys.path.insert(0, str(SRC))
    monkeypatch.syspath_prepend(str(SRC))
    return _load_check_module()


def _run_check(*args: str) -> subprocess.CompletedProcess:
    env = {
        "PYTHONPATH": str(SRC),
        "UV_PROJECT_ENVIRONMENT": "/Users/bennet/Desktop/temper/.venv",
    }
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )


# --- U3 scenario 1: integration -------------------------------------------------


def test_clean_run_exits_zero():
    result = _run_check()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: every registered input and parameter is live" in result.stdout


def test_list_registry_mode_exits_zero():
    result = _run_check("--list-registry")
    assert result.returncode == 0
    for marker in (
        "=== Gate inputs ===",
        "acceptance_gate.inner",
        "=== CI gate script survey (U1/U4) ===",
        "=== Tracked findings ===",
        "R37-PHANTOM-REQUIRED-METRICS",
        "=== Physics parameters ===",
        "k_fr4",
    ):
        assert marker in result.stdout, f"missing '{marker}'"


def test_json_mode_outputs_records():
    result = _run_check("--json")
    assert result.returncode == 0
    # The import chain emits a DEBUG line before the JSON payload.
    start = result.stdout.find("[")
    records = json.loads(result.stdout[start:])
    assert isinstance(records, list) and records
    assert all({"target", "disposition", "kind"} <= r.keys() for r in records)


# --- U3 scenario 2: dead input fails, naming the gate and input -----------------


def test_dead_input_makes_check_fail(check_module, monkeypatch):
    from dataclasses import dataclass

    from temper_placer.validation.gate_input_registry import GateInputRegistry

    real_registry = check_module.build_default_registry()

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

    dead_input = real_registry.gates[0].declared_inputs[0]
    dead_registry = GateInputRegistry(
        gates=(
            DeadGate(
                name="dead_gate",
                kind="container",
                module="temper_placer.placer.cp_sat.gate",
                declared_inputs=(dead_input,),
                build_baseline=real_registry.gates[0].build_baseline,
                consume=consume_ignoring_input,
                perturb=real_registry.gates[0].perturb,
            ),
        ),
        physics_parameters=real_registry.physics_parameters,
    )

    import temper_placer.validation.gate_input_registry as gir

    monkeypatch.setattr(gir, "build_default_registry", lambda: dead_registry)
    monkeypatch.setattr(check_module, "build_default_registry", lambda: dead_registry)

    exit_code = check_module._main([])
    assert exit_code != 0
    # The check script prints FAIL lines captured via capsys-equivalent:
    captured = _capture_main(check_module, [])
    assert "dead_gate" in captured
    assert "positions_mm" in captured


def _capture_main(check_module, argv):
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        check_module._main(argv)
    return buf.getvalue()


# --- U3 scenario 3: unregistered physics parameter fails ------------------------


def test_unregistered_parameter_makes_check_fail(check_module, monkeypatch, tmp_path):
    import temper_placer.validation.gate_input_registry as gir

    data = _yaml_load(gir.physics_map_path())
    data["parameters"] = [p for p in data["parameters"] if p["name"] != "k_fr4"]
    reduced = tmp_path / "reduced_physics_parameter_map.yaml"
    reduced.write_text(_yaml_dump(data))
    monkeypatch.setattr(gir, "physics_map_path", lambda: reduced)
    monkeypatch.setattr(check_module, "build_default_registry", gir.build_default_registry)

    captured = _capture_main(check_module, [])
    assert "unregistered physics parameter" in captured


def _yaml_load(path):
    import yaml

    with open(path) as fh:
        return yaml.safe_load(fh)


def _yaml_dump(data):
    import yaml

    return yaml.safe_dump(data)


# --- U3 scenario 4: stability ---------------------------------------------------


def test_repeat_run_reproduces_verdict():
    r1 = _run_check()
    r2 = _run_check()
    assert r1.returncode == r2.returncode == 0
    for marker in ("param:k_fr4", "gate:acceptance_gate.inner.positions_mm"):
        assert marker in r1.stdout and marker in r2.stdout


# --- U3 scenario 5: manifest entry ----------------------------------------------

def test_check_script_has_manifest_entry():
    import yaml

    manifest = yaml.safe_load((REPO_ROOT / "scripts" / "manifest.yaml").read_text())
    entries = {e["path"] for e in manifest["scripts"]}
    assert "check_dead_parameter_inputs.py" in entries
