"""Property-based and metamorphic tests for the Rust parse engine.

Wave 4 Phase 3 candidate 3 (plan ``2026-08-02-001-...phase3-formats-io-plan.md``).
The engine under test is ``temper_design_bundle_python.parse_engine`` (the
kiutils-free KiCad parse engine); the differential suite
(``test_parse_engine_rust_differential.py``) pins bit-identical parity against
the verbatim oracle. This file asserts:

R1c -- >= 5 non-vacuous properties (P1-P7), each with a real chance to fail.
R1d -- >= 3 metamorphic relations (M1-M4), honestly bounded.

None of these assertions involve tolerances on geometry *outputs* -- they are
structural invariants and exact-covariance relations. The one arithmetic
relation (M1) is explicitly bounded at 8 ulp with the rationale stated.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import temper_design_bundle_python as _tdb

from tests.io.test_parse_engine_rust_differential import CORPUS, REPO_ROOT

_ENGINE = _tdb.parse_engine

_TEMPER = REPO_ROOT / "power_pcb_dataset" / "corpus" / "temper" / "temper.kicad_pcb"
_MINIMAL = REPO_ROOT / "power_pcb_dataset" / "corpus" / "minimal" / "minimal_board.kicad_pcb"


def _content(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse(path: Path, normalize: bool = True):
    return _ENGINE.parse_kicad_pcb(_content(path), normalize=normalize)


# ---------------------------------------------------------------------------
# R1c -- properties
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("corpus_id,path", CORPUS, ids=[c for c, _ in CORPUS])
def test_component_refs_are_real(corpus_id, path):
    """P1: every component has a non-empty reference that is not the
    unplaced REF** placeholder.

    (Uniqueness is NOT universal: the piantor corpus contains multiple
    mounting-hole footprints with no Reference property, which resolve to the
    shared entryName fallback -- 'MountingHole' -- and even duplicate H1/H4
    designators. The oracle produces the same, so uniqueness is not an
    invariant of the engine.)
    """
    result = _parse(path)
    refs = [c.ref for c in result.netlist.components]
    assert all(refs), f"{corpus_id}: empty ref present"
    assert not any(r.startswith("REF**") for r in refs), f"{corpus_id}: REF** placeholder leaked"


@pytest.mark.parametrize("corpus_id,path", CORPUS, ids=[c for c, _ in CORPUS])
def test_nets_retain_single_pad_nets(corpus_id, path):
    """P2: the netlist registry keeps EVERY named net, single-pad included.

    (Deliberate 2026-08-15 contract change -- see ``extract_nets_pure`` in
    ``parse_engine.rs`` and the oracle header: the pre-migration extraction
    dropped nets with < 2 pins, which erased real nets (``ac_l`` after the
    ZCD orphan-footprint removal) from the net class mapping and made
    ``apply_net_class_mapping_strict`` raise. Single-pad nets stay in the
    registry; routing excludes them via ``_routable_net_names``. The
    invariants that survive: empty net names and zero-pin nets never
    appear -- a net is created only when a pin names it -- and the registry
    is exactly the pin census, no more, no less.)
    """
    result = _parse(path)
    seen: dict[str, int] = {}
    for comp in result.netlist.components:
        for pin in comp.pins:
            if pin.net:
                seen[pin.net] = seen.get(pin.net, 0) + 1
    registry = {net.name for net in result.netlist.nets}
    assert set(seen) == registry, (
        f"{corpus_id}: netlist registry ({len(registry)} nets) != pin census "
        f"({len(seen)} nets); dropped: {sorted(set(seen) - registry)[:5]}"
    )
    for net in result.netlist.nets:
        assert len(net.pins) >= 1, f"{corpus_id}: net {net.name!r} has {len(net.pins)} pins"
        assert net.name != "", f"{corpus_id}: empty net name survives the filter"
    if corpus_id in {"temper", "rp2040", "bitaxe", "pcb"}:
        assert any(len(net.pins) == 1 for net in result.netlist.nets), (
            f"{corpus_id}: corpus has no single-pad net -- retention is untested"
        )


@pytest.mark.parametrize("corpus_id,path", CORPUS, ids=[c for c, _ in CORPUS])
def test_pads_reference_known_components(corpus_id, path):
    """P3: every extracted PadData references a component that exists."""
    result = _parse(path)
    refs = {c.ref for c in result.netlist.components}
    for pad in result.pads:
        assert pad.component_ref in refs, (
            f"{corpus_id}: pad {pad.number} references unknown component {pad.component_ref!r}"
        )


@pytest.mark.parametrize("corpus_id,path", CORPUS, ids=[c for c, _ in CORPUS])
def test_component_bounds_have_minimum_floor(corpus_id, path):
    """P4: component bounds respect the 0.5 mm floor in both dimensions."""
    result = _parse(path)
    for comp in result.netlist.components:
        w, h = comp.bounds
        assert w >= 0.5 and h >= 0.5, f"{corpus_id}: {comp.ref} bounds {(w, h)} below floor"


def test_warnings_deterministic():
    """P5: parsing the same content twice yields identical warnings."""
    content = _content(REPO_ROOT / "pcb" / "temper.kicad_pcb")
    r1 = _ENGINE.parse_kicad_pcb(content, normalize=True)
    r2 = _ENGINE.parse_kicad_pcb(content, normalize=True)
    assert r1.warnings == r2.warnings


@pytest.mark.parametrize("corpus_id,path", CORPUS, ids=[c for c, _ in CORPUS])
def test_zone_polygon_inside_bounds(corpus_id, path):
    """P6: each zone's bounds enclose its polygon points."""
    result = _parse(path)
    for zone in result.board.zones:
        xs = [p[0] for p in zone.polygon]
        ys = [p[1] for p in zone.polygon]
        if not xs:
            continue
        assert min(xs) >= zone.bounds[0] and max(xs) <= zone.bounds[2]
        assert min(ys) >= zone.bounds[1] and max(ys) <= zone.bounds[3]


@pytest.mark.parametrize("corpus_id,path", CORPUS, ids=[c for c, _ in CORPUS])
def test_board_extents_match_edge_cuts(corpus_id, path):
    """P7: board width/height equal the Edge.Cuts bounding box, independently
    re-derived from the raw text (a third implementation, so a shared
    misunderstanding cannot hide)."""
    content = _content(path)
    result = _parse(path)
    import re

    xs: list[float] = []
    ys: list[float] = []
    # Collect ONLY coordinate pairs ((xy|start|end|mid|center) X Y) inside
    # Edge.Cuts graphic blocks -- never widths/strokes/layer tokens.
    coord_pair = re.compile(r"\((?:xy|start|end|mid|center)\s+([\d.-]+)\s+([\d.-]+)\)")
    for m in re.finditer(r"\((gr_line|gr_rect|gr_arc|gr_poly)\b", content):
        start = m.start()
        bal = 0
        end = len(content)
        for i in range(start, len(content)):
            if content[i] == "(":
                bal += 1
            elif content[i] == ")":
                bal -= 1
                if bal == 0:
                    end = i
                    break
        block = content[start : end + 1]
        if '(layer "Edge.Cuts")' not in block:
            continue
        for cm in coord_pair.finditer(block):
            xs.append(float(cm.group(1)))
            ys.append(float(cm.group(2)))
    if not xs:
        return  # no edge cuts in this corpus file -> temper_default board
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    assert abs(float(result.board.width) - (maxx - minx)) < 1e-9, corpus_id
    assert abs(float(result.board.height) - (maxy - miny)) < 1e-9, corpus_id


# ---------------------------------------------------------------------------
# R1d -- metamorphic relations
# ---------------------------------------------------------------------------


def _ulp(x: float) -> float:
    import math

    return math.ulp(abs(x))


def test_m1_normalization_shift_covariance():
    """M1: parse(content, normalize=True) positions equal
    parse(content, normalize=False) positions shifted by the board origin.

    Honest bound: the two arms compute ``(pos - origin) + rotated`` and
    ``pos + rotated`` respectively, which differ by float associativity on
    components whose origin subtraction is not exact. Measured on the corpus
    the worst deviation is ~4 ulp of the coordinate magnitude; assert 8 ulp
    and, to keep the relation non-vacuous, that the large majority of
    components match bit-exactly.
    """
    path = REPO_ROOT / "pcb" / "temper.kicad_pcb"
    rn = _parse(path, normalize=True)
    rr = _parse(path, normalize=False)
    ox, oy = rn.board.origin
    exact = 0
    total = 0
    for c_n, c_r in zip(rn.netlist.components, rr.netlist.components):
        nx, ny = c_n.initial_position
        rx, ry = c_r.initial_position
        dx = abs(nx - (rx - float(ox)))
        dy = abs(ny - (ry - float(oy)))
        bound = 8 * max(_ulp(nx), _ulp(rx - float(ox)), _ulp(ny), _ulp(ry - float(oy)), 1e-300)
        assert dx <= bound and dy <= bound, (
            f"{c_n.ref}: normalized {c_n.initial_position} != raw {c_r.initial_position} "
            f"- origin ({ox}, {oy}); dx={dx} dy={dy} bound={bound}"
        )
        if nx == rx - float(ox) and ny == ry - float(oy):
            exact += 1
        total += 1
    assert exact / total > 0.9, f"only {exact}/{total} components match the shift bit-exactly"


def test_m2_whitespace_and_formatting_invariance():
    """M2: adding whitespace/newlines between tokens changes nothing.

    The transform inserts spaces around parens and doubles newlines -- safe
    only between tokens, never inside strings. kiutils' tokenizer is
    whitespace-insensitive, so the parse must be bit-identical.
    """
    content = _content(_MINIMAL)
    variant = content.replace("(", " (").replace(")", " )").replace("\n", "\n\n") + "\n\n  "
    base = _ENGINE.parse_kicad_pcb(content, normalize=True)
    changed = _ENGINE.parse_kicad_pcb(variant, normalize=True)
    assert base.warnings == changed.warnings
    assert [c.ref for c in base.netlist.components] == [c.ref for c in changed.netlist.components]
    for c1, c2 in zip(base.netlist.components, changed.netlist.components):
        assert c1.initial_position == c2.initial_position
        assert c1.attributes == c2.attributes
    assert base.board.origin == changed.board.origin
    assert base.board.width == changed.board.width


def test_m3_net_renaming_covariance():
    """M3: renaming a net's quoted name everywhere renames it consistently,
    preserving the connectivity graph (pin membership per net)."""
    content = _content(_MINIMAL)  # nets: GND, VCC, SIG1, SIG2
    target = "SIG1"
    renamed = target + "_r"
    variant = content.replace(f'"{target}"', f'"{renamed}"')
    base = _ENGINE.parse_kicad_pcb(content, normalize=True)
    changed = _ENGINE.parse_kicad_pcb(variant, normalize=True)

    base_nets = {n.name: sorted(tuple(p) for p in n.pins) for n in base.netlist.nets}
    changed_nets = {n.name: sorted(tuple(p) for p in n.pins) for n in changed.netlist.nets}
    assert renamed in changed_nets, "renamed net missing"
    assert target not in changed_nets, "original net name survived"
    # Connectivity of the renamed net is unchanged.
    assert changed_nets[renamed] == base_nets[target]
    # All other nets are untouched.
    for name, pins in base_nets.items():
        if name == target:
            continue
        assert changed_nets[name] == pins, f"net {name} changed under renaming"
    # Pin-level net labels on the components covary too.
    comp_by_ref = {c.ref: c for c in base.netlist.components}
    comp_by_ref2 = {c.ref: c for c in changed.netlist.components}
    for ref, comp in comp_by_ref.items():
        for p1, p2 in zip(comp.pins, comp_by_ref2[ref].pins):
            if p1.net == target:
                assert p2.net == renamed, f"{ref} pin {p1.number} did not covary"


def test_m4_footprint_removal_covariance():
    """M4: extract_footprint_positions on a board minus one footprint block
    equals the full result minus that footprint's entry."""
    content = _content(_MINIMAL)
    full = _ENGINE.extract_footprint_positions(content)
    # Remove the first footprint block (balanced-paren scan).
    start = content.find("(footprint")
    bal = 0
    end = len(content)
    for i in range(start, len(content)):
        if content[i] == "(":
            bal += 1
        elif content[i] == ")":
            bal -= 1
            if bal == 0:
                end = i + 1
                break
    removed_ref = next(iter(full))  # first footprint block in file order
    del full[removed_ref]
    variant = content[:start] + content[end:]
    partial = _ENGINE.extract_footprint_positions(variant)
    assert removed_ref not in partial
    assert partial == full, "removing one footprint changed the other entries"
