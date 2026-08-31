"""Tests for the fail-closed split-board contract gate."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_split_board_contract import (  # noqa: E402
    EXIT_BLOCKED,
    EXIT_GATE_ERROR,
    EXIT_MALFORMED,
    EXIT_OK,
    EXIT_VIOLATION,
    GateError,
    _check_atopile_entrypoint,
    _check_distinct_board_artifacts,
    _check_drc_report,
    _check_manifest_location,
    _check_provenance,
    _evidence_digest,
    _load_json,
    _read_artifact,
    assert_generation_ready,
    generate_with_contract,
    load_contract,
    run,
    validate_contract,
)

VALID_INCOMPLETE = """
schema_version: 1
architecture: split_power_control
status: contract-incomplete
fixture_context: unit-test
hierarchy: elec/src/split_board_hierarchy.ato
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
      drc:
        required: true
        report: null
        ceiling_source:
          path: ceiling.json
          board_id: split-fixture
          sha256: null
      provenance: {required: true, record: null}
  control:
    id: CONTROL_BOARD
    owner: control
    required_domains: [SELV]
    artifacts: {pcb: null, netlist: null}
    source: {entrypoint: null}
    checks:
      drc:
        required: true
        report: null
        ceiling_source:
          path: ceiling.json
          board_id: split-fixture
          sha256: null
      provenance: {required: true, record: null}
interface:
  name: POWER_CONTROL_SELV_INTERFACE
  domain_manifest: domain_manifest.yaml
  connector_ref: J_POWER_CONTROL
  allowed_domains: [SELV]
  nets: [gnd, "+15V", "+3V3", PWM_HS, PWM_LS, SHUTDOWN, RELAY_CTRL, DISCHARGE_CTRL, V_BUS_SENSE, I_SENSE]
contract:
  connector: {status: incomplete, evidence: null}
  enclosure: {status: incomplete, evidence: null}
cross_domain:
  pollution_degree: 3
  reinforced_creepage_mm: 12.6
  method: measure_cross_domain_creepage.py
  report: null
"""


def write_contract(tmp_path: Path, text: str = VALID_INCOMPLETE) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    (tmp_path / "domain_manifest.yaml").write_text(
        (repo_root / "elec" / "domain_manifest.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "measure_cross_domain_creepage.py").write_text(
        "# synthetic test method\n", encoding="utf-8"
    )
    hierarchy_dir = tmp_path / "elec" / "src"
    hierarchy_dir.mkdir(parents=True, exist_ok=True)
    (hierarchy_dir / "split_board_hierarchy.ato").write_text(
        (repo_root / "elec" / "src" / "split_board_hierarchy.ato").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
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


def test_fixture_context_is_rejected_for_tracked_production_manifest():
    production = Path(__file__).resolve().parents[2] / "elec" / "split_board_manifest.yaml"

    with pytest.raises(GateError, match="only for manifests outside"):
        _check_manifest_location(production, "unit-test")


def test_nonfinite_json_values_fail_closed(tmp_path):
    path = tmp_path / "nonfinite.json"
    path.write_text('{"minimum_creepage_mm": NaN}\n', encoding="utf-8")

    with pytest.raises(GateError, match="non-finite"):
        _load_json(path, "fixture")


def test_atopile_entrypoint_requires_board_module_shape(tmp_path):
    path = tmp_path / "power.ato"
    path.write_text("# comments are not an entrypoint\n", encoding="utf-8")

    with pytest.raises(GateError, match="no Atopile module"):
        _check_atopile_entrypoint(path, "power source", "power")


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("name", "OTHER_INTERFACE"),
        ("power_board", "OTHER_POWER_BOARD"),
        ("control_board", "OTHER_CONTROL_BOARD"),
        ("connector", "OTHER_CONNECTOR"),
        ("nets", ["gnd"]),
        ("allowed_domains", ["HV"]),
    ],
)
def test_interface_fields_must_match_domain_manifest(tmp_path, field, replacement):
    path = write_contract(tmp_path)
    source_path = tmp_path / "domain_manifest.yaml"
    source_data = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    source_data["board_interface"][field] = replacement
    if field == "nets":
        source_data["board_interface"]["signals"] = [
            source_data["board_interface"]["signals"][0]
        ]
    source_path.write_text(yaml.safe_dump(source_data, sort_keys=False), encoding="utf-8")

    with pytest.raises(GateError):
        validate_contract(path)


def test_atopile_interface_signals_must_match_domain_manifest(tmp_path):
    path = write_contract(tmp_path)
    hierarchy_dir = tmp_path / "elec" / "src"
    hierarchy_dir.mkdir(parents=True, exist_ok=True)
    hierarchy = (
        Path(__file__).resolve().parents[2]
        / "elec"
        / "src"
        / "split_board_hierarchy.ato"
    ).read_text(encoding="utf-8")
    (hierarchy_dir / "split_board_hierarchy.ato").write_text(
        hierarchy.replace("signal i_sense", "signal stale_sense"), encoding="utf-8"
    )

    with pytest.raises(GateError, match="signals do not match"):
        validate_contract(path)


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
    (tmp_path / "power_board.ato").write_text(
        "module PowerBoardBoundary:\n    source = new PowerSource\n",
        encoding="utf-8",
    )
    (tmp_path / "control_board.ato").write_text(
        "module ControlBoardBoundary:\n    source = new ControlSource\n",
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence.json"
    evidence_record = {
        "schema_version": 1,
        "approved": True,
        "source_identity": "review-2026-08-30",
        "engineering_values": {"decision": "approved"},
    }
    evidence_record["content_sha256"] = hashlib.sha256(
        json.dumps(evidence_record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    evidence.write_text(json.dumps(evidence_record), encoding="utf-8")
    board_hashes: dict[str, str] = {}
    provenance_hashes: dict[str, str] = {}
    (tmp_path / "measure_cross_domain_creepage.py").write_text(
        "# synthetic test method\n", encoding="utf-8"
    )
    for role in ("power", "control"):
        board = tmp_path / f"{role}.kicad_pcb"
        netlist = tmp_path / f"{role}.net"
        board.write_text(
            "(kicad_pcb (version 20240108) (generator pcbnew) "
            f"(comment {role}) "
            "(general (thickness 1.6)) "
            "(layers (0 \"F.Cu\" signal) (31 \"B.Cu\" signal)) "
            "(setup (pad_to_mask_clearance 0)))\n",
            encoding="utf-8",
        )
        netlist.write_text(
            f"(export (version \"D\") (components (comp (ref {role[0].upper()}1))) "
            "(nets (net (code 1) (name \"gnd\") "
            f"(node (ref {role[0].upper()}1) (pin \"1\")))))\n",
            encoding="utf-8",
        )
        digest = hashlib.sha256(board.read_bytes()).hexdigest()
        provenance = tmp_path / f"{role}-provenance.json"
        provenance_record = {
            "source": "measured-live",
            "dirty": False,
            "measured_at_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
            "tool_versions": {"kicad-cli": "10.0.5"},
            "inputs": [{"path": board.name, "sha256": digest}],
        }
        provenance_record["content_sha256"] = hashlib.sha256(
            json.dumps(provenance_record, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        provenance.write_text(json.dumps(provenance_record), encoding="utf-8")
        board_hashes[role] = digest
        provenance_hashes[role] = provenance_record["content_sha256"]
    ceiling_record = {
        "schema_version": 1,
        "source_identity": "split-fixture-ceiling",
        "boards": [{
            "board_id": "split-fixture",
            "error_ceiling": 2,
            "warning_ceiling": 0,
            "violations_by_type": {"clearance": 2},
            "warnings_by_type": {},
        }],
    }
    ceiling = tmp_path / "ceiling.json"
    ceiling.write_text(json.dumps(ceiling_record), encoding="utf-8")
    ceiling_sha256 = hashlib.sha256(ceiling.read_bytes()).hexdigest()
    for role in ("power", "control"):
        report_record = {
            "schema_version": 1,
            "approved": True,
            "source_identity": "kicad-cli-10.0.5",
            "pollution_degree": 3,
            "required_creepage_mm": 12.6,
            "engineering_values": {"all_track_errors": True},
            "method_config": {"backend": "kicad-cli", "all_track_errors": True},
            "sample_count": 120,
            "violations_by_type": {"clearance": 1},
            "warnings_by_type": {},
            "pcb_sha256": board_hashes[role],
            "provenance_sha256": provenance_hashes[role],
            "acceptance": {
                "source": "project-drc-ceiling",
                "ceiling_source": "ceiling.json",
                "ceiling_board_id": "split-fixture",
            },
        }
        report_record["content_sha256"] = hashlib.sha256(
            json.dumps(report_record, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        (tmp_path / f"{role}-drc.json").write_text(json.dumps(report_record), encoding="utf-8")
    cross_record = {
        "schema_version": 1,
        "approved": True,
        "source_identity": "cross-domain-campaign-2026-08-30",
        "engineering_values": {"sample_count": 120},
        "pollution_degree": 3,
        "required_creepage_mm": 12.6,
        "minimum_creepage_mm": 12.6,
        "boards": ["POWER_BOARD", "CONTROL_BOARD"],
        "violations": [],
        "method": "measure_cross_domain_creepage.py",
        "method_sha256": hashlib.sha256(
            (tmp_path / "measure_cross_domain_creepage.py").read_bytes()
        ).hexdigest(),
        "configuration": {"pollution_degree": 3, "reinforced_creepage_mm": 12.6},
        "board_inputs": {
            "POWER_BOARD": {"pcb_sha256": board_hashes["power"], "provenance_sha256": provenance_hashes["power"]},
            "CONTROL_BOARD": {"pcb_sha256": board_hashes["control"], "provenance_sha256": provenance_hashes["control"]},
        },
    }
    cross_record["content_sha256"] = hashlib.sha256(
        json.dumps(cross_record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (tmp_path / "cross.json").write_text(json.dumps(cross_record), encoding="utf-8")
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
        "        report: null", "        report: power-drc.json", 1
    ).replace(
        "        report: null", "        report: control-drc.json", 1
    ).replace(
        "      provenance: {required: true, record: null}",
        "      provenance: {required: true, record: power-provenance.json}",
        1,
    ).replace(
        "      provenance: {required: true, record: null}",
        "      provenance: {required: true, record: control-provenance.json}",
        1,
    ).replace(
        "evidence: null", "evidence: evidence.json"
    ).replace(
        "method: ../scripts/measure_cross_domain_creepage.py",
        "method: measure_cross_domain_creepage.py",
    )
    text = text.rsplit("  report: null", 1)[0] + "  report: cross.json\n"
    text = text.replace("sha256: null", f"sha256: {ceiling_sha256}")
    complete_path = write_contract(tmp_path, text)
    source_path = tmp_path / "domain_manifest.yaml"
    source_data = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    source_interface = source_data["board_interface"]
    for signal in source_interface["signals"]:
        if signal["status"] == "unresolved":
            signal["status"] = "resolved"
            if signal["net"] == "+3V3":
                signal["owner"] = "POWER_BOARD"
                signal["direction"] = "POWER_BOARD_TO_CONTROL_BOARD"
            else:
                signal["owner"] = "CONTROL_BOARD"
                signal["direction"] = "CONTROL_BOARD_TO_POWER_BOARD"
    source_interface["fault_aggregation"]["status"] = "resolved"
    source_interface["connector_spec"] = {
        "part_number": "J-APPROVED",
        "pinout": "reviewed-10-net",
        "retention": "locking",
        "single_fault_review": "review-1",
    }
    source_interface["mechanical_spec"] = {
        "enclosure_compartment": "compartment-a",
        "board_partition": "review-2",
        "cable_routing": "review-3",
        "mounting": "review-4",
    }
    source_interface["generation"]["status"] = "ready"
    source_path.write_text(yaml.safe_dump(source_data, sort_keys=False), encoding="utf-8")

    assert validate_contract(complete_path) == []
    assert run(complete_path) == EXIT_OK
    assert_generation_ready(complete_path)

    # A syntactically shaped but dangling commit is not a valid blocked
    # prerequisite; it is malformed provenance and therefore exit 1.
    provenance_path = tmp_path / "power-provenance.json"
    provenance_data = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance_data["measured_at_commit"] = "a" * 40
    provenance_path.write_text(json.dumps(provenance_data), encoding="utf-8")
    assert run(complete_path) == EXIT_MALFORMED


def test_invalid_target_cannot_be_rounded_down_to_pd2(tmp_path):
    path = write_contract(tmp_path, VALID_INCOMPLETE.replace("12.6", "8.0"))

    with pytest.raises(GateError, match="12.6 mm"):
        validate_contract(path)


def test_contract_paths_must_not_escape_repo(tmp_path):
    path = write_contract(
        tmp_path,
        VALID_INCOMPLETE.replace(
            "method: measure_cross_domain_creepage.py",
            "method: ../outside/measure_cross_domain_creepage.py",
        ),
    )

    with pytest.raises(GateError, match="escapes its repository"):
        validate_contract(path)


def test_contract_paths_reject_symlink_escape(tmp_path):
    outside = tmp_path.parent / "split-board-contract-outside.py"
    outside.write_text("# outside\n", encoding="utf-8")
    link = tmp_path / "method-link.py"
    link.symlink_to(outside)
    path = write_contract(
        tmp_path,
        VALID_INCOMPLETE.replace(
            "method: measure_cross_domain_creepage.py",
            "method: method-link.py",
        ),
    )

    with pytest.raises(GateError, match="escapes its repository"):
        validate_contract(path)


def test_blocked_generation_guard_writes_nothing(tmp_path):
    path = write_contract(tmp_path)
    writes: list[str] = []

    with pytest.raises(GateError, match="not ready"):
        generate_with_contract(path, lambda: writes.append("artifact"))

    assert writes == []


def test_blocked_cli_emits_machine_readable_missing_prerequisites(tmp_path, capsys):
    path = write_contract(tmp_path)

    assert run(path) == EXIT_BLOCKED
    payload_line = next(
        line for line in capsys.readouterr().out.splitlines()
        if line.startswith("SPLIT_BOARD_CONTRACT_PAYLOAD=")
    )
    payload = json.loads(payload_line.split("=", 1)[1])
    assert payload["status"] == "blocked"
    assert payload["missing_prerequisites"]


def test_empty_or_malformed_board_artifact_fails_closed(tmp_path):
    empty = tmp_path / "empty.ato"
    empty.write_text("  \n", encoding="utf-8")
    with pytest.raises(GateError, match="empty"):
        _read_artifact(empty, "board source", suffix=".ato")

    malformed = tmp_path / "bad.kicad_pcb"
    malformed.write_text("(kicad_pcb (version 20240108)", encoding="utf-8")
    from check_split_board_contract import _check_sexp_artifact

    with pytest.raises(GateError, match="unbalanced"):
        _check_sexp_artifact(malformed, "board PCB", b"kicad_pcb", ".kicad_pcb")


def test_reused_board_artifact_identity_fails_closed(tmp_path):
    artifact = tmp_path / "same.ato"
    artifact.write_text("same", encoding="utf-8")
    paths = {
        "power": {"source": artifact},
        "control": {"source": artifact},
    }
    hashes = {"power": {"source": "a"}, "control": {"source": "a"}}
    with pytest.raises(GateError, match="distinct"):
        _check_distinct_board_artifacts(paths, hashes)


def test_stale_provenance_is_rejected(tmp_path):
    board = tmp_path / "power.kicad_pcb"
    board.write_text("(kicad_pcb (version 20240108))", encoding="utf-8")
    provenance = {
        "source": "measured-live",
        "dirty": False,
        "measured_at_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "tool_versions": {"kicad-cli": "10.0.5"},
        "inputs": [{"path": board.name, "sha256": "0" * 64}],
    }
    provenance["content_sha256"] = _evidence_digest(provenance)
    record = tmp_path / "provenance.json"
    record.write_text(json.dumps(provenance), encoding="utf-8")
    manifest = tmp_path / "split_board_manifest.yaml"
    manifest.write_text("fixture_context: unit-test\n", encoding="utf-8")
    with pytest.raises(GateError, match="does not match the PCB"):
        _check_provenance(record, board, "POWER_BOARD", manifest)


def test_nonzero_drc_is_allowed_only_within_project_ceiling(tmp_path):
    board = tmp_path / "power.kicad_pcb"
    board.write_text("(kicad_pcb (version 20240108))", encoding="utf-8")
    provenance_record = {
        "source": "measured-live",
        "dirty": False,
        "measured_at_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "tool_versions": {"kicad-cli": "10.0.5"},
        "inputs": [{"path": board.name, "sha256": hashlib.sha256(board.read_bytes()).hexdigest()}],
    }
    provenance_record["content_sha256"] = _evidence_digest(provenance_record)
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps(provenance_record), encoding="utf-8")
    report_record = {
        "schema_version": 1,
        "approved": True,
        "source_identity": "kicad-cli-10.0.5",
        "pollution_degree": 3,
        "required_creepage_mm": 12.6,
        "engineering_values": {"all_track_errors": True},
        "method_config": {"backend": "kicad-cli"},
        "sample_count": 1,
        "violations_by_type": {"clearance": 1},
        "warnings_by_type": {},
        "pcb_sha256": hashlib.sha256(board.read_bytes()).hexdigest(),
        "provenance_sha256": provenance_record["content_sha256"],
        "acceptance": {
            "source": "project-drc-ceiling",
            "ceiling_source": "drc-ceiling.json",
            "ceiling_board_id": "POWER_BOARD",
        },
    }
    report_record["content_sha256"] = _evidence_digest(report_record)
    report = tmp_path / "drc.json"
    report.write_text(json.dumps(report_record), encoding="utf-8")
    manifest = tmp_path / "split_board_manifest.yaml"
    manifest.write_text("fixture_context: unit-test\n", encoding="utf-8")
    limits = {
        "source_ref": "drc-ceiling.json",
        "board_id": "POWER_BOARD",
        "violations_by_type": {"clearance": 1},
        "warnings_by_type": {},
        "error_ceiling": 1,
        "warning_ceiling": 0,
    }
    _check_drc_report(
        report, "POWER_BOARD", board, provenance, provenance_record, manifest, limits
    )
    limits["violations_by_type"]["clearance"] = 0
    report_record["content_sha256"] = _evidence_digest(report_record)
    report.write_text(json.dumps(report_record), encoding="utf-8")
    with pytest.raises(GateError, match="exceeds project ceiling"):
        _check_drc_report(
            report, "POWER_BOARD", board, provenance, provenance_record, manifest, limits
        )
    report_record["acceptance"]["ceilings"] = {
        "violations_by_type": {"clearance": 99},
        "warnings_by_type": {},
    }
    report_record["content_sha256"] = _evidence_digest(report_record)
    report.write_text(json.dumps(report_record), encoding="utf-8")
    with pytest.raises(GateError, match="self-declared ceilings"):
        _check_drc_report(
            report, "POWER_BOARD", board, provenance, provenance_record, manifest, limits
        )
