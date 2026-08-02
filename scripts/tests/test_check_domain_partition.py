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
    GateError,
    build_graph,
    check_board_interface_contract,
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
domains:
  HV:
    nets: [ac_l, hv_return]
  SELV:
    nets: [v15, pwm, shutdown]
isolators: []
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
            "nets: [v15, pwm, shutdown]\ndomains:",
            "nets: [v15, hv_return, shutdown]\ndomains:",
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
