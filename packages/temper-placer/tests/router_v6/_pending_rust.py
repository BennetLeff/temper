"""The Phase-A "pending Rust" convention for Wave-4 differential suites.

Why this module exists
----------------------
Gate **G1** (``docs/wave4-discipline-contract.md``) requires the differential
test that pins the pre-migration implementation to be written *before* the
Rust, **red -> green**, with git history proving the test commit predates the
Rust one.  That means a differential suite has to exist, and has to *fail*,
while its Rust arm is still absent.

The repo had no convention for that state, because every Wave-4 differential
landed so far was written in the same PR as its Rust (#732 imports
``temper_geometry`` at module scope precisely so that a *stale* extension
fails collection loudly).  This slice is the first PR that is deliberately
Phase A only, so it has to choose one.  The candidates and why they were
rejected:

* ``pytest.importorskip`` / ``pytest.mark.skipif`` -- **a skip is not a red.**
  A skipped suite is indistinguishable on CI from a suite that was never
  written, which is exactly the failure mode G1 exists to prevent.
* ``pytest.mark.xfail(strict=True)`` -- reports **XFAIL**, which is a *green*
  run.  It also inverts at green time: every marker would have to be deleted
  in the Rust PR, so the Rust PR could quietly delete an assertion along with
  the marker and nobody would see a status change.
* a module-scope ``import temper_geometry_not_yet`` -- one collection error
  for the whole file.  That *is* red, but it collapses N differential tests
  into a single unnamed failure, so the Rust PR cannot demonstrate
  test-by-test which comparisons went from red to green.

The convention chosen: **resolve the Rust symbol lazily, inside each test.**
:func:`rust` raises :class:`PendingRustError` (an ``AssertionError`` subclass,
so pytest renders it as an ordinary failure) naming the exact symbol that is
missing.  Consequences:

1. The suite is **RED, test by test**, with one named failure per kernel --
   the granularity G1's red->green evidence actually needs.
2. **No assertion and no corpus row changes at green time.**  Each suite
   confines its knowledge of the Rust arm to a short ``_rust_*`` adapter
   block at the top of the file; the test bodies below it call only those
   adapters.  When Phase B adds the pyfunctions, the adapters bind and the
   file passes.  A reviewer diffing the Rust PR therefore sees edits *only*
   inside that block -- and any edit below it is a weakened assertion,
   visible on its own line.  That is the property writing the test first is
   supposed to buy, and confining the churn is what makes it checkable.
3. :func:`missing_symbols` gives the Rust PR a single checklist test
   (``test_rust_symbols_exist``) that enumerates what is still owed.

The oracle arm is exercised *before* the Rust arm is resolved in every test,
so an oracle that has itself broken fails with its own error rather than
being masked by the pending-Rust failure.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable

__all__ = [
    "PendingRustError",
    "missing_symbols",
    "rust",
]


class PendingRustError(AssertionError):
    """The Rust arm of a differential does not exist yet.

    Subclasses ``AssertionError`` on purpose: pytest reports it as a plain
    test failure (red), not as an error, a skip, or an xfail.
    """


def rust(module_name: str, symbol: str) -> Callable[..., object]:
    """Return the Rust pyfunction ``module_name.symbol``.

    Raises :class:`PendingRustError` -- i.e. fails the calling test -- while
    the extension module or the symbol is absent.  ``module_name`` is a
    *migration target*, not a promise about where Phase B will put the
    kernel; if the home crate moves, only the ``_RUST_MODULE`` constant at
    the top of each differential suite changes.
    """
    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:  # pragma: no cover - exercised while red
        raise PendingRustError(
            f"pending Rust: extension module {module_name!r} is not importable "
            f"({exc}); the Phase-B migration must provide {module_name}.{symbol}"
        ) from None
    try:
        return getattr(mod, symbol)
    except AttributeError:
        raise PendingRustError(
            f"pending Rust: {module_name}.{symbol} does not exist yet -- "
            f"this differential case is RED until the Phase-B migration adds it"
        ) from None


def missing_symbols(module_name: str, symbols: tuple[str, ...]) -> list[str]:
    """Names in ``symbols`` that ``module_name`` does not currently export.

    Returns every name when the module itself is not importable.
    """
    try:
        mod = importlib.import_module(module_name)
    except ImportError:
        return list(symbols)
    return [s for s in symbols if not hasattr(mod, s)]
