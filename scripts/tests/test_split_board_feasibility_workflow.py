"""Contract tests for the split-board feasibility CI wiring."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "python-tests.yml"


def _board_job() -> dict[str, object]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["board-provenance-requirements-gates"]


def _workflow_triggers() -> dict[str, object]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML's YAML 1.1 resolver reads the unquoted GitHub key ``on`` as True.
    return document.get("on", document.get(True, {}))


def _steps_by_name() -> dict[str, dict[str, object]]:
    steps = _board_job()["steps"]
    return {step["name"]: step for step in steps if "name" in step}


def _step_index(name: str) -> int:
    steps = _board_job()["steps"]
    return next(index for index, step in enumerate(steps) if step.get("name") == name)


def test_split_board_replay_is_exactly_wired_before_netlist() -> None:
    steps = _steps_by_name()
    setup_name = "Setup barrier -- split-board replay environment ready"
    wiring_name = "Split-board feasibility workflow wiring tests"
    replay_name = "Split-board feasibility admission replay gate"

    assert setup_name in steps
    assert wiring_name in steps
    assert replay_name in steps

    wiring = steps[wiring_name]
    replay = steps[replay_name]
    expected_wiring_command = (
        "uv run --no-sync pytest scripts/tests/test_split_board_feasibility_workflow.py "
        "-v --tb=short"
    )
    expected_replay_command = "uv run --no-sync python scripts/check_split_board_feasibility.py"
    expected_gate_if = (
        "${{ !cancelled() && steps.setup_split_board.outcome == 'success' }}"
    )

    assert wiring["run"] == expected_wiring_command
    assert replay["run"] == expected_replay_command
    assert wiring.get("working-directory", ".") == "."
    assert replay.get("working-directory", ".") == "."
    assert not wiring.get("continue-on-error", False)
    assert not replay.get("continue-on-error", False)
    assert wiring["if"] == expected_gate_if
    assert replay["if"] == expected_gate_if

    setup_index = _step_index(setup_name)
    wiring_index = _step_index(wiring_name)
    replay_index = _step_index(replay_name)
    cache_index = _step_index("Cache netlist")
    build_index = _step_index("Build electronics netlist")
    assert setup_index < wiring_index < replay_index < cache_index < build_index


def test_split_board_qualification_changes_trigger_both_events() -> None:
    triggers = _workflow_triggers()
    qualification_path = "power_pcb_dataset/qualification/**"
    assert qualification_path in triggers["push"]["paths"]
    assert qualification_path in triggers["pull_request"]["paths"]


def test_split_board_failure_does_not_bypass_pre_netlist_setup() -> None:
    steps = _steps_by_name()
    setup = steps["Setup barrier -- split-board replay environment ready"]
    expected_setup_if = (
        "${{ !cancelled() && steps.setup_split_board.outcome == 'success' }}"
    )

    assert setup["id"] == "setup_split_board"
    assert setup["run"] == "echo \"extensions and dependencies ready for split-board replay\""
    assert "if" not in setup
    assert not setup.get("continue-on-error", False)

    cache = steps["Cache netlist"]
    build = steps["Build electronics netlist"]
    assert cache["if"] == expected_setup_if
    assert build["id"] == "build-netlist"
    assert build["if"] == (
        "${{ !cancelled() && steps.setup_split_board.outcome == 'success' "
        "&& steps.cache-netlist.outcome == 'success' "
        "&& steps.cache-netlist.outputs.cache-hit != 'true' }}"
    )
    assert not cache.get("continue-on-error", False)
    assert not build.get("continue-on-error", False)

    main_setup = steps["Setup barrier -- environment ready"]
    assert main_setup["id"] == "setup"
    # The condition deliberately omits replay outcomes, so a failed replay can
    # still reach this barrier after cache/build setup succeeds. It requires
    # either a successful cache hit (with a skipped build) or a successful
    # actual netlist build, so a real netlist failure cannot open the gate.
    assert main_setup["if"] == (
        "${{ !cancelled() && steps.setup_split_board.outcome == 'success' "
        "&& steps.cache-netlist.outcome == 'success' "
        "&& (steps.cache-netlist.outputs.cache-hit == 'true' || "
        "steps.build-netlist.outcome == 'success') }}"
    )
    assert not main_setup.get("continue-on-error", False)
