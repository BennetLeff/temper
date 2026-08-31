"""Tests for check_domain_partition.py.

These deliberately do NOT rely on the real elec/build/default.net or the
real elec/domain_manifest.yaml (those are exercised directly by running the
gate itself, see docs/evidence/2026-07-26-domain-partition-check.md).
Instead every scenario here builds a small, hand-written synthetic netlist
and manifest so each test is a controlled, minimal reproduction of one
specific behavior -- matching the pattern used elsewhere in this repo
(scripts/tests/test_literal_removal_check.py builds synthetic git repos and
diffs rather than exercising the real repository history).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import time  # noqa: E402

from check_domain_partition import (  # noqa: E402
    EXIT_GATE_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    MANDATORY_GENERATION_REQUIRED_FIELDS,
    GateError,
    build_graph,
    check_board_interface_contract,
    check_board_interface_generation_ready,
    check_board_partition_contract,
    check_domain_disjointness,
    check_isolator_integrity,
    check_netlist_freshness,
    connected_components,
    load_manifest,
    parse_netlist,
    resolve_isolator_refs,
    run,
)

# ---------------------------------------------------------------------------
# Netlist / manifest builders
# ---------------------------------------------------------------------------


def make_netlist_text(
    components: list[tuple[str, str]],
    nets: list[tuple[str, list[tuple[str, str]]]],
) -> str:
    """Build minimal, valid KiCad-format netlist text.

    components: [(ref, instance_path), ...]
    nets: [(net_name, [(ref, pin), ...]), ...]  -- code auto-assigned
    """
    comp_blocks = []
    for ref, instance_path in components:
        comp_blocks.append(
            f'    (comp (ref "{ref}")\n'
            f'      (value "?")\n'
            f'      (footprint "Test:Footprint")\n'
            f'      (libsource (lib "lib") (part "TestPart") (description "d"))\n'
            f'      (sheetpath (names "/tmp/x/main.ato:Top::{instance_path}") '
            f'(tstamps "t"))\n'
            f'      (tstamps "t"))\n'
        )
    net_blocks = []
    for i, (name, nodes) in enumerate(nets, start=1):
        node_lines = "".join(
            f'      (node (ref "{ref}") (pin "{pin}") (pintype "stereo"))\n'
            for ref, pin in nodes
        )
        net_blocks.append(f'    (net (code "{i}") (name "{name}")\n{node_lines}    )\n')

    return (
        "(export (version \"E\")\n"
        "  (design (source \"test\") (date \"\") (tool \"test\"))\n"
        "  (components\n" + "".join(comp_blocks) + "  )\n"
        "  (libparts)\n"
        "  (nets\n" + "".join(net_blocks) + "  )\n"
        ")\n"
    )


def write_netlist(tmp_path: Path, components, nets, name: str = "test.net") -> Path:
    p = tmp_path / name
    p.write_text(make_netlist_text(components, nets))
    return p


def write_manifest(tmp_path: Path, text: str, name: str = "manifest.yaml") -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


MINIMAL_ISOLATED_MANIFEST = """
schema_version: 1
domains:
  HV:
    nets: ["ac_l", "hv_return"]
  SELV:
    nets: ["v15", "selv_gnd"]
isolators:
  - instance_path: aux.psu
    component: "Test isolator"
    groups:
      primary: ["1", "2"]
      secondary: ["3", "4"]
"""


SPLIT_BOARD_INTERFACE_MANIFEST = """
schema_version: 1
board_interface:
  name: POWER_CONTROL_SELV_INTERFACE
  power_board: POWER_BOARD
  control_board: CONTROL_BOARD
  connector: J_POWER_CONTROL
  allowed_domains: [SELV]
  nets: [v15, pwm, shutdown]
  safety_target:
    standard: IEC 60335-1
    pollution_degree: 3
    reinforced_creepage_mm: 12.6
  signals:
    - net: v15
      role: supply
      owner: POWER_BOARD
      direction: POWER_BOARD_TO_CONTROL_BOARD
      domain: SELV
      return_net: selv_gnd
      fault_behavior: "loss blocks power-up"
      status: resolved
    - net: pwm
      role: control
      owner: CONTROL_BOARD
      direction: CONTROL_BOARD_TO_POWER_BOARD
      domain: SELV
      return_net: selv_gnd
      fault_behavior: "loss disables power stage"
      status: resolved
    - net: shutdown
      role: fault
      owner: CONTROL_BOARD
      direction: CONTROL_BOARD_TO_POWER_BOARD
      domain: SELV
      return_net: selv_gnd
      fault_behavior: "active fault disables power stage"
      status: resolved
  fault_aggregation:
    output_net: shutdown
    active_level: high
    latched: true
    sources: [OCP_01]
    status: resolved
  connector_spec:
    part_number: null
    pinout: null
    retention: null
    single_fault_review: null
  mechanical_spec:
    enclosure_compartment: null
    board_partition: null
    cable_routing: null
    mounting: null
  generation:
    status: blocked
    required_fields:
      - connector_spec.part_number
      - connector_spec.pinout
      - connector_spec.retention
      - connector_spec.single_fault_review
      - mechanical_spec.enclosure_compartment
      - mechanical_spec.board_partition
      - mechanical_spec.cable_routing
      - mechanical_spec.mounting
domains:
  HV:
    nets: [ac_l, hv_return]
  SELV:
    nets: [v15, pwm, shutdown, selv_gnd]
isolators: []
"""


SPLIT_BOARD_PARTITION_MANIFEST = """
schema_version: 1
board_interface:
  name: POWER_CONTROL_SELV_INTERFACE
  power_board: POWER_BOARD
  control_board: CONTROL_BOARD
  connector: J_POWER_CONTROL
  allowed_domains: [SELV]
  nets: [v15, pwm, shutdown]
  safety_target:
    standard: IEC 60335-1
    pollution_degree: 3
    reinforced_creepage_mm: 12.6
  signals:
    - net: v15
      role: supply
      owner: POWER_BOARD
      direction: POWER_BOARD_TO_CONTROL_BOARD
      domain: SELV
      return_net: selv_gnd
      fault_behavior: "loss blocks power-up"
      status: resolved
    - net: pwm
      role: control
      owner: CONTROL_BOARD
      direction: CONTROL_BOARD_TO_POWER_BOARD
      domain: SELV
      return_net: selv_gnd
      fault_behavior: "loss disables power stage"
      status: resolved
    - net: shutdown
      role: fault
      owner: CONTROL_BOARD
      direction: CONTROL_BOARD_TO_POWER_BOARD
      domain: SELV
      return_net: selv_gnd
      fault_behavior: "active fault disables power stage"
      status: resolved
  fault_aggregation:
    output_net: shutdown
    active_level: high
    latched: true
    sources: [OCP_01]
    status: resolved
  connector_spec:
    part_number: null
    pinout: null
    retention: null
    single_fault_review: null
  mechanical_spec:
    enclosure_compartment: null
    board_partition: null
    cable_routing: null
    mounting: null
  generation:
    status: blocked
    required_fields:
      - connector_spec.part_number
      - connector_spec.pinout
      - connector_spec.retention
      - connector_spec.single_fault_review
      - mechanical_spec.enclosure_compartment
      - mechanical_spec.board_partition
      - mechanical_spec.cable_routing
      - mechanical_spec.mounting
board_partition:
  status: planned
  boards:
    POWER_BOARD:
      domain: HV
      modules: [power_in, hb]
      components: [power_in.r1]
    CONTROL_BOARD:
      domain: SELV
      modules: [mcu, rtd_pan]
      components: [mcu.u1]
  cross_domain_modules: [aux]
  cross_domain_components:
    - instance_path: aux.psu
      module: aux
      sides: {POWER_BOARD: [primary], CONTROL_BOARD: [secondary]}
  isolator_sides:
    - instance_path: aux.psu
      power_board_group: primary
      control_board_group: secondary
domains:
  HV:
    nets: [ac_l, hv_return]
  SELV:
    nets: [v15, pwm, shutdown, selv_gnd]
isolators:
  - instance_path: aux.psu
    component: Test isolator
    groups:
      primary: [1]
      secondary: [2]
"""


def _isolated_topology_nets():
    """A correctly isolated topology: PS1 pins 1/2 (primary=HV) never share
    a net with pins 3/4 (secondary=SELV)."""
    return [
        ("ac_l", [("PS1", "1")]),
        ("hv_return", [("PS1", "2")]),
        ("v15", [("PS1", "3")]),
        ("selv_gnd", [("PS1", "4")]),
    ]


class TestBoardInterfaceContract:
    def test_real_contract_has_ten_nets_and_resolves_current_sense(self):
        manifest = load_manifest(Path(__file__).resolve().parents[2] / "elec" / "domain_manifest.yaml")

        assert manifest.board_interface is not None
        interface = manifest.board_interface
        assert len(interface.nets) == 10
        assert interface.nets[-1] == "I_SENSE"
        current = interface.signals[-1]
        assert current.net == "I_SENSE"
        assert current.owner == "POWER_BOARD"
        assert current.direction == "POWER_BOARD_TO_CONTROL_BOARD"
        assert current.domain == "SELV"
        assert current.return_net == "gnd"
        assert current.status == "resolved"
        assert {entry["name"] for entry in interface.deferred_signals} == {
            "FAN_PWM",
            "FAN_TACH",
        }

    def test_real_contract_has_exact_readiness_set_and_typed_ten_net_records(self):
        manifest = load_manifest(
            Path(__file__).resolve().parents[2] / "elec" / "domain_manifest.yaml"
        )
        interface = manifest.board_interface
        assert interface is not None
        assert {
            "connector_spec.part_number",
            "connector_spec.pinout",
            "connector_spec.retention",
            "connector_spec.single_fault_review",
            "mechanical_spec.enclosure_compartment",
            "mechanical_spec.board_partition",
            "mechanical_spec.cable_routing",
            "mechanical_spec.mounting",
        } == MANDATORY_GENERATION_REQUIRED_FIELDS
        assert len(interface.signals) == 10
        assert {signal.net for signal in interface.signals} == set(interface.nets)
        assert all(signal.domain == "SELV" for signal in interface.signals)
        assert all(signal.return_net == "gnd" for signal in interface.signals)

    def test_signal_return_net_must_be_declared_and_allowed(self, tmp_path):
        text = SPLIT_BOARD_INTERFACE_MANIFEST.replace(
            "return_net: selv_gnd", "return_net: hv_return", 1
        ).replace(
            "  HV:\n    nets: [ac_l, hv_return]",
            "  HV:\n    nets: [ac_l, hv_return]",
        )
        with pytest.raises(GateError, match="outside allowed domains"):
            load_manifest(write_manifest(tmp_path, text))

    def test_signal_role_requires_coherent_owner_and_direction(self, tmp_path):
        text = SPLIT_BOARD_INTERFACE_MANIFEST.replace(
            "      owner: POWER_BOARD\n      direction: POWER_BOARD_TO_CONTROL_BOARD\n",
            "      owner: CONTROL_BOARD\n      direction: CONTROL_BOARD_TO_POWER_BOARD\n",
            1,
        )
        with pytest.raises(GateError, match="incoherent role/owner/direction"):
            load_manifest(write_manifest(tmp_path, text))

    def test_required_fields_are_authoritative_exact_set(self, tmp_path):
        text = SPLIT_BOARD_INTERFACE_MANIFEST.replace(
            "      - mechanical_spec.mounting\n",
            "      - mechanical_spec.mounting\n      - generation.extra\n",
        )
        with pytest.raises(GateError, match="must be exactly the mandatory readiness set"):
            load_manifest(write_manifest(tmp_path, text))

    def test_generation_readiness_fails_closed_on_unresolved_fields(self, tmp_path):
        manifest = load_manifest(
            write_manifest(tmp_path, SPLIT_BOARD_INTERFACE_MANIFEST)
        )

        with pytest.raises(GateError, match="generation blocked"):
            check_board_interface_generation_ready(manifest)

    def test_generation_readiness_rejects_signal_outside_allowed_domain(self, tmp_path):
        manifest_text = SPLIT_BOARD_INTERFACE_MANIFEST.replace(
            "    - net: pwm\n      role: control\n      owner: CONTROL_BOARD\n      direction: CONTROL_BOARD_TO_POWER_BOARD\n      domain: SELV\n",
            "    - net: pwm\n      role: control\n      owner: CONTROL_BOARD\n      direction: CONTROL_BOARD_TO_POWER_BOARD\n      domain: HV\n",
            1,
        )
        with pytest.raises(GateError, match="declares domain"):
            load_manifest(write_manifest(tmp_path, manifest_text))

    def test_resolved_signal_rejects_unresolved_sentinel(self, tmp_path):
        manifest_text = SPLIT_BOARD_INTERFACE_MANIFEST.replace(
            "      owner: POWER_BOARD\n      direction: POWER_BOARD_TO_CONTROL_BOARD\n",
            "      owner: UNRESOLVED\n      direction: POWER_BOARD_TO_CONTROL_BOARD\n",
            1,
        )

        with pytest.raises(GateError, match="UNRESOLVED sentinel"):
            load_manifest(write_manifest(tmp_path, manifest_text))

    def test_generation_readiness_fails_closed_on_unresolved_fault_aggregation(
        self, tmp_path
    ):
        manifest_text = SPLIT_BOARD_INTERFACE_MANIFEST.replace(
            "    status: resolved\n  connector_spec:",
            "    status: unresolved\n  connector_spec:",
            1,
        )
        manifest = load_manifest(write_manifest(tmp_path, manifest_text))

        with pytest.raises(GateError, match="fault aggregation semantics"):
            check_board_interface_generation_ready(manifest)

    def test_signal_schema_requires_all_semantic_fields(self, tmp_path):
        malformed = SPLIT_BOARD_INTERFACE_MANIFEST.replace(
            "      status: resolved\n", "      status: resolved\n", 1
        ).replace(
            "      fault_behavior: \"loss blocks power-up\"\n", "", 1
        )

        with pytest.raises(GateError, match="missing keys"):
            load_manifest(write_manifest(tmp_path, malformed))

    def test_split_board_interface_accepts_only_declared_selv_nets(self, tmp_path):
        netlist = parse_netlist(
            write_netlist(
                tmp_path,
                [("J1", "connector")],
                [
                    ("v15", [("J1", "1")]),
                    ("pwm", [("J1", "2")]),
                    ("shutdown", [("J1", "3")]),
                ],
            )
        )
        manifest = load_manifest(
            write_manifest(tmp_path, SPLIT_BOARD_INTERFACE_MANIFEST)
        )

        assert manifest.board_interface is not None
        assert check_board_interface_contract(netlist, manifest) == []

    def test_split_board_interface_rejects_hv_net(self, tmp_path):
        manifest_text = SPLIT_BOARD_INTERFACE_MANIFEST.replace(
            "nets: [v15, pwm, shutdown]",
            "nets: [v15, hv_return, shutdown]",
            1,
        )
        manifest_text = manifest_text.replace(
            "    - net: pwm\n", "    - net: hv_return\n", 1
        ).replace(
            "      domain: SELV\n      return_net: selv_gnd\n"
            "      fault_behavior: \"loss disables power stage\"\n",
            "      domain: HV\n      return_net: selv_gnd\n"
            "      fault_behavior: \"loss disables power stage\"\n",
            1,
        )
        netlist = parse_netlist(
            write_netlist(
                tmp_path,
                [("J1", "connector")],
                [
                    ("v15", [("J1", "1")]),
                    ("hv_return", [("J1", "2")]),
                    ("shutdown", [("J1", "3")]),
                ],
            )
        )
        manifest = load_manifest(write_manifest(tmp_path, manifest_text))

        violations = check_board_interface_contract(netlist, manifest)

        assert len(violations) == 1
        assert "hv_return" in violations[0]
        assert "HV" in violations[0]


class TestBoardPartitionContract:
    def test_real_manifest_assigns_hv_power_and_mcu_rtd_control(self):
        repo_root = Path(__file__).resolve().parents[2]
        manifest = load_manifest(repo_root / "elec" / "domain_manifest.yaml")

        assert manifest.board_partition is not None
        partition = manifest.board_partition
        assert partition.board_domains[partition.power_board] == "HV"
        assert partition.board_domains[partition.control_board] == "SELV"
        assert "hb" in partition.modules[partition.power_board]
        assert "mcu" in partition.modules[partition.control_board]
        assert "rtd_pan" in partition.modules[partition.control_board]
        assert "thermal" in partition.modules[partition.control_board]
        assert check_board_partition_contract(manifest) == []

    def test_real_partition_accounts_for_every_component_and_all_isolator_sides(self):
        repo_root = Path(__file__).resolve().parents[2]
        manifest = load_manifest(repo_root / "elec" / "domain_manifest.yaml")
        partition = manifest.board_partition
        assert partition is not None
        assert set(partition.cross_domain_modules) == {"aux_supply", "ct_sense"}
        assert len(partition.cross_domain_components) == 15
        assert {
            entry["instance_path"] for entry in partition.cross_domain_components
        } == {
            "aux_supply.c_in_bulk", "aux_supply.c_out", "aux_supply.c_out_hf",
            "aux_supply.psu", "ct_sense.c_filter", "ct_sense.ct",
            "ct_sense.r_bias_bot", "ct_sense.r_bias_top", "ct_sense.r_burden",
            "discharge.k_dis1", "discharge.k_dis2", "hb.gate_hs.driver",
            "power_in.bypass_relay", "power_in.y_cap_pe", "safety.ocp2.ct",
        }
        assert {
            side.instance_path for side in partition.isolator_sides
        } == {
            "aux_supply.psu", "hb.gate_hs.driver", "ct_sense.ct",
            "safety.ocp2.ct", "power_in.bypass_relay", "discharge.k_dis1",
            "discharge.k_dis2", "power_in.y_cap_pe",
        }
        assert check_board_partition_contract(
            manifest,
            netlist=parse_netlist(repo_root / "elec" / "build" / "default.net"),
            src_dir=repo_root / "elec" / "src",
        ) == []

    def test_split_board_partition_keeps_domains_and_isolator_sides_explicit(self, tmp_path):
        manifest = load_manifest(
            write_manifest(tmp_path, SPLIT_BOARD_PARTITION_MANIFEST)
        )

        assert manifest.board_partition is not None
        assert manifest.board_partition.board_domains == {
            "POWER_BOARD": "HV",
            "CONTROL_BOARD": "SELV",
        }
        assert manifest.board_partition.modules["CONTROL_BOARD"] == (
            "mcu",
            "rtd_pan",
        )
        side = manifest.board_partition.isolator_sides[0]
        assert (side.power_board_group, side.control_board_group) == (
            "primary",
            "secondary",
        )
        assert check_board_partition_contract(manifest) == []

    def test_partition_rejects_hv_control_board(self, tmp_path):
        text = SPLIT_BOARD_PARTITION_MANIFEST.replace(
            "CONTROL_BOARD:\n      domain: SELV",
            "CONTROL_BOARD:\n      domain: HV",
        )

        with pytest.raises(GateError, match="different domains"):
            load_manifest(write_manifest(tmp_path, text))

    def test_partition_requires_every_declared_isolator_side_mapping(self, tmp_path):
        text = SPLIT_BOARD_PARTITION_MANIFEST.replace(
            "isolator_sides:\n    - instance_path: aux.psu\n      power_board_group: primary\n      control_board_group: secondary\n",
            "isolator_sides: []\n",
        )

        with pytest.raises(GateError, match="isolator_sides must be a non-empty list"):
            load_manifest(write_manifest(tmp_path, text))

    def test_partition_requires_exact_group_coverage(self, tmp_path):
        text = SPLIT_BOARD_PARTITION_MANIFEST.replace(
            "      primary: [1]\n      secondary: [2]\n",
            "      primary: [1]\n      secondary: [2]\n      shield: [3]\n",
        )

        with pytest.raises(GateError, match="map every group exactly once"):
            load_manifest(write_manifest(tmp_path, text))

    def test_partition_reports_interface_domain_leak(self, tmp_path):
        manifest = load_manifest(
            write_manifest(tmp_path, SPLIT_BOARD_PARTITION_MANIFEST)
        )
        # Exercise the semantic check independently of YAML parsing: a
        # future caller cannot move an interface net to HV and still receive
        # a clean partition verdict.
        manifest.domains["HV"].append("shutdown")
        manifest.domains["SELV"].remove("shutdown")

        violations = check_board_partition_contract(manifest)

        assert violations == [
            "split-board interface net 'shutdown' is not owned by the "
            "control-board domain 'SELV'"
        ]


def test_split_board_atopile_boundary_has_no_connector_or_physical_board_claim():
    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / "elec" / "src" / "split_board_hierarchy.ato").read_text()

    assert "interface PowerControlSELV" in source
    for signal in (
        "gnd",
        "vcc_15v",
        "vcc_3v3",
        "pwm_hs",
        "pwm_ls",
        "shutdown",
        "relay_ctrl",
        "discharge_ctrl",
        "v_bus_sense",
        "i_sense",
    ):
        assert f"signal {signal}" in source
    assert "module PowerBoardBoundary" in source
    assert "module ControlBoardBoundary" in source
    assert "connector =" not in source.lower()
    assert "pcb/temper.kicad_pcb" in source


def _shorted_topology_nets():
    """The exact defect class this gate exists to catch: the isolator's
    primary and secondary pins land on the SAME net (a direct short across
    the barrier), mirroring aux_supply.psu pins 2 and 4 both landing on
    PWR_RTN in the real design. All four manifest-declared nets are still
    present (hv_return now carries both the primary AND secondary pin;
    selv_gnd is kept alive via an unrelated dummy component) so this
    fixture isolates exactly one variable -- the short -- rather than also
    changing which nets exist."""
    return [
        ("ac_l", [("PS1", "1")]),
        ("hv_return", [("PS1", "2"), ("PS1", "4")]),  # primary AND secondary pin here
        ("v15", [("PS1", "3")]),
        ("selv_gnd", [("DUMMY1", "1")]),
    ]


ISOLATED_COMPONENTS = [("PS1", "aux.psu")]
SHORTED_COMPONENTS = [("PS1", "aux.psu"), ("DUMMY1", "some.dummy")]


# ---------------------------------------------------------------------------
# parse_netlist / load_manifest basics
# ---------------------------------------------------------------------------


class TestParseNetlist:
    def test_parses_minimal_valid_netlist(self, tmp_path):
        path = write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        nl = parse_netlist(path)
        assert set(nl.components) == {"PS1"}
        assert nl.components["PS1"].instance_path == "aux.psu"
        assert len(nl.nets) == 4

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(GateError, match="not found"):
            parse_netlist(tmp_path / "nope.net")

    def test_empty_file_raises(self, tmp_path):
        p = tmp_path / "empty.net"
        p.write_text("")
        with pytest.raises(GateError, match="empty"):
            parse_netlist(p)

    def test_zero_components_raises(self, tmp_path):
        # A netlist with a nets block but no components at all.
        text = (
            '(export (version "E")\n'
            '  (design (source "t")(date "")(tool "t"))\n'
            "  (components\n  )\n"
            "  (libparts)\n"
            '  (nets\n    (net (code "1") (name "x")\n    )\n  )\n'
            ")\n"
        )
        p = tmp_path / "x.net"
        p.write_text(text)
        with pytest.raises(GateError, match="zero components"):
            parse_netlist(p)

    def test_duplicate_pin_in_two_nets_raises(self, tmp_path):
        path = write_netlist(
            tmp_path,
            ISOLATED_COMPONENTS,
            [
                ("net_a", [("PS1", "1")]),
                ("net_b", [("PS1", "1")]),  # same (ref, pin) twice
            ],
        )
        with pytest.raises(GateError, match="more than one net"):
            parse_netlist(path)


class TestLoadManifest:
    def test_parses_valid_manifest(self, tmp_path):
        path = write_manifest(tmp_path, MINIMAL_ISOLATED_MANIFEST)
        m = load_manifest(path)
        assert set(m.domains) == {"HV", "SELV"}
        assert len(m.isolators) == 1
        assert m.isolators[0].groups["primary"] == ["1", "2"]

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(GateError, match="not found"):
            load_manifest(tmp_path / "nope.yaml")

    def test_empty_file_is_gate_error_not_silent_pass(self, tmp_path):
        """The core anti-vacuous-truth requirement: an empty manifest must
        fail closed, never be silently treated as '0 domains, 0 violations,
        PASSED'."""
        path = write_manifest(tmp_path, "")
        with pytest.raises(GateError, match="empty"):
            load_manifest(path)

    def test_manifest_with_no_domains_key_is_gate_error(self, tmp_path):
        path = write_manifest(tmp_path, "schema_version: 1\nisolators: []\n")
        with pytest.raises(GateError, match="domains"):
            load_manifest(path)

    def test_manifest_with_empty_domains_dict_is_gate_error(self, tmp_path):
        path = write_manifest(tmp_path, "domains: {}\nisolators: []\n")
        with pytest.raises(GateError, match="domains"):
            load_manifest(path)

    def test_domain_with_empty_net_list_is_gate_error(self, tmp_path):
        text = "domains:\n  HV:\n    nets: []\n  SELV:\n    nets: [\"x\"]\nisolators: []\n"
        path = write_manifest(tmp_path, text)
        with pytest.raises(GateError, match="empty"):
            load_manifest(path)

    def test_single_domain_is_gate_error(self, tmp_path):
        text = "domains:\n  HV:\n    nets: [\"a\"]\nisolators: []\n"
        path = write_manifest(tmp_path, text)
        with pytest.raises(GateError, match="fewer than 2"):
            load_manifest(path)

    def test_net_declared_in_two_domains_is_gate_error(self, tmp_path):
        text = (
            "domains:\n"
            "  HV:\n    nets: [\"shared\"]\n"
            "  SELV:\n    nets: [\"shared\"]\n"
            "isolators: []\n"
        )
        path = write_manifest(tmp_path, text)
        with pytest.raises(GateError, match="both domain"):
            load_manifest(path)

    def test_isolator_with_one_group_is_gate_error(self, tmp_path):
        text = (
            "domains:\n  HV:\n    nets: [\"a\"]\n  SELV:\n    nets: [\"b\"]\n"
            "isolators:\n"
            "  - instance_path: x.y\n"
            "    groups:\n      only_one: [\"1\"]\n"
        )
        path = write_manifest(tmp_path, text)
        with pytest.raises(GateError, match="at least 2 pin"):
            load_manifest(path)

    def test_isolator_pin_in_two_groups_is_gate_error(self, tmp_path):
        text = (
            "domains:\n  HV:\n    nets: [\"a\"]\n  SELV:\n    nets: [\"b\"]\n"
            "isolators:\n"
            "  - instance_path: x.y\n"
            "    groups:\n      primary: [\"1\", \"2\"]\n      secondary: [\"2\", \"3\"]\n"
        )
        path = write_manifest(tmp_path, text)
        with pytest.raises(GateError, match="both group"):
            load_manifest(path)


# ---------------------------------------------------------------------------
# resolve_isolator_refs: instance_path matching and completeness
# ---------------------------------------------------------------------------


class TestResolveIsolatorRefs:
    def test_matches_by_instance_path(self, tmp_path):
        netlist = parse_netlist(
            write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        )
        manifest = load_manifest(write_manifest(tmp_path, MINIMAL_ISOLATED_MANIFEST))
        ref_isolator = resolve_isolator_refs(netlist, manifest.isolators)
        assert set(ref_isolator) == {"PS1"}

    def test_unmatched_instance_path_is_gate_error(self, tmp_path):
        netlist = parse_netlist(
            write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        )
        text = MINIMAL_ISOLATED_MANIFEST.replace("aux.psu", "does.not.exist")
        manifest = load_manifest(write_manifest(tmp_path, text))
        with pytest.raises(GateError, match="matches no component"):
            resolve_isolator_refs(netlist, manifest.isolators)

    def test_incomplete_group_coverage_is_gate_error(self, tmp_path):
        """PS1 has a 5th wired pin the manifest's groups don't cover -- an
        isolator with an undeclared pin must fail closed, not silently
        assume the undeclared pin is harmless."""
        components = ISOLATED_COMPONENTS
        nets = _isolated_topology_nets() + [("extra_net", [("PS1", "5")])]
        netlist = parse_netlist(write_netlist(tmp_path, components, nets))
        manifest = load_manifest(write_manifest(tmp_path, MINIMAL_ISOLATED_MANIFEST))
        with pytest.raises(GateError, match="not covered by any declared group"):
            resolve_isolator_refs(netlist, manifest.isolators)

    def test_declared_pin_not_wired_is_gate_error(self, tmp_path):
        """Manifest declares pin '4' but PS1 in this netlist never uses it
        -- stale manifest, must fail closed."""
        components = ISOLATED_COMPONENTS
        nets = [
            ("ac_l", [("PS1", "1")]),
            ("hv_return", [("PS1", "2")]),
            ("v15", [("PS1", "3")]),
        ]
        netlist = parse_netlist(write_netlist(tmp_path, components, nets))
        manifest = load_manifest(write_manifest(tmp_path, MINIMAL_ISOLATED_MANIFEST))
        with pytest.raises(GateError, match="not wired in the netlist"):
            resolve_isolator_refs(netlist, manifest.isolators)


# ---------------------------------------------------------------------------
# End-to-end via run(): the behaviors the CI gate actually depends on
# ---------------------------------------------------------------------------


class TestRunEndToEnd:
    def test_clean_isolated_topology_passes(self, tmp_path, capsys):
        netlist = write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        manifest = write_manifest(tmp_path, MINIMAL_ISOLATED_MANIFEST)
        code = run(netlist, manifest, tmp_path, skip_freshness=True)
        out = capsys.readouterr().out
        assert code == EXIT_OK
        assert "PASSED" in out

    def test_shorted_barrier_fails_with_path(self, tmp_path, capsys):
        """The core falsifier: a component whose primary and secondary
        pins land on the same net (a direct short across the isolation
        barrier, exactly the aux_supply.psu pins 2/4 -> PWR_RTN defect in
        the real design) must FAIL and must print the shared net."""
        netlist = write_netlist(tmp_path, SHORTED_COMPONENTS, _shorted_topology_nets())
        manifest = write_manifest(tmp_path, MINIMAL_ISOLATED_MANIFEST)
        code = run(netlist, manifest, tmp_path, skip_freshness=True)
        out = capsys.readouterr().out
        assert code == EXIT_VIOLATION
        assert "FAILED" in out
        assert "barrier is bridged" in out
        assert "hv_return" in out

    def test_missing_netlist_fails_closed(self, tmp_path):
        manifest = write_manifest(tmp_path, MINIMAL_ISOLATED_MANIFEST)
        code = run(tmp_path / "nope.net", manifest, tmp_path, skip_freshness=True)
        assert code == EXIT_GATE_ERROR

    def test_missing_manifest_fails_closed(self, tmp_path):
        netlist = write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        code = run(netlist, tmp_path / "nope.yaml", tmp_path, skip_freshness=True)
        assert code == EXIT_GATE_ERROR

    def test_empty_manifest_fails_closed_not_silently_passes(self, tmp_path):
        """Anti-vacuous-truth, stated as an end-to-end behavior: an empty
        manifest must never produce exit 0."""
        netlist = write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        manifest = write_manifest(tmp_path, "")
        code = run(netlist, manifest, tmp_path, skip_freshness=True)
        assert code == EXIT_GATE_ERROR
        assert code != EXIT_OK

    def test_missing_isolator_declaration_causes_visible_false_positive(
        self, tmp_path, capsys
    ):
        """If a real isolator is NOT declared in the manifest, the default
        conservative assumption (undeclared component = fully conductive
        across all its pins) makes a correctly isolated topology LOOK
        shorted. This is deliberate: the failure mode of an incomplete
        manifest is a loud, visible false positive a human must adjudicate,
        never a silently missed real short."""
        netlist = write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        manifest = write_manifest(
            tmp_path,
            MINIMAL_ISOLATED_MANIFEST.replace(
                "isolators:\n  - instance_path: aux.psu\n"
                '    component: "Test isolator"\n'
                "    groups:\n      primary: [\"1\", \"2\"]\n      secondary: [\"3\", \"4\"]\n",
                "isolators: []\n",
            ),
        )
        code = run(netlist, manifest, tmp_path, skip_freshness=True)
        out = capsys.readouterr().out
        assert code == EXIT_VIOLATION
        assert "FAILED" in out

    def test_declared_net_not_in_netlist_fails_closed(self, tmp_path):
        netlist = write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        text = MINIMAL_ISOLATED_MANIFEST.replace("hv_return", "typo_net_name")
        manifest = write_manifest(tmp_path, text)
        code = run(netlist, manifest, tmp_path, skip_freshness=True)
        assert code == EXIT_GATE_ERROR

    def test_multi_hop_path_is_reported(self, tmp_path, capsys):
        """A domain crossing that goes through an intermediate net (not a
        direct same-net collision) must still be found, and the printed
        path must show the intermediate hop and the bridging component --
        this is the 'net-by-net path' requirement, not just a same-net
        check."""
        components = ISOLATED_COMPONENTS + [("R1", "some.resistor")]
        nets = [
            ("ac_l", [("PS1", "1")]),
            ("hv_return", [("PS1", "2")]),
            ("v15", [("PS1", "3"), ("R1", "1")]),
            ("mid_net", [("R1", "2")]),
            ("selv_gnd", [("PS1", "4")]),
        ]
        # Redeclare SELV to include mid_net so a 2-hop crossing exists:
        # ac_l(HV) -- PS1 -- hv_return(HV); v15(SELV) -- R1 -- mid_net.
        # Make mid_net an HV net instead, so v15(SELV) -[R1]-> mid_net(HV)
        # is the multi-hop violation to detect.
        manifest_text = MINIMAL_ISOLATED_MANIFEST.replace(
            'nets: ["ac_l", "hv_return"]', 'nets: ["ac_l", "hv_return", "mid_net"]'
        )
        netlist = write_netlist(tmp_path, components, nets)
        manifest = write_manifest(tmp_path, manifest_text)
        code = run(netlist, manifest, tmp_path, skip_freshness=True)
        out = capsys.readouterr().out
        assert code == EXIT_VIOLATION
        assert "R1" in out
        assert "mid_net" in out
        assert "v15" in out


# ---------------------------------------------------------------------------
# Netlist freshness (staleness must fail closed, not silently check old data)
# ---------------------------------------------------------------------------


class TestNetlistFreshness:
    def test_fresh_netlist_passes(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.ato").write_text("# source\n")
        time.sleep(0.05)
        netlist = write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        check_netlist_freshness(netlist, src_dir)  # must not raise

    def test_stale_netlist_fails_closed(self, tmp_path):
        """The netlist predates a source file -- this must be a GateError,
        never treated as '0 violations found'. This is the single most
        common way this class of gate has died on this project: silently
        checking yesterday's design and reporting a clean bill of health."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        netlist = write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        time.sleep(0.05)
        (src_dir / "main.ato").write_text("# edited after the netlist was built\n")
        with pytest.raises(GateError, match="STALE"):
            check_netlist_freshness(netlist, src_dir)

    def test_missing_netlist_is_gate_error(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.ato").write_text("# source\n")
        with pytest.raises(GateError, match="not found"):
            check_netlist_freshness(tmp_path / "nope.net", src_dir)

    def test_stamped_netlist_survives_newer_sources(self, tmp_path):
        """A restored cache: sources newer than the netlist, content unchanged.

        This is the case that broke the gate on 2026-07-28. `git checkout`
        stamps every .ato with the checkout time, so a cached netlist is always
        mtime-older than sources it in fact matches. Runs 30383701486 (rebuilt,
        passed) and 30384514627 (cached, errored) differed only in that.
        """
        import os

        from _lib.freshness import write_stamp

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        source = src_dir / "main.ato"
        source.write_text("# source\n")
        netlist = write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        write_stamp(netlist, [source], src_dir)

        future = time.time() + 10_000
        os.utime(source, (future, future))
        assert source.stat().st_mtime > netlist.stat().st_mtime

        check_netlist_freshness(netlist, src_dir)  # must not raise

    def test_stamped_netlist_still_fails_on_real_edit(self, tmp_path):
        """Content hashing must not weaken the gate: an actual source change
        is still STALE even though the stamp exists."""
        from _lib.freshness import write_stamp

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        source = src_dir / "main.ato"
        source.write_text("# source\n")
        netlist = write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        write_stamp(netlist, [source], src_dir)

        source.write_text("# genuinely edited after the build\n")
        with pytest.raises(GateError, match="STALE"):
            check_netlist_freshness(netlist, src_dir)

    def test_stamped_netlist_catches_backdated_edit(self, tmp_path):
        """An edit back-dated older than the netlist passes the mtime check and
        must still be caught -- content hashing is strictly stronger here, not
        merely more cache-friendly."""
        import os

        from _lib.freshness import write_stamp

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        source = src_dir / "main.ato"
        source.write_text("# source\n")
        netlist = write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        write_stamp(netlist, [source], src_dir)

        source.write_text("# edited, then back-dated\n")
        past = time.time() - 10_000
        os.utime(source, (past, past))
        assert source.stat().st_mtime < netlist.stat().st_mtime

        with pytest.raises(GateError, match="STALE"):
            check_netlist_freshness(netlist, src_dir)

    def test_run_end_to_end_fails_closed_on_stale_netlist(self, tmp_path):
        """Same check exercised through run() (skip_freshness=False, the
        real CI default) end-to-end."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        netlist = write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        manifest = write_manifest(tmp_path, MINIMAL_ISOLATED_MANIFEST)
        time.sleep(0.05)
        (src_dir / "main.ato").write_text("# edited after the netlist was built\n")
        code = run(netlist, manifest, src_dir, skip_freshness=False)
        assert code == EXIT_GATE_ERROR


# ---------------------------------------------------------------------------
# Direct checks on the graph/BFS mechanics
# ---------------------------------------------------------------------------


class TestGraphMechanics:
    def test_isolator_groups_are_not_unioned_across_barrier(self, tmp_path):
        netlist = parse_netlist(
            write_netlist(tmp_path, ISOLATED_COMPONENTS, _isolated_topology_nets())
        )
        manifest = load_manifest(write_manifest(tmp_path, MINIMAL_ISOLATED_MANIFEST))
        ref_isolator = resolve_isolator_refs(netlist, manifest.isolators)
        graph = build_graph(netlist, ref_isolator)
        component_of = connected_components(graph)
        # primary side (ac_l, hv_return) must NOT share a component with
        # secondary side (v15, selv_gnd).
        assert component_of["1"] != component_of["3"]  # ac_l vs v15 (codes 1,3)
        violations = check_domain_disjointness(netlist, manifest, graph, component_of)
        assert violations == []
        iso_violations = check_isolator_integrity(netlist, ref_isolator, graph, component_of)
        assert iso_violations == []

    def test_undeclared_component_unions_all_its_pins(self, tmp_path):
        """Default (fail-closed) behavior: a component NOT declared as an
        isolator conducts across all of its own pins -- this is what makes
        the MCU-style 'ordinary IC bridges HV and SELV pins' finding
        possible without special-casing it."""
        components = [("U1", "some.chip")]
        nets = [
            ("net_a", [("U1", "1")]),
            ("net_b", [("U1", "2")]),
            ("net_c", [("U1", "3")]),
        ]
        netlist = parse_netlist(write_netlist(tmp_path, components, nets))
        graph = build_graph(netlist, ref_isolator={})
        component_of = connected_components(graph)
        assert component_of["1"] == component_of["2"] == component_of["3"]
