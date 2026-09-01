#!/usr/bin/env python3
"""CI gate: find electrical assertions in ``elec/**/*.ato`` that cannot fail.

WHY THIS EXISTS
---------------
On 2026-08-17 a review of the power stage produced a list of defects that all
shared one shape: *a check that could not fail*.  None was wrong in its own
terms; each read as correct.  Three verified examples:

* ``PowerInput`` asserts ``fuse.current_rating >= constraints.i_max`` and
  ``cmc.current_rating >= constraints.i_max``.  ``constraints.i_max`` is the
  **declared** 15 A branch rating.  The doubler topology actually draws ~27 A.
  Both assertions are true; neither can fail in response to anything the
  circuit does, because neither operand depends on the circuit.
* ``main.ato`` sets ``p_output_max = 1800W`` and then asserts
  ``p_output_max within 1500W to 1800W``.  The value sits exactly on the
  unreachable end of its own range and the assertion passes.
* A rectifier diode was checked against MUR1560's ``I_F(AV)`` = 15 A when
  ``I_FRM`` = 30 A is the binding rating for a capacitor-input rectifier.  The
  check passed truthfully while measuring a quantity nobody had questioned.

This repository already owns the concept on the software side --- mutation
tests, anti-vacuity tests, ``scripts/check_vacuous_gates.py``,
``scripts/check_rust_coverage_illusions.py``.  It had never been applied to
the electrical assertions.  This gate is that application.

METHOD -- and its limits
------------------------
The gate reads the ``.ato`` sources directly (``scripts/_lib/ato_model.py``
explains why it does not shell out to ``ato``), elaborates every assertion's
expression into a dependency closure, classifies each terminal quantity, and
then **perturbs** it.

Each terminal quantity in an assertion's closure is classified as exactly one
of three roles.  The classification is closed: a component attribute that is
in neither table is a gate ERROR, never a guess (see ``classify_leaf``).

``CIRCUIT``
    A property of a part that determines what the circuit *does* --- a
    resistor's ``value``, a capacitor's ``value``.  Change it and the
    behaviour of the design changes.
``RATING``
    A datasheet limit of a part --- ``voltage_rating``, ``current_rating``,
    ``power_rating``.  This is the thing an assertion *checks*, not the thing
    the circuit *does*.
``SPEC``
    A declared design constant --- ``constraints.i_max``, ``v_bus_half``,
    ``p_output_max``.  A number a human typed.

Perturbation then answers the question that matters: **can this assertion's
truth value change?**  Each leaf is swept over a wide multiplicative range and
the assertion is re-evaluated.  Three findings fall out:

``TAUTOLOGY``
    No perturbation of *any* leaf changes the outcome.  The assertion cannot
    fail under any edit to the design.  Strongest form of vacuity.
``NO_CIRCUIT_COUPLING``
    No perturbation of any ``CIRCUIT`` leaf changes the outcome --- usually
    because the closure contains no ``CIRCUIT`` leaf at all.  The assertion is
    decoupled from the circuit: no component change can ever make it fail.
    This is the ``PowerInput`` class, caught by construction.
``TIE_MARGIN``
    The assertion is decided by an exact numeric tie: a ``within`` band whose
    value sits exactly on an endpoint, or a comparison whose sides are exactly
    equal.  This is the ``main.ato:494-495`` class.

An assertion that is none of these is *satisfied*, not vacuous: the gate found
a concrete perturbation that makes it false and records that witness.  The
distinction between "cannot fail" and "can fail, currently passes" is the
entire product of this gate.

KNOWN BLIND SPOTS (state them; do not pretend this is exhaustive)
----------------------------------------------------------------
1. **This gate cannot tell you an assertion is checking the WRONG quantity.**
   The MUR1560 ``I_F(AV)`` vs ``I_FRM`` defect from the incident is NOT
   detectable here.  ``I_F(AV)`` is a real rating, compared against a real
   derived current; the assertion is well-formed and non-vacuous.  Only an
   engineer who knows a capacitor-input rectifier is peak-limited can see it.
   The gate narrows the search space; it does not close it.
2. **Only the two ground-truth classes are proven.**  Everything else it
   reports is a candidate for an electrical review, not a proven defect.
3. **Perturbation is multiplicative and finite.**  A pathological expression
   whose truth flips only inside a narrow additive window this sweep steps
   over would be misreported as invariant.  The sweep is deliberately wide
   (1e-6 .. 1e6) to make that unlikely, not impossible.
4. **Assertions are evaluated in their defining module's scope**, not per
   instance.  If an enclosing module numerically overrode a quantity an
   assertion depends on, definition-local evaluation would be wrong; the gate
   detects that case and raises rather than reporting a number it cannot
   stand behind (see ``check_no_instance_overrides``).
5. **Tolerance intervals are honoured.**  Assertions that are undecidable
   across the declared tolerances are reported as ``INDETERMINATE`` rather
   than silently rounded to a pass, and an assertion that evaluates FALSE is
   reported as ``VIOLATED`` rather than filed under "can fail, currently
   passes".
6. It reads ``elec/src/**/*.ato`` only.  It says nothing about the netlist,
   the board, or the firmware.

THE RATCHET -- and exactly how blocking this is
-----------------------------------------------
Say it plainly: **on the tree this gate landed against, 74 of 86 assertions
are circuit-decoupled.**  That count is not a tuning artefact; this
design-as-code has almost no derived quantities, so most of its assertions
compare one hand-typed literal to another.  Fixing that is electrical work
owned by the power-stage engineer, and every entry is a separate change.  A
gate cannot do it and must not pretend to.

So all four finding kinds go into one **shrink-only ledger**
(``.ato-assertion-vacuity-inventory``), following the same discipline as
``.hash-order-inventory``: a new site fails, a grown count fails, **and a
shrunk or stale entry also fails**, so paid-down debt has to be recorded in
the diff instead of quietly evaporating.

What that means in practice:

* **Non-blocking for the 79 findings that exist today.**  They are recorded.
  The gate is green on the current tree.
* **Blocking from commit one for every new or edited assertion.**  The ledger
  key includes the assertion's source text, so writing a new vacuous assertion
  --- or editing an existing one into a different vacuous form --- fails the
  build immediately.
* **Fully blocking when the ledger reaches zero**, i.e. when every rating
  assertion in the design is compared against a quantity derived from the
  circuit rather than against a number someone typed.  At that point delete
  the ledger file and the gate is unconditional.

Uniform ratcheting of all four kinds (rather than hard-blocking the sharp ones)
is a deliberate call.  Three ``TIE_MARGIN`` findings exist today and the fix
for each is an electrical decision, not a mechanical one.  A gate that ships
red gets switched off, and a switched-off gate detects nothing --- which is how
the tripwires this replaces died.

USAGE
-----
    uv run python scripts/check_ato_assertion_vacuity.py
    uv run python scripts/check_ato_assertion_vacuity.py --report      # full inventory
    uv run python scripts/check_ato_assertion_vacuity.py --write-inventory

EXIT CODES
----------
0   the ledger matches the tree exactly
1   a new / grown / shrunk / stale ledger entry
2   the scan itself broke (parse error, unclassifiable leaf, scope evaporated)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.ato_model import (  # noqa: E402
    Assertion,
    BinOp,
    Compare,
    Definition,
    Literal,
    ParseError,
    Quantity,
    Ref,
    Tolerance,
    UnaryOp,
    UnitError,
    Within,
    parse_tree,
    walk_refs,
)
from _lib.repo import find_repo_root  # noqa: E402

DEFAULT_SRC = Path("elec/src")
DEFAULT_INVENTORY = Path(".ato-assertion-vacuity-inventory")

# A scan that finds nothing must not pass.  ``elec/src`` has 8 .ato files and
# 86 assertions today; these floors are set well below that so ordinary
# editing does not trip them, but a glob that silently matches nothing does.
MIN_ATO_FILES = 4
MIN_ASSERTIONS = 40

EXIT_OK = 0
EXIT_FINDING = 1
EXIT_GATE_ERROR = 2


class GateError(Exception):
    """The scan itself could not be completed. Never a silent pass."""


# ---------------------------------------------------------------------------
# Leaf role classification
# ---------------------------------------------------------------------------
# These two tables are the gate's only judgement call, so they are explicit,
# closed, and small.  A component attribute in neither table raises rather
# than defaulting, because a mis-defaulted attribute would silently move an
# assertion between "coupled to the circuit" and "not coupled" -- the exact
# distinction this gate sells.

#: Datasheet limits. What an assertion *checks*.
RATING_ATTRS = frozenset(
    {
        "voltage_rating",
        "current_rating",
        "power_rating",
        "i_source_peak",
        "i_sink_peak",
        "v_cc_sec_max",
        "v_cci_max",
        "v_ce_max",
        "v_ce_sat",
        "i_c_max",
        "v_iso",
        "contact_current",
        "coil_voltage",
        "i_f_av",
        "i_frm",
    }
)

#: Part properties that determine circuit behaviour. What the circuit *does*.
CIRCUIT_ATTRS = frozenset(
    {
        "value",
        "resistance",
        "capacitance",
        "inductance",
        "resistance_cold",
        "turns_ratio",
        "dcr",
    }
)

ROLE_CIRCUIT = "CIRCUIT"
ROLE_RATING = "RATING"
ROLE_SPEC = "SPEC"

TRUE, FALSE, INDET = "TRUE", "FALSE", "INDETERMINATE"

#: Multiplicative perturbation sweep. Deliberately wide: the question is
#: "can this outcome change at all", not "does it change by a little".
MULTIPLIERS = (
    1e-6,
    1e-3,
    0.1,
    0.5,
    0.9,
    1.1,
    2.0,
    10.0,
    1e3,
    1e6,
)

MAX_RESOLVE_DEPTH = 24


# ---------------------------------------------------------------------------
# Design model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Leaf:
    """A terminal (literal-valued) quantity an assertion depends on."""

    key: str  # canonical identity, e.g. "PowerInput::fuse.current_rating"
    role: str
    quantity: Quantity
    display: str


@dataclass
class Resolution:
    """Where a dotted reference bottoms out."""

    expr: object
    scope: Definition  # definition in whose scope ``expr`` must be evaluated
    key: str
    owner_kind: str  # "component" | "module" | "interface" | "extern"
    attr: str


@dataclass
class Finding:
    kind: str
    assertion: Assertion
    detail: str
    witness: str = ""

    @property
    def key(self) -> str:
        """Stable ledger identity: finding kind, file, module, assertion text.

        Deliberately **not** keyed on line number --- other agents edit these
        files concurrently and a line-keyed ledger would churn on every
        unrelated comment edit.  The assertion source text is the identity, so
        *changing* an assertion retires its ledger entry and requires the new
        form to be re-reviewed.  That is the intended cost.
        """
        return (
            f"{self.kind}|{self.assertion.file}::{self.assertion.owner}::"
            f"{self.assertion.source}"
        )

    def render(self) -> str:
        location = f"{self.assertion.file}:{self.assertion.line}"
        return f"{location}  [{self.assertion.owner}]  assert {self.assertion.source}  -- {self.detail}"


class Design:
    """Elaborated view of the ``.ato`` sources with a perturbable evaluator."""

    def __init__(self, definitions: dict[str, Definition]) -> None:
        self.definitions = definitions
        unique: dict[int, Definition] = {}
        for definition in definitions.values():
            unique[id(definition)] = definition
        self.unique_definitions = sorted(unique.values(), key=lambda d: (d.file, d.line))

    # -- assertions ------------------------------------------------------
    def assertions(self) -> list[Assertion]:
        out: list[Assertion] = []
        for definition in self.unique_definitions:
            out.extend(definition.assertions)
        return sorted(out, key=lambda a: (a.file, a.line))

    # -- name resolution -------------------------------------------------
    def owner_definition(self, scope: Definition, path: tuple[str, ...]) -> object:
        """Definition (or external type name) of the instance owning path[-1]."""
        current: object = scope
        for segment in path[:-1]:
            if not isinstance(current, Definition):
                return current
            type_name = current.instances.get(segment)
            if type_name is None:
                type_name = current.deep_instances.get((segment,))
            if type_name is None:
                return None
            current = self.definitions.get(type_name, type_name)
        return current

    def resolve(
        self, scope: Definition, path: tuple[str, ...], depth: int = 0
    ) -> Resolution | None:
        if depth > MAX_RESOLVE_DEPTH:
            raise GateError(
                f"reference resolution exceeded depth {MAX_RESOLVE_DEPTH} at "
                f"{scope.name}.{'.'.join(path)} -- probable definition cycle"
            )
        if path in scope.deep_assignments:
            return Resolution(
                expr=scope.deep_assignments[path],
                scope=scope,
                key=f"{scope.name}::{'.'.join(path)}",
                owner_kind=self._owner_kind(scope, path),
                attr=path[-1],
            )
        if len(path) == 1:
            expr = scope.attributes.get(path[0])
            if expr is None:
                return None
            return Resolution(
                expr=expr,
                scope=scope,
                key=f"{scope.name}::{path[0]}",
                owner_kind="module" if scope.kind != "component" else "component",
                attr=path[0],
            )
        type_name = scope.instances.get(path[0]) or scope.deep_instances.get((path[0],))
        if type_name is None or type_name not in self.definitions:
            return None
        return self.resolve(self.definitions[type_name], path[1:], depth + 1)

    def _owner_kind(self, scope: Definition, path: tuple[str, ...]) -> str:
        owner = self.owner_definition(scope, path)
        if owner is None:
            return "module"
        if isinstance(owner, Definition):
            return owner.kind
        return "extern"

    # -- evaluation ------------------------------------------------------
    def evaluate(
        self,
        scope: Definition,
        expr: object,
        overrides: dict[str, Quantity],
        depth: int = 0,
    ) -> Quantity:
        if depth > MAX_RESOLVE_DEPTH:
            raise GateError("expression evaluation exceeded depth -- probable cycle")
        if isinstance(expr, Literal):
            return expr.quantity
        if isinstance(expr, Ref):
            resolution = self.resolve(scope, expr.path)
            if resolution is None:
                raise GateError(
                    f"unresolvable reference {'.'.join(expr.path)} in {scope.name} "
                    f"({scope.file}) -- the gate refuses to score an assertion it "
                    f"cannot read"
                )
            if resolution.key in overrides:
                return overrides[resolution.key]
            return self.evaluate(resolution.scope, resolution.expr, overrides, depth + 1)
        if isinstance(expr, UnaryOp):
            value = self.evaluate(scope, expr.operand, overrides, depth + 1)
            return -value if expr.op == "-" else value
        if isinstance(expr, BinOp):
            left = self.evaluate(scope, expr.left, overrides, depth + 1)
            right = self.evaluate(scope, expr.right, overrides, depth + 1)
            if expr.op == "+":
                return left + right
            if expr.op == "-":
                return left - right
            if expr.op == "*":
                return left * right
            if expr.op == "/":
                return left / right
            raise GateError(f"unsupported operator {expr.op!r}")
        if isinstance(expr, Tolerance):
            base = self.evaluate(scope, expr.base, overrides, depth + 1)
            spread = self.evaluate(scope, expr.spread, overrides, depth + 1)
            if expr.is_percent:
                delta = base * spread.scaled(0.01)
            else:
                # An absolute spread must carry the base's dimension. Silently
                # subtracting a bare number from a dimensioned base is how a
                # 20% tolerance became +/-0.2 ohm; refuse instead.
                if spread.dim != base.dim:
                    raise UnitError(
                        f"tolerance spread {spread} is dimensionally incompatible "
                        f"with base {base}; write it as a percentage or give it a unit"
                    )
                delta = spread
            low = base.lo - abs(delta.hi)
            high = base.hi + abs(delta.hi)
            return Quantity(low, high, base.dim)
        raise GateError(f"cannot evaluate node {type(expr).__name__}")

    def truth(
        self, scope: Definition, expr: object, overrides: dict[str, Quantity]
    ) -> str:
        """Three-valued evaluation of a predicate over interval quantities.

        ``a >= b`` is TRUE only when it holds across the *whole* declared
        tolerance range of both sides, FALSE only when it fails across the
        whole range, and INDETERMINATE otherwise.  Collapsing the middle case
        into a pass is exactly the false confidence this gate exists to find.
        """
        if isinstance(expr, Compare):
            left = self.evaluate(scope, expr.left, overrides)
            right = self.evaluate(scope, expr.right, overrides)
            if left.dim != right.dim:
                raise UnitError(f"dimension mismatch across {expr.op}")
            return _compare_intervals(expr.op, left, right)
        if isinstance(expr, Within):
            value = self.evaluate(scope, expr.value, overrides)
            low = self.evaluate(scope, expr.lo, overrides)
            high = self.evaluate(scope, expr.hi, overrides)
            if value.dim != low.dim or value.dim != high.dim:
                raise UnitError("dimension mismatch in `within`")
            if value.lo >= low.lo and value.hi <= high.hi:
                return TRUE
            if value.hi < low.lo or value.lo > high.hi:
                return FALSE
            return INDET
        raise GateError(f"assertion is not a predicate: {type(expr).__name__}")

    # -- dependency closure ---------------------------------------------
    def leaves(self, scope: Definition, expr: object, depth: int = 0) -> dict[str, Leaf]:
        """Terminal quantities the value of *expr* depends on, keyed canonically."""
        if depth > MAX_RESOLVE_DEPTH:
            raise GateError("closure computation exceeded depth -- probable cycle")
        found: dict[str, Leaf] = {}
        for ref in walk_refs(expr):
            resolution = self.resolve(scope, ref.path)
            if resolution is None:
                raise GateError(
                    f"unresolvable reference {'.'.join(ref.path)} in {scope.name}"
                )
            nested = walk_refs(resolution.expr)
            if nested:
                found.update(self.leaves(resolution.scope, resolution.expr, depth + 1))
                continue
            role = classify_leaf(resolution, scope, ref)
            found[resolution.key] = Leaf(
                key=resolution.key,
                role=role,
                quantity=self.evaluate(resolution.scope, resolution.expr, {}),
                display=".".join(ref.path),
            )
        return found


def _compare_intervals(op: str, left: Quantity, right: Quantity) -> str:
    if op == ">=":
        if left.lo >= right.hi:
            return TRUE
        if left.hi < right.lo:
            return FALSE
        return INDET
    if op == ">":
        if left.lo > right.hi:
            return TRUE
        if left.hi <= right.lo:
            return FALSE
        return INDET
    if op == "<=":
        return _compare_intervals(">=", right, left)
    if op == "<":
        return _compare_intervals(">", right, left)
    if op == "==":
        if left.is_exact and right.is_exact:
            return TRUE if left.lo == right.lo else FALSE
        return INDET
    if op == "!=":
        result = _compare_intervals("==", left, right)
        if result == TRUE:
            return FALSE
        if result == FALSE:
            return TRUE
        return INDET
    raise GateError(f"unsupported comparison {op!r}")


def classify_leaf(resolution: Resolution, scope: Definition, ref: Ref) -> str:
    """Assign a leaf its role, or raise. There is no default branch.

    An attribute of a ``component`` instance is either a datasheet rating or a
    circuit-determining property.  Guessing wrong would silently reclassify an
    assertion, so an unknown attribute is a gate error that names the file it
    came from.
    """
    if resolution.owner_kind != "component":
        return ROLE_SPEC
    attr = resolution.attr
    if attr in RATING_ATTRS:
        return ROLE_RATING
    if attr in CIRCUIT_ATTRS:
        return ROLE_CIRCUIT
    raise GateError(
        f"unclassified component attribute {attr!r} (via {'.'.join(ref.path)} in "
        f"{scope.name}, {scope.file}). Add it to RATING_ATTRS or CIRCUIT_ATTRS in "
        f"{Path(__file__).name} -- this gate must not guess whether an attribute "
        f"describes what a part can withstand or what the circuit does."
    )


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


@dataclass
class Analysis:
    assertion: Assertion
    baseline: str
    leaves: dict[str, Leaf]
    flipping: dict[str, str] = field(default_factory=dict)  # leaf key -> witness

    def circuit_leaves(self) -> list[Leaf]:
        return [leaf for leaf in self.leaves.values() if leaf.role == ROLE_CIRCUIT]

    def rating_leaves(self) -> list[Leaf]:
        return [leaf for leaf in self.leaves.values() if leaf.role == ROLE_RATING]


def analyse(design: Design, definition: Definition, assertion: Assertion) -> Analysis:
    leaves = design.leaves(definition, assertion.expr)
    baseline = design.truth(definition, assertion.expr, {})
    flipping: dict[str, str] = {}
    for key, leaf in leaves.items():
        for multiplier in MULTIPLIERS:
            try:
                perturbed = design.truth(
                    definition,
                    assertion.expr,
                    {key: leaf.quantity.scaled(multiplier)},
                )
            except (UnitError, ZeroDivisionError):
                # A perturbation that makes the expression undefined (e.g. a
                # divisor swept through zero) carries no information about
                # whether the assertion can fail. Skip it, do not count it.
                continue
            if perturbed != baseline:
                flipping[key] = (
                    f"{leaf.display} x{multiplier:g} "
                    f"({leaf.quantity} -> {leaf.quantity.scaled(multiplier)}) "
                    f"turns {baseline} into {perturbed}"
                )
                break
    return Analysis(assertion=assertion, baseline=baseline, leaves=leaves, flipping=flipping)


def tie_margin_detail(design: Design, definition: Definition, assertion: Assertion) -> str:
    """Return a description when the assertion is decided by an exact tie.

    Two shapes, both meaning "this assertion has literally zero margin":

    * ``value within lo to hi`` where the value sits exactly on ``lo`` or
      ``hi``.  ``p_output_max = 1800W`` asserted ``within 1500W to 1800W`` is
      the motivating case: the declared value is pinned to the unreachable end
      of the band the assertion pretends to constrain it inside.
    * ``a <= b`` / ``a >= b`` where both sides are exact and equal.  The check
      passes only by the inclusive endpoint; any change in either direction on
      the wrong side fails it, and no change at all is being tolerated.
    """
    expr = assertion.expr
    if isinstance(expr, Within):
        value = design.evaluate(definition, expr.value, {})
        low = design.evaluate(definition, expr.lo, {})
        high = design.evaluate(definition, expr.hi, {})
        if not value.is_exact:
            return ""
        if value.lo == low.lo:
            return (
                f"declared value {value} sits exactly on the LOWER end of its own "
                f"band [{low.lo:g}, {high.hi:g}] -- zero margin below"
            )
        if value.hi == high.hi:
            return (
                f"declared value {value} sits exactly on the UPPER end of its own "
                f"band [{low.lo:g}, {high.hi:g}] -- zero margin above"
            )
        return ""
    if isinstance(expr, Compare) and expr.op in {"<=", ">="}:
        left = design.evaluate(definition, expr.left, {})
        right = design.evaluate(definition, expr.right, {})
        if left.is_exact and right.is_exact and left.lo == right.lo:
            return (
                f"both sides evaluate to exactly {left} -- the assertion passes "
                f"only by the inclusive endpoint, with zero margin"
            )
    return ""


def no_circuit_coupling_detail(analysis: Analysis) -> str:
    """Describe *why* nothing the circuit does can falsify this assertion."""
    circuit = analysis.circuit_leaves()
    ratings = analysis.rating_leaves()
    if not circuit:
        if ratings:
            names = ", ".join(sorted(leaf.display for leaf in ratings))
            spec_names = sorted(
                leaf.display
                for leaf in analysis.leaves.values()
                if leaf.role == ROLE_SPEC
            )
            counterpart = (
                f"declared constant(s) [{', '.join(spec_names)}]"
                if spec_names
                else "an inline literal written into the assertion itself"
            )
            return (
                f"rating-vs-declared: component rating(s) [{names}] are compared "
                f"only against {counterpart}; no component value appears anywhere "
                f"in the closure, so no circuit change can falsify this"
            )
        names = ", ".join(sorted(leaf.display for leaf in analysis.leaves.values()))
        return (
            f"declared-only: every operand [{names}] is a hand-typed constant; "
            f"the assertion re-states a declaration rather than testing it"
        )
    names = ", ".join(sorted(leaf.display for leaf in circuit))
    return (
        f"circuit operands [{names}] are present but perturbing each of them "
        f"across 1e-6..1e6 never changes the outcome"
    )


def find_violations(
    src_root: Path,
    repo_root: Path,
    min_files: int | None = None,
    min_assertions: int | None = None,
) -> tuple[list[Finding], dict[str, object]]:
    """Analyse every assertion under *src_root*.

    Returned as ``(findings, stats)``.  Exposed as a module-level, path-taking
    function so ``ci-corpus/canaries/`` and ``scripts/tests/`` can drive it.

    *min_files* / *min_assertions* override the anti-vacuity floors so that
    small synthetic fixtures can be analysed.  They default to the real
    constants; production callers never pass them.
    """
    min_files = MIN_ATO_FILES if min_files is None else min_files
    min_assertions = MIN_ASSERTIONS if min_assertions is None else min_assertions
    ato_files = sorted(src_root.rglob("*.ato"))
    if len(ato_files) < min_files:
        raise GateError(
            f"scope evaporated -- {len(ato_files)} .ato file(s) found under "
            f"{src_root}, expected at least {min_files}. A gate that scans "
            f"nothing passes vacuously; refusing."
        )
    try:
        definitions = parse_tree(src_root, repo_root)
    except ParseError as exc:
        raise GateError(f"{exc}") from exc

    design = Design(definitions)
    by_definition = {
        assertion_id: definition
        for definition in design.unique_definitions
        for assertion_id in (id(a) for a in definition.assertions)
    }
    assertions = design.assertions()
    if len(assertions) < min_assertions:
        raise GateError(
            f"scope evaporated -- {len(assertions)} assertion(s) parsed from "
            f"{src_root}, expected at least {min_assertions}. Either the sources "
            f"lost their assertions or the reader stopped understanding them; "
            f"either way this gate must not report a clean scan."
        )

    check_no_instance_overrides(design)

    findings: list[Finding] = []
    stats = {
        "assertions": len(assertions),
        "files": len(ato_files),
        "satisfied": 0,
        "indeterminate": 0,
    }
    for assertion in assertions:
        definition = by_definition[id(assertion)]
        analysis = analyse(design, definition, assertion)

        tie = tie_margin_detail(design, definition, assertion)
        if tie:
            findings.append(Finding("TIE_MARGIN", assertion, tie))

        if not analysis.flipping:
            findings.append(  # TAUTOLOGY
                Finding(
                    "TAUTOLOGY",
                    assertion,
                    f"outcome stays {analysis.baseline} under perturbation of every "
                    f"one of its {len(analysis.leaves)} operand(s) across 1e-6..1e6 "
                    f"-- this assertion cannot fail under any edit to the design",
                )
            )
        else:
            circuit_flips = [
                key
                for key in analysis.flipping
                if analysis.leaves[key].role == ROLE_CIRCUIT
            ]
            if not circuit_flips:
                findings.append(  # NO_CIRCUIT_COUPLING
                    Finding(
                        "NO_CIRCUIT_COUPLING",
                        assertion,
                        no_circuit_coupling_detail(analysis),
                    )
                )
            else:
                stats["satisfied"] = int(stats["satisfied"]) + 1
                # Non-vacuity is *earned*, not assumed: record the concrete
                # perturbation that makes this assertion false. An assertion
                # with no witness is exactly what the ledgered kinds are.
                findings.append(  # SATISFIED
                    Finding(
                        "SATISFIED",
                        assertion,
                        f"currently {analysis.baseline}; falsifiable by a circuit change",
                        witness=analysis.flipping[circuit_flips[0]],
                    )
                )

        if analysis.baseline == FALSE:
            # Not vacuity -- its opposite. Reported here because the perturbation
            # classifier would otherwise file a *failing* assertion under
            # SATISFIED ("can fail, currently passes"), which is exactly the
            # wrong verdict. Zero of these exist today, so this is blocking.
            findings.append(  # VIOLATED
                Finding(
                    "VIOLATED",
                    assertion,
                    "evaluates FALSE across the declared tolerance intervals -- "
                    "this assertion is not merely un-falsifiable, it is violated",
                )
            )

        if analysis.baseline == INDET:
            stats["indeterminate"] = int(stats["indeterminate"]) + 1
            findings.append(  # INDETERMINATE
                Finding(
                    "INDETERMINATE",
                    assertion,
                    "not decidable across the declared tolerance intervals -- the "
                    "assertion is neither provably true nor provably false as written",
                )
            )
    return findings, stats


def check_no_instance_overrides(design: Design) -> None:
    """Fail if an enclosing module numerically overrides an asserted quantity.

    Assertions are evaluated in their defining module's scope.  That is only
    sound while no instantiation site rewrites a value the assertion reads --
    ``Top`` doing ``power_in.v_bus_half = 200V`` would make every
    ``PowerInput``-local evaluation wrong.  Rather than silently report numbers
    from the wrong scope, the gate refuses.
    """
    asserted_paths: set[tuple[str, tuple[str, ...]]] = set()
    for definition in design.unique_definitions:
        for assertion in definition.assertions:
            for ref in walk_refs(assertion.expr):
                asserted_paths.add((definition.name, ref.path))

    conflicts: list[str] = []
    for definition in design.unique_definitions:
        for target in definition.deep_assignments:
            if len(target) < 2:
                continue
            instance_type = definition.instances.get(target[0])
            if instance_type is None:
                continue
            inner = design.definitions.get(instance_type)
            if inner is None:
                continue
            for owner, path in asserted_paths:
                if owner == inner.name and path == target[1:]:
                    conflicts.append(
                        f"{definition.file}: {definition.name} overrides "
                        f"{'.'.join(target)}, which {inner.name} asserts on"
                    )
    if conflicts:
        raise GateError(
            "instantiation-site override of an asserted quantity; definition-local "
            "evaluation would be wrong:\n  " + "\n  ".join(sorted(set(conflicts)))
        )


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

LEDGER_HEADER = """\
# Assertions in elec/**/*.ato that this gate found cannot fail, or cannot be
# decided. See scripts/check_ato_assertion_vacuity.py for what this file is
# and why it is a ratchet rather than a suppression list.
#
# Format: <KIND>|<file>::<module>::<assert source> <count>
# Regenerate with:
#   uv run python scripts/check_ato_assertion_vacuity.py --write-inventory
#
# This ledger is expected to SHRINK. An entry that no longer fires is a
# FAILURE, not a pass: record the fix in the same commit. Every line here is
# an electrical question for the power-stage owner.
#
# KINDS, in descending sharpness:
#   VIOLATED            evaluates FALSE as written
#   TAUTOLOGY           outcome invariant under perturbation of every operand
#   TIE_MARGIN          decided by an exact numeric tie; zero margin
#   NO_CIRCUIT_COUPLING no component value can falsify it
#   INDETERMINATE       undecidable across the declared tolerance intervals
#
# Nothing may be added here by hand. Anything NOT listed here fails the build,
# so a newly written vacuous assertion is blocked from commit one.
"""

#: Every finding kind is ledgered. Uniform treatment is deliberate: a gate
#: with a "blocking" tier that is red on the day it lands gets disabled, and a
#: disabled gate detects nothing. Ratcheting all four kinds makes the gate
#: green on today's tree and blocking for every new or edited assertion.
LEDGERED_KINDS = (
    "VIOLATED",
    "TAUTOLOGY",
    "TIE_MARGIN",
    "NO_CIRCUIT_COUPLING",
    "INDETERMINATE",
)


def load_ledger(path: Path) -> dict[str, int]:
    entries: dict[str, int] = {}
    if not path.exists():
        return entries
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, _, count = line.rpartition(" ")
        if not key:
            raise GateError(f"malformed ledger line in {path}: {raw!r}")
        try:
            entries[key.strip()] = int(count)
        except ValueError as exc:
            raise GateError(f"malformed ledger count in {path}: {raw!r}") from exc
    return entries


def write_ledger(path: Path, findings: list[Finding]) -> int:
    counts: dict[str, int] = {}
    for finding in findings:
        if finding.kind not in LEDGERED_KINDS:
            continue
        counts[finding.key] = counts.get(finding.key, 0) + 1
    lines = [LEDGER_HEADER]
    for key in sorted(counts):
        lines.append(f"{key} {counts[key]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(counts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None, help="repository root")
    parser.add_argument("--src", type=Path, default=None, help="directory of .ato sources")
    parser.add_argument("--inventory", type=Path, default=None, help="ledger path")
    parser.add_argument(
        "--write-inventory",
        action="store_true",
        help="regenerate the shrink-only ledger from the current tree",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="print the full inventory, including ledgered and satisfied assertions",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root or find_repo_root(Path(__file__).resolve().parent)
    src_root = args.src or (root / DEFAULT_SRC)
    ledger_path = args.inventory or (root / DEFAULT_INVENTORY)

    try:
        findings, stats = find_violations(src_root, root)
    except (GateError, UnitError) as exc:
        print(f"GATE ERROR: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    ledgered = [f for f in findings if f.kind in LEDGERED_KINDS]

    if args.write_inventory:
        written = write_ledger(ledger_path, findings)
        print(f"wrote {written} ledger entries to {ledger_path}")
        return EXIT_OK

    if args.report:
        print_report(findings, stats)

    ledger = load_ledger(ledger_path)
    seen: dict[str, int] = {}
    for finding in ledgered:
        seen[finding.key] = seen.get(finding.key, 0) + 1

    new_sites = [f for f in ledgered if ledger.get(f.key, 0) == 0]
    grew = sorted(
        (key, ledger[key], count)
        for key, count in seen.items()
        if key in ledger and count > ledger[key]
    )
    shrank = sorted(
        (key, ledger[key], seen[key])
        for key in ledger
        if key in seen and seen[key] < ledger[key]
    )
    stale = sorted(key for key in ledger if key not in seen)

    if not (new_sites or grew or shrank or stale):
        counts = tally_kinds(findings)
        print(
            f"OK: {stats['assertions']} assertion(s) across {stats['files']} .ato "
            f"file(s). {stats['satisfied']} genuinely constrain a circuit-derived "
            f"quantity (each has a recorded falsifying witness). "
            f"{len(ledgered)} ledgered."
        )
        print(
            "  RECORDED DEBT: "
            + ", ".join(f"{kind}={counts.get(kind, 0)}" for kind in LEDGERED_KINDS)
        )
        print(
            "  Every one of those is an assertion that cannot fail (or cannot be "
            "decided) as written. They are recorded, not resolved."
        )
        return EXIT_OK

    print("FAIL: .ato assertion vacuity gate\n")
    for finding in new_sites:
        print(f"NEW_SITE             {finding.render()}")
    for key, was, now in grew:
        print(f"COUNT_GREW           {key}: {was} -> {now}")
    for key, was, now in shrank:
        print(f"COUNT_SHRANK         {key}: {was} -> {now} (record the fix)")
    for key in stale:
        print(f"STALE_ENTRY          {key} no longer fires (record the fix)")
    print(
        "\nNEW_SITE means an assertion that cannot fail was added or edited. Fix the "
        "assertion -- compare it against a quantity derived from the circuit, or give "
        "the band a real margin. Do not delete it, and do not hand-edit the ledger.\n"
        "STALE_ENTRY / COUNT_SHRANK mean debt was paid down: rerun --write-inventory "
        "in the same commit so the fix shows up in the diff."
    )
    return EXIT_FINDING


def tally_kinds(findings: list[Finding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.kind] = counts.get(finding.kind, 0) + 1
    return counts


def print_report(findings: list[Finding], stats: dict[str, object]) -> None:
    print("=" * 78)
    print("ATO ASSERTION VACUITY INVENTORY")
    print("=" * 78)
    print(
        f"{stats['assertions']} assertion(s) in {stats['files']} .ato file(s); "
        f"{stats['satisfied']} are circuit-coupled (not reported)."
    )
    by_kind: dict[str, list[Finding]] = {}
    for finding in findings:
        by_kind.setdefault(finding.kind, []).append(finding)
    for kind in LEDGERED_KINDS:
        group = by_kind.get(kind, [])
        print(f"\n--- {kind}: {len(group)} ---")
        for finding in group:
            print(f"  {finding.render()}")
    satisfied = by_kind.get("SATISFIED", [])
    print(f"\n--- SATISFIED (not vacuous, with falsifying witness): {len(satisfied)} ---")
    for finding in satisfied:
        print(f"  {finding.render()}")
        print(f"      witness: {finding.witness}")
    print("=" * 78)


if __name__ == "__main__":
    raise SystemExit(main())
