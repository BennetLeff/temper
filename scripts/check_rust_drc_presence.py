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

- Unset / "0" / "false" (default -- local dev): the Rust backend is
  OPTIONAL. A contributor without a Rust toolchain, or who hasn't run
  `maturin develop` yet, gets a warning and exit 0 -- the Python
  fallback is a documented, correct (if slower) path, and demanding
  Rust unconditionally would break local development for anyone not
  actively working on this crate.
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
MODULE_NAME = "temper_drc_rs"
LIB_RS = REPO_ROOT / "packages" / "temper-drc-rs" / "src" / "lib.rs"


def _required() -> bool:
    return os.environ.get("TEMPER_REQUIRE_RUST_DRC", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _expected_symbols(lib_rs: Path) -> list[str] | None:
    """Parse the `#[pymodule] fn temper_drc_rs(...)` body of lib.rs for the
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
        rf"fn\s+{re.escape(MODULE_NAME)}\s*\([^)]*\)\s*->\s*PyResult<\(\)>\s*\{{(.*?)\n\}}",
        text,
        re.DOTALL,
    )
    if match is None:
        return None

    body = match.group(1)
    names = re.findall(r"wrap_pyfunction!\(\s*(?:crate::[\w:]+::)?(\w+)\s*,", body)
    return names or None


def main() -> int:
    required = _required()
    label = "FAIL" if required else "WARN"

    try:
        module = importlib.import_module(MODULE_NAME)
    except ImportError as exc:
        msg = f"{MODULE_NAME} is not importable ({exc})."
        if required:
            print(
                f"{label}: {msg} TEMPER_REQUIRE_RUST_DRC=1 -- the Rust "
                f"backend is mandatory here (this is CI). Build it with "
                f"`maturin develop --release --manifest-path "
                f"packages/temper-drc-rs/Cargo.toml`.",
                file=sys.stderr,
            )
            return 1
        print(
            f"{label}: {msg} Rust backend is optional here; the Python "
            f"fallback in verify_clearance() will be used instead.",
            file=sys.stderr,
        )
        return 0

    expected = _expected_symbols(LIB_RS)
    if expected is None:
        msg = f"could not determine expected symbols by parsing {LIB_RS}"
        if required:
            print(
                f"{label}: {msg}. Failing closed under "
                f"TEMPER_REQUIRE_RUST_DRC=1 -- presence cannot be proven.",
                file=sys.stderr,
            )
            return 1
        print(f"{label}: {msg}. Skipping freshness check (backend optional here).", file=sys.stderr)
        return 0

    missing = [name for name in expected if not hasattr(module, name)]
    if missing:
        msg = (
            f"{MODULE_NAME} is importable but is missing symbol(s) "
            f"{missing} that {LIB_RS} currently registers -- the installed "
            f"wheel is STALE (built from an older revision of this crate). "
            f"Rebuild with `maturin develop --release --manifest-path "
            f"packages/temper-drc-rs/Cargo.toml` and reinstall."
        )
        if required:
            print(f"{label}: {msg}", file=sys.stderr)
            return 1
        print(f"{label}: {msg}", file=sys.stderr)
        return 0

    print(f"OK: {MODULE_NAME} present and fresh -- symbols {expected} all found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
