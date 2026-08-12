"""Net classification at parse time -- regression for the "every net is
Signal" defect.

Root cause (fixed here): the ``Net`` pyclass constructor
(``packages/temper-design-bundle/src/netlist_contracts.rs``) defaults
``net_class`` to ``"Signal"`` when the caller supplies nothing, and the
parser (``parse_engine.rs``, reached via ``temper_placer.io.kicad_parser``)
never supplied one. The project's real net-class SSOT,
``TEMPER_NET_ASSIGNMENTS`` (``temper_placer.core.design_rules``), was never
consulted at parse time, so ``collections.Counter(n.net_class for n in
parsed.netlist.nets)`` came back ``{"Signal": 110}`` for the entire
production board -- mains live, mains neutral, ground, and the +170V DC bus
were indistinguishable to every downstream Rust DRC/clearance check.

Fix: ``kicad_parser.parse_kicad_pcb`` now passes ``TEMPER_NET_ASSIGNMENTS``
into the Rust parse engine's ``net_class_mapping`` parameter by default,
which applies it (via the already-existing, already-tested
``Netlist.apply_net_class_mapping``) to the freshly built netlist before
returning -- so classification happens in Rust, at parse time, driven by a
single Python-owned SSOT table (never transcribed into Rust).

These tests fail on the pre-fix code: every assertion below that a named
mains/HV net gets a non-``"Signal"`` class is false against the old
``_rs.parse_kicad_pcb(content, normalize=normalize)`` (no mapping argument
at all).
"""

from __future__ import annotations

import collections
from pathlib import Path

import pytest

from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS
from temper_placer.io.kicad_parser import parse_kicad_pcb

PCB_PATH = Path("pcb/temper.kicad_pcb")


def _skip_if_board_missing() -> None:
    if not PCB_PATH.exists():
        pytest.skip("production board not yet generated")


def test_production_board_nets_are_not_all_signal() -> None:
    """The pre-fix defect, verbatim: every net classified as "Signal".

    On the pre-fix parser this Counter comes back as ``{"Signal": 110}`` --
    a single key. Real classification must produce more than one distinct
    net class.
    """
    _skip_if_board_missing()

    result = parse_kicad_pcb(PCB_PATH)
    counts = collections.Counter(n.net_class for n in result.netlist.nets)

    assert len(counts) > 1, (
        f"every net classified identically ({counts!r}) -- net classification "
        "did not run; TEMPER_NET_ASSIGNMENTS was not applied at parse time"
    )
    assert counts.keys() != {"Signal"}, f"every net is still 'Signal': {counts!r}"


@pytest.mark.parametrize(
    ("net_name", "expected_class"),
    [
        # Mains AC, straight off the board's own lowercase net names (not
        # the historical uppercase "AC_L"/"AC_N" aliases TEMPER_NET_ASSIGNMENTS
        # also carries for other boards/fixtures).
        ("ac_l", "ACMains"),
        ("ac_n", "ACMains"),
        # The 170V DC bus and its return / switch node.
        ("+170V_BUS", "HighVoltage"),
        ("DC_BUS_RTN", "HighVoltage"),
        ("SW_NODE", "HighVoltage"),
        # Gate-drive nets, split HV (secondary/floating side) vs. SELV
        # (primary/MCU side) per the R4 GateDrive split.
        ("GATE_HS", "GateDriveHV"),
        ("GATE_LS", "GateDriveHV"),
        ("PWM_HS", "GateDriveSELV"),
        ("PWM_LS", "GateDriveSELV"),
    ],
)
def test_named_mains_and_hv_nets_classify_correctly(
    net_name: str, expected_class: str
) -> None:
    """Every net this task's own defect report names by name must resolve
    to its real class, not the "Signal" default.

    Also asserts the expectation is consistent with the live
    ``TEMPER_NET_ASSIGNMENTS`` SSOT -- if that table's own assignment for
    this net ever changes, this test's hardcoded expectation must be
    updated deliberately, not silently pass against a stale value.
    """
    _skip_if_board_missing()

    assert TEMPER_NET_ASSIGNMENTS.get(net_name) == expected_class, (
        f"test fixture out of sync with TEMPER_NET_ASSIGNMENTS: expected "
        f"{net_name!r} -> {expected_class!r}, SSOT says "
        f"{TEMPER_NET_ASSIGNMENTS.get(net_name)!r}"
    )

    result = parse_kicad_pcb(PCB_PATH)
    net = result.netlist.get_net(net_name)

    assert net.net_class == expected_class, (
        f"net {net_name!r} classified as {net.net_class!r}, expected "
        f"{expected_class!r} per TEMPER_NET_ASSIGNMENTS"
    )


def test_gnd_net_is_a_known_ssot_gap_not_a_parser_bug() -> None:
    """``"gnd"`` -- the board's real, primary ground net (distinct from the
    smaller ``PWR_RTN``/``CGND`` nets ``TEMPER_NET_ASSIGNMENTS`` does map to
    "GND") -- has NO entry in ``TEMPER_NET_ASSIGNMENTS`` at all, so it
    correctly falls through to the "Signal" default under this parser fix.

    This is a real, pre-existing gap in the net-class SSOT table itself
    (out of scope for the parser-wiring fix this test file otherwise
    covers) -- pinned here so it is visible and doesn't silently re-hide
    now that classification actually runs, and so a future SSOT fix has an
    explicit test to flip.
    """
    _skip_if_board_missing()

    assert "gnd" not in TEMPER_NET_ASSIGNMENTS, (
        "TEMPER_NET_ASSIGNMENTS now has a 'gnd' entry -- update this test's "
        "expected_class instead of leaving it pinned to the historical gap"
    )

    result = parse_kicad_pcb(PCB_PATH)
    net = result.netlist.get_net("gnd")
    assert net.net_class == "Signal"


def test_net_class_mapping_none_means_disabled_not_default() -> None:
    """``net_class_mapping={}`` is the documented opt-out -- explicitly
    passing an empty mapping must leave every net at the raw "Signal"
    default, proving the SSOT default is applied by ``parse_kicad_pcb``
    itself (not unconditionally inside the Rust engine)."""
    _skip_if_board_missing()

    result = parse_kicad_pcb(PCB_PATH, net_class_mapping={})
    counts = collections.Counter(n.net_class for n in result.netlist.nets)

    assert counts.keys() == {"Signal"}, (
        f"expected every net at the 'Signal' default with mapping disabled, got {counts!r}"
    )


def test_net_class_mapping_override_takes_precedence_over_ssot() -> None:
    """A caller-supplied mapping overrides the default SSOT table entirely
    (not merged with it)."""
    _skip_if_board_missing()

    result = parse_kicad_pcb(PCB_PATH, net_class_mapping={"ac_l": "CustomClass"})
    net = result.netlist.get_net("ac_l")
    assert net.net_class == "CustomClass"

    # A net the override doesn't mention keeps the raw default -- the
    # override is not merged with TEMPER_NET_ASSIGNMENTS.
    other = result.netlist.get_net("ac_n")
    assert other.net_class == "Signal"
