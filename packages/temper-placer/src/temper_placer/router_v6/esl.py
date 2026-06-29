"""
Encoder Specification Language (ESL) for SAT constraint verification.

# @req(2026-06-28-006, FR-LANG1): ESL predicate primitives
# @req(2026-06-28-006, FR-LANG3): eval_esl as executable ground truth

Provides predicate primitives and composition operators that declaratively
state what each constraint type means in terms of SAT primary-variable
assignments.  Each predicate is a callable ``(dict[str, bool]) -> bool``.

Predicate primitives
--------------------
* ``at_most_k(vars, k)`` — True iff at most *k* of *vars* are True
* ``all_true(vars)`` — True iff all *vars* are True
* ``any_true(vars)`` — True iff at least one of *vars* is True
* ``exactly_one_of(vars)`` — True iff exactly one of *vars* is True
* ``implies(a, b)`` — True iff a → b (material implication)
* ``iff(a, b)`` — True iff a ↔ b (material equivalence)

Composition operators
---------------------
* ``and_(*predicates)`` — True iff all predicates are True
* ``or_(*predicates)`` — True iff at least one predicate is True

Top-level evaluation
--------------------
* ``eval_esl(model, assignment)`` — evaluate all constraints in a
  ``ConstraintModel`` against a primary-variable assignment

Relationship to constraint types
--------------------------------
Each constraint type in ``constraint_model.py`` has exactly one ``esl()``
method that returns an ESL predicate for that constraint.  The ``esl()``
method is verified by the BMC layer against the CNF encoding produced by
``populate_sat_from_constraints`` in ``sat_model.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from temper_placer.router_v6.constraint_model import ConstraintModel

Predicate = Callable[[dict[str, bool]], bool]


# ---------------------------------------------------------------------------
# Predicate primitives
# ---------------------------------------------------------------------------


def all_true(vars: list[str]) -> Predicate:
    """Return a predicate that is True iff all *vars* are True in the assignment.

    Example:
        >>> p = all_true(["x0", "x1"])
        >>> p({"x0": True, "x1": True})
        True
        >>> p({"x0": True, "x1": False})
        False
    """
    return lambda ass: all(ass.get(v, False) for v in vars)


def any_true(vars: list[str]) -> Predicate:
    """Return a predicate that is True iff at least one *var* is True.

    Example:
        >>> p = any_true(["x0", "x1"])
        >>> p({"x0": False, "x1": False})
        False
        >>> p({"x0": False, "x1": True})
        True
    """
    return lambda ass: any(ass.get(v, False) for v in vars)


def at_most_k(vars: list[str], k: int) -> Predicate:
    """Return a predicate that is True iff at most *k* of *vars* are True.

    If k < 0, the predicate is always False.
    If k >= len(vars), the predicate is always True (trivially satisfied).

    Example:
        >>> p = at_most_k(["x0", "x1", "x2"], 2)
        >>> p({"x0": True, "x1": True, "x2": True})
        False
        >>> p({"x0": True, "x1": False, "x2": False})
        True
    """
    if k < 0:
        return lambda _ass: False
    if k >= len(vars):
        return lambda _ass: True
    return lambda ass: sum(1 for v in vars if ass.get(v, False)) <= k


def exactly_one_of(vars: list[str]) -> Predicate:
    """Return a predicate that is True iff exactly one of *vars* is True.

    Example:
        >>> p = exactly_one_of(["x0", "x1", "x2"])
        >>> p({"x0": True, "x1": False, "x2": False})
        True
        >>> p({"x0": True, "x1": True, "x2": False})
        False
    """
    return lambda ass: sum(1 for v in vars if ass.get(v, False)) == 1


def implies(a: str, b: str) -> Predicate:
    """Return a predicate that is True iff *a* implies *b* (not a or b).

    Example:
        >>> p = implies("x0", "x1")
        >>> p({"x0": True, "x1": False})
        False
        >>> p({"x0": False, "x1": False})
        True
    """
    return lambda ass: (not ass.get(a, False)) or ass.get(b, False)


def iff(a: str, b: str) -> Predicate:
    """Return a predicate that is True iff *a* iff *b* (a <-> b).

    Example:
        >>> p = iff("x0", "x1")
        >>> p({"x0": True, "x1": True})
        True
        >>> p({"x0": True, "x1": False})
        False
        >>> p({"x0": False, "x1": False})
        True
    """
    return lambda ass: ass.get(a, False) == ass.get(b, False)


# ---------------------------------------------------------------------------
# Composition operators
# ---------------------------------------------------------------------------


def and_(*predicates: Predicate) -> Predicate:
    """Return a predicate that is True iff all given predicates are True.

    Example:
        >>> p = and_(iff("x0", "x1"), at_most_k(["x0", "x1", "x2"], 1))
        >>> p({"x0": False, "x1": False, "x2": True})
        True
    """
    return lambda ass: all(p(ass) for p in predicates)


def or_(*predicates: Predicate) -> Predicate:
    """Return a predicate that is True iff at least one given predicate is True.

    Example:
        >>> p = or_(all_true(["x0"]), all_true(["x1"]))
        >>> p({"x0": False, "x1": True})
        True
    """
    return lambda ass: any(p(ass) for p in predicates)


# ---------------------------------------------------------------------------
# Top-level evaluation
# ---------------------------------------------------------------------------


def eval_esl(
    model: ConstraintModel,
    assignment: dict[str, bool],
) -> bool:
    """Evaluate all constraints in *model* against *assignment*.

    # @req(2026-06-28-006, FR-LANG3): eval_esl as executable ground truth

    Returns True iff the assignment satisfies every constraint in the model.
    Empty models (no constraints) are vacuously True.

    This is the ground truth against which the CNF encoding is checked:
    for every assignment, eval_esl(model, assignment) must agree with
    the CNF satisfiability under that assignment.
    """
    for constraint in model.constraints:
        esl_pred = constraint.esl()
        if not esl_pred(assignment):
            return False
    return True
