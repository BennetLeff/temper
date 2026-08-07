"""Tests for check_netlist_stage_checks.py.

These deliberately do NOT rely on the real elec/build/default.net,
elec/domain_manifest.yaml, or elec/src/*.ato -- matching the pattern in
test_check_domain_partition.py and test_check_isolation_keepout.py (synthetic
netlist/manifest/source fixtures, one controlled minimal reproduction of one
behavior per test). The real inputs are exercised directly by running the
gate itself; see the task report for the real-netlist findings.

Groups:
  TestSinglePinNets            -- check 1: a net with exactly one node
  TestUnconnectedPowerPins     -- check 2: dangling / isolated power pins
  TestVoltageDomainCompat      -- check 3: named-net floor violations, and
                                   the false-positive regression this check's
                                   scoping was specifically fixed to avoid
  TestAllowlist                -- allowlisted findings are excluded from the
                                   live count and exit code
  TestAntiVacuity               -- missing/empty/malformed inputs -> GateError,
                                   never a silent "0 findings"
  TestFailBeforePassAfter       -- explicit before/after pairs per check
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_domain_partition import load_manifest, parse_netlist  # noqa: E402
from check_netlist_stage_checks import (  # noqa: E402
    ATO_SOURCE_FILES,
    EXIT_GATE_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    GateError,
    check_single_pin_nets,
    check_unconnected_power_pins,
    check_voltage_domain_compat,
    compute_net_voltage_floors,
    find_power_pins,
    is_power_pin_name,
    load_allowlist,
    parse_ato_classes,
    path_to_ref,
    resolve_instances,
    run,
)

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

# A minimal, generic .ato source model: one power-and-signal IC (TestIC:
# VCC/GND/SIG pins) and one two-terminal part with a settable voltage_rating
# (TestResistor), instantiated under Top. Individual tests override pieces of
# this by passing their own `main_body` / `extra_components`.
COMPONENTS_ATO = """
component TestIC:
    footprint = "Test:IC"
    mpn = "TESTIC"
    signal VCC ~ pin 1
    signal GND ~ pin 2
    signal SIG ~ pin 3

component TestResistor:
    footprint = "Test:R"
    voltage_rating: voltage
    signal p1 ~ pin 1
    signal p2 ~ pin 2

component FixedPartWithDefault:
    footprint = "Test:Fixed"
    voltage_rating = 1000V
    signal p1 ~ pin 1
    signal p2 ~ pin 2
"""


def write_ato_source(tmp_path: Path, main_body: str, components_ato: str = COMPONENTS_ATO) -> Path:
    src_dir = tmp_path / "src"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "components.ato").write_text(components_ato)
    (src_dir / "main.ato").write_text(f"module Top:\n{main_body}\n")
    # The remaining ATO_SOURCE_FILES entries are intentionally left absent --
    # parse_ato_classes() must skip missing files gracefully.
    for name in ATO_SOURCE_FILES:
        assert name in ("components.ato", "main.ato") or not (src_dir / name).exists()
    return src_dir


def make_netlist_text(
    components: list[tuple[str, str]],
    nets: list[tuple[str, list[tuple[str, str]]]],
) -> str:
    """Minimal, valid KiCad-format netlist text (mirrors
    test_check_domain_partition.py's builder of the same name)."""
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


MINIMAL_MANIFEST = """
schema_version: 1
domains:
  HV:
    nets: ["+170V_BUS"]
  SELV:
    nets: ["gnd"]
"""

# "+170V_BUS" is the only net in MINIMAL_MANIFEST with an explicit voltage
# in its own name, so it is the only one check_voltage_domain_compat/run()
# require to actually exist in the netlist (a declared-but-missing net
# fails closed, matching check_domain_partition.py's own contract -- "gnd"
# carries no explicit voltage and is never looked up). Tests that are not
# about voltage-domain compatibility at all still need to satisfy this, so
# they merge in this baseline: one inert component, safely rated (1000V,
# via FixedPartWithDefault's own class default) far above the 170V floor,
# with BOTH its pins on "+170V_BUS" -- a 2-node net, so it also never trips
# the single-pin-net check on its own.
BASELINE_ATO_BODY = "    _baseline = new FixedPartWithDefault\n"
BASELINE_COMPONENTS = [("BASE1", "_baseline")]
BASELINE_NETS = [("+170V_BUS", [("BASE1", "1"), ("BASE1", "2")])]


def write_manifest(tmp_path: Path, text: str = MINIMAL_MANIFEST, name: str = "manifest.yaml") -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def write_allowlist(tmp_path: Path, text: str, name: str = "allowlist.yaml") -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


# ---------------------------------------------------------------------------
# Check 1: single-pin nets
# ---------------------------------------------------------------------------


class TestSinglePinNets:
    def test_single_pin_net_detected(self, tmp_path: Path) -> None:
        netlist_path = write_netlist(
            tmp_path,
            components=[("U1", "ic1")],
            nets=[("lonely_net", [("U1", "3")])],
        )
        netlist = parse_netlist(netlist_path)
        findings = check_single_pin_nets(netlist)
        assert len(findings) == 1
        assert findings[0].net_name == "lonely_net"
        assert findings[0].ref == "U1"
        assert findings[0].pin == "3"

    def test_multi_pin_net_not_flagged(self, tmp_path: Path) -> None:
        netlist_path = write_netlist(
            tmp_path,
            components=[("U1", "ic1"), ("U2", "ic2")],
            nets=[("shared", [("U1", "3"), ("U2", "3")])],
        )
        netlist = parse_netlist(netlist_path)
        findings = check_single_pin_nets(netlist)
        assert findings == []


# ---------------------------------------------------------------------------
# Check 2: unconnected power pins
# ---------------------------------------------------------------------------


class TestPowerPinNaming:
    @pytest.mark.parametrize("name", ["VCC", "VDD", "VSS", "GND", "GND1", "GNDI", "DGND", "VCCI_1", "VDDA", "VSSB", "VP", "VN", "VS", "VIN"])
    def test_real_power_names_match(self, name: str) -> None:
        assert is_power_pin_name(name)

    @pytest.mark.parametrize("name", ["VBIAS", "VREF", "VO", "OUT", "SIG", "p1", "S", "A", "IO16"])
    def test_non_power_names_do_not_match(self, name: str) -> None:
        assert not is_power_pin_name(name)


class TestUnconnectedPowerPins:
    def test_power_pin_never_wired(self, tmp_path: Path) -> None:
        src_dir = write_ato_source(tmp_path, "    u1 = new TestIC\n")
        netlist_path = write_netlist(
            tmp_path,
            components=[("U1", "u1")],
            # VCC (pin 1) never appears in any net at all.
            nets=[("gnd_net", [("U1", "2")]), ("sig_net", [("U1", "3")])],
        )
        classes = parse_ato_classes([src_dir / n for n in ATO_SOURCE_FILES])
        resolved = resolve_instances(classes, root="Top")
        netlist = parse_netlist(netlist_path)
        power_pins = find_power_pins(classes, resolved)
        findings = check_unconnected_power_pins(netlist, power_pins, path_to_ref(netlist))
        vcc_findings = [f for f in findings if f.signal_name == "VCC"]
        assert len(vcc_findings) == 1
        assert "absent from the compiled netlist" in vcc_findings[0].reason

    def test_power_pin_isolated_single_node(self, tmp_path: Path) -> None:
        src_dir = write_ato_source(tmp_path, "    u1 = new TestIC\n")
        netlist_path = write_netlist(
            tmp_path,
            components=[("U1", "u1")],
            nets=[
                ("vcc_net", [("U1", "1")]),  # VCC wired only to itself
                ("gnd_net", [("U1", "2")]),
                ("sig_net", [("U1", "3")]),
            ],
        )
        classes = parse_ato_classes([src_dir / n for n in ATO_SOURCE_FILES])
        resolved = resolve_instances(classes, root="Top")
        netlist = parse_netlist(netlist_path)
        power_pins = find_power_pins(classes, resolved)
        findings = check_unconnected_power_pins(netlist, power_pins, path_to_ref(netlist))
        vcc_findings = [f for f in findings if f.signal_name == "VCC"]
        assert len(vcc_findings) == 1
        assert "no other connection" in vcc_findings[0].reason

    def test_power_pin_properly_connected_not_flagged(self, tmp_path: Path) -> None:
        src_dir = write_ato_source(tmp_path, "    u1 = new TestIC\n    u2 = new TestIC\n")
        netlist_path = write_netlist(
            tmp_path,
            components=[("U1", "u1"), ("U2", "u2")],
            nets=[
                ("vcc_net", [("U1", "1"), ("U2", "1")]),  # shared VCC rail
                ("gnd_net", [("U1", "2"), ("U2", "2")]),
                ("sig1", [("U1", "3")]),
                ("sig2", [("U2", "3")]),
            ],
        )
        classes = parse_ato_classes([src_dir / n for n in ATO_SOURCE_FILES])
        resolved = resolve_instances(classes, root="Top")
        netlist = parse_netlist(netlist_path)
        power_pins = find_power_pins(classes, resolved)
        findings = check_unconnected_power_pins(netlist, power_pins, path_to_ref(netlist))
        assert findings == []

    def test_ordinary_passive_on_power_net_does_not_false_positive(self, tmp_path: Path) -> None:
        """Regression guard for the false-positive mode explicitly rejected
        in the module docstring: a decoupling capacitor's generically-named
        p1/p2 pins sharing a VCC net must not, by itself, make anything
        report a violation (this check only ever looks at DECLARED power
        pins, never generic passive terminals)."""
        src_dir = write_ato_source(
            tmp_path, "    u1 = new TestIC\n    c1 = new TestResistor\n    c1.voltage_rating = 10V\n"
        )
        netlist_path = write_netlist(
            tmp_path,
            components=[("U1", "u1"), ("C1", "c1")],
            nets=[
                ("vcc_net", [("U1", "1"), ("C1", "1")]),  # only ONE declared power pin on this net
                ("gnd_net", [("U1", "2"), ("C1", "2")]),
                ("sig1", [("U1", "3")]),
            ],
        )
        classes = parse_ato_classes([src_dir / n for n in ATO_SOURCE_FILES])
        resolved = resolve_instances(classes, root="Top")
        netlist = parse_netlist(netlist_path)
        power_pins = find_power_pins(classes, resolved)
        findings = check_unconnected_power_pins(netlist, power_pins, path_to_ref(netlist))
        assert findings == []


# ---------------------------------------------------------------------------
# Check 3: voltage-domain compatibility
# ---------------------------------------------------------------------------


class TestVoltageDomainCompat:
    def test_underrated_part_on_named_net_flagged(self, tmp_path: Path) -> None:
        src_dir = write_ato_source(
            tmp_path, "    r1 = new TestResistor\n    r1.voltage_rating = 25V\n"
        )
        netlist_path = write_netlist(
            tmp_path,
            components=[("R1", "r1")],
            nets=[("+170V_BUS", [("R1", "1")]), ("gnd", [("R1", "2")])],
        )
        classes = parse_ato_classes([src_dir / n for n in ATO_SOURCE_FILES])
        resolved = resolve_instances(classes, root="Top")
        netlist = parse_netlist(netlist_path)
        manifest = load_manifest(write_manifest(tmp_path))
        floors = compute_net_voltage_floors(manifest)
        findings = check_voltage_domain_compat(netlist, manifest, floors, resolved, path_to_ref(netlist))
        assert len(findings) == 1
        assert findings[0].instance_path == "r1"
        assert findings[0].net_name == "+170V_BUS"
        assert findings[0].voltage_rating == 25.0
        assert findings[0].floor_voltage == 170.0

    def test_adequately_rated_part_not_flagged(self, tmp_path: Path) -> None:
        src_dir = write_ato_source(
            tmp_path, "    r1 = new TestResistor\n    r1.voltage_rating = 250V\n"
        )
        netlist_path = write_netlist(
            tmp_path,
            components=[("R1", "r1")],
            nets=[("+170V_BUS", [("R1", "1")]), ("gnd", [("R1", "2")])],
        )
        classes = parse_ato_classes([src_dir / n for n in ATO_SOURCE_FILES])
        resolved = resolve_instances(classes, root="Top")
        netlist = parse_netlist(netlist_path)
        manifest = load_manifest(write_manifest(tmp_path))
        floors = compute_net_voltage_floors(manifest)
        findings = check_voltage_domain_compat(netlist, manifest, floors, resolved, path_to_ref(netlist))
        assert findings == []

    def test_unrated_part_not_flagged(self, tmp_path: Path) -> None:
        """No voltage_rating known -> never claim a violation (no guessing)."""
        src_dir = write_ato_source(tmp_path, "    r1 = new TestResistor\n")
        netlist_path = write_netlist(
            tmp_path,
            components=[("R1", "r1")],
            nets=[("+170V_BUS", [("R1", "1")]), ("gnd", [("R1", "2")])],
        )
        classes = parse_ato_classes([src_dir / n for n in ATO_SOURCE_FILES])
        resolved = resolve_instances(classes, root="Top")
        netlist = parse_netlist(netlist_path)
        manifest = load_manifest(write_manifest(tmp_path))
        floors = compute_net_voltage_floors(manifest)
        findings = check_voltage_domain_compat(netlist, manifest, floors, resolved, path_to_ref(netlist))
        assert findings == []

    def test_domain_wide_floor_not_applied_to_unnamed_net(self, tmp_path: Path) -> None:
        """Regression guard for the exact false positive found and fixed
        against the real board: an under-rated part on a domain net WITHOUT
        an explicit voltage in ITS OWN name (e.g. 'gnd', which is in SELV
        alongside the explicitly-named '+15V') must NOT be flagged just
        because some OTHER net in the same domain names a higher voltage."""
        src_dir = write_ato_source(
            tmp_path, "    r1 = new TestResistor\n    r1.voltage_rating = 5V\n" + BASELINE_ATO_BODY
        )
        netlist_path = write_netlist(
            tmp_path,
            components=[("R1", "r1")] + BASELINE_COMPONENTS,
            # r1 is on 'gnd' (SELV, no explicit voltage in its own name) and
            # nowhere near '+170V_BUS' at all; BASELINE exists only so the
            # manifest's HV net-existence requirement is satisfiable.
            nets=[("gnd", [("R1", "1"), ("R1", "2")])] + BASELINE_NETS,
        )
        classes = parse_ato_classes([src_dir / n for n in ATO_SOURCE_FILES])
        resolved = resolve_instances(classes, root="Top")
        netlist = parse_netlist(netlist_path)
        manifest = load_manifest(write_manifest(tmp_path))
        floors = compute_net_voltage_floors(manifest)
        assert "gnd" not in floors  # precondition: 'gnd' itself names no voltage
        findings = check_voltage_domain_compat(netlist, manifest, floors, resolved, path_to_ref(netlist))
        assert findings == []

    def test_fixed_default_voltage_from_component_class(self, tmp_path: Path) -> None:
        """A component with a bare, class-level `voltage_rating = X` (no
        per-instance override) resolves via the class default."""
        src_dir = write_ato_source(tmp_path, "    f1 = new FixedPartWithDefault\n")
        netlist_path = write_netlist(
            tmp_path,
            components=[("F1", "f1")],
            nets=[("+170V_BUS", [("F1", "1")]), ("gnd", [("F1", "2")])],
        )
        classes = parse_ato_classes([src_dir / n for n in ATO_SOURCE_FILES])
        resolved = resolve_instances(classes, root="Top")
        assert resolved["f1"].voltage_rating == 1000.0
        netlist = parse_netlist(netlist_path)
        manifest = load_manifest(write_manifest(tmp_path))
        floors = compute_net_voltage_floors(manifest)
        findings = check_voltage_domain_compat(netlist, manifest, floors, resolved, path_to_ref(netlist))
        assert findings == []  # 1000V >= 170V floor


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------


class TestAllowlist:
    def test_allowlisted_finding_excluded_from_live_count(self, tmp_path: Path) -> None:
        src_dir = write_ato_source(
            tmp_path, "    u1 = new TestIC\n" + BASELINE_ATO_BODY
        )
        netlist_path = write_netlist(
            tmp_path,
            components=[("U1", "u1")] + BASELINE_COMPONENTS,
            # U1's VCC/GND (pins 1/2) are wired together (2-node net) so
            # this test stays scoped to the single-pin-net check, not also
            # tripping the (unrelated) unconnected-power-pin check. BASELINE
            # separately satisfies the manifest's +170V_BUS existence
            # requirement.
            nets=[
                ("lonely", [("U1", "3")]),
                ("u1_power", [("U1", "1"), ("U1", "2")]),
            ]
            + BASELINE_NETS,
        )
        manifest_path = write_manifest(tmp_path)
        allowlist_path = write_allowlist(
            tmp_path,
            "allowlist:\n"
            "  - check: single_pin_net\n"
            "    net: \"lonely\"\n"
            "    reason: \"test justification\"\n",
        )
        code = run(netlist_path, manifest_path, src_dir, allowlist_path, skip_freshness=True)
        assert code == EXIT_OK

    def test_malformed_allowlist_is_gate_error(self, tmp_path: Path) -> None:
        allowlist_path = write_allowlist(tmp_path, "allowlist:\n  - check: single_pin_net\n")
        with pytest.raises(GateError, match="missing 'reason'"):
            load_allowlist(allowlist_path)

    def test_allowlist_entry_with_no_key_fields_is_gate_error(self, tmp_path: Path) -> None:
        allowlist_path = write_allowlist(
            tmp_path, "allowlist:\n  - check: single_pin_net\n    reason: \"x\"\n"
        )
        with pytest.raises(GateError, match="no key fields"):
            load_allowlist(allowlist_path)

    def test_missing_allowlist_file_is_empty_not_an_error(self, tmp_path: Path) -> None:
        assert load_allowlist(tmp_path / "does_not_exist.yaml") == []


# ---------------------------------------------------------------------------
# TestAntiVacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_missing_netlist_file(self, tmp_path: Path) -> None:
        src_dir = write_ato_source(tmp_path, "    u1 = new TestIC\n")
        manifest_path = write_manifest(tmp_path)
        code = run(
            tmp_path / "does_not_exist.net", manifest_path, src_dir, tmp_path / "none.yaml",
            skip_freshness=True,
        )
        assert code == EXIT_GATE_ERROR

    def test_missing_manifest_file(self, tmp_path: Path) -> None:
        src_dir = write_ato_source(tmp_path, "    u1 = new TestIC\n")
        netlist_path = write_netlist(tmp_path, [("U1", "u1")], [("n1", [("U1", "1")]), ("n2", [("U1", "2")])])
        code = run(
            netlist_path, tmp_path / "does_not_exist.yaml", src_dir, tmp_path / "none.yaml",
            skip_freshness=True,
        )
        assert code == EXIT_GATE_ERROR

    def test_domain_with_no_explicit_voltage_net_is_gate_error(self, tmp_path: Path) -> None:
        manifest = write_manifest(
            tmp_path,
            "schema_version: 1\ndomains:\n  HV:\n    nets: [\"ac_l\"]\n  SELV:\n    nets: [\"gnd\"]\n",
        )
        loaded = load_manifest(manifest)
        with pytest.raises(GateError, match="no net across any declared domain"):
            compute_net_voltage_floors(loaded)

    def test_root_class_missing_is_gate_error(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "components.ato").write_text(COMPONENTS_ATO)
        (src_dir / "main.ato").write_text("module NotTop:\n    u1 = new TestIC\n")
        classes = parse_ato_classes([src_dir / n for n in ATO_SOURCE_FILES])
        with pytest.raises(GateError, match="not found"):
            resolve_instances(classes, root="Top")

    def test_instantiation_cycle_is_gate_error(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "components.ato").write_text(COMPONENTS_ATO)
        (src_dir / "main.ato").write_text(
            "module Top:\n    child = new Cyclic\n"
            "\nmodule Cyclic:\n    back = new Top\n"
        )
        classes = parse_ato_classes([src_dir / n for n in ATO_SOURCE_FILES])
        with pytest.raises(GateError, match="cycle"):
            resolve_instances(classes, root="Top")

    def test_stray_top_level_instantiation_not_misattributed(self, tmp_path: Path) -> None:
        """`temper = new Top` at column 0, after Top's body, must not become
        a fake self-instantiation of Top (which would otherwise recurse
        forever) -- the specific hazard parse_ato_classes()'s docstring
        names and its indent-tracking logic exists to prevent."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "components.ato").write_text(COMPONENTS_ATO)
        (src_dir / "main.ato").write_text(
            "module Top:\n    u1 = new TestIC\n\ntemper = new Top\n"
        )
        classes = parse_ato_classes([src_dir / n for n in ATO_SOURCE_FILES])
        resolved = resolve_instances(classes, root="Top")  # must not raise / hang
        assert set(resolved) == {"u1"}

    def test_zero_classes_parsed_is_gate_error_via_run(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()  # no .ato files at all
        netlist_path = write_netlist(tmp_path, [("U1", "u1")], [("n1", [("U1", "1")]), ("n2", [("U1", "2")])])
        manifest_path = write_manifest(tmp_path)
        code = run(netlist_path, manifest_path, src_dir, tmp_path / "none.yaml", skip_freshness=True)
        assert code == EXIT_GATE_ERROR


# ---------------------------------------------------------------------------
# TestFailBeforePassAfter
# ---------------------------------------------------------------------------


class TestFailBeforePassAfter:
    def test_single_pin_net_before_fails_after_passes(self, tmp_path: Path) -> None:
        src_dir = write_ato_source(
            tmp_path, "    u1 = new TestIC\n    u2 = new TestIC\n" + BASELINE_ATO_BODY
        )
        manifest_path = write_manifest(tmp_path)
        allowlist_path = tmp_path / "none.yaml"

        # U1/U2's VCC/GND pins (1/2) are each wired together across the two
        # components (2-node nets) so this pair stays scoped to the
        # single-pin-net check, not also tripping the unrelated
        # unconnected-power-pin check.
        power_nets = [("vcc", [("U1", "1"), ("U2", "1")]), ("gnd", [("U1", "2"), ("U2", "2")])]

        before_path = write_netlist(
            tmp_path,
            components=[("U1", "u1"), ("U2", "u2")] + BASELINE_COMPONENTS,
            nets=[("sig", [("U1", "3")])] + power_nets + BASELINE_NETS,  # single-pin: no far end
            name="before.net",
        )
        assert run(before_path, manifest_path, src_dir, allowlist_path, skip_freshness=True) == EXIT_VIOLATION

        after_path = write_netlist(
            tmp_path,
            components=[("U1", "u1"), ("U2", "u2")] + BASELINE_COMPONENTS,
            nets=[("sig", [("U1", "3"), ("U2", "3")])] + power_nets + BASELINE_NETS,  # now properly connected
            name="after.net",
        )
        assert run(after_path, manifest_path, src_dir, allowlist_path, skip_freshness=True) == EXIT_OK

    def test_voltage_domain_before_fails_after_passes(self, tmp_path: Path) -> None:
        manifest_path = write_manifest(tmp_path)
        allowlist_path = tmp_path / "none.yaml"

        src_before = write_ato_source(
            tmp_path, "    r1 = new TestResistor\n    r1.voltage_rating = 25V\n",
        )
        before_path = write_netlist(
            tmp_path,
            components=[("R1", "r1")],
            # Both r1 pins share "+170V_BUS" -- avoids an unrelated
            # single-pin-net finding contaminating this voltage-domain-
            # specific before/after pair.
            nets=[("+170V_BUS", [("R1", "1"), ("R1", "2")])],
            name="before.net",
        )
        assert run(before_path, manifest_path, src_before, allowlist_path, skip_freshness=True) == EXIT_VIOLATION

        src_dir_after = tmp_path / "src_after"
        src_dir_after.mkdir()
        (src_dir_after / "components.ato").write_text(COMPONENTS_ATO)
        (src_dir_after / "main.ato").write_text(
            "module Top:\n    r1 = new TestResistor\n    r1.voltage_rating = 250V\n"
        )
        after_path = write_netlist(
            tmp_path,
            components=[("R1", "r1")],
            nets=[("+170V_BUS", [("R1", "1"), ("R1", "2")])],
            name="after.net",
        )
        assert run(after_path, manifest_path, src_dir_after, allowlist_path, skip_freshness=True) == EXIT_OK

    def test_unconnected_power_pin_before_fails_after_passes(self, tmp_path: Path) -> None:
        src_dir = write_ato_source(
            tmp_path, "    u1 = new TestIC\n    u2 = new TestIC\n" + BASELINE_ATO_BODY
        )
        manifest_path = write_manifest(tmp_path)
        allowlist_path = tmp_path / "none.yaml"

        # SIG pins (U1.3/U2.3) are omitted entirely from both netlists below
        # (never referenced) -- a pin genuinely absent from the compiled
        # netlist produces no net record at all and is not itself a
        # single-pin-net finding, keeping this pair scoped to the power-pin
        # check specifically.
        before_path = write_netlist(
            tmp_path,
            components=[("U1", "u1"), ("U2", "u2")] + BASELINE_COMPONENTS,
            nets=[
                ("vcc", [("U1", "1")]),  # isolated -- floating power pin
                ("gnd", [("U1", "2"), ("U2", "2")]),
                ("vcc2", [("U2", "1")]),
            ]
            + BASELINE_NETS,
            name="before.net",
        )
        assert run(before_path, manifest_path, src_dir, allowlist_path, skip_freshness=True) == EXIT_VIOLATION

        after_path = write_netlist(
            tmp_path,
            components=[("U1", "u1"), ("U2", "u2")] + BASELINE_COMPONENTS,
            nets=[
                ("vcc", [("U1", "1"), ("U2", "1")]),  # now shared, both connected
                ("gnd", [("U1", "2"), ("U2", "2")]),
            ]
            + BASELINE_NETS,
            name="after.net",
        )
        assert run(after_path, manifest_path, src_dir, allowlist_path, skip_freshness=True) == EXIT_OK
