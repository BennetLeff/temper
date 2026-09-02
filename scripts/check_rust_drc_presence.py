#!/usr/bin/env python3
"""Fail-closed presence/freshness gate for a locally-built PyO3 extension.

Problem this closes
--------------------
On 2026-07-26, `packages/temper-drc-rs` gained a new exported symbol
(`verify_route_clearance`) alongside the pre-existing `run_drc`. In the
primary checkout, the *installed* `temper_drc_rs` wheel predated that
change: `import temper_drc_rs` still succeeded (the module is not
missing, just stale), so the differential test proving Rust/Python
clearance equivalence
(`packages/temper-placer/tests/router_v6/test_clearance_rust_
differential.py`) silently **skipped** (`pytestmark = skipif(not
_HAS_RUST_CLEARANCE, ...)`), and `verify_clearance()`'s `backend="auto"`
dispatch silently fell back to the slow pure-Python path. Both effects
are exit-0, invisible in a CI summary that only reports pass/fail
counts. This is failure class 6 ("Silently skipped") in
`docs/METHODOLOGY.md` Sec 4.

A bare `import temper_drc_rs; assert True` check (which is what CI ran
before this script existed -- see the "Verify temper-drc-rs loads" step
in `.github/workflows/python-tests.yml`) cannot catch this: the module
*is* importable. What's missing is present, not absent.

What this script does
----------------------
Derives the set of symbols the *current source* (`lib.rs`'s
`#[pymodule]` registration block) expects the compiled extension to
export, then checks the *installed* module actually has every one of
them. A mismatch means the installed build predates the source -- the
exact bug above, generalized to catch any future symbol this crate
adds, not just the specific one that broke this time.

This intentionally does not attempt semantic versioning or content
hashing -- symbol-presence is the cheapest check that would have caught
the actual incident, and it is comparably cheap to a second `import`.
Cargo.toml version bumps are not required for every PR, so a Cargo.toml
version compare would under-detect; comparing source-derived symbol
names against the runtime module over-detects nothing, because if a
name is registered in `#[pymodule]` it MUST appear on the import (pyo3
guarantees this) or the wheel is stale by definition.

The "is the accelerator expected here" signal
-----------------------------------------------
Controlled by `TEMPER_REQUIRE_RUST_DRC`:

- Unset / "0" / "false" (default -- local dev): missing Rust symbols produce
  a warning and exit 0, so contributors can inspect unrelated tooling without
  building every extension. The production clearance API remains Rust-only
  and fails closed when either required symbol is missing.
- "1" / "true" / "yes" (CI sets this): the Rust backend is MANDATORY.
  Any problem below is a hard failure (exit 1), because in CI the
  accelerator itself -- and the differential proof that depends on it
  actually running -- is the thing under test. A CI run that can't
  prove Rust/Python equivalence must not report green.

Fails closed: if the source of truth (`lib.rs`) can't be read or
parsed, that is treated as "cannot determine presence" -- a hard
failure under `TEMPER_REQUIRE_RUST_DRC=1`, never a silent pass.

Usage
-----
    python scripts/check_rust_drc_presence.py
    TEMPER_REQUIRE_RUST_DRC=1 python scripts/check_rust_drc_presence.py
"""

from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_SPECS = (
    (
        "temper_drc_rs",
        REPO_ROOT / "packages" / "temper-drc-rs" / "src" / "lib.rs",
    ),
    (
        "temper_orchestration",
        REPO_ROOT / "packages" / "temper-orchestration" / "src" / "lib.rs",
    ),
)


def _required() -> bool:
    return os.environ.get("TEMPER_REQUIRE_RUST_DRC", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _expected_symbols(module_name: str, lib_rs: Path) -> list[str] | None:
    """Parse a module's `#[pymodule] fn ...` body for the
    Python-visible names it registers via `wrap_pyfunction!`.

    Returns None if the file is missing or the pymodule block can't be
    located -- ambiguous, and the caller must treat that as a failure
    when the backend is required (fail closed), not as "nothing to
    check."
    """
    try:
        text = lib_rs.read_text()
    except OSError:
        return None

    match = re.search(
        rf"fn\s+{re.escape(module_name)}\s*\([^)]*\)\s*->\s*PyResult<\(\)>\s*\{{(.*?)\n\}}",
        text,
        re.DOTALL,
    )
    if match is None:
        return None

    body = match.group(1)
    names = re.findall(r"wrap_pyfunction!\(\s*(?:[\w:]+::)?(\w+)\s*,", body)
    return names or None


def _check_module(module_name: str, lib_rs: Path, *, required: bool) -> bool:
    """Check one extension and return whether its required symbols are present."""
    label = "FAIL" if required else "WARN"

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        msg = f"{module_name} is not importable ({exc})."
        print(
            f"{label}: {msg} Rust symbols are required by production clearance; "
            "build the extension before running clearance checks.",
            file=sys.stderr,
        )
        return False

    expected = _expected_symbols(module_name, lib_rs)
    if expected is None:
        msg = f"could not determine expected symbols by parsing {lib_rs}"
        print(f"{label}: {msg}. Failing closed under the required Rust gate.", file=sys.stderr)
        return False

    missing = [name for name in expected if not hasattr(module, name)]
    if missing:
        print(
            f"{label}: {module_name} is importable but is missing symbol(s) "
            f"{missing} that {lib_rs} currently registers -- the installed "
            "wheel is STALE. Rebuild the extension with maturin.",
            file=sys.stderr,
        )
        return False

    print(f"OK: {module_name} present and fresh -- symbols {expected} all found.")
    return True


def main() -> int:
    required = _required()
    results = [
        _check_module(module_name, lib_rs, required=required)
        for module_name, lib_rs in MODULE_SPECS
    ]
    return 0 if all(results) or not required else 1


if __name__ == "__main__":
    raise SystemExit(main())
