"""Contract checks for the ISO7741 candidate-only construction.

These checks intentionally keep the candidate's unresolved component facts
red/pending.  They do not turn datasheet context into an electrical approval.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT / "elec/qualification/iso7741_gate_drive"
GENERATED = ROOT / "power_pcb_dataset/qualification/iso7741_gate_drive/generated"


def test_candidate_isolated_from_production_sources() -> None:
    for source in (CANDIDATE / "src").glob("*.ato"):
        text = source.read_text(encoding="utf-8")
        source_lines = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        assert "elec/src" not in source_lines
        assert "pcb/temper" not in source_lines
    assert (CANDIDATE / "ato.yaml").is_file()


def test_component_facts_are_explicitly_pending() -> None:
    facts = json.loads(
        (CANDIDATE / "validation/component_facts.json").read_text(encoding="utf-8")
    )
    assert facts["status"] == "pending"
    assert facts["facts"]["ISO7741FQDWWRQ1"]["pin_map_status"] == "pending"
    assert facts["facts"]["UCC27517AQDBVRQ1"]["uvlo_status"].startswith("pending")
    assert len(facts["blocking_reasons"]) >= 3


def test_candidate_bom_has_exact_two_domain_architecture() -> None:
    expected = {
        "ISO7741FQDWWRQ1": 2,
        "UCC27517AQDBVRQ1": 2,
        "TPS7B6933QDBVRQ1": 2,
        "TLV1701QDBVRQ1": 2,
        "TLV431BQDBZRQ1": 2,
        "SN74LVC1G08QDBVRQ1": 4,
        "SN74LVC1G04QDBVRQ1": 2,
    }
    bom = CANDIDATE / "build/default.csv"
    assert bom.is_file(), "run the candidate-local Atopile build first"
    counts: dict[str, int] = {}
    with bom.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            refs = [ref for ref in row["Designator"].split(",") if ref]
            counts[row["Comment"]] = len(refs)
    for part, quantity in expected.items():
        assert counts.get(part) == quantity


def test_every_candidate_package_pin_is_explicitly_connected_or_tied_off() -> None:
    source = (CANDIDATE / "src/modules.ato").read_text(encoding="utf-8")
    for pin in range(1, 17):
        assert re.search(rf"barrier\.p{pin} ~", source)
    for pin in range(1, 6):
        assert re.search(rf"driver\.p{pin} ~", source)
    assert "high_side.local_gnd ~ hs_gnd" in source
    assert "low_side.local_gnd ~ ls_gnd" in source
    assert "high_side.switch_return ~ hs_switch_return" in source
    assert "low_side.switch_return ~ ls_switch_return" in source
    assert "high_side.switch_return ~ hv_minus" not in source
    assert "low_side.switch_return ~ hv_minus" not in source


def test_reviewed_candidate_footprints_have_declared_pad_counts() -> None:
    footprints = {
        "ISO7741_DWW16.kicad_mod": 16,
        "Package_DBV5.kicad_mod": 5,
        "Package_DBZ3.kicad_mod": 3,
    }
    footprint_root = CANDIDATE / "footprints/temper_iso7741_gate_drive.pretty"
    for filename, expected_pads in footprints.items():
        text = (footprint_root / filename).read_text(encoding="utf-8")
        assert len(re.findall(r"\(pad \"[0-9]+\"", text)) == expected_pads
        assert "pending authority review" in text


def test_generated_netlist_keeps_high_low_domain_identity() -> None:
    netlist = (CANDIDATE / "build/default.net").read_text(encoding="utf-8")
    assert netlist.count('(libsource (lib "lib") (part "ISO7741FQDWWRQ1")') == 2
    assert "candidate.high_side.barrier" in netlist
    assert "candidate.low_side.barrier" in netlist
    assert "candidate.high_side.driver" in netlist
    assert "candidate.low_side.driver" in netlist
    assert "hs_switch_return" in netlist
    assert "ls_switch_return" in netlist


def test_canonical_exports_exist_and_candidate_stays_stopped_indeterminate() -> None:
    contract = json.loads(
        (CANDIDATE / "validation/candidate_contract.json").read_text(encoding="utf-8")
    )
    assert contract["status"] == "stopped-indeterminate"
    assert contract["fail_closed"]["uvlo_not_12v_13v"] == "reject"
    assert (GENERATED / "iso7741_gate_drive.kicad_sch").is_file()
    assert (GENERATED / "iso7741_gate_drive_stage.kicad_sch").is_file()
