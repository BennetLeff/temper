#!/usr/bin/env python3
"""Constraint mutation runner — inject R4 bug-class mutations into CP-SAT encoders.

R32 / KTD1 / KTD2: each PCL constraint encoding (the 8 handlers in
``temper_placer/placer/cp_sat/handlers/``) is mutated with one of the R4
fail-capable bug classes — sign flip, dropped term, loosened bound,
off-by-one, double-count — and the encoding's own existing defenses
(encoder unit tests + the post-solve ``PlacementAuditor``) must catch it.

Design:
- Mutations are applied at SOURCE level: the handler module's text is parsed
  into an AST, the bug is injected by an AST transform, and the mutated source
  is ``exec``-ed as a fresh module. The handler's ``@register_handler``
  decorator then replaces the real function in ``HANDLER_REGISTRY`` — no
  runtime monkeypatching of the live encoder.
- Each mutation must actually change the encoder's output on a probe input
  (the model proto differs from the unmutated encoder's); a mutation that
  leaves the proto identical is a no-op and is rejected, not counted as a
  survivor.
- Kill detection runs the per-surface defense subset (never the whole test
  suite — the per-mutation CI cost model): the encoder-unit-test mirror and
  the post-solve auditor. A mutation is *killed* when at least one defense
  fails, *survived* when all pass.
- The solver inside the defense harnesses is pinned
  (``num_search_workers=1``, fixed ``random_seed``) so kill verdicts are
  reproducible. The assertions mirror the existing encoder tests exactly;
  only the solver parameters differ from ``CpSatModel.solve``'s 8-worker
  default (see ``_pinned_solve``).

Output: a per-encoding, per-mutation killed/survived classification with
bug-class labels. ``--write-register <path>`` emits the kill-set register
YAML (U2) that ``scripts/constraint_mutation_gate.py`` enforces.

Usage:
    python scripts/constraint_mutation_runner.py [--write-register power_pcb_dataset/constraint_kill_sets.yaml]
"""

from __future__ import annotations

import argparse
import ast
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
HANDLERS_DIR = (
    REPO_ROOT
    / "packages/temper-placer/src/temper_placer/placer/cp_sat/handlers"
)

VALID_OPERATORS = (
    "sign-flip",
    "dropped-term",
    "loosened-bound",
    "off-by-one",
    "double-count",
)

# Fixed solver seed for reproducible kill verdicts (CI cost model: every
# mutation runs only its surface's defense subset, each a small CP-SAT solve).
SOLVER_SEED = 20260802

# Router-V6 topology family: registered as deferred (see the register).
# The esl/BMC defense machinery that would kill mutations against these
# encodings was removed (plan 2026-08-02-005's verified assumption); the
# mutation suite measures existing defenses only, so this family is
# registered rather than force-fed a kill set.
ROUTER_V6_CLASSES = (
    "CapacityConstraint",
    "DiffPairConstraint",
    "LayerConstraint",
    "ChannelSeparationConstraint",
)
ROUTER_V6_DEFERRED_REASON = (
    "The router-V6 topology family's ESL/BMC defense machinery (esl.py, bmc.py, "
    "test_bmc_*.py) was removed in commit 772776115; without those defenses there "
    "is nothing for a mutation to be killed against. The mutation suite measures "
    "existing defenses only (KTD2), and plan 2026-08-02-005 (which restores the "
    "family's exhaustive ground truth) is not landing in this changeset. Once the "
    "family regains defenses, move these entries from deferred to active with a "
    "non-empty killed set. The family is also slated for review under the Wave 4 "
    "Rust migration."
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class HandlerSurface:
    """One PCL handler encoder discovered in ``handlers/``."""

    surface_id: str  # module stem, e.g. "separated"
    constraint_type: str  # ConstraintType value, e.g. "SEPARATED"
    handler_fn: str  # encoder function name, e.g. "encode_separated"
    module_path: Path


@dataclass
class MutationSpec:
    """One concrete mutation of a handler surface."""

    mutation_id: str
    operator: str  # one of VALID_OPERATORS
    description: str
    transform: object  # callable(ast.Module) -> ast.Module


@dataclass
class Defense:
    """One existing defense scenario for a surface (encoder-test mirror or auditor)."""

    name: str  # e.g. "encoder-unit:TestSeparated::test_separated_enforces_clearance"
    kind: str  # "encoder-unit" | "placement-auditor"
    description: str
    run: object  # callable() -> None; raises AssertionError on violation


@dataclass
class Scenario:
    """A probe problem shared by the no-op check and the defenses."""

    name: str
    description: str
    build: object  # callable() -> (CpSatModel, list[BaseConstraint], EncoderContext)


@dataclass
class MutationResult:
    """Outcome of applying one mutation to one surface."""

    surface_id: str
    constraint_type: str
    mutation_id: str
    operator: str
    description: str
    outcome: str  # "killed" | "survived" | "no-op" | "error"
    defenses_fired: list[str] = field(default_factory=list)
    detail: str = ""


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _remove_statement(tree: ast.Module, pred) -> bool:
    """Remove the first statement satisfying *pred* from its parent body."""
    parents = _parent_map(tree)
    for node in list(ast.walk(tree)):
        if isinstance(node, ast.stmt) and pred(node):
            parent = parents.get(node)
            if parent is None:
                continue
            for attr in ("body", "orelse", "finalbody"):
                body = getattr(parent, attr, None)
                if isinstance(body, list) and node in body:
                    body.remove(node)
                    if not body:  # keep the block valid (e.g. a lone if/elif branch)
                        body.append(ast.Pass())
                    return True
    return False


def _find_call_stmt(tree: ast.Module, func_attr: str, arg_pred=None):
    """Return the first Expr statement whose Call targets *func_attr* (and optionally matches *arg_pred*)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute) and call.func.attr == func_attr:
                if arg_pred is None or arg_pred(call):
                    return node
    return None


def _wrap_assign_value(tree: ast.Module, target_name: str, wrap) -> bool:
    """Wrap the value of ``<target_name> = <value>`` in ``wrap(value)``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == target_name for t in node.targets
        ):
            node.value = wrap(node.value)
            return True
    return False


def _flip_compare_ops(tree: ast.Module, pred, new_op) -> int:
    """Flip the comparison operator of every Compare matching *pred* to *new_op*."""
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and pred(node) and node.ops:
            node.ops = [new_op]
            count += 1
    return count


def _make_floor_div(value: ast.AST, divisor: int) -> ast.AST:
    return ast.BinOp(left=value, op=ast.FloorDiv(), right=ast.Constant(divisor))


# ---------------------------------------------------------------------------
# Mutation transforms (per surface; AST-based, source-level)
# ---------------------------------------------------------------------------

# Each transform receives the parsed module and returns the mutated module.


def _separated_transforms() -> dict[str, MutationSpec]:
    def sign_flip_x(tree: ast.Module) -> ast.Module:
        n = 0
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Compare)
                and isinstance(node.ops[0], ast.LtE)
                and isinstance(node.left, ast.BinOp)
                and isinstance(node.left.op, ast.Add)
                and isinstance(node.left.right, ast.Name)
                and node.left.right.id == "margin"
                and isinstance(node.left.left, ast.Attribute)
                and node.left.left.attr in ("x_end", "x_start")
            ):
                node.left.op = ast.Sub()
                n += 1
        assert n == 2, f"expected 2 x-axis margin adds, flipped {n}"
        return tree

    def drop_y_ok(tree: ast.Module) -> ast.Module:
        removed = _remove_statement(
            tree,
            lambda s: (
                isinstance(s, ast.Expr)
                and isinstance(s.value, ast.Call)
                and isinstance(s.value.func, ast.Attribute)
                and s.value.func.attr == "AddBoolOr"
                and any("y_ok.Not()" in ast.unparse(a) for a in s.value.args)
            ),
        )
        assert removed, "y_ok definitional clause not found"
        return tree

    def loosened_margin(tree: ast.Module) -> ast.Module:
        assert _wrap_assign_value(tree, "margin", lambda v: _make_floor_div(v, 2))
        return tree

    def off_by_one_x(tree: ast.Module) -> ast.Module:
        # a.x_end + margin <= b.x_start  ->  a.x_end + margin - 1 <= b.x_start
        n = 0
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Compare)
                and isinstance(node.ops[0], ast.LtE)
                and isinstance(node.left, ast.BinOp)
                and isinstance(node.left.op, ast.Add)
                and isinstance(node.left.right, ast.Name)
                and node.left.right.id == "margin"
                and isinstance(node.left.left, ast.Attribute)
                and node.left.left.attr in ("x_end", "x_start")
            ):
                node.left = ast.BinOp(
                    left=node.left, op=ast.Sub(), right=ast.Constant(1)
                )
                n += 1
        assert n == 2, f"expected 2 x-axis adds, shifted {n}"
        return tree

    return {
        "sep_sign_flip_x_margin": MutationSpec(
            "sep_sign_flip_x_margin",
            "sign-flip",
            "x-axis separation margin sign flipped on both direction constraints "
            "(a.x_end + margin <= b.x_start becomes a.x_end - margin <= b.x_start): "
            "components may overlap by up to the margin on x",
            sign_flip_x,
        ),
        "sep_drop_y_ok_clause": MutationSpec(
            "sep_drop_y_ok_clause",
            "dropped-term",
            "y_ok definitional clause AddBoolOr([y_ok.Not(), below, above]) dropped: "
            "y_ok becomes a free literal, so the final x_ok ∨ y_ok disjunction is "
            "satisfiable without any y separation (the weak-nooverlap2d class)",
            drop_y_ok,
        ),
        "sep_loosened_margin": MutationSpec(
            "sep_loosened_margin",
            "loosened-bound",
            "min_distance_mm margin halved before mm_to_units: the enforced "
            "Chebyshev clearance is half the stated requirement",
            loosened_margin,
        ),
        "sep_off_by_one_x": MutationSpec(
            "sep_off_by_one_x",
            "off-by-one",
            "x-axis direction bounds loosened by one grid unit "
            "(margin - 1): a 0.01 mm fencepost error in the x separation",
            off_by_one_x,
        ),
    }


def _enclosing_transforms() -> dict[str, MutationSpec]:
    def sign_flip_y_min(tree: ast.Module) -> ast.Module:
        # v.y_start >= zy_min_u + margin_u  ->  v.y_start <= zy_min_u + margin_u
        def is_y_start(node: ast.AST) -> bool:
            return (
                isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Attribute)
                and node.left.attr == "y_start"
            )

        flipped = _flip_compare_ops(tree, is_y_start, ast.LtE())
        assert flipped == 1, f"expected 1 y_start comparison, flipped {flipped}"
        return tree

    def drop_y_start(tree: ast.Module) -> ast.Module:
        removed = _remove_statement(
            tree,
            lambda s: (
                isinstance(s, ast.Expr)
                and isinstance(s.value, ast.Call)
                and isinstance(s.value.func, ast.Attribute)
                and s.value.func.attr == "add_constraint_enforced"
                and s.value.args
                and isinstance(s.value.args[0], ast.Compare)
                and isinstance(s.value.args[0].left, ast.Attribute)
                and s.value.args[0].left.attr == "y_start"
            ),
        )
        assert removed, "y_start bound not found"
        return tree

    def loosened_margin(tree: ast.Module) -> ast.Module:
        assert _wrap_assign_value(tree, "margin_u", lambda v: _make_floor_div(v, 2))
        return tree

    def off_by_one_margin(tree: ast.Module) -> ast.Module:
        assert _wrap_assign_value(
            tree, "margin_u", lambda v: ast.BinOp(left=v, op=ast.Sub(), right=ast.Constant(1))
        )
        return tree

    return {
        "enc_sign_flip_y_min": MutationSpec(
            "enc_sign_flip_y_min",
            "sign-flip",
            "y_min bound direction flipped (v.y_start >= zy_min_u + margin_u becomes "
            "v.y_start <= zy_min_u + margin_u): the component is pushed toward/out of "
            "the zone bottom instead of kept inside",
            sign_flip_y_min,
        ),
        "enc_drop_y_start": MutationSpec(
            "enc_drop_y_start",
            "dropped-term",
            "v.y_start >= zy_min_u + margin_u dropped: the component may start below "
            "the zone's lower boundary",
            drop_y_start,
        ),
        "enc_loosened_margin": MutationSpec(
            "enc_loosened_margin",
            "loosened-bound",
            "zone margin halved before mm_to_units: the enforced inset is half the "
            "stated margin, so components may sit closer to the zone edge",
            loosened_margin,
        ),
        "enc_off_by_one_margin": MutationSpec(
            "enc_off_by_one_margin",
            "off-by-one",
            "zone margin loosened by one grid unit (margin_u - 1): a 0.01 mm "
            "fencepost error in the margin comparison",
            off_by_one_margin,
        ),
    }


def _adjacent_transforms() -> dict[str, MutationSpec]:
    def _first_x_edge_compare(node: ast.AST) -> bool:
        # the FIRST edge-to-edge x bound is va.x_start - vb.x_end <= max_d
        return (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.BinOp)
            and isinstance(node.left.op, ast.Sub)
            and isinstance(node.left.left, ast.Attribute)
            and node.left.left.attr == "x_start"
            and isinstance(node.left.left.value, ast.Name)
            and node.left.left.value.id == "va"
            and isinstance(node.left.right, ast.Attribute)
            and node.left.right.attr == "x_end"
            and len(node.comparators) == 1
            and isinstance(node.comparators[0], ast.Name)
            and node.comparators[0].id == "max_d"
        )

    def sign_flip_comparison(tree: ast.Module) -> ast.Module:
        flipped = _flip_compare_ops(tree, _first_x_edge_compare, ast.GtE())
        assert flipped == 1, f"expected 1 x-direction bound, flipped {flipped}"
        return tree

    def drop_x_direction(tree: ast.Module) -> ast.Module:
        # The two edge-to-edge x constraints are
        #   va.x_start - vb.x_end <= max_d   (a-left-of-b direction)
        #   vb.x_start - va.x_end <= max_d   (b-left-of-a direction)
        # Drop the second so the pair may drift arbitrarily far apart in the
        # b-right-of-a direction.
        removed = _remove_statement(
            tree,
            lambda s: (
                isinstance(s, ast.Expr)
                and isinstance(s.value, ast.Call)
                and isinstance(s.value.func, ast.Attribute)
                and s.value.func.attr == "add_constraint_enforced"
                and s.value.args
                and isinstance(s.value.args[0], ast.Compare)
                and isinstance(s.value.args[0].left, ast.BinOp)
                and isinstance(s.value.args[0].left.left, ast.Attribute)
                and s.value.args[0].left.left.attr == "x_start"
                and isinstance(s.value.args[0].left.left.value, ast.Name)
                and s.value.args[0].left.left.value.id == "vb"
                and isinstance(s.value.args[0].left.right, ast.Attribute)
                and s.value.args[0].left.right.attr == "x_end"
                and isinstance(s.value.args[0].left.right.value, ast.Name)
                and s.value.args[0].left.right.value.id == "va"
            ),
        )
        assert removed, "second x-direction bound not found"
        return tree

    def loosened_bound(tree: ast.Module) -> ast.Module:
        assert _wrap_assign_value(
            tree, "max_d", lambda v: ast.BinOp(left=ast.Constant(2), op=ast.Mult(), right=v)
        )
        return tree

    def off_by_one(tree: ast.Module) -> ast.Module:
        assert _wrap_assign_value(
            tree, "max_d", lambda v: ast.BinOp(left=v, op=ast.Add(), right=ast.Constant(1))
        )
        return tree

    return {
        "adj_sign_flip_comparison": MutationSpec(
            "adj_sign_flip_comparison",
            "sign-flip",
            "first edge-to-edge x bound direction flipped (va.x_start - vb.x_end <= max_d "
            "becomes >= max_d): the proximity cap becomes a minimum-distance floor on x",
            sign_flip_comparison,
        ),
        "adj_drop_x_direction": MutationSpec(
            "adj_drop_x_direction",
            "dropped-term",
            "second edge-to-edge x bound (vb.x_start - va.x_end <= max_d) dropped: "
            "the pair may drift arbitrarily far apart in the b-right-of-a direction",
            drop_x_direction,
        ),
        "adj_loosened_bound": MutationSpec(
            "adj_loosened_bound",
            "loosened-bound",
            "max_distance_mm doubled before mm_to_units: the enforced proximity cap "
            "is twice the stated requirement",
            loosened_bound,
        ),
        "adj_off_by_one": MutationSpec(
            "adj_off_by_one",
            "off-by-one",
            "max_distance_mm loosened by one grid unit (max_d + 1): a 0.01 mm "
            "fencepost error in the proximity cap",
            off_by_one,
        ),
    }


def _onside_transforms() -> dict[str, MutationSpec]:
    def _left_bound_compare(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Attribute)
            and node.left.attr == "x_start"
            and len(node.comparators) == 1
            and isinstance(node.comparators[0], ast.BinOp)
            and isinstance(node.comparators[0].op, ast.Add)
            and isinstance(node.comparators[0].right, ast.Name)
            and node.comparators[0].right.id == "max_d_u"
        )

    def sign_flip_bound(tree: ast.Module) -> ast.Module:
        n = 0
        for node in ast.walk(tree):
            if _left_bound_compare(node):
                node.comparators[0].op = ast.Sub()
                n += 1
        assert n == 1, f"expected 1 left bound, flipped {n}"
        return tree

    def drop_constraint(tree: ast.Module) -> ast.Module:
        removed = _remove_statement(
            tree,
            lambda s: (
                isinstance(s, ast.Expr)
                and isinstance(s.value, ast.Call)
                and isinstance(s.value.func, ast.Attribute)
                and s.value.func.attr == "add_constraint_enforced"
                and s.value.args
                and isinstance(s.value.args[0], ast.Compare)
                and isinstance(s.value.args[0].left, ast.Attribute)
                and s.value.args[0].left.attr == "x_start"
            ),
        )
        assert removed, "left-side onside bound not found"
        return tree

    def loosened_bound(tree: ast.Module) -> ast.Module:
        assert _wrap_assign_value(
            tree, "max_d_u", lambda v: ast.BinOp(left=ast.Constant(2), op=ast.Mult(), right=v)
        )
        return tree

    def off_by_one(tree: ast.Module) -> ast.Module:
        assert _wrap_assign_value(
            tree, "max_d_u", lambda v: ast.BinOp(left=v, op=ast.Add(), right=ast.Constant(1))
        )
        return tree

    return {
        "oside_sign_flip_bound": MutationSpec(
            "oside_sign_flip_bound",
            "sign-flip",
            "left-edge bound sign flipped (v.x_start <= board_x_min + max_d_u becomes "
            "v.x_start <= board_x_min - max_d_u): the margin is subtracted, pushing the "
            "allowed start negative (infeasible)",
            sign_flip_bound,
        ),
        "oside_drop_constraint": MutationSpec(
            "oside_drop_constraint",
            "dropped-term",
            "left-edge onside bound dropped entirely: the component is no longer "
            "pinned near the left edge",
            drop_constraint,
        ),
        "oside_loosened_bound": MutationSpec(
            "oside_loosened_bound",
            "loosened-bound",
            "max_distance_mm doubled before mm_to_units: components may sit twice as "
            "far from the edge as stated",
            loosened_bound,
        ),
        "oside_off_by_one": MutationSpec(
            "oside_off_by_one",
            "off-by-one",
            "max_distance_mm loosened by one grid unit (max_d_u + 1): a 0.01 mm "
            "fencepost error in the edge-distance cap",
            off_by_one,
        ),
    }


def _anchored_transforms() -> dict[str, MutationSpec]:
    def sign_flip_y_pos(tree: ast.Module) -> ast.Module:
        n = 0
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Compare)
                and isinstance(node.ops[0], ast.Eq)
                and isinstance(node.left, ast.Attribute)
                and node.left.attr == "y_center"
                and len(node.comparators) == 1
                and isinstance(node.comparators[0], ast.Name)
                and node.comparators[0].id == "py_u"
            ):
                node.comparators[0] = ast.UnaryOp(op=ast.USub(), operand=ast.Name(id="py_u"))
                n += 1
        assert n == 1, f"expected 1 y_center equality, flipped {n}"
        return tree

    def drop_y_center(tree: ast.Module) -> ast.Module:
        removed = _remove_statement(
            tree,
            lambda s: (
                isinstance(s, ast.Expr)
                and isinstance(s.value, ast.Call)
                and isinstance(s.value.func, ast.Attribute)
                and s.value.func.attr == "add_constraint_enforced"
                and s.value.args
                and isinstance(s.value.args[0], ast.Compare)
                and isinstance(s.value.args[0].left, ast.Attribute)
                and s.value.args[0].left.attr == "y_center"
            ),
        )
        assert removed, "y_center equality not found"
        return tree

    def off_by_one_x(tree: ast.Module) -> ast.Module:
        n = 0
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Compare)
                and isinstance(node.ops[0], ast.Eq)
                and isinstance(node.left, ast.Attribute)
                and node.left.attr == "x_center"
                and len(node.comparators) == 1
                and isinstance(node.comparators[0], ast.Name)
                and node.comparators[0].id == "px_u"
            ):
                node.comparators[0] = ast.BinOp(
                    left=ast.Name(id="px_u"), op=ast.Add(), right=ast.Constant(1)
                )
                n += 1
        assert n == 1, f"expected 1 x_center equality, shifted {n}"
        return tree

    return {
        "anchor_sign_flip_y_pos": MutationSpec(
            "anchor_sign_flip_y_pos",
            "sign-flip",
            "y position sign flipped (v.y_center == py_u becomes v.y_center == -py_u): "
            "the anchor target is negative, which no valid IntVar can equal",
            sign_flip_y_pos,
        ),
        "anchor_drop_y_center": MutationSpec(
            "anchor_drop_y_center",
            "dropped-term",
            "v.y_center == py_u dropped: the component's y coordinate is unanchored",
            drop_y_center,
        ),
        "anchor_off_by_one_x": MutationSpec(
            "anchor_off_by_one_x",
            "off-by-one",
            "x anchor target shifted by one grid unit (px_u + 1): a 0.01 mm "
            "fencepost error in the anchor position",
            off_by_one_x,
        ),
    }


def _keepout_transforms() -> dict[str, MutationSpec]:
    def drop_no_overlap(tree: ast.Module) -> ast.Module:
        removed = _remove_statement(
            tree,
            lambda s: (
                isinstance(s, ast.Expr)
                and isinstance(s.value, ast.Call)
                and isinstance(s.value.func, ast.Attribute)
                and s.value.func.attr == "AddNoOverlap2D"
            ),
        )
        assert removed, "AddNoOverlap2D statement not found"
        return tree

    def sign_flip_start(tree: ast.Module) -> ast.Module:
        n = 0
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "kx_s" for t in node.targets)
                and isinstance(node.value, ast.BinOp)
                and isinstance(node.value.op, ast.Sub)
            ):
                node.value = ast.BinOp(
                    left=node.value.right, op=ast.Sub(), right=node.value.left
                )
                n += 1
        assert n == 1, f"expected 1 kx_s assignment, flipped {n}"
        return tree

    def loosened_interval(tree: ast.Module) -> ast.Module:
        assert _wrap_assign_value(
            tree, "kx_w", lambda v: _make_floor_div(v, 2)
        ), "kx_w assignment not found"
        assert _wrap_assign_value(tree, "ky_h", lambda v: _make_floor_div(v, 2))
        return tree

    def double_count_margin(tree: ast.Module) -> ast.Module:
        n = 0
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id in ("kx_w", "ky_h") for t in node.targets)
                and isinstance(node.value, ast.BinOp)
                and isinstance(node.value.op, ast.Add)
                and isinstance(node.value.right, ast.BinOp)
                and isinstance(node.value.right.op, ast.Mult)
                and isinstance(node.value.right.left, ast.Constant)
                and node.value.right.left.value == 2
            ):
                node.value.right.left = ast.Constant(4)
                n += 1
        assert n == 2, f"expected 2 margin-doubled sizes, mutated {n}"
        return tree

    return {
        "keepout_drop_no_overlap": MutationSpec(
            "keepout_drop_no_overlap",
            "dropped-term",
            "AddNoOverlap2D statement dropped: the keepout interval is created but "
            "never enforced, so components may overlap the keepout zone",
            drop_no_overlap,
        ),
        "keepout_sign_flip_start": MutationSpec(
            "keepout_sign_flip_start",
            "sign-flip",
            "keepout start sign flipped (kx_s = mm_to_units(zx_min) - margin_u becomes "
            "kx_s = margin_u - mm_to_units(zx_min)): the interval is mirrored about the "
            "origin",
            sign_flip_start,
        ),
        "keepout_loosened_interval": MutationSpec(
            "keepout_loosened_interval",
            "loosened-bound",
            "keepout interval size halved: the enforced keepout is half its stated "
            "extent (a looser constraint)",
            loosened_interval,
        ),
        "keepout_double_count_margin": MutationSpec(
            "keepout_double_count_margin",
            "double-count",
            "keepout margin counted twice (2 * margin_u becomes 4 * margin_u in both "
            "interval sizes): the keepout grows by two extra margins",
            double_count_margin,
        ),
    }


def _aligned_transforms() -> dict[str, MutationSpec]:
    def _first_axis_compare(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.BinOp)
            and isinstance(node.left.op, ast.Sub)
            and isinstance(node.left.left, ast.Name)
            and node.left.left.id == "cva"
            and isinstance(node.left.right, ast.Name)
            and node.left.right.id == "cvb"
        )

    def sign_flip_comparison(tree: ast.Module) -> ast.Module:
        flipped = _flip_compare_ops(tree, _first_axis_compare, ast.GtE())
        assert flipped == 1, f"expected 1 axis comparison, flipped {flipped}"
        return tree

    def drop_direction(tree: ast.Module) -> ast.Module:
        removed = _remove_statement(
            tree,
            lambda s: (
                isinstance(s, ast.Expr)
                and isinstance(s.value, ast.Call)
                and isinstance(s.value.func, ast.Attribute)
                and s.value.func.attr == "add_constraint_enforced"
                and s.value.args
                and isinstance(s.value.args[0], ast.Compare)
                and isinstance(s.value.args[0].left, ast.BinOp)
                and isinstance(s.value.args[0].left.left, ast.Name)
                and s.value.args[0].left.left.id == "cvb"
            ),
        )
        assert removed, "reverse-direction alignment bound not found"
        return tree

    def loosened_tol(tree: ast.Module) -> ast.Module:
        assert _wrap_assign_value(
            tree, "tol_u", lambda v: ast.BinOp(left=ast.Constant(2), op=ast.Mult(), right=v)
        )
        return tree

    def off_by_one(tree: ast.Module) -> ast.Module:
        assert _wrap_assign_value(
            tree, "tol_u", lambda v: ast.BinOp(left=v, op=ast.Add(), right=ast.Constant(1))
        )
        return tree

    return {
        "align_sign_flip_comparison": MutationSpec(
            "align_sign_flip_comparison",
            "sign-flip",
            "first axis alignment comparison flipped (cva - cvb <= tol_u becomes "
            "cva - cvb >= tol_u): the tolerance cap becomes a minimum-separation floor",
            sign_flip_comparison,
        ),
        "align_drop_direction": MutationSpec(
            "align_drop_direction",
            "dropped-term",
            "reverse-direction alignment bound (cvb - cva <= tol_u) dropped: one "
            "direction of the |diff| <= tol pair is unconstrained",
            drop_direction,
        ),
        "align_loosened_tol": MutationSpec(
            "align_loosened_tol",
            "loosened-bound",
            "tolerance doubled before mm_to_units: the enforced alignment tolerance "
            "is twice the stated requirement",
            loosened_tol,
        ),
        "align_off_by_one": MutationSpec(
            "align_off_by_one",
            "off-by-one",
            "tolerance loosened by one grid unit (tol_u + 1): a 0.01 mm fencepost "
            "error in the alignment tolerance",
            off_by_one,
        ),
    }


def _loop_area_transforms() -> dict[str, MutationSpec]:
    def _area_ceiling_compare(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name)
            and node.left.id == "area"
            and len(node.comparators) == 1
            and isinstance(node.comparators[0], ast.Name)
            and node.comparators[0].id == "max_area_units"
        )

    def sign_flip_ceiling(tree: ast.Module) -> ast.Module:
        flipped = _flip_compare_ops(tree, _area_ceiling_compare, ast.GtE())
        assert flipped == 1, f"expected 1 area ceiling, flipped {flipped}"
        return tree

    def drop_aabb_max_x(tree: ast.Module) -> ast.Module:
        removed = _remove_statement(
            tree,
            lambda s: (
                isinstance(s, ast.Expr)
                and isinstance(s.value, ast.Call)
                and isinstance(s.value.func, ast.Attribute)
                and s.value.func.attr == "add"
                and s.value.args
                and isinstance(s.value.args[0], ast.Compare)
                and isinstance(s.value.args[0].left, ast.Name)
                and s.value.args[0].left.id == "loop_x_max"
            ),
        )
        assert removed, "loop_x_max AABB bound not found"
        return tree

    def loosened_ceiling(tree: ast.Module) -> ast.Module:
        assert _wrap_assign_value(
            tree,
            "max_area_units",
            lambda v: ast.BinOp(left=ast.Constant(2), op=ast.Mult(), right=v),
        )
        return tree

    def double_count_units(tree: ast.Module) -> ast.Module:
        n = 0
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "max_area_units"
                    for t in node.targets
                )
                and isinstance(node.value, ast.BinOp)
                and isinstance(node.value.op, ast.Mult)
                and isinstance(node.value.right, ast.Attribute)
                and node.value.right.attr == "units_per_mm"
            ):
                node.value = ast.BinOp(
                    left=node.value, op=ast.Mult(), right=node.value.right
                )
                n += 1
        assert n == 1, f"expected 1 max_area_units conversion, mutated {n}"
        return tree

    def off_by_one(tree: ast.Module) -> ast.Module:
        # loosen by one unit: area <= max_area_units + 1
        n = 0
        for node in ast.walk(tree):
            if _area_ceiling_compare(node):
                node.comparators[0] = ast.BinOp(
                    left=ast.Name(id="max_area_units"),
                    op=ast.Add(),
                    right=ast.Constant(1),
                )
                n += 1
        assert n == 1, f"expected 1 area ceiling, shifted {n}"
        return tree

    return {
        "loop_sign_flip_ceiling": MutationSpec(
            "loop_sign_flip_ceiling",
            "sign-flip",
            "area ceiling direction flipped (area <= max_area_units becomes "
            "area >= max_area_units): the ceiling becomes a minimum-area floor",
            sign_flip_ceiling,
        ),
        "loop_drop_aabb_max_x": MutationSpec(
            "loop_drop_aabb_max_x",
            "dropped-term",
            "loop_x_max >= v.x_end dropped: the AABB's x maximum is unconstrained, "
            "so the computed width (and area) can understate the true loop extent",
            drop_aabb_max_x,
        ),
        "loop_loosened_ceiling": MutationSpec(
            "loop_loosened_ceiling",
            "loosened-bound",
            "max_area ceiling doubled: the enforced loop-area cap is twice the "
            "stated requirement",
            loosened_ceiling,
        ),
        "loop_double_count_units": MutationSpec(
            "loop_double_count_units",
            "double-count",
            "units_per_mm applied twice in the mm2 -> units2 ceiling conversion: "
            "the cap is multiplied by an extra units-per-mm factor",
            double_count_units,
        ),
        "loop_off_by_one": MutationSpec(
            "loop_off_by_one",
            "off-by-one",
            "area ceiling loosened by one grid unit (max_area_units + 1): a "
            "fencepost error in the area cap",
            off_by_one,
        ),
    }


# surface_id -> {mutation_id: MutationSpec}
MUTATION_CATALOG: dict[str, dict[str, MutationSpec]] = {
    "separated": _separated_transforms(),
    "enclosing": _enclosing_transforms(),
    "adjacent": _adjacent_transforms(),
    "onside": _onside_transforms(),
    "anchored": _anchored_transforms(),
    "keepout": _keepout_transforms(),
    "aligned": _aligned_transforms(),
    "loop_area": _loop_area_transforms(),
}


# ---------------------------------------------------------------------------
# Handler surface discovery (AST scan, bmc_adoption_gate shape)
# ---------------------------------------------------------------------------


def discover_handler_surfaces() -> list[HandlerSurface]:
    """AST-scan ``handlers/`` for ``@register_handler`` encoder functions."""
    surfaces: list[HandlerSurface] = []
    for path in sorted(HANDLERS_DIR.glob("*.py")):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Name)
                    and dec.func.id == "register_handler"
                    and dec.args
                    and isinstance(dec.args[0], ast.Attribute)
                    and dec.args[0].attr
                ):
                    surfaces.append(
                        HandlerSurface(
                            surface_id=path.stem,
                            constraint_type=dec.args[0].attr,
                            handler_fn=node.name,
                            module_path=path,
                        )
                    )
    return sorted(surfaces, key=lambda s: s.surface_id)


# ---------------------------------------------------------------------------
# Pinned solve (deterministic kill verdicts)
# ---------------------------------------------------------------------------


def _pinned_solve(model, time_limit_s: float = 1.0):
    """Solve *model* with pinned CP-SAT parameters for reproducible verdicts.

    Replicates ``CpSatModel.solve``'s result extraction (positions/sizes/
    rotations in grid units) but with ``num_search_workers=1`` and a fixed
    ``random_seed`` instead of the 8-worker default, so a mutation's
    killed/survived classification is stable across runs. No objective is
    set: every defense scenario here is a feasibility probe, matching the
    existing encoder tests.
    """
    from ortools.sat.python import cp_model

    from temper_placer.placer.cp_sat.model import CpSolverSolution, SolveStatus

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = SOLVER_SEED

    status = solver.Solve(model.model_ref)

    positions: dict[str, tuple[int, int]] = {}
    rotations: dict[str, int] = {}
    sizes: dict[str, tuple[int, int]] = {}

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for vars_ in model.components:
            ref = vars_.ref
            positions[ref] = (solver.Value(vars_.x_center), solver.Value(vars_.y_center))
            rotations[ref] = solver.Value(vars_.rot_ref) if vars_.rot_ref is not None else 0
            sizes[ref] = (solver.Value(vars_.x_size), solver.Value(vars_.y_size))

    unsat_labels: list[str] = []
    if status == cp_model.INFEASIBLE:
        insufficient = solver.SufficientAssumptionsForInfeasibility()
        labels = getattr(model, "_assumption_labels", {})
        unsat_labels = [labels.get(i, f"assumption_{i}") for i in insufficient]

    return CpSolverSolution(
        status=SolveStatus(status),
        objective_value=solver.ObjectiveValue(),
        positions=positions,
        rotations=rotations,
        sizes=sizes,
        solve_time_s=solver.WallTime(),
        unsat_assumptions=unsat_labels,
    )


def _placement_from_solve(model, sol, ctx):
    """Build an audit ``Placement`` from a solved model + encoder context."""
    from temper_placer.placer.cp_sat.audit import Placement

    return Placement(
        positions_mm={
            ref: (model.units_to_mm(x), model.units_to_mm(y))
            for ref, (x, y) in sol.positions.items()
        },
        sizes_mm={
            ref: (model.units_to_mm(w), model.units_to_mm(h))
            for ref, (w, h) in sol.sizes.items()
        },
        rotations=sol.rotations,
        board_w_mm=ctx.board_w_mm,
        board_h_mm=ctx.board_h_mm,
        zones=dict(ctx.zones),
        zone_components=dict(ctx.zone_components),
    )


# ---------------------------------------------------------------------------
# Defense scenarios + per-surface defense subsets
# ---------------------------------------------------------------------------


def _scenarios() -> dict[str, Scenario]:
    """Probe scenarios mirroring the existing encoder tests (test_encoder.py)."""

    from temper_placer.pcl.constraints import (
        AdjacentConstraint,
        AlignedConstraint,
        AnchoredConstraint,
        Axis,
        BoardSide,
        ConstraintTier,
        EdgeType,
        EnclosingConstraint,
        KeepoutConstraint,
        LoopAreaConstraint,
        OnSideConstraint,
        SeparatedConstraint,
    )
    from temper_placer.placer.cp_sat.encoder import EncoderContext

    def build_separated():
        model = _mk_model(["A", "B"], 200)
        c = SeparatedConstraint(
            "A", "B", min_distance_mm=5.0, tier=ConstraintTier.HARD,
            because="Isolation requirement per safety analysis",
        )
        return model, [c], EncoderContext(
            board_w_mm=30.0, board_h_mm=30.0, board_x_max_units=3000, board_y_max_units=3000
        )

    def build_enclosing():
        model = _mk_model(["Q1", "Q2"], 100)
        c = EnclosingConstraint(
            outer="HV_ZONE", inner=["Q1", "Q2"], tier=ConstraintTier.HARD,
            because="All high voltage parts must stay in HV safety zone for isolation",
        )
        return model, [c], EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0, board_x_max_units=2000, board_y_max_units=2000,
            zones={"HV_ZONE": (5.0, 5.0, 15.0, 15.0)},
        )

    def build_adjacent():
        model = _mk_model(["Q1", "Q2"], 100)
        c = AdjacentConstraint(
            "Q1", "Q2", max_distance_mm=10.0, tier=ConstraintTier.HARD,
            because="Half-bridge pair must be close to minimize loop area ind",
        )
        return model, [c], EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0, board_x_max_units=2000, board_y_max_units=2000
        )

    def build_onside():
        model = _mk_model(["J1"], 200)
        c = OnSideConstraint(
            components=["J1"], side=BoardSide.LEFT, edge=EdgeType.FLUSH,
            max_distance_mm=2.0, tier=ConstraintTier.HARD,
            because="Connector must be on left edge for external access housing",
        )
        return model, [c], EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0, board_x_max_units=2000, board_y_max_units=2000
        )

    def build_anchored():
        model = _mk_model(["U_MCU"], 300, bounds=(0, 0, 3000, 2000))
        c = AnchoredConstraint(
            component="U_MCU", tier=ConstraintTier.HARD, position=(15.0, 10.0),
            because="MCU must be centered in MCU zone for antenna clearance",
        )
        return model, [c], EncoderContext(
            board_w_mm=30.0, board_h_mm=20.0, board_x_max_units=3000, board_y_max_units=2000
        )

    def build_keepout():
        model = _mk_model(["A"], 200)
        c = KeepoutConstraint(
            zone_name="NO_FLY", tier=ConstraintTier.HARD,
            because="No components allowed in keepout for safety isolation zone",
        )
        return model, [c], EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0, board_x_max_units=2000, board_y_max_units=2000,
            zones={"NO_FLY": (4.0, 4.0, 6.0, 6.0)},
        )

    def build_aligned():
        model = _mk_model(["C1", "C2", "C3"], 80, width=80, height=50)
        c = AlignedConstraint(
            components=["C1", "C2", "C3"], axis=Axis.X, tolerance_mm=0.5,
            tier=ConstraintTier.HARD,
            because="Align decoupling capacitors for visual consistency and routing",
        )
        return model, [c], EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0, board_x_max_units=2000, board_y_max_units=2000
        )

    def build_loop_area():
        model = _mk_model(["C_BUS", "Q1", "Q2", "C_OUT"], 200, bounds=(0, 0, 5000, 5000))
        c = LoopAreaConstraint(
            loop_name="commutation", max_area_mm2=500.0, tier=ConstraintTier.HARD,
            because="Minimize commutation loop to reduce voltage overshoot and EMI emission",
        )
        return model, [c], EncoderContext(
            board_w_mm=50.0, board_h_mm=50.0, board_x_max_units=5000, board_y_max_units=5000,
            loop_components={"commutation": ["C_BUS", "Q1", "Q2", "C_OUT"]},
        )

    def build_keepout_origin_margin():
        model = _mk_model(["A"], 200)
        c = KeepoutConstraint(
            zone_name="ORIGIN_FLY", tier=ConstraintTier.HARD, margin_mm=1.0,
            because="No components allowed near origin keepout for safety isolation",
        )
        return model, [c], EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0, board_x_max_units=2000, board_y_max_units=2000,
            zones={"ORIGIN_FLY": (0.0, 0.0, 2.0, 2.0)},
        )

    def build_keepout_origin_margin_anchored():
        # The component is anchored next to the origin zone so the doubled
        # keepout interval (margin double-count) must cover it — an
        # over-constrained infeasibility the feasible-assertion catches.
        model = _mk_model(["A"], 200)
        anchor = AnchoredConstraint(
            component="A", tier=ConstraintTier.HARD, position=(5.0, 5.0),
            because="Keepout defense test anchors the component beside the zone",
        )
        c = KeepoutConstraint(
            zone_name="ORIGIN_FLY", tier=ConstraintTier.HARD, margin_mm=1.0,
            because="No components allowed near origin keepout for safety isolation",
        )
        return model, [anchor, c], EncoderContext(
            board_w_mm=20.0, board_h_mm=20.0, board_x_max_units=2000, board_y_max_units=2000,
            zones={"ORIGIN_FLY": (0.0, 0.0, 2.0, 2.0)},
        )

    def build_loop_area_spread():
        model = _mk_model(["C_BUS", "Q1", "Q2", "C_OUT"], 200, bounds=(0, 0, 5000, 5000))
        c = LoopAreaConstraint(
            loop_name="commutation", max_area_mm2=5000.0, tier=ConstraintTier.HARD,
            because="Minimize commutation loop to reduce voltage overshoot and EMI emission",
        )
        # Anchor two loop components at opposite corners so the AABB is large.
        anchor1 = AnchoredConstraint(
            component="C_BUS", tier=ConstraintTier.HARD, position=(5.0, 5.0),
            because="Loop defense test anchors the loop AABB",
        )
        anchor2 = AnchoredConstraint(
            component="Q1", tier=ConstraintTier.HARD, position=(45.0, 45.0),
            because="Loop defense test anchors the loop AABB",
        )
        return model, [anchor1, anchor2, c], EncoderContext(
            board_w_mm=50.0, board_h_mm=50.0, board_x_max_units=5000, board_y_max_units=5000,
            loop_components={"commutation": ["C_BUS", "Q1", "Q2", "C_OUT"]},
        )

    return {
        "separated:2comp_5mm": Scenario(
            "separated_2comp_5mm",
            "mirror of TestSeparated::test_separated_enforces_clearance",
            build_separated,
        ),
        "enclosing:2comp_zone": Scenario(
            "enclosing_2comp_zone",
            "mirror of TestEnclosing::test_enclosing_within_zone",
            build_enclosing,
        ),
        "adjacent:2comp_10mm": Scenario(
            "adjacent_2comp_10mm",
            "mirror of TestAdjacent::test_adjacent_proximity",
            build_adjacent,
        ),
        "onside:left_edge": Scenario(
            "onside_left_edge",
            "mirror of TestOnSide::test_on_side_left_edge",
            build_onside,
        ),
        "anchored:position_fix": Scenario(
            "anchored_position_fix",
            "mirror of TestAnchored::test_anchored_position_fix",
            build_anchored,
        ),
        "keepout:zone_exclusion": Scenario(
            "keepout_zone_exclusion",
            "mirror of TestKeepout::test_keepout_zone_exclusion",
            build_keepout,
        ),
        # U4 triage addition: zone covering the origin with a non-zero margin.
        # The existing keepout test's zone sits mid-board and never exercises
        # the margin path; this scenario does, and it turns the dropped /
        # sign-flipped / double-counted interval mutations into kills.
        "keepout:origin_zone_margin": Scenario(
            "keepout_origin_zone_margin",
            "mirror of tests/pcl/test_keepout_mutation_defense.py (zone at origin, margin 1mm)",
            build_keepout_origin_margin,
        ),
        "aligned:pairwise_x": Scenario(
            "aligned_pairwise_x",
            "mirror of TestAligned::test_aligned_pairwise_x_axis",
            build_aligned,
        ),
        "loop_area:ceiling": Scenario(
            "loop_area_ceiling",
            "mirror of TestLoopArea::test_loop_area_ceiling",
            build_loop_area,
        ),
        # U4 triage addition: anchored component beside the origin zone + margin.
        # Kills the margin double-count mutation (the doubled interval covers the
        # anchored component -> infeasible).
        "keepout:origin_zone_margin_anchored": Scenario(
            "keepout_origin_zone_margin_anchored",
            "mirror of tests/pcl/test_keepout_mutation_defense.py (anchored, margin 1mm)",
            build_keepout_origin_margin_anchored,
        ),
        # U4 triage addition: two loop components anchored at opposite corners
        # force the AABB machinery to work, so the ceiling is actually binding.
        "loop_area:anchored_spread": Scenario(
            "loop_area_anchored_spread",
            "mirror of tests/pcl/test_loop_area_mutation_defense.py (anchored spread)",
            build_loop_area_spread,
        ),
    }


def _mk_model(refs: list[str], size: int, width: int | None = None, height: int | None = None, bounds=(0, 0, 2000, 2000)):
    """Build a CpSatModel with the given polarized (fixed-size) components."""
    from temper_placer.placer.cp_sat.model import CpSatModel

    model = CpSatModel(units_per_mm=100)
    for ref in refs:
        model.add_component(ref, 0, 0, width or size, height or size)
        model.add_rotation(ref, is_polarized=True)
    model.set_bounds(*bounds)
    return model


_REF_NAMES = {
    2: ["A", "B"],
    3: ["C1", "C2", "C3"],
    4: ["C_BUS", "Q1", "Q2", "C_OUT"],
}


def _build_defenses() -> dict[str, list[Defense]]:
    """Per-surface defense subsets (KTD2 cost model: never the whole suite).

    Every surface gets two defenses on its primary (existing-test mirror)
    scenario: the encoder unit-test mirror and the post-solve auditor. Surfaces
    whose triage added a strengthened test (U4) get an extra encoder mirror on
    the new scenario — that new test is now part of the encoding's defense set.
    """
    from temper_placer.placer.cp_sat.audit import PlacementAuditor

    def make_encoder(name: str, surface: str, scenario_key: str, check) -> Defense:
        def run() -> None:
            model, constraints, ctx = _scenarios()[scenario_key].build()
            from temper_placer.placer.cp_sat.encoder import encode_constraints

            encode_constraints(constraints, model, ctx)
            sol = _pinned_solve(model)
            check(model, sol, constraints, ctx)

        return Defense(
            name=name,
            kind="encoder-unit",
            description=f"encoder unit-test mirror: {_scenarios()[scenario_key].description}",
            run=run,
        )

    def make_auditor(name: str, surface: str, scenario_key: str) -> Defense:
        def run() -> None:
            model, constraints, ctx = _scenarios()[scenario_key].build()
            from temper_placer.placer.cp_sat.encoder import encode_constraints

            encode_constraints(constraints, model, ctx)
            sol = _pinned_solve(model)
            assert sol.feasible, f"auditor defense: solve infeasible for {surface}"
            placement = _placement_from_solve(model, sol, ctx)
            loop_components = dict(ctx.loop_components)
            report = PlacementAuditor(placement).audit(constraints, loop_components)
            assert report.all_pass, (
                f"auditor defense: {len(report.violations)} violation(s): "
                + "; ".join(v.description for v in report.violations[:3])
            )

        return Defense(
            name=name,
            kind="placement-auditor",
            description="post-solve PlacementAuditor on the solved placement",
            run=run,
        )

    # --- per-surface checks (assertions mirror the existing encoder tests) ---

    def check_separated(model, sol, constraints, ctx):
        assert sol.feasible, "separated: solve infeasible"
        ax, ay = sol.positions["A"]
        bx, by = sol.positions["B"]
        gap_x = abs(ax - bx) - 200
        gap_y = abs(ay - by) - 200
        assert gap_x >= 480 or gap_y >= 480, (
            f"separated: gap_x={gap_x}, gap_y={gap_y}, expected >=500 units clearance"
        )

    def check_enclosing(model, sol, constraints, ctx):
        assert sol.feasible, "enclosing: solve infeasible"
        for ref in ["Q1", "Q2"]:
            x, y = sol.positions[ref]
            sw, sh = sol.sizes[ref]
            assert x - sw // 2 >= 500, f"{ref} x_start too low"
            assert y - sh // 2 >= 500, f"{ref} y_start too low"
            assert x + sw // 2 <= 1500, f"{ref} x_end too high"
            assert y + sh // 2 <= 1500, f"{ref} y_end too high"

    def check_adjacent(model, sol, constraints, ctx):
        assert sol.feasible, "adjacent: solve infeasible"
        ax, ay = sol.positions["Q1"]
        bx, by = sol.positions["Q2"]
        assert abs(ax - bx) <= 1000, f"x centre distance {abs(ax - bx)} > 1000 units"
        assert abs(ay - by) <= 1000, f"y centre distance {abs(ay - by)} > 1000 units"

    def check_onside(model, sol, constraints, ctx):
        assert sol.feasible, "onside: solve infeasible"
        x, y = sol.positions["J1"]
        sw, sh = sol.sizes["J1"]
        assert x - sw // 2 <= 200, f"J1 x_start={x - sw // 2} > 200 units from left edge"

    def check_anchored(model, sol, constraints, ctx):
        assert sol.feasible, "anchored: solve infeasible"
        x, y = sol.positions["U_MCU"]
        assert abs(x - 1500) < 50, f"U_MCU x={x} expected 1500"
        assert abs(y - 1000) < 50, f"U_MCU y={y} expected 1000"

    def check_keepout(model, sol, constraints, ctx):
        assert sol.feasible, "keepout: solve infeasible"
        x, y = sol.positions["A"]
        sw, sh = sol.sizes["A"]
        x1, x2 = x - sw // 2, x + sw // 2
        y1, y2 = y - sh // 2, y + sh // 2
        assert not (x1 < 600 and x2 > 400 and y1 < 600 and y2 > 400), (
            f"A at ({x1},{y1})-({x2},{y2}) overlaps keepout"
        )

    def check_aligned(model, sol, constraints, ctx):
        assert sol.feasible, "aligned: solve infeasible"
        xs = [sol.positions[r][0] for r in ["C1", "C2", "C3"]]
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                assert abs(xs[i] - xs[j]) <= 50, (
                    f"C{i + 1}-C{j + 1} x diff {abs(xs[i] - xs[j])} > 50 units"
                )

    def check_loop_area(model, sol, constraints, ctx):
        assert sol.feasible, "loop_area: solve infeasible"
        xs = [sol.positions[r][0] - sol.sizes[r][0] // 2 for r in ["C_BUS", "Q1", "Q2", "C_OUT"]]
        ys = [sol.positions[r][1] - sol.sizes[r][1] // 2 for r in ["C_BUS", "Q1", "Q2", "C_OUT"]]
        xe = [sol.positions[r][0] + sol.sizes[r][0] // 2 for r in ["C_BUS", "Q1", "Q2", "C_OUT"]]
        ye = [sol.positions[r][1] + sol.sizes[r][1] // 2 for r in ["C_BUS", "Q1", "Q2", "C_OUT"]]
        aabb_w = (max(xe) - min(xs)) / 100.0
        aabb_h = (max(ye) - min(ys)) / 100.0
        aabb_area = aabb_w * aabb_h
        assert aabb_area <= 500.0, f"Loop area {aabb_area:.1f} mm^2 > 500"

    def check_keepout_origin(model, sol, constraints, ctx):
        assert sol.feasible, "keepout(origin): solve infeasible"
        x, y = sol.positions["A"]
        sw, sh = sol.sizes["A"]
        x1, x2 = x - sw // 2, x + sw // 2
        y1, y2 = y - sh // 2, y + sh // 2
        # zone (0,0)-(2,2)mm with margin 1mm -> [-100,300]x[-100,300] in units
        assert not (x1 < 300 and x2 > -100 and y1 < 300 and y2 > -100), (
            f"A at ({x1},{y1})-({x2},{y2}) overlaps origin keepout"
        )

    def check_keepout_origin_anchored(model, sol, constraints, ctx):
        assert sol.feasible, "keepout(origin,anchored): solve infeasible"
        x, y = sol.positions["A"]
        sw, sh = sol.sizes["A"]
        x1, x2 = x - sw // 2, x + sw // 2
        y1, y2 = y - sh // 2, y + sh // 2
        assert not (x1 < 300 and x2 > -100 and y1 < 300 and y2 > -100), (
            f"A at ({x1},{y1})-({x2},{y2}) overlaps origin keepout"
        )

    def check_loop_area_spread(model, sol, constraints, ctx):
        assert sol.feasible, "loop_area(spread): solve infeasible"
        refs = ["C_BUS", "Q1", "Q2", "C_OUT"]
        xs = [sol.positions[r][0] - sol.sizes[r][0] // 2 for r in refs]
        ys = [sol.positions[r][1] - sol.sizes[r][1] // 2 for r in refs]
        xe = [sol.positions[r][0] + sol.sizes[r][0] // 2 for r in refs]
        ye = [sol.positions[r][1] + sol.sizes[r][1] // 2 for r in refs]
        aabb_w = (max(xe) - min(xs)) / 100.0
        aabb_h = (max(ye) - min(ys)) / 100.0
        aabb_area = aabb_w * aabb_h
        assert aabb_area <= 5000.0, f"Loop area {aabb_area:.1f} mm^2 > 5000"

    checks = {
        "separated": check_separated,
        "enclosing": check_enclosing,
        "adjacent": check_adjacent,
        "onside": check_onside,
        "anchored": check_anchored,
        "keepout": check_keepout,
        "aligned": check_aligned,
        "loop_area": check_loop_area,
    }

    defenses: dict[str, list[Defense]] = {}
    for surface_id in checks:
        primary = _scenario_names_for_surface(surface_id)[0]
        defenses[surface_id] = [
            make_encoder(
                f"encoder-unit:{surface_id}",
                surface_id,
                primary,
                checks[surface_id],
            ),
            make_auditor(f"placement-auditor:{surface_id}", surface_id, primary),
        ]
        if surface_id == "keepout":
            # U4: the origin-zone margin scenarios (new tests in
            # tests/pcl/test_keepout_mutation_defense.py).
            defenses[surface_id].append(
                make_encoder(
                    "encoder-unit:test_keepout_mutation_defense::test_origin_zone_keepout",
                    surface_id,
                    "keepout:origin_zone_margin",
                    check_keepout_origin,
                )
            )
            defenses[surface_id].append(
                make_encoder(
                    "encoder-unit:test_keepout_mutation_defense::test_origin_zone_keepout_anchored",
                    surface_id,
                    "keepout:origin_zone_margin_anchored",
                    check_keepout_origin_anchored,
                )
            )
        if surface_id == "loop_area":
            # U4: the anchored-spread scenario (new test in
            # tests/pcl/test_loop_area_mutation_defense.py).
            defenses[surface_id].append(
                make_encoder(
                    "encoder-unit:test_loop_area_mutation_defense::test_anchored_spread_ceiling",
                    surface_id,
                    "loop_area:anchored_spread",
                    check_loop_area_spread,
                )
            )
    return defenses


def _scenario_names_for_surface(surface_id: str) -> list[str]:
    """All scenario keys belonging to *surface_id*, in insertion order.

    The first entry is the primary (existing-test mirror) scenario; U4-added
    scenarios come after. Insertion order, not alphabetical, so the mirror
    stays the primary probe.
    """
    return [k for k in _scenarios() if k.startswith(f"{surface_id}:")]


def _primary_scenario(surface_id: str) -> Scenario:
    """The primary (existing-test mirror) scenario for *surface_id*."""
    names = _scenario_names_for_surface(surface_id)
    assert names, f"no scenarios for {surface_id}"
    return _scenarios()[names[0]]


# ---------------------------------------------------------------------------
# Core mutation application
# ---------------------------------------------------------------------------


def _load_mutated_module(source: str, module_name: str):
    """Compile+exec mutated handler source into a fresh module namespace."""
    mod = types.ModuleType(module_name)
    mod.__dict__["__name__"] = module_name
    exec(compile(source, f"<{module_name}>", "exec"), mod.__dict__)
    return mod


def _encode_proto(surface: HandlerSurface, scenario_name: str):
    """Encode *scenario_name* for *surface* and return the model proto text.

    The CpModel's text proto is a deterministic rendering of every variable,
    constraint, and enforcement literal added by the encoder — identical
    models render identically, so string equality is the "output changed" probe.
    """
    scenarios = _scenarios()
    from temper_placer.placer.cp_sat.encoder import encode_constraints

    model, constraints, ctx = scenarios[scenario_name].build()
    encode_constraints(constraints, model, ctx)
    return str(model.model_ref)


def run_mutation(
    surface: HandlerSurface,
    spec: MutationSpec,
    defenses: list[Defense],
) -> MutationResult:
    """Apply *spec* to *surface* and classify killed / survived / no-op."""
    source = surface.module_path.read_text()
    orig_tree = ast.parse(source)
    try:
        mutated_tree = spec.transform(ast.parse(source))
    except AssertionError as exc:
        return MutationResult(
            surface.surface_id, surface.constraint_type, spec.mutation_id,
            spec.operator, spec.description, "error", detail=f"transform failed: {exc}",
        )

    mutated_source = ast.unparse(mutated_tree)
    if ast.dump(orig_tree) == ast.dump(mutated_tree):
        return MutationResult(
            surface.surface_id, surface.constraint_type, spec.mutation_id,
            spec.operator, spec.description, "error",
            detail="transform produced an identical AST (no mutation applied)",
        )

    from temper_placer.placer.cp_sat.handlers import HANDLER_REGISTRY

    constraint_type = surface.constraint_type
    # resolve the real enum value
    from temper_placer.pcl.constraints import ConstraintType as CT

    ct = CT[constraint_type]

    # --- no-op probe: the mutation must change the encoder's output on at
    # least one of the surface's probe scenarios ---
    scenario_names = list(_scenarios().keys())
    # only scenarios belonging to this surface
    scenario_names = _scenario_names_for_surface(surface.surface_id)
    changed = False
    noop_detail = "encoder output identical on every probe input (mutation not exercised)"
    orig_handler = HANDLER_REGISTRY.get(ct)
    try:
        # Baseline protos for EVERY scenario must be captured with the original
        # handler registered, before any mutated module is loaded — a per-
        # scenario baseline captured after a previous load would compare
        # mutated-vs-mutated and misclassify a real mutation as a no-op.
        baselines: dict[str, str] = {}
        for scenario_name in scenario_names:
            try:
                baselines[scenario_name] = _encode_proto(surface, scenario_name)
            except Exception as exc:  # pragma: no cover - scenario infrastructure
                return MutationResult(
                    surface.surface_id, surface.constraint_type, spec.mutation_id,
                    spec.operator, spec.description, "error",
                    detail=f"baseline encode failed ({scenario_name}): {exc}",
                )
        _load_mutated_module(
            mutated_source, f"_mut_{surface.surface_id}_{spec.mutation_id}"
        )
        mutated_handler = HANDLER_REGISTRY.get(ct)
        if mutated_handler is orig_handler:
            return MutationResult(
                surface.surface_id, surface.constraint_type, spec.mutation_id,
                spec.operator, spec.description, "error",
                detail="mutated module did not replace the registry entry",
            )
        for scenario_name in scenario_names:
            try:
                mutated_proto = _encode_proto(surface, scenario_name)
            except Exception as exc:  # pragma: no cover - scenario infrastructure
                return MutationResult(
                    surface.surface_id, surface.constraint_type, spec.mutation_id,
                    spec.operator, spec.description, "error",
                    detail=f"mutated encode failed ({scenario_name}): {exc}",
                )
            if mutated_proto != baselines[scenario_name]:
                changed = True
                break
    finally:
        if orig_handler is not None:
            HANDLER_REGISTRY[ct] = orig_handler

    if not changed:
        return MutationResult(
            surface.surface_id, surface.constraint_type, spec.mutation_id,
            spec.operator, spec.description, "no-op",
            detail=noop_detail,
        )

    # --- run the per-surface defense subset ---
    # (defenses encode through HANDLER_REGISTRY, so run them while the
    #  mutated handler is registered)
    fired: list[str] = []
    try:
        _load_mutated_module(mutated_source, f"_mut_{surface.surface_id}_{spec.mutation_id}")
        for defense in defenses:
            try:
                defense.run()
            except AssertionError:
                fired.append(defense.name)
                # continue running remaining defenses to record all that fire
            except Exception:  # mutation broke the defense machinery
                fired.append(defense.name)
        if fired:
            return MutationResult(
                surface.surface_id, surface.constraint_type, spec.mutation_id,
                spec.operator, spec.description, "killed", fired,
                detail="; ".join(fired),
            )
        return MutationResult(
            surface.surface_id, surface.constraint_type, spec.mutation_id,
            spec.operator, spec.description, "survived",
            detail="all defenses passed",
        )
    finally:
        if orig_handler is not None:
            HANDLER_REGISTRY[ct] = orig_handler


def run_suite() -> list[MutationResult]:
    """Run every mutation in the catalog against its surface's defenses."""
    surfaces = {s.surface_id: s for s in discover_handler_surfaces()}
    defenses = _build_defenses()

    # Baseline sanity: every defense must pass on the unmutated encoder. A
    # defense that fails here is a harness bug, not a kill — fail loudly so a
    # broken mirror can never masquerade as a mutation verdict.

    for surface_id, defs in defenses.items():
        for defense in defs:
            try:
                defense.run()
            except Exception as exc:  # pragma: no cover - harness bug
                raise RuntimeError(
                    f"baseline defense {defense.name} failed on the unmutated "
                    f"encoder for {surface_id}: {exc}"
                ) from exc

    # Reject operators outside the R4 fail-capable bug classes (KTD1). A
    # strawman operator (e.g. multiply the encoder output by 1000) is invalid
    # by construction — the catalog may only use VALID_OPERATORS.
    for surface_id, specs in MUTATION_CATALOG.items():
        for mutation_id, spec in specs.items():
            if spec.operator not in VALID_OPERATORS:
                raise ValueError(
                    f"{surface_id}:{mutation_id} uses invalid operator "
                    f"{spec.operator!r}; valid: {', '.join(VALID_OPERATORS)}"
                )

    results: list[MutationResult] = []
    for surface_id in sorted(MUTATION_CATALOG):
        surface = surfaces.get(surface_id)
        if surface is None:
            results.append(
                MutationResult(
                    surface_id, "?", "?", "?", "?", "error",
                    detail=f"no handler surface discovered for {surface_id}",
                )
            )
            continue
        for _mutation_id, spec in sorted(MUTATION_CATALOG[surface_id].items()):
            results.append(run_mutation(surface, spec, defenses.get(surface_id, [])))
    return results


# ---------------------------------------------------------------------------
# Register emission (U2)
# ---------------------------------------------------------------------------


def _triage_from_register(path: Path) -> dict[tuple[str, str], tuple[str, str]]:
    """Load prior triage verdicts from an existing register (if present).

    Survivor triage (benign vs test-gap + rationale) is curated by hand; when
    the runner regenerates the register, the prior triage is preserved for
    mutations that still survive so a re-run cannot silently drop it.
    """
    import yaml

    triage: dict[tuple[str, str], tuple[str, str]] = {}
    if not path.exists():
        return triage
    doc = yaml.safe_load(path.read_text())
    for surface in (doc or {}).get("families", {}).get("placer-pcl-handlers", {}).get("surfaces", []):
        sid = surface.get("id")
        for m in surface.get("mutations", []):
            if m.get("outcome") == "survived" and m.get("triage"):
                triage[(sid, m["id"])] = (m["triage"], m.get("triage_rationale", ""))
    return triage


def results_to_register(results: list[MutationResult], triage: dict[tuple[str, str], tuple[str, str]]) -> dict:
    """Build the kill-set register document (U2 schema)."""
    by_surface: dict[str, list[MutationResult]] = {}
    for r in results:
        by_surface.setdefault(r.surface_id, []).append(r)

    surfaces_out: list[dict] = []
    for surface_id in sorted(by_surface):
        rs = sorted(by_surface[surface_id], key=lambda r: r.mutation_id)
        mutations_out = []
        killed: list[str] = []
        survived: list[str] = []
        for r in rs:
            entry: dict = {
                "id": r.mutation_id,
                "operator": r.operator,
                "description": r.description,
                "outcome": r.outcome,
            }
            if r.outcome == "killed":
                killed.append(r.mutation_id)
                entry["defenses_fired"] = r.defenses_fired
            elif r.outcome == "survived":
                survived.append(r.mutation_id)
                status, rationale = triage.get(
                    (surface_id, r.mutation_id), ("test-gap", "TODO: triage survivor")
                )
                entry["triage"] = status
                entry["triage_rationale"] = rationale
            else:  # no-op / error
                entry["detail"] = r.detail
            mutations_out.append(entry)
        surfaces_out.append(
            {
                "id": surface_id,
                "constraint_type": next(
                    (r.constraint_type for r in rs if r.constraint_type != "?"), surface_id
                ),
                "handler_module": f"temper_placer.placer.cp_sat.handlers.{surface_id}",
                "mutations": mutations_out,
                "killed": killed,
                "survived": survived,
            }
        )

    return {
        "schema_version": 1,
        "generated": "2026-08-02",
        "generator": "scripts/constraint_mutation_runner.py",
        "note": (
            "Kill-set register for the constraint mutation suite (R32). Each "
            "surface's mutations are the R4 bug classes (sign-flip, dropped-term, "
            "loosened-bound, off-by-one, double-count) applied at source level; "
            "outcome is killed when the surface's existing defenses (encoder "
            "unit-test mirrors + post-solve PlacementAuditor) fail. Survivors are "
            "triaged: benign (documented rationale) or test-gap (TODO). Enforced "
            "by scripts/constraint_mutation_gate.py."
        ),
        "families": {
            "placer-pcl-handlers": {
                "status": "active",
                "surfaces": surfaces_out,
            },
            "router-v6-topology": {
                "status": "deferred",
                "deferred_reason": ROUTER_V6_DEFERRED_REASON,
                "classes": list(ROUTER_V6_CLASSES),
            },
        },
    }


def write_register(path: Path, register: dict) -> None:
    import yaml

    path.write_text(
        yaml.safe_dump(
            register,
            sort_keys=False,
            default_flow_style=False,
            width=120,
            allow_unicode=True,
        )
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-register",
        metavar="PATH",
        help="write the kill-set register YAML to PATH (default: only print results)",
    )
    parser.add_argument(
        "--surface",
        help="limit the run to one surface id (e.g. separated)",
    )
    parser.add_argument(
        "--triage-from",
        metavar="PATH",
        help="preserve curated survivor triage from an existing register when "
        "regenerating (default: none, survivors become untriaged test-gap)",
    )
    args = parser.parse_args(argv)

    results = run_suite()
    if args.surface:
        results = [r for r in results if r.surface_id == args.surface]

    # summary table
    print(f"{'surface':<10} {'mutation':<28} {'operator':<14} {'outcome':<9} defenses")
    print("-" * 100)
    counts = {"killed": 0, "survived": 0, "no-op": 0, "error": 0}
    for r in sorted(results, key=lambda r: (r.surface_id, r.mutation_id)):
        counts[r.outcome] += 1
        print(
            f"{r.surface_id:<10} {r.mutation_id:<28} {r.operator:<14} {r.outcome:<9} "
            f"{','.join(r.defenses_fired) or r.detail}"
        )
    print("-" * 100)
    print(
        f"total={len(results)} killed={counts['killed']} survived={counts['survived']} "
        f"no-op={counts['no-op']} error={counts['error']}"
    )

    if args.write_register:
        triage = _triage_from_register(Path(args.triage_from)) if args.triage_from else {}
        register = results_to_register(results, triage)
        write_register(Path(args.write_register), register)
        print(f"register written to {args.write_register}")

    return 0 if counts["error"] == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
