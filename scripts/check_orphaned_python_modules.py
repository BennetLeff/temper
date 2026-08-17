#!/usr/bin/env python3
"""Fail when a production Python module has zero importers anywhere.

WHY THIS EXISTS
----------------
`scripts/check_unwired_kernels.py` catches a Rust kernel that is registered
into a Python module but never called from Python -- the Rust-migrated-but-
never-wired direction. `scripts/vulture_gate.py` catches unused names *within*
a file that is otherwise imported. Neither catches the third shape this repo
keeps producing: a WHOLE Python module that nothing imports at all -- a
pure-delegation shim whose last caller was deleted, a spike that was never
wired in, a superseded duplicate. `docs/evidence/2026-08-17-python-deprecation-
spike.md` (PR #1302) found dozens of these by hand, one directory tree at a
time; this gate is the mechanized, shrink-only version of that sweep so the
next one does not have to be redone by hand and does not silently regrow.

METHOD -- and its limits
-------------------------
A module M (a `.py` file, not `__init__.py`) is REFERENCED if either:

  1. Some OTHER Python file under packages/, scripts/, or tools/ contains an
     `import`/`from ... import ...` statement (absolute OR relative -- both
     spellings are resolved to M's dotted path, see `resolve_import`) that
     names M, OR a string-literal argument to `importlib.import_module` /
     `importlib.reload` / `pkgutil` equal to M's dotted path.
  2. Some `.rs` file under packages/*/src registers a runtime cross-extension
     call that names M's dotted path -- `py.import("M")`,
     `PyModule::import(py, "M")`, or `.import_bound(py, "M")` -- invisible to
     a Python-only scan by construction (this is `check_unwired_kernels.py`'s
     documented blind spot in the OPPOSITE direction: there, Rust kernels are
     invisible to Python liveness scans; here, Python modules are invisible to
     Python-only liveness scans because only Rust calls them).
  3. M is named in `[project.scripts]` of any `pyproject.toml` (a console-
     script entry point -- the process boundary, not an import).

Reference counting does NOT distinguish production from test callers at the
file-import level the way `check_unwired_kernels.py` does for kernel symbols,
because a module that is imported ONLY by its own tests is a different,
narrower finding (differential/fixture-only, like `io/footprint_library.py`
in PR #1302) than one with zero importers anywhere -- this gate reports both,
tagged separately, and only the zero-importers-anywhere set is a hard failure.

KNOWN BLIND SPOTS (state them; do not pretend this is exhaustive):
  - A module reachable only via `getattr(pkg, "module_name")` dynamic lookup
    with a computed (non-literal) string is invisible to this scan, exactly
    like `check_unwired_kernels.py`'s documented getattr-with-a-name-arg case.
  - A module imported only inside a `try/except ImportError` optional-plugin
    block is counted as referenced (the import statement is there); whether
    that branch is ever reachable is not evaluated.
  - This does not attempt call-graph reachability from a real entry point --
    only "is it imported by name from somewhere," the same granularity
    `check_unwired_kernels.py` uses for Rust kernels.
  - A CLOSED CLUSTER of mutually-referencing dead modules is invisible to
    this gate by construction: if dead module A imports dead module B and
    nothing outside the cluster imports either, both look "referenced." This
    is a real, confirmed instance in this repo -- `router_v6/constraints_drc_
    oracle.py` + `constraints_design_rules.py` + `constraints_spatial_index.py`
    (~1,984 LOC, docs/evidence/2026-08-17-python-deprecation-spike.md) --
    caught by hand-tracing, not by this gate. This gate catches the far more
    common shape (a shim or spike whose single external caller was deleted),
    not a whole dead subgraph. Do not read "0 orphaned" as "0 dead code."

THE RATCHET
-----------
Shrink-only ledger, same shape as `.unwired-kernel-inventory`:

    NEW_ORPHANED   a module with zero references anywhere, not in the ledger.
                   Hard fail. Either wire it, delete it, or ledger it with a
                   reason (e.g. a deliberate plugin/future-phase module).
    STALE_ENTRY    a ledgered module that IS now referenced. Hard fail --
                   paid-down debt that stays on the books hides the next
                   regression. Rerun with --write-inventory.

USAGE
    uv run python scripts/check_orphaned_python_modules.py
    uv run python scripts/check_orphaned_python_modules.py --write-inventory

EXIT CODES
    0  every production module is referenced, or ledgered with a reason
    1  a new orphaned module, or a stale ledger entry
    2  the scan itself failed (no modules found, unreadable tree)
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INVENTORY = REPO_ROOT / ".orphaned-python-module-inventory"

# Excluded from the CANDIDATE set entirely (not "referenced" -- structurally
# not the kind of file this gate is about).
EXCLUDED_NAME_PATTERNS = (
    "__init__.py",
    "__main__.py",
    "conftest.py",
)

RUST_PY_IMPORT = re.compile(
    r'(?:py\.import|PyModule::import(?:_bound)?\(py,?)\s*\(\s*"([A-Za-z_][A-Za-z0-9_.]*)"'
)


def is_candidate(path: Path) -> bool:
    name = path.name
    if name in EXCLUDED_NAME_PATTERNS:
        return False
    if "_py_oracle" in name:
        return False
    return True


def module_dotted_path(path: Path, src_root: Path) -> str:
    """`.../src/temper_placer/router_v6/foo.py` -> `temper_placer.router_v6.foo`."""
    rel = path.relative_to(src_root).with_suffix("")
    return ".".join(rel.parts)


def package_dotted_path(path: Path, src_root: Path) -> str:
    """`__package__` for `path` -- the dotted name of its CONTAINING directory.

    True for both a regular module (`__package__` is its parent package) and
    an `__init__.py` (`__package__` is the package itself, which is also the
    directory containing the file) -- no special-casing needed.
    """
    rel = path.parent.relative_to(src_root)
    return ".".join(rel.parts)


def src_roots() -> list[Path]:
    return sorted(p for p in REPO_ROOT.glob("packages/*/src") if p.is_dir())


def all_python_files() -> list[Path]:
    """Every .py file worth scanning FOR references (production + tests)."""
    out: list[Path] = []
    for root_name in ("packages", "scripts", "tools"):
        base = REPO_ROOT / root_name
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            p = str(py)
            if "/.venv/" in p or "/target/" in p:
                continue
            out.append(py)
    return out


def candidate_modules() -> dict[str, Path]:
    """dotted module path -> file, for every production module this gate watches."""
    out: dict[str, Path] = {}
    for src_root in src_roots():
        for py in src_root.rglob("*.py"):
            if not is_candidate(py):
                continue
            out[module_dotted_path(py, src_root)] = py
    return out


def resolve_relative(pkg: str, level: int, module: str | None) -> str:
    """Mirror CPython's `importlib._bootstrap._resolve_name`.

    `pkg` is the importing file's `__package__`. `level` is the ImportFrom
    node's dot count. `module` is the part after the dots (may be None for
    `from . import x`).
    """
    bits = pkg.split(".")
    trim = level - 1
    bits = bits[: len(bits) - trim] if trim > 0 else bits
    base = ".".join(bits)
    return f"{base}.{module}" if module else base


def imports_in_file(path: Path) -> tuple[set[str], bool]:
    """Absolute dotted module paths this file's imports resolve to, and whether it parsed."""
    referenced: set[str] = set()
    try:
        src = path.read_text()
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return referenced, False

    src_root = next((r for r in src_roots() if _is_relative_to(path, r)), None)
    pkg = package_dotted_path(path, src_root) if src_root else ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                referenced.add(alias.name)
                # Also credit every parent prefix so `import a.b.c` counts as
                # referencing `a.b` and `a` too (rarely the discriminating
                # case here since we only key on LEAF modules, but harmless).
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                resolved = resolve_relative(pkg, node.level, node.module)
            else:
                resolved = node.module or ""
            if resolved:
                referenced.add(resolved)
                for alias in node.names:
                    if alias.name != "*":
                        referenced.add(f"{resolved}.{alias.name}")
        elif isinstance(node, ast.Call):
            func = node.func
            fname = func.attr if isinstance(func, ast.Attribute) else (
                func.id if isinstance(func, ast.Name) else None)
            if fname in ("import_module", "reload", "find_loader", "find_spec"):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        referenced.add(arg.value)
    return referenced, True


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def rust_references() -> set[str]:
    referenced: set[str] = set()
    for rs in REPO_ROOT.glob("packages/*/src/**/*.rs"):
        if "/target" in str(rs):
            continue
        try:
            text = rs.read_text()
        except OSError:
            continue
        for m in RUST_PY_IMPORT.finditer(text):
            referenced.add(m.group(1))
    return referenced


def console_script_targets() -> set[str]:
    referenced: set[str] = set()
    for toml_path in REPO_ROOT.glob("packages/*/pyproject.toml"):
        try:
            data = tomllib.loads(toml_path.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            continue
        scripts = data.get("project", {}).get("scripts", {})
        for target in scripts.values():
            mod = target.split(":", 1)[0]
            referenced.add(mod)


    return referenced


def load_inventory() -> dict[str, str]:
    if not INVENTORY.exists():
        return {}
    entries: dict[str, str] = {}
    for line in INVENTORY.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        mod, _, reason = line.partition("\t")
        entries[mod.strip()] = reason.strip()
    return entries


def write_inventory(orphaned: dict[str, str], previous: dict[str, str]) -> None:
    lines = [
        "# Production Python modules with zero importers anywhere.",
        "#",
        "# Shrink-only. A new entry is a hard failure -- wire the module, delete",
        "# it, or add it here WITH A REASON. An entry that becomes referenced is",
        "# also a failure, so paid-down debt shows up in a diff instead of",
        "# rotting on the books.",
        "#",
        "# Generated by scripts/check_orphaned_python_modules.py --write-inventory",
        "# <dotted.module.path>\\t<reason>",
        "",
    ]
    for mod in sorted(orphaned):
        reason = previous.get(mod, "").strip() or "orphaned at time of recording; no reason given"
        lines.append(f"{mod}\t{reason}")
    INVENTORY.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write-inventory", action="store_true",
                     help="record the current orphaned set (shrink-only ledger)")
    args = ap.parse_args()

    modules = candidate_modules()
    if not modules:
        print("FAIL: found zero candidate production modules -- the scan is "
              "broken, not the tree (a gate that inspects nothing passes "
              "vacuously).", file=sys.stderr)
        return 2

    all_referenced: set[str] = set()
    unparseable: list[str] = []
    for py in all_python_files():
        refs, ok = imports_in_file(py)
        all_referenced |= refs
        if not ok:
            unparseable.append(str(py.relative_to(REPO_ROOT)))
    all_referenced |= rust_references()
    all_referenced |= console_script_targets()

    if unparseable:
        print(f"WARN: {len(unparseable)} file(s) did not parse and were "
              f"skipped as an import SOURCE (they can still be a valid "
              f"import TARGET): {', '.join(unparseable[:5])}", file=sys.stderr)

    orphaned = {mod: str(path.relative_to(REPO_ROOT))
                for mod, path in modules.items() if mod not in all_referenced}

    ledger = load_inventory()

    if args.write_inventory:
        write_inventory(orphaned, ledger)
        print(f"wrote {INVENTORY.name}: {len(orphaned)} orphaned module(s) "
              f"of {len(modules)} candidate(s)")
        return 0

    new = sorted(set(orphaned) - set(ledger))
    stale = sorted(set(ledger) - set(orphaned))

    if not new and not stale:
        print(f"OK: {len(modules)} candidate module(s); "
              f"{len(orphaned)} orphaned, all ledgered.")
        return 0

    print("FAIL: orphaned-python-module gate\n")
    for mod in new:
        print(f"NEW_ORPHANED   {mod}  ({orphaned[mod]})")
        print("               zero importers found (Python or Rust py.import).")
    for mod in stale:
        print(f"STALE_ENTRY    {mod} is now referenced -- record the fix")
    print()
    if new:
        print("A module with zero importers anywhere is dead weight or a "
              "silent regression (its last caller was deleted without "
              "deleting it). Delete the module, wire a real caller, or add "
              "it to the ledger with a reason (e.g. a deliberately staged "
              "future-phase module).")
    if stale:
        print("STALE_ENTRY means the module was wired back up (or deleted and "
              "the ledger not updated): rerun with --write-inventory and "
              "commit the result.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
