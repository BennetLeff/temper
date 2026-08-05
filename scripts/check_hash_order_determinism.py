#!/usr/bin/env python3
"""Salted-hash order gate: no NEW site may record an order PYTHONHASHSEED picked.

Motivating incident
-------------------
CPython randomises the string hash salt per process (PEP 456). Two consequences
are load-bearing for a tool that emits board geometry:

  * ``set``/``frozenset`` iteration order for ``str`` elements differs between
    two runs of identical code on identical input;
  * ``hash(some_str)`` returns a different integer in every process.

Six sites derived an *ordered* or *numeric* result from one of those, and every
one reached a board artifact:

  * ``heuristics/organizational.py:123``, ``:139`` -- a ``set`` of net refs
    became ``FunctionalModule.components``, whose *index* selects each
    component's polar angle. 8 fresh interpreters, 8 distinct orders.
  * ``heuristics/structural.py:753`` -- a ``set`` of loop components drove both
    a polar-angle index and the float accumulation order of a centroid ``sum()``
    (observed as a 1-ULP coordinate difference: ``59.50946904060019`` vs
    ``59.509469040600194``).
  * ``heuristics/topological_init.py`` (5 sites) -- a ``set`` of unplaced refs
    seeded a zone assignment's insertion order, which became the cluster order,
    which selected each cluster's sub-region.
    (Those three modules are fixed by PR #730.)
  * ``router_v6/channel_mapping.py:457`` -- ``hash(channel_id) % len(nodes)``
    returned a *geometric coordinate*. 12/12 fresh interpreters disagreed.
  * ``router_v6/thermal_relief.py`` -- iterating a ``frozenset[str]`` of plane
    nets ordered the emitted thermal-relief report. 8/8 interpreters disagreed.
    (Those two are fixed by the PR that adds this gate; issue #752, 6 & 7.)

Four modules, six sites, found one at a time over several weeks by four separate
investigations. A seventh will be written. This gate exists to fail on the
seventh, not to re-assert the six.

What is flagged
---------------
A finding needs **both halves** of the defect in one place:

  1. a value whose order or magnitude comes from the hash salt -- a set-typed
     expression, or a call to the ``hash()`` builtin; and
  2. an operation that *records* that order -- materialising it into a list,
     accumulating a float over it, pairing it with positions, capturing its
     first element, appending in its loop body, or keying a dict by its loop
     variable.

Half 2 is why ``heuristics/structural.identify_thermal_components`` is clean: it
accumulates into ``thermal_refs`` (a ``set``), never iterates it, and returns by
re-projecting through ``netlist.components``. Set membership, ``set.add``,
``set.update``, ``in``, ``len``, ``sorted``, ``any``/``all`` and set algebra all
consume a set without recording its order and are not flagged. A gate that
flagged every ``for x in some_set`` would be switched off within a week.

Four exemptions exist, each because the construct is *provably* order-invariant,
and each stated as a rule rather than as a site:

  * ``def __hash__(self): return hash(self.key)`` -- the only correct use of the
    builtin: the value never leaves the process that produced it.
  * ``sum(1 for x in <set> ...)`` and other integer-literal summands -- integer
    addition is associative, so accumulation order cannot move the result. A
    float summand is flagged; that is the exact shape of the 1-ULP defect above.
  * ``list(<set>)[0]`` under a proven ``len(<set>) == 1`` / ``<= 1`` guard --
    a singleton has only one order.
  * ``for x in <set>: if cond: flag = True; break`` -- a break that sets a
    constant rather than capturing ``x`` computes "does any element match",
    which is order-invariant. A break that *captures* the element is flagged.

Scope
-----
Default-include, narrow documented-exclude, following
``scripts/check_vacuous_gates.py``'s rationale (an allowlist requires a
maintainer to remember to add every new module, which is the mechanism that
produces blind spots): every ``.py`` file under ``packages/*/src``, recursive,
no exceptions.

Test trees are **out of scope**, not suppressed: a test's own iteration order
does not reach a board artifact, and the runtime half of this gate
(``packages/temper-placer/tests/deterministic/test_hash_order_determinism.py``)
covers the production entry points directly by re-running them in fresh
interpreters under many ``PYTHONHASHSEED`` values. Both halves are necessary and
neither subsumes the other: the static half sees code no test exercises; the
runtime half sees composition across calls that the static half cannot follow.
The runtime half also runs under the invocation CI actually uses for this
package (``cd packages/temper-placer && pytest tests/deterministic/``), which
does not load a repo-root ``conftest.py``.

The inventory, and why it is not a denylist
-------------------------------------------
The detector finds this class throughout the tree, not only at the six known
sites. Those are pre-existing, they are real (audited one by one -- see the PR
that introduced this file), and fixing forty of them in the PR that fixes two
would be unreviewable. They are therefore recorded in ``.hash-order-inventory``
and the gate is a **ratchet**, on the model of ``tools/loc_cap_check.py`` and
``scripts/vulture_gate.py``:

  * a site not in the inventory FAILS -- this is the whole point, and it is what
    catches code that does not exist yet;
  * an inventory entry that no longer fires FAILS (``STALE_ENTRY``) -- debt paid
    must be recorded, or the ledger silently stops shrinking;
  * a count that grew within an existing entry FAILS.

An entry is ``path::qualname::construct count``, so it survives line-number
churn but not a second site of the same construct in the same function. There
is deliberately **no per-site suppression comment**: the only way to silence a
finding is to edit a reviewed, version-controlled ledger where the diff is
visible.

Exit codes
----------
  0 - clean
  1 - findings outside the inventory, stale inventory entries, or a scope that
      matched too few files (fail-closed: an evaporated scope is a gate failure,
      not a pass)
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

INCLUDE_GLOBS: tuple[str, ...] = ("packages/*/src/**/*.py",)
INVENTORY_PATH = REPO_ROOT / ".hash-order-inventory"

# A file count this far below the real surface means the glob broke.
MIN_FILES_SCANNED = 200

_SET_ANNOTATION_NAMES = frozenset(
    {"set", "frozenset", "Set", "FrozenSet", "AbstractSet", "MutableSet", "KeysView"}
)
_SET_CONSTRUCTORS = frozenset({"set", "frozenset"})
_SET_RETURNING_METHODS = frozenset(
    {"union", "intersection", "difference", "symmetric_difference", "copy"}
)
_ORDER_RECORDING_METHODS = frozenset({"append", "extend", "insert"})


@dataclass(frozen=True)
class Finding:
    path: str
    qualname: str
    construct: str
    line: int
    detail: str

    @property
    def key(self) -> str:
        return f"{self.path}::{self.qualname}::{self.construct}"

    def render(self) -> str:
        return f"{self.path}:{self.line}: [{self.construct}] in {self.qualname}(): {self.detail}"


def _annotation_is_set(node: ast.expr | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Subscript):
        return _annotation_is_set(node.value)
    if isinstance(node, ast.Name):
        return node.id in _SET_ANNOTATION_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in _SET_ANNOTATION_NAMES
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _annotation_is_set(node.left) or _annotation_is_set(node.right)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return _annotation_is_set(ast.parse(node.value, mode="eval").body)
        except SyntaxError:
            return False
    return False


def _call_func_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _names_read(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def _target_names(node: ast.expr) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


class _Analyzer(ast.NodeVisitor):
    """Flag set/hash-ordered values at the point where their order is recorded.

    Name typing is conservative in one direction only: a name assigned a
    set-typed expression, and never assigned a definitely-not-set expression,
    counts as a set. A name with conflicting bindings is dropped, so ambiguity
    never produces a finding.
    """

    def __init__(self, path: str, set_returning_funcs: frozenset[str]) -> None:
        self.path = path
        self.set_returning_funcs = set_returning_funcs
        self.findings: list[Finding] = []
        self._set_names: set[str] = set()
        self._conflicted: set[str] = set()
        self._scope: list[str] = []
        self._hash_dunder_depth = 0
        # Names proven to hold exactly one element by an enclosing len()==1 test.
        self._singleton_names: list[set[str]] = [set()]

    # ---------------------------------------------------------------- typing

    def _mark_set(self, name: str) -> None:
        if name not in self._conflicted:
            self._set_names.add(name)

    def _mark_not_set(self, name: str) -> None:
        self._conflicted.add(name)
        self._set_names.discard(name)

    def expr_is_set(self, node: ast.expr) -> bool:
        if isinstance(node, ast.Set | ast.SetComp):
            return True
        if isinstance(node, ast.Name):
            return node.id in self._set_names
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, ast.Sub | ast.BitOr | ast.BitAnd | ast.BitXor
        ):
            return self.expr_is_set(node.left) or self.expr_is_set(node.right)
        if isinstance(node, ast.Call):
            name = _call_func_name(node)
            if name is None:
                return False
            if name in _SET_CONSTRUCTORS:
                return True
            if (
                isinstance(node.func, ast.Attribute)
                and name in _SET_RETURNING_METHODS
                and self.expr_is_set(node.func.value)
            ):
                return True
            return name in self.set_returning_funcs
        return False

    @staticmethod
    def _definitely_not_set(node: ast.expr) -> bool:
        return isinstance(
            node,
            ast.List | ast.ListComp | ast.Tuple | ast.Dict | ast.DictComp | ast.JoinedStr,
        )

    # ------------------------------------------------------------- bindings

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            if _annotation_is_set(node.annotation):
                self._mark_set(node.target.id)
            else:
                self._mark_not_set(node.target.id)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                if self.expr_is_set(node.value):
                    self._mark_set(target.id)
                elif self._definitely_not_set(node.value):
                    self._mark_not_set(target.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        args = node.args
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
            if _annotation_is_set(arg.annotation):
                self._mark_set(arg.arg)
        self._scope.append(node.name)
        if node.name == "__hash__":
            self._hash_dunder_depth += 1
            self.generic_visit(node)
            self._hash_dunder_depth -= 1
        else:
            self.generic_visit(node)
        self._scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    @property
    def qualname(self) -> str:
        return ".".join(self._scope) if self._scope else "<module>"

    # ---------------------------------------------- singleton-guard tracking

    def visit_If(self, node: ast.If) -> None:
        proven = self._singleton_names[-1] | self._names_proven_singleton(node.test)
        self._singleton_names.append(proven)
        for stmt in node.body:
            self.visit(stmt)
        self._singleton_names.pop()
        self.visit(node.test)
        for stmt in node.orelse:
            self.visit(stmt)

    @staticmethod
    def _names_proven_singleton(test: ast.expr) -> set[str]:
        """Names ``n`` for which ``test`` proves ``len(n) <= 1``."""
        proven: set[str] = set()
        for cmp_node in ast.walk(test):
            if not isinstance(cmp_node, ast.Compare) or len(cmp_node.ops) != 1:
                continue
            left, op, right = cmp_node.left, cmp_node.ops[0], cmp_node.comparators[0]
            if not (
                isinstance(left, ast.Call)
                and isinstance(left.func, ast.Name)
                and left.func.id == "len"
                and left.args
                and isinstance(left.args[0], ast.Name)
            ):
                continue
            if not (isinstance(right, ast.Constant) and right.value == 1):
                continue
            if isinstance(op, ast.Eq | ast.LtE):
                proven.add(left.args[0].id)
        return proven

    # -------------------------------------------------------------- rule 1

    def _check_hash_builtin(self, node: ast.Call) -> None:
        if not (isinstance(node.func, ast.Name) and node.func.id == "hash"):
            return
        if self._hash_dunder_depth:
            return
        self._flag(
            node,
            "hash-builtin",
            "hash() is salted per process (PEP 456); its value must not be "
            "stored, returned, compared or used to index. Use a stable digest "
            "(hashlib / zlib.crc32) if a key is genuinely needed, or an order "
            "the input already defines.",
        )

    # -------------------------------------------------------------- rule 2

    def _flag(self, node: ast.AST, construct: str, detail: str) -> None:
        self.findings.append(
            Finding(
                self.path,
                self.qualname,
                construct,
                getattr(node, "lineno", 0),
                detail,
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        self._check_hash_builtin(node)
        name = _call_func_name(node)
        first = node.args[0] if node.args else None

        if name in {"list", "tuple"} and first is not None and self.expr_is_set(first):
            if not self._is_singleton_guarded(first):
                self._flag(
                    node,
                    "set-materialised",
                    f"{name}(<set>) freezes PYTHONHASHSEED's iteration order into "
                    "an ordered value. Project through an order the input defines "
                    "(netlist order, coordinate order) or sort.",
                )
        elif name == "sum" and first is not None and self._float_sum_over_set(first):
            self._flag(
                node,
                "set-accumulated",
                "sum() over a set accumulates in PYTHONHASHSEED order; float "
                "addition is not associative, so the result moves by ULPs "
                "between processes.",
            )
        elif name in {"enumerate", "zip"} and first is not None and self.expr_is_set(first):
            self._flag(
                node,
                "set-indexed",
                f"{name}(<set>) pairs elements with positions PYTHONHASHSEED chose.",
            )
        elif (
            name == "next"
            and first is not None
            and isinstance(first, ast.Call)
            and _call_func_name(first) == "iter"
            and first.args
            and self.expr_is_set(first.args[0])
        ):
            self._flag(
                node,
                "set-first-element",
                "next(iter(<set>)) selects whichever element PYTHONHASHSEED put first.",
            )
        elif (
            name == "pop"
            and isinstance(node.func, ast.Attribute)
            and not node.args
            and self.expr_is_set(node.func.value)
        ):
            self._flag(
                node,
                "set-first-element",
                "<set>.pop() removes whichever element PYTHONHASHSEED put first.",
            )
        elif name == "join" and first is not None and self.expr_is_set(first):
            self._flag(
                node,
                "set-materialised",
                "join(<set>) renders elements in PYTHONHASHSEED order.",
            )

        self.generic_visit(node)

    def _is_singleton_guarded(self, node: ast.expr) -> bool:
        """True if every name feeding this expression is proven len<=1 here."""
        proven = self._singleton_names[-1]
        names = _names_read(node)
        return bool(names) and names <= proven

    def _float_sum_over_set(self, node: ast.expr) -> bool:
        """``sum()`` whose summands come from a set and are not integer literals."""
        if self.expr_is_set(node):
            return True
        if not isinstance(node, ast.GeneratorExp | ast.ListComp):
            return False
        if not node.generators or not self.expr_is_set(node.generators[0].iter):
            return False
        elt = node.elt
        if isinstance(elt, ast.Constant) and isinstance(elt.value, int):
            # `sum(1 for x in s)` is a count; integer addition is associative.
            return False
        if isinstance(elt, ast.Call) and _call_func_name(elt) == "len":
            return False
        return True

    def visit_ListComp(self, node: ast.ListComp) -> None:
        if node.generators and self.expr_is_set(node.generators[0].iter):
            self._flag(
                node,
                "set-materialised",
                "a list comprehension over a set produces a list whose order PYTHONHASHSEED chose.",
            )
        self.generic_visit(node)

    def visit_Starred(self, node: ast.Starred) -> None:
        if self.expr_is_set(node.value):
            self._flag(
                node,
                "set-materialised",
                "unpacking a set into a list/tuple display freezes PYTHONHASHSEED's order.",
            )
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        iter_node = node.iter
        enumerated = (
            isinstance(iter_node, ast.Call)
            and _call_func_name(iter_node) == "enumerate"
            and bool(iter_node.args)
        )
        target = iter_node.args[0] if enumerated else iter_node  # type: ignore[union-attr]
        if self.expr_is_set(target):
            reason = self._body_records_order(node, enumerated)
            if reason is not None:
                self._flag(
                    node,
                    "set-loop-records-order",
                    f"iterating a set and {reason}: PYTHONHASHSEED's order is "
                    "carried into an ordered artifact. Iterate an order the input "
                    "defines instead (e.g. project the set back through the "
                    "netlist), or sort.",
                )
        self.generic_visit(node)

    def _body_records_order(self, node: ast.For, enumerated: bool) -> str | None:
        """Name the first order-recording operation in a loop body, if any."""
        if enumerated:
            return "binding a positional index with enumerate()"
        loop_vars = _target_names(node.target)
        for stmt in ast.walk(node):
            if stmt is node:
                continue
            if isinstance(stmt, ast.Yield | ast.YieldFrom):
                return "yielding"
            if isinstance(stmt, ast.AugAssign) and isinstance(
                stmt.op, ast.Add | ast.Sub | ast.Mult
            ):
                return "accumulating with an augmented assignment"
            if isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    # A dict keyed by the loop variable takes the set's order as
                    # its insertion order. A dict keyed by something *derived*
                    # from it does not necessarily -- not flagged.
                    if (
                        isinstance(tgt, ast.Subscript)
                        and isinstance(tgt.slice, ast.Name)
                        and tgt.slice.id in loop_vars
                    ):
                        return (
                            "keying a dict by the loop variable (its insertion order is the set's)"
                        )
            if isinstance(stmt, ast.Call):
                if _call_func_name(stmt) in _ORDER_RECORDING_METHODS:
                    return f"calling .{_call_func_name(stmt)}()"
            if isinstance(stmt, ast.Break) and self._break_captures_element(node, loop_vars):
                return "capturing the first matching element and breaking"
        return None

    @staticmethod
    def _break_captures_element(node: ast.For, loop_vars: set[str]) -> bool:
        """True if the loop body binds a name from the loop variable.

        ``for x in s: if cond(x): found = True; break`` answers "does any element
        match", which is order-invariant. ``... : first = x; break`` answers
        "which element", which is not.
        """
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign) and _names_read(stmt.value) & loop_vars:
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name) and tgt.id not in loop_vars:
                        return True
        return False


def _collect_set_returning_functions(trees: dict[Path, ast.Module]) -> frozenset[str]:
    """Function/method names repo-wide whose return annotation is a set.

    This is what lets ``net.get_component_refs()`` be recognised as a set at a
    call site in a different file from its definition.
    """
    names: set[str] = set()
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _annotation_is_set(
                node.returns
            ):
                names.add(node.name)
    return frozenset(names)


def iter_scope_files(root: Path) -> list[Path]:
    seen: set[Path] = set()
    for pattern in INCLUDE_GLOBS:
        seen.update(p for p in root.glob(pattern) if p.is_file())
    return sorted(seen)


def analyze(root: Path, paths: list[Path]) -> list[Finding]:
    trees: dict[Path, ast.Module] = {}
    for path in paths:
        try:
            trees[path] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:  # pragma: no cover - defensive
            print(f"GATE ERROR: cannot parse {path}: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

    set_returning = _collect_set_returning_functions(trees)

    findings: list[Finding] = []
    for path, tree in trees.items():
        rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
        analyzer = _Analyzer(rel, set_returning)
        analyzer.visit(tree)
        findings.extend(analyzer.findings)
    return sorted(findings, key=lambda f: (f.path, f.line, f.construct))


def load_inventory(path: Path) -> dict[str, int]:
    entries: dict[str, int] = {}
    if not path.exists():
        return entries
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, _, count = line.rpartition(" ")
        entries[key.strip()] = int(count)
    return entries


def render_inventory(findings: list[Finding]) -> str:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.key] = counts.get(finding.key, 0) + 1
    lines = [
        "# Known salted-hash order-dependency sites. See",
        "# scripts/check_hash_order_determinism.py for what this file is and why",
        "# it is a ratchet rather than a suppression list.",
        "#",
        "# Format: <path>::<qualname>::<construct> <count>",
        "# Regenerate with: python scripts/check_hash_order_determinism.py --write-inventory",
        "# An entry that no longer fires is a FAILURE, not a pass: record the fix.",
        "#",
        "# This ledger is expected to SHRINK. Any branch that fixes one of these",
        "# sites must delete its line here in the same commit, or the gate fails",
        "# with STALE_ENTRY. That is deliberate: it is the only mechanism that",
        "# makes paid-down debt visible in a diff.",
        "",
    ]
    lines.extend(f"{key} {counts[key]}" for key in sorted(counts))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--inventory", type=Path, default=INVENTORY_PATH)
    parser.add_argument("--min-files", type=int, default=MIN_FILES_SCANNED)
    parser.add_argument(
        "--write-inventory",
        action="store_true",
        help="Rewrite the inventory from the current tree (review the diff!).",
    )
    parser.add_argument(
        "--no-inventory",
        action="store_true",
        help="Report every finding, ignoring the inventory (audit mode).",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    paths = iter_scope_files(root)
    if len(paths) < args.min_files:
        print(
            f"GATE ERROR: scope evaporated -- {len(paths)} file(s) matched "
            f"{list(INCLUDE_GLOBS)} under {root}, expected at least "
            f"{args.min_files}. A gate that scans nothing passes vacuously; "
            "refusing.",
            file=sys.stderr,
        )
        return 1

    findings = analyze(root, paths)

    if args.write_inventory:
        args.inventory.write_text(render_inventory(findings), encoding="utf-8")
        print(f"Wrote {args.inventory} ({len(findings)} finding(s)).")
        return 0

    if args.no_inventory:
        for finding in findings:
            print(finding.render())
        print(f"\n{len(findings)} finding(s) in {len(paths)} scanned file(s).")
        return 1 if findings else 0

    inventory = load_inventory(args.inventory)
    seen: dict[str, list[Finding]] = {}
    for finding in findings:
        seen.setdefault(finding.key, []).append(finding)

    new_sites: list[Finding] = []
    grew: list[tuple[str, int, int]] = []
    for key, group in seen.items():
        allowed = inventory.get(key, 0)
        if len(group) > allowed:
            if allowed == 0:
                new_sites.extend(group)
            else:
                grew.append((key, allowed, len(group)))
    stale = sorted(key for key in inventory if key not in seen)
    shrank = sorted(
        (key, inventory[key], len(seen[key]))
        for key in inventory
        if key in seen and len(seen[key]) < inventory[key]
    )

    if not (new_sites or grew or stale or shrank):
        print(
            f"OK: {len(findings)} known salted-hash order site(s) in "
            f"{len(paths)} scanned file(s); no new ones."
        )
        return 0

    print("FAIL: salted-hash order gate\n")
    for finding in new_sites:
        print(f"NEW_SITE               {finding.render()}")
    for key, was, now in grew:
        print(f"COUNT_GREW             {key}: {was} -> {now}")
    for key, was, now in shrank:
        print(f"COUNT_SHRANK           {key}: {was} -> {now} (record the fix)")
    for key in stale:
        print(f"STALE_ENTRY            {key} no longer fires (record the fix)")
    print(
        "\nA NEW_SITE derives an ordered or numeric result from something "
        "PYTHONHASHSEED randomises per process. See this script's docstring for "
        "the six sites that motivated the gate and what a correct fix looks "
        "like. STALE_ENTRY/COUNT_SHRANK mean debt was paid but the ledger was "
        f"not updated: rerun with --write-inventory and commit {args.inventory.name}."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
