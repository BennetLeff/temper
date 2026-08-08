#!/usr/bin/env python3
"""Gate-mutation engine (R42, U1): weaken a gate script's own logic and
report exactly what changed.

Motivation
----------
This project's own session-of-record (2026-08-07) found nine distinct
mechanisms by which a check reported success while being structurally
incapable of reporting failure: a value discarded before reaching its
consumer, a rule matching names while ignoring geometry, a fatal check
gated behind ``verbose``, a validator iterating an empty dict, an
unguarded ``all()`` over a possibly-empty iterable, a comparison written
backwards (``rated >= actual*0.5``), and others -- see
``docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md``. Every
one of those is a *specific, small, surgical* change to already-correct
code that a gate's own test suite either notices or does not. This module
is the mechanical form of "make that change and see if anything notices":
given a gate script and a declarative mutation spec, it produces a
mutated COPY of the gate's source (never touching the committed file --
KTD5) plus a machine-readable diff record naming exactly what was
changed and where.

Mutation axes (KTD1: declarative, human-reviewable, one row per triple in
``ci-corpus/mutations.yaml``) -- chosen to model the nine observed
failure mechanisms above, not generic arithmetic off-by-ones:

  guard-strip        drop a ``raise`` (typically ``raise GateError(...)``)
                      to ``pass`` -- models "StageDRCFailure gated behind
                      verbose" and "SIL prints [WARN] instead of failing":
                      the fatal path is reached but no longer fires.
  condition-invert    wrap an ``if`` test in ``not (...)`` -- models a
                      guard that runs backwards, e.g. a vacuity check that
                      now fires exactly when it should NOT.
  scope-remove        drop one element from a module-level container
                      constant (a scan-root tuple, an aggregator set) --
                      models "a CI group collecting zero tests from a
                      deleted path" / gate-subset-blindness, mechanized.
  violation-discard   replace a ``violations.append(...)`` (or similar
                      accumulator) call with ``pass`` -- models "a value
                      discarded before reaching its consumer": the
                      detection logic still runs, but its finding never
                      reaches the verdict.
  comparison-flip     swap a comparison operator for its off-by-one
                      neighbour (``>=``<->``>``, ``<=``<->``<``) -- models
                      "swap >= for >" and the backwards-power-assertion
                      class (a boundary that now excludes the value it
                      used to include, or vice versa).
  threshold-set       overwrite a specific numeric ``Constant`` with an
                      explicit new value named in the manifest -- models
                      a threshold that quietly loosens.
  return-stub         insert a literal ``return`` (source given verbatim
                      in the manifest) as the first statement of a
                      function -- models "a test binary returning 0
                      instead of calling UnityEnd()" / "return a constant
                      success": the entire function body becomes dead
                      code.

Every mutation is validated against a ``line_hint`` substring recorded in
the manifest before it is applied: if the hinted text is not found on the
target line, the mutation is reported NOT APPLICABLE (KTD1 test scenario
5) rather than silently mutating the wrong thing -- this is the drift
guard that keeps a hand-authored locator (function name + occurrence
index) honest as the gate's source changes.

This module never writes to the repository: ``apply_mutation`` returns
mutated source text in memory; ``write_mutant`` (used by the runner)
writes it to a fresh ``tempfile`` location. The committed gate scripts are
provably untouched by any operation here.

Usage
-----
  uv run python scripts/gate_mutate.py --describe ci-corpus/mutations.yaml
  uv run python scripts/gate_mutate.py --apply ci-corpus/mutations.yaml \\
      --mutation-id <id> --out /tmp/mutant.py
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.repo import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()

AXES = (
    "guard-strip",
    "condition-invert",
    "scope-remove",
    "violation-discard",
    "comparison-flip",
    "threshold-set",
    "return-stub",
)

_CMP_FLIP = {
    ast.GtE: ast.Gt,
    ast.Gt: ast.GtE,
    ast.LtE: ast.Lt,
    ast.Lt: ast.LtE,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}


@dataclass
class MutationSpec:
    gate: str  # repo-relative path, e.g. "scripts/check_isolation_keepout.py"
    mutation_id: str
    axis: str
    description: str
    function: str | None = None  # None = whole module
    match: str = ""  # "raise" | "if-invert" | "container-remove" |
    # "append-drop" | "compare-op-flip" | "constant-set" | "return-stub"
    index: int = 0
    name: str | None = None  # container-remove: the module-level constant name
    remove_value: Any = None  # container-remove: element to drop
    old_value: float | None = None  # constant-set: expected current value (drift guard)
    new_value: float | None = None  # constant-set: replacement value
    stub_code: str | None = None  # return-stub: literal statement(s) to prepend
    line_hint: str = ""  # drift guard: substring expected on the target line

    def __post_init__(self) -> None:
        if self.axis not in AXES:
            raise ValueError(f"unknown axis {self.axis!r} (mutation {self.mutation_id})")


@dataclass
class DiffRecord:
    mutation_id: str
    axis: str
    gate: str
    applicable: bool
    file: str
    line: int | None = None
    target: str = ""
    before: str = ""
    after: str = ""
    note: str = ""

    def summary(self) -> str:
        if not self.applicable:
            return f"[{self.mutation_id}] NOT APPLICABLE ({self.note})"
        return f"[{self.mutation_id}] {self.file}:{self.line} {self.target}: {self.before!r} -> {self.after!r}"


class GateMutateError(Exception):
    """Raised when a mutation spec cannot be resolved at all (bad axis/match)."""


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _scope_node(tree: ast.Module, function: str | None) -> ast.AST | None:
    if function is None:
        return tree
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function:
            return node
    return None


def _nth(nodes: list[ast.AST], index: int) -> ast.AST | None:
    if 0 <= index < len(nodes):
        return nodes[index]
    return None


def _replace_node(tree: ast.Module, target: ast.AST, replacement: ast.AST) -> None:
    """In-place: replace every occurrence of ``target`` (by identity) with
    ``replacement`` anywhere in ``tree``."""

    class _Repl(ast.NodeTransformer):
        def visit(self, node):  # noqa: D102 - internal
            if node is target:
                return replacement
            return self.generic_visit(node)

    _Repl().visit(tree)


def _line_of(node: ast.AST, lines: list[str]) -> tuple[int, str]:
    lineno = getattr(node, "lineno", None)
    if lineno is None or not (1 <= lineno <= len(lines)):
        return -1, ""
    return lineno, lines[lineno - 1].strip()


def _check_hint(line_text: str, hint: str, mutation_id: str) -> str | None:
    """Return an error note if the drift guard fails, else None."""
    if hint and hint not in line_text:
        return (
            f"line_hint {hint!r} not found in target line {line_text!r} -- "
            f"the gate's source has drifted since mutation {mutation_id!r} "
            "was authored; re-locate the target before re-registering"
        )
    return None


# ---------------------------------------------------------------------------
# Per-axis appliers. Each returns a DiffRecord; mutates ``tree`` in place
# when ``applicable`` is True.
# ---------------------------------------------------------------------------


def _apply_guard_strip(tree: ast.Module, spec: MutationSpec, lines: list[str]) -> DiffRecord:
    scope = _scope_node(tree, spec.function)
    if scope is None:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate,
                           note=f"function {spec.function!r} not found")
    raises = [n for n in ast.walk(scope) if isinstance(n, ast.Raise)]
    target = _nth(raises, spec.index)
    if target is None:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate,
                           note=f"no raise statement at index {spec.index} in "
                                f"{spec.function or '<module>'} (found {len(raises)})")
    lineno, text = _line_of(target, lines)
    err = _check_hint(text, spec.line_hint, spec.mutation_id)
    if err:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate, line=lineno, note=err)
    replacement = ast.Pass()
    ast.copy_location(replacement, target)
    _replace_node(tree, target, replacement)
    return DiffRecord(spec.mutation_id, spec.axis, spec.gate, True, spec.gate, line=lineno,
                       target=f"raise statement #{spec.index} in {spec.function or '<module>'}",
                       before=text, after="pass", note=spec.description)


def _apply_if_invert(tree: ast.Module, spec: MutationSpec, lines: list[str]) -> DiffRecord:
    scope = _scope_node(tree, spec.function)
    if scope is None:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate,
                           note=f"function {spec.function!r} not found")
    ifs = [n for n in ast.walk(scope) if isinstance(n, ast.If)]
    target = _nth(ifs, spec.index)
    if target is None:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate,
                           note=f"no if-statement at index {spec.index} in "
                                f"{spec.function or '<module>'} (found {len(ifs)})")
    lineno, text = _line_of(target, lines)
    err = _check_hint(text, spec.line_hint, spec.mutation_id)
    if err:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate, line=lineno, note=err)
    before_expr = ast.unparse(target.test)
    new_test = ast.UnaryOp(op=ast.Not(), operand=target.test)
    ast.copy_location(new_test, target.test)
    ast.fix_missing_locations(new_test)
    target.test = new_test
    return DiffRecord(spec.mutation_id, spec.axis, spec.gate, True, spec.gate, line=lineno,
                       target=f"if-test #{spec.index} in {spec.function or '<module>'}",
                       before=before_expr, after=f"not ({before_expr})", note=spec.description)


def _apply_container_remove(tree: ast.Module, spec: MutationSpec, lines: list[str]) -> DiffRecord:
    if not spec.name:
        raise GateMutateError(f"container-remove mutation {spec.mutation_id!r} needs 'name'")
    target_assign = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == spec.name:
                target_assign = node
                break
    if target_assign is None:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate,
                           note=f"module-level constant {spec.name!r} not found")
    lineno, text = _line_of(target_assign, lines)
    err = _check_hint(text, spec.line_hint, spec.mutation_id)
    if err:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate, line=lineno, note=err)
    value_node = target_assign.value
    # Unwrap a bare frozenset(...)/set(...)/tuple(...)/list(...) call to its
    # literal argument, matching the real declaration shapes in this repo
    # (e.g. AGGREGATORS = {"all"}, SCAN_ROOT_NAMES = ("elec", ...)).
    container = value_node
    if isinstance(container, ast.Call) and container.args:
        container = container.args[0]
    if not isinstance(container, (ast.Set, ast.List, ast.Tuple)):
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate, line=lineno,
                           note=f"{spec.name!r} is not a literal set/list/tuple ({type(container).__name__})")
    before_elts = [ast.literal_eval(e) for e in container.elts]
    if spec.remove_value not in before_elts:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate, line=lineno,
                           note=f"{spec.remove_value!r} not present in {spec.name}={before_elts!r}")
    new_elts = [e for e in container.elts if ast.literal_eval(e) != spec.remove_value]
    container.elts = new_elts
    return DiffRecord(spec.mutation_id, spec.axis, spec.gate, True, spec.gate, line=lineno,
                       target=f"container constant {spec.name}",
                       before=repr(before_elts), after=repr([e for e in before_elts if e != spec.remove_value]),
                       note=spec.description)


def _apply_append_drop(tree: ast.Module, spec: MutationSpec, lines: list[str]) -> DiffRecord:
    scope = _scope_node(tree, spec.function)
    if scope is None:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate,
                           note=f"function {spec.function!r} not found")

    def _is_append_call(n: ast.AST) -> bool:
        return (
            isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Attribute)
            and n.value.func.attr == "append"
        )

    calls = [n for n in ast.walk(scope) if _is_append_call(n)]
    target = _nth(calls, spec.index)
    if target is None:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate,
                           note=f"no .append(...) statement at index {spec.index} in "
                                f"{spec.function or '<module>'} (found {len(calls)})")
    lineno, text = _line_of(target, lines)
    err = _check_hint(text, spec.line_hint, spec.mutation_id)
    if err:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate, line=lineno, note=err)
    replacement = ast.Pass()
    ast.copy_location(replacement, target)
    _replace_node(tree, target, replacement)
    return DiffRecord(spec.mutation_id, spec.axis, spec.gate, True, spec.gate, line=lineno,
                       target=f".append() call #{spec.index} in {spec.function or '<module>'}",
                       before=text, after="pass", note=spec.description)


def _apply_compare_op_flip(tree: ast.Module, spec: MutationSpec, lines: list[str]) -> DiffRecord:
    scope = _scope_node(tree, spec.function)
    if scope is None:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate,
                           note=f"function {spec.function!r} not found")
    compares = [n for n in ast.walk(scope) if isinstance(n, ast.Compare)
                and any(type(op) in _CMP_FLIP for op in n.ops)]
    target = _nth(compares, spec.index)
    if target is None:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate,
                           note=f"no flippable comparison at index {spec.index} in "
                                f"{spec.function or '<module>'} (found {len(compares)})")
    lineno, text = _line_of(target, lines)
    err = _check_hint(text, spec.line_hint, spec.mutation_id)
    if err:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate, line=lineno, note=err)
    before_expr = ast.unparse(target)
    target.ops = [_CMP_FLIP[type(op)]() if type(op) in _CMP_FLIP else op for op in target.ops]
    ast.fix_missing_locations(target)
    after_expr = ast.unparse(target)
    return DiffRecord(spec.mutation_id, spec.axis, spec.gate, True, spec.gate, line=lineno,
                       target=f"comparison #{spec.index} in {spec.function or '<module>'}",
                       before=before_expr, after=after_expr, note=spec.description)


def _apply_constant_set(tree: ast.Module, spec: MutationSpec, lines: list[str]) -> DiffRecord:
    scope = _scope_node(tree, spec.function)
    if scope is None:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate,
                           note=f"function {spec.function!r} not found")

    def _is_numeric_const(n: ast.AST) -> bool:
        return isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)

    consts = [n for n in ast.walk(scope) if _is_numeric_const(n)]
    target = _nth(consts, spec.index)
    if target is None:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate,
                           note=f"no numeric constant at index {spec.index} in "
                                f"{spec.function or '<module>'} (found {len(consts)})")
    lineno, text = _line_of(target, lines)
    err = _check_hint(text, spec.line_hint, spec.mutation_id)
    if err:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate, line=lineno, note=err)
    if spec.old_value is not None and abs(float(target.value) - spec.old_value) > 1e-9:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate, line=lineno,
                           note=f"constant at index {spec.index} is {target.value!r}, expected "
                                f"old_value={spec.old_value!r} -- drifted, re-locate before re-registering")
    if spec.new_value is None:
        raise GateMutateError(f"threshold-set mutation {spec.mutation_id!r} needs 'new_value'")
    before_val = target.value
    target.value = spec.new_value
    return DiffRecord(spec.mutation_id, spec.axis, spec.gate, True, spec.gate, line=lineno,
                       target=f"numeric constant #{spec.index} in {spec.function or '<module>'}",
                       before=repr(before_val), after=repr(spec.new_value), note=spec.description)


def _apply_return_stub(tree: ast.Module, spec: MutationSpec, lines: list[str]) -> DiffRecord:
    scope = _scope_node(tree, spec.function)
    if scope is None or not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate,
                           note=f"function {spec.function!r} not found (return-stub requires a function)")
    lineno, text = _line_of(scope, lines)
    err = _check_hint(text, spec.line_hint, spec.mutation_id)
    if err:
        return DiffRecord(spec.mutation_id, spec.axis, spec.gate, False, spec.gate, line=lineno, note=err)
    if not spec.stub_code:
        raise GateMutateError(f"return-stub mutation {spec.mutation_id!r} needs 'stub_code'")
    try:
        stub_stmts = ast.parse(spec.stub_code, mode="exec").body
    except SyntaxError as exc:
        raise GateMutateError(f"return-stub stub_code for {spec.mutation_id!r} is invalid Python: {exc}") from exc
    for stmt in stub_stmts:
        ast.fix_missing_locations(stmt)
    scope.body = stub_stmts + scope.body
    return DiffRecord(spec.mutation_id, spec.axis, spec.gate, True, spec.gate, line=lineno,
                       target=f"function {spec.function} body",
                       before="<original body>", after=spec.stub_code, note=spec.description)


_APPLIERS = {
    "raise": _apply_guard_strip,
    "if-invert": _apply_if_invert,
    "container-remove": _apply_container_remove,
    "append-drop": _apply_append_drop,
    "compare-op-flip": _apply_compare_op_flip,
    "constant-set": _apply_constant_set,
    "return-stub": _apply_return_stub,
}


def apply_mutation(source_text: str, spec: MutationSpec) -> tuple[str | None, DiffRecord]:
    """Apply one mutation to *source_text* (the gate's committed source,
    read into memory -- never written back). Returns (mutated_text, diff);
    mutated_text is None when the mutation is not applicable."""
    applier = _APPLIERS.get(spec.match)
    if applier is None:
        raise GateMutateError(f"unknown match kind {spec.match!r} (mutation {spec.mutation_id!r})")
    tree = ast.parse(source_text, filename=spec.gate)
    lines = source_text.splitlines()
    diff = applier(tree, spec, lines)
    if not diff.applicable:
        return None, diff
    mutated = ast.unparse(ast.fix_missing_locations(tree))
    return mutated + "\n", diff


def write_mutant(repo_root: Path, spec: MutationSpec, scratch_dir: Path) -> tuple[Path | None, DiffRecord]:
    """Read the committed gate at *repo_root*/spec.gate, apply the
    mutation, and write the result to a fresh file under *scratch_dir*
    (never touching the committed file). Returns (mutant_path, diff);
    mutant_path is None when the mutation is not applicable."""
    gate_path = repo_root / spec.gate
    source_text = gate_path.read_text(encoding="utf-8")
    mutated, diff = apply_mutation(source_text, spec)
    if mutated is None:
        return None, diff
    scratch_dir.mkdir(parents=True, exist_ok=True)
    out_path = scratch_dir / f"{Path(spec.gate).stem}__{spec.mutation_id}.py"
    out_path.write_text(mutated, encoding="utf-8")
    return out_path, diff


def committed_bytes_unchanged(repo_root: Path, gates: list[str], before: dict[str, bytes]) -> list[str]:
    """Return the list of gate paths whose on-disk bytes differ from
    *before* -- used by the test suite and the runner's own self-check to
    prove a mutation sweep never touched the committed files (KTD5)."""
    changed = []
    for rel in gates:
        current = (repo_root / rel).read_bytes()
        if current != before.get(rel):
            changed.append(rel)
    return changed


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


def load_manifest(path: Path) -> list[MutationSpec]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = data.get("mutations")
    if not isinstance(entries, list):
        raise GateMutateError(f"{path}: top-level 'mutations' key must be a list")
    specs = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise GateMutateError(f"{path}: mutations[{i}] is not a mapping")
        entry = dict(entry)
        entry.pop("canary", None)  # runner-only field, not part of the mutation itself
        try:
            specs.append(MutationSpec(**entry))
        except TypeError as exc:
            raise GateMutateError(f"{path}: mutations[{i}] ({entry.get('mutation_id')}): {exc}") from exc
    return specs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "ci-corpus" / "mutations.yaml")
    parser.add_argument("--describe", action="store_true", help="list every registered mutation")
    parser.add_argument("--apply", action="store_true", help="apply one mutation and print the diff")
    parser.add_argument("--mutation-id", type=str, default=None)
    parser.add_argument("--out", type=Path, default=None, help="write the mutated source here (--apply only)")
    args = parser.parse_args(argv)

    specs = load_manifest(args.manifest)

    if args.describe or not args.apply:
        print(f"{len(specs)} mutation(s) registered in {args.manifest}")
        by_gate: dict[str, list[MutationSpec]] = {}
        for s in specs:
            by_gate.setdefault(s.gate, []).append(s)
        for gate, gate_specs in sorted(by_gate.items()):
            print(f"\n{gate} ({len(gate_specs)} mutation(s)):")
            for s in gate_specs:
                print(f"  [{s.axis}] {s.mutation_id}: {s.description}")
        return 0

    target = next((s for s in specs if s.mutation_id == args.mutation_id), None)
    if target is None:
        print(f"no mutation with id {args.mutation_id!r} in {args.manifest}", file=sys.stderr)
        return 2
    mutant_path, diff = write_mutant(REPO_ROOT, target, args.out.parent if args.out else Path("/tmp"))
    print(diff.summary())
    if mutant_path is None:
        return 1
    if args.out:
        args.out.write_text(mutant_path.read_text())
        print(f"wrote mutant to {args.out}")
    else:
        print(f"wrote mutant to {mutant_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
