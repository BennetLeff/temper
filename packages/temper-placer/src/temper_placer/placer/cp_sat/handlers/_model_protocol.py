"""Structural-typing boundary for the six ported ``encode_*`` handlers.

Wave-4 PORT-behind-abstraction port of the "BLOCKER-ORTOOLS" handler
cluster (588 LOC, ``handlers/encode_*.py``). See
``docs/evidence/2026-08-07-port-inventory-verification.md`` sec 6b for the
original claim, and the follow-up finding that 2 of the 8 handlers
(``keepout.py``, ``separated.py``) call ``model.model_ref`` (the raw
``ortools.sat.python.cp_model.CpModel``) directly for reified constraints
(``OnlyEnforceIf``, ``AddBoolOr``) and ad hoc interval/no-overlap
construction. This module intentionally does **not** cover those two
primitives — see "Deliberately excluded" below.

``adjacent.py``, ``aligned.py``, ``anchored.py``, ``enclosing.py``,
``loop_area.py``, and ``onside.py`` build every constraint exclusively
through named ``CpSatModel`` methods and arithmetic/comparison operators
on ``IntVar``-like objects (``ComponentVars`` fields). Nothing in those
six files imports ``ortools`` or touches ``model.model_ref``. This module
names that dependency surface as an explicit ``typing.Protocol`` so the
six handlers can be type-checked (and, in principle, executed) against
*any* object satisfying it — not just the concrete, ortools-backed
``CpSatModel``/``ComponentVars`` in ``cp_sat/model.py``.

**No runtime behaviour changes.** ``CpSatModel`` and ``ComponentVars``
already satisfy this Protocol structurally (Python's ``Protocol`` is
duck-typed — no inheritance or registration needed), so porting the six
handlers to depend on it instead of the concrete types is a pure
type-annotation change. Every annotation in the six handler files is
under ``from __future__ import annotations`` (PEP 563: annotations are
never evaluated at runtime, only strings), so this refactor cannot alter
the bytecode of any function body — only what a type checker sees.

**Why this is still real work.** Before this module, the six handlers'
only *stated* dependency was ``CpSatModel``/``ComponentVars`` — the
ortools-backed wrapper types themselves, imported (under
``TYPE_CHECKING``) from ``cp_sat/model.py``, which does ``from
ortools.sat.python import cp_model`` at module scope. A type checker
running against the handler files alone could not distinguish "this file
needs six specific methods" from "this file needs the whole ortools
wrapper". This module makes the *actual* minimal surface explicit and
machine-checkable, which is the prerequisite for ever writing a second
(e.g. Rust-backed) implementation: the second implementation only has to
satisfy ``ModelProtocol``/``ComponentVarsProtocol``/``IntVarExpr``, not
reproduce ``CpSatModel`` wholesale.

**Deliberately excluded (parked, not forgotten).** This Protocol does not
model ``OnlyEnforceIf``-reified constraints, ``AddBoolOr``, or ad hoc
``NewIntervalVar``/``AddNoOverlap2D`` calls over an arbitrary extra
interval list. Those are CP-SAT's own reification/interval-scheduling
primitives, not generic expression algebra — designing a solver-agnostic
abstraction for them is real design work whose right shape depends on the
still-open solver-replacement decision, not something to pre-empt inside
a mechanical porting pass. ``keepout.py`` and ``separated.py`` (200 of
the original 588 LOC) call ``model.model_ref`` directly for exactly this
reason and stay outside this Protocol, and outside this port, until that
decision is made.
"""

from __future__ import annotations

from typing import Protocol


class ConstraintExpr(Protocol):
    """Opaque handle to a built linear/bounded constraint expression.

    Returned by comparison operators on ``IntVarExpr`` (``<=``, ``>=``,
    ``==``) and passed opaquely to ``ModelProtocol.add`` /
    ``add_constraint_enforced``. Handlers never construct one directly
    and never inspect its internals — it is threaded through, not built.
    Satisfied by ``ortools.sat.python.cp_model.BoundedLinearExpression``.
    """


class IntVarExpr(Protocol):
    """A model integer-variable-like expression.

    Satisfied by ``ortools.sat.python.cp_model.IntVar`` and by any
    arithmetic combination of them (``LinearExpr``). A hypothetical
    Rust-backed solver's variable handle would need to support the same
    six operators to be usable by these handlers unmodified.
    """

    def __add__(self, other: object) -> IntVarExpr: ...
    def __sub__(self, other: object) -> IntVarExpr: ...
    def __le__(self, other: object) -> ConstraintExpr: ...
    def __ge__(self, other: object) -> ConstraintExpr: ...
    def __eq__(self, other: object) -> ConstraintExpr: ...  # type: ignore[override]


class ComponentVarsProtocol(Protocol):
    """Per-component placement variables the six handlers read.

    Matches the subset of ``cp_sat.model.ComponentVars`` they actually
    touch — deliberately omits ``rot_ref``/``orig_w``/``orig_h``, which
    none of the six read.
    """

    ref: str
    x_center: IntVarExpr
    y_center: IntVarExpr
    x_start: IntVarExpr
    y_start: IntVarExpr
    x_end: IntVarExpr
    y_end: IntVarExpr


class ModelProtocol(Protocol):
    """The subset of ``CpSatModel`` the six ported handlers require.

    Every method here is already a named, documented ``CpSatModel``
    method (not a raw ``model_ref`` passthrough); ``mm_to_units`` is
    itself already Rust-delegated (``temper_constraints::encoder``), so
    every float-sensitive computation reachable from these six handlers
    already has a Rust implementation behind it. There is no additional
    floating-point/geometric arithmetic left in these six files to move —
    what remains is either plain integer arithmetic on already-converted
    units (no rounding ambiguity, not worth an FFI round trip for a
    called-once-per-constraint site) or direct construction of
    ``IntVarExpr`` constraints, which is the ortools-coupled part by
    definition and cannot move while ortools remains the solver.
    """

    units_per_mm: int

    def mm_to_units(self, mm: float) -> int: ...
    def new_assumption(self, label: str) -> IntVarExpr: ...
    def new_int_var(self, lb: int, ub: int, name: str) -> IntVarExpr: ...
    def add(self, constraint: ConstraintExpr) -> None: ...
    def add_constraint_enforced(
        self, constraint: ConstraintExpr, assumption: IntVarExpr
    ) -> None: ...
    def add_multiplication_equality(
        self, target: IntVarExpr, a: IntVarExpr, b: IntVarExpr
    ) -> None: ...
