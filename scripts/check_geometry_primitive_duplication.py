#!/usr/bin/env python3
"""Fail when a Rust crate carries its own body of a point-to-segment-distance-shaped kernel that isn't allowlisted with a reason.

WHY THIS EXISTS
---------------
2026-08-13 audit: `point_to_segment_distance` (a clamped point-to-segment
projection distance -- the primitive behind creepage/clearance measurement
on this mains-voltage board) had **5 independent Rust bodies**:

    temper-geometry/src/creepage_check.rs            degenerate: denom == 0.0 or !denom.is_finite()
    temper-geometry/src/geometry_kernels.rs           degenerate: len2 < 1e-12
    temper-geometry/src/drc_constraints_geometry.rs   degenerate: seg_len_sq < 1e-10
    temper-geometry/src/fixed_copper.rs               degenerate: dx == 0.0 and dy == 0.0 (function RENAMED to
                                                       `point_segment_distance` -- a plain name grep undercounts)
    temper-constraint-compiler/src/constraints/mod.rs degenerate: ab_len_sq == 0.0 (different final rounding: pow+sqrt, not hypot)

Four different epsilons for "is this segment degenerate" on the same
computation, one of them (creepage_check.rs) directly on the HV creepage
safety path. Measured divergence (see
`docs/evidence/2026-08-13-point-to-segment-distance-epsilon-consolidation.md`):
geometry_kernels.rs and drc_constraints_geometry.rs disagree with the
numerically-correct contract on ~20-24% of near-degenerate segments (not a
1-ulp rounding difference -- a real decision-boundary difference). No test
caught this because each copy is bit-pinned to its OWN Python oracle; a
differential proves internal consistency, not that the copy should exist.

This gate does not re-litigate which epsilon is correct (the evidence doc
does). It makes the NEXT accidental copy -- including a renamed one --
loud instead of silent.

WHAT COUNTS AS A COPY
----------------------
A Rust function is a point-to-segment-distance BODY (not a thin delegating
call) if it independently implements all three of:

  1. a squared-length / "is this segment degenerate" branch
     (`== 0.0`, `< 1e-N`, or `.is_finite()` guarding a length-like binding)
  2. a clamp of the projection parameter into [0, 1]
     (`py_min`/`py_max`, `.clamp(0.0, 1.0)`, or an explicit `min`/`max` pair
     against 0.0 and 1.0 literals)
  3. a final Euclidean close (`hypot`, `.sqrt()`, or `powf(_, 0.5)`)

Detection is structural (body shape), not name-based -- a function renamed
to dodge a `point_to_segment_distance` grep (as fixed_copper.rs's copy was)
still matches. A function that only CALLS a shared kernel (no local
degenerate/clamp/close arithmetic of its own) is a delegate, not a copy,
and is out of scope -- mirroring is the caller's job there, exactly as
`check_wire_format_fidelity.py` treats callers of a shared primitive.

ALLOWLIST
---------
`.geometry-primitive-duplication-allowlist` records every KNOWN copy with a
one-line reason (typically: "own pinned Python oracle, epsilon inherited
from a genuinely different pre-migration reference; see the evidence doc").
A copy not in the allowlist is NEW and fails the gate. An allowlist entry
whose function no longer matches the structural fingerprint (deleted, or
turned into a delegating call) is STALE and also fails the gate -- paid-down
duplication that stays on the books hides the next regression.

USAGE
    uv run python scripts/check_geometry_primitive_duplication.py
    uv run python scripts/check_geometry_primitive_duplication.py --write-allowlist

EXIT CODES
    0  every point-to-segment-distance-shaped body in the tree is allowlisted
    1  a new copy appeared, or an allowlist entry is stale
    2  the scan found no matches at all (broken scan, not a clean tree --
       creepage_check.rs's own canonical copy must always match)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = REPO_ROOT / ".geometry-primitive-duplication-allowlist"

# A candidate function start: `fn NAME(`. The parameter list and body are
# extracted by balanced-delimiter scanning below (NOT a single regex capture
# group) because several kernels in this repo take tuple-typed params like
# `p: (f64, f64)`, whose nested `)` breaks a naive `\(([^)]*)\)` capture.
FN_NAME = re.compile(r"\bfn\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")

TUPLE_PARAMS = re.compile(r"\(f64,\s*f64\)")

DEGENERATE = re.compile(
    r"(==\s*0\.0|<\s*1e-\d+|\.is_finite\(\))"
)
CLAMP = re.compile(
    r"py_min|py_max|\.clamp\(\s*0\.0\s*,\s*1\.0\s*\)|max\(\s*0\.0|min\(\s*1\.0"
)
CLOSE = re.compile(
    r"hypot|\.sqrt\(\)|powf\([^,]+,\s*0\.5\)|py_pow\([^,]+,\s*2\.0\)"
    # A Euclidean close via a same-crate helper call (`point_distance(...)`,
    # `euclidean_dist(...)`, `distance(...)`) counts too -- the degenerate
    # branch and the final-distance call frequently route through a shared
    # `_distance`/`_dist` helper rather than inlining hypot/sqrt directly.
    r"|\b[a-zA-Z_]*(?:distance|dist)\s*\("
)


def _extract_balanced(text: str, open_idx: int, open_ch: str, close_ch: str) -> tuple[str, int]:
    """Return (span INCLUDING both delimiters, index just past the closer),
    scanning from the opening delimiter at open_idx."""
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return text[open_idx : i + 1], i + 1
    return text[open_idx:], len(text)


def _looks_like_ptsd_signature(params: str) -> bool:
    # Strip attribute/type noise the split-by-comma heuristic below can't
    # parse (generic bounds, lifetimes) -- none of this repo's point-to-
    # segment kernels use them, so their absence is itself informative.
    if "<" in params or "&" in params:
        return False
    parts = [p.strip() for p in params.split(",") if p.strip()]
    tuple_shaped = len(TUPLE_PARAMS.findall(params)) >= 2
    if not parts:
        return tuple_shaped
    all_f64 = len(parts) >= 5 and all(p.endswith("f64") and "(" not in p for p in parts)
    return all_f64 or tuple_shaped


def _scan_text(text: str) -> list[tuple[str, str]]:
    """(function name, one-line evidence) for every structural match in `text`."""
    out: list[tuple[str, str]] = []
    for m in FN_NAME.finditer(text):
        name = m.group(1)
        open_paren = m.end() - 1
        params, after_params = _extract_balanced(text, open_paren, "(", ")")
        params = params[1:-1]  # strip the enclosing parens
        if not _looks_like_ptsd_signature(params):
            continue
        # Skip past an optional `-> f64` / `-> Rect` return-type arrow to the
        # function's opening `{`.
        tail = text[after_params : after_params + 200]
        brace_offset = tail.find("{")
        if brace_offset == -1:
            continue
        open_brace = after_params + brace_offset
        body, _ = _extract_balanced(text, open_brace, "{", "}")
        has_degenerate = bool(DEGENERATE.search(body))
        has_clamp = bool(CLAMP.search(body))
        has_close = bool(CLOSE.search(body))
        if has_degenerate and has_clamp and has_close:
            evidence = f"degenerate={has_degenerate} clamp={has_clamp} close={has_close}"
            out.append((name, evidence))
    return out


def scan(globs: list[str] | None = None) -> list[tuple[str, str, str]]:
    """(relative path, function name, one-line evidence) for every structural match."""
    out: list[tuple[str, str, str]] = []
    for pattern in globs or ["packages/*/src/**/*.rs"]:
        for rs in sorted(REPO_ROOT.glob(pattern)):
            if "/target" in str(rs) or "/target-shared" in str(rs):
                continue
            try:
                text = rs.read_text()
            except OSError:
                continue
            for name, evidence in _scan_text(text):
                out.append((str(rs.relative_to(REPO_ROOT)), name, evidence))
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
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--write-allowlist", action="store_true")
    ap.add_argument(
        "--extra-glob",
        action="append",
        default=[],
        help="additional glob(s) to scan, relative to repo root (test fixtures use this)",
    )
    args = ap.parse_args()

    results = scan()
    if args.extra_glob:
        results += scan(globs=args.extra_glob)

    if not results:
        print(
            "FAIL: found no point-to-segment-distance-shaped body in the tree -- "
            "the scan is broken, not the tree (creepage_check.rs's own canonical "
            "copy must always match; a gate that inspects nothing passes vacuously).",
            file=sys.stderr,
        )
        return 2

    found = {f"{path}::{name}": path for path, name, _ in results}
    allow = load_allowlist()

    if args.write_allowlist:
        lines = [
            "# Known Rust bodies matching the point-to-segment-distance structural",
            "# fingerprint (degenerate-length branch + [0,1] clamp + Euclidean close).",
            "# Each entry needs a REASON. A copy with its own pinned Python oracle,",
            "# genuinely mirroring a different pre-migration reference, is a",
            "# documented-KEEP; an unconsidered copy is the bug this gate exists to",
            "# catch. See docs/evidence/2026-08-13-point-to-segment-distance-epsilon-",
            "# consolidation.md for the epsilon table and the merits-based decision.",
            "#",
            "# <path>::<function>\\t<reason>",
            "",
        ]
        for key in sorted(found):
            lines.append(f"{key}\t{allow.get(key, '').strip() or 'recorded without a reason'}")
        ALLOWLIST.write_text("\n".join(lines) + "\n")
        print(f"wrote {ALLOWLIST.name}: {len(found)} entr(ies)")
        return 0

    new = sorted(set(found) - set(allow))
    stale = sorted(set(allow) - set(found))

    if not new and not stale:
        print(
            f"OK: {len(found)} point-to-segment-distance-shaped bod(ies) found; "
            f"every one is allowlisted with a reason."
        )
        return 0

    print("FAIL: geometry-primitive-duplication gate\n")
    for key in new:
        path, fn = key.rsplit("::", 1)
        print(f"NEW_COPY       {path}::{fn}")
        print(
            "               matches the point-to-segment-distance structural "
            "fingerprint (degenerate-length branch + [0,1] clamp + Euclidean "
            "close) and is not in the allowlist."
        )
        print(
            "               Either delegate to a shared kernel "
            "(temper_geometry::creepage_check::point_to_segment_distance is "
            "canonical -- see the evidence doc), or record this copy in "
            f"{ALLOWLIST.name} with a reason (own pinned oracle, genuinely "
            "different pre-migration reference, etc.)."
        )
    for key in stale:
        print(f"STALE_ENTRY    {key} no longer matches the fingerprint -- record the fix "
              f"(delete the entry with --write-allowlist)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
