#!/usr/bin/env python3
"""Fail when a Rust kernel is registered into a Python module but nothing in production calls it.

WHY THIS EXISTS
---------------
On 2026-08-06 an audit found **4,096 LOC across 15 router_v6 files** whose Rust
kernels were fully built, registered, and proven bit-equivalent against pinned
oracles -- and never called by anything except their own differential:

    congestion cluster   1,300 LOC   23/23 symbols   PR #751
    DFM cluster          1,597 LOC   13/13 symbols   PR #749
    quality metrics        598 LOC   23/23 symbols   PR #750
    escape_via + net_ordering  601 LOC              PR #751

Every one of those PRs was correct by the documented process. That is the
problem this gate closes: `docs/migration-pipeline.md` stage 3 and the
discipline contract's G1-G8 checklist both END at "the differential is green".
No gate asked whether the Python call site changed, so a migration could be
complete, verified, merged -- and inert. The Rust existed; the Python still ran.

A differential cannot catch this. It compares the pinned ORACLE against the
Rust directly and passes whether or not the shipped module delegates. That is
by design and is not a flaw in the differential; it just means the wiring needs
its own check.

WHAT COUNTS AS WIRED
--------------------
A symbol registered with `m.add_function(wrap_pyfunction!(NAME, m)?)?` or
`m.add_class::<NAME>()` exists to be called from Python. It is WIRED if any
NON-TEST Python file references it -- `packages/*/src/**`, `scripts/`, `tools/`.
Test files prove equivalence; they do not put a kernel into production.

Both import spellings count, and this matters: the one correctly wired module
found during the audit (`heuristics/structural.py`) uses a function-local
`from temper_geometry import keepout_mask_flags_py`, which a naive
`import temper_geometry` scan misses entirely.

THE RATCHET
-----------
Some kernels are legitimately unwired for a while -- Phase B lands the Rust,
the shim follows. So this is a shrink-only inventory, exactly like
`.hash-order-inventory`:

    NEW_UNWIRED    a registered symbol with no production caller that is not in
                   the ledger. Hard fail. Either wire it or record it with a
                   reason.
    STALE_ENTRY    a ledger entry that IS now wired. Also a hard fail, because
                   paid-down debt that stays on the books hides the next
                   regression. Rerun with --write-inventory.

Failing on STALE_ENTRY is deliberate: it is the only mechanism that makes
progress visible in a diff.

USAGE
    uv run python scripts/check_unwired_kernels.py
    uv run python scripts/check_unwired_kernels.py --write-inventory

EXIT CODES
    0  every registered kernel is wired, or ledgered with a reason
    1  a new unwired kernel, or a stale ledger entry
    2  the scan itself failed (no symbols found, unreadable tree)
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INVENTORY = REPO_ROOT / ".unwired-kernel-inventory"

# Registration forms that mean "callable from Python".
# Registration is frequently PATH-QUALIFIED -- `wrap_pyfunction!(fdm::solve_py, m)`.
# Capturing the first identifier yields the Rust MODULE (`fdm`), not the function,
# which is wrong twice over: it invents a symbol that can never be "wired" (a module
# is not callable from Python), and it silently drops the real one. Measured on
# 2026-08-06: 113 of 572 registered functions were path-qualified, so the gate was
# not watching them AT ALL, while 18 Rust module names sat in the ledger being
# triaged as if they were kernels. Consume the `::` segments and keep the last.
ADD_FUNCTION = re.compile(
    r"wrap_pyfunction!\(\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*::\s*)*([A-Za-z_][A-Za-z0-9_]*)")
ADD_CLASS = re.compile(
    r"add_class::<\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*::\s*)*([A-Za-z_][A-Za-z0-9_]*)")
# `#[pyo3(name = "...")]` renames the Python-visible symbol.
PYO3_NAME = re.compile(r'#\[pyo3\([^)]*name\s*=\s*"([^"]+)"')
PYCLASS_NAME = re.compile(r'#\[pyclass\([^)]*name\s*=\s*"([^"]+)"')


def registered_symbols() -> dict[str, str]:
    """Python-visible symbol -> the .rs file that registers it."""
    out: dict[str, str] = {}
    sources: list[tuple[str, str]] = []
    for rs in REPO_ROOT.glob("packages/*/src/**/*.rs"):
        if "/target" in str(rs):
            continue
        try:
            sources.append((str(rs.relative_to(REPO_ROOT)), rs.read_text()))
        except OSError:
            continue

    # Renames are resolved REPO-WIDE, not per file. A `#[pyclass(name = "X")]`
    # is routinely declared in one module and registered in another --
    # `PyDsnCircle` is `#[pyclass(name = "DSNCircle")]` in dsn_types.rs but
    # registered from lib.rs. A per-file map cannot see across that boundary,
    # so it reports the Rust name, which no Python caller ever writes, and the
    # kernel looks unwired however thoroughly it is used.
    renames: dict[str, str] = {}
    for _rel, text in sources:
        renames.update(pyclass_renames(text))

    for rel, text in sources:
        for m in ADD_FUNCTION.finditer(text):
            out.setdefault(m.group(1), rel)
        for m in ADD_CLASS.finditer(text):
            rust_name = m.group(1)
            # A `#[pyclass(name = "X")]` is visible to Python as X, NOT as the
            # Rust struct name -- e.g. `PyFabPreset` is `FabPreset` to callers,
            # and `core/manufacturing.py` imports it under that name. Scanning
            # for the Rust name would report a wired kernel as unwired.
            out.setdefault(renames.get(rust_name, rust_name), rel)
    return out


def registered_symbols_runtime() -> dict[str, str]:
    """AUDIT MODE: the symbols the built extensions actually export.

    `dir(module)` is the list Python callers really see, so it is immune to the
    ways a registered name diverges from its Python name -- path-qualified
    registration, `#[pyclass(name=...)]` declared in another file,
    `#[pyo3(name=...)]` on a function, and `use X as Y` aliases at the
    registration site. Every one of those has produced a wrong verdict here.

    It is NOT the default, and that is deliberate: it requires the extensions to
    be built, and the gate runs in trunk-health.yml under a bare `python3` with
    no venv. A ledger keyed to this view would report phantom STALE_ENTRYs in
    CI, which is a worse failure than the parser's -- noise that trains people
    to ignore the gate. Use it as a periodic audit:

        uv run --no-sync python scripts/check_unwired_kernels.py --runtime

    and reconcile anything it finds by hand.
    """
    import importlib
    import pkgutil

    out: dict[str, str] = {}
    for name in sorted({m.name for m in pkgutil.iter_modules() if m.name.startswith("temper_")}):
        mod = None
        try:
            mod = importlib.import_module(f"{name}.{name}")   # maturin layout
        except Exception:
            try:
                candidate = importlib.import_module(name)
                if str(getattr(candidate, "__file__", "")).endswith((".so", ".pyd")):
                    mod = candidate
            except Exception:
                mod = None
        if mod is None:
            continue          # pure-Python package: its names are not kernels
        for sym in dir(mod):
            if sym.startswith("_"):
                continue
            try:
                obj = getattr(mod, sym)
            except Exception:
                continue
            if callable(obj) or isinstance(obj, type):
                out.setdefault(sym, name)
    return out


def pyclass_renames(text: str) -> dict[str, str]:
    """Rust type name -> Python-visible name, for `#[pyclass(name = "...")]`.

    Attribute-to-item binding, not first-match-in-file: the attribute applies to
    the `struct`/`enum` that immediately follows it, so an unrelated rename
    earlier in the same module must not be picked up.
    """
    renames: dict[str, str] = {}
    pending: str | None = None
    for line in text.splitlines():
        s = line.strip()
        hit = PYCLASS_NAME.search(s) or PYO3_NAME.search(s)
        if hit:
            pending = hit.group(1)
            continue
        m = re.match(r"(?:pub\s+)?(?:struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", s)
        if m:
            if pending:
                renames[m.group(1)] = pending
            pending = None
        elif s and not s.startswith(("#[", "//", "///")):
            pending = None
    return renames


def code_identifiers(src: str) -> set[str]:
    """Names REFERENCED BY CODE in one module -- not names merely mentioned.

    Text matching cannot tell a call from prose, and that is not a hypothetical
    distinction: `net_ordering.py`'s docstring named `net_priority_key_py` and
    `net_priority_lt_py` while explaining that nothing constructs a
    `NetPriority` any more. A raw substring scan read the explanation of their
    deadness as proof of their liveness and marked both wired (PR #839).

    That failure is silent and in the unsafe direction -- an unwired kernel
    reported as wired is exactly what this gate exists to catch -- so matching
    is done over the AST instead: attribute accesses, bare names, imported
    aliases, and string arguments to `getattr`/`importlib` (dynamic dispatch is
    a real call site; `dag_engine.py` resolves pipeline stages that way).

    Comments and docstrings contribute nothing, which is the point.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # Unparseable file: fall back to raw text. Over-counting here can only
        # mark something wired that is not, so it is logged by the caller
        # rather than trusted silently.
        raise

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.alias):
            names.add(node.name.rsplit(".", 1)[-1])
            if node.asname:
                names.add(node.asname)
        elif isinstance(node, ast.Call):
            func = node.func
            label = getattr(func, "attr", None) or getattr(func, "id", None)
            if label in {"getattr", "hasattr", "import_module", "__import__"}:
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        names.update(arg.value.split("."))
    return names


def production_references() -> tuple[set[str], list[str]]:
    """Identifiers referenced by every non-test Python source, and unparseable files."""
    roots = ["packages", "scripts", "tools"]
    names: set[str] = set()
    unparseable: list[str] = []
    for root in roots:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            p = str(py)
            if "/tests/" in p or "/test_" in p or p.endswith("_test.py"):
                continue
            if "/.venv/" in p or "/target" in p or "/_py_oracle" in p:
                continue
            try:
                src = py.read_text()
            except OSError:
                continue
            try:
                names |= code_identifiers(src)
            except SyntaxError:
                unparseable.append(str(py.relative_to(REPO_ROOT)))
                names |= set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", src))
    return names, unparseable


def load_inventory() -> dict[str, str]:
    if not INVENTORY.exists():
        return {}
    entries: dict[str, str] = {}
    for line in INVENTORY.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sym, _, reason = line.partition("\t")
        entries[sym.strip()] = reason.strip()
    return entries


def write_inventory(unwired: dict[str, str], previous: dict[str, str]) -> None:
    lines = [
        "# Registered Rust kernels with no production caller.",
        "#",
        "# Shrink-only. A new entry is a hard failure -- wire the kernel or add it",
        "# here WITH A REASON. An entry that becomes wired is also a failure, so",
        "# paid-down debt shows up in a diff instead of rotting on the books.",
        "#",
        "# Generated by scripts/check_unwired_kernels.py --write-inventory",
        "# <symbol>\\t<reason>",
        "",
    ]
    for sym in sorted(unwired):
        reason = previous.get(sym, "").strip() or "unwired at time of recording; no reason given"
        lines.append(f"{sym}\t{reason}")
    INVENTORY.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runtime", action="store_true",
                    help="AUDIT: read symbols from the built extensions instead of "
                         "parsing Rust (exact, but needs `maturin develop`)")
    ap.add_argument("--write-inventory", action="store_true",
                    help="record the current unwired set (shrink-only ledger)")
    args = ap.parse_args()

    symbols = registered_symbols_runtime() if args.runtime else registered_symbols()
    if not symbols:
        print("FAIL: found zero registered pyo3 symbols -- the scan is broken, "
              "not the tree (a gate that inspects nothing passes vacuously).",
              file=sys.stderr)
        return 2

    referenced, unparseable = production_references()
    if not referenced:
        print("FAIL: found zero production Python sources to scan.", file=sys.stderr)
        return 2
    if unparseable:
        print(f"WARN: {len(unparseable)} file(s) did not parse; matched as raw text "
              f"(a mention in prose there can still mask an unwired kernel): "
              f"{', '.join(unparseable[:5])}", file=sys.stderr)

    unwired = {sym: where for sym, where in symbols.items() if sym not in referenced}

    ledger = load_inventory()

    if args.write_inventory:
        write_inventory(unwired, ledger)
        print(f"wrote {INVENTORY.name}: {len(unwired)} unwired kernel(s) "
              f"of {len(symbols)} registered")
        return 0

    new = sorted(set(unwired) - set(ledger))
    stale = sorted(set(ledger) - set(unwired))

    if not new and not stale:
        print(f"OK: {len(symbols)} registered kernel(s); "
              f"{len(unwired)} unwired, all ledgered.")
        return 0

    print("FAIL: unwired-kernel gate\n")
    for sym in new:
        print(f"NEW_UNWIRED   {sym}  ({unwired[sym]})")
        print("              registered into a Python module but no non-test caller.")
    for sym in stale:
        print(f"STALE_ENTRY   {sym} is now wired -- record the fix")
    print()
    if new:
        print("A registered kernel with no production caller is a migration that "
              "stopped at 'the differential is green'. The differential compares "
              "the ORACLE against the Rust and passes either way; it cannot see "
              "whether the shipped module delegates. Wire the Python call site, "
              "or add the symbol to the ledger with a reason.")
    if stale:
        print("STALE_ENTRY means debt was paid but the ledger was not updated: "
              "rerun with --write-inventory and commit the result.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
