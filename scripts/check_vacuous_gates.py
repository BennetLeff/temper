#!/usr/bin/env python3
"""Anti-vacuous-truth gate: reject unguarded ``all(...)`` in gate and
validator modules.

``all()`` over an empty collection is vacuously ``True`` in Python -- a
verification function that aggregates per-item results with a bare
``all(...)`` therefore reports a clean verdict for input it never
actually measured -- see docs/METHODOLOGY.md Sec 4 ("vacuous", failure
class 4) and Sec 5 ("Anti-vacuous-truth"): *"Every ``all()`` in a
checker requires a non-empty assertion in front of it."*  This gate is
the mechanical form of that rule.

``any()`` is deliberately **not** flagged: ``any()`` over an empty
collection returns ``False`` in Python, which is already the desired
fail-closed behavior for a gate -- "nothing evaluated" correctly reads
as "not passing." Flagging ``any()`` would fire on correct code, which
is itself a defect in a checker (METHODOLOGY Sec 5, specificity: a
check that fires on correct code is a defect).

Scope
-----
**2026-07-27 rewrite** (see docs/evidence/2026-07-27-gate-subset-blindness-audit.md):
the previous scope was an *include-list* keyed on ``SCOPE_TOKENS = ("gate",
"valid")`` matched against the repo-relative path substring, restricted to
``packages/*/src``. Measured against the real validator surface it covered
2 of 13 known validator modules -- worse, it structurally could not see
``scripts/*.py`` at all (``find_scope_files`` only globbed
``packages/*/src``), so every one of the CI gate scripts audited alongside
this one (``check_domain_partition.py``, ``capacity_budget_gate.py``,
``mpn_fabrication_gate.py``, ``check_derived_doc_drift.py``, this file
itself, ...) was never scanned regardless of filename. A path substring is
also both too broad (a directory named ``validation/`` sweeps in
unrelated modules) and too narrow (``domain_clearance.py``,
``drc_runner.py`` under ``deterministic/feedback/`` have neither token
anywhere in their path).

The scope is now a **default-include, narrow documented-exclude** union of:

1. Every ``.py`` file under ``packages/*/src`` (recursive), except the
   ``router_v6`` package -- excluded per the forced-segment fail-closed
   plan (``docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md``);
   see that plan's current status before assuming this exclusion still
   applies (UNVERIFIED as of this rewrite -- a concurrent agent is
   actively working router_v6 code and this gate does not touch it).
2. Every ``.py`` file under ``packages/*/tests`` (recursive) EXCEPT actual
   test modules, matched by filename convention (``test_*.py``,
   ``*_test.py``, ``conftest.py``) rather than by path substring -- the
   previous ``"/tests/"`` substring exclusion silently dropped real
   validator *implementation* modules that happen to live under a
   ``tests/requirements/validators/`` tree (``isolation.py``,
   ``emi_filter.py``, ``ground_plane.py``, ``pick_and_place.py``,
   ``routability_check.py``, ``clearance_check.py``) even though they are
   not test files themselves. Same ``router_v6`` exclusion applies.
3. Every top-level ``.py`` file directly under ``scripts/`` (non-recursive
   -- this naturally excludes ``scripts/_lib/``, ``scripts/tests/``,
   ``scripts/spikes/``, ``scripts/templates/`` without a separate rule).

Rationale for "default-include, narrow exclude" over an allowlist: an
allowlist (of files, or of filename tokens) requires a maintainer to
remember to add every new gate/validator module to it -- exactly the
mechanism that produced the 2-of-13 blind spot in the first place. A
denylist only has to name known non-validator conventions (test files);
a new validator module added anywhere in scope is scanned automatically,
with no action required and no PR-invisible omission possible.

This is not free: the packages/*/tests union pulls in some fixture and
helper modules that are not "validators" in spirit (Hypothesis strategy
builders, golden-data generators). That is an accepted false-inclusion
cost -- the detector below only flags unguarded ``all()`` calls, so a
non-gate module with no such call produces no output either way. The
asymmetry matters: false-inclusion costs nothing when there is nothing to
flag; false-exclusion is silent forever.

Detection
---------
For every ``all(...)`` call, the gate resolves the source collection
being iterated (the comprehension's ``.iter``, or the bare call
argument) and considers the call **guarded** -- and therefore OK -- if
either:

1. an earlier statement in the same function/module (`if not <expr>:`,
   `assert <expr>`, or `assert len(<expr>)`) asserts the collection is
   non-empty before the call, or
2. the comprehension's predicate/element itself performs a per-item
   ``is None`` / ``is not None`` check -- i.e. it already treats a
   missing/unmeasured item as failing rather than passing it through.

This is a syntactic heuristic, not a prover: it is deliberately
conservative (favors false negatives over false positives) so it stays
usable as a hard CI gate rather than a noisy advisory one.

This gate asserts zero unguarded calls directly -- there is no
allowlist. Once a gate/validator module ships with an unguarded
``all()``, fix it; don't accumulate an exception file (see commit
df862924, which collapsed ``import-linter-baseline.yaml`` the same way
once it reached zero).

Tautological assertions
------------------------
**2026-07-28 addition.** A second, related failure class: an ``assert``
whose truth value cannot depend on the code under test --
``packages/temper-placer/tests/requirements/safety/test_clearance.py``
shipped, verbatim, ``assert result.passed or not result.passed  #
Depends on actual implementation`` in the safety clearance suite. It
reads like coverage in a diff and a test-count summary and asserts
nothing: the expression is ``True`` for every possible ``result``. This
gate's own scope (above) would not have caught it even if it checked
assertions, because that scope deliberately *excludes* ``test_*.py``
files -- they are exactly where a tautological ``assert`` does its
damage (a vacuous ``all()`` lives in a validator; a vacuous ``assert``
lives in the test that is supposed to catch the validator being wrong).
So tautological-assertion detection uses its **own**, wider scope:
``find_tautology_scope_files`` (see below) includes test-named files.

Patterns detected (four; each chosen because it is a syntactic shape
that is *always* true independent of runtime values, not merely true
today):

1. ``assert X or not X`` / ``assert not X or X`` -- direct tautology.
   Flagged only when the shared core expression ``X`` is Call-free.
   Rationale: with a bare ``Call`` (e.g. ``assert f() or not f()``),
   Python evaluates the call fresh each time it is reached, so the two
   occurrences are not guaranteed to observe the same value (a mocked,
   stateful, or genuinely nondeterministic ``f`` could return
   differently across the two evaluations) -- the syntactic tautology
   argument no longer goes through. Excluding calls trades a
   (currently unobserved in this repo) false negative for eliminating
   that false-positive class outright.

2. ``assert X or True`` / ``assert True or X`` (also literal ``1`` in
   the ``True`` position) -- the assertion is vacuously true regardless
   of ``X``, and unlike (1) this holds even when ``X`` contains a call:
   either ``X`` is evaluated and its result discarded (``X or True``),
   or it is never evaluated at all (``True or X``, short-circuited) --
   both are always-pass by construction, no exception needed.

3. ``assert X is X`` -- flagged only when Call-free. ``is`` on a
   syntactically identical Call-free expression re-reads the exact same
   object twice (no allocation in between), so it is always ``True`` --
   **and, unlike ``==``, this holds for every type, including NaN
   floats** (``is`` compares identity, not value; a NaN *is* itself even
   though it does not *equal* itself). There is therefore no legitimate
   NaN-check reading of ``X is X``, which is why it is flagged
   unconditionally (modulo the Call exclusion) while ``X == X`` is not
   (next).

4. ``assert X == X`` -- flagged **only when both sides are pure
   literals** (``ast.Constant``, or a ``Tuple``/``List``/``Set`` built
   only from pure literals, recursively) -- e.g. ``assert (1, 2) == (1,
   2)``. **Deliberately not flagged for a bare name/attribute/subscript**
   (``assert x == x``, ``assert result.value == result.value``): this
   is the idiomatic self-equality NaN guard (``nan == nan`` is
   ``False`` in IEEE 754; ``x == x`` is a real, if terse, "``x`` is not
   NaN" assertion for any variable that might hold a float). A checker
   that flagged this shape would fire on legitimate numeric code
   -- exactly the "gets disabled" failure mode this gate's own docstring
   warns about elsewhere. Literal-vs-itself has no such reading (a
   written-out literal cannot be NaN -- Python has no NaN literal
   syntax), so it is safe to flag.

**Deliberately not attempted, and why:**

- ``assert X >= X`` / ``assert X <= X`` -- these have the *same* NaN-guard
  reading as ``X == X`` (``nan >= nan`` and ``nan <= nan`` are both
  ``False`` in IEEE 754, so ``x >= x`` is exactly as legitimate a
  "not NaN" idiom as ``x == x``). Extending the literal-only carve-out to
  these operators was considered and rejected: zero real hits in this
  repo made the extra surface area not worth the risk of a future false
  positive on a genuine range/monotonicity check shaped like ``lo <= lo``.
- A general "structurally always-true comparison" prover (e.g. symbolic
  simplification of arbitrary boolean expressions) -- out of scope for a
  syntactic heuristic; the four shapes above were chosen because each is
  a *literal* pattern seen (or, for ``is``/literal-``==``, a direct
  generalization of one seen) in this repo, not a speculative case.
- ``assert True`` / ``assert 1`` **bare, with something before them in
  the same block** -- deliberately NOT flagged. A test that calls a
  risky operation and then writes a bare ``assert True`` afterward is
  using it as an (unidiomatic but real) smoke test: "the line above
  would have raised if this were broken." Three such cases exist in
  this repo today (``test_loop_termination_pbt.py``,
  ``test_finish_board_gate.py``, ``test_hv_lv_golden_fixture.py``), all
  preceded by a real operation (an assertion on a prior result, a
  skip-guard, a snapshot-regeneration branch) -- all correctly excluded.
  ``assert True`` / ``assert 1`` **is** flagged when it is the block's
  first substantive statement (no non-docstring, non-``pass``
  statement precedes it) -- nothing ran that this could even
  implicitly be smoke-testing, so it is unconditionally vacuous.

Combined with pattern (1)'s Call exclusion, this also correctly leaves
alone ``assert sha256_file(f) == sha256_file(f)`` (in
``scripts/tests/_lib/test_lib_measurement_provenance.py``) and the
analogous ``compute_inputs_digest`` case in
``test_lib_freshness.py``: syntactically self-identical, but both sides
are calls, and the assertion is testing something real -- that the
function is *deterministic* (same input -> same output across two
independent invocations) -- not asserting a tautology.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import ast
import re

from rich.console import Console

console = Console()

# Only all() is vacuous. any() over an empty collection is already
# fail-closed (returns False) -- see module docstring.
AGGREGATORS = {"all"}

# Package excluded from scope entirely (see module docstring: frozen per
# the forced-segment fail-closed plan; UNVERIFIED whether still current).
EXCLUDED_PACKAGE = "router_v6"

# Filename conventions that mark a file as an actual test module rather
# than a validator/gate implementation -- matched on the filename only,
# never on path substring (see module docstring for why "/tests/" as a
# path substring is wrong: it drops real validator implementations that
# happen to live under a tests/requirements/validators/ tree).
_TEST_FILENAME_RE = re.compile(r"^(test_.*|.*_test|conftest)\.py$")

_GUARD_RE_TEMPLATES = [
    r"if\s+not\s+{expr}\b",
    r"assert\s+{expr}\b",
    r"assert\s+len\(\s*{expr}\s*\)",
    r"if\s+len\(\s*{expr}\s*\)\s*==\s*0",
]

_STRIP_SUFFIX_RE = re.compile(r"\.(values|keys|items)\(\)$")


# ---------------------------------------------------------------------------
# scope
# ---------------------------------------------------------------------------


def _is_router_v6(rel_path: str) -> bool:
    """True when *rel_path* falls under the excluded router_v6 package."""
    parts = rel_path.split("/")
    return EXCLUDED_PACKAGE in parts


def find_packages_scope_files(packages_dir: Path) -> list[Path]:
    """Return every in-scope ``.py`` file under ``packages/*/src`` and
    ``packages/*/tests`` (see module docstring for the exclusion rules)."""
    results: list[Path] = []
    for src_dir in sorted(packages_dir.glob("*/src")):
        for py_file in sorted(src_dir.rglob("*.py")):
            rel = py_file.relative_to(packages_dir.parent).as_posix()
            if _is_router_v6(rel):
                continue
            results.append(py_file)
    for tests_dir in sorted(packages_dir.glob("*/tests")):
        for py_file in sorted(tests_dir.rglob("*.py")):
            rel = py_file.relative_to(packages_dir.parent).as_posix()
            if _is_router_v6(rel):
                continue
            if _TEST_FILENAME_RE.match(py_file.name):
                continue
            results.append(py_file)
    return results


def find_scripts_scope_files(scripts_dir: Path) -> list[Path]:
    """Return every top-level ``.py`` file directly under ``scripts/``.

    Non-recursive by construction: this naturally excludes ``_lib/``,
    ``tests/``, ``spikes/``, and ``templates/`` subdirectories without a
    separate exclusion rule.
    """
    if not scripts_dir.is_dir():
        return []
    return sorted(
        f for f in scripts_dir.glob("*.py") if f.is_file() and f.name != "__init__.py"
    )


def find_scope_files(packages_dir: Path, scripts_dir: Path | None = None) -> list[Path]:
    """Return every in-scope ``.py`` file (packages + top-level scripts/)."""
    results = find_packages_scope_files(packages_dir)
    if scripts_dir is not None:
        results.extend(find_scripts_scope_files(scripts_dir))
    return results


# ---------------------------------------------------------------------------
# detection
# ---------------------------------------------------------------------------


def _root_node(call: ast.Call) -> ast.AST | None:
    """Return the AST node for the collection an all() call iterates."""
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, (ast.GeneratorExp, ast.ListComp, ast.SetComp)) and arg.generators:
        return arg.generators[0].iter
    return arg


def _is_literal_source(node: ast.AST | None) -> bool:
    """True when the iterated collection is a non-empty literal.

    ``all(x in name for x in ["a", "b"])``-style keyword matching over a
    fixed literal written at the call site can never be "unmeasured" --
    the cardinality is baked into the source, not into runtime input.
    That is a different concern from the vacuity this gate targets, so
    such calls are out of scope.
    """
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(node.elts) > 0
    return False


def _root_expr(call: ast.Call) -> tuple[str, bool]:
    """Return ``(root_source, is_comprehension)`` for an all() call.

    ``root_source`` is the unparsed source of the collection being
    iterated (comprehension ``.iter``, or the bare call argument).
    """
    node = _root_node(call)
    if node is None:
        return "", False
    arg = call.args[0]
    is_comp = isinstance(arg, (ast.GeneratorExp, ast.ListComp, ast.SetComp)) and bool(
        arg.generators
    )
    return _STRIP_SUFFIX_RE.sub("", ast.unparse(node)), is_comp


def _inline_none_guarded(call: ast.Call) -> bool:
    """True if the comprehension already performs a per-item None check."""
    if not call.args:
        return False
    arg = call.args[0]
    if not isinstance(arg, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
        return False
    pieces = [ast.unparse(arg.elt)]
    pieces.extend(ast.unparse(cond) for gen in arg.generators for cond in gen.ifs)
    text = " ".join(pieces)
    return bool(re.search(r"\bis\s+(not\s+)?None\b", text))


def _preceding_guard(
    scope_source_lines: list[str],
    start_line: int,
    end_line: int,
    root: str,
) -> bool:
    """True if any line in ``[start_line, end_line)`` guards *root*."""
    if not root:
        return False
    patterns = [
        re.compile(t.format(expr=re.escape(root))) for t in _GUARD_RE_TEMPLATES
    ]
    for lineno in range(start_line, end_line):
        if lineno < 1 or lineno > len(scope_source_lines):
            continue
        line = scope_source_lines[lineno - 1]
        if any(p.search(line) for p in patterns):
            return True
    return False


def _sibling_guard(enclosing_stmt: ast.stmt | None, root: str) -> bool:
    """True if *root* is guarded elsewhere in the same statement.

    Catches ``return all(...) and bool(items)``-shaped expressions where
    the non-empty check sits beside the aggregation rather than on a
    preceding line.
    """
    if not root or enclosing_stmt is None:
        return False
    text = ast.unparse(enclosing_stmt)
    return bool(re.search(rf"not\s+{re.escape(root)}\b", text))


def find_violations(py_file: Path) -> list[tuple[int, str]]:
    """Return ``[(lineno, snippet), ...]`` of unguarded all() calls."""
    try:
        source = py_file.read_text()
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        console.print(f"[yellow]WARNING: syntax error in {py_file}, skipping[/]")
        return []

    lines = source.splitlines()
    violations: list[tuple[int, str]] = []

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def enclosing_scope_start(node: ast.AST) -> int:
        cur = node
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cur.lineno
        return 1

    def enclosing_stmt(node: ast.AST) -> ast.stmt | None:
        cur = node
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, ast.stmt):
                return cur
        return None

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id not in AGGREGATORS:
            continue

        if _is_literal_source(_root_node(node)):
            continue

        if _inline_none_guarded(node):
            continue

        root, _is_comp = _root_expr(node)
        scope_start = enclosing_scope_start(node)
        if _preceding_guard(lines, scope_start, node.lineno, root):
            continue
        if _sibling_guard(enclosing_stmt(node), root):
            continue

        snippet = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
        violations.append((node.lineno, snippet))

    return violations


# ---------------------------------------------------------------------------
# tautological-assertion scope
# ---------------------------------------------------------------------------


def find_tautology_scope_files(
    packages_dir: Path, scripts_dir: Path | None = None
) -> list[Path]:
    """Return every in-scope ``.py`` file for tautological-assertion detection.

    Deliberately **wider** than ``find_scope_files`` above: this scope
    *includes* files matching the test-module naming convention
    (``test_*.py`` / ``*_test.py`` / ``conftest.py``) that the all()-scope
    excludes, and it walks ``scripts/`` recursively rather than
    top-level-only. Both differences exist for the same reason: a
    tautological ``assert`` does its damage precisely inside test
    functions (that is where both real hits in this repo live -- see
    module docstring), so excluding test-named files here -- as is
    correct for the all()-aggregation scope, which targets validator
    *implementations* -- would silently exempt the exact files this
    detector exists to cover. The ``router_v6`` exclusion carries over
    unchanged (same frozen-package rationale as ``find_scope_files``).
    """
    results: list[Path] = []
    for src_dir in sorted(packages_dir.glob("*/src")):
        for py_file in sorted(src_dir.rglob("*.py")):
            rel = py_file.relative_to(packages_dir.parent).as_posix()
            if _is_router_v6(rel):
                continue
            results.append(py_file)
    for tests_dir in sorted(packages_dir.glob("*/tests")):
        for py_file in sorted(tests_dir.rglob("*.py")):
            rel = py_file.relative_to(packages_dir.parent).as_posix()
            if _is_router_v6(rel):
                continue
            results.append(py_file)
    if scripts_dir is not None and scripts_dir.is_dir():
        for py_file in sorted(scripts_dir.rglob("*.py")):
            if py_file.name == "__init__.py":
                continue
            results.append(py_file)
    return results


# ---------------------------------------------------------------------------
# tautological-assertion detection
# ---------------------------------------------------------------------------

# Constant values that make an ``X or <literal>`` / ``<literal> or X``
# disjunction vacuously true regardless of X (see module docstring,
# pattern 2). Only True/1 per the patterns actually specified/observed;
# not generalized to arbitrary truthy literals (e.g. non-empty strings)
# to keep the flagged shape recognizable as the ``or True`` idiom rather
# than catching unrelated "assert X or <fallback-ish literal>" code this
# gate has no evidence is vacuous in practice.
_OR_TRUE_VALUES = (True, 1)


def _dump(node: ast.AST) -> str:
    """Structural fingerprint of *node*, position-independent."""
    return ast.dump(node, annotate_fields=False)


def _contains_call(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) for n in ast.walk(node))


def _strip_not(node: ast.expr) -> tuple[ast.expr, bool]:
    """Return ``(core, was_negated)``, unwrapping one leading ``not``."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return node.operand, True
    return node, False


def _is_pure_literal(node: ast.AST) -> bool:
    """True for a literal with no runtime-dependent sub-expression.

    Covers ``ast.Constant`` and literal ``Tuple``/``List``/``Set``
    built only from pure literals (recursively). Used to gate the
    ``X == X`` self-equality pattern to the shapes that can never be
    the legitimate float-NaN self-equality idiom (see module docstring
    pattern 4) -- a hand-written literal cannot be NaN, since Python
    has no NaN literal syntax.
    """
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        if not node.elts:
            # Empty tuple/list/set literal -- trivially a pure literal (no
            # element to fail the check). This all() would otherwise be an
            # unguarded aggregation over a reachable-empty collection; here
            # the vacuous-True IS the correct answer, made explicit rather
            # than left for check_vacuous_gates.py to flag as a maybe-bug.
            return True
        return all(_is_pure_literal(elt) for elt in node.elts)
    return False


def _is_or_true(test: ast.expr) -> bool:
    """True if *test* is ``... or True``-shaped (module docstring #2)."""
    if not (isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or)):
        return False
    return any(
        isinstance(v, ast.Constant) and v.value in _OR_TRUE_VALUES
        for v in test.values
    )


def _is_or_not_self(test: ast.expr) -> bool:
    """True if *test* is ``X or not X`` / ``not X or X`` (docstring #1)."""
    if not (
        isinstance(test, ast.BoolOp)
        and isinstance(test.op, ast.Or)
        and len(test.values) == 2
    ):
        return False
    a, b = test.values
    a_core, a_neg = _strip_not(a)
    b_core, b_neg = _strip_not(b)
    if a_neg == b_neg:
        return False
    if _contains_call(a_core) or _contains_call(b_core):
        return False
    return _dump(a_core) == _dump(b_core)


def _self_compare_kind(test: ast.expr) -> str | None:
    """Return ``"is-self"``/``"eq-self-literal"`` for a self-comparison
    (docstring #3/#4), else ``None``."""
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1):
        return None
    left, op, right = test.left, test.ops[0], test.comparators[0]
    if _dump(left) != _dump(right):
        return None
    if _contains_call(left):
        return None
    if isinstance(op, ast.Is):
        return "is-self"
    if isinstance(op, ast.Eq) and _is_pure_literal(left):
        return "eq-self-literal"
    return None


def _is_bare_truthy_literal(test: ast.expr) -> bool:
    """True for a bare ``True``/``1`` assert target (docstring pattern 5,
    subject to the sole-statement guard applied by the caller)."""
    return isinstance(test, ast.Constant) and test.value in _OR_TRUE_VALUES


def _is_inert_stmt(stmt: ast.stmt) -> bool:
    """True for a statement with no runtime effect: a docstring/bare
    string-literal expression, or ``pass``. Used to decide whether a
    bare ``assert True`` has anything real preceding it in its block."""
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
        return isinstance(stmt.value.value, str)
    return False


_TAUTOLOGY_MESSAGES = {
    "or-not": (
        "tautological assertion: {snippet!r}. `X or not X` is true for"
        " every value of X; this asserts nothing about the code under"
        " test. Assert a concrete expected outcome instead."
    ),
    "or-true": (
        "tautological assertion: {snippet!r}. An `or True`/`True or`"
        " disjunct makes this assertion pass unconditionally regardless"
        " of the other operand."
    ),
    "is-self": (
        "tautological assertion: {snippet!r}. `X is X` re-reads the same"
        " object twice and is always true; it does not check anything"
        " about X's value."
    ),
    "eq-self-literal": (
        "tautological assertion: {snippet!r}. Both sides of `==` are the"
        " same literal; this is always true regardless of the code"
        " under test."
    ),
    "bare-literal": (
        "vacuous assertion: {snippet!r} asserts a hardcoded literal with"
        " nothing preceding it in this block -- it cannot even function"
        " as an implicit smoke test for a prior operation. Assert a real"
        " invariant, or remove it."
    ),
}


def find_tautology_violations(py_file: Path) -> list[tuple[int, str, str]]:
    """Return ``[(lineno, snippet, kind), ...]`` of tautological asserts."""
    try:
        source = py_file.read_text()
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        console.print(f"[yellow]WARNING: syntax error in {py_file}, skipping[/]")
        return []

    lines = source.splitlines()

    def snippet_for(lineno: int) -> str:
        return lines[lineno - 1].strip() if lineno <= len(lines) else ""

    violations: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        kind: str | None = None
        if _is_or_not_self(test):
            kind = "or-not"
        elif _is_or_true(test):
            kind = "or-true"
        else:
            kind = _self_compare_kind(test)
        if kind is not None:
            violations.append((node.lineno, snippet_for(node.lineno), kind))

    # Bare `assert True` / `assert 1`: only when nothing substantive
    # precedes it in its own statement block (module docstring pattern 5).
    for stmt_node in ast.walk(tree):
        for _field, value in ast.iter_fields(stmt_node):
            if not isinstance(value, list):
                continue
            if not value:
                continue
            if not all(isinstance(v, ast.stmt) for v in value):
                continue
            for idx, stmt in enumerate(value):
                if not (isinstance(stmt, ast.Assert) and _is_bare_truthy_literal(stmt.test)):
                    continue
                preceding = value[:idx]
                # `not preceding` (idx == 0, this assert is the block's
                # first statement) makes the all() vacuously True on
                # purpose: "nothing precedes it" is exactly the condition
                # this pattern targets, so the vacuous-True case IS a hit,
                # not a checker blind spot -- written explicitly so
                # check_vacuous_gates.py's own guard heuristic recognizes it.
                if not preceding or all(_is_inert_stmt(s) for s in preceding):
                    violations.append(
                        (stmt.lineno, snippet_for(stmt.lineno), "bare-literal")
                    )

    return violations


def find_all_tautology_violations(
    packages_dir: Path, scripts_dir: Path | None, repo_root: Path
) -> tuple[dict[str, tuple[int, str, str]], int]:
    """Scan every tautology-scope file. Same ``(results, files_scanned)``
    contract as ``find_all_violations`` (see its docstring)."""
    results: dict[str, tuple[int, str, str]] = {}
    scope_files = find_tautology_scope_files(packages_dir, scripts_dir)
    for py_file in scope_files:
        rel = _rel_str(py_file, repo_root)
        for lineno, snippet, kind in find_tautology_violations(py_file):
            results[f"{rel}:{lineno}"] = (lineno, snippet, kind)
    return results, len(scope_files)


def _rel_str(py_file: Path, repo_root: Path) -> str:
    try:
        return py_file.relative_to(repo_root).as_posix()
    except ValueError:
        return py_file.as_posix()


def find_all_violations(
    packages_dir: Path, scripts_dir: Path | None, repo_root: Path
) -> tuple[dict[str, tuple[int, str]], int]:
    """Scan every in-scope file.

    Returns ``({key: (lineno, snippet)}, files_scanned)`` -- the second
    element is the denominator this gate must report on both pass and
    fail (see docs/evidence/2026-07-27-gate-subset-blindness-audit.md:
    a gate reporting "0 violations" without also reporting how many
    files it looked at cannot be distinguished from a gate that scanned
    nothing).
    """
    results: dict[str, tuple[int, str]] = {}
    scope_files = find_scope_files(packages_dir, scripts_dir)
    for py_file in scope_files:
        rel = _rel_str(py_file, repo_root)
        for lineno, snippet in find_violations(py_file):
            results[f"{rel}:{lineno}"] = (lineno, snippet)
    return results, len(scope_files)


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Anti-vacuous-truth gate: require a non-empty guard"
        " (or per-item None check) in front of every all() in gate and"
        " validator modules, and reject tautological assert expressions"
        " (X or not X, X or True, X is X, literal X == X, bare assert"
        " True/1) anywhere in packages/scripts, including test files"
    )
    parser.add_argument(
        "--packages-dir",
        type=Path,
        default="packages",
        help="Path to the packages/ directory (default: packages)",
    )
    parser.add_argument(
        "--scripts-dir",
        type=Path,
        default="scripts",
        help="Path to the top-level scripts/ directory (default: scripts)."
        " Pass a nonexistent path to disable this half of the scan"
        " (used by falsifier tests) -- find_scripts_scope_files returns"
        " an empty list for a non-directory rather than erroring.",
    )

    args = parser.parse_args()

    packages_dir = args.packages_dir
    if not packages_dir.is_absolute():
        packages_dir = Path.cwd() / packages_dir

    scripts_dir = args.scripts_dir
    if not scripts_dir.is_absolute():
        scripts_dir = Path.cwd() / scripts_dir

    if not packages_dir.is_dir():
        console.print(f"[red]Packages directory not found: {packages_dir}[/]")
        sys.exit(1)

    repo_root = packages_dir.parent
    violations, files_scanned = find_all_violations(packages_dir, scripts_dir, repo_root)
    taut_violations, taut_files_scanned = find_all_tautology_violations(
        packages_dir, scripts_dir, repo_root
    )

    denominator = (
        f"Scanned {files_scanned} file(s) in scope"
        f" ({packages_dir}/*/src + */tests, {scripts_dir or '<disabled>'}/*.py)."
    )
    taut_denominator = (
        f"Scanned {taut_files_scanned} file(s) in tautology scope"
        f" ({packages_dir}/*/src + */tests (incl. test-named files),"
        f" {scripts_dir or '<disabled>'}/**/*.py)."
    )

    if files_scanned == 0 or taut_files_scanned == 0:
        console.print(
            f"[red]FAIL (closed): {denominator} {taut_denominator} An"
            f" anti-vacuous-truth gate that scans zero files cannot report a"
            f" meaningful pass -- this is exactly the failure mode this gate"
            f" exists to catch. Check --packages-dir/--scripts-dir.[/]"
        )
        sys.exit(1)

    if violations:
        for key in sorted(violations):
            lineno, snippet = violations[key]
            console.print(
                f"[red]FAIL: {key} — unguarded aggregation: {snippet!r}."
                f" all() over an empty collection is vacuously True;"
                f" assert non-empty (or a per-item None check) before"
                f" aggregating.[/]"
            )

    if taut_violations:
        for key in sorted(taut_violations):
            lineno, snippet, kind = taut_violations[key]
            message = _TAUTOLOGY_MESSAGES[kind].format(snippet=snippet)
            console.print(f"[red]FAIL: {key} — {message}[/]")

    total = len(violations) + len(taut_violations)
    if total:
        console.print(
            f"[red]{denominator} {len(violations)} unguarded-aggregation"
            f" violation(s). {taut_denominator} {len(taut_violations)}"
            f" tautological-assertion violation(s).[/]"
        )
        sys.exit(1)

    console.print(
        f"[green]Anti-vacuous-truth gate passed. {denominator} 0 violations."
        f" {taut_denominator} 0 violations.[/]"
    )


if __name__ == "__main__":
    main()
