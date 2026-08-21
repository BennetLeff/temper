"""A pad that declares no copper layer is not copper.

WHAT THIS PINS. ``parse_kicad_pcb`` reported ``Pin.layer == "F.Cu"`` for every
pad that declares no copper layer at all -- ``extract_components_pure``'s
``copper.first().unwrap_or("F.Cu")``. On ``pcb/temper.kicad_pcb`` that is
``K1.13`` and ``K1.14``, ``(layers "F.Fab")``: the Omron G4A-1A-E's #250 Faston
quick-connect tabs, which the footprint's own ``descr`` states have "zero PCB
copper connection on this variant". They are pad-shaped fabrication
*documentation*, and they carry mains nets (``power_in.ntc-no``, ``w1_2``), so
every copper-distance census that took ``Pin.layer`` at face value put two
phantom mains conductors on the board.

``Pin.layer`` itself is NOT corrected here and cannot be: its ``"F.Cu"``
fallback is pinned byte-for-byte by two oracles this change may not re-pin --
``tests/io/_parse_engine_py_oracle/_parse_modules.py``
(``layer = copper_layers[0] if copper_layers else "F.Cu"``) and
``tests/core/_netlist_py_oracle.py``'s field list. ``Pin.is_copper`` routes
around it, reading the pad's own declared ``(layers ...)``.

Both directions are asserted, because a predicate that says "no pad is copper"
would also remove the false violations: a real copper pad must stay copper, on
every spelling KiCad writes (``F.Cu``, ``B.Cu``, ``In1.Cu``, the through-hole
wildcard ``*.Cu``, and the both-sides ``F&B.Cu``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from temper_placer.core.netlist import Pin
from temper_placer.io.kicad_parser import parse_kicad_pcb

REPO_ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"

# The two `(layers "F.Fab")` pads on the production board, and the net each one
# carries. Named rather than discovered so the test states what it is about.
FAB_ONLY_PADS = {("K1", 2, "13"): "power_in.ntc-no", ("K1", 3, "14"): "w1_2"}


@pytest.fixture(scope="module")
def parsed():
    return parse_kicad_pcb(PRODUCTION_BOARD, normalize=False)


def _pins(parsed) -> dict[tuple[str, int, str], object]:
    """Every pin, keyed by ``(ref, ordinal, number)``.

    The ordinal is load-bearing: 9 of this board's 527 pads are unnumbered NPTH
    mounting holes (``(pad "" np_thru_hole ...)``), so ``(ref, number)`` alone
    collapses them and loses 9 pads.
    """
    return {
        (c.ref, i, p.number): p
        for c in parsed.netlist.components
        for i, p in enumerate(c.pins)
    }


def _declared_layers_from_bytes() -> dict[tuple[str, int, str], tuple[str, ...]]:
    """Every pad's ``(layers ...)`` read straight from the board file.

    Independent of the parser under test -- this is the ground truth the
    assertions below are graded against, so a defect in the parser cannot also
    supply the expectation. Keyed the same way as :func:`_pins`.
    """
    text = PRODUCTION_BOARD.read_text(encoding="utf-8")
    out: dict[tuple[str, int, str], tuple[str, ...]] = {}
    for block in text.split("\n  (footprint ")[1:]:
        ref_match = re.search(r'\(property "Reference" "([^"]+)"', block)
        if ref_match is None:
            continue
        ref = ref_match.group(1)
        pads = re.findall(r'\(pad "([^"]*)"[^\n]*?\(layers ([^)]*)\)', block)
        for i, (num, layers) in enumerate(pads):
            out[(ref, i, num)] = tuple(layers.replace('"', "").split())
    return out


def test_fab_only_pads_are_not_copper(parsed):
    """The regression itself: RED before the fix, both pads reported copper."""
    pins = _pins(parsed)
    for key, net in FAB_ONLY_PADS.items():
        pin = pins[key]
        assert pin.net == net, f"{key}: wrong pad -- board changed under this test"
        assert tuple(pin.declared_pad_layers) == ("F.Fab",), (
            f"{key}: expected the board's own (layers \"F.Fab\"), "
            f"got {pin.declared_pad_layers!r}"
        )
        assert pin.is_copper is False, (
            f"{key} declares only F.Fab and places no copper, but is_copper is True. "
            f"Pin.layer reports {pin.layer!r}, which is the defect this guards."
        )


def test_every_other_pad_on_the_board_is_copper(parsed):
    """The other direction: exactly 525 of 527 pads must stay copper.

    A predicate that under-reports copper would silence real violations, so the
    count is asserted, not just the two exclusions.
    """
    pins = _pins(parsed)
    assert len(pins) == 527, f"board pad count changed: {len(pins)}"
    non_copper = {k for k, p in pins.items() if not p.is_copper}
    assert non_copper == set(FAB_ONLY_PADS), (
        f"non-copper set drifted: {sorted(non_copper)}"
    )


def test_is_copper_agrees_with_the_board_bytes(parsed):
    """Every pad, graded against its own `(layers ...)` read from the file."""
    declared = _declared_layers_from_bytes()
    assert len(declared) == 527, f"byte scan found {len(declared)} pads, expected 527"
    for key, pin in _pins(parsed).items():
        tokens = declared[key]
        expected = any(t.endswith(".Cu") for t in tokens)
        assert pin.is_copper is expected, f"{key}: {tokens} -> is_copper={pin.is_copper}"
        assert tuple(pin.declared_pad_layers) == tokens, key


def test_pad_data_agrees_with_pins(parsed):
    """``ParseResult.pads`` carries the same classification as ``.netlist``."""
    pads: dict[tuple[str, int, str], object] = {}
    seen: dict[str, int] = {}
    for pad in parsed.pads:
        ref = pad.component_ref
        i = seen.get(ref, 0)
        seen[ref] = i + 1
        pads[(ref, i, pad.number)] = pad
    pins = _pins(parsed)
    assert set(pads) == set(pins)
    for key, pin in pins.items():
        assert pads[key].is_copper is pin.is_copper, key


@pytest.mark.parametrize(
    ("layers", "expected"),
    [
        (("F.Cu", "F.Mask", "F.Paste"), True),
        (("F.Cu", "F.Paste", "F.Mask"), True),
        (("F.Cu", "F.Mask"), True),
        (("B.Cu", "B.Paste", "B.Mask"), True),
        (("In1.Cu",), True),
        (("In2.Cu", "*.Mask"), True),
        (("*.Cu", "*.Mask"), True),
        (("*.Cu",), True),
        # Both outer copper layers -- KiCad's edge/castellated-pad spelling.
        (("F&B.Cu", "*.Mask"), True),
        # Copper not listed first: a first-token-only test would miss it.
        (("F.Mask", "F.Paste", "F.Cu"), True),
        # No copper anywhere -> not copper, whatever else is declared.
        (("F.Fab",), False),
        (("B.Fab",), False),
        (("B.Paste",), False),
        (("F.SilkS",), False),
        (("F.Mask", "F.Paste"), False),
        (("*.Mask",), False),
        (("User.1",), False),
    ],
)
def test_layer_set_classification(layers, expected):
    """Every spelling KiCad writes, on a Pin carrying that declared set.

    ``layer`` is held at its defaulted ``"F.Cu"`` throughout, so a classifier
    that consulted ``layer`` instead of the declared set would return ``True``
    for every row and fail on all seven negatives.
    """
    pin = Pin(name="1", number="1", position=(0.0, 0.0))
    assert pin.layer == "F.Cu"
    pin.declared_pad_layers = layers
    assert pin.is_copper is expected, f"{layers} -> {pin.is_copper}"


def test_hand_built_pin_falls_back_to_its_layer():
    """No injected set (the placer's synthetic pins) -> classify ``layer``."""
    assert Pin(name="1", number="1", position=(0.0, 0.0)).is_copper is True
    assert Pin(name="1", number="1", position=(0.0, 0.0), layer="B.Cu").is_copper is True
    assert Pin(name="1", number="1", position=(0.0, 0.0), layer="In1.Cu").is_copper is True
    # "all" is this parser's own spelling for the through-hole wildcard.
    assert Pin(name="1", number="1", position=(0.0, 0.0), layer="all").is_copper is True
    assert Pin(name="1", number="1", position=(0.0, 0.0), layer="F.Fab").is_copper is False
    assert Pin(name="1", number="1", position=(0.0, 0.0), layer="F.SilkS").is_copper is False
