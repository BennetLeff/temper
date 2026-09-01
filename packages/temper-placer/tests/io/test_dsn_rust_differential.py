"""Differential test: the Rust DSN emitter vs the pinned Python oracle.

Wave 4, Phase 3 — candidate 6 of
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`` (the DSN
surface; gate ``R1 with deterministic-DSN pinning (R6)``, gate set R1a-R1h).

The migrated surface is ``temper_placer/io/dsn_exporter.py`` (559 LOC) and
``temper_placer/io/dsn.py`` (131 LOC), now delegation shims over
``temper-io-types``' ``dsn_exporter.rs`` / ``dsn_types.rs``. The pre-migration
implementations are pinned VERBATIM as ``_dsn_exporter_py_oracle.py`` and
``_dsn_py_oracle.py`` (origin/main ``ebf9326ff``), and every assertion here
drives IDENTICAL inputs through both sides.

**The contract is bytes, not structure.** DSN output is a serialized artifact:
``io/dsn_schema.py`` hashes the design into a ``;schema-version:`` header that
``io/dsn_validator.py`` fails closed on, and ``tests/io/test_dsn_kicad.py`` pins
the emitted file as importable by KiCad's SPECCTRA importer. So the primary
assertion in every case below is ``str(rust) == str(python)`` — the exact
characters, no normalization, no whitespace tolerance.

That byte assertion is paired with a structural one over the expression tree,
because the two can fail independently: a leaf that drifts from ``int`` to
``float`` renders the same (``10`` either way, since the float formatter trims
``.0``) while being a different value to any downstream consumer that reads
``.args``. The canonicalizer therefore:

  * compares every float as ``float.hex()`` — an exact bit pattern, never a
    tolerance;
  * carries each non-float leaf's concrete ``type`` name in the comparison key,
    so an int/float or str/int drift cannot hide behind numeric equality;
  * walks nested expressions and the ``comment`` field.

Ordering is asserted, not assumed. Several fixtures below exist only to pin an
ordering that a naive port gets wrong: keepouts sort as STRINGS (``KO_10``
before ``KO_2``), image pins sort by the scaled X coordinate first and the pin
number second with a STABLE sort, and padstack/image emission order in
non-deterministic mode is Python dict INSERTION order.
"""

from __future__ import annotations

import numpy as np
import pytest

import tests.io._dsn_exporter_py_oracle as _oracle
from temper_placer.core.board import Board, Layer, LayerStackup
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.dsn_exporter import DSNExporter

# ---------------------------------------------------------------------------
# canonicalization
# ---------------------------------------------------------------------------


def _leaf(value):
    """A comparison key that pins both the VALUE and its concrete TYPE.

    Floats become their exact ``float.hex()`` bit pattern. Everything else
    carries ``type(value).__name__`` alongside the value, so ``10`` (int) and
    ``10.0`` (float) — which render identically through the DSN float
    formatter's trailing-zero trim — are never equal here.
    """
    if isinstance(value, bool):
        # Checked before `int`: bool is an int subclass in CPython, and the
        # DSN formatter's fallthrough renders it as "True", not "1".
        return ("bool", value)
    if isinstance(value, float):
        return ("float", value.hex())
    if isinstance(value, int):
        return ("int", value)
    return (type(value).__name__, value)


def canon(expr):
    """Canonicalize either side's DSNExpression into comparable plain tuples."""
    args = []
    for a in expr.args:
        if hasattr(a, "name") and hasattr(a, "args"):
            args.append(canon(a))
        else:
            args.append(_leaf(a))
    return ("expr", expr.name, tuple(args), _leaf(expr.comment))


def assert_identical(rust_expr, py_expr, label: str) -> None:
    """Assert bit-identical output on both the byte and structural channels."""
    rust_text = str(rust_expr)
    py_text = str(py_expr)
    assert rust_text == py_text, f"{label}: DSN bytes differ"
    assert canon(rust_expr) == canon(py_expr), f"{label}: expression tree differs"


def both(board, netlist, **kwargs):
    """Build the migrated exporter and the pinned oracle over the same inputs."""
    return DSNExporter(board, netlist, **kwargs), _oracle.DSNExporter(board, netlist, **kwargs)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _stackup_4layer() -> LayerStackup:
    return LayerStackup(
        layers=[
            Layer(name="F.Cu", layer_type="signal"),
            Layer(name="In1.Cu", layer_type="plane"),
            Layer(name="In2.Cu", layer_type="mixed"),
            Layer(name="B.Cu", layer_type="signal"),
        ]
    )


def _empty_board() -> tuple[Board, Netlist]:
    return Board(width=100.0, height=80.0), Netlist()


def _rich_netlist() -> Netlist:
    """Components chosen to hit every branch of the library/placement emitters."""
    return Netlist(
        components=[
            # Asymmetric pin layout: non-zero center offset.
            Component(
                ref="J1",
                footprint="Connector:Conn_01x03",
                bounds=(10.0, 3.0),
                pins=[
                    Pin("1", "1", (0.0, 0.0), width=1.5, height=1.5, shape="thru_hole",
                        layer="all"),
                    Pin("2", "2", (10.0, 0.0), width=1.5, height=1.5, shape="thru_hole",
                        layer="all"),
                    Pin("3", "3", (20.0, 0.0), width=1.5, height=1.5, shape="thru_hole",
                        layer="all"),
                ],
                initial_position=(12.5, 30.0),
                initial_rotation_quadrant=2,
            ),
            # Natural-sort bait: pin numbers 1, 2, 10, 11 must not sort lexically.
            Component(
                ref="U1",
                footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                bounds=(5.0, 4.0),
                pins=[
                    Pin("A", "1", (-1.905, 1.905), width=0.6, height=1.5),
                    Pin("B", "2", (-1.905, 0.635), width=0.6, height=1.5),
                    Pin("C", "10", (1.905, 0.635), width=0.6, height=1.5),
                    Pin("D", "11", (1.905, 1.905), width=0.6, height=1.5),
                ],
                initial_position=(40.0, 20.0),
                initial_rotation_quadrant=1,
            ),
            # Back side: `side` must become "back" from the first pin's layer.
            Component(
                ref="R1",
                footprint="Resistor_SMD:R_0805",
                bounds=(2.0, 1.25),
                pins=[
                    Pin("1", "1", (-0.9375, 0.0), width=1.0, height=1.4, layer="B.Cu"),
                    Pin("2", "2", (0.9375, 0.0), width=1.0, height=1.4, layer="B.Cu"),
                ],
                initial_position=(60.0, 45.0),
            ),
            # Shares R1's footprint+ref-suffix shape but a distinct ref, and
            # reuses R1's pad geometry so the padstack dedup path is hit.
            Component(
                ref="R2",
                footprint="Resistor_SMD:R_0805",
                bounds=(2.0, 1.25),
                pins=[
                    Pin("1", "1", (-0.9375, 0.0), width=1.0, height=1.4, layer="B.Cu"),
                    Pin("2", "2", (0.9375, 0.0), width=1.0, height=1.4, layer="B.Cu"),
                ],
                initial_position=(65.0, 45.0),
            ),
            # No pins at all: the `outline` fallback branch.
            Component(
                ref="H1",
                footprint="MountingHole:MountingHole_3.2mm",
                bounds=(3.2, 3.2),
                pins=[],
                initial_position=(5.0, 5.0),
            ),
            # Circle pads on an explicit layer, and a ref that lowercases into a
            # different sort position than it uppercases.
            Component(
                ref="c10",
                footprint="Capacitor_SMD:C_0402",
                bounds=(1.0, 0.5),
                pins=[
                    Pin("1", "1", (-0.48, 0.0), width=0.56, height=0.62, shape="circle"),
                    Pin("2", "2", (0.48, 0.0), width=0.56, height=0.62, shape="circle"),
                ],
                initial_position=(70.0, 10.0),
            ),
        ],
        nets=[
            Net(name="SIG1", pins=[("U1", "1"), ("R1", "1")]),
            Net(name="GND", pins=[("U1", "2"), ("R1", "2"), ("c10", "2")]),
            Net(name="+3V3", pins=[("U1", "10"), ("c10", "1")]),
            Net(name="VCC3V3", pins=[("U1", "11"), ("R2", "1")]),
            Net(name="DC_BUS-", pins=[("J1", "1"), ("R2", "2")]),
            Net(name="net-(U1-Pad2)", pins=[("J1", "2"), ("J1", "3")]),
            Net(name="VDD12V", pins=[("J1", "1"), ("U1", "1")]),
            Net(name="orphan", pins=[]),
        ],
    )


def _rich_board() -> Board:
    return Board(
        width=76.2,
        height=50.8,
        # 12 keepouts, so that KO_10/KO_11 vs KO_2 pins the STRING sort.
        keepouts=[(float(i), float(i) + 0.5, float(i) + 2.0, float(i) + 3.0) for i in range(12)],
        layer_stackup=_stackup_4layer(),
    )


# ---------------------------------------------------------------------------
# R1a — behavioral A/B, per section
# ---------------------------------------------------------------------------


def test_structure_empty_board_bit_identical():
    board, netlist = _empty_board()
    r, p = both(board, netlist)
    assert_identical(r.export_structure(), p.export_structure(), "structure/empty")


def test_structure_4layer_both_layer_type_modes():
    board = Board(width=50.0, height=50.0, layer_stackup=_stackup_4layer())
    r, p = both(board, Netlist())
    assert_identical(r.export_structure(True), p.export_structure(True), "structure/signal")
    assert_identical(r.export_structure(False), p.export_structure(False), "structure/types")


def test_structure_keepouts_sort_as_strings_not_numbers():
    """KO_10 and KO_11 must precede KO_2 — the key is `str(k.args[0])`."""
    board = _rich_board()
    r, p = both(board, Netlist())
    assert_identical(r.export_structure(), p.export_structure(), "structure/keepouts")
    text = str(r.export_structure())
    assert text.index("KO_10") < text.index("KO_2"), "keepout order is not the pinned string sort"


def test_structure_boundary_uses_bankers_rounding():
    """`round()` is half-to-even in Python; `f64::round` is half-away-from-zero.

    A board 0.005mm over a 10um tick scales to an exact .5 and must round DOWN
    to the even neighbour. This fixture fails against a naive `f64::round` port.
    """
    for width, height in [
        (100.005, 80.015),  # -> 10000.5 / 8001.5
        (0.005, 0.015),  # -> 0.5 / 1.5
        (0.025, 0.035),  # -> 2.5 / 3.5
    ]:
        board = Board(width=width, height=height)
        r, p = both(board, Netlist())
        assert_identical(r.export_structure(), p.export_structure(), f"round/{width}")


def test_library_rich_netlist_bit_identical():
    r, p = both(_rich_board(), _rich_netlist())
    assert_identical(r.export_library(), p.export_library(), "library/rich")


def test_library_pin_order_is_natural_not_lexical():
    r, p = both(_rich_board(), _rich_netlist())
    text = str(r.export_library())
    assert_identical(r.export_library(), p.export_library(), "library/order")
    # U1 has pins 1, 2, 10, 11 — a lexical sort would put 10 and 11 first.
    img = text[text.index("Package_SO_SOIC-8") :]
    img = img[: img.index("(image", 1)] if "(image" in img[1:] else img
    # `(pin <padstack> <number> <x> <y>)` — index 1 is the pin number.
    order = [seg.split()[1] for seg in img.split("(pin ")[1:]]
    assert order == ["1", "2", "10", "11"], f"pin order {order} is not natural"


def test_placement_rich_netlist_bit_identical():
    r, p = both(_rich_board(), _rich_netlist())
    assert_identical(r.export_placement(), p.export_placement(), "placement/rich")


def test_network_rich_netlist_bit_identical():
    r, p = both(_rich_board(), _rich_netlist())
    assert_identical(r.export_network(), p.export_network(), "network/rich")


def test_network_without_net_classes():
    r, p = both(_rich_board(), _rich_netlist())
    assert_identical(
        r.export_network(use_net_classes=False),
        p.export_network(use_net_classes=False),
        "network/no-classes",
    )


@pytest.mark.parametrize(
    "exclude",
    [
        None,
        set(),
        {"GND"},
        {"+3V3"},  # excluded by its RAW name
        {"_PLUS3V3"},  # excluded by its SANITIZED name
        {"GND", "SIG1", "VCC3V3", "nonexistent"},
    ],
)
def test_network_exclude_nets_bit_identical(exclude):
    r, p = both(_rich_board(), _rich_netlist())
    assert_identical(
        r.export_network(exclude_nets=exclude),
        p.export_network(exclude_nets=exclude),
        f"network/exclude={exclude}",
    )


def test_network_power_classification_edges():
    """Every arm of the prefix list and the voltage regex, plus its near-misses."""
    names = [
        "GND", "PGND", "CGND", "VCC", "VDD", "DC_BUS", "_PLUS",
        "GNDA", "VCC3V3", "vcc3v3", "VDD12", "VDD12V", "VDD12V5",
        "+5V", "+3V3", "-12V", "A+B", "A-B",
        "SIG_VCC3V3", "XGND", "MYVDD5V", "NET1", "clk", "",
        # Lower-case AND not prefix-matched: the ONLY shape in which the
        # regex's re.IGNORECASE is observable. Without these, dropping `(?i)`
        # changes nothing anywhere in the suite (found by mutation M5).
        "sig_vcc3v3", "myvdd5v", "x_plus12v", "a_vdd3", "n_vcc9v9",
    ]
    netlist = Netlist(
        components=[
            Component(ref=f"U{i}", footprint="fp", bounds=(1.0, 1.0),
                      pins=[Pin("1", "1", (0.0, 0.0))])
            for i in range(len(names))
        ],
        nets=[Net(name=n, pins=[(f"U{i}", "1")]) for i, n in enumerate(names) if n],
    )
    r, p = both(Board(width=10.0, height=10.0), netlist)
    assert_identical(r.export_network(), p.export_network(), "network/classification")


def test_wiring_bit_identical():
    from temper_placer.io._kicad_types import TraceData

    traces = [
        TraceData(start=(0.0, 0.0), end=(10.0, 10.0), width=0.2, layer="F.Cu", net="SIG1"),
        TraceData(start=(-1.5, 2.25), end=(3.125, -4.0), width=0.15, layer="B.Cu", net="GND"),
        TraceData(start=(1e-7, 1e7), end=(0.0000005, 123456.789), width=0.9999995,
                  layer="In1.Cu", net="X"),
    ]
    r, p = both(_rich_board(), _rich_netlist())
    assert_identical(r.export_wiring(traces), p.export_wiring(traces), "wiring")
    assert_identical(r.export_wiring([]), p.export_wiring([]), "wiring/empty")


def test_export_pcb_full_bit_identical():
    from temper_placer.io._kicad_types import TraceData

    traces = [TraceData(start=(0.0, 0.0), end=(1.0, 1.0), width=0.2, layer="F.Cu", net="SIG1")]
    r, p = both(_rich_board(), _rich_netlist())
    assert_identical(r.export_pcb("temper"), p.export_pcb("temper"), "pcb/plain")
    assert_identical(
        r.export_pcb("temper", traces=traces), p.export_pcb("temper", traces=traces), "pcb/traces"
    )
    assert_identical(
        r.export_pcb("temper", traces=[]), p.export_pcb("temper", traces=[]), "pcb/empty-traces"
    )
    assert_identical(
        r.export_pcb("x", exclude_nets={"GND"}),
        p.export_pcb("x", exclude_nets={"GND"}),
        "pcb/exclude",
    )


def test_export_pcb_carries_the_schema_version_header():
    """The header the validator fails closed on must survive the migration."""
    r, p = both(_rich_board(), _rich_netlist())
    rust_text = str(r.export_pcb("temper"))
    assert rust_text.startswith(";schema-version: sha256:")
    assert rust_text == str(p.export_pcb("temper"))


def test_positions_and_rotations_arrays_bit_identical():
    netlist = _rich_netlist()
    n = len(netlist.components)
    rng = np.random.default_rng(20260804)
    positions = rng.uniform(0.0, 70.0, size=(n, 2))
    # Exact .5 ticks after scaling, to keep the rounding mode under test.
    positions[0] = [0.005, 0.015]
    positions[1] = [12.345, 0.025]
    one_hot = np.zeros((n, 4))
    for i in range(n):
        one_hot[i, i % 4] = 1.0
    flat = np.array([i % 4 for i in range(n)])

    for label, rot in [("one-hot", one_hot), ("flat", flat), ("none", None)]:
        r, p = both(_rich_board(), netlist, positions=positions, rotations=rot)
        assert_identical(r.export_placement(), p.export_placement(), f"placement/{label}")
        assert_identical(r.export_pcb("t"), p.export_pcb("t"), f"pcb/{label}")


def test_non_deterministic_mode_bit_identical():
    """The fanout-then-span ordering, and dict INSERTION order for emission."""
    netlist = _rich_netlist()
    r, p = both(_rich_board(), netlist, deterministic=False)
    assert_identical(r.export_structure(), p.export_structure(), "nd/structure")
    assert_identical(r.export_library(), p.export_library(), "nd/library")
    assert_identical(r.export_placement(), p.export_placement(), "nd/placement")
    assert_identical(r.export_network(), p.export_network(), "nd/network")
    assert_identical(r.export_pcb("t"), p.export_pcb("t"), "nd/pcb")


def test_non_deterministic_mode_with_rotations():
    netlist = _rich_netlist()
    n = len(netlist.components)
    rots = np.array([i % 4 for i in range(n)])
    r, p = both(_rich_board(), netlist, rotations=rots, deterministic=False)
    assert_identical(r.export_placement(), p.export_placement(), "nd/placement-rot")
    assert_identical(r.export_network(), p.export_network(), "nd/network-rot")


def test_non_deterministic_pcb_has_no_schema_comment():
    r, p = both(_rich_board(), _rich_netlist(), deterministic=False)
    assert not str(r.export_pcb("t")).startswith(";")
    assert_identical(r.export_pcb("t"), p.export_pcb("t"), "nd/pcb-no-comment")


def test_center_offsets_bit_identical():
    r, p = both(_rich_board(), _rich_netlist())
    rust = [tuple(t) for t in r._center_offsets]
    py = [tuple(t) for t in p._center_offsets]
    assert [(_leaf(x), _leaf(y)) for x, y in rust] == [(_leaf(x), _leaf(y)) for x, y in py]


def test_empty_netlist_every_section():
    board, netlist = _empty_board()
    r, p = both(board, netlist)
    for name in ("export_structure", "export_library", "export_placement", "export_network"):
        assert_identical(getattr(r, name)(), getattr(p, name)(), f"empty/{name}")
    assert_identical(r.export_pcb("e"), p.export_pcb("e"), "empty/pcb")


def test_duplicate_refs_resolve_to_the_last_occurrence():
    """`Netlist._component_index` is a dict comprehension: last write wins."""
    netlist = Netlist(
        components=[
            Component(ref="U1", footprint="a", bounds=(1.0, 1.0),
                      pins=[Pin("1", "1", (0.0, 0.0))]),
            Component(ref="U1", footprint="b", bounds=(1.0, 1.0),
                      pins=[Pin("1", "1", (5.0, 5.0))]),
            Component(ref="U2", footprint="c", bounds=(1.0, 1.0),
                      pins=[Pin("1", "1", (2.0, 2.0))]),
        ],
        nets=[Net(name="N", pins=[("U1", "1"), ("U2", "1")])],
    )
    board = Board(width=20.0, height=20.0)
    for det in (True, False):
        r, p = both(board, netlist, deterministic=det)
        assert_identical(r.export_pcb("d"), p.export_pcb("d"), f"dup-ref/det={det}")


def test_net_names_needing_dsn_quoting():
    names = ['has space', 'has(paren)', 'has"quote"', "", "tab\tsep", "uni-Δ"]
    netlist = Netlist(
        components=[
            Component(ref=f"U{i}", footprint="f p", bounds=(1.0, 1.0),
                      pins=[Pin("1", "1", (0.0, 0.0))])
            for i in range(len(names))
        ],
        nets=[Net(name=n, pins=[(f"U{i}", "1")]) for i, n in enumerate(names)],
    )
    r, p = both(Board(width=10.0, height=10.0), netlist)
    assert_identical(r.export_network(), p.export_network(), "quoting")
    assert_identical(r.export_library(), p.export_library(), "quoting/library")


def test_pad_dimensions_that_stress_the_3dp_format():
    """`f"{w:.3f}"` feeds the padstack NAME, so its rounding is observable."""
    dims = [
        (0.0005, 0.0015),  # half-way at the 3rd decimal
        (0.0025, 0.0035),
        (1.0 / 3.0, 2.0 / 3.0),
        (0.1 + 0.2, 1e-9),
        (1234.5678, 0.9995),
        # Subnormal: the one region where reassociating the `/2` and the `*S`
        # in the pad half-extent is NOT bit-neutral (found by mutation M10).
        (5e-324, 1e-320),
    ]
    netlist = Netlist(
        components=[
            Component(
                ref=f"U{i}", footprint="fp", bounds=(1.0, 1.0),
                pins=[Pin("1", "1", (0.0, 0.0), width=w, height=h)],
            )
            for i, (w, h) in enumerate(dims)
        ]
    )
    r, p = both(Board(width=10.0, height=10.0), netlist)
    assert_identical(r.export_library(), p.export_library(), "pad-dims")


def test_pin_coordinates_that_stress_the_rounding_mode():
    coords = [
        (0.005, 0.015), (0.025, 0.035), (-0.005, -0.015), (-0.025, -0.035),
        (0.0049999999, 0.0050000001), (1e-12, -1e-12),
    ]
    netlist = Netlist(
        components=[
            Component(
                ref=f"U{i}", footprint="fp", bounds=(1.0, 1.0),
                pins=[
                    Pin("1", "1", (x, y), width=0.0, height=0.0),
                    Pin("2", "2", (-x, -y), width=0.0, height=0.0),
                ],
            )
            for i, (x, y) in enumerate(coords)
        ]
    )
    r, p = both(Board(width=10.0, height=10.0), netlist)
    assert_identical(r.export_library(), p.export_library(), "pin-round")


def test_shape_and_layer_variants():
    shapes = [None, "", "rect", "circle", "oval", "roundrect", "thru_hole", "Rect", "CIRCLE"]
    layers = ["F.Cu", "B.Cu", "all", "In1.Cu", "weird.layer.name"]
    comps = []
    i = 0
    for sh in shapes:
        for ly in layers:
            kwargs = {"width": 0.5, "height": 0.7, "layer": ly}
            if sh is not None:
                kwargs["shape"] = sh
            comps.append(
                Component(ref=f"U{i}", footprint="fp", bounds=(1.0, 1.0),
                          pins=[Pin("1", "1", (0.0, 0.0), **kwargs)])
            )
            i += 1
    r, p = both(_rich_board(), Netlist(components=comps))
    assert_identical(r.export_library(), p.export_library(), "shapes")


def test_footprint_names_with_separators():
    fps = ["Lib:Foot", "a/b/c", "Lib:a/b", "plain", "::", "//", "Lib:Foot_U1"]
    netlist = Netlist(
        components=[
            Component(ref=f"U{i}", footprint=f, bounds=(1.0, 1.0),
                      pins=[Pin("1", "1", (0.0, 0.0))])
            for i, f in enumerate(fps)
        ]
    )
    r, p = both(Board(width=10.0, height=10.0), netlist)
    assert_identical(r.export_library(), p.export_library(), "fp-names/library")
    assert_identical(r.export_placement(), p.export_placement(), "fp-names/placement")


def test_refs_that_collide_only_after_lowercasing():
    """The image/placement sorts key on `.lower()`; ties must stay stable."""
    refs = ["U1", "u1", "U10", "u2", "U2", "AA", "aa", "Ab", "aB"]
    netlist = Netlist(
        components=[
            Component(ref=r_, footprint="fp", bounds=(1.0, 1.0),
                      pins=[Pin("1", "1", (0.0, 0.0))])
            for r_ in refs
        ]
    )
    r, p = both(Board(width=10.0, height=10.0), netlist)
    assert_identical(r.export_library(), p.export_library(), "lower-ties/library")
    assert_identical(r.export_placement(), p.export_placement(), "lower-ties/placement")


def test_pin_number_natural_sort_edges():
    numbers = ["1", "2", "10", "11", "007", "7", "A1", "A10", "A2", "1A", "", "-1", "-10", "1.5"]
    netlist = Netlist(
        components=[
            Component(
                ref="U1", footprint="fp", bounds=(1.0, 1.0),
                # Distinct x per pin so the first (x-coordinate) sort is a real
                # permutation before the stable pin-number sort runs.
                pins=[
                    Pin(n or "e", n, (float(i) - 6.0, 0.0), width=0.2, height=0.2)
                    for i, n in enumerate(numbers)
                ],
            )
        ]
    )
    r, p = both(Board(width=30.0, height=10.0), netlist)
    assert_identical(r.export_library(), p.export_library(), "pin-natural")


def test_no_stackup_falls_back_to_two_layers():
    board = Board(width=10.0, height=10.0)
    board.layer_stackup = None
    netlist = _rich_netlist()
    r, p = both(board, netlist)
    for name in ("export_structure", "export_library", "export_placement", "export_network"):
        assert_identical(getattr(r, name)(), getattr(p, name)(), f"no-stackup/{name}")


# The ``_dsn_py_oracle.py`` DSN primitive types oracle was retired by FREEZE
# on 2026-08-21 (batch 3): its golden vectors are baked into
# ``dsn_types.rs``'s ``frozen_dsn_tests`` module, generated by
# ``scripts/oracle_freeze_specs/dsn_primitives.py`` (100 cases, 15
# non-vacuity checks). The two tests that compared against it
# (``test_dsn_primitives_match_the_pinned_python`` and
# ``test_bool_argument_formats_as_python_str_not_as_int``) are superseded by
# that frozen corpus.


# ---------------------------------------------------------------------------
# R1a — the shipped corpus, end to end
# ---------------------------------------------------------------------------


CORPUS = [
    "power_pcb_dataset/corpus/temper",
    "power_pcb_dataset/corpus/minimal",
    "power_pcb_dataset/corpus/bitaxe_ultra",
    "power_pcb_dataset/corpus/rp2040_designguide",
    "power_pcb_dataset/corpus/piantor_right",
]


def _corpus_boards():
    """Every parsed corpus board, so the differential runs on real designs."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[4]
    for rel in CORPUS:
        d = root / rel
        if not d.is_dir():
            continue
        for pcb in sorted(d.glob("*.kicad_pcb")):
            yield rel, pcb


@pytest.mark.parametrize("deterministic", [True, False])
def test_corpus_boards_export_bit_identically(deterministic):
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    seen = 0
    for rel, pcb in _corpus_boards():
        result = parse_kicad_pcb(pcb)
        r, p = both(result.board, result.netlist, deterministic=deterministic)
        assert_identical(r.export_pcb(pcb.stem), p.export_pcb(pcb.stem), f"corpus/{rel}/{pcb.name}")
        seen += 1
    assert seen > 0, "corpus differential ran on zero boards — the fixture path is wrong"


# ---------------------------------------------------------------------------
# R1d — metamorphic relations (honestly bounded)
# ---------------------------------------------------------------------------


def test_metamorphic_determinism_is_idempotent():
    """M1. Re-exporting the same inputs yields the same bytes, on both sides.

    Bound: this shows stability across calls, not across processes; the hash
    header is what pins cross-process stability, and it is asserted separately.
    """
    board, netlist = _rich_board(), _rich_netlist()
    r, p = both(board, netlist)
    a, b = str(r.export_pcb("t")), str(r.export_pcb("t"))
    assert a == b == str(p.export_pcb("t"))


def test_metamorphic_input_order_does_not_change_deterministic_output():
    """M2. Permuting components and nets leaves deterministic output unchanged.

    Bound: holds only in deterministic mode and only for permutations that do
    not change the multiset — the non-deterministic path orders by fanout and
    span and is explicitly permitted to differ, which the paired assertion on
    the oracle confirms rather than assumes.
    """
    board = _rich_board()
    base = _rich_netlist()
    shuffled = Netlist(
        components=list(reversed(base.components)),
        nets=list(reversed(base.nets)),
    )
    r1, p1 = both(board, base)
    r2, p2 = both(board, shuffled)
    # The library/placement/network sections are order-independent...
    assert str(r1.export_placement()) == str(r2.export_placement())
    assert str(r1.export_network()) == str(r2.export_network())
    # ...and the port agrees with the oracle on exactly that, in both orders.
    assert str(r2.export_placement()) == str(p2.export_placement())
    assert str(r2.export_network()) == str(p2.export_network())


def test_metamorphic_excluding_a_net_removes_only_that_net():
    """M3. Excluding one net drops its `(net ...)` and leaves the rest intact.

    Bound: the net CLASS lists also lose the name, so the relation is stated
    over the `(net <name> ...)` forms only — asserted against the oracle so the
    class-level consequence is still pinned byte-for-byte.
    """
    board, netlist = _rich_board(), _rich_netlist()
    r, p = both(board, netlist)
    full = str(r.export_network())
    without = str(r.export_network(exclude_nets={"GND"}))
    assert "(net GND " in full and "(net GND " not in without
    for name in ("SIG1", "_PLUS3V3", "VCC3V3"):
        assert f"(net {name} " in full and f"(net {name} " in without
    assert without == str(p.export_network(exclude_nets={"GND"}))


def test_metamorphic_translating_all_pads_translates_the_image_not_at_all():
    """M4. A rigid translation of every pad in a footprint cancels out.

    The image centers pins on their own bounding box, so translating all of a
    component's pins by the same offset must leave `(image ...)` unchanged and
    move only `(place ...)`.

    Bound: exact only when the translation is representable such that the
    center offset subtracts back exactly — powers of two are, so the fixture
    uses them; the general float case is covered by the PBT suite instead.
    """
    def _netlist(dx: float, dy: float) -> Netlist:
        return Netlist(
            components=[
                Component(
                    ref="U1", footprint="fp", bounds=(4.0, 4.0),
                    pins=[
                        Pin("1", "1", (-1.0 + dx, -1.0 + dy), width=0.5, height=0.5),
                        Pin("2", "2", (1.0 + dx, 1.0 + dy), width=0.5, height=0.5),
                    ],
                    initial_position=(10.0, 10.0),
                )
            ]
        )

    board = Board(width=40.0, height=40.0)
    base_r, base_p = both(board, _netlist(0.0, 0.0))
    moved_r, moved_p = both(board, _netlist(0.25, 0.5))
    assert str(base_r.export_library()) == str(moved_r.export_library())
    assert str(base_r.export_library()) == str(base_p.export_library())
    assert str(moved_r.export_library()) == str(moved_p.export_library())
    assert str(base_r.export_placement()) != str(moved_r.export_placement())
    assert str(moved_r.export_placement()) == str(moved_p.export_placement())
