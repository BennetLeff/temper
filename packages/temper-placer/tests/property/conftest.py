"""
Hypothesis strategies for ghost-pad injection property tests.

Generates random ``DesignRules`` and ``BoardState`` instances with
mixed HV / LV / None safety categories and arbitrary number of pins
(0..200).  Used by ``test_ghost_pad_injection.py`` to drive the
NFR3 property coverage gate.
"""

from __future__ import annotations

from hypothesis import strategies as st

from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Net, Netlist, Pin

# Pin name / number generators.
_pin_name = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Nd"), max_codepoint=90),
    min_size=1,
    max_size=4,
)
_net_name = st.text(
    alphabet=st.characters(whitelist_categories=("Lu",), max_codepoint=90),
    min_size=1,
    max_size=8,
)
_ref = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Nd"), max_codepoint=90),
    min_size=1,
    max_size=4,
)

# Safety category distribution: None is the most common, then LV, then HV/AC.
_safety = st.sampled_from([None, None, None, "LV", "LV", "HV", "AC"])


@st.composite
def design_rules_with_hv(
    draw, *, max_classes: int = 5, max_creepage: float = 10.0
) -> DesignRules:
    """Generate a DesignRules with 1..max_classes classes and 0..N nets."""
    n_classes = draw(st.integers(min_value=1, max_value=max_classes))
    classes: dict[str, NetClassRules] = {}
    for i in range(n_classes):
        name = f"CLS_{i}"
        safety = draw(_safety)
        creepage = (
            draw(
                st.floats(
                    min_value=0.0,
                    max_value=max_creepage,
                    allow_nan=False,
                    allow_infinity=False,
                )
            )
            if safety in {"HV", "AC"}
            else 0.0
        )
        classes[name] = NetClassRules(
            name=name,
            trace_width=0.2,
            clearance=0.2,
            dru_priority=10 * (i + 1),
            creepage_mm=creepage,
            safety_category=safety,
        )
    n_nets = draw(st.integers(min_value=0, max_value=20))
    assignments: dict[str, str] = {}
    for i in range(n_nets):
        net = f"NET_{i}"
        cls_name = draw(st.sampled_from(list(classes.keys())))
        assignments[net] = cls_name
    return DesignRules(
        net_classes=classes,
        net_class_assignments=assignments,
    )


@st.composite
def arbitrary_netlist(
    draw, *, max_components: int = 10, max_pins: int = 10
) -> Netlist:
    """Generate a netlist with 0..max_components and 0..max_pins per component."""
    n_components = draw(st.integers(min_value=0, max_value=max_components))
    components: list[Component] = []
    nets: list[Net] = []
    for ci in range(n_components):
        n_pins = draw(st.integers(min_value=0, max_value=max_pins))
        pins: list[Pin] = []
        for pi in range(n_pins):
            x = draw(
                st.floats(
                    min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False
                )
            )
            y = draw(
                st.floats(
                    min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False
                )
            )
            net = draw(
                st.one_of(
                    st.none(),
                    st.sampled_from(
                        [f"NET_{ni}" for ni in range(20)]
                        + [f"AUTO_{ci}_{pi}"]
                    ),
                )
            )
            name = f"P{pi}"
            pins.append(
                Pin(name=name, number=name, position=(x, y), net=net)
            )
        bounds = (
            draw(
                st.floats(
                    min_value=1.0, max_value=20.0, allow_nan=False, allow_infinity=False
                )
            ),
            draw(
                st.floats(
                    min_value=1.0, max_value=20.0, allow_nan=False, allow_infinity=False
                )
            ),
        )
        components.append(
            Component(
                ref=f"C{ci}",
                footprint="TEST",
                bounds=bounds,
                pins=pins,
            )
        )

    # Build nets: every pin with a non-None net is a member.
    net_to_pins: dict[str, list[tuple[str, str]]] = {}
    for comp in components:
        for pin in comp.pins:
            if pin.net is not None and not pin.net.startswith("AUTO_"):
                net_to_pins.setdefault(pin.net, []).append((comp.ref, pin.name))
    for net_name, pin_list in net_to_pins.items():
        nets.append(
            Net(name=net_name, pins=pin_list, net_class="CLS_0")
        )

    return Netlist(components=components, nets=nets)


@st.composite
def board_state_with_ghost_pads(
    draw,
    *,
    max_components: int = 10,
    max_pins: int = 10,
    grid_size: int = 20,
) -> tuple:
    """Generate a (BoardState, design_rules) pair suitable for ghost-pad tests.

    Returns a tuple (state, design_rules).  The state's netlist is
    derived from the design_rules' assignments (so every net resolves
    to a real class).  The state's zone_slots is a regular grid of
    ``grid_size x grid_size`` slots at 5mm spacing.
    """
    rules = draw(design_rules_with_hv())
    netlist = draw(arbitrary_netlist(max_components=max_components, max_pins=max_pins))

    # Build a uniform slot grid.
    slots = [
        (float(x), float(y))
        for x in range(0, grid_size * 5, 5)
        for y in range(0, grid_size * 5, 5)
    ]
    from temper_placer.deterministic.state import BoardState

    state = BoardState(
        netlist=netlist,
        component_zone_map=frozenset(
            [(c.ref, "Signal") for c in netlist.components]
        ),
        zone_slots=frozenset([("Signal", tuple(slots))]),
        design_rules=rules,
    )
    return state, rules
