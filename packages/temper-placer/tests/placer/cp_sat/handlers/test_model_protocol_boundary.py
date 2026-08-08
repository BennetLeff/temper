"""Static boundary enforcement for the `_model_protocol.ModelProtocol` port.

Regression guard for the exact defect this port was created to fix: the
2026-08-07 port-inventory survey claimed none of the 8 `handlers/encode_*.py`
files call the raw `ortools.sat.python.cp_model.CpModel` API, checked that
with a grep for `\\b(ortools|cp_model|CpSolver)\\b`, and missed that
`keepout.py`/`separated.py` both call `model.model_ref.<CpModel method>`
directly — a pattern that grep cannot match because `model_ref` doesn't
contain any of those substrings.

This test parses the AST instead of grepping, so it can't repeat that
mistake: it asserts the six *ported* handlers never touch `model.model_ref`
(or `.model_ref` on any name) and never import `ortools`/`cp_model`
directly, and it asserts the two *parked* handlers still do — so a future
edit that quietly moves one across the boundary (either direction) fails
CI instead of going unnoticed the way the original miscategorisation did.
"""

from __future__ import annotations

import ast
from pathlib import Path

_HANDLERS_DIR = (
    Path(__file__).resolve().parents[4]  # .../packages/temper-placer
    / "src"
    / "temper_placer"
    / "placer"
    / "cp_sat"
    / "handlers"
)

_PORTED = ["adjacent.py", "aligned.py", "anchored.py", "enclosing.py", "loop_area.py", "onside.py"]
_PARKED = ["keepout.py", "separated.py"]


def _uses_model_ref(tree: ast.AST) -> bool:
    """True if any ``<expr>.model_ref`` attribute access appears in the module."""
    return any(
        isinstance(node, ast.Attribute) and node.attr == "model_ref" for node in ast.walk(tree)
    )


def _imports_ortools_at_runtime(tree: ast.Module) -> bool:
    """True if a *top-level, unconditional* import names ortools/cp_model.

    Deliberately module-level only (not nested in TYPE_CHECKING or a
    function body) -- the six ported handlers only need ortools names
    for type hints, guarded by ``if TYPE_CHECKING:`` per PEP 563 (this
    repo already uses ``from __future__ import annotations`` throughout,
    so runtime evaluation of those hints never happens).
    """
    for node in tree.body:  # top level only
        if isinstance(node, ast.ImportFrom) and node.module and "ortools" in node.module:
            return True
        if isinstance(node, ast.Import) and any("ortools" in alias.name for alias in node.names):
            return True
    return False


def _parse(filename: str) -> ast.Module:
    path = _HANDLERS_DIR / filename
    assert path.is_file(), f"expected handler file at {path}"
    return ast.parse(path.read_text(), filename=str(path))


class TestPortedHandlersStayBehindTheProtocol:
    """The 6 ported handlers must never reach past ModelProtocol into model_ref."""

    def test_no_model_ref_access(self) -> None:
        offenders = [f for f in _PORTED if _uses_model_ref(_parse(f))]
        assert offenders == [], (
            f"ported handler(s) {offenders} touch `model_ref` (the raw ortools CpModel) "
            "directly -- this crosses back over the ModelProtocol boundary; either the "
            "handler needs to move to the parked set (keepout.py/separated.py) or the "
            "new call needs a ModelProtocol method instead"
        )

    def test_no_runtime_ortools_import(self) -> None:
        offenders = [f for f in _PORTED if _imports_ortools_at_runtime(_parse(f))]
        assert offenders == [], (
            f"ported handler(s) {offenders} import ortools at module scope (not under "
            "TYPE_CHECKING) -- this reintroduces a runtime ortools dependency the port "
            "was meant to remove"
        )


class TestParkedHandlersStillNeedTheEscapeHatch:
    """Documents (and pins) why keepout.py/separated.py are NOT in this port.

    If either of these ever stops touching `model_ref`, the parking
    rationale in `_model_protocol.py`'s docstring is stale and the file
    should be reconsidered for inclusion in the Protocol port, not left
    parked by inertia.
    """

    def test_keepout_and_separated_still_use_model_ref(self) -> None:
        still_direct = [f for f in _PARKED if _uses_model_ref(_parse(f))]
        assert still_direct == _PARKED, (
            f"expected {_PARKED} to all still call model_ref directly; got {still_direct}. "
            "If a file dropped off this list, its parking rationale needs re-checking, not "
            "silent deletion of this test."
        )
