#!/usr/bin/env python3
"""Fail when `initial_rotation_quadrant` is used as if it were already degrees.

WHY THIS EXISTS
---------------
`Component.initial_rotation_quadrant` (renamed 2026-08-13 from
`initial_rotation`) is a quarter-turn INDEX: 0-3 -> 0/90/180/270 degrees. It
is not a degree value, and its plain `int`/`i64` type does not stop anyone
from treating it as one.

That exact confusion produced three independent wrong safety-geometry
answers in this repo in a single day (2026-08-11): a CP-SAT pinned-footprint
`/ 90` that silently zeroed every non-zero rotation, a clearance
miscomputation of ~6.6mm on a real capacitor pair, and a placement candidate
DRC later refuted with 10 overlapping courtyards. Auditing this field's read
sites for the rename that motivated this gate found a fourth, live instance:
`router_v6/_pipeline_verify.py` passed the raw 0-3 index straight through as
a `rotation` field consumed everywhere else in DEGREES, with no `* 90` at
all (fixed in the same change that added this gate).

Renaming the field to `initial_rotation_quadrant` and adding
`core/netlist.py`'s `rotation_quadrant_to_degrees` / `_to_radians` helpers
makes the correct spelling available and the unit legible to a reader. It
does not stop new code from writing the wrong arithmetic anyway -- Python
does not care that `comp.initial_rotation_quadrant / 90` is nonsensical. This
gate is the enforcement half: a static, textual scan for the shapes that are
never correct for this field, run over every `.py` and `.rs` file in the
tree (except this file's own test fixtures, which construct bad patterns
only inside temporary files, and `docs/evidence/`, which is a frozen
historical record this gate does not police -- see AGENTS.md's "make regen"
section on why evidence files are not maintained code).

THE RULES
---------
1. `initial_rotation_quadrant` (optionally through `getattr(..., "...")`)
   must never be the left operand of `/`. Division by anything is never a
   correct operation on a 0-3 index in this codebase -- every correct
   conversion either multiplies by 90 (degrees) or by `pi / 2` (radians), or
   takes it `% 4` to normalize an out-of-range stored value. A `/` next to
   this name is the exact PR #1144 shape (`_rot_idx / 90`).
2. `math.radians(...)` / `np.radians(...)` / `numpy.radians(...)` must never
   be called directly on an expression containing `initial_rotation_quadrant`
   with no `* 90` in between -- `radians()` expects a DEGREE argument, and
   the raw index is 100x too small (`radians(1)` is ~0.017 rad, not the
   correct `pi/2`).
3. `.to_radians()` must never be called directly on
   `initial_rotation_quadrant` (through `as f64` / `.unwrap()` /
   `.unwrap_or(N)` only) with no `* 90.0` in between -- the Rust mirror of
   rule 2.

Correct usage (multiplying by 90, by `pi / 2`, calling
`rotation_quadrant_to_degrees`/`_to_radians`/`RotationQuadrant::to_degrees`/
`_to_radians`, or comparing/normalizing with `% 4`) is unaffected -- none of
those patterns match any rule above.

USAGE
    uv run python scripts/check_rotation_quadrant_arithmetic.py

EXIT CODES
    0  no footgun-shaped usage found
    1  at least one violation found (printed with file:line)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

FIELD = "initial_rotation_quadrant"

# Rule 1: the field immediately followed by `/`, with an optional
# `getattr(comp, "initial_rotation_quadrant", ...)` wrapper collapsed first.
_GETATTR_RE = re.compile(
    r'getattr\(\s*[\w\.]+\s*,\s*["\']' + re.escape(FIELD) + r'["\']\s*(?:,[^)]*)?\)'
)
# The divisor must be a NUMBER (90, 180, 360, ...) -- the real defect this
# rule targets always divides the index by a magic constant to (wrongly)
# "convert" it. Requiring a digit after the `/` is what keeps this rule from
# firing on prose like "initial_position / initial_rotation_quadrant /
# initial_side" (a slash-separated list of attribute names, not division),
# which real docstrings elsewhere in this tree use.
#
# The field and the `/` need not be perfectly adjacent -- `float(getattr(
# comp, "initial_rotation_quadrant", 0) or 0) / 90` is the same defect as a
# bare `x / 90` -- but the allowed gap is deliberately a SHORT, code-shaped
# set (an `or <default>` idiom and/or one closing paren), not "any
# character up to the next slash": this codebase's own rotation docstrings
# routinely spell out the four angles as `0/90/180/270`, and a wildcard gap
# matched straight through prose like "quarter-turn INDEX (0-3 ->
# 0/90/180/" (a real line in this very module) before this was narrowed.
_DIVISION_RE = re.compile(
    re.escape(FIELD) + r"\b(?:\s*or\s*[\d.]+)?\s*\)?\s*/\s*(?=\d)"
)

# Rule 2: math.radians(...)/np.radians(...)/numpy.radians(...) called
# directly on an expression that contains the bare field name with no `*`
# (multiplication) appearing between the opening paren and the field.
_RADIANS_CALL_RE = re.compile(
    r"(?:math|np|numpy)\.radians\(\s*([^()]*" + re.escape(FIELD) + r"[^()]*)\)"
)

# Rule 3: `<field>(.unwrap()|.unwrap_or(N)| as f64)* .to_radians()` in Rust,
# possibly parenthesized (`(x as f64).to_radians()`), with no `*` anywhere
# in between.
_TO_RADIANS_DIRECT_RE = re.compile(
    re.escape(FIELD)
    + r"\b(?:\s*(?:as\s+f64|\.unwrap\(\)|\.unwrap_or\(\s*-?\d+\s*\)))*\s*\)?\s*\.to_radians\(\)"
)

SKIP_DIR_PARTS = {"target", "target-shared", ".venv", "node_modules"}

# This gate's own module docstring and its test file discuss the footgun
# shapes in prose, and the test file builds bad-pattern fixtures at runtime
# (in tmp_path) rather than as literal scannable source. Both are excluded
# from self-scanning as a belt-and-suspenders measure on top of the
# digit-after-slash tightening above.
_SELF_EXCLUDE = {
    "scripts/check_rotation_quadrant_arithmetic.py",
    "scripts/tests/test_check_rotation_quadrant_arithmetic.py",
}


def _iter_source_files() -> list[Path]:
    out: list[Path] = []
    for pattern in ("**/*.py", "**/*.rs"):
        for p in REPO_ROOT.glob(pattern):
            parts = set(p.parts)
            if parts & SKIP_DIR_PARTS:
                continue
            rel = str(p.relative_to(REPO_ROOT))
            if "docs/evidence" in rel or rel in _SELF_EXCLUDE:
                continue
            out.append(p)
    return out


class Violation:
    __slots__ = ("path", "lineno", "line", "rule")

    def __init__(self, path: Path, lineno: int, line: str, rule: str) -> None:
        self.path = path
        self.lineno = lineno
        self.line = line
        self.rule = rule

    def __str__(self) -> str:
        rel = self.path.relative_to(REPO_ROOT) if self.path.is_absolute() else self.path
        return f"{rel}:{self.lineno}: [{self.rule}] {self.line.strip()}"


def scan_text(path: Path, text: str) -> list[Violation]:
    violations: list[Violation] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if FIELD not in line:
            continue
        # Collapse `getattr(x, "initial_rotation_quadrant", default)` down to
        # the bare field name so rule 1 sees the same shape whether the
        # field was read via attribute access or getattr().
        collapsed = _GETATTR_RE.sub(FIELD, line)
        if _DIVISION_RE.search(collapsed):
            violations.append(Violation(path, lineno, line, "division"))
        m = _RADIANS_CALL_RE.search(collapsed)
        if m and "*" not in m.group(1):
            violations.append(Violation(path, lineno, line, "radians-without-x90"))
        if _TO_RADIANS_DIRECT_RE.search(collapsed):
            violations.append(Violation(path, lineno, line, "to_radians-without-x90"))
    return violations


def scan(root: Path | None = None) -> list[Violation]:
    base = root if root is not None else REPO_ROOT
    files = _iter_source_files() if root is None else [
        p for pattern in ("**/*.py", "**/*.rs") for p in base.glob(pattern)
    ]
    violations: list[Violation] = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        violations.extend(scan_text(p, text))
    return violations


def main() -> int:
    violations = scan()
    if not violations:
        print("check_rotation_quadrant_arithmetic: OK -- no footgun-shaped usage found")
        return 0
    print(
        f"check_rotation_quadrant_arithmetic: {len(violations)} violation(s) -- "
        "'initial_rotation_quadrant' is a 0-3 quarter-turn INDEX, not degrees.\n"
        "Use core/netlist.py's rotation_quadrant_to_degrees()/_to_radians(), or "
        "temper_geometry::rotation_quadrant::RotationQuadrant in Rust.\n",
        file=sys.stderr,
    )
    for v in violations:
        print(str(v), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
