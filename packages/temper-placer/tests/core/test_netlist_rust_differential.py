"""Differential test: Rust netlist pyclasses vs the pinned Python oracle.

Wave 4, **Phase 3, candidate 1** (plan
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``). The
pyo3 pyclasses in ``temper_design_bundle_python.netlist_contracts`` must
reproduce the pre-migration ``temper_placer/core/netlist.py``
bit-identically. That implementation is pinned VERBATIM as the oracle
(``_netlist_py_oracle.py``, commit ``e799183c4``) and every assertion here
drives IDENTICAL inputs through both sides.

Comparison convention
---------------------
Everything goes through :func:`tests.core._contract_canon.canon`, which
carries each leaf's concrete ``type`` and compares floats as
``float.hex()`` -- never a tolerance -- and numpy arrays as
``(dtype, shape, tobytes())``. That is what makes the *float32 surface* on
``get_bounds_array`` / ``get_fixed_mask`` / ``build_adjacency_matrix``
provable rather than assumed: a Rust ``f64`` round-trip would change the
dtype and fail here even though every nominal value still matched.

Calls that can raise are compared with :func:`canon_call`, so error *type*
and *message* parity is asserted alongside value parity.
"""

from __future__ import annotations

import numpy as np
import pytest
import temper_design_bundle_python as _tdb

import tests.core._netlist_py_oracle as _oracle
from tests.core._contract_canon import canon, canon_call

# Rust symbols under test -- must exist or this file fails to collect (RED).
_rs = _tdb.netlist_contracts
RS_PIN = _rs.Pin
RS_COMPONENT = _rs.Component
RS_NET = _rs.Net
RS_NETLIST = _rs.Netlist
RS_BUILD_ADJACENCY = _rs.build_adjacency_matrix

PY_SIDE = (_oracle.Pin, _oracle.Component, _oracle.Net, _oracle.Netlist)
RS_SIDE = (RS_PIN, RS_COMPONENT, RS_NET, RS_NETLIST)


# ---------------------------------------------------------------------------
# Fixture corpora -- built as *argument tuples* so the identical arguments go
# to both sides. Deliberately mixes int and float where the annotation says
# float, because the dataclass does not coerce and the Rust must not either.
# ---------------------------------------------------------------------------

PIN_ARGS = [
    (("VCC", "1", (0.0, 0.0)), {}),
    (("GND", "2", (1, 2)), {}),  # int position -- must stay int
    (("A", "3", (0.5, -1.5)), {"net": "NET1", "width": 2, "height": 0.8}),
    (
        ("B", "4", (0.0, 0.0)),
        {
            "net": None,
            "width": 1.25,
            "height": 1.25,
            "shape": "roundrect",
            "layer": "B.Cu",
            "drill": 0.4,
            "is_pth": True,
            "roundrect_ratio": 0.125,
            "pad_rotation_deg": 45.0,
        },
    ),
    # Extreme / adversarial floats: subnormals and infinities must survive
    # byte-for-byte through construction and repr.
    (("E", "5", (5e-324, 1e308)), {"width": float("inf"), "drill": -0.0}),
]

COMPONENT_ARGS = [
    (("R1", "R_0402", (1.0, 0.5)), {}),
    (("R2", "R_0402", (1, 2)), {}),  # int bounds -> int .width/.height
    (
        ("U1", "QFN-32", (5.0, 5.0)),
        {
            "net_class": "HighVoltage",
            "zone": "HV_ZONE",
            "fixed": True,
            "initial_position": (10.0, 20.0),
            "initial_rotation_quadrant": 2,
            "initial_side": 1,
            "attributes": {"MPN": "X", "value": "10k"},
            "tags": frozenset({"power", "hot"}),
            "sheetpath": "hb.power_loop.q_high",
        },
    ),
]

NET_ARGS = [
    (("GND", [("R1", "1"), ("R2", "2")]), {}),
    (("VCC", []), {}),
    (
        ("AC_L", [("U1", "A"), ("R1", "1"), ("U1", "B")]),
        {"net_class": "HighVoltage", "weight": 3, "max_current": 12.5, "voltage_class": "HV"},
    ),
]


def _make(cls, args, kwargs):
    return cls(*args, **kwargs)


def _pins(cls):
    return [_make(cls.Pin if hasattr(cls, "Pin") else cls, a, k) for a, k in PIN_ARGS]


def _build_netlist(pin_cls, comp_cls, net_cls, netlist_cls):
    """A non-trivial netlist built identically on both sides.

    Includes a component with several pins, a multi-pin net, a net that
    references an unknown component, and a net whose two pins land on the
    same component (which `build_adjacency_matrix` must deduplicate).
    """
    p = lambda name, num: pin_cls(name, num, (0.0, 0.0), net=None)  # noqa: E731
    r1 = comp_cls("R1", "R_0402", (1.0, 0.5), pins=[p("1", "1"), p("2", "2")])
    r2 = comp_cls("R2", "R_0402", (1.0, 0.5), pins=[p("1", "1"), p("2", "2")])
    u1 = comp_cls("U1", "QFN-32", (5.0, 5.0), pins=[p("A", "1"), p("B", "2")], fixed=True)
    nets = [
        net_cls("GND", [("R1", "1"), ("R2", "1"), ("U1", "A")]),
        net_cls("VCC", [("R1", "2"), ("U1", "B")]),
        net_cls("SELF", [("U1", "A"), ("U1", "B")]),
        net_cls("DANGLING", [("NOPE", "1"), ("R2", "2")]),
    ]
    return netlist_cls(components=[r1, r2, u1], nets=nets)


def _py_netlist():
    return _build_netlist(_oracle.Pin, _oracle.Component, _oracle.Net, _oracle.Netlist)


def _rs_netlist():
    return _build_netlist(RS_PIN, RS_COMPONENT, RS_NET, RS_NETLIST)


# ---------------------------------------------------------------------------
# Pin
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("args,kwargs", PIN_ARGS)
def test_pin_construction_is_bit_identical(args, kwargs):
    """Every field, with its concrete type, survives construction identically."""
    assert canon(_oracle.Pin(*args, **kwargs)) == canon(RS_PIN(*args, **kwargs))


@pytest.mark.parametrize("args,kwargs", PIN_ARGS)
def test_pin_repr_identical(args, kwargs):
    assert repr(_oracle.Pin(*args, **kwargs)) == repr(RS_PIN(*args, **kwargs))


@pytest.mark.parametrize("args,kwargs", PIN_ARGS)
def test_pin_mask_expansion_identical(args, kwargs):
    assert canon(_oracle.Pin(*args, **kwargs).mask_expansion) == canon(
        RS_PIN(*args, **kwargs).mask_expansion
    )


def test_pin_equality_semantics_identical():
    a, k = PIN_ARGS[0]
    b, bk = PIN_ARGS[1]
    for cls in (_oracle.Pin, RS_PIN):
        assert cls(*a, **k) == cls(*a, **k)
        assert cls(*a, **k) != cls(*b, **bk)
        # A foreign type is NotImplemented -> falls back to identity -> False.
        assert (cls(*a, **k) == "nope") is False


def test_pin_is_mutable_like_the_dataclass():
    """`fixtures/synthetic.py` does `pin.net = ...`; the pyclass must allow it."""
    for cls in (_oracle.Pin, RS_PIN):
        pin = cls("A", "1", (0.0, 0.0))
        pin.net = "NEW"
        assert pin.net == "NEW"


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("args,kwargs", COMPONENT_ARGS)
def test_component_construction_is_bit_identical(args, kwargs):
    assert canon(_oracle.Component(*args, **kwargs)) == canon(RS_COMPONENT(*args, **kwargs))


@pytest.mark.parametrize("args,kwargs", COMPONENT_ARGS)
def test_component_repr_identical(args, kwargs):
    assert repr(_oracle.Component(*args, **kwargs)) == repr(RS_COMPONENT(*args, **kwargs))


@pytest.mark.parametrize("args,kwargs", COMPONENT_ARGS)
def test_component_width_height_preserve_type(args, kwargs):
    """`bounds=(1, 2)` must yield `int` width, not `1.0` -- the sharpest
    silent-widening failure mode in this migration."""
    py = _oracle.Component(*args, **kwargs)
    rs = RS_COMPONENT(*args, **kwargs)
    assert canon(py.width) == canon(rs.width)
    assert canon(py.height) == canon(rs.height)


def test_component_default_containers_are_fresh_per_instance():
    """`field(default_factory=...)` -- two instances must NOT share a list."""
    for cls in (_oracle.Component, RS_COMPONENT):
        a, b = cls("R1", "f", (1.0, 1.0)), cls("R2", "f", (1.0, 1.0))
        a.pins.append("X")
        a.attributes["k"] = "v"
        assert b.pins == []
        assert b.attributes == {}


def test_component_pins_list_is_shared_by_identity():
    """`comp.pins.append(...)` must mutate the component, not a copy."""
    for pin_cls, comp_cls in ((_oracle.Pin, _oracle.Component), (RS_PIN, RS_COMPONENT)):
        comp = comp_cls("R1", "f", (1.0, 1.0))
        comp.pins.append(pin_cls("A", "1", (0.0, 0.0)))
        assert len(comp.pins) == 1


def test_component_get_pin_and_get_pins_for_net_identical():
    py = _py_netlist().get_component("R1")
    rs = _rs_netlist().get_component("R1")
    for probe in ("1", "2", "A", "missing"):
        assert canon_call(py.get_pin, probe) == canon_call(rs.get_pin, probe)
    for net in (None, "GND", "absent"):
        assert canon_call(py.get_pins_for_net, net) == canon_call(rs.get_pins_for_net, net)


# ---------------------------------------------------------------------------
# Net
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("args,kwargs", NET_ARGS)
def test_net_construction_and_repr_identical(args, kwargs):
    py, rs = _oracle.Net(*args, **kwargs), RS_NET(*args, **kwargs)
    assert canon(py) == canon(rs)
    assert repr(py) == repr(rs)


@pytest.mark.parametrize("args,kwargs", NET_ARGS)
def test_net_pin_count_and_component_refs_identical(args, kwargs):
    py, rs = _oracle.Net(*args, **kwargs), RS_NET(*args, **kwargs)
    assert canon(py.pin_count) == canon(rs.pin_count)
    assert canon(py.get_component_refs()) == canon(rs.get_component_refs())


def test_net_pins_list_is_shared_by_identity():
    """`io/_parse_nets.py:50` does `nets_dict[pin.net].pins.append(...)`.

    If the getter returned a fresh list, every parsed net would come out
    empty -- and a value-equality differential would not notice.
    """
    for cls in (_oracle.Net, RS_NET):
        pins: list[tuple[str, str]] = []
        net = cls("N", pins)
        net.pins.append(("R1", "1"))
        assert net.pins == [("R1", "1")]
        assert pins == [("R1", "1")], "the caller's own list object must be the stored one"


def test_net_class_is_assignable():
    """`Netlist.apply_net_class_mapping` and `io/_parse_nets.py` assign it."""
    for cls in (_oracle.Net, RS_NET):
        net = cls("N", [])
        net.net_class = "Power"
        assert net.net_class == "Power"


# ---------------------------------------------------------------------------
# Netlist
# ---------------------------------------------------------------------------


def test_netlist_construction_and_indices_identical():
    assert canon(_py_netlist()) == canon(_rs_netlist())


def test_netlist_repr_identical():
    """`_component_index` & co. carry `repr=False` and must stay out."""
    assert repr(_py_netlist()) == repr(_rs_netlist())
    assert "_component_index" not in repr(_rs_netlist())


def test_netlist_empty_construction_identical():
    assert canon(_oracle.Netlist()) == canon(RS_NETLIST())
    assert repr(_oracle.Netlist()) == repr(RS_NETLIST())


def test_netlist_explicitly_passed_indices_are_overwritten():
    """The three index fields are `init=True`, but `__post_init__` rebuilds
    them unconditionally -- a passed-in value must NOT survive."""
    poison = {"BOGUS": 99}
    py = _oracle.Netlist(components=[], nets=[], _component_index=dict(poison))
    rs = RS_NETLIST(components=[], nets=[], _component_index=dict(poison))
    assert canon(py) == canon(rs)
    assert py._component_index == {}
    assert rs._component_index == {}


@pytest.mark.parametrize("ref", ["R1", "R2", "U1", "ABSENT"])
def test_netlist_component_lookups_identical(ref):
    py, rs = _py_netlist(), _rs_netlist()
    assert canon_call(py.get_component_index, ref) == canon_call(rs.get_component_index, ref)
    assert canon_call(py.get_component, ref) == canon_call(rs.get_component, ref)
    assert canon_call(py.get_component_nets, ref) == canon_call(rs.get_component_nets, ref)


@pytest.mark.parametrize("name", ["GND", "VCC", "SELF", "ABSENT"])
def test_netlist_net_lookups_identical(name):
    py, rs = _py_netlist(), _rs_netlist()
    assert canon_call(py.get_net, name) == canon_call(rs.get_net, name)
    assert canon_call(py.get_net_pins, name) == canon_call(rs.get_net_pins, name)


def test_netlist_counts_identical():
    py, rs = _py_netlist(), _rs_netlist()
    assert canon(py.n_components) == canon(rs.n_components)
    assert canon(py.n_nets) == canon(rs.n_nets)


def test_netlist_bounds_array_is_bit_identical_including_dtype():
    """float32 surface: dtype and raw bytes, not a tolerance."""
    py, rs = _py_netlist().get_bounds_array(), _rs_netlist().get_bounds_array()
    assert canon(py) == canon(rs)
    assert py.dtype == np.float32


def test_netlist_fixed_mask_is_bit_identical_including_dtype():
    py, rs = _py_netlist().get_fixed_mask(), _rs_netlist().get_fixed_mask()
    assert canon(py) == canon(rs)
    assert py.dtype == np.bool_


def test_netlist_empty_arrays_keep_their_dtypes():
    """The empty netlist's bounds array is float32 shape (0,) -- a distinct
    fingerprint from the (0, 0) float64 empty adjacency below."""
    assert canon(_oracle.Netlist().get_bounds_array()) == canon(RS_NETLIST().get_bounds_array())
    assert canon(_oracle.Netlist().get_fixed_mask()) == canon(RS_NETLIST().get_fixed_mask())


@pytest.mark.parametrize(
    "mapping",
    [
        {},
        {"GND": "Ground"},
        {"GND": "Ground", "VCC": "Power", "ABSENT": "Nope"},
        {"GND": "Signal"},  # already equal -> must NOT count as updated
    ],
)
def test_netlist_apply_net_class_mapping_identical(mapping):
    py, rs = _py_netlist(), _rs_netlist()
    assert canon(py.apply_net_class_mapping(mapping)) == canon(
        rs.apply_net_class_mapping(mapping)
    )
    assert canon([n.net_class for n in py.nets]) == canon([n.net_class for n in rs.nets])


def test_netlist_validate_identical():
    """Includes the dangling-component and unknown-pin error classes."""
    assert canon(_py_netlist().validate()) == canon(_rs_netlist().validate())


def test_netlist_validate_duplicate_detection_identical():
    def build(pin_cls, comp_cls, net_cls, netlist_cls):
        p = pin_cls("1", "1", (0.0, 0.0))
        dup = [comp_cls("R1", "f", (1.0, 1.0), pins=[p]) for _ in range(2)]
        nets = [net_cls("N", [("R1", "1")]), net_cls("N", [("R1", "1")])]
        return netlist_cls(components=dup, nets=nets)

    py = build(_oracle.Pin, _oracle.Component, _oracle.Net, _oracle.Netlist)
    rs = build(RS_PIN, RS_COMPONENT, RS_NET, RS_NETLIST)
    assert canon(py.validate()) == canon(rs.validate())


def test_netlist_build_indices_rebuilds_after_mutation():
    """`build_indices()` is public and called by consumers after edits."""
    py, rs = _py_netlist(), _rs_netlist()
    for nl, comp_cls in ((py, _oracle.Component), (rs, RS_COMPONENT)):
        nl.components.append(comp_cls("R9", "f", (1.0, 1.0)))
        nl.build_indices()
    assert canon(py) == canon(rs)
    assert canon(py.get_component_index("R9")) == canon(rs.get_component_index("R9"))


@pytest.mark.parametrize("iterations", [0, 1, 2, 3])
def test_netlist_find_isomorphic_groups_identical(iterations):
    assert canon(_py_netlist().find_isomorphic_groups(iterations)) == canon(
        _rs_netlist().find_isomorphic_groups(iterations)
    )


def test_netlist_find_isomorphic_groups_empty_identical():
    assert canon(_oracle.Netlist().find_isomorphic_groups()) == canon(
        RS_NETLIST().find_isomorphic_groups()
    )


# ---------------------------------------------------------------------------
# build_adjacency_matrix
# ---------------------------------------------------------------------------


def test_build_adjacency_matrix_is_bit_identical_including_dtype():
    py = _oracle.build_adjacency_matrix(_py_netlist())
    rs = RS_BUILD_ADJACENCY(_rs_netlist())
    assert canon(py) == canon(rs)
    assert py.dtype == np.float32


def test_build_adjacency_matrix_empty_keeps_float64_shape_0_0():
    """The empty path is `np.array([]).reshape(0, 0)` -- NO dtype argument,
    so it is float64 while the populated path is float32. A Rust port that
    "tidied" this into a uniform dtype would be a behaviour change."""
    py = _oracle.build_adjacency_matrix(_oracle.Netlist())
    rs = RS_BUILD_ADJACENCY(RS_NETLIST())
    assert canon(py) == canon(rs)
    assert py.dtype == np.float64
    assert py.shape == (0, 0)


def test_build_adjacency_matrix_accepts_the_delegating_public_class():
    """`core.community` calls it with a `temper_placer.core.netlist.Netlist`.

    The Rust function is duck-typed on `.components`/`.nets`, so it must
    accept the public (post-migration) class too, not just its own.
    """
    from temper_placer.core.netlist import Netlist as PublicNetlist

    assert canon(RS_BUILD_ADJACENCY(PublicNetlist())) == canon(
        _oracle.build_adjacency_matrix(_oracle.Netlist())
    )


# ---------------------------------------------------------------------------
# The public module must actually delegate (guards against a shim that
# quietly kept the Python implementation).
# ---------------------------------------------------------------------------


def test_dataclasses_replace_works_on_the_public_contracts():
    """`deterministic/stages/apply_placements.py` rebuilds both `Component`
    and `Netlist` with `dataclasses.replace`.

    A pyclass is not a dataclass, so this raised
    `TypeError: replace() should be called on dataclass instances` until the
    shim installed a real `__dataclass_fields__`. Found by the deterministic
    stage suite, not by the contract differential -- pinned here.
    """
    import dataclasses

    from temper_placer.core.netlist import Component as PubComponent
    from temper_placer.core.netlist import Netlist as PubNetlist

    py_comp = _oracle.Component("R1", "fp", (1.0, 2.0))
    rs_comp = PubComponent("R1", "fp", (1.0, 2.0))
    assert canon(dataclasses.replace(py_comp, initial_position=(3.0, 4.0))) == canon(
        dataclasses.replace(rs_comp, initial_position=(3.0, 4.0))
    )

    py_nl, rs_nl = _py_netlist(), _rs_netlist()
    assert canon(dataclasses.replace(py_nl, components=[py_comp])) == canon(
        dataclasses.replace(rs_nl, components=[rs_comp])
    )
    # Round-tripping with no changes must be an exact copy.
    assert canon(dataclasses.replace(rs_nl)) == canon(rs_nl)
    assert isinstance(dataclasses.replace(rs_nl), PubNetlist)


def test_dataclass_field_surface_matches_the_oracle():
    """The full ``Field`` surface -- not just ``(name, init)`` -- agrees with
    the pinned oracle.

    ``dataclasses.replace()`` happens to read only ``f.name`` and ``f.init``,
    but ``dataclasses.fields()`` is public API: ``f.default`` and
    ``f.default_factory`` drive callers that materialize field defaults,
    ``f.type`` is the annotation a ``fields()`` consumer sees, and
    ``typing.get_type_hints`` is how annotation tooling resolves the
    contract. The compat layer must reproduce all of it, not only the two
    attributes ``_replace`` reads.
    """
    import dataclasses
    import typing

    from temper_placer.core import netlist as public

    def _canonicalize(t):
        """Reduce a resolved annotation to structure, mapping classes to names.

        The oracle resolves ``Component`` to
        ``tests.core._netlist_py_oracle.Component`` while the shim resolves
        it to the pyclass ``temper_placer.core.netlist.Component`` -- different
        objects by design. Comparing structural form (name + type arguments)
        is the honest equality here.
        """
        origin = typing.get_origin(t)
        if origin is None:
            return t.__name__ if isinstance(t, type) else t
        return (
            getattr(origin, "__name__", repr(origin)),
            tuple(_canonicalize(arg) for arg in typing.get_args(t)),
        )

    for py_cls, rs_cls in [
        (_oracle.Pin, public.Pin),
        (_oracle.Component, public.Component),
        (_oracle.Net, public.Net),
        (_oracle.Netlist, public.Netlist),
    ]:
        assert dataclasses.is_dataclass(rs_cls)
        py_fields = dataclasses.fields(py_cls)
        rs_fields = dataclasses.fields(rs_cls)
        assert [f.name for f in rs_fields] == [f.name for f in py_fields]
        for py_f, rs_f in zip(py_fields, rs_fields):
            assert rs_f.init == py_f.init
            assert rs_f.repr == py_f.repr
            if py_f.default is dataclasses.MISSING:
                assert rs_f.default is dataclasses.MISSING
            else:
                assert rs_f.default == py_f.default
            if py_f.default_factory is dataclasses.MISSING:
                assert rs_f.default_factory is dataclasses.MISSING
            else:
                assert rs_f.default_factory is not dataclasses.MISSING
                # Same zero-arg factory behaviour: identical callable where
                # the oracle used a builtin (list/dict/frozenset), otherwise
                # the materialized default must be identical.
                assert rs_f.default_factory() == py_f.default_factory()
            assert rs_f.type == py_f.type
        py_hints = typing.get_type_hints(py_cls)
        rs_hints = typing.get_type_hints(rs_cls)
        assert set(rs_hints) == set(py_hints)
        for name in py_hints:
            assert _canonicalize(py_hints[name]) == _canonicalize(rs_hints[name]), name


def test_public_module_delegates_to_rust():
    from temper_placer.core import netlist as public

    assert public.Pin is RS_PIN
    assert public.Component is RS_COMPONENT
    assert public.Net is RS_NET
    assert public.Netlist is RS_NETLIST
    assert public.build_adjacency_matrix is RS_BUILD_ADJACENCY


def test_compute_eigenvector_centrality_stays_python_r3():
    """R3 verdict: `np.linalg.eigh` (LAPACK) is NOT migrated.

    This asserts the *decision*, so that a later change which quietly moves
    it into Rust has to confront the recorded blocker rather than slip past.
    """
    from temper_placer.core import netlist as public

    assert public.compute_eigenvector_centrality.__module__ == "temper_placer.core.netlist"
    assert not hasattr(_rs, "compute_eigenvector_centrality")
    # Behaviour still matches the oracle exactly (it is the same code).
    for n in (0, 1, 3):
        adj = _oracle.build_adjacency_matrix(_py_netlist()) if n == 3 else np.zeros((n, n), np.float32)
        assert canon(public.compute_eigenvector_centrality(adj)) == canon(
            _oracle.compute_eigenvector_centrality(adj)
        )


def test_explicit_none_literal_defaults_divergence_pinned():
    """The pyo3 Option params cannot distinguish an *omitted* argument from an
    *explicitly passed* `None`, so explicit `None` collapses onto the literal
    default on the pyclasses while the dataclasses store what they are given.
    Affected literal-default fields on the netlist contracts: `Component`
    (`net_class="Signal"`, `fixed=False`), `Pin` (`width=1.0`, `height=1.0`,
    `shape="rect"`, `layer="F.Cu"`, `drill=0.0`, `is_pth=False`,
    `roundrect_ratio=0.25`, `pad_rotation_deg=0.0`) and `Net`
    (`net_class="Signal"`, `weight=1.0`, `max_current=0.0`,
    `voltage_class="LV"`). The `None`-defaulted fields (`Pin.net`, `zone`,
    `initial_position`, ...) store `None` on both arms and are NOT affected.

    Latent: no in-repo caller passes explicit `None` for any of these fields
    (verified 2026-08-04). Assert each arm's exact behavior (#712 pattern-5
    precedent) so a change to either arm -- or a new caller passing explicit
    `None` -- is caught. Recorded in VERIFICATION.md (board/netlist documented
    deviation 6).
    """
    # --- Component: net_class, fixed --------------------------------------
    py = _oracle.Component("R1", "fp", (1.0, 1.0), net_class=None, fixed=None)
    rs = RS_COMPONENT("R1", "fp", (1.0, 1.0), net_class=None, fixed=None)
    assert py.net_class is None and py.fixed is None  # oracle stores the passed None
    assert canon(rs.net_class) == canon("Signal")  # pyclass collapses to the default
    assert canon(rs.fixed) == canon(False)
    # Omitted-arg defaults agree between the arms.
    assert canon(_oracle.Component("R1", "fp", (1.0, 1.0)).net_class) == canon(
        RS_COMPONENT("R1", "fp", (1.0, 1.0)).net_class
    )
    # An explicit non-None value is stored identically.
    assert canon(
        _oracle.Component("R1", "fp", (1.0, 1.0), net_class="HV").net_class
    ) == canon(RS_COMPONENT("R1", "fp", (1.0, 1.0), net_class="HV").net_class)

    # --- Pin: the eight literal-default fields ----------------------------
    pin_none_kwargs = {
        "width": None, "height": None, "shape": None, "layer": None,
        "drill": None, "is_pth": None, "roundrect_ratio": None,
        "pad_rotation_deg": None,
    }
    py = _oracle.Pin("1", "1", (0.0, 0.0), **pin_none_kwargs)
    rs = RS_PIN("1", "1", (0.0, 0.0), **pin_none_kwargs)
    for field, default in [
        ("width", 1.0), ("height", 1.0), ("shape", "rect"), ("layer", "F.Cu"),
        ("drill", 0.0), ("is_pth", False), ("roundrect_ratio", 0.25),
        ("pad_rotation_deg", 0.0),
    ]:
        assert canon(getattr(py, field)) == canon(None), field  # oracle stores None
        assert canon(getattr(rs, field)) == canon(default), field  # pyclass default
    # `net` has a None default on BOTH arms -- explicit None is faithful here.
    assert _oracle.Pin("1", "1", (0.0, 0.0), net=None).net is None
    assert RS_PIN("1", "1", (0.0, 0.0), net=None).net is None

    # --- Net: the four literal-default fields -----------------------------
    py = _oracle.Net("N", [], net_class=None, weight=None, max_current=None, voltage_class=None)
    rs = RS_NET("N", [], net_class=None, weight=None, max_current=None, voltage_class=None)
    assert py.net_class is None and py.weight is None  # oracle stores the passed None
    assert py.max_current is None and py.voltage_class is None
    assert canon(rs.net_class) == canon("Signal")
    assert canon(rs.weight) == canon(1.0)
    assert canon(rs.max_current) == canon(0.0)
    assert canon(rs.voltage_class) == canon("LV")
    # Omitted-arg defaults agree between the arms.
    assert canon(_oracle.Net("N", []).weight) == canon(RS_NET("N", []).weight)
