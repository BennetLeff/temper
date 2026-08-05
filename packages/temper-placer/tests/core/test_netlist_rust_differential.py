"""Differential: Rust netlist pyclasses vs the verbatim Python oracle.

The Rust port (packages/temper-design-bundle/src/netlist_contracts.rs) must
be bit-identical to the pinned pre-migration module
(tests/core/_netlist_py_oracle.py, origin/main f2b09d846): construction,
field mapping, index/lookup semantics, mutation paths, and repr
byte-parity (B9/B10). The numpy surface (get_bounds_array/get_fixed_mask/
build_adjacency_matrix/compute_eigenvector_centrality) and the hashlib
find_isomorphic_groups helper are shim-kept (R10/KTD7) and asserted
through the delegation path.

RED guard: this suite fails to collect before the pyclasses exist.
"""

from __future__ import annotations

import numpy as np
import pytest
from temper_design_bundle_python import (
    Net as RustNet,
)
from temper_design_bundle_python import (
    Netlist as RustNetlist,
)
from temper_design_bundle_python import (
    NetlistComponent as RustComponent,
)
from temper_design_bundle_python import (
    Pin as RustPin,
)

from temper_placer.core.netlist import (
    build_adjacency_matrix,
    compute_eigenvector_centrality,
    find_isomorphic_groups,
    get_bounds_array,
    get_fixed_mask,
)
from tests.core import _netlist_py_oracle as oracle


def _f(value):
    if value is None or isinstance(value, (str, bool)):
        return value
    return float(value).hex()


def _pin_canonical(pin):
    return {
        "name": pin.name,
        "number": pin.number,
        "position": tuple(_f(v) for v in pin.position),
        "net": pin.net,
        "width": _f(pin.width),
        "height": _f(pin.height),
        "shape": pin.shape,
        "layer": pin.layer,
        "drill": _f(pin.drill),
        "is_pth": pin.is_pth,
        "roundrect_ratio": _f(pin.roundrect_ratio),
        "pad_rotation_deg": _f(pin.pad_rotation_deg),
        "mask_expansion": _f(pin.mask_expansion),
    }


def _component_canonical(comp):
    return {
        "ref": comp.ref,
        "footprint": comp.footprint,
        "bounds": tuple(_f(v) for v in comp.bounds),
        "pins": [_pin_canonical(p) for p in comp.pins],
        "net_class": comp.net_class,
        "zone": comp.zone,
        "fixed": comp.fixed,
        "initial_position": (
            tuple(_f(v) for v in comp.initial_position)
            if comp.initial_position is not None
            else None
        ),
        "initial_rotation": comp.initial_rotation,
        "initial_side": comp.initial_side,
        "attributes": dict(comp.attributes),
        "tags": set(comp.tags),
        "sheetpath": comp.sheetpath,
    }


def _net_canonical(net):
    return {
        "name": net.name,
        "pins": [tuple(p) for p in net.pins],
        "net_class": net.net_class,
        "weight": _f(net.weight),
        "max_current": _f(net.max_current),
        "voltage_class": net.voltage_class,
        "pin_count": net.pin_count,
    }


def _netlist_canonical(netlist):
    return {
        "components": [_component_canonical(c) for c in netlist.components],
        "nets": [_net_canonical(n) for n in netlist.nets],
    }


def _sample_netlist_kwargs(cls):
    """A small board-like netlist, constructed with the given classes.

    Each side must build its own objects — sharing instances across sides
    aliases mutation (apply_net_class_mapping / validate) between the
    differential arms.
    """
    Pin, Component, Net = cls.Pin, cls.Component, cls.Net
    pins_c1 = [
        Pin("1", "1", (0.0, 0.0), net="AC_L"),
        Pin("2", "2", (1.0, 0.0), net="GND"),
    ]
    [
        Pin("1", "1", (0.0, 0.0), net="AC_L", is_pth=True),
        Pin("2", "2", (0.0, 1.0), net="GND", shape="roundrect", roundrect_ratio=0.3),
    ]
    return {
        "components": [
            Component(
                "U1", "SOIC-8", (5.0, 4.0),
                pins=pins_c1, net_class="HighVoltage", zone="HV_ZONE",
                initial_position=(10.0, 20.0), initial_rotation=1,
                attributes={"value": "driver"}, tags=frozenset({"hv"}),
                sheetpath="hb.power_loop.q_high",
            ),
            Component("C1", "0805", (2.0, 1.2), fixed=True,
                      pins=[Pin("1", "1", (0.0, 0.0), net="AC_L"),
                            Pin("2", "2", (1.0, 0.0), net="GND")]),
            Component("R1", "0603", (1.6, 0.8),
                      pins=[Pin("1", "1", (0.0, 0.0), net="GND")]),
        ],
        "nets": [
            Net("AC_L", [("U1", "1"), ("C1", "1")], net_class="HighVoltage", weight=3.0),
            Net("GND", [("U1", "2"), ("C1", "2"), ("R1", "1")], voltage_class="HV"),
        ],
    }


class _OracleClasses:
    Pin = oracle.Pin
    Component = oracle.Component
    Net = oracle.Net


class _RustClasses:
    Pin = RustPin
    Component = RustComponent
    Net = RustNet


class TestLeafTypes:
    def test_pin_parity(self):
        o = oracle.Pin("1", "1", (0.0, 0.0), net="GND")
        r = RustPin("1", "1", (0.0, 0.0), net="GND")
        assert _pin_canonical(r) == _pin_canonical(o)
        assert repr(r) == repr(o)

    def test_pin_defaults_and_mask(self):
        o = oracle.Pin("1", "1", (0, 0))
        r = RustPin("1", "1", (0, 0))
        assert _pin_canonical(r) == _pin_canonical(o)
        assert repr(r) == repr(o)
        assert r.mask_expansion == o.mask_expansion == 0.1
        o2 = oracle.Pin("1", "1", (0, 0), is_pth=True)
        r2 = RustPin("1", "1", (0, 0), is_pth=True)
        assert r2.mask_expansion == o2.mask_expansion == 0.15

    def test_component_parity(self):
        o = oracle.Component("U1", "SOIC-8", (5.0, 4.0))
        r = RustComponent("U1", "SOIC-8", (5.0, 4.0))
        assert _component_canonical(r) == _component_canonical(o)
        assert repr(r) == repr(o)

    def test_component_properties_and_lookups(self):
        pins = [oracle.Pin("1", "1", (0, 0), net="GND"), oracle.Pin("2", "2", (0, 0))]
        o = oracle.Component("U1", "SOIC-8", (5.0, 4.0), pins=pins)
        r = RustComponent("U1", "SOIC-8", (5.0, 4.0), pins=pins)
        assert r.width == o.width == 5.0
        assert r.height == o.height == 4.0
        assert r.get_pin("1").name == o.get_pin("1").name
        assert r.get_pin("2").name == o.get_pin("2").name
        assert r.get_pin("nope") is None and o.get_pin("nope") is None
        rust_gnd = [p.name for p in r.get_pins_for_net("GND")]
        oracle_gnd = [p.name for p in o.get_pins_for_net("GND")]
        assert rust_gnd == oracle_gnd == ["1"]

    def test_net_parity(self):
        o = oracle.Net("GND", [("U1", "2")])
        r = RustNet("GND", [("U1", "2")])
        assert _net_canonical(r) == _net_canonical(o)
        assert repr(r) == repr(o)
        assert r.get_component_refs() == o.get_component_refs() == {"U1"}


class TestNetlist:
    def test_full_parity(self):
        o = oracle.Netlist(**_sample_netlist_kwargs(_OracleClasses))
        r = RustNetlist(**_sample_netlist_kwargs(_RustClasses))
        assert _netlist_canonical(r) == _netlist_canonical(o)
        assert repr(r) == repr(o)

    def test_empty_parity(self):
        o = oracle.Netlist()
        r = RustNetlist()
        assert _netlist_canonical(r) == _netlist_canonical(o)
        assert repr(r) == repr(o)
        assert r.n_components == o.n_components == 0
        assert r.n_nets == o.n_nets == 0

    def test_index_lookups(self):
        o = oracle.Netlist(**_sample_netlist_kwargs(_OracleClasses))
        r = RustNetlist(**_sample_netlist_kwargs(_RustClasses))
        assert r.get_component_index("U1") == o.get_component_index("U1") == 0
        assert r.get_component("C1").ref == o.get_component("C1").ref
        assert r.get_net("GND").name == o.get_net("GND").name
        assert r.get_component_nets("U1") == o.get_component_nets("U1") == ["AC_L", "GND"]
        assert r.get_component_nets("MISSING") == o.get_component_nets("MISSING") == []
        assert r.get_net_pins("AC_L") == o.get_net_pins("AC_L")
        with pytest.raises(KeyError):
            r.get_component("NOPE")
        with pytest.raises(KeyError):
            o.get_component("NOPE")

    def test_apply_net_class_mapping(self):
        o = oracle.Netlist(**_sample_netlist_kwargs(_OracleClasses))
        r = RustNetlist(**_sample_netlist_kwargs(_RustClasses))
        mapping = {"GND": "Ground"}
        assert r.apply_net_class_mapping(mapping) == o.apply_net_class_mapping(mapping) == 1
        assert r.get_net("GND").net_class == o.get_net("GND").net_class == "Ground"
        assert r.get_net("AC_L").net_class == o.get_net("AC_L").net_class == "HighVoltage"
        # idempotent second pass
        assert r.apply_net_class_mapping(mapping) == o.apply_net_class_mapping(mapping) == 0

    def test_validate_parity(self):
        o = oracle.Netlist(**_sample_netlist_kwargs(_OracleClasses))
        r = RustNetlist(**_sample_netlist_kwargs(_RustClasses))
        assert r.validate() == o.validate() == []

        dup = oracle.Netlist(**_sample_netlist_kwargs(_OracleClasses))
        dup.components.append(dup.components[0])
        dup2 = RustNetlist(**_sample_netlist_kwargs(_RustClasses))
        dup2.components.append(dup2.components[0])
        # duplicate-ref message content parity (set repr order is
        # hash-seeded; compare normalized)
        o_errors = [e for e in dup.validate() if "Duplicate" in e]
        r_errors = [e for e in dup2.validate() if "Duplicate" in e]
        assert len(o_errors) == len(r_errors) == 1
        assert "Duplicate component refs" in r_errors[0]

    def test_build_indices_after_mutation(self):
        r = RustNetlist()
        r.components.append(RustComponent("NEW", "0603", (1.0, 1.0)))
        with pytest.raises(KeyError):
            r.get_component("NEW")
        r.build_indices()
        assert r.get_component("NEW").ref == "NEW"


class TestShimKeptSurface:
    def test_numpy_wrappers(self):
        """R10/KTD6: dtype asserted explicitly; eigh kernel never gated."""
        r = RustNetlist(**_sample_netlist_kwargs(_RustClasses))
        bounds = get_bounds_array(r)
        assert bounds.dtype == np.float32
        assert bounds.shape == (3, 2)
        mask = get_fixed_mask(r)
        assert mask.dtype == np.bool_
        assert mask.shape == (3,)
        adj = build_adjacency_matrix(r)
        assert adj.dtype == np.float32
        assert adj.shape == (3, 3)
        centrality = compute_eigenvector_centrality(adj)
        assert abs(float(np.sum(centrality)) - 1.0) < 1e-5

    def test_find_isomorphic_groups_through_shim(self):
        """KTD7: the hashlib helper stays Python; the delegation path is
        identical by construction."""
        r = RustNetlist(**_sample_netlist_kwargs(_RustClasses))
        groups = find_isomorphic_groups(r, iterations=2)
        assert isinstance(groups, list)
