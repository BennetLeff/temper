"""Differential tests: Rust paren-balanced copper-strip kernels vs the
pre-migration Python reference (``router_v6/_strip_copper.py``, Wave-4 PORT).

``_strip_copper.py`` is the last production-path Python in this repo whose
real string-manipulation logic survived the Rust migration wave: it removes
committed ``(segment ...)``/``(via ...))/``(zone ...)`` s-expression blocks
from KiCad board content by tracking parenthesis depth from each block's
opening line. The three pure functions migrated to
``packages/temper-io-types/src/strip_copper.rs`` are pinned bit-exactly
against a VERBATIM copy of the pre-migration implementations (the
``_oracle_*`` block below, ``git show 28de4543d:packages/temper-placer/src/
temper_placer/router_v6/_strip_copper.py``):

- ``_oracle_strip_blocks`` — the paren-depth loop. Every behavioural corner
  the Rust port must reproduce lives here: ``str.split("\\n")`` (CRLF keeps
  ``\\r`` on the line), ``re.match(r"^\\s*\\((<kw>)\\s")`` (the keyword must
  be followed by a whitespace character -- ``(zone)`` and ``(zoney ...)`` do
  NOT match), ``line.count("(") - line.count(")")`` counting *every* paren
  character including those inside quoted strings (naive by design -- both
  sides agree because both are naive), and the defensive ``depth <= 0``
  close (a depth that would go negative closes the block one line early).
- ``_oracle_strip_existing_copper`` — segments + vias + zones.
- ``_oracle_strip_existing_zones`` — zones only.

The ``_oracle_*`` prefix is the only difference from the committed file.

Consumers (``_adapter_convert.py``'s ``_write_routes_to_content``, the
measurement/CLI clean re-route path in ``scripts/route_board.py``, and the
``strip_existing_copper`` import in ``test_topology_copper_audit.py``) see
the same two public functions through the delegation shim, so "which blocks
count as committed copper" is still answered in exactly one place -- it is
just answered in Rust now.

RED state (R1f): this module imports ``temper_io_types.strip_existing_copper``
at collection time, so the whole file fails to collect with ``AttributeError``
before the Rust surface lands.
"""

from __future__ import annotations

import re
from collections import Counter

import pytest
import temper_io_types as _rs
from hypothesis import given, settings, strategies as st

from temper_placer.router_v6._strip_copper import (
    strip_existing_copper as shim_strip_existing_copper,
)
from temper_placer.router_v6._strip_copper import (
    strip_existing_zones as shim_strip_existing_zones,
)

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles (copied from _strip_copper.py AS COMMITTED at
# origin/main 28de4543d before the migration; do not edit -- they are the
# reference).  Only the ``_oracle_`` name prefix differs from the committed
# file.
# ---------------------------------------------------------------------------


def _oracle_strip_blocks(content: str, keywords: tuple[str, ...]) -> tuple[str, int]:
    """Remove every top-level ``(keyword ...)`` block for each *keywords*
    entry, tracking paren depth from each block's opening line.

    A block "opens" on the first line (after leading whitespace) that
    matches ``(keyword ``. From there, every ``(``/``)`` on subsequent
    lines (including the opening line itself) adjusts a running depth
    counter; the block ends on the line where that counter returns to
    zero (or below, defensively). This is correct whether the whole block
    is on one line (``(segment ...)``, ``(via ...)``) or spans many
    (``(zone ...)``).

    Returns ``(cleaned_content, blocks_removed)``.
    """
    pattern = re.compile(r"^\s*\((" + "|".join(re.escape(k) for k in keywords) + r")\s")
    lines = content.split("\n")
    out: list[str] = []
    removed = 0
    depth = 0
    in_block = False
    for line in lines:
        if not in_block and pattern.match(line):
            in_block = True
            depth = 0
            removed += 1
        if in_block:
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                in_block = False
            continue
        out.append(line)
    return "\n".join(out), removed


def _oracle_strip_existing_copper(content: str) -> tuple[str, int]:
    """Remove every committed ``(segment ...)``, ``(via ...)``, and
    ``(zone ...)`` top-level s-expression block from *content*.

    Routing an already-routed, already-poured board is not the same
    experiment as routing a bare one. This is the routing-*input* half of
    R7: a board handed to ``route_pcb`` through this function no longer
    carries its committed zones as data the router (or anything reading
    its output) could mistake for authoritative.

    Returns ``(cleaned_content, blocks_removed)`` where ``blocks_removed``
    counts segments + vias + zones together.
    """
    return _oracle_strip_blocks(content, ("segment", "via", "zone"))


def _oracle_strip_existing_zones(content: str) -> tuple[str, int]:
    """Remove only ``(zone ...)`` blocks from *content*, leaving any
    ``(segment ...)``/``(via ...)`` entries untouched.

    This is the routing-*output* half of R7: called immediately before a
    regenerated set of pours is written, so the written board's zones are
    exactly this run's regenerated set -- never the stale carryover from
    whatever the input board happened to have -- regardless of whether the
    caller already stripped zones from the routing input.

    Returns ``(cleaned_content, zones_removed)``.
    """
    return _oracle_strip_blocks(content, ("zone",))


# Accessing the Rust surface at import time is what makes this file fail to
# collect (RED) until strip_copper.rs lands.
_RS_COPPER = _rs.strip_existing_copper
_RS_ZONES = _rs.strip_existing_zones


def _assert_parity(got, expected, label: str) -> None:
    """Bit-exact string + exact count comparison."""
    assert got[1] == expected[1], f"{label}: removed={got[1]!r} oracle={expected[1]!r}"
    assert got[0] == expected[0], (
        f"{label}: content differs\n--- rust ---\n{got[0]!r}\n--- oracle ---\n{expected[0]!r}"
    )


def test_oracle_is_verbatim_semantics() -> None:
    """Pins the oracle's own behaviour on hand cases so a broken verbatim
    copy cannot silently agree with a broken port."""
    board = _sample_board(_SAMPLE_ZONE, _SAMPLE_SEGMENT, _SAMPLE_VIA)
    cleaned, n = _oracle_strip_existing_copper(board)
    assert n == 3
    assert "(zone " not in cleaned
    assert "(segment " not in cleaned
    assert "(via " not in cleaned
    assert cleaned.count("(") == cleaned.count(")")
    # keyword must be followed by whitespace: a bare (zone) is not a block
    cleaned2, n2 = _oracle_strip_existing_zones("(kicad_pcb\n  (zone)\n  (zonex (net 1))\n)")
    assert n2 == 0
    assert cleaned2 == "(kicad_pcb\n  (zone)\n  (zonex (net 1))\n)"


# ---------------------------------------------------------------------------
# Realistic KiCad content fixtures (verbatim s-expression snippets)
# ---------------------------------------------------------------------------

_SAMPLE_ZONE = """  (zone (net 4) (net_name "+3V3") (layer "F.Cu") (hatch full 0.5)
    (priority 50)
    (connect_pads yes (clearance 6))
    (min_thickness 0.25)
    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon
      (pts
        (xy 122.5485 147.3413)
        (xy 122.5643 147.3601)
        (xy 122.601 147.3926)
      )
    )
  )"""

_SAMPLE_SEGMENT = (
    '  (segment (start 10.0 10.0) (end 20.0 10.0) (width 0.2) '
    '(layer "F.Cu") (net 1) (tstamp "aaaa"))'
)
_SAMPLE_VIA = (
    '  (via (at 15.0 15.0) (size 0.8) (drill 0.4) '
    '(layers "F.Cu" "B.Cu") (net 1) (tstamp "bbbb"))'
)

# A structurally real, interleaved board: two multi-line zones (one per
# layer), two segments, a via, gr_* decoration and a footprint.
_BOARD_SNIPPET = """(kicad_pcb (version 20211014) (generator kiutils)
  (general (thickness 1.6))
  (net 0 "")
  (net 1 "GND")
  (net 2 "+3V3")
  (net 3 "SW_NODE")
  (gr_rect (start 0 0) (end 100 80) (layer "Edge.Cuts") (width 0.05))
  (gr_line (start 0 0) (end 100 0) (layer "Edge.Cuts") (width 0.05))
  (segment (start 10.0 10.0) (end 20.0 10.0) (width 0.2) (layer "F.Cu") (net 1) (tstamp "aaaa"))
  (via (at 15.0 15.0) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net 1) (tstamp "bbbb"))
  (zone (net 2) (net_name "+3V3") (layer "F.Cu") (hatch full 0.5)
    (priority 50)
    (connect_pads yes (clearance 6))
    (min_thickness 0.25)
    (fill yes (thermal_gap 0.5))
    (polygon
      (pts
        (xy 1.0 1.0)
        (xy 99.0 1.0)
        (xy 99.0 79.0)
        (xy 1.0 79.0)
      )
    )
  )
  (segment (start 30.0 30.0) (end 40.0 30.0) (width 0.2) (layer "B.Cu") (net 3) (tstamp "cccc"))
  (zone (net 1) (net_name "GND") (layer "B.Cu") (hatch full 0.5)
    (priority 40)
    (min_thickness 0.25)
    (fill yes)
    (polygon
      (pts
        (xy 2.0 2.0)
        (xy 98.0 2.0)
        (xy 98.0 78.0)
      )
    )
  )
  (footprint "R_SMD:R_0603" (at 50 40) (layer "F.Cu")
    (fp_text reference "R1" (at 0 0) (layer "F.SilkS"))
  )
)
"""

# A ``(segment ...)`` nested INSIDE a zone block is consumed by the zone's
# paren-depth span -- it must not be counted/stripped independently.
_NESTED_SEGMENT_IN_ZONE = """(kicad_pcb (version 20211014)
  (zone (net 1) (net_name "GND") (layer "F.Cu") (hatch full 0.5)
    (priority 50)
    (segment (start 1 1) (end 2 2) (width 0.2) (layer "F.Cu") (net 1) (tstamp "x"))
    (polygon (pts (xy 0 0) (xy 10 0) (xy 10 10)))
  )
  (segment (start 5 5) (end 6 6) (width 0.2) (layer "F.Cu") (net 1) (tstamp "y"))
)"""

# A zone whose opening line carries unbalanced parens: the block swallows
# following lines until the running depth returns to zero -- the defensive
# ``depth <= 0`` close fires mid-content.
_UNBALANCED_DEPTH = (
    '(kicad_pcb\n'
    '  (zone (net 1 (net_name "GND"\n'
    '    (polygon (pts (xy 0 0)))\n'
    '  )))\n'
    '  (net 2 "X")\n'
    '  (segment (start 1 1) (end 2 2) (width 0.2) (layer "F.Cu") (net 1) (tstamp "z"))\n'
    ')\n'
)

# Parens inside quoted strings are counted by the naive depth tracker in
# BOTH implementations.  Balanced-in-quotes is harmless; a *net-negative*
# quoted string (``"(GND("``) shifts the running depth exactly the same way
# on both sides -- parity, not correctness, is what this pins.
_QUOTED_PARENS_BALANCED = """(kicad_pcb (version 20211014)
  (zone (net 1) (net_name "GND(x)") (layer "F.Cu") (hatch full 0.5)
    (priority 50)
    (polygon
      (pts
        (xy 0 0)
        (xy 10 0)
        (xy 10 10)
        (net_name "(inside)")
      )
    )
  )
)"""

_QUOTED_PARENS_UNBALANCED = '(kicad_pcb\n  (zone (net 1) (net_name "GND(") (layer "F.Cu")\n  )\n  (net 2 "X")\n)\n'

# CRLF line endings: ``str.split("\\n")`` keeps the ``\\r`` on each line;
# the leading-whitespace class and the paren counts both still work, and
# surviving lines keep their ``\\r`` byte-for-byte.
_CRLF = (
    "(kicad_pcb\r\n"
    '  (zone (net 1) (net_name "GND") (layer "F.Cu")\r\n'
    "    (polygon (pts (xy 0 0) (xy 10 0)))\r\n"
    "  )\r\n"
    '  (segment (start 1 1) (end 2 2) (width 0.2) (layer "F.Cu") (net 1) (tstamp "z"))\r\n'
    ")\r\n"
)

# Keyword must be followed by a whitespace character: ``(zone)``, ``(zonex``
# and ``(via)``/``(segment)`` (no space, no body) are NOT top-level blocks.
_KEYWORD_NO_TRAILING_SPACE = """(kicad_pcb (version 20211014)
  (zone)
  (zonex (net 1))
  (zone 1 (net 1))
  (via)
  (segment)
)"""

_TAB_INDENTED = "(kicad_pcb\n\t(zone (net 1) (net_name \"GND\")\n\t\t(polygon (pts (xy 0 0)))\n\t)\n)\n"


def _sample_board(*blocks: str) -> str:
    body = "\n".join(blocks)
    return (
        '(kicad_pcb (version 20211014) (generator kiutils)\n'
        '  (general (thickness 1.6))\n'
        '  (net 1 "GND")\n'
        f"{body}\n"
        ")\n"
    )


# ---------------------------------------------------------------------------
# Differential: rust vs verbatim oracle, both publics, over every fixture
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("content", [
    _BOARD_SNIPPET,
    _NESTED_SEGMENT_IN_ZONE,
    _UNBALANCED_DEPTH,
    _QUOTED_PARENS_BALANCED,
    _QUOTED_PARENS_UNBALANCED,
    _CRLF,
    _KEYWORD_NO_TRAILING_SPACE,
    _TAB_INDENTED,
    _sample_board(_SAMPLE_ZONE, _SAMPLE_SEGMENT, _SAMPLE_VIA),
    _sample_board(_SAMPLE_ZONE),
    _sample_board(_SAMPLE_SEGMENT, _SAMPLE_VIA),
    "()",
    "  (zone)  ",
    "(kicad_pcb\n)\n",
    "(kicad_pcb\n)",
    "",
    "no parens at all\njust text\n",
])
class TestRustVsOracleFixtures:
    def test_strip_existing_copper_parity(self, content: str) -> None:
        _assert_parity(_RS_COPPER(content), _oracle_strip_existing_copper(content), "copper")

    def test_strip_existing_zones_parity(self, content: str) -> None:
        _assert_parity(_RS_ZONES(content), _oracle_strip_existing_zones(content), "zones")


def test_real_production_board_parity() -> None:
    """The strongest fixture is the real committed board: both implementations
    must agree byte-for-byte on pcb/temper.kicad_pcb (2290 segments + 48 vias
    + 96 zones)."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[4]
    content = (repo_root / "pcb" / "temper.kicad_pcb").read_text(encoding="utf-8")

    _assert_parity(_RS_COPPER(content), _oracle_strip_existing_copper(content), "real board copper")
    _assert_parity(_RS_ZONES(content), _oracle_strip_existing_zones(content), "real board zones")


def test_shim_delegates_to_rust() -> None:
    """The delegation shim must be byte-identical to the Rust surface (the
    consumers' contract), not just to the oracle."""
    for content in (_BOARD_SNIPPET, _CRLF, _sample_board(_SAMPLE_ZONE, _SAMPLE_SEGMENT)):
        _assert_parity(shim_strip_existing_copper(content), _RS_COPPER(content), "shim copper")
        _assert_parity(shim_strip_existing_zones(content), _RS_ZONES(content), "shim zones")


# ---------------------------------------------------------------------------
# Differential: rust vs oracle over hypothesis-generated boards (random sweep)
# ---------------------------------------------------------------------------

_NET_NAMES = ["GND", "+3V3", "SW_NODE", "12V", "AC_L"]
_LAYERS = ["F.Cu", "B.Cu", "In1.Cu"]
_PLAIN_LINES = st.sampled_from([
    "(kicad_pcb (version 20211014) (generator kiutils)",
    "  (general (thickness 1.6))",
    '  (net 1 "GND")',
    '  (gr_line (start 0 0) (end 10 0) (layer "Edge.Cuts") (width 0.05))',
    '  (footprint "R_SMD:R_0603" (at 50 40) (layer "F.Cu")',
    '    (fp_text reference "R1" (at 0 0) (layer "F.SilkS"))',
    "  )",
    '  (gr_text "board" (at 5 5) (layer "F.SilkS"))',
    "",
])


@st.composite
def _block(draw):
    """A well-formed top-level ``(segment|via|zone)`` block: single-line for
    segment/via, multi-line with a nested polygon for zone."""
    kw = draw(st.sampled_from(["segment", "via", "zone"]))
    net = draw(st.integers(0, 20))
    net_name = draw(st.sampled_from(_NET_NAMES))
    layer = draw(st.sampled_from(_LAYERS))
    if kw == "zone":
        n_points = draw(st.integers(1, 4))
        coords = draw(
            st.lists(
                st.tuples(st.integers(0, 100), st.integers(0, 100)),
                min_size=n_points,
                max_size=n_points,
            )
        )
        lines = [
            f'  (zone (net {net}) (net_name "{net_name}") (layer "{layer}") (hatch full 0.5)',
            f"    (priority {draw(st.integers(1, 99))})",
            "    (connect_pads yes (clearance 6))",
            "    (min_thickness 0.25)",
            "    (fill yes (thermal_gap 0.5))",
            "    (polygon",
            "      (pts",
        ]
        for x, y in coords:
            lines.append(f"        (xy {x} {y})")
        lines.append("      )")
        lines.append("    )")
        lines.append("  )")
        return "\n".join(lines)
    tstamp = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=4, max_size=8))
    if kw == "segment":
        return (
            f'  (segment (start {draw(st.integers(0, 100))} {draw(st.integers(0, 100))}) '
            f'(end {draw(st.integers(0, 100))} {draw(st.integers(0, 100))}) (width 0.2) '
            f'(layer "{layer}") (net {net}) (tstamp "{tstamp}"))'
        )
    return (
        f'  (via (at {draw(st.integers(0, 100))} {draw(st.integers(0, 100))}) (size 0.8) '
        f'(drill 0.4) (layers "{layer}" "B.Cu") (net {net}) (tstamp "{tstamp}"))'
    )


@st.composite
def _content(draw):
    """A board-like document: a header line, 0..6 top-level items each either
    a plain balanced line or a keyword block, and a footer line."""
    items = draw(
        st.lists(
            st.one_of(_PLAIN_LINES, _block()),
            min_size=0,
            max_size=6,
        )
    )
    return "\n".join(["(kicad_pcb (version 20211014)"] + items + [")", ""])


def _count_blocks(content: str, keywords: tuple[str, ...]) -> int:
    """Number of top-level keyword blocks by matching their opening lines --
    a re-derivation of the block's own opening rule, used only to prove the
    property fixtures are non-vacuous."""
    pattern = re.compile(r"^\s*\((" + "|".join(re.escape(k) for k in keywords) + r")\s")
    return sum(1 for line in content.split("\n") if pattern.match(line))


@settings(max_examples=40, deadline=None)
@given(c=st.data())
def test_random_board_differential(c) -> None:
    content = c.draw(_content())
    _assert_parity(_RS_COPPER(content), _oracle_strip_existing_copper(content), "random copper")
    _assert_parity(_RS_ZONES(content), _oracle_strip_existing_zones(content), "random zones")


# ---------------------------------------------------------------------------
# PBT properties (R1c, >= 5, each with a vacuity guard)
# ---------------------------------------------------------------------------


@settings(max_examples=40, deadline=None)
@given(c=st.data())
def test_p1_removed_count_is_exact(c) -> None:
    content = c.draw(_content())
    n_blocks = _count_blocks(content, ("segment", "via", "zone"))
    n_zones = _count_blocks(content, ("zone",))
    if n_blocks == 0:
        # vacuity guard: this property only speaks when blocks are present
        assert _RS_COPPER(content)[0] == content
        assert _RS_COPPER(content)[1] == 0
        return
    _, removed_copper = _RS_COPPER(content)
    _, removed_zones = _RS_ZONES(content)
    assert removed_copper == n_blocks
    assert removed_zones == n_zones


@settings(max_examples=40, deadline=None)
@given(c=st.data())
def test_p2_paren_balance_preserved(c) -> None:
    content = c.draw(_content())
    assert content.count("(") == content.count(")"), "generator produced unbalanced content"
    cleaned, removed = _RS_COPPER(content)
    assert removed >= 1, "vacuity: property needs at least one block to strip"
    assert cleaned.count("(") == cleaned.count(")")


@settings(max_examples=40, deadline=None)
@given(c=st.data())
def test_p3_no_target_keyword_block_survives(c) -> None:
    content = c.draw(_content())
    assert _count_blocks(content, ("segment", "via", "zone")) >= 1
    cleaned, removed = _RS_COPPER(content)
    assert removed >= 1
    assert "(segment " not in cleaned
    assert "(via " not in cleaned
    assert "(zone " not in cleaned


@settings(max_examples=40, deadline=None)
@given(c=st.data())
def test_p4_strip_is_idempotent(c) -> None:
    content = c.draw(_content())
    cleaned_once, removed_first = _RS_COPPER(content)
    assert removed_first >= 1, "vacuity: property needs a block to strip"
    cleaned_twice, removed_second = _RS_COPPER(cleaned_once)
    assert cleaned_twice == cleaned_once
    assert removed_second == 0


@settings(max_examples=40, deadline=None)
@given(c=st.data())
def test_p5_zones_strip_leaves_segments_and_vias_untouched(c) -> None:
    content = c.draw(_content())
    n_zones = _count_blocks(content, ("zone",))
    n_copper_others = _count_blocks(content, ("segment", "via"))
    assert n_zones >= 1 and n_copper_others >= 1, (
        "vacuity: property needs both a zone and a segment/via to say anything"
    )
    cleaned, removed = _RS_ZONES(content)
    assert removed == n_zones
    segment_via_lines = [
        line for line in content.split("\n") if _count_blocks(line, ("segment", "via")) > 0
    ]
    assert segment_via_lines
    for line in segment_via_lines:
        assert line in cleaned, f"zone strip lost a segment/via line: {line!r}"


# ---------------------------------------------------------------------------
# Metamorphic relations (R1d, >= 3)
# ---------------------------------------------------------------------------


@settings(max_examples=40, deadline=None)
@given(c=st.data())
def test_mr1_zones_strip_is_idempotent(c) -> None:
    """Second application removes nothing and changes nothing."""
    content = c.draw(_content())
    assert _count_blocks(content, ("zone",)) >= 1
    once, removed_first = _RS_ZONES(content)
    assert removed_first >= 1
    twice, removed_second = _RS_ZONES(once)
    assert twice == once
    assert removed_second == 0


@settings(max_examples=40, deadline=None)
@given(c=st.data())
def test_mr2_strip_is_permutation_invariant(c) -> None:
    """Reordering non-overlapping top-level items changes neither the removal
    count nor the multiset of surviving lines."""
    content = c.draw(_content())
    assert _count_blocks(content, ("segment", "via", "zone")) >= 1
    items = content.split("\n")[1:-2]
    assert len(items) >= 2
    permuted = "\n".join(["(kicad_pcb (version 20211014)"] + items[::-1] + [")", ""])
    assert permuted != content, "vacuity: permutation must differ from the input"
    a_clean, a_removed = _RS_COPPER(content)
    b_clean, b_removed = _RS_COPPER(permuted)
    assert a_removed == b_removed
    assert Counter(a_clean.split("\n")) == Counter(b_clean.split("\n"))


@settings(max_examples=40, deadline=None)
@given(c=st.data())
def test_mr3_zones_then_copper_decomposes(c) -> None:
    """Copper stripping = stripping zones first, then stripping the
    remaining segments/vias.  Concretely: copper(X) is unchanged by an
    extra pre-strip of zones, and an extra post-strip of zones on copper(X)
    is a no-op -- zone removal is subsumed by copper removal."""
    content = c.draw(_content())
    assert _count_blocks(content, ("zone",)) >= 1
    assert _count_blocks(content, ("segment", "via")) >= 1
    copper = _RS_COPPER(content)
    copper_after_zones = _RS_COPPER(_RS_ZONES(content)[0])
    assert copper[0] == copper_after_zones[0]
    assert copper[1] == copper_after_zones[1]
    zones_after_copper = _RS_ZONES(copper[0])
    assert zones_after_copper[0] == copper[0]
    assert zones_after_copper[1] == 0
