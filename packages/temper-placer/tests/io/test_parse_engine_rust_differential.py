"""Differential test: Rust parse engine (temper_design_bundle_python.parse_engine)
vs the pinned verbatim kiutils oracle.

Wave 4, Phase 3, candidate 3 -- the parse engine
(``io/kicad_parser.py``, ``io/_parse_*``, ``io/_kicad_types.py``,
``io/kicad_metadata.py``), per plan
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``.

The pre-migration kiutils implementation is pinned VERBATIM as the oracle
(``tests/io/_parse_engine_py_oracle/``, commit 79ab9bd0e) and every
assertion here drives IDENTICAL inputs through both sides. The Rust engine
parses the raw ``.kicad_pcb`` text itself (kiutils leaves the boundary,
parent R4); it must reproduce the kiutils-based extraction bit-identically.

Comparison convention (mirrors the priority/loop differentials): objects are
canonicalized into comparable tuples before assertion. Every non-float leaf
carries its CONCRETE type in the key (``("int", v)`` vs ``("float", v.hex())``)
so int-vs-float cannot hide behind numeric equality; floats are compared as
exact bit patterns via ``float.hex()``. Dicts are compared key-sorted
(insertion order is not part of these outputs' contract); lists and tuples in
order.

Empty-input semantics are asserted explicitly (see test_empty_input_*): the
engine must raise on empty/blank content -- never return a half-built result.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import temper_design_bundle_python as _tdb

from tests.io._parse_engine_py_oracle import _parse_board as _oracle_board
from tests.io._parse_engine_py_oracle import _parse_nets as _oracle_nets
from tests.io._parse_engine_py_oracle import kicad_metadata as _oracle_metadata
from tests.io._parse_engine_py_oracle import kicad_parser as _oracle_parser

# Rust symbols under test -- must exist or this file fails to collect (RED).
_PARSE_ENGINE = _tdb.parse_engine

REPO_ROOT = Path(__file__).resolve().parents[4]
CORPUS = [
    ("temper", REPO_ROOT / "power_pcb_dataset" / "corpus" / "temper" / "temper.kicad_pcb"),
    ("minimal", REPO_ROOT / "power_pcb_dataset" / "corpus" / "minimal" / "minimal_board.kicad_pcb"),
    (
        "rp2040",
        REPO_ROOT / "power_pcb_dataset" / "corpus" / "rp2040_designguide" / "RP2040-Guide.kicad_pcb",
    ),
    (
        "bitaxe",
        REPO_ROOT / "power_pcb_dataset" / "corpus" / "bitaxe_ultra" / "bitaxeUltra.kicad_pcb",
    ),
    (
        "piantor",
        REPO_ROOT / "power_pcb_dataset" / "corpus" / "piantor_right" / "keyboard_pcb.kicad_pcb",
    ),
    ("pcb", REPO_ROOT / "pcb" / "temper.kicad_pcb"),
]

# Corpus ids that carry routed traces/vias/zones/stackup (used to skip
# per-surface assertions where the corpus cannot exercise them).
TRACED = {"rp2040", "bitaxe", "piantor", "pcb"}
ZONED = {"rp2040", "bitaxe", "piantor", "pcb"}
STACKUP = {"rp2040", "bitaxe", "piantor"}
PCB_PRODUCTION = {"pcb"}


# ---------------------------------------------------------------------------
# Canonicalization: concrete-type-carrying, bit-exact comparison keys.
# ---------------------------------------------------------------------------


def _canon(value, _depth=0):
    """Recursive comparison key carrying the concrete type of every leaf.

    Floats -> ("float", value.hex()); ints stay ("int", v); lists and tuples
    keep order; dicts are key-sorted. numpy arrays -> (dtype, shape, bytes).
    pyclass/dataclass objects -> (ClassName, field-keys...) via _FIELD_TABLE.
    """
    t = type(value)
    if value is None:
        return ("none",)
    if t is bool:
        return ("bool", value)
    if t is int:
        return ("int", value)
    if t is float:
        return ("float", value.hex())
    if t is str:
        return ("str", value)
    if t is tuple:
        return ("tuple", tuple(_canon(x, _depth + 1) for x in value))
    if t is list:
        return ("list", tuple(_canon(x, _depth + 1) for x in value))
    if t is dict:
        return (
            "dict",
            tuple(
                (_canon(k, _depth + 1), _canon(v, _depth + 1))
                for k, v in sorted(value.items(), key=lambda kv: repr(kv[0]))
            ),
        )
    if t.__module__ == "numpy":
        return ("ndarray", str(value.dtype), tuple(value.shape), value.tobytes())
    name = t.__name__
    fields = _FIELD_TABLE.get(name)
    if fields is not None:
        return (name, tuple(_canon(getattr(value, f), _depth + 1) for f in fields))
    return ("pyclass", name, repr(value))


_FIELD_TABLE = {
    "ParseResult": ("netlist", "board", "warnings", "traces", "vias", "pads"),
    "TraceData": ("start", "end", "width", "layer", "net"),
    "PadData": (
        "position",
        "size",
        "shape",
        "drill",
        "rotation",
        "layer",
        "number",
        "net",
        "component_ref",
    ),
    "ViaData": ("position", "diameter", "drill", "net", "layers"),
    "Netlist": ("components", "nets"),
    "Component": (
        "ref",
        "footprint",
        "bounds",
        "pins",
        "net_class",
        "zone",
        "fixed",
        "initial_position",
        "initial_rotation",
        "initial_side",
        "attributes",
        "tags",
        "sheetpath",
    ),
    "Pin": (
        "name",
        "number",
        "position",
        "net",
        "width",
        "height",
        "shape",
        "layer",
        "drill",
        "is_pth",
        "roundrect_ratio",
        "pad_rotation_deg",
    ),
    "Net": ("name", "pins"),
    "Board": (
        "width",
        "height",
        "origin",
        "zones",
        "mounting_holes",
        "keepouts",
        "ground_domains",
        "layer_stackup",
        "outline_polygon",
        "_zone_map",
    ),
    "MountingHole": ("position", "diameter", "keepout_radius"),
    "Zone": (
        "name",
        "bounds",
        "net_classes",
        "components",
        "weight",
        "polygon",
        "layers",
        "max_size",
        "can_expand",
        "zone_type",
    ),
    "LayerStackup": ("layers", "thickness"),
    "Layer": ("name", "layer_type", "copper_weight", "is_routable"),
    "DrillDefinition": ("oval", "diameter", "width", "offset"),
    "Position": ("X", "Y", "angle", "unlocked"),
    "KiCadMetadata": ("courtyards", "pad_sizes", "board_width", "board_height"),
    "PadSize": ("component_ref", "pad_number", "width", "height", "shape"),
    "Courtyard": ("component_ref", "points"),
    "StackupInfo": ("layers", "total_thickness_mm", "layer_count", "dielectrics"),
    "LayerInfo": ("index", "name", "layer_type", "thickness_um", "plane_net"),
    "DielectricInfo": ("name", "material", "thickness_mm", "epsilon_r", "loss_tangent"),
}


def assert_same(actual, expected, label):
    """Bit-exact canonical comparison with a leaf-level failure report."""
    ca, ce = _canon(actual), _canon(expected)
    assert ca == ce, (
        f"{label}: canonical keys differ\n"
        f"  actual:   {str(ca)[:400]}\n"
        f"  expected: {str(ce)[:400]}"
    )


def _content(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# R1a -- behavioural A/B: parse_kicad_pcb bit-parity on the corpus.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("corpus_id,path", CORPUS, ids=[c for c, _ in CORPUS])
@pytest.mark.parametrize("normalize", [True, False], ids=["normalize", "raw"])
def test_parse_kicad_pcb_bit_parity(corpus_id, path, normalize):
    content = _content(path)
    oracle = _oracle_parser.parse_kicad_pcb(path, normalize=normalize)
    rust = _PARSE_ENGINE.parse_kicad_pcb(content, normalize=normalize)
    assert_same(rust, oracle, f"{corpus_id} parse_kicad_pcb(normalize={normalize})")


# ---------------------------------------------------------------------------
# Discriminating fixtures (close surviving mutants the corpus cannot reach)
# ---------------------------------------------------------------------------

# M8 anti-vacuity: a segment on net 0 ("" -- falsy). The corpus has no
# net-0 trace, so only this fixture discriminates "net 0 stays unnamed" from
# "net 0 resolves like any net". Needs a footprint: the parse returns early
# (empty traces) when the board has no footprints.
NET0_FIXTURE = """(kicad_pcb (version 20211014) (generator test)
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  (net 0 "")
  (net 1 "GND")
  (gr_line (start 0 0) (end 100 0) (layer "Edge.Cuts"))
  (gr_line (start 100 0) (end 100 100) (layer "Edge.Cuts"))
  (gr_line (start 100 100) (end 0 100) (layer "Edge.Cuts"))
  (gr_line (start 0 100) (end 0 0) (layer "Edge.Cuts"))
  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu")
    (at 50 50)
    (property "Reference" "R1")
    (pad "1" smd rect (at -0.8 0) (size 1.0 1.0) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "GND"))
  )
  (segment (start 10 10) (end 20 10) (width 0.25) (layer "F.Cu") (net 0))
  (segment (start 30 10) (end 40 10) (width 0.25) (layer "F.Cu") (net 1))
)
"""


def test_net0_trace_remains_unnamed():
    """A trace on net 0 (the empty net) must get net=None -- `if track.net:`
    is a truthiness test, and int 0 is falsy. Closes the M8 surviving
    mutant (the corpus has no net-0 traces)."""
    # Write the fixture for the oracle (it reads paths).
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "net0.kicad_pcb"
        p.write_text(NET0_FIXTURE)
        oracle = _oracle_parser.parse_kicad_pcb(p, normalize=True)
        rust = _PARSE_ENGINE.parse_kicad_pcb(NET0_FIXTURE, normalize=True)
        assert_same(rust, oracle, "net0 fixture")
        nets = {t.net for t in rust.traces}
        assert nets == {None, "GND"}, f"net0 fixture trace nets: {nets}"

# ---------------------------------------------------------------------------
# Discriminating fixtures from the adversarial review (each RED first).
# ---------------------------------------------------------------------------


def _board(body: str, nets: str = '  (net 0 "")\n  (net 1 "GND")\n') -> str:
    """A minimal valid board: nets, an Edge.Cuts outline, and `body`."""
    return (
        "(kicad_pcb (version 20211014) (generator test)\n"
        "  (general (thickness 1.6))\n"
        '  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))\n'
        f"{nets}"
        '  (gr_line (start 0 0) (end 100 0) (layer "Edge.Cuts"))\n'
        '  (gr_line (start 100 0) (end 100 100) (layer "Edge.Cuts"))\n'
        '  (gr_line (start 100 100) (end 0 100) (layer "Edge.Cuts"))\n'
        '  (gr_line (start 0 100) (end 0 0) (layer "Edge.Cuts"))\n'
        f"{body}"
        ")\n"
    )


def _raised_by(fn):
    """Run `fn()`; return the exception type it raised, or None if it
    returned normally. (B017 forbids asserting blind `pytest.raises(Exception)`
    -- the oracle raises a different exception type per malformed token
    family, so the probe asserts "an exception of some type" instead.)"""
    try:
        fn()
        return None
    except Exception as e:
        return type(e)


def _assert_both_raise(content: str, label: str):
    """Both arms must fail closed on a malformed board (the parity contract:
    a token kiutils raises on must not silently degrade to a default value in
    Rust)."""
    import tempfile

    def oracle_run():
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "malformed.kicad_pcb"
            p.write_text(content)
            _oracle_parser.parse_kicad_pcb(p, normalize=True)

    assert _raised_by(oracle_run) is not None, f"{label}: oracle did not raise"
    assert _raised_by(
        lambda: _PARSE_ENGINE.parse_kicad_pcb(content, normalize=True)
    ) is not None, f"{label}: Rust did not raise (fail-open)"


def _assert_same_content(content: str, label: str):
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "fixture.kicad_pcb"
        p.write_text(content)
        oracle = _oracle_parser.parse_kicad_pcb(p, normalize=True)
    rust = _PARSE_ENGINE.parse_kicad_pcb(content, normalize=True)
    assert_same(rust, oracle, label)


# P1a: an empty-string Reference property must DROP the footprint (the
# oracle's `if not ref or ref.startswith("REF**")` treats "" as falsy). The
# corpus has no empty-reference footprint, so only this fixture discriminates
# the phantom-component mutant.
EMPTY_REF_FIXTURE = _board(
    '  (footprint "R:R_0603" (layer "F.Cu") (at 50 50)\n'
    '    (property "Reference" "")\n'
    '    (pad "1" smd rect (at -0.8 0) (size 1.0 1.0) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "GND"))\n'
    "  )\n"
)


def test_empty_ref_property_footprint_dropped():
    _assert_same_content(EMPTY_REF_FIXTURE, "empty-ref fixture")
    comps = _PARSE_ENGINE.parse_kicad_pcb(EMPTY_REF_FIXTURE, normalize=True).netlist.components
    assert comps == [], f"empty-reference footprint emitted: {comps}"


# P1a: a footprint token with no libId (its first child is `(layer ...)`)
# makes kiutils store the RAW LIST as entryName, and the oracle's
# `_get_footprint_reference` raises AttributeError on `ename.startswith` --
# the engine must fail closed the same way, never emitting a phantom
# Component with ref=''.
NO_LIBID_FIXTURE = _board(
    '  (footprint (layer "F.Cu") (at 50 50)\n'
    '    (pad "1" smd rect (at -0.8 0) (size 1.0 1.0) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "GND"))\n'
    "  )\n"
)


def test_no_libid_footprint_raises():
    _assert_both_raise(NO_LIBID_FIXTURE, "no-libId fixture")


# P1b: a nameless pad `(net 1)` makes kiutils' Net.from_sexpr raise
# IndexError on `exp[2]`; the engine must fail closed. (A full ParseResult
# with pin.net='' would be fail-open -- the pin is then silently dropped as
# unconnected by the `if not pin.net` filter.)
NAMELESS_PAD_NET_FIXTURE = _board(
    '  (footprint "R:R_0603" (layer "F.Cu") (at 50 50)\n'
    '    (property "Reference" "R1")\n'
    '    (pad "1" smd rect (at -0.8 0) (size 1.0 1.0) (layers "F.Cu" "F.Paste" "F.Mask") (net 1))\n'
    "  )\n"
)


def test_nameless_pad_net_raises():
    _assert_both_raise(NAMELESS_PAD_NET_FIXTURE, "nameless pad net fixture")


NAMELESS_BOARD_NET_FIXTURE = _board(
    '  (footprint "R:R_0603" (layer "F.Cu") (at 50 50)\n'
    '    (property "Reference" "R1")\n'
    '    (pad "1" smd rect (at -0.8 0) (size 1.0 1.0) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "GND"))\n'
    "  )\n",
    nets='  (net 0 "")\n  (net 1)\n',
)


def test_nameless_board_net_raises():
    _assert_both_raise(NAMELESS_BOARD_NET_FIXTURE, "nameless board net fixture")


# P2b: a via without a `(layers ...)` token. kiutils' Via defaults layers to
# [] and the oracle's `tuple(track.layers) if hasattr(...)` LIVE branch
# yields () (the ("F.Cu","B.Cu") else-branch is dead code there). Empty must
# stay empty. Needs a footprint: the parse early-returns empty traces on a
# footprint-less board, which masks this.
VIA_NO_LAYERS_FIXTURE = _board(
    '  (footprint "R:R_0603" (layer "F.Cu") (at 50 50)\n'
    '    (property "Reference" "R1")\n'
    '    (pad "1" smd rect (at 0 0) (size 1.0 1.0) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "GND"))\n'
    "  )\n"
    "  (via (at 10 10) (size 0.6) (drill 0.3) (net 1))\n"
)


def test_via_without_layers_stays_empty():
    _assert_same_content(VIA_NO_LAYERS_FIXTURE, "via-no-layers fixture")
    vias = _PARSE_ENGINE.parse_kicad_pcb(VIA_NO_LAYERS_FIXTURE, normalize=True).vias
    assert vias and vias[0].layers == (), f"via layers: {vias[0].layers}"


# P2c: a drill offset keeps its angle and the unlocked marker -- kiutils'
# Position.from_sexpr stores exp[3] as angle unless it is 'unlocked' and
# scans the WHOLE list for 'unlocked'.
DRILL_OFFSET_ANGLE_FIXTURE = _board(
    '  (footprint "R:R_0603" (layer "F.Cu") (at 50 50)\n'
    '    (property "Reference" "R1")\n'
    '    (pad "1" thru_hole circle (at 0 0) (size 2.0 2.0) (drill 1.5 (offset 0.5 0.25 45)) (net 1 "GND"))\n'
    '    (pad "2" thru_hole circle (at 0 2) (size 2.0 2.0) (drill 1.5 (offset 0.5 0.25 45 unlocked)) (net 1 "GND"))\n'
    "  )\n"
)


def test_drill_offset_keeps_angle_and_unlocked():
    _assert_same_content(DRILL_OFFSET_ANGLE_FIXTURE, "drill-offset-angle fixture")
    pins = _PARSE_ENGINE.parse_kicad_pcb(DRILL_OFFSET_ANGLE_FIXTURE, normalize=True).netlist.components[0].pins
    assert pins[0].drill.offset.angle == 45, pins[0].drill.offset
    assert pins[0].drill.offset.unlocked is False, pins[0].drill.offset
    assert pins[1].drill.offset.angle == 45, pins[1].drill.offset
    assert pins[1].drill.offset.unlocked is True, pins[1].drill.offset


# P2e: `(track_width 0)` -- the oracle's `get_float(...) or get_float(...)`
# treats the parsed 0.0 as falsy and falls through to None (-> the 0.25
# default downstream); `Some(0.0).or(...)` would keep 0.0 and diverge.
TRACK_WIDTH_ZERO_NETCLASS = (
    "(kicad_pcb (version 20211014) "
    '(net_class "Default" (clearance 0.2) (track_width 0))'
    ")\n"
)


def test_track_width_zero_net_class_parity():
    oracle = _oracle_nets.extract_net_classes(TRACK_WIDTH_ZERO_NETCLASS)
    rust = _PARSE_ENGINE.extract_net_classes(TRACK_WIDTH_ZERO_NETCLASS)
    assert_same(rust, oracle, "track_width 0 net class")
    assert rust["Default"]["trace_width"] is None


# P2a: tokenizer conformance -- the 'kiutils-exact' claim asserted on
# adversarial token strings, not just the corpus. Both arms must tokenize
# identically (and both must raise on the unbalanced bare-quote inputs).
def test_tokenizer_kiutils_exact():
    from kiutils.utils.sexpr import parse_sexp

    cases = [
        "(at 5^0 50)",            # caret: bare token split, `^` skipped
        '(x "R1"())',             # quote not followed by )/ws -> bare, quotes kept
        '(x "a\\"b"())',          # backslash-quote run, bad lookahead -> bare
        '(fp_text ref "a\\"b")',  # escaped quote inside a proper string
        "(at +5 10)",             # `+5`: the int form has no `+` -> bare string
        "(at -5 10)",             # `-5` int
        "(at +5.0 10)",           # `+5.0`: the decimal form accepts `+` -> int 5
        "(at 5.0 10)",            # integral decimal -> int
        "(at 5.5 10)",            # fractional decimal -> float
        "(a\r\nb)",               # CRLF whitespace
        '"unterminated',          # unterminated string -> bare token
        "(net 5)",                # bare numbers stay ints
        "5^0",
        '"a"b" c',
        "(at 5 10 unlocked)",     # unlocked marker is a bare token
        "(a (b ^ c) d)",
        '(x "5")',                # proper string
        '(x "5"y)',               # bad lookahead -> bare with quotes
    ]
    for case in cases:
        oracle = parse_sexp(case)
        rust = _PARSE_ENGINE.tokenize(case)
        assert rust == oracle, f"tokenizer mismatch for {case!r}: rust={rust!r} oracle={oracle!r}"
    # Unbalanced bare-quote inputs raise on both arms (fail-closed parity).
    for case in ['"R1"(', '"a\\"b"(']:
        assert _raised_by(lambda case=case: parse_sexp(case)) is not None, f"oracle accepted {case!r}"
        assert _raised_by(lambda case=case: _PARSE_ENGINE.tokenize(case)) is not None, (
            f"rust accepted unbalanced {case!r}"
        )


# P2d: courtyard Strategy-2 must include unnumbered pads. The oracle iterates
# `for pad in fp.pads:` with no number filter, while its `_extract_pad_sizes`
# skips empty pad numbers -- so the engine's raw `pad_sizes` surface keeps
# skipping them (parity) and the shim's pad-bbox fallback reads the separate
# `pad_bbox_inputs` surface (all pads).
UNNUMBERED_PAD_COURTYARD_FIXTURE = _board(
    '  (footprint "R:R_0603" (layer "F.Cu") (at 50 50)\n'
    '    (property "Reference" "R1")\n'
    '    (pad "" smd rect (at 5 0) (size 4 4) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "GND"))\n'
    "  )\n"
)


def test_courtyard_unnumbered_pad_parity():
    import tempfile

    from temper_placer.io.kicad_metadata import extract_kicad_metadata as shim_extract

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "unnumbered.kicad_pcb"
        p.write_text(UNNUMBERED_PAD_COURTYARD_FIXTURE)
        oracle = _oracle_metadata.extract_kicad_metadata(p)
        rust = shim_extract(p)
    assert_same(rust, oracle, "unnumbered-pad courtyard fixture")
    assert list(rust.courtyards["R1"].points) == [
        (-2.5, -2.5),
        (2.5, -2.5),
        (2.5, 2.5),
        (-2.5, 2.5),
    ]


# P3: malformed positions fail closed -- kiutils' Position.from_sexpr raises
# for a list shorter than 3 items; the engine must not silently default to
# (0,0).
TRUNCATED_AT_FIXTURE = _board(
    '  (footprint "R:R_0603" (layer "F.Cu") (at 5)\n'
    '    (property "Reference" "R1")\n'
    '    (pad "1" smd rect (at 0 0) (size 1.0 1.0) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "GND"))\n'
    "  )\n"
)


def test_truncated_position_raises():
    _assert_both_raise(TRUNCATED_AT_FIXTURE, "truncated position fixture")


# P3: an oval drill missing its width -- kiutils does `object.width =
# exp[3]` unconditionally (IndexError); fail closed the same way.
OVAL_DRILL_NO_WIDTH_FIXTURE = _board(
    '  (footprint "R:R_0603" (layer "F.Cu") (at 50 50)\n'
    '    (property "Reference" "R1")\n'
    '    (pad "1" thru_hole oval (at 0 0) (size 2.0 1.0) (drill oval 1.5) (net 1 "GND"))\n'
    "  )\n"
)


def test_oval_drill_missing_width_raises():
    _assert_both_raise(OVAL_DRILL_NO_WIDTH_FIXTURE, "oval drill no width fixture")

# ---------------------------------------------------------------------------
# R1a -- extract_footprint_positions parity (pure-text regex surface).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("corpus_id,path", CORPUS, ids=[c for c, _ in CORPUS])
def test_extract_footprint_positions_parity(corpus_id, path):
    content = _content(path)
    oracle = _oracle_parser.extract_footprint_positions(content)
    rust = _PARSE_ENGINE.extract_footprint_positions(content)
    assert_same(rust, oracle, f"{corpus_id} extract_footprint_positions")


# ---------------------------------------------------------------------------
# R1a -- extract_net_classes parity (pure-text regex surface).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("corpus_id,path", CORPUS, ids=[c for c, _ in CORPUS])
def test_extract_net_classes_parity(corpus_id, path):
    content = _content(path)
    oracle = _oracle_nets.extract_net_classes(content)
    rust = _PARSE_ENGINE.extract_net_classes(content)
    assert_same(rust, oracle, f"{corpus_id} extract_net_classes")


# ---------------------------------------------------------------------------
# R1a -- kicad_metadata parity (board dims, pad sizes, GEOS courtyards).
# ---------------------------------------------------------------------------

# GEOS note: the courtyard polygons are computed by shapely/GEOS
# (buffer/convex_hull/unary_union) which is NOT reimplementable in Rust
# bit-exactly (measured 169/169 mismatches for a simpler geometry op; see
# MIGRATION_PHASE_GUIDE "Numerical traps"). The Rust engine therefore
# produces the raw courtyard inputs (FpPoly coords, FpCircle center+end,
# FpRect corners, FpLine/FpArc points) and the Python shim runs the SAME
# shapely code on them. This test asserts the FULL KiCadMetadata equality:
# because both arms feed the identical shapely step with identical raw
# inputs, the polygon outputs are equal by construction -- the differential
# proves the raw-input parity that the shared GEOS step consumes.


@pytest.mark.parametrize("corpus_id,path", CORPUS, ids=[c for c, _ in CORPUS])
def test_extract_kicad_metadata_parity(corpus_id, path):
    from temper_placer.io.kicad_metadata import extract_kicad_metadata as shim_extract

    oracle = _oracle_metadata.extract_kicad_metadata(path)
    rust = shim_extract(path)
    assert_same(rust, oracle, f"{corpus_id} extract_kicad_metadata")


# ---------------------------------------------------------------------------
# R1a -- v6 surface: design rules + stackup parity.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("corpus_id,path", CORPUS, ids=[c for c, _ in CORPUS])
def test_extract_design_rules_parity(corpus_id, path):
    from kiutils.board import Board as KiBoard

    from temper_placer.io._parse_nets import _extract_design_rules as shim_design_rules

    content = _content(path)
    ki_board = KiBoard.from_file(str(path))
    warnings: list[str] = []
    oracle = _oracle_nets._extract_design_rules(ki_board, warnings, content)
    # The shim drops the kiutils board (kiutils left the boundary); the text
    # kernel and the assembly are shared logic proven by the oracle parity.
    rust = shim_design_rules(None, [], content)
    assert_same(rust, oracle, f"{corpus_id} extract_design_rules")


@pytest.mark.parametrize("corpus_id,path", CORPUS, ids=[c for c, _ in CORPUS])
def test_extract_stackup_parity(corpus_id, path):
    from kiutils.board import Board as KiBoard

    from temper_placer.io._parse_board import _extract_stackup as shim_stackup

    if corpus_id not in STACKUP:
        pytest.skip("no declared stackup in this corpus file")
    content = _content(path)
    ki_board = KiBoard.from_file(str(path))
    warnings: list[str] = []
    oracle = _oracle_board._extract_stackup(ki_board, warnings)
    rust = shim_stackup(None, [], pcb_content=content)
    assert_same(rust, oracle, f"{corpus_id} extract_stackup")


# ---------------------------------------------------------------------------
# Empty-input semantics (asserted, per the anti-vacuity discipline).
# ---------------------------------------------------------------------------


def test_empty_input_raises():
    with pytest.raises(ValueError):
        _PARSE_ENGINE.parse_kicad_pcb("", normalize=True)


def test_blank_input_raises():
    with pytest.raises(ValueError):
        _PARSE_ENGINE.parse_kicad_pcb("   \n  \n ", normalize=True)


def test_non_sexpr_input_raises():
    with pytest.raises(ValueError):
        _PARSE_ENGINE.parse_kicad_pcb("not an s-expression at all", normalize=True)
