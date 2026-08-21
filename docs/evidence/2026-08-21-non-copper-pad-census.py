# provenance: board sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
# Read-only with respect to any .kicad_pcb: boards are parsed, never opened for
# write, and the production board's sha256 is asserted before and after. No
# threshold, ceiling, ratchet, allowlist or oracle is read for modification or
# written.
"""Enumerate every pad that declares no copper layer, and cross-check kicad-cli.

Answers three questions with one run:

1. **Which pads change classification?** Every ``(pad ...)`` token's
   ``(layers ...)`` set is read straight from the board bytes -- independent of
   this repo's parser, so a parser defect cannot also supply the expectation --
   and compared against what ``parse_kicad_pcb`` reports through ``Pin.layer``
   (the pinned, defective field) and ``Pin.is_copper`` (the correction).

2. **Does it orphan a net?** Removing a pad from a copper census is monotone
   for distances, but a net whose declared terminal places no copper cannot be
   reached by any trace. Every affected net's real-copper pad count is
   reported.

3. **Does kicad-cli agree?** ``kicad-cli pcb drc`` reads the board directly.
   If it never names a pad this repo called copper, the two disagree and
   kicad-cli is the authority. ``--drc-report`` grades that.

Usage::

    python docs/evidence/2026-08-21-non-copper-pad-census.py
    python docs/evidence/2026-08-21-non-copper-pad-census.py \\
        --board power_pcb_dataset/corpus/rp2040_designguide/RP2040-Guide.kicad_pcb
    kicad-cli pcb drc --all-track-errors --format json -o /tmp/drc.json \\
        pcb/temper.kicad_pcb
    python docs/evidence/2026-08-21-non-copper-pad-census.py --drc-report /tmp/drc.json
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb

PAD_RE = re.compile(r'\(pad\s+"([^"]*)"[^\n]*?\(layers\s+([^)]*)\)')
# Two spellings of a footprint's reference designator: KiCad 7+ writes
# `(property "Reference" "K1")`, KiCad 6 and the older corpus boards write
# `(fp_text reference "K1" ...)`. Both are matched so the corpus boards can be
# graded by the same census as the production board.
REF_RES = (
    re.compile(r'\(property "Reference" "([^"]+)"'),
    re.compile(r"\(fp_text\s+reference\s+\"?([^\"\s)]+)"),
)
# `(footprint ` at any indentation -- the production board indents by two
# spaces, the corpus boards by none.
FOOTPRINT_SPLIT = re.compile(r"\n\s*\(footprint ")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def declared_from_bytes(board: Path) -> dict[tuple[int, int], tuple[str, str, tuple[str, ...]]]:
    """``(footprint index, pad ordinal) -> (ref, pad number, layer tokens)``.

    Keyed positionally, not by ``(ref, pad number)``, and both halves are
    load-bearing. Unnumbered NPTH mounting pads (``(pad "" np_thru_hole ...)``)
    share the empty pad number, so the pad ordinal is needed; and reference
    designators are NOT unique across footprints on every corpus board
    (``piantor_right`` has ``H4`` three times and ``H1`` twice), so the
    footprint index is needed too. Footprints appear in the same order in the
    file and in ``netlist.components``, which is what makes the two sides
    comparable.
    """
    text = board.read_text(encoding="utf-8")
    out: dict[tuple[int, int], tuple[str, str, tuple[str, ...]]] = {}
    for fi, block in enumerate(FOOTPRINT_SPLIT.split(text)[1:]):
        ref = "<noref>"
        for pattern in REF_RES:
            m = pattern.search(block)
            if m is not None:
                ref = m.group(1)
                break
        for i, (num, layers) in enumerate(PAD_RE.findall(block)):
            out[(fi, i)] = (ref, num, tuple(layers.replace('"', "").split()))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, default=Path("pcb/temper.kicad_pcb"))
    ap.add_argument(
        "--drc-report",
        type=Path,
        default=None,
        help="kicad-cli `pcb drc --format json` output for the same board",
    )
    args = ap.parse_args(argv[1:])

    before = sha256(args.board)
    print(f"board                : {args.board}")
    print(f"board sha256 BEFORE  : {before}")

    declared = declared_from_bytes(args.board)
    parsed = parse_kicad_pcb(args.board, normalize=False)
    pins = {
        (ci, i): (c.ref, p)
        for ci, c in enumerate(parsed.netlist.components)
        for i, p in enumerate(c.pins)
    }

    if set(declared) != set(pins):
        raise SystemExit(
            "byte scan and parser disagree on the pad set "
            f"({len(declared)} vs {len(pins)}) -- refusing to report a census "
            "over two different boards"
        )

    print(f"pads                 : {len(declared)}")
    print("\n--- declared layer-set histogram ---")
    hist = collections.Counter(v[2] for v in declared.values())
    for tokens, n in hist.most_common():
        cu = any(t.endswith(".Cu") for t in tokens)
        print(f"  {n:5d}  {'copper    ' if cu else 'NO COPPER '} {tokens}")

    print("\n--- pads that place NO copper ---")
    ghosts = []
    for key in sorted(declared):
        _ref_from_bytes, num, tokens = declared[key]
        if any(t.endswith(".Cu") for t in tokens):
            continue
        ref, pin = pins[key]
        ghosts.append((ref, num, tokens, pin))
        print(
            f"  {ref}.{num or '<unnumbered>'}  declared={tokens}  "
            f"Pin.layer={pin.layer!r}  Pin.is_copper={pin.is_copper}  "
            f"net={pin.net!r}"
        )
    if not ghosts:
        print("  (none)")
    print(f"\n  total: {len(ghosts)} of {len(declared)} pads")

    # Cross-check: is_copper must agree with the bytes for EVERY pad, not just
    # the interesting ones. Under-reporting copper would silence real
    # violations, which is the failure mode that matters most here.
    wrong = [
        (k, declared[k], pins[k][1].is_copper)
        for k in declared
        if pins[k][1].is_copper is not any(t.endswith(".Cu") for t in declared[k][2])
    ]
    if wrong:
        for _k, d, got in wrong:
            print(f"  MISCLASSIFIED {d[0]}.{d[1]} declared={d[2]} is_copper={got}")
        raise SystemExit(f"{len(wrong)} pad(s) misclassified against the board bytes")
    print("  is_copper agrees with the board bytes on every pad.")

    # `Pin.layer` is NOT corrected (two pinned oracles encode its "F.Cu"
    # fallback -- see the accompanying .md ss 6). Show the residual lie so it
    # stays visible rather than becoming folklore.
    lying = [(r, n) for r, n, _t, p in ghosts if str(p.layer).endswith(".Cu")]
    if lying:
        print(
            f"\n  NOTE: Pin.layer still reports a copper layer for "
            f"{len(lying)} of them: {lying}. That field is pinned by "
            "tests/io/_parse_engine_py_oracle and tests/core/_netlist_py_oracle; "
            "use Pin.is_copper."
        )

    print("\n--- nets carrying a non-copper declared pad ---")
    by_net: dict[str, list] = {}
    for c in parsed.netlist.components:
        for p in c.pins:
            if p.net:
                by_net.setdefault(p.net, []).append((c.ref, p.number, p.is_copper))
    touched = {p.net for _r, _n, _t, p in ghosts if p.net}
    for net in sorted(touched):
        pads = by_net[net]
        real = [x for x in pads if x[2]]
        verdict = (
            "ORPHANED by the exclusion"
            if len(real) < 2
            else "still routable among its real pads"
        )
        print(f"  {net!r}: {len(pads)} declared, {len(real)} copper -> {verdict}")
        for ref, num, cu in pads:
            print(f"      {ref}.{num:<4} {'copper' if cu else 'NO COPPER'}")
    if not touched:
        print("  (none)")

    if args.drc_report is not None:
        print("\n--- kicad-cli cross-check ---")
        report = json.loads(args.drc_report.read_text(encoding="utf-8"))
        buckets = {
            k: (report.get(k) or [])
            for k in ("violations", "unconnected_items", "schematic_parity")
        }
        for k, v in buckets.items():
            print(f"  {k}: {len(v)}")
        descs = [
            i.get("description", "")
            for items in buckets.values()
            for v in items
            for i in v.get("items", [])
        ]
        for ref, num, _t, _p in ghosts:
            hits = [d for d in descs if f"of {ref}" in d and f"ad {num}" in d]
            print(f"  {ref}.{num}: {len(hits)} kicad-cli item(s)")
            for d in hits[:5]:
                print(f"      {d}")
        print(
            "  kicad-cli reads the board directly; a pad it never names is a "
            "pad it never treated as copper."
        )

    after = sha256(args.board)
    print(f"\nboard sha256 AFTER   : {after}")
    if after != before:
        raise SystemExit("BOARD WAS MODIFIED -- aborting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
