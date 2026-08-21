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
touches, combined). ``PROTECTED_NETS`` below names both, and
``compute_target_assignments`` drops them unconditionally: whatever class
``TEMPER_NET_ASSIGNMENTS`` gives them, and whether or not
``pcb/temper.kicad_pro`` declares that class, this script will not write
them.

That protection used to lean on a second, structural mechanism -- "target
class must be a class ``kicad_pro`` actually declares", which held while
both nets mapped to ``"GND"`` and ``kicad_pro`` declared no such class.
Neither half of that is true any more: ``kicad_pro`` declared ``GND`` on
2026-08-12 (docs/evidence/2026-08-12-gnd-class-decision.md) and
``TEMPER_NET_ASSIGNMENTS`` now maps ``PWR_RTN`` to ``"HighVoltage"``. The
structural backstop is gone; ``PROTECTED_NETS`` is now the mechanism, not
the belt on top of it, and ``_verify_protected_unchanged`` re-checks the
rendered text before any write so a bug in the diff/edit path cannot slip
one through unnoticed.

Why the reservation is per-net, not file-wide
---------------------------------------------
This script used to react to "a protected net's class is now declared" by
``exit 5``-ing before computing any diff at all -- refusing the whole file
over one reserved decision. That is a strictly larger refusal than the one
``check_hv_netclass_coverage.py`` reserves, and it had a cost nobody
measured: from the moment ``kicad_pro`` declared ``GND``, *every* pending
assignment this script derives became unwritable, including four OVP
protective-divider nets (``safety.ovp.r_{div,adc}_top{1,2}-p2``) that
``TEMPER_NET_ASSIGNMENTS`` maps to ``HighVoltage`` and that consequently
sat at KiCad's ``Default`` 0.2mm -- outside every netclass-keyed clearance
and creepage rule in ``pcb/temper.kicad_dru`` -- while reaching full
``+170V_BUS`` under the single fault IEC 60335-1 cl. 8.1.4 requires be
assumed (docs/evidence/2026-08-13-ovp01-midchain-single-fault-creepage.md).
The blocked write was collateral damage from an unrelated reservation.

The reservation itself is unchanged in force -- ``PWR_RTN`` and ``CGND``
are still never written, and the condition is still reported loudly, on
stderr, on every run. Only its *blast radius* is narrowed: a reserved net
now blocks itself and nothing else.

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

sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer" / "src"))

from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS  # noqa: E402

# Nets this script will never touch, whatever class design_rules.py gives
# them and whether or not kicad_pro declares that class. See module
# docstring: the structural "GND has no declared kicad_pro class" backstop
# this used to sit on top of no longer exists, so this set is now the
# mechanism rather than defense in depth, and `_verify_protected_unchanged`
# re-checks it against the rendered text before any write.
PROTECTED_NETS: frozenset[str] = frozenset({"PWR_RTN", "CGND"})

NETCLASS_ASSIGNMENTS_KEY = '"netclass_assignments": {'


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


def compute_reserved(declared_classes: set[str]) -> list[tuple[str, str]]:
    """Return [(net, ssot_class)] for every PROTECTED_NETS member whose
    ``TEMPER_NET_ASSIGNMENTS`` class is a class ``kicad_pro`` actually
    declares -- i.e. every net that *could* be written today and is
    deliberately not being written, pending the human decision
    ``check_hv_netclass_coverage.py``'s docstring reserves.

    This is a report, not a gate. It exists so the reservation stays
    visible on every run instead of becoming an unremarked silence -- but
    it deliberately does not block the nets it does not name. See the
    module docstring's "Why the reservation is per-net" section.
    """
    reserved: list[tuple[str, str]] = []
    for net in sorted(PROTECTED_NETS):
        cls = TEMPER_NET_ASSIGNMENTS.get(net)
        if cls is not None and cls in declared_classes:
            reserved.append((net, cls))
    return reserved


def _verify_protected_unchanged(before_text: str, after_text: str) -> None:
    """Raise SyncError if any PROTECTED_NETS entry's assignment differs
    between *before_text* and *after_text*.

    ``compute_target_assignments`` already excludes protected nets, so this
    can only fire on a bug in the diff or text-edit path (e.g. a regex that
    matched more than its own key). It runs on the rendered text, after the
    edit and before the write, so a protected net cannot be added,
    retargeted, or removed by this script even by accident.
    """
    before = load_current_assignments(before_text)
    after = load_current_assignments(after_text)
    for net in sorted(PROTECTED_NETS):
        if before.get(net) != after.get(net):
            raise SyncError(
                f"refusing to write: protected net {net!r} would change from "
                f"{before.get(net)!r} to {after.get(net)!r}. PROTECTED_NETS is "
                "reserved for an explicit human decision (see module "
                "docstring); a sync that moves one is a bug, not an update."
            )


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

    # The PWR_RTN/CGND reservation, reported per-net and never silently.
    # This used to `return 5` here, before any diff was computed, which
    # refused the whole file over one reserved decision and left every
    # unrelated pending assignment unwritable (see module docstring). The
    # refusal is unchanged in force -- these nets are excluded from
    # `targets` above and re-checked against the rendered text below -- but
    # it now blocks only itself.
    for protected, cls in compute_reserved(declared_classes):
        on_file = current.get(protected)
        state = (
            "AGREES ALREADY, nothing pending"
            if on_file == cls
            else f"PENDING: would become {cls!r}"
        )
        print(
            f"RESERVED: {protected!r} -> {cls!r} in TEMPER_NET_ASSIGNMENTS, a "
            f"class pcb/temper.kicad_pro declares; on file it is {on_file!r} "
            f"({state}). NOT written, now or ever, by this script: "
            "PWR_RTN/CGND reclassification is an explicit human decision "
            "reserved by scripts/check_hv_netclass_coverage.py's docstring "
            "(an order-of-magnitude larger blast radius than any net this "
            "script does write). This reservation covers these nets only -- "
            "every other net is synced normally.",
            file=sys.stderr,
        )

    missing, mismatched = compute_diff(current, targets)

    # Fail closed: a protected net must never reach the write path. It
    # cannot, via compute_target_assignments -- assert it anyway rather
    # than trust that at a distance.
    touched = {net for net, _ in missing} | {net for net, _, _ in mismatched}
    leaked = sorted(touched & PROTECTED_NETS)
    if leaked:
        print(
            f"ERROR: protected net(s) {leaked} reached the sync diff -- "
            "compute_target_assignments should have excluded them. Refusing "
            "to proceed.",
            file=sys.stderr,
        )
        return 5

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

    # Last gate before the write: prove on the rendered text that no
    # protected net moved. Nothing above should be able to move one; this
    # is what makes "narrower refusal" a narrowing rather than a loosening.
    try:
        _verify_protected_unchanged(text, new_text)
    except SyncError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 5

    args.kicad_pro.write_text(new_text, encoding="utf-8")
    print(f"\nWROTE {args.kicad_pro}: {len(missing)} added, {len(mismatched)} corrected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
