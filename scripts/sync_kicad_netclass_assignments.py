#!/usr/bin/env python3
"""Sync ``pcb/temper.kicad_pro``'s ``net_settings.netclass_assignments``
from ``TEMPER_NET_ASSIGNMENTS`` (``packages/temper-placer/src/temper_placer/
core/design_rules.py``), the Python-side source of truth for net -> netclass
classification.

Why this exists
----------------
PR #1023 hand-fixed four stale/case-mismatched entries in ``pcb/temper.
kicad_pro`` (``ac_l``/``ac_n`` entered uppercase, never matching the real
lowercase board net names; ``SW_NODE``/``+170V_BUS`` absent entirely) and,
in the same commit's own message, found roughly twenty more of the same
defect shape but deliberately did not fix them -- unmeasured, out of scope
for that change. That PR's own commit message names the root cause: "two
hand-maintained copies of one mapping is what caused this defect [twice]."
This script is the generator that closes the gap: ``kicad_pro``'s
assignments are now DERIVED from ``TEMPER_NET_ASSIGNMENTS``, not
hand-copied from it, so the two tables cannot independently drift again as
long as this script (or its ``--check`` mode, wired into CI) is run.

What it does NOT do
--------------------
It never removes an existing ``kicad_pro`` entry, even one that names a net
no longer present on the board (a "dead alias" -- there are many, e.g.
``SWITCH_NODE``/``PWM_H``/``RTD_CS`` from an earlier schematic revision).
Only additive/corrective sync: add a missing net, or correct a net whose
declared class disagrees with ``TEMPER_NET_ASSIGNMENTS``. This mirrors
PR #1023's own precedent (it only ever added lines, never deleted any) and
keeps this script's blast radius scoped to exactly what the SSOT asserts,
not a wholesale replacement that could silently drop something a human
added directly to ``kicad_pro`` for a reason this script doesn't know
about.

PWR_RTN is structurally protected, not just by convention
-----------------------------------------------------------
``scripts/check_hv_netclass_coverage.py``'s docstring flags ``PWR_RTN``
(and its alias ``CGND``) as a fifth net in this exact defect shape, left as
an explicit, open, human decision because of its order-of-magnitude larger
blast radius (a return net with far more copper than every net this script
touches, combined). Both map, via ``TEMPER_NET_ASSIGNMENTS``, to the
``"GND"`` class -- and ``pcb/temper.kicad_pro`` has no ``"Ground"`` (or any
other) declared netclass corresponding to it, so this script's own
"target class must be a class ``kicad_pro`` actually declares" rule already
excludes them structurally, without needing a special-cased net-name
blocklist. ``PROTECTED_NET_CLASSES`` below is defense in depth for exactly
this net: if ``design_rules.py`` or ``kicad_pro`` ever changes shape such
that ``GND`` *would* resolve to a declared class, this script still refuses
to touch ``PWR_RTN``/``CGND`` rather than silently picking up the
order-of-magnitude change that gate's docstring reserves for a human.

Usage
-----
    uv run python scripts/sync_kicad_netclass_assignments.py --check
    uv run python scripts/sync_kicad_netclass_assignments.py --write

``--check`` (CI mode): exit 0 if ``kicad_pro`` already agrees with the SSOT
for every net the SSOT covers, exit 1 and print the diff otherwise. Makes
no changes.

``--write``: apply the sync in place, preserving the file's existing
formatting and key order (only appends new keys or corrects an existing
value's string in place) -- never a full JSON re-dump, which would risk
reformatting unrelated parts of a hand-maintained KiCad project file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KICAD_PRO_PATH = REPO_ROOT / "pcb" / "temper.kicad_pro"
KICAD_PCB_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"

sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer" / "src"))

from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS  # noqa: E402

# Nets this script will never touch, even if their design_rules.py class
# were ever to resolve to a declared kicad_pro netclass in the future. See
# module docstring -- this is defense in depth on top of the structural
# "GND has no declared kicad_pro class" protection that holds today.
PROTECTED_NETS: frozenset[str] = frozenset({"PWR_RTN", "CGND"})

NETCLASS_ASSIGNMENTS_KEY = '"netclass_assignments": {'

_BOARD_NET_RE = re.compile(r'\(net \d+ "([^"]*)"\)')


def load_board_net_names(pcb_path: Path) -> set[str] | None:
    """Return the set of net names declared in *pcb_path*'s net table, or
    ``None`` if the file cannot be read or declares no nets.

    Read-only; this script never writes the board. Used ONLY by the
    ``PROTECTED_NETS`` tripwire in ``main`` to decide whether a protected
    net names real copper. ``None`` (unreadable/empty board) makes that
    tripwire fail closed -- it then behaves exactly as if every protected
    net named real copper.
    """
    try:
        text = pcb_path.read_text(encoding="utf-8")
    except OSError:
        return None
    names = set(_BOARD_NET_RE.findall(text))
    names.discard("")
    return names or None


class SyncError(Exception):
    """Raised for any condition that must fail closed."""


def load_declared_classes(kicad_pro_text: str) -> set[str]:
    data = json.loads(kicad_pro_text)
    classes = data.get("net_settings", {}).get("classes", [])
    return {c["name"] for c in classes if "name" in c}


def load_current_assignments(kicad_pro_text: str) -> dict[str, str]:
    data = json.loads(kicad_pro_text)
    return dict(data.get("net_settings", {}).get("netclass_assignments", {}))


def compute_target_assignments(declared_classes: set[str]) -> dict[str, str]:
    """Return {net: class} for every TEMPER_NET_ASSIGNMENTS entry whose
    class is both a real declared kicad_pro netclass and not a protected
    net -- i.e. exactly what this script is authorized to write.
    """
    targets: dict[str, str] = {}
    for net, cls in TEMPER_NET_ASSIGNMENTS.items():
        if net in PROTECTED_NETS:
            continue
        if cls not in declared_classes:
            continue
        targets[net] = cls
    return targets


def compute_diff(
    current: dict[str, str], targets: dict[str, str]
) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    """Return (missing, mismatched): missing = [(net, class)] entries
    absent from *current*; mismatched = [(net, old_class, new_class)]
    entries present but disagreeing.
    """
    missing: list[tuple[str, str]] = []
    mismatched: list[tuple[str, str, str]] = []
    for net, cls in targets.items():
        if net not in current:
            missing.append((net, cls))
        elif current[net] != cls:
            mismatched.append((net, current[net], cls))
    return missing, mismatched


def _find_netclass_assignments_block(text: str) -> tuple[int, int]:
    """Return (start, end) character offsets of the netclass_assignments
    object body (the region between its opening ``{`` and matching ``}``),
    via brace counting -- robust to nested braces never actually occurring
    here (values are plain strings), but written generically anyway rather
    than assuming a flat object.
    """
    key_idx = text.find(NETCLASS_ASSIGNMENTS_KEY)
    if key_idx == -1:
        raise SyncError(f"could not find {NETCLASS_ASSIGNMENTS_KEY!r} in {KICAD_PRO_PATH}")
    open_brace = key_idx + len(NETCLASS_ASSIGNMENTS_KEY) - 1
    depth = 0
    for i in range(open_brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return open_brace, i
    raise SyncError("unterminated netclass_assignments object in kicad_pro")


def apply_sync(
    text: str,
    missing: list[tuple[str, str]],
    mismatched: list[tuple[str, str, str]],
) -> str:
    """Return *text* with the given missing/mismatched entries applied,
    editing only inside the netclass_assignments block and preserving
    every other byte of the file untouched.
    """
    start, end = _find_netclass_assignments_block(text)
    block = text[start : end + 1]  # includes the surrounding { and }

    # 1. Fix mismatched values in place, by exact-match on the existing
    #    "net": "old_class" line -- never touches key order or any other
    #    net's line.
    for net, old_cls, new_cls in mismatched:
        pattern = re.compile(
            r'("' + re.escape(net) + r'"\s*:\s*")' + re.escape(old_cls) + r'(")'
        )
        new_block, n = pattern.subn(r"\g<1>" + new_cls + r"\g<2>", block, count=1)
        if n != 1:
            raise SyncError(
                f"expected exactly one occurrence of {net!r}: {old_cls!r} in "
                f"netclass_assignments, found {n}"
            )
        block = new_block

    # 2. Append missing entries just before the closing brace, giving the
    #    previously-last line a trailing comma if it lacks one. Rebuilt
    #    cleanly from the trimmed tail rather than patched in place, so no
    #    stray trailing-whitespace-only line can survive from the original
    #    pre-closing-brace indentation.
    if missing:
        inner = block[1:-1]  # strip the outer { }
        trimmed = inner.rstrip()
        if trimmed and not trimmed.endswith(","):
            trimmed += ","
        new_lines = ",\n".join(f'      "{net}": "{cls}"' for net, cls in missing)
        # "\n    " reproduces the 4-space indentation KiCad uses before the
        # closing brace's own line, matching every other object in this file.
        inner = f"{trimmed}\n{new_lines}\n    " if trimmed else f"\n{new_lines}\n    "
        block = "{" + inner + "}"

    return text[:start] + block + text[end + 1 :]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 and print the diff if kicad_pro is out of sync; make no changes.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply the sync to pcb/temper.kicad_pro in place.",
    )
    parser.add_argument(
        "--kicad-pro",
        type=Path,
        default=KICAD_PRO_PATH,
        help=f"Path to the kicad_pro file (default: {KICAD_PRO_PATH})",
    )
    args = parser.parse_args()

    if not args.check and not args.write:
        parser.error("one of --check or --write is required")

    if not args.kicad_pro.exists():
        print(f"ERROR: {args.kicad_pro} not found", file=sys.stderr)
        return 5

    text = args.kicad_pro.read_text(encoding="utf-8")

    try:
        declared_classes = load_declared_classes(text)
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"ERROR: could not parse {args.kicad_pro}: {exc}", file=sys.stderr)
        return 5

    current = load_current_assignments(text)
    targets = compute_target_assignments(declared_classes)

    # PROTECTED_NETS tripwire.
    #
    # The PRIMARY refusal is `compute_target_assignments`, which drops every
    # PROTECTED_NET from `targets` unconditionally -- this script can never
    # write PWR_RTN or CGND, and that is unchanged by the narrowing below.
    # This tripwire is the defense-in-depth layer on top: hard-fail (exit 5)
    # rather than let a protected net's reserved human decision be picked up
    # silently.
    #
    # NARROWED 2026-08-19 (netclass two-table reconciliation). As written, the
    # tripwire fired whenever a protected net's TEMPER_NET_ASSIGNMENTS class
    # merely *was* a declared kicad_pro class -- regardless of whether there
    # was any pending decision to adjudicate. Two same-day changes made that
    # unconditionally true and thereby turned this entire gate off:
    #
    #   * 2026-08-12, commit 322cbf5b0 (#1092) reassigned
    #     TEMPER_NET_ASSIGNMENTS["PWR_RTN"] from "GND" to "HighVoltage" -- a
    #     declared class. But that reclassification IS the human decision this
    #     tripwire reserves, and it had already been TAKEN AND LANDED: PR
    #     #1083 wrote "PWR_RTN": "HighVoltage" into pcb/temper.kicad_pro.
    #     Both tables have agreed ever since, so there has been nothing left
    #     to reserve -- yet the tripwire kept firing on the agreement itself.
    #   * 2026-08-12 also gave kicad_pro a real declared "GND" class
    #     (docs/evidence/2026-08-12-gnd-class-decision.md), so CGND -> "GND"
    #     became "declared" too.
    #
    # Measured consequence: `--check` exited 5 before computing any diff, on
    # every run, from 2026-08-12 to 2026-08-19. The repo's only net -> netclass
    # drift generator was dead for a week, which is how 13 missing and 1
    # mismatched entry accumulated between TEMPER_NET_ASSIGNMENTS and
    # pcb/temper.kicad_pro unnoticed -- including 7 elec/domain_manifest.yaml
    # HV-domain nets sitting at KiCad's Default 0.2mm/no-creepage class on the
    # fab-authoritative kicad-cli DRC path.
    #
    # The tripwire now fires when there is an actual reserved decision to
    # make: a protected net whose kicad_pro value would have to CHANGE
    # (`current != target`) AND which names real copper on the board, so that
    # the change would carry the physical blast radius the reservation exists
    # for. Both escape conditions are provable from the files themselves, not
    # a hand-maintained name allowlist, and anything with real copper and a
    # real pending change still hard-fails exactly as before. An unreadable
    # board file yields `board_nets is None` and fails closed.
    board_nets = load_board_net_names(KICAD_PCB_PATH)
    for protected in sorted(PROTECTED_NETS):
        cls = TEMPER_NET_ASSIGNMENTS.get(protected)
        if cls not in declared_classes:
            # Structural protection still holds: the class is not one
            # kicad_pro declares, so it could never be written anyway.
            continue
        if current.get(protected) == cls:
            print(
                f"NOTE: {protected!r} (protected) resolves to declared "
                f"kicad_pro netclass {cls!r}, and pcb/temper.kicad_pro ALREADY "
                f"carries that exact value -- the reserved reclassification "
                f"has been taken and landed in both tables; nothing pending."
            )
            continue
        if board_nets is not None and protected not in board_nets:
            print(
                f"NOTE: {protected!r} (protected) resolves to declared "
                f"kicad_pro netclass {cls!r} but names NO net on "
                f"pcb/temper.kicad_pcb, so no assignment for it can reach any "
                f"conductor. Still never written (excluded from targets); "
                f"deleting the stale entry is the reserved decision, not this "
                f"script's."
            )
            continue
        print(
            f"ERROR: {protected!r} (protected) resolves to a declared "
            f"kicad_pro netclass ({cls!r}) and pcb/temper.kicad_pro does not "
            f"already carry that value (currently {current.get(protected)!r}) "
            "-- this script refuses to proceed rather than silently pick it "
            "up. See module docstring; this is the PWR_RTN/CGND "
            "reclassification reserved for a human decision.",
            file=sys.stderr,
        )
        return 5

    missing, mismatched = compute_diff(current, targets)

    if not missing and not mismatched:
        print(
            f"OK: {args.kicad_pro} netclass_assignments already agrees with "
            f"TEMPER_NET_ASSIGNMENTS for all {len(targets)} covered net(s)."
        )
        return 0

    print(f"{len(missing)} missing, {len(mismatched)} mismatched (of {len(targets)} covered nets):")
    for net, cls in missing:
        print(f"  MISSING     {net!r}: (absent) -> {cls!r}")
    for net, old, new in mismatched:
        print(f"  MISMATCHED  {net!r}: {old!r} -> {new!r}")

    if args.check:
        print("\nFAIL: run with --write to apply, or update TEMPER_NET_ASSIGNMENTS if it is wrong.")
        return 1

    new_text = apply_sync(text, missing, mismatched)
    # Round-trip through json.loads to verify the surgical edit produced
    # valid JSON before writing anything to disk.
    try:
        json.loads(new_text)
    except json.JSONDecodeError as exc:
        print(f"ERROR: sync produced invalid JSON, aborting write: {exc}", file=sys.stderr)
        return 5

    args.kicad_pro.write_text(new_text, encoding="utf-8")
    print(f"\nWROTE {args.kicad_pro}: {len(missing)} added, {len(mismatched)} corrected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
