"""Stable parsed-PCB terminal extraction for future all-pad planning."""

from types import SimpleNamespace

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.netlist import Component, Pin
from temper_placer.router_v6.terminal_extraction import extract_net_terminals


def _pcb() -> SimpleNamespace:
    u1 = Component("U1", "fp", (2, 2), initial_position=(10, 20))
    u1.pins = [Pin("1", "1", (1, 0), net="NET", layer="F.Cu")]
    j1 = Component("J1", "fp", (2, 2), initial_position=(30, 20))
    j1.pins = [Pin("2", "2", (0, 0), net="NET", layer="all", is_pth=True)]
    return SimpleNamespace(
        components=[j1, u1],
        stackup=SimpleNamespace(
            layers=[
                SimpleNamespace(name="F.Cu", index=0, layer_type="signal"),
                SimpleNamespace(name="In1.Cu", index=1, layer_type="plane"),
                SimpleNamespace(name="B.Cu", index=31, layer_type="signal"),
            ]
        ),
    )


def test_extraction_uses_canonical_world_position_identity_and_declared_layers():
    terminals = extract_net_terminals(_pcb(), "NET", [("U1", "1"), ("J1", "2")])

    assert [(terminal.identity.component_ref, terminal.identity.pad) for terminal in terminals] == [
        ("J1", "2"),
        ("U1", "1"),
    ]
    assert terminals[1].identity.x == 11
    assert terminals[1].identity.y == 20
    assert terminals[1].layer_names == ("F.Cu",)
    assert terminals[1].identity.layers == (0,)
    assert terminals[0].layer_names == ("F.Cu", "B.Cu")
    assert terminals[0].identity.layers == (0, 31)


def test_extraction_does_not_guess_unknown_layer_indices():
    pcb = _pcb()
    pcb.components[1].pins[0].layer = "User.Cu"

    terminal = extract_net_terminals(pcb, "NET", [("U1", "1")])[0]

    assert terminal.layer_names == ("User.Cu",)
    assert terminal.identity.layers == ()


@given(st.permutations([("U1", "1"), ("J1", "2")]))
@settings(max_examples=10, deadline=30_000)
def test_extraction_is_deterministic_under_net_pin_permutation(pin_order):
    expected = extract_net_terminals(_pcb(), "NET", [("U1", "1"), ("J1", "2")])

    actual = extract_net_terminals(_pcb(), "NET", list(pin_order))

    assert actual == expected
