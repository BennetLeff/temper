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
