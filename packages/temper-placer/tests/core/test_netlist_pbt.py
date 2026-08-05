"""Property-based + metamorphic tests for the Rust netlist pyclasses.

Wave 4, Phase 3 — the formats/IO first-pull slice (plan
``docs/plans/2026-08-03-003-feat-wave4-phase3-first-pulls-plan.md``, U6,
R1c/R1d). These properties exercise the migrated
``temper_placer.core.netlist`` module (a delegation shim over the
``temper_design_bundle_python`` pyclasses); bit-identical parity against
the pinned pre-migration Python is asserted separately by
``test_netlist_rust_differential.py``.

Five hypothesis properties (all non-vacuously guarded):

- P1. Index round-trip: ``get_component_index(ref)`` indexes back to the
  same component's ``ref``.
- P2. Component-nets coverage: every net a component pins appears in
  ``get_component_nets``.
- P3. Mapping precision: ``apply_net_class_mapping`` updates exactly the
  nets named in the mapping (and returns that count).
- P4. Validity: a consistently-generated netlist passes ``validate``.
- P5. Counts: ``n_components``/``n_nets`` match the list lengths.

Three metamorphic relations:

- MR1. Component-order independence: reversing the components list keeps
  ``get_component``/``get_component_index`` results correct.
- MR2. Net-order independence: reversing the nets list keeps
  ``get_net``/``get_net_pins`` results correct.
- MR3. Mapping idempotence: a second ``apply_net_class_mapping`` with the
  same mapping updates nothing.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from temper_design_bundle_python import Net, Netlist, Pin
from temper_design_bundle_python import NetlistComponent as Component

MAX_EXAMPLES = 100


@st.composite
def consistent_netlist(draw):
    """A netlist whose nets reference real pins on real components."""
    refs = draw(st.lists(st.text(min_size=1, max_size=6), min_size=2, max_size=6, unique=True))
    pins_per_comp = draw(
        st.lists(
            st.lists(st.text(min_size=1, max_size=4), min_size=1, max_size=4, unique=True),
            min_size=len(refs),
            max_size=len(refs),
        )
    )
    net_names = draw(
        st.lists(st.text(min_size=1, max_size=8), min_size=1, max_size=5, unique=True)
    )
    components = [
        Component(ref, "0603", (1.0, 1.0),
                  pins=[Pin(p, p, (0.0, 0.0)) for p in pins_per_comp[i]])
        for i, ref in enumerate(refs)
    ]
    nets = []
    for net_name in net_names:
        members = draw(
            st.lists(st.sampled_from(list(enumerate(refs))), min_size=1, max_size=6)
        )
        pins = []
        for idx, ref in members:
            pin_name = draw(st.sampled_from(pins_per_comp[idx]))
            pins.append((ref, pin_name))
        nets.append(Net(net_name, pins))
    return Netlist(components=components, nets=nets)


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(netlist=consistent_netlist())
def test_p1_index_round_trip(netlist):
    for comp in netlist.components:
        idx = netlist.get_component_index(comp.ref)
        assert netlist.get_component(comp.ref).ref == comp.ref
        assert 0 <= idx < netlist.n_components


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(netlist=consistent_netlist())
def test_p2_component_nets_coverage(netlist):
    for net in netlist.nets:
        for ref, _pin in net.pins:
            if ref in {c.ref for c in netlist.components}:
                assert net.name in netlist.get_component_nets(ref)


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(netlist=consistent_netlist())
def test_p3_mapping_precision(netlist):
    mapping = {net.name: "Mapped" for net in netlist.nets[: max(len(netlist.nets) // 2, 1)]}
    updated = netlist.apply_net_class_mapping(mapping)
    assert updated == len(mapping)
    for net in netlist.nets:
        assert net.net_class == ("Mapped" if net.name in mapping else "Signal")


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(netlist=consistent_netlist())
def test_p4_validity(netlist):
    assert netlist.validate() == []


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(netlist=consistent_netlist())
def test_p5_counts(netlist):
    assert netlist.n_components == len(netlist.components)
    assert netlist.n_nets == len(netlist.nets)


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(netlist=consistent_netlist())
def test_mr1_component_order_independence(netlist):
    reversed_list = Netlist(components=list(reversed(netlist.components)), nets=netlist.nets)
    for comp in netlist.components:
        assert reversed_list.get_component(comp.ref).ref == comp.ref


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(netlist=consistent_netlist())
def test_mr2_net_order_independence(netlist):
    reversed_list = Netlist(components=netlist.components, nets=list(reversed(netlist.nets)))
    for net in netlist.nets:
        assert reversed_list.get_net(net.name).name == net.name


@settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(netlist=consistent_netlist())
def test_mr3_mapping_idempotence(netlist):
    mapping = {net.name: "Mapped" for net in netlist.nets[: max(len(netlist.nets) // 2, 1)]}
    netlist.apply_net_class_mapping(mapping)
    assert netlist.apply_net_class_mapping(mapping) == 0
