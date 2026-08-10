#!/usr/bin/env python3
"""Migration-narrowing gate: detect a Rust port silently NARROWING a Python capability.

Background (2026-08-04 triage on ``docs/plans`` Wave 4): two confirmed defects
landed on ``main`` where a Rust port of a Python module quietly dropped a
degree of freedom the Python had, and neither the differential test suites
nor review caught it because the suites never generated the input that would
expose the gap:

1. ``H_CONV_BACKGROUND`` (``packages/temper-placer/src/temper_placer/physics/
   heat_removal.py``) is a module-level constant that Python passes into its
   arithmetic implicitly (it's just a name in scope). The Rust port
   (``packages/temper-thermal/src/heat_removal.rs``) turned it into
   ``pub const H_CONV_BACKGROUND: f64 = 10.0;`` and the Python call site
   never threaded it through to ``_tt.build_h_field_py(...)`` — the name
   still exists in Python, but it no longer reaches the computation. The
   constant became silently unconfigurable. Caught only by
   ``tests/validation/test_dead_parameter_probe.py``, which perturbs the
   attribute and observes no effect.

2. ``rotation`` (``packages/temper-geometry/src/escape_via.rs``) was
   extracted from the pyo3 boundary as ``Option<i64>``, but the Python it
   mirrors (``_normalize_rotation`` in ``packages/temper-placer/src/
   temper_placer/core/pin_geometry.py``) accepts ``int | float | None`` and
   does ``float(rotation)``. Fractional rotations raised ``TypeError``
   instead of producing an angle.

Neither shape is visible to a differential suite: the suite compares Rust
against the pinned Python oracle *on the inputs the suite generates*, and
neither generated a perturbed constant or a fractional rotation.

This gate performs two static checks, heuristic by design (see "False
positives" below):

  CHECK A (const-ification): a ``pub const``/``pub static`` NAME in
  ``packages/*/src/**/*.rs`` that also exists as a module-level constant in
  some ``packages/temper-placer/src/**/*.py`` file which imports that
  crate's compiled extension and calls into it, but never passes NAME as an
  argument to that call.

  CHECK B (numeric narrowing at the pyo3 boundary): a
  ``let NAME: (Option<)?(i64|i32|u32|usize)(>)? = <expr>.extract(...)``
  binding in ``packages/*/src/**/*.rs``, where a Python file under
  ``packages/temper-placer/src/**/*.py`` has a same-named (or
  ``initial_``-prefixed) field/parameter whose type annotation admits
  ``float`` or which is passed through ``float(...)``.

False positives: both checks are intentionally coarse — name-matching
heuristics over syntax, not a real cross-language type system. A NAME that
happens to collide across an unrelated Rust const and Python constant, or a
Rust field name that happens to match an unrelated Python float field, will
be flagged. That is by design (a static gate for this defect class cannot be
both sound and complete cheaply); false positives are suppressed via the
allowlist file (``.migration-narrowing-allowlist``), where every entry
requires a written reason. Do NOT allowlist a genuine capability narrowing —
the allowlist is for coincidental name collisions only.

KNOWN LIMITATION — CHECK A IS NOT WIREABLE AS A BLOCKING GATE YET.
CHECK A cannot distinguish the defect it is looking for (a Python constant
that production still reads, which the Rust port silently hardcoded — the
``H_CONV_BACKGROUND`` shape) from a **retained differential oracle** (a
pre-migration constant deliberately kept, unused in production, as the
in-repo statement of the rule the Rust reproduces). The latter is not a
defect: ``docs/migration-pipeline.md`` stage 3 *requires* every migration to
pin the pre-migration implementation as an oracle, so a correctly executed
migration produces exactly this shape on purpose. Both look identical to a
name-matching scan — a Rust ``pub const`` and a same-named Python module
constant that is not threaded through the delegate call.

Measured on the 2026-08-10 tree, all 8 CHECK A findings were retained
oracles, not defects — the 7 pattern sets in
``router_v6/net_classification.py`` (whose own module docstring says the
constants are "retained, unchanged and unused in production ... pinned
oracle for test_net_classification_rust_differential.py") plus
``CONTACT_TOLERANCE_MM`` in ``router_v6/connectivity.py``. Because the
migration process mandates the oracle pattern, CHECK A's false-positive
rate GROWS with every completed migration, which is backwards for a gate
meant to protect the migration.

The fix is production-reachability analysis: report a constant only when it
is reachable from a production code path, not merely defined in a module
whose functions delegate to Rust. ``scripts/check_unwired_kernels.py``
already does AST-based production-vs-test caller analysis for the unwired-
kernel ledger and is the machinery to reuse. Until that lands, run CHECK A
manually and read its output as a worklist, not a verdict; only CHECK B is
precise enough to gate on.

Exit codes:
  0 - OK (no new findings outside the allowlist, no stale allowlist entries)
  3 - New finding(s) not covered by the allowlist
  4 - Stale allowlist entr(y/ies) (no longer reproduced by a real run)
  5 - Internal/usage error (bad allowlist file, bad args, parse failure)

Usage:
  uv run python scripts/check_migration_narrowing.py
  uv run python scripts/check_migration_narrowing.py --init
  uv run python scripts/check_migration_narrowing.py --help
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.repo import find_repo_root
from _lib.github_summary import get_github_summary_path

REPO_ROOT = find_repo_root()
ALLOWLIST_PATH = REPO_ROOT / ".migration-narrowing-allowlist"

PLACER_PY_GLOB = "packages/temper-placer/src/**/*.py"
ALL_RUST_GLOB = "packages/*/src/**/*.rs"

NARROW_TYPES = ("i64", "i32", "u32", "usize")

# --- Check A regexes ---------------------------------------------------
RUST_CONST_RE = re.compile(
    r"^\s*pub\s+(?:const|static)\s+(?:ref\s+)?([A-Z_][A-Z0-9_]*)\s*:"
)

# --- Check B regexes -----------------------------------------------------
_NARROW_ALT = "|".join(NARROW_TYPES)
RUST_EXTRACT_TYPED_RE = re.compile(
    r"^\s*let\s+(?:mut\s+)?([a-z_][a-z0-9_]*)\s*:\s*"
    r"(Option\s*<\s*(?:" + _NARROW_ALT + r")\s*>|(?:" + _NARROW_ALT + r"))\s*=\s*"
    r".*\.extract(?:::<[^>]+>)?\(\s*\)"
)
RUST_EXTRACT_TURBOFISH_RE = re.compile(
    r"^\s*let\s+(?:mut\s+)?([a-z_][a-z0-9_]*)\s*=\s*"
    r".*\.extract::<\s*(?:Option\s*<\s*(?:" + _NARROW_ALT + r")\s*>|(?:" + _NARROW_ALT + r"))\s*>\(\s*\)"
)

PY_FLOAT_ANNOTATION_RE_TMPL = r"\b{name}\s*:\s*[^=\n,)]{{0,60}}\bfloat\b"
PY_FLOAT_CALL_RE_TMPL = r"\bfloat\(\s*(?:\w+\.)*{name}\s*\)"


@dataclass(frozen=True)
class RustConst:
    name: str
    rust_file: str  # repo-relative
    rust_line: int
    python_module: str  # e.g. "temper_thermal"


@dataclass(frozen=True)
class RustExtract:
    name: str
    narrow_type: str
    rust_file: str
    rust_line: int


@dataclass(frozen=True)
class FindingA:
    name: str
    rust_file: str
    rust_line: int
    python_file: str
    python_line: int

    def key(self) -> tuple[str, str, str, str]:
        return ("CHECK_A", self.rust_file, self.name, self.python_file)


@dataclass(frozen=True)
class FindingB:
    name: str
    narrow_type: str
    rust_file: str
    rust_line: int
    python_file: str
    python_line: int
    matched_variant: str

    def key(self) -> tuple[str, str, str, str]:
        return ("CHECK_B", self.rust_file, self.name, self.python_file)


def _crate_python_module(rust_file: Path, root: Path) -> str | None:
    """Map ``packages/<crate>/src/...`` to its pyo3 python import name."""
    try:
        rel = rust_file.relative_to(root)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) < 2 or parts[0] != "packages":
        return None
    return parts[1].replace("-", "_")


def find_rust_pub_constants(root: Path) -> list[RustConst]:
    results: list[RustConst] = []
    for rs in sorted(root.glob(ALL_RUST_GLOB)):
        module = _crate_python_module(rs, root)
        if module is None:
            continue
        try:
            text = rs.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(rs.relative_to(root))
        for lineno, line in enumerate(text.splitlines(), 1):
            m = RUST_CONST_RE.match(line)
            if m:
                results.append(RustConst(m.group(1), rel, lineno, module))
    return results


# Check B pairs a Rust binding name with a same-named Python identifier by
# scanning every placer `.py` line. Below a few characters that pairing
# carries no cross-language identity: a one- or two-letter binding collides
# with some comprehension's loop variable in essentially every file. Measured
# on the 2026-08-10 tree, every sub-3-character binding was a false positive —
# `let v: i64` in both `drc_oracle_marshal.rs:189` (a generic
# `get_attr_opt_i64` helper) and `pcl_contracts.rs:396` (an enum's `.value`)
# matched the `v` of `[float(v) for v in board_bounds]` in
# `constraints/_payload.py:59`, an unrelated file in an unrelated crate.
# The defect class this check exists for is always a NAMED field crossing the
# boundary (`rotation`, `initial_rotation`), never a one-letter binding, so
# the guard costs no real detection.
MIN_CHECK_B_NAME_LEN = 3


def find_rust_narrow_extracts(root: Path) -> list[RustExtract]:
    results: list[RustExtract] = []
    for rs in sorted(root.glob(ALL_RUST_GLOB)):
        try:
            text = rs.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(rs.relative_to(root))
        for lineno, line in enumerate(text.splitlines(), 1):
            m = RUST_EXTRACT_TYPED_RE.match(line)
            if m:
                if len(m.group(1)) < MIN_CHECK_B_NAME_LEN:
                    continue
                narrow_type = m.group(2).replace(" ", "")
                results.append(RustExtract(m.group(1), narrow_type, rel, lineno))
                continue
            m = RUST_EXTRACT_TURBOFISH_RE.match(line)
            if m:
                if len(m.group(1)) < MIN_CHECK_B_NAME_LEN:
                    continue
                # narrow type isn't captured by group here beyond presence;
                # recover it from the turbofish text itself.
                tf = re.search(r"extract::<\s*([^>]*(?:<[^>]*>)?[^>]*)>", line)
                narrow_type = tf.group(1).replace(" ", "") if tf else "unknown"
                results.append(RustExtract(m.group(1), narrow_type, rel, lineno))
    return results


class _PyModuleInfo:
    """AST-derived facts about one Python file, used by Check A."""

    def __init__(self) -> None:
        self.module_consts: dict[str, int] = {}  # NAME -> lineno
        # calls: list of (source_module, arg_names, lineno)
        self.delegate_calls: list[tuple[str, set[str], int]] = []


def _collect_arg_names(call: ast.Call) -> set[str]:
    names: set[str] = set()
    for arg in list(call.args) + [kw.value for kw in call.keywords]:
        for node in ast.walk(arg):
            if isinstance(node, ast.Name):
                names.add(node.id)
    return names


def analyze_python_file(path: Path) -> _PyModuleInfo | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return None

    info = _PyModuleInfo()

    # imports: local-name -> module string
    imports: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name
                imports[local] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                local = alias.asname or alias.name
                imports[local] = node.module

    # module-level SCREAMING_SNAKE_CASE constants
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Name) and t.id.isupper() and t.id not in info.module_consts:
                info.module_consts[t.id] = node.lineno

    # calls that delegate to an imported module (attribute-style or
    # direct name imported via `from module import name`)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        source_module: str | None = None
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            source_module = imports.get(node.func.value.id)
        elif isinstance(node.func, ast.Name):
            source_module = imports.get(node.func.id)
        if source_module is None:
            continue
        info.delegate_calls.append((source_module, _collect_arg_names(node), node.lineno))

    return info


def check_a(root: Path) -> list[FindingA]:
    consts = find_rust_pub_constants(root)
    if not consts:
        return []

    py_files = sorted(root.glob(PLACER_PY_GLOB))
    py_cache: dict[Path, _PyModuleInfo | None] = {}

    def get_info(p: Path) -> _PyModuleInfo | None:
        if p not in py_cache:
            py_cache[p] = analyze_python_file(p)
        return py_cache[p]

    findings: list[FindingA] = []
    for const in consts:
        for py_file in py_files:
            info = get_info(py_file)
            if info is None or const.name not in info.module_consts:
                continue
            delegate_calls = [
                c for c in info.delegate_calls if c[0] == const.python_module
            ]
            if not delegate_calls:
                continue
            if any(const.name in arg_names for _, arg_names, _ in delegate_calls):
                continue
            findings.append(
                FindingA(
                    name=const.name,
                    rust_file=const.rust_file,
                    rust_line=const.rust_line,
                    python_file=str(py_file.relative_to(root)),
                    python_line=info.module_consts[const.name],
                )
            )
    return findings


def _name_variants(name: str) -> list[str]:
    variants = [name]
    if not name.startswith("initial_"):
        variants.append(f"initial_{name}")
    return variants


def check_b(root: Path) -> list[FindingB]:
    extracts = find_rust_narrow_extracts(root)
    if not extracts:
        return []

    py_files = sorted(root.glob(PLACER_PY_GLOB))
    py_texts: dict[Path, str] = {}
    for p in py_files:
        try:
            py_texts[p] = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

    findings: list[FindingB] = []
    for ex in extracts:
        for variant in _name_variants(ex.name):
            ann_re = re.compile(PY_FLOAT_ANNOTATION_RE_TMPL.format(name=re.escape(variant)))
            call_re = re.compile(PY_FLOAT_CALL_RE_TMPL.format(name=re.escape(variant)))
            found_here = False
            for py_file, text in py_texts.items():
                for lineno, line in enumerate(text.splitlines(), 1):
                    if ann_re.search(line) or call_re.search(line):
                        findings.append(
                            FindingB(
                                name=ex.name,
                                narrow_type=ex.narrow_type,
                                rust_file=ex.rust_file,
                                rust_line=ex.rust_line,
                                python_file=str(py_file.relative_to(root)),
                                python_line=lineno,
                                matched_variant=variant,
                            )
                        )
                        found_here = True
                        break
                if found_here:
                    break
            if found_here:
                break  # one variant match is enough to report this extract once
    return findings


# --- Allowlist -------------------------------------------------------------

ALLOWLIST_LINE_RE = re.compile(
    r"^(CHECK_A|CHECK_B)\|([^|]+)\|([^|]+)\|([^|#]+?)\s*(?:#.*)?$"
)


def load_allowlist(path: Path) -> set[tuple[str, str, str, str]]:
    if not path.exists():
        return set()
    entries: set[tuple[str, str, str, str]] = set()
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = ALLOWLIST_LINE_RE.match(line)
        if not m:
            print(
                f"[MIGRATION-NARROWING-ERROR] Unparseable allowlist line "
                f"{path}:{lineno}: {raw}",
                file=sys.stderr,
            )
            sys.exit(5)
        check, rust_file, name, python_file = m.groups()
        entries.add((check, rust_file.strip(), name.strip(), python_file.strip()))
    return entries


def _format_a(f: FindingA) -> str:
    return (
        f"  {f.rust_file}:{f.rust_line} `{f.name}` (Rust pub const) <-> "
        f"{f.python_file}:{f.python_line} `{f.name}` (Python module constant, "
        f"not threaded through the delegate call)"
    )


def _format_b(f: FindingB) -> str:
    return (
        f"  {f.rust_file}:{f.rust_line} `let {f.name}: {f.narrow_type} = ...extract(...)` "
        f"<-> {f.python_file}:{f.python_line} (`{f.matched_variant}` admits float)"
    )


def _init_line_a(f: FindingA) -> str:
    return (
        f"CHECK_A|{f.rust_file}|{f.name}|{f.python_file}  "
        f"# reason: TODO-AUDIT seeded by --init on {f.rust_file}:{f.rust_line} / "
        f"{f.python_file}:{f.python_line} — confirm this is a coincidental name "
        f"collision, not a real narrowing, before keeping this entry."
    )


def _init_line_b(f: FindingB) -> str:
    return (
        f"CHECK_B|{f.rust_file}|{f.name}|{f.python_file}  "
        f"# reason: TODO-AUDIT seeded by --init on {f.rust_file}:{f.rust_line} / "
        f"{f.python_file}:{f.python_line} — confirm `{f.name}` in Rust and "
        f"`{f.matched_variant}` in Python are the same domain field before "
        f"keeping this entry."
    )


def run_init(root: Path, allowlist_path: Path) -> int:
    findings_a = check_a(root)
    findings_b = check_b(root)
    lines = [
        "# Migration-narrowing gate allowlist.",
        "#",
        "# Format: CHECK_A|<rust_file>|<NAME>|<python_file>  # reason: <why this",
        "# is a coincidental name collision, not a real capability narrowing>",
        "#",
        "# Every entry MUST carry a reason. Do NOT allowlist a genuine",
        "# capability-narrowing defect (a Rust port silently dropping a",
        "# parameter/precision the Python had) — that is the exact defect class",
        "# this gate exists to catch. See scripts/check_migration_narrowing.py",
        "# module docstring for the two confirmed historical instances.",
        "",
    ]
    for f in findings_a:
        lines.append(_init_line_a(f))
    for f in findings_b:
        lines.append(_init_line_b(f))
    allowlist_path.write_text("\n".join(lines) + "\n")
    print(
        f"[MIGRATION-NARROWING] Seeded {allowlist_path} with "
        f"{len(findings_a)} CHECK_A + {len(findings_b)} CHECK_B finding(s). "
        f"Review each TODO-AUDIT reason before committing — do not blindly "
        f"keep entries that are real defects."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migration-narrowing gate: detect a Rust port silently "
        "narrowing a Python capability (const-ification or numeric "
        "narrowing at the pyo3 boundary)."
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Regenerate the allowlist from a real run (review before committing).",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=ALLOWLIST_PATH,
        help="Path to the allowlist file (default: .migration-narrowing-allowlist)",
    )
    args = parser.parse_args()

    root = REPO_ROOT

    if args.init:
        return run_init(root, args.allowlist)

    allowlist = load_allowlist(args.allowlist)

    findings_a = check_a(root)
    findings_b = check_b(root)

    all_keys = {f.key() for f in findings_a} | {f.key() for f in findings_b}
    new_a = [f for f in findings_a if f.key() not in allowlist]
    new_b = [f for f in findings_b if f.key() not in allowlist]
    stale = sorted(allowlist - all_keys)

    exit_code = 0
    gh_summary_path = get_github_summary_path()
    gh_summary = open(gh_summary_path, "a") if gh_summary_path else None

    if stale:
        print(
            "=== STALE ALLOWLIST ENTRIES (no longer reproduced by a real run — "
            f"remove from {args.allowlist.name}) ==="
        )
        for check, rust_file, name, python_file in stale:
            print(f"  {check}|{rust_file}|{name}|{python_file}")
        print()
        exit_code = 4

    if new_a or new_b:
        print(
            "=== MIGRATION-NARROWING GATE: possible capability narrowing "
            "detected ==="
        )
        print(
            "A Rust port may have silently narrowed a capability the Python "
            "had (const-ified a configurable value, or narrowed a numeric "
            "type at the pyo3 boundary). If this is a REAL defect, fix the "
            "Rust port (thread the parameter through / widen the type) — do "
            "NOT allowlist it. If this is a coincidental name collision, add "
            f"an entry to {args.allowlist.name} with a written reason.\n"
        )
        if new_a:
            print("--- CHECK A: const-ification ---")
            for f in new_a:
                print(_format_a(f))
            print()
        if new_b:
            print("--- CHECK B: numeric narrowing at the pyo3 boundary ---")
            for f in new_b:
                print(_format_b(f))
            print()
        exit_code = 3

    if exit_code == 0:
        msg = (
            f"Migration-narrowing gate PASSED — "
            f"{len(findings_a) + len(findings_b)} known finding(s) allowlisted, "
            f"0 new, 0 stale"
        )
        print(msg)
        if gh_summary:
            gh_summary.write(f"### Migration-Narrowing Gate\n{msg}\n")
    else:
        bucket = "NEW findings" if (new_a or new_b) else "STALE allowlist entries"
        print(f"Migration-narrowing gate FAILED ({bucket})")
        if gh_summary:
            gh_summary.write("### Migration-Narrowing Gate :x:\n")
            gh_summary.write(f"**{bucket}**\n")

    if gh_summary:
        gh_summary.close()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
