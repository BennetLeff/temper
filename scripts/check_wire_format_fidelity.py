#!/usr/bin/env python3
"""Fail when a Rust kernel reimplements a Python geometry helper but its wire format drops a field that helper reads.

WHY THIS EXISTS
---------------
Three kernels shipped in 2026-08 computing different answers than the Python
they replaced, each because the wire format carried fewer fields than the
shipped helper reads:

    escape_via.rs           hardcoded DEFAULT_ROUNDRECT_RATIO; the shipped
                            pin_world_radius reads `pin.roundrect_ratio`
    net_ordering.rs         no `initial_side` slot; the shipped
                            pin_world_position mirrors X for back-side pads
    congestion_analysis.rs  same `initial_side` omission

None was caught by its differential. All three passed -- 164, 145 and 575
tests -- because the fixture builders never populated the missing field, so
the divergence was unreachable from the corpus. Each kernel also DOCUMENTED
the omission as safe, in comments of the form "the corpus never carries X,
so X is always its default". That is a property of the fixtures, not of the
domain, and it was false on any real board.

A differential cannot catch this by construction: it compares the pinned
oracle against the Rust over corpus inputs, so a field absent from every
corpus row is absent from the proof.

THE RULE
--------
A kernel that defines its OWN copy of a geometry helper -- `pin_world_position`,
`world_radius`, `pad_world_position` -- is reimplementing shipped Python, and
must reference every attribute that Python reads for the same computation:

    computes a POSITION   (rotate_local_to_world / normalize_rotation)
                          -> must reference `initial_side`, `initial_rotation_quadrant`
    computes a RADIUS     (bounding_radius / pad_bounding)
                          -> must reference `roundrect_ratio`, `shape`

"Reference" is deliberately weak -- the name appearing anywhere in the file,
including in a comment explaining a deliberate omission. This gate exists to
force the ENGAGEMENT, not to dictate the answer. A kernel that considered a
field and documented why it does not apply passes; a kernel that never
considered it fails.

Kernels that merely CALL a shared primitive (`rotate_local_to_world_py`) are
not reimplementing anything and are out of scope -- mirroring is the caller's
job there.

ALLOWLIST
---------
`.wire-format-allowlist` records deliberate exceptions with a reason, e.g.
io/dsn_exporter.py keeps `pin_world_position` in Python on purpose because
porting sin/cos would "inject a divergence into a sort key, where fixture
differentials are least likely to catch it" -- the same failure this gate
covers, correctly reasoned about by that author.

USAGE
    uv run python scripts/check_wire_format_fidelity.py
    uv run python scripts/check_wire_format_fidelity.py --write-allowlist

EXIT CODES
    0  every reimplementing kernel references the fields its helper reads
    1  a kernel drops a field, or an allowlist entry is stale
    2  the scan found no kernels at all (broken scan, not a clean tree)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = REPO_ROOT / ".wire-format-allowlist"
HELPER = REPO_ROOT / "packages/temper-placer/src/temper_placer/core/pin_geometry.py"

OWN_COPY = re.compile(r"\bfn\s+(pin_world_position|world_radius|pad_world_position)\b")
DOES_POSITION = re.compile(r"rotate_local_to_world|normalize_rotation")
DOES_RADIUS = re.compile(r"bounding_radius|pad_bounding")

POSITION_FIELDS = ("initial_side", "initial_rotation_quadrant")
RADIUS_FIELDS = ("roundrect_ratio", "shape")


def helper_reads() -> set[str]:
    """Attributes the shipped helper reads off a pin/component."""
    if not HELPER.exists():
        return set()
    src = HELPER.read_text()
    return (set(re.findall(r"(?:pin|comp|component)\.([a-z_]+)", src))
            | set(re.findall(r'getattr\((?:pin|comp|component),\s*"([a-z_]+)"', src)))


def scan() -> list[tuple[str, list[str]]]:
    """(kernel path, missing fields) for every kernel with its own helper copy."""
    reads = helper_reads()
    out: list[tuple[str, list[str]]] = []
    for rs in sorted(REPO_ROOT.glob("packages/*/src/**/*.rs")):
        if "/target" in str(rs):
            continue
        try:
            text = rs.read_text()
        except OSError:
            continue
        if not OWN_COPY.search(text):
            continue
        required: list[str] = []
        if DOES_POSITION.search(text):
            required += [f for f in POSITION_FIELDS if f in reads or not reads]
        if DOES_RADIUS.search(text):
            required += [f for f in RADIUS_FIELDS if f in reads or not reads]
        missing = [f for f in dict.fromkeys(required) if f not in text]
        out.append((str(rs.relative_to(REPO_ROOT)), missing))
    return out


def load_allowlist() -> dict[str, str]:
    if not ALLOWLIST.exists():
        return {}
    entries: dict[str, str] = {}
    for line in ALLOWLIST.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, reason = line.partition("\t")
        entries[key.strip()] = reason.strip()
    return entries


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write-allowlist", action="store_true")
    args = ap.parse_args()

    results = scan()
    if not results:
        print("FAIL: found no kernel defining its own geometry helper -- the scan "
              "is broken, not the tree (a gate that inspects nothing passes "
              "vacuously).", file=sys.stderr)
        return 2

    violations = {f"{path}::{field}": path
                  for path, missing in results for field in missing}
    allow = load_allowlist()

    if args.write_allowlist:
        lines = [
            "# Kernels that reimplement a shipped geometry helper but omit a field",
            "# that helper reads. Each entry needs a REASON -- a deliberate,",
            "# reasoned omission is fine; an unconsidered one is the bug this gate",
            "# exists to catch.",
            "#",
            "# <kernel path>::<field>\\t<reason>",
            "",
        ]
        for key in sorted(violations):
            lines.append(f"{key}\t{allow.get(key, '').strip() or 'recorded without a reason'}")
        ALLOWLIST.write_text("\n".join(lines) + "\n")
        print(f"wrote {ALLOWLIST.name}: {len(violations)} entr(ies)")
        return 0

    new = sorted(set(violations) - set(allow))
    stale = sorted(set(allow) - set(violations))

    if not new and not stale:
        checked = len(results)
        print(f"OK: {checked} kernel(s) reimplement a geometry helper; "
              f"each references the fields that helper reads.")
        return 0

    print("FAIL: wire-format fidelity gate\n")
    for key in new:
        path, field = key.rsplit("::", 1)
        print(f"DROPPED_FIELD  {field}")
        print(f"               {path} reimplements a shipped geometry helper but")
        print(f"               never mentions `{field}`, which that helper reads.")
        print("               The differential cannot catch this: if no corpus row")
        print("               sets the field, the divergence is unreachable from")
        print("               the proof. Handle it, or record it with a reason.")
    for key in stale:
        print(f"STALE_ENTRY    {key} no longer drops the field -- record the fix")
    return 1


if __name__ == "__main__":
    sys.exit(main())
