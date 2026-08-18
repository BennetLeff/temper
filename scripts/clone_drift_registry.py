"""Clone-drift registry — the SSOT for function PAIRS known to have been
cloned from one another, so a future silent divergence between them is a
CI failure instead of a rediscovery.

Why this file exists (and how it differs from the two registries it sits
next to)
---------------------------------------------------------------------------
``duplicate_predicate_registry.py`` / ``check_duplicate_predicates.py``
catch a NEW independent copy of a predicate that has already been
consolidated onto one shared implementation — the fix there is "delegate,
don't reimplement".

``check_fact_registry_drift.py`` catches a scalar FACT (a number or a
string) declared in more than one place drifting out of agreement — the
fix there is "the values must match".

Neither catches the shape 2026-08-17's task brief is built around: **one
FILE cloned from another, on purpose, with NO shared implementation and NO
intention of ever re-consolidating them** (a pour-topology generator for
``gnd`` on In1.Cu and one for ``+3V3``/``vcc``/``+15V``/``V_BUS_SENSE`` on
In2.Cu genuinely are two different generators; forcing them onto one
shared function would re-introduce the multi-rail-vs-single-rail
impedance mismatch the fork exists to avoid). The clone is legitimate.
What is NOT legitimate is a FIX landing in one twin and never propagating
to the other — the exact thing that hit ``_power_islands.py``/
``_ground_plane.py`` three separate times in one day (2026-08-17):

  1. ``STITCH_TRACE_WIDTH_MM`` — a *scalar fact*, already the shape
     ``check_fact_registry_drift.py`` exists for (not re-registered here;
     see that gate's ``default_via_diameter_mm`` family for the same
     kind of via-geometry constant already covered).
  2. A comment in ``_power_islands.py`` asserting the two constants were
     "identical" — natural-language prose, not a value or an AST shape
     any mechanical gate can verify; see "What this does NOT catch"
     below.
  3. ``_blocked()`` and the via-drop stub — ``_ground_plane.py`` was
     fixed (2026-08-16, "fix/route-to-100-percent") to buffer the
     candidate line by its own half-width and check it against real
     per-net-pair-clearance foreign-copper obstacle sets;
     ``_power_islands.py``'s copies were cloned from a PRE-FIX version of
     ``_ground_plane.py`` and never received the fix, producing +77
     ``shorting_items`` once stitch width reached spec (PR #1329's own
     regression). Fixed 2026-08-17 by PR #1332 (commit ``4da46bac2``,
     ``docs/evidence/2026-08-17-stitch-congestion-rootcause-and-fix.md``).
     **THIS is the shape this registry exists to catch**: a *structural*
     divergence (an entire obstacle-check branch present in one twin and
     absent in the other) between two functions that are provably clones
     of one another, not a scalar value.

Mechanism
---------
Exact textual comparison of two clone functions drowns in false
positives (variable renames, an extra blank line, a comment) the instant
either twin receives ANY unrelated edit. A purely semantic
("do these two functions compute the same thing for all inputs")
comparison is not tractable in general and definitely not for functions
that call out to Shapely geometry, `pcb` parse state, and net-topology
data structures.

The middle ground this registry uses, mirroring
``check_geometry_primitive_duplication.py``'s own "structural, not
textual, not semantic" choice for a single fixed function shape:
NORMALIZED-AST STRUCTURAL SIMILARITY. Each registered pair's two function
bodies are parsed, every ``Name``/``Attribute``/``Constant``/``arg`` leaf
is collapsed to a type-tagged placeholder (so a variable rename, a
different net-class string literal, or a different clearance constant
does NOT count as drift), and the resulting token sequences are compared
with ``difflib.SequenceMatcher.ratio()``. What DOES move the score:
control-flow shape — an ``if`` branch present in one twin and missing in
the other, a different number of boolean conditions, a call to a
function the other twin never calls (``other_copper_fcu_backbone``,
``routed_fcu_backbone`` in the ``_blocked`` incident above) — exactly the
"a whole check silently absent" shape #1329's regression was.

Each :class:`ClonePair` below carries the LIVE similarity score measured
at the moment it was registered, minus a small tolerance, as
``min_similarity``: a floor. A future edit to EITHER twin that pushes the
live score below the floor is a VIOLATION — either an accidental
divergence (the #1329 shape: one twin fixed, the other cloned-and-stale)
or a genuinely new, INTENTIONAL divergence that was never recorded here.
Either way the registry must be touched deliberately (raise or justify a
new floor with a reason), the same discipline
``check_duplicate_predicates.py``'s docstring describes for its own
families and ``check_geometry_primitive_duplication.py``'s allowlist
enforces for its structural fingerprint.

This is deliberately an EXPLICIT, hand-reviewed registry (mirrors
``check_fact_registry_drift.py``'s own "Design" section rationale, and
``duplicate_predicate_registry.py``'s), not a whole-repo pairwise AST
sweep running on every PR: a full O(n^2) function-pair comparison across
~700 non-test Python files is a research/audit tool
(``scripts/find_clone_pairs.py``, committed alongside this registry,
NOT wired into CI), not a gate. Registering a newly-discovered clone pair
here is itself the deliberate, reviewed act of adopting it as a
regression guard — the same convention ``CONSOLIDATED_FAMILIES`` and the
per-netclass via-geometry table in ``check_fact_registry_drift.py`` both
already use.

What this does NOT catch
-------------------------
- A BRAND NEW clone pair that has never been registered. Finding those is
  ``scripts/find_clone_pairs.py``'s job, run by a human periodically (or
  whenever two files "smell" cloned), same limitation
  ``check_duplicate_predicates.py``'s own docstring states for new
  duplicate-predicate families.
- A natural-language claim (a comment, a docstring) about two constants
  or two functions being "the same" — incident #2 in the motivation above.
  There is no AST for prose. The only mechanical defence against a false
  comment is to delete the comment and replace the claim with something a
  gate CAN check (a :class:`ClonePair` entry, or, for a scalar, a
  ``check_fact_registry_drift.py`` ``Fact``) — which is what
  ``_power_islands.py``'s current header comment does now (it cites this
  registry and the fact-registry gate instead of asserting equality in
  prose).
- Whether either twin's OWN logic is correct in isolation — this registry
  only proves the two twins have not drifted apart from each other
  further than the registered floor allows. A bug present in BOTH twins
  identically (the exact failure mode the 2026-08-13 point-to-segment
  audit found for oracle-pinned Rust kernels) is invisible to a
  similarity comparison by construction.
- A rename that changes a function's qualified name. ``extract_function``
  fails closed (TOOL ERROR) rather than silently reporting 0 pairs, but a
  human still has to notice the gate went red and re-point the registry
  entry at the new name — same limitation the geometry-primitive gate's
  own allowlist has for a deleted/renamed entry.

Exit codes (mirrors check_duplicate_predicates.py / check_fact_registry_drift.py)
------------------------------------------------------------------------------------------
  0 - CLEAN: registry non-empty, every twin function found in both files,
      every pair's live similarity >= its registered floor.
  3 - VIOLATION: at least one pair's live similarity fell below its floor.
  5 - TOOL ERROR: registry empty (vacuous), a home file is missing, a
      qualname was not found, or a qualname is AMBIGUOUS (more than one
      definition shares the identical dotted path within one file — the
      exact "scope_anchor matches 3x and silently locks onto the wrong
      window" failure mode PR #1320's own draft caught, applied here to
      qualname resolution instead of a regex anchor). Never conflated
      with "0 violations".
"""

from __future__ import annotations

import ast
import difflib
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


class RegistryError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


@dataclass(frozen=True)
class ClonePair:
    """One registered pair of functions believed to be clones of one
    another (one was written by copying the other, or both were forked
    from a common ancestor), where a future structural divergence beyond
    ``min_similarity`` should be reviewed rather than silently shipped.

    Attributes:
        name: Registry key (also used in test/CLI output).
        file_a / qualname_a: Repo-relative path and dotted def-path
            (``outer_func.inner_func`` for a nested function, or
            ``ClassName.method`` for a method) of the first twin.
        file_b / qualname_b: Same, for the second twin.
        min_similarity: Floor for the live normalized-AST similarity
            score (0.0-1.0). Registered as the live score measured at
            ``paired_on`` minus a small tolerance (this module's CLI
            reports the exact live score so a reviewer can set this
            precisely, mirroring ``check_geometry_primitive_duplication.
            py --write-allowlist``'s "measure, then record" workflow).
        evidence: Where the clone relationship (and any known/accepted
            partial divergence) is documented.
        notes: Why the two are NOT (and should not become) byte-identical
            — the known, accepted shape of the remaining gap. Every entry
            with ``min_similarity < 0.99`` should explain the delta here;
            an unexplained gap is indistinguishable from an unnoticed one.
        paired_on: ISO date this pair was registered (or its floor last
            deliberately adjusted).
    """

    name: str
    file_a: str
    qualname_a: str
    file_b: str
    qualname_b: str
    min_similarity: float
    evidence: str
    notes: str = ""
    paired_on: str = ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PAIRED_FUNCTIONS: tuple[ClonePair, ...] = (
    ClonePair(
        name="power_islands_ground_plane_blocked",
        file_a="packages/temper-placer/src/temper_placer/router_v6/_ground_plane.py",
        qualname_a="generate_ground_plane_blocks._blocked",
        file_b="packages/temper-placer/src/temper_placer/router_v6/_power_islands.py",
        qualname_b="generate_power_islands_blocks._blocked",
        # Live similarity measured 2026-08-18 post-#1332-fix: 0.877.
        # Floor set with a small tolerance below that so ordinary
        # unrelated edits (a renamed local, an added comment feeding a
        # DIFFERENT constant into the same shape) do not false-positive,
        # while a whole obstacle-check branch disappearing from either
        # twin (the #1329 shape: 2 branches instead of 4) drops the score
        # far below this floor.
        min_similarity=0.80,
        evidence=(
            "docs/evidence/2026-08-17-stitch-congestion-rootcause-and-fix.md "
            "(PR #1332, commit 4da46bac2): '_power_islands.py's copies of "
            "both functions were cloned from an *earlier* version of "
            "_ground_plane.py, before that fix landed, and never received "
            "it.' Both twins now walk the identical 3-tier check (buffered "
            "footprint -> keepout -> other_copper_fcu_backbone -> this "
            "run's own emitted copper) after #1332."
        ),
        notes=(
            "REGRESSION GUARD, not a currently-red finding — both twins "
            "were reconciled by #1332 and CLEAN as of registration. "
            "Score is <1.0 (not a byte-identical pair) because "
            "_power_islands.py's twin ALSO loops over "
            "run_new_fcu_copper (this run's OTHER, earlier-emitted power "
            "rails on the same In2.Cu net — a check _ground_plane.py has "
            "no analogue for, since gnd is a single net on In1.Cu with "
            "no sibling rails to avoid). That extra loop is the accepted, "
            "permanent structural difference; it is NOT the #1329 shape "
            "(a missing check), it is one twin legitimately doing strictly "
            "more because its problem is legitimately bigger (4 rails vs "
            "1)."
        ),
        paired_on="2026-08-18",
    ),
    ClonePair(
        name="power_islands_ground_plane_emit_segment",
        file_a="packages/temper-placer/src/temper_placer/router_v6/_ground_plane.py",
        qualname_a="generate_ground_plane_blocks._emit_segment",
        file_b="packages/temper-placer/src/temper_placer/router_v6/_power_islands.py",
        qualname_b="generate_power_islands_blocks._emit_segment",
        # Live similarity measured 2026-08-18: 0.883.
        min_similarity=0.80,
        evidence=(
            "Same incident and fix as power_islands_ground_plane_blocked "
            "above — the two segment emitters share "
            "STITCH_TRACE_WIDTH_MM/BACKBONE_LAYER emission shape and both "
            "were part of the same clone-then-diverge history."
        ),
        notes=(
            "REGRESSION GUARD. _power_islands.py's twin returns a buffered "
            "Polygon obstacle for the corridor-aware A* pass's own "
            "bookkeeping (multi-rail: this run's own new copper must be an "
            "obstacle for the NEXT rail processed in the same run); "
            "_ground_plane.py's twin returns None (gnd has no next rail in "
            "the same run). That return-value/one-extra-buffer difference "
            "is the accepted permanent gap."
        ),
        paired_on="2026-08-18",
    ),
    ClonePair(
        name="zone_pour_clearance_creepage_required",
        file_a="packages/temper-placer/src/temper_placer/router_v6/zone_pour_clearance.py",
        qualname_a="ZonePourClearanceTable.required",
        file_b="packages/temper-placer/src/temper_placer/router_v6/zone_pour_creepage.py",
        qualname_b="ZonePourCreepageTable.required",
        # Live similarity measured 2026-08-18: 0.949.
        min_similarity=0.85,
        evidence=(
            "zone_pour_creepage.py's OWN module docstring says it "
            "outright: 'Twin of :mod:`zone_pour_clearance` for the "
            "CREEPAGE constraint.' It imports OTHER_TYPES/"
            "UNASSIGNED_NETCLASS/kicad_class_name directly from "
            "zone_pour_clearance.py rather than redefining them — an "
            "acknowledged, deliberate fork of the ONE method "
            "(ZonePourClearanceTable.required's lookup-with-fallback "
            "shape) that could not be shared outright because the two "
            "tables' fallback semantics genuinely differ (see notes)."
        ),
        notes=(
            "THIS is the '#1332-shaped, legitimate and permanent' case "
            "the task brief asks the registry to distinguish from the "
            "#1329 shape. The ~5% gap is DOCUMENTED and INTENTIONAL, not "
            "an oversight: an unmatched pair resolves to "
            "``default_clearance_mm`` (0.2mm, a real minimum every pair "
            "must observe) in the clearance table, vs literal ``0.0`` (NO "
            "creepage requirement exists for that pair, per "
            "zone_pour_creepage.py's own docstring: 'A pair no creepage "
            "rule matches resolves to 0.0 in this table: KiCad's DRC "
            "applies no creepage check to such a pair') in the creepage "
            "table. Forcing these two fallbacks to match would be a "
            "SAFETY-RELEVANT change in one direction or the other (either "
            "creepage would start silently demanding 0.2mm where none is "
            "required, or clearance would stop enforcing its 0.2mm floor "
            "for unmatched pairs) — this registry must not be the reason "
            "someone 'simplifies' that away. If a future edit makes the "
            "two ``required()`` bodies MORE similar than this floor (e.g. "
            "both start returning 0.0), that is not caught by this gate "
            "either — see the 'What this does NOT catch' section in this "
            "module's own docstring; a similarity FLOOR only catches "
            "divergence, never convergence."
        ),
        paired_on="2026-08-18",
    ),
)


# ---------------------------------------------------------------------------
# AST normalization + similarity
# ---------------------------------------------------------------------------


def normalize_function_ast(node: ast.AST) -> str:
    """Structural skeleton of a function body: AST node-type tokens with
    every ``Name``/``Attribute``/``Constant``/``arg`` LEAF collapsed to a
    type-tagged placeholder, so a variable rename, a different string/
    numeric literal, or a different attribute base does not count as
    drift, but control-flow shape (branch count, boolean composition,
    which functions are CALLED, loop/comprehension shape) does. Mirrors
    ``check_geometry_primitive_duplication.py``'s "structural, not
    textual" choice, generalized from one fixed function shape to
    arbitrary function pairs.
    """
    tokens: list[str] = []

    def visit(n: ast.AST) -> None:
        if isinstance(n, ast.Name):
            tokens.append("NAME")
            return
        if isinstance(n, ast.Attribute):
            # The attribute NAME itself is structurally meaningful (a call
            # to `.intersects(...)` vs `.contains(...)` is a real
            # behavioural difference, not a rename) -- only the object
            # expression it hangs off collapses.
            tokens.append("ATTR." + n.attr)
            visit(n.value)
            return
        if isinstance(n, ast.Constant):
            tokens.append(f"CONST.{type(n.value).__name__}")
            return
        if isinstance(n, ast.arg):
            tokens.append("ARG")
            return
        tokens.append(type(n).__name__)
        for _field, value in ast.iter_fields(n):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        visit(item)
            elif isinstance(value, ast.AST):
                visit(value)

    visit(node)
    return " ".join(tokens)


def similarity(node_a: ast.AST, node_b: ast.AST) -> float:
    """difflib ratio over the two nodes' normalized token streams, in
    [0.0, 1.0]."""
    ta = normalize_function_ast(node_a)
    tb = normalize_function_ast(node_b)
    return difflib.SequenceMatcher(None, ta, tb).ratio()


# ---------------------------------------------------------------------------
# Qualname extraction (fails closed on ambiguity, mirrors the scope_anchor
# lesson from check_fact_registry_drift.py's own history)
# ---------------------------------------------------------------------------


def _all_qualified_defs(
    tree: ast.Module,
) -> tuple[dict[str, ast.AST], set[str]]:
    """Every function/method definition in *tree*, keyed by its dotted
    def-path (nested-function and class-nesting joined by '.'). Returns
    ``(defs, ambiguous)`` — ``ambiguous`` names two-or-more sibling
    definitions share the identical dotted path (e.g. two functions
    literally named the same thing nested at the same depth under the
    same parent, such as one in an ``if`` branch and one in its ``else``)
    so callers can fail closed instead of silently keeping whichever
    definition the traversal happened to see last.
    """
    defs: dict[str, ast.AST] = {}
    seen_twice: set[str] = set()

    class V(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def _visit_fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            qual = ".".join([*self.stack, node.name])
            if qual in defs:
                seen_twice.add(qual)
            else:
                defs[qual] = node
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_fn(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_fn(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

    V().visit(tree)
    return defs, seen_twice


def extract_function(repo_root: Path, file: str, qualname: str) -> ast.AST:
    """Return the AST node for *qualname* (a dotted def-path) in *file*.

    Raises :class:`RegistryError` (fail closed -- exit 5, never a silent
    wrong-answer) if: the file does not exist, does not parse, the
    qualname has no definition, or the qualname is AMBIGUOUS (more than
    one sibling definition shares it).
    """
    path = repo_root / file
    if not path.is_file():
        raise RegistryError(f"file not found: {file}")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as e:
        raise RegistryError(f"{file} does not parse: {e}") from e

    defs, ambiguous = _all_qualified_defs(tree)
    if qualname in ambiguous:
        raise RegistryError(
            f"qualname {qualname!r} is AMBIGUOUS in {file} -- more than one "
            "sibling definition shares this exact dotted path; refusing to "
            "silently pick one (the scope_anchor-matches-3x failure mode, "
            "applied to qualname resolution)"
        )
    if qualname not in defs:
        raise RegistryError(
            f"qualname {qualname!r} not found in {file} -- renamed, moved, "
            "or deleted since this pair was registered"
        )
    return defs[qualname]


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


@dataclass
class PairResult:
    pair: ClonePair
    live_similarity: float | None
    passed: bool
    error: str | None = None


def scan_pair(pair: ClonePair, repo_root: Path) -> PairResult:
    try:
        node_a = extract_function(repo_root, pair.file_a, pair.qualname_a)
        node_b = extract_function(repo_root, pair.file_b, pair.qualname_b)
    except RegistryError as e:
        return PairResult(pair=pair, live_similarity=None, passed=False, error=str(e))

    live = similarity(node_a, node_b)
    passed = live >= pair.min_similarity
    return PairResult(pair=pair, live_similarity=live, passed=passed)
