"""Tests for the fail-closed split-board contract gate."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_split_board_contract import (  # noqa: E402
    EXIT_GATE_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    GateError,
    assert_generation_ready,
    load_contract,
    run,
    validate_contract,
)

VALID_INCOMPLETE = """
schema_version: 1
architecture: split_power_control
status: contract-incomplete
generation:
  enabled: false
  blocking_requirements: [connector, enclosure]
boards:
  power:
    id: POWER_BOARD
    owner: power
    required_domains: [HV, SELV]
    artifacts: {pcb: null, netlist: null}
    source: {entrypoint: null}
    checks:
      drc: {required: true, report: null}
      provenance: {required: true, record: null}
  control:
    id: CONTROL_BOARD
    owner: control
    required_domains: [SELV]
    artifacts: {pcb: null, netlist: null}
    source: {entrypoint: null}
    checks:
      drc: {required: true, report: null}
      provenance: {required: true, record: null}
interface:
  name: POWER_CONTROL_SELV_INTERFACE
  domain_manifest: domain_manifest.yaml
  connector_ref: J_POWER_CONTROL
  allowed_domains: [SELV]
  nets: [gnd, "+15V"]
contract:
  connector: {status: incomplete, evidence: null}
  enclosure: {status: incomplete, evidence: null}
cross_domain:
  pollution_degree: 3
  reinforced_creepage_mm: 12.6
  method: ../scripts/measure_cross_domain_creepage.py
  report: null
"""


def write_contract(tmp_path: Path, text: str = VALID_INCOMPLETE) -> Path:
    path = tmp_path / "split_board_manifest.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_real_contract_is_explicitly_blocked_until_reviews_complete():
    path = Path(__file__).resolve().parents[2] / "elec" / "split_board_manifest.yaml"

    errors = validate_contract(path)

    assert any("connector contract is not complete" in error for error in errors)
    assert any("enclosure contract is not complete" in error for error in errors)
    assert any("generation is disabled" in error for error in errors)
    assert run(path) == EXIT_VIOLATION


def test_incomplete_contract_has_a_valid_schema_but_is_not_generation_ready(tmp_path):
    path = write_contract(tmp_path)

    loaded = load_contract(path)

    assert loaded["architecture"] == "split_power_control"
    with pytest.raises(GateError, match="not ready"):
        assert_generation_ready(path)


def test_missing_contract_fails_closed(tmp_path):
    path = tmp_path / "missing.yaml"

    assert run(path) == EXIT_GATE_ERROR
    with pytest.raises(GateError, match="not found"):
        load_contract(path)


def test_ready_contract_requires_real_artifacts_and_evidence(tmp_path):
    text = VALID_INCOMPLETE.replace(
        "status: contract-incomplete", "status: ready"
    ).replace(
        "enabled: false", "enabled: true"
    ).replace(
        "status: incomplete", "status: complete"
    )
    path = write_contract(tmp_path, text)

    errors = validate_contract(path)

    assert any("power board PCB artifact" in error for error in errors)
    assert any("control board PCB artifact" in error for error in errors)
    assert any("cross-domain report" in error for error in errors)
    assert run(path) == EXIT_VIOLATION


def test_complete_contract_passes_only_with_matching_evidence(tmp_path):
    text = VALID_INCOMPLETE.replace(
        "status: contract-incomplete", "status: ready"
    ).replace(
        "enabled: false", "enabled: true"
    ).replace(
        "status: incomplete", "status: complete"
    )
    source_manifest = tmp_path / "domain_manifest.yaml"
    source_manifest.write_text(
        """board_interface:
  name: POWER_CONTROL_SELV_INTERFACE
  allowed_domains: [SELV]
  nets: [gnd, "+15V"]
""",
        encoding="utf-8",
    )
    (tmp_path / "measure_cross_domain_creepage.py").write_text(
        "# synthetic test method\n", encoding="utf-8"
    )
    (tmp_path / "power_board.ato").write_text("# synthetic source\n", encoding="utf-8")
    (tmp_path / "control_board.ato").write_text("# synthetic source\n", encoding="utf-8")
    evidence = tmp_path / "evidence.md"
    evidence.write_text("reviewed", encoding="utf-8")
    report = tmp_path / "drc.json"
    report.write_text(
        json.dumps({"sample_count": 120, "violations_by_type": {}, "warnings_by_type": {}}),
        encoding="utf-8",
    )
    cross_report = tmp_path / "cross.json"
    cross_report.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pollution_degree": 3,
                "required_creepage_mm": 12.6,
                "minimum_creepage_mm": 12.6,
                "boards": ["POWER_BOARD", "CONTROL_BOARD"],
                "violations": [],
            }
        ),
        encoding="utf-8",
    )
    for role in ("power", "control"):
        board = tmp_path / f"{role}.kicad_pcb"
        netlist = tmp_path / f"{role}.net"
        board.write_text(f"{role} board", encoding="utf-8")
        netlist.write_text(f"{role} netlist", encoding="utf-8")
        digest = hashlib.sha256(board.read_bytes()).hexdigest()
        provenance = tmp_path / f"{role}-provenance.json"
        provenance.write_text(
            json.dumps(
                {
                    "source": "measured-live",
                    "dirty": False,
                    "measured_at_commit": "a" * 40,
                    "kicad_cli_version": "10.0.5",
                    "inputs": [{"path": board.name, "sha256": digest}],
                }
            ),
            encoding="utf-8",
        )
    text = text.replace(
        "artifacts: {pcb: null, netlist: null}",
        "artifacts: {pcb: power.kicad_pcb, netlist: power.net}",
        1,
    ).replace(
        "artifacts: {pcb: null, netlist: null}",
        "artifacts: {pcb: control.kicad_pcb, netlist: control.net}",
        1,
    ).replace(
        "source: {entrypoint: null}",
        "source: {entrypoint: power_board.ato}",
        1,
    ).replace(
        "source: {entrypoint: null}",
        "source: {entrypoint: control_board.ato}",
        1,
    ).replace(
        "drc: {required: true, report: null}",
        "drc: {required: true, report: drc.json}",
    ).replace(
        "provenance: {required: true, record: null}",
        "provenance: {required: true, record: power-provenance.json}",
        1,
    ).replace(
        "provenance: {required: true, record: null}",
        "provenance: {required: true, record: control-provenance.json}",
        1,
    ).replace(
        "evidence: null", "evidence: evidence.md"
    ).replace(
        "  report: null", "  report: cross.json"
    ).replace(
        "method: ../scripts/measure_cross_domain_creepage.py",
        "method: measure_cross_domain_creepage.py",
    )
    complete_path = write_contract(tmp_path, text)

    assert validate_contract(complete_path) == []
    assert run(complete_path) == EXIT_OK
    assert_generation_ready(complete_path)


def test_invalid_target_cannot_be_rounded_down_to_pd2(tmp_path):
    path = write_contract(tmp_path, VALID_INCOMPLETE.replace("12.6", "8.0"))

    with pytest.raises(GateError, match="12.6 mm"):
        validate_contract(path)
