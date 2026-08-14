#!/usr/bin/env python3
"""Net accounting gate: catch a net whose pin-identity view silently
collapses a real, multi-pad net into a "trivial, nothing to connect" one.

**Motivation.** A task investigating `discharge.k_dis1-no`/
`discharge.k_dis2-no` "vanishing" under `--net-batching` found they do not
vanish -- Stage 4's A* actually runs for them and prints "routed
successfully" -- but they end up with zero connecting copper in
`pad_connectivity_audit`'s ground-truth check anyway. The root cause:
`Net.pins` for both nets is `[('K2', '3'), ('K2', '3')]` /
`[('K3', '3'), ('K3', '3')]` -- two IDENTICAL `(component_ref, pin_name)`
tuples. K2/K3 (the discharge relays,
`temper:Relay_SPDT_Schrack-RT314012`) fabricate contact pad "3" (and "1",
"4") as TWO physical solder holes, 7.5mm apart, sharing one pad number for
16A current sharing -- a real, documented pattern, not a parsing artifact.
Two independent call sites in `temper_placer.router_v6` used
`(component_ref, pin_name)` tuple identity as a proxy for "physical pad
identity" and both got it wrong for this shape:
`_pipeline_grid._net_pad_positions` (`Component.get_pin` always returns
its FIRST name/number match, so both occurrences of the duplicate tuple
resolved to the SAME coordinate) and
`topology_copper_audit.is_self_referential_net` (`len(set(pins)) == 1`
was trusted as proof of "same physical pad" for `len(pins) >= 2`). Both
are fixed (see their own docstrings), but the underlying assumption --
tuple identity implies physical-pad identity -- has no general proof, and
nothing stopped a future net or a future call site from making the same
mistake silently. This gate is the standing invariant: it flags any net
where the `(component_ref, pad_number)` identity view of its pins says
"at most 1 distinct pin" while the board's REAL pad count -- the number of
raw `(pad ...)` occurrences for that net, i.e. how many physical copper
pads actually exist, regardless of whether their names collide -- is
more than 1.

**Self-contained by design** (same posture as
`check_copper_net_consistency.py`): reads `pcb/temper.kicad_pcb` directly
with its own paren-balanced regex extraction, deliberately NOT importing
`temper_placer.router_v6` (which pulls in this repo's full pyo3/maturin
extension chain -- unnecessary weight and a shared-bug risk for a check
whose whole point is independence from that code). Both sides of the
comparison -- the pin-identity view and the "real" pad count -- come from
the exact same raw `(pad "N" ... (net M "name"))` occurrences this gate
parses itself: a pin-identity tuple is `(component_ref, pad_number)`, one
per occurrence; the real pad count is simply how many occurrences there
are for that net. This mirrors exactly what `Net.pins`
(`extract_nets_pure` in `parse_engine.rs`) and
`pad_connectivity_audit._pads_by_net` independently derive from the same
board file.

**What this deliberately does NOT check**: whether every net is actually
routed with real copper. Most of this board's nets are legitimately
unrouted today (2-layer channel-capacity congestion, documented
elsewhere) -- an unrouted-but-declared net is normal, not a defect this
gate exists to catch (same posture as `check_copper_net_consistency.py`'s
own "net-set asymmetry (deliberately NOT enforced)" note). This gate is
narrower and cheaper: it never needs to run the router at all, only parse
the board once.

Fail-closed contract, matching this repo's other board-reading gates:
never exits 0 unless it positively confirms it ran a real check on real,
non-empty data. Exits non-zero for:
  - the board file is missing
  - the board has zero nets with pads

Exit codes:
  0 - PASSED: 0 unexpected mismatches (allowlisted exceptions aside)
      across a real, non-empty check
  3 - VIOLATION: at least one net's pin-identity view disagrees with its
      real pad count, and is not a pre-approved, reviewed exception
  5 - GATE ERROR: the gate could not run a trustworthy check at all

Usage:
  uv run python scripts/check_net_pin_identity_pad_correspondence.py
  uv run python scripts/check_net_pin_identity_pad_correspondence.py --board PATH
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path
from _lib.repo import find_repo_root

REPO_ROOT = find_repo_root()
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

# Hand-curated, human-reasoned suppressions (same posture as
# mpn_fabrication_gate.py's allowlist) -- NOT a way to silence this gate,
# a record of nets where the ambiguous shape (duplicate (component_ref,
# pad_number) tuples with real pad_count > 1) is real, understood, and
# verified-correctly-handled downstream, so it stays a permanent, benign
# property of these two components' footprints rather than a defect.
#
# discharge.k_dis1-no / discharge.k_dis2-no: K2/K3
# (temper:Relay_SPDT_Schrack-RT314012) fabricate contact pad "3" as two
# physical solder holes 7.5mm apart, both pad-numbered "3", for 16A
# current sharing -- confirmed against the footprint's own embedded
# datasheet comment in pcb/temper.kicad_pcb, not assumed. Both
# `_pipeline_grid._net_pad_positions` (routing) and
# `topology_copper_audit.is_self_referential_net` (diagnostic
# classification) were fixed this task to resolve/never misclassify this
# exact shape -- see their docstrings. Any OTHER net hitting this
# invariant is NOT pre-approved and must fail this gate until reviewed.
KNOWN_DUPLICATE_PAD_NUMBER_NETS: frozenset[str] = frozenset(
    {"discharge.k_dis1-no", "discharge.k_dis2-no"}
)


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Self-contained raw-text extraction (deliberately NOT imported from
# temper_placer -- see the module docstring's "Self-contained by design"
# section).
# ---------------------------------------------------------------------------

_FOOTPRINT_START_RE = re.compile(r'\n\s*\(footprint\s+"')
_REFERENCE_RE = re.compile(r'\(property\s+"Reference"\s+"([^"]*)"\)')
# One (pad "N" ... (net M "name")) occurrence. Pad blocks are single
# top-level s-expressions but may span multiple lines internally (net
# attribute is always on its own nested line in this project's KiCad
# export) -- match number and its OWN net attribute non-greedily up to
# the pad's own closing structure by requiring the net clause to appear
# before the next "(pad " token (bounded via a lookahead-free split
# instead, see _extract_pads_for_footprint).
_PAD_START_RE = re.compile(r'\(pad\s+"([^"]*)"')
_NET_ATTR_RE = re.compile(r'\(net\s+\d+\s+"([^"]*)"\)')


def _extract_footprint_blocks(content: str) -> list[str]:
    """Paren-balanced extraction of every top-level ``(footprint ...)``
    block, same technique as ``net_batching.py``'s ``_extract_ref_to_block``
    (split on footprint-start markers, each slice runs to the next one)."""
    starts = [m.start() for m in _FOOTPRINT_START_RE.finditer(content)]
    starts.append(len(content))
    return [content[starts[i] : starts[i + 1]] for i in range(len(starts) - 1)]


def _extract_pad_net_occurrences(footprint_block: str, ref: str) -> list[tuple[str, str]]:
    """Return ``(pad_number, net_name)`` for every ``(pad ...)`` occurrence
    in *footprint_block* that carries a ``(net ...)`` attribute (an
    unconnected pad has none and is skipped -- matches
    ``extract_nets_pure``'s ``if not pin.net: continue``).

    Split the block on each ``(pad "N"`` start so a pad's own ``(net ...)``
    clause is never accidentally attributed to a DIFFERENT pad later in
    the same footprint.
    """
    starts = [m.start() for m in _PAD_START_RE.finditer(footprint_block)]
    if not starts:
        return []
    starts.append(len(footprint_block))
    out: list[tuple[str, str]] = []
    for i in range(len(starts) - 1):
        segment = footprint_block[starts[i] : starts[i + 1]]
        num_m = _PAD_START_RE.match(segment)
        net_m = _NET_ATTR_RE.search(segment)
        if num_m and net_m:
            out.append((num_m.group(1), net_m.group(1)))
    return out


def _net_pin_occurrences(content: str) -> dict[str, list[tuple[str, str]]]:
    """net_name -> [(component_ref, pad_number), ...], one entry per raw
    physical ``(pad ...)`` occurrence -- mirrors ``Net.pins`` /
    ``pad_connectivity_audit``'s pad extraction exactly (same source data,
    independently re-derived here per this module's stated convention)."""
    occurrences: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for block in _extract_footprint_blocks(content):
        ref_m = _REFERENCE_RE.search(block)
        if not ref_m:
            continue
        ref = ref_m.group(1)
        for pad_number, net_name in _extract_pad_net_occurrences(block, ref):
            occurrences[net_name].append((ref, pad_number))
    return dict(occurrences)


def find_pin_identity_pad_mismatches(
    net_pin_occurrences: dict[str, list[tuple[str, str]]],
) -> list[str]:
    """Nets whose ``(component_ref, pad_number)`` identity view collapses
    to <=1 distinct tuple while the real occurrence count (physical pad
    count) is > 1 -- see the module docstring for the full mechanism.
    """
    mismatches: list[str] = []
    for net_name, occurrences in net_pin_occurrences.items():
        if not occurrences:
            continue
        distinct = len(set(occurrences))
        if distinct <= 1 and len(occurrences) > 1:
            mismatches.append(net_name)
    return sorted(mismatches)


def run(board_path: Path, *, allowlist: frozenset[str] = KNOWN_DUPLICATE_PAD_NUMBER_NETS) -> int:
    if not board_path.exists():
        print(f"GATE ERROR: board not found: {board_path}", file=sys.stderr)
        return EXIT_GATE_ERROR

    try:
        content = board_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"GATE ERROR: failed to read board {board_path}: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    net_pin_occurrences = _net_pin_occurrences(content)
    if not net_pin_occurrences:
        print(f"GATE ERROR: board {board_path} has zero nets with pads", file=sys.stderr)
        return EXIT_GATE_ERROR

    all_mismatches = find_pin_identity_pad_mismatches(net_pin_occurrences)
    known = sorted(n for n in all_mismatches if n in allowlist)
    unexpected = sorted(n for n in all_mismatches if n not in allowlist)

    print(f"Board: {board_path}")
    print(f"Nets checked: {len(net_pin_occurrences)}")
    if known:
        print(
            f"Known, reviewed duplicate-pad-number nets ({len(known)}, "
            f"see KNOWN_DUPLICATE_PAD_NUMBER_NETS): {', '.join(known)}"
        )

    gh = get_github_summary_path()

    if not unexpected:
        print(
            f"\nPASSED -- 0 unexpected pin-identity/pad-count mismatches "
            f"across {len(net_pin_occurrences)} net(s) checked "
            f"({len(known)} pre-approved, reviewed exception(s))."
        )
        if gh:
            with open(gh, "a") as f:
                f.write("### Net Pin-Identity / Pad Correspondence Gate -- PASSED\n")
                f.write(
                    f"0 unexpected violations across {len(net_pin_occurrences)} "
                    f"net(s) ({len(known)} pre-approved exception(s): "
                    f"{', '.join(known) if known else 'none'}).\n"
                )
        return EXIT_OK

    print(f"\n=== VIOLATIONS: {len(unexpected)} (unexpected, not on the allowlist) ===")
    for name in unexpected:
        occurrences = net_pin_occurrences.get(name, [])
        print(
            f"  {name}: pin-identity view collapses to <=1 distinct "
            f"(ref, pad_number) tuple ({occurrences!r}) but the board "
            f"carries {len(occurrences)} real physical pad occurrence(s) "
            "for this net -- either a pin-resolution code path elsewhere "
            "collapsed a real multi-pad net, or this is a genuine naming "
            "coincidence that needs an explicit, reasoned exception added "
            "to KNOWN_DUPLICATE_PAD_NUMBER_NETS, never a silent pass."
        )

    if gh:
        with open(gh, "a") as f:
            f.write("### Net Pin-Identity / Pad Correspondence Gate -- FAILED\n")
            f.write(f"{len(unexpected)} unexpected violation(s)\n\n")
            for name in unexpected:
                f.write(f"- `{name}`\n")

    print(f"\nFAILED -- {len(unexpected)} unexpected violation(s)")
    return EXIT_VIOLATION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    args = parser.parse_args()
    sys.exit(run(args.board))


if __name__ == "__main__":
    main()
