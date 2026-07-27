"""Tests for capacity_budget_gate.py.

Covers:
  - the S-expression parser (unit)
  - reachability / occupancy classification on small synthetic netlists
    (unit) -- including the "AVAILABLE" path, to prove the checker is
    *capable* of reporting availability and isn't just unconditionally
    pessimistic
  - anti-vacuity: missing/empty netlist, missing/empty BOM, malformed
    netlist, and a required package with zero instances must all fail
    closed (never exit 0)
  - a capacity_defect fixture (real occupant wired into a dead-output
    gate) exits 3
  - an integration test against the real elec/build/ output (skipped if
    that gitignored directory hasn't been built) asserting the exact
    zero-available-SET-path-capacity finding from
    docs/hardware/UVL02_DESIGN.md SS7.1 and OCP02_DESIGN.md
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capacity_budget_gate import (  # noqa: E402
    AVAILABLE,
    GND_TIED,
    OCCUPIED,
    UNREFERENCED,
    GateError,
    _parse_sexp,
    _sexp_get_val,
    analyze,
    check_required_packages,
    classify_occupancy,
    load_identity,
    load_netlist,
    load_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_SCRIPT = REPO_ROOT / "scripts" / "capacity_budget_gate.py"
CONFIG_PATH = REPO_ROOT / "scripts" / "capacity_budget_packages.yaml"
REAL_NETLIST = REPO_ROOT / "elec" / "build" / "default.net"
REAL_BOM = REPO_ROOT / "elec" / "build" / "default.csv"


# --------------------------------------------------------------------------
# S-expression parser
# --------------------------------------------------------------------------


def test_parse_sexp_basic_nesting():
    tree = _parse_sexp('(export (a "1") (b (c "2") (c "3")))')
    assert tree == [["export", ["a", "1"], ["b", ["c", "2"], ["c", "3"]]]]


def test_parse_sexp_escaped_quote_in_string():
    tree = _parse_sexp(r'(net (name "a \"weird\" name"))')
    assert _sexp_get_val(tree[0], "name") == 'a "weird" name'


def test_parse_sexp_unbalanced_parens_raises():
    with pytest.raises(GateError):
        _parse_sexp("(export (a 1)")


def test_parse_sexp_unterminated_string_raises():
    with pytest.raises(GateError):
        _parse_sexp('(export (a "unterminated)')


# --------------------------------------------------------------------------
# Synthetic netlist fixtures
# --------------------------------------------------------------------------

MINIMAL_NET_TEMPLATE = """
(export (version "E")
  (design)
  (components
    (comp (ref "U1")
      (value "?")
      (footprint "Package_SO:SOIC-14")
      (libsource (lib "lib") (part "SN74HC4075DR") (description "x"))
      (sheetpath (names "/x/main.ato:Top::safety.fault_or") (tstamps "a1"))
      (tstamps "a1"))
    (comp (ref "U2")
      (value "?")
      (footprint "Package_SO:SOIC-14")
      (libsource (lib "lib") (part "SN74HC00DR") (description "x"))
      (sheetpath (names "/x/main.ato:Top::safety.latch") (tstamps "a2"))
      (tstamps "a2"))
    {extra_components})
  (nets
    (net (code "1") (name "U1-A1") {a1_extra})
    (net (code "2") (name "U1-B1") (node (ref "U1") (pin "2")))
    (net (code "3") (name "U1-C1") (node (ref "U1") (pin "8")))
    (net (code "4") (name "U1-Y1") {y1_extra})
    (net (code "5") (name "U1-A2") (node (ref "U1") (pin "3")))
    (net (code "6") (name "U1-B2") (node (ref "U1") (pin "4")))
    (net (code "7") (name "U1-C2") (node (ref "U1") (pin "5")))
    (net (code "8") (name "U1-Y2") (node (ref "U1") (pin "6")))
    (net (code "9") (name "U1-GND") (node (ref "U1") (pin "7")))
    (net (code "10") (name "U1-A3") (node (ref "U1") (pin "11")))
    (net (code "11") (name "U1-B3") (node (ref "U1") (pin "12")))
    (net (code "12") (name "U1-C3") (node (ref "U1") (pin "13")))
    (net (code "13") (name "U1-Y3") (node (ref "U1") (pin "10")))
    (net (code "14") (name "U1-VCC") (node (ref "U1") (pin "14")))
    (net (code "15") (name "U2-A1-SET") {set_extra})
    (net (code "16") (name "U2-A3-RESET") {reset_extra})))
"""

MINIMAL_CSV = """Comment,Designator,Footprint,LCSC,Price
SN74HC4075DR,U1,Package_SO:SOIC-14,SN74HC4075DR,0.00
SN74HC00DR,U2,Package_SO:SOIC-14,SN74HC00DR,0.00
"""


def _write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def test_gate1_available_when_output_reaches_set(tmp_path):
    """An unreferenced input whose gate's Y1 is wired straight to the SET
    pin must be reported AVAILABLE -- proves the checker isn't
    unconditionally pessimistic.
    """
    net_text = MINIMAL_NET_TEMPLATE.format(
        extra_components="",
        a1_extra='(node (ref "U1") (pin "1"))',
        y1_extra='(node (ref "U1") (pin "9")) (node (ref "U2") (pin "1"))',
        set_extra="",
        reset_extra='(node (ref "U2") (pin "9"))',
    )
    netlist = load_netlist(_write(tmp_path / "n.net", net_text))
    ref_to_mpn = load_identity(_write(tmp_path / "b.csv", MINIMAL_CSV))
    registry = load_registry(CONFIG_PATH)
    check_required_packages(netlist, ref_to_mpn, registry)
    report = analyze(netlist, ref_to_mpn, registry)

    gate1_a1 = next(
        g for g in report.packages[0].gates if g.gate_name == "gate1" and g.pin_name == "A1"
    )
    assert gate1_a1.verdict == AVAILABLE
    assert gate1_a1.occupancy == UNREFERENCED
    assert report.total_available == 3  # A1, B1, C1 of gate1 all reach SET
    assert report.defects == []


def test_gnd_tied_input_on_dead_gate_is_unusable(tmp_path):
    """All-GND-tied inputs on a gate whose output drives nothing must be
    UNUSABLE, not AVAILABLE, even though the pins themselves are free.
    """
    net_text = MINIMAL_NET_TEMPLATE.format(
        extra_components="",
        a1_extra='(node (ref "U1") (pin "1"))',
        y1_extra='(node (ref "U1") (pin "9"))',  # Y1 singleton: dead gate
        set_extra='(node (ref "U2") (pin "1"))',
        reset_extra='(node (ref "U2") (pin "9"))',
    )
    # Tie A1 to the package's own GND net (net 9, U1 pin 7) by re-pointing it.
    net_text = net_text.replace(
        '(net (code "1") (name "U1-A1") (node (ref "U1") (pin "1")))',
        '(net (code "9") (name "GND") (node (ref "U1") (pin "7")) (node (ref "U1") (pin "1")))',
    )
    netlist = load_netlist(_write(tmp_path / "n.net", net_text))
    ref_to_mpn = load_identity(_write(tmp_path / "b.csv", MINIMAL_CSV))
    registry = load_registry(CONFIG_PATH)
    report = analyze(netlist, ref_to_mpn, registry)

    a1 = next(g for g in report.packages[0].gates if g.gate_name == "gate1" and g.pin_name == "A1")
    assert a1.occupancy == GND_TIED
    assert a1.verdict != AVAILABLE
    assert "dead gate" in a1.reason


def test_reset_qualifier_only_path_is_unusable_not_available(tmp_path):
    """A gate whose output reaches ONLY the reset-qualifier pin (not SET)
    must be reported UNUSABLE with that specific reason -- this is the
    fault_any_or.C2 case from the real design.
    """
    net_text = MINIMAL_NET_TEMPLATE.format(
        extra_components="",
        a1_extra='(node (ref "U1") (pin "1"))',
        y1_extra='(node (ref "U1") (pin "9")) (node (ref "U2") (pin "9"))',  # -> RESET only
        set_extra='(node (ref "U2") (pin "1"))',  # SET pin must still exist as its own net
        reset_extra="",
    )
    netlist = load_netlist(_write(tmp_path / "n.net", net_text))
    ref_to_mpn = load_identity(_write(tmp_path / "b.csv", MINIMAL_CSV))
    registry = load_registry(CONFIG_PATH)
    report = analyze(netlist, ref_to_mpn, registry)

    a1 = next(g for g in report.packages[0].gates if g.gate_name == "gate1" and g.pin_name == "A1")
    assert a1.verdict != AVAILABLE
    assert "reset-qualifier" in a1.reason
    assert report.total_available == 0


def test_capacity_defect_real_occupant_on_dead_gate(tmp_path):
    """A real (non-GND, non-cascade) occupant driving an input whose gate
    output is a dead end must be reported as a blocking defect.
    """
    net_text = MINIMAL_NET_TEMPLATE.format(
        extra_components=(
            '(comp (ref "R1") (value "10k") (footprint "R_0603") '
            '(libsource (lib "lib") (part "R") (description "x")) '
            '(sheetpath (names "/x/main.ato:Top::foo.r1") (tstamps "a3")) (tstamps "a3"))'
        ),
        a1_extra='(node (ref "U1") (pin "1")) (node (ref "R1") (pin "1"))',
        y1_extra='(node (ref "U1") (pin "9"))',  # dead
        set_extra='(node (ref "U2") (pin "1"))',
        reset_extra='(node (ref "U2") (pin "9"))',
    )
    netlist = load_netlist(_write(tmp_path / "n.net", net_text))
    csv_text = MINIMAL_CSV + "10k,R1,R_0603,RC0603,0.00\n"
    ref_to_mpn = load_identity(_write(tmp_path / "b.csv", csv_text))
    registry = load_registry(CONFIG_PATH)
    report = analyze(netlist, ref_to_mpn, registry)

    assert len(report.defects) == 1
    assert "gate1" in report.defects[0]
    assert "drives nothing" in report.defects[0]


def test_cascade_input_is_not_flagged_as_defect(tmp_path):
    """An input driven by another aggregator gate's own output (a cascade
    link) must not itself be reported as a "real occupant" for defect
    purposes -- cascades are deliberate design elements.
    """
    net_text = MINIMAL_NET_TEMPLATE.format(
        extra_components="",
        a1_extra="",
        y1_extra='(node (ref "U1") (pin "9")) (node (ref "U1") (pin "3"))',  # Y1 -> A2 cascade
        set_extra='(node (ref "U2") (pin "1"))',  # SET pin must still exist as its own net
        reset_extra="",
    )
    net_text = net_text.replace(
        '(net (code "5") (name "U1-A2") (node (ref "U1") (pin "3")))',
        "",
    )
    netlist = load_netlist(_write(tmp_path / "n.net", net_text))
    ref_to_mpn = load_identity(_write(tmp_path / "b.csv", MINIMAL_CSV))
    registry = load_registry(CONFIG_PATH)
    report = analyze(netlist, ref_to_mpn, registry)

    a2 = next(g for g in report.packages[0].gates if g.gate_name == "gate2" and g.pin_name == "A2")
    assert a2.occupancy == OCCUPIED
    assert "cascade" in a2.reason
    # Y1 is a dead end (no path to SET) but has ONLY a cascade occupant on
    # its own input (A1/B1/C1 unreferenced) -- gate1 must not be flagged.
    assert not any("gate1" in d for d in report.defects)


# --------------------------------------------------------------------------
# Anti-vacuity: fail-closed proofs
# --------------------------------------------------------------------------


def _run_gate(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE_SCRIPT)] + args,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_missing_netlist_fails_closed(tmp_path):
    result = _run_gate(["--netlist", str(tmp_path / "nope.net")])
    assert result.returncode == 5
    assert "not found" in result.stderr
    assert "PASSED" not in result.stdout


def test_empty_netlist_fails_closed(tmp_path):
    empty = tmp_path / "empty.net"
    empty.write_text("")
    result = _run_gate(["--netlist", str(empty)])
    assert result.returncode == 5
    assert "empty" in result.stderr


def test_missing_bom_fails_closed(tmp_path):
    result = _run_gate(["--bom", str(tmp_path / "nope.csv")])
    assert result.returncode == 5


def test_empty_bom_fails_closed(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("")
    result = _run_gate(["--bom", str(empty)])
    assert result.returncode == 5


def test_malformed_netlist_fails_closed(tmp_path):
    bad = tmp_path / "bad.net"
    bad.write_text("(export (components (comp (ref \"U1\"))")  # unbalanced
    result = _run_gate(["--netlist", str(bad)])
    assert result.returncode == 5


def test_required_package_absent_fails_closed(tmp_path):
    net = _write(
        tmp_path / "n.net",
        """
(export (version "E") (design)
  (components
    (comp (ref "R1") (value "10k") (footprint "R_0603")
      (libsource (lib "lib") (part "R") (description "x"))
      (sheetpath (names "/x/main.ato:Top::foo.r1") (tstamps "a1")) (tstamps "a1")))
  (nets
    (net (code "1") (name "N1") (node (ref "R1") (pin "1")))
    (net (code "2") (name "N2") (node (ref "R1") (pin "2")))))
""",
    )
    csv = _write(tmp_path / "b.csv", "Comment,Designator,Footprint,LCSC,Price\n10k,R1,R_0603,RC0603,0.00\n")
    result = _run_gate(["--netlist", str(net), "--bom", str(csv)])
    assert result.returncode == 5
    assert "zero instances" in result.stderr


def test_unrecognised_aggregator_mpn_in_config_fails_closed(tmp_path):
    """If fault_tree.aggregator_mpns names an MPN with no 'packages' entry,
    that is a config error and must fail closed, not silently skip it.
    """
    bad_config = tmp_path / "bad_packages.yaml"
    data = yaml.safe_load(CONFIG_PATH.read_text())
    data["fault_tree"]["aggregator_mpns"] = ["NOT_A_REAL_PART"]
    bad_config.write_text(yaml.safe_dump(data))
    result = _run_gate(["--config", str(bad_config)])
    assert result.returncode == 5
    assert "unrecognised package" in result.stderr


def test_two_destination_instances_is_ambiguous_and_fails_closed(tmp_path):
    net_text = MINIMAL_NET_TEMPLATE.format(
        extra_components=(
            '(comp (ref "U3") (value "?") (footprint "Package_SO:SOIC-14") '
            '(libsource (lib "lib") (part "SN74HC00DR") (description "x")) '
            '(sheetpath (names "/x/main.ato:Top::safety.latch2") (tstamps "a4")) (tstamps "a4"))'
        ),
        a1_extra="",
        y1_extra="",
        set_extra="",
        reset_extra="",
    )
    net = _write(tmp_path / "n.net", net_text)
    csv = _write(tmp_path / "b.csv", MINIMAL_CSV + "SN74HC00DR,U3,Package_SO:SOIC-14,SN74HC00DR,0.00\n")
    result = _run_gate(["--netlist", str(net), "--bom", str(csv)])
    assert result.returncode == 5
    assert "ambiguous" in result.stderr


# --------------------------------------------------------------------------
# Occupancy classification unit tests
# --------------------------------------------------------------------------


def test_classify_occupancy_unreferenced(tmp_path):
    net_text = MINIMAL_NET_TEMPLATE.format(
        extra_components="", a1_extra="", y1_extra="", set_extra="", reset_extra=""
    )
    netlist = load_netlist(_write(tmp_path / "n.net", net_text))
    occ, desc, code = classify_occupancy(netlist, {}, "U1", "1", own_gnd_net=None)
    assert occ == UNREFERENCED


def test_classify_occupancy_no_net_entry_at_all(tmp_path):
    net_text = MINIMAL_NET_TEMPLATE.format(
        extra_components="", a1_extra="", y1_extra="", set_extra="", reset_extra=""
    )
    # Remove net 1 entirely so U1 pin 1 has no net entry.
    net_text = net_text.replace('(net (code "1") (name "U1-A1") )', "")
    netlist = load_netlist(_write(tmp_path / "n.net", net_text))
    occ, desc, code = classify_occupancy(netlist, {}, "U1", "1", own_gnd_net=None)
    assert occ == UNREFERENCED
    assert code is None


# --------------------------------------------------------------------------
# Integration: the real build (skipped if elec/build/ hasn't been made)
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    not (REAL_NETLIST.is_file() and REAL_BOM.is_file()),
    reason="elec/build/ is gitignored; run `make netlist` first",
)
def test_real_tree_reports_zero_available_set_path_inputs():
    """The falsifier for this whole gate: on the tree that motivated this
    check, docs/hardware/UVL02_DESIGN.md SS7.1 and OCP02_DESIGN.md both
    assert, by manual survey, that zero SET-path inputs are available
    across fault_or and fault_any_or. If this test ever finds a free
    input, the CHECK is wrong -- go verify against the design docs before
    touching this assertion.
    """
    netlist = load_netlist(REAL_NETLIST)
    ref_to_mpn = load_identity(REAL_BOM)
    registry = load_registry(CONFIG_PATH)
    check_required_packages(netlist, ref_to_mpn, registry)
    report = analyze(netlist, ref_to_mpn, registry)

    assert report.total_available == 0, (
        f"Expected 0 available SET-path inputs (per UVL02_DESIGN.md SS7.1); "
        f"got {report.total_available}. Investigate before adjusting this "
        f"assertion -- the design docs are the ground truth here."
    )
    assert report.total_inputs == 18  # 2 packages x 3 gates x 3 inputs
    assert len(report.packages) == 2
    assert report.defects == []

    # Spot-check the specific reasons the design docs give for each
    # "looks free" input, so a regression in *why* is caught even though
    # the headline number (0) can't move.
    all_results = [g for pkg in report.packages for g in pkg.gates]

    # fault_or gate3 (all 3 inputs GND-tied, dead output)
    fault_or_g3 = [g for g in all_results if g.gate_name == "gate3" and g.instance_path == "safety.fault_or"]
    assert len(fault_or_g3) == 3
    for g in fault_or_g3:
        assert g.occupancy == GND_TIED
        assert "dead gate" in g.reason

    # fault_any_or gate3 (all 3 inputs entirely unreferenced, dead output)
    fault_any_or_g3 = [
        g for g in all_results if g.gate_name == "gate3" and g.instance_path == "safety.fault_any_or"
    ]
    assert len(fault_any_or_g3) == 3
    for g in fault_any_or_g3:
        assert g.occupancy == UNREFERENCED
        assert "dead gate" in g.reason

    # fault_any_or.C1 is occupied (claimed by THM-02) -- must show up as
    # OCCUPIED, not available, per the d99c88e2 finding.
    c1 = next(
        g
        for g in all_results
        if g.instance_path == "safety.fault_any_or" and g.gate_name == "gate1" and g.pin_name == "C1"
    )
    assert c1.occupancy == OCCUPIED
    assert c1.verdict != AVAILABLE

    # fault_any_or.C2 is GND-tied but reaches only the reset qualifier.
    c2 = next(
        g
        for g in all_results
        if g.instance_path == "safety.fault_any_or" and g.gate_name == "gate2" and g.pin_name == "C2"
    )
    assert c2.occupancy == GND_TIED
    assert "reset-qualifier" in c2.reason


@pytest.mark.skipif(
    not (REAL_NETLIST.is_file() and REAL_BOM.is_file()),
    reason="elec/build/ is gitignored; run `make netlist` first",
)
def test_real_tree_cli_exits_zero_not_three():
    """0 available capacity is a legitimate state (human decision pending,
    see UVL02_DESIGN.md SS7.1), not a bug -- the gate must exit 0 (with a
    warning), not 3, on today's tree.
    """
    result = _run_gate([])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout
    assert "0 genuinely available" in result.stdout
