#!/usr/bin/env python3
"""Symbol-level freshness check for the installed pyo3 extensions.

Why this exists: `scripts/check_stale_extensions.py` compares mtimes (or a
build stamp). On 2026-08-19 it reported `fresh=10 stale=0` while the installed
`temper_geometry` .so did NOT export `pad_anchor_plan_py`, a function its own
`channel_skeleton.rs` registers with `wrap_pyfunction!` -- and
`scripts/route_board.py` had failed minutes earlier with exactly that
AttributeError. A measurement taken against that .so is not a measurement of
this source tree. This checks the property that actually matters: does the
imported module expose every symbol the Rust source registers?

Handles: `wrap_pyfunction!(path::to::fn, m)` paths, `#[pyo3(name = "...")]`
renames, and registration onto a submodule rather than the crate root.
"""

from __future__ import annotations

import importlib
import re
import sys
import types
from pathlib import Path

ROOT = Path("/home/bennet/Desktop/temper")
CRATE_TO_MOD = {
    "temper-constraint-compiler": "temper_constraint_compiler",
    "temper-constraints": "temper_constraints",
    "temper-design-bundle": "temper_design_bundle_python",
    "temper-drc-rs": "temper_drc_rs",
    "temper-geometry": "temper_geometry",
    "temper-io-types": "temper_io_types",
    "temper-orchestration": "temper_orchestration",
    "temper-quality-oracle": "temper_quality_oracle",
    "temper-rust-router": "temper_rust_router",
    "temper-thermal": "temper_thermal",
}
WRAP = re.compile(r"wrap_pyfunction!\(\s*((?:[A-Za-z_]\w*::)*[A-Za-z_]\w*)")
RENAME = re.compile(
    r'#\[pyo3\(name\s*=\s*"([^"]+)"\)\]((?:\s*(?:#\[[^\]]*\]|//[^\n]*))*)\s*(?:pub(?:\([^)]*\))?\s+)?fn\s+([A-Za-z_]\w*)'
)


def crate_src(crate: str) -> Path:
    p = ROOT / "packages" / crate / "src"
    return p if p.exists() else ROOT / "packages/temper-placer" / crate / "src"


def module_symbols(m: types.ModuleType) -> set[str]:
    seen: set[int] = set()
    out: set[str] = set()

    def walk(x, depth=0):
        if depth > 3 or id(x) in seen:
            return
        seen.add(id(x))
        for a in dir(x):
            out.add(a)
            v = getattr(x, a, None)
            if isinstance(v, types.ModuleType):
                walk(v, depth + 1)

    walk(m)
    return out


bad = 0
for crate, mod in sorted(CRATE_TO_MOD.items()):
    registered: set[str] = set()
    renames: dict[str, str] = {}
    for rs in crate_src(crate).rglob("*.rs"):
        t = rs.read_text(encoding="utf-8", errors="replace")
        for hit in WRAP.findall(t):
            registered.add(hit.rsplit("::", 1)[-1])
        for export, _mid, rust_name in RENAME.findall(t):
            renames[rust_name] = export
    expected = {renames.get(n, n) for n in registered}
    try:
        m = importlib.import_module(mod)
    except Exception as e:  # noqa: BLE001
        print(f"[UNLOADABLE] {crate} -> {mod}: {e}")
        bad += 1
        continue
    present = module_symbols(m)

    # A #[pyo3(name = ...)] rename this scanner did not pair (attribute order
    # varies) usually only adds/removes a `_py` suffix or `py_` prefix.
    def has(n: str) -> bool:
        return (
            n in present
            or (n.endswith("_py") and n[:-3] in present)
            or (n.startswith("py_") and n[3:] in present)
        )

    missing = sorted(n for n in expected if not has(n))
    if missing:
        print(
            f"[SYMBOL-STALE] {crate} -> {mod}: missing {len(missing)}/{len(expected)} "
            f"registered pyfunctions: {', '.join(missing[:8])}"
            + (" ..." if len(missing) > 8 else "")
        )
        bad += 1
    else:
        print(f"[OK] {crate} -> {mod}: all {len(expected)} registered pyfunctions present")
print(
    f"\n{'FAILED' if bad else 'PASSED'} -- {bad}/{len(CRATE_TO_MOD)} crate(s) symbol-stale or unloadable."
)
sys.exit(1 if bad else 0)
