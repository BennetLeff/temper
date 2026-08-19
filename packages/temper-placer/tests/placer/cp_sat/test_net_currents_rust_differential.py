"""Net-current resolution: single-SSOT, fail-closed, real-board-net tests.

HISTORY OF THIS FILE, and why it no longer tests a differential.

It used to pin ``temper_drc_rs.get_net_current`` (case-insensitive
SUBSTRING) against ``StackupGate._DEFAULT_NET_CURRENTS`` (exact ``dict.get``),
two hand-kept copies of the same table, and recorded their divergence as an
accepted gap under the dispatch rule "keep the Python exact-match as the
authority". That rule resolved every disagreement in favour of the Python
table -- which, because the board spells its mains nets ``ac_l``/``ac_n`` in
lower case and the table's keys were ``AC_L``/``AC_N``, meant resolving them
to the 0.1 A default and DISCARDING the Rust kernel's correct 15.0 A.

The Python duplicate has been deleted (AGENTS.md's standing rule: fix the
Rust, then delete the Python; never leave two homes "in agreement"), so
there is no longer a differential to run. What replaces it is the property
the differential should have been testing all along.

AGENTS.md names this file's predecessor as the cautionary example:

    "A differential test only proves what you feed it. The Rust/Python
    ampacity divergence above survived a genuinely-running differential
    test because that test's input was ``"Gate_H"`` -- a net name absent
    from this board. Both sides looked it up, both agreed, green."

So every test below is driven from ``pcb/temper.kicad_pcb``'s own net table
and ``elec/domain_manifest.yaml``'s HV declaration, never from a
hand-written fixture name. A test that cannot see the real board cannot
witness this defect class.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import temper_drc_rs
import yaml
from temper_placer.placer.cp_sat.gates import StackupGate

_REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from check_hv_netclass_coverage import parse_board_net_names  # noqa: E402

BOARD_NETS = sorted(parse_board_net_names(_REPO_ROOT / "pcb" / "temper.kicad_pcb"))
HV_NETS = sorted(
    yaml.safe_load((_REPO_ROOT / "elec" / "domain_manifest.yaml").read_text())["domains"]["HV"][
        "nets"
    ]
)


# ---------------------------------------------------------------------------
# The duplicate is gone
# ---------------------------------------------------------------------------


def test_python_duplicate_table_is_deleted():
    """The second home must not come back.

    Two hand-kept copies of a safety table agree on the day they are
    written and drift afterwards; this pair drifted into a 150x
    understatement of the mains current.
    """
    assert not hasattr(StackupGate, "_DEFAULT_NET_CURRENTS")
    assert not hasattr(StackupGate, "_DEFAULT_CURRENT")


# ---------------------------------------------------------------------------
# Fail-closed resolution
# ---------------------------------------------------------------------------


def test_unknown_net_resolves_to_none_not_a_default():
    """The core fix. An undeclared net must be distinguishable from a
    declared signal net -- it was not, and that is the whole defect."""
    assert temper_drc_rs.try_net_design_current_a("NO_SUCH_NET_ANYWHERE") is None
    assert StackupGate.__new__(StackupGate)._resolve_net_current("NO_SUCH_NET_ANYWHERE") is None


def test_unknown_net_raises_from_the_raising_accessor():
    with pytest.raises(KeyError) as exc:
        temper_drc_rs.get_net_current("NO_SUCH_NET_ANYWHERE")
    assert "NO_SUCH_NET_ANYWHERE" in str(exc.value)


@pytest.mark.parametrize("ghost", ["DC_BUS+", "DC_BUS-", "+5V", "GATE_H", "GATE_L", "AC_MAINS"])
def test_ghost_vocabulary_does_not_resolve(ghost):
    """Keys from the superseded schematic revision name no conductor on
    this board and must not answer for one."""
    assert temper_drc_rs.try_net_design_current_a(ghost) is None


@pytest.mark.parametrize(
    "superset", ["NET_SW_NODE_1", "+3V3_SENSE", "XGATE_HSY", "Net-(C1-Pad1)-DC_BUS+"]
)
def test_substring_supersets_do_not_resolve(superset):
    """Matching is exact, never containment. The old substring walk also
    iterated a HashMap, so a name containing two keys resolved
    non-deterministically."""
    assert temper_drc_rs.try_net_design_current_a(superset) is None


# ---------------------------------------------------------------------------
# Real board coverage -- the tests the old differential could not express
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("net", HV_NETS)
def test_every_hv_domain_net_has_a_declared_current(net):
    """Every mains/HV-domain conductor resolves to a real, positive current.

    Driven from elec/domain_manifest.yaml, so a net added to the HV domain
    without an ampacity figure fails here immediately.
    """
    current = temper_drc_rs.try_net_design_current_a(net)
    assert current is not None, f"HV-domain net {net!r} has no declared design current"
    assert current > 0.0


@pytest.mark.parametrize(
    ("net", "expected_a"),
    [
        # The conductors that silently resolved to 0.1 A before the fix.
        ("+170V_BUS", 22.5),
        ("DC_BUS_RTN", 22.5),
        ("PWR_RTN", 22.5),
        ("SW_NODE", 22.5),
        ("tank-out", 22.5),
        ("tank.c_tank1-p2", 22.5),
        ("hb-gnd", 22.5),
        ("w1_1", 15.0),
        ("w1_2", 15.0),
        ("power_in.ntc-no", 15.0),
        # These two resolved correctly in Rust but were overridden to 0.1 A
        # by the deleted Python table's exact, case-sensitive lookup.
        ("ac_l", 15.0),
        ("ac_n", 15.0),
    ],
)
def test_power_conductors_resolve_to_their_cited_current(net, expected_a):
    assert net in BOARD_NETS, f"{net!r} is not a real board net -- fixture is stale"
    assert temper_drc_rs.try_net_design_current_a(net) == pytest.approx(expected_a)


def test_gate_path_and_width_path_agree_on_every_board_net():
    """The DRC gate that CHECKS copper and the resolver that SIZES it read
    the same single table. They disagreed for the mains nets before the
    Python duplicate was deleted."""
    gate = StackupGate.__new__(StackupGate)
    for net in BOARD_NETS:
        assert gate._resolve_net_current(net) == temper_drc_rs.try_net_design_current_a(net)


def test_no_table_key_is_a_ghost():
    """Every declared key names a real board net (case-insensitively)."""
    lowered = {n.lower() for n in BOARD_NETS}
    ghosts = sorted(k for k in temper_drc_rs.NET_CURRENTS if k.lower() not in lowered)
    assert not ghosts, f"net_currents() keys naming no board net: {ghosts}"


# ---------------------------------------------------------------------------
# The rating parameter
# ---------------------------------------------------------------------------


def test_tank_bus_current_derives_from_the_declared_rating():
    """The bus/tank figure is derived from RATED_OUTPUT_POWER_W, not baked
    in, so settling the pending rating decision moves the copper
    requirement instead of leaving a stale literal behind."""
    assert temper_drc_rs.tank_bus_rms_current_a() == pytest.approx(22.5)
    assert temper_drc_rs.RATED_OUTPUT_POWER_W == pytest.approx(1800.0)
    for net in ("+170V_BUS", "DC_BUS_RTN", "PWR_RTN", "SW_NODE", "tank-out"):
        assert temper_drc_rs.try_net_design_current_a(net) == pytest.approx(
            temper_drc_rs.tank_bus_rms_current_a()
        )


def test_ac_mains_does_not_scale_with_the_output_rating():
    """The mains conductors are sized to the branch-circuit limit
    (ACMainsConstraints.i_max), which does not move with output power."""
    assert temper_drc_rs.AC_MAINS_CURRENT_A == pytest.approx(15.0)
    for net in ("ac_l", "ac_n", "w1_1", "w1_2", "power_in.ntc-no"):
        assert temper_drc_rs.try_net_design_current_a(net) == pytest.approx(
            temper_drc_rs.AC_MAINS_CURRENT_A
        )
