#!/usr/bin/env python3
"""Ref-designator identity-drift gate: catch safety assertions keyed to an
unstable identifier.

Motivation
----------
KiCad/atopile reference designators (``U3``, ``K1``, ``C6``, ...) are
*positional* labels, assigned by compile-order within a footprint prefix --
not stable identity. Deleting one component reflows every later same-prefix
ref down a slot: on a branch that deleted ``U3`` (the ZCD optocoupler,
``power_in.zcd_opto``), the recompiled netlist now has ``U3`` denoting
``power_mgmt.buck_3v3.buck`` (a buck converter) and ``U7`` denoting
``hb.gate_hs.boot_diode`` -- where those two refs previously named the
mains<->SELV gate-driver isolator and the ZCD optocoupler (measured
directly against that branch's compiled netlist while writing this gate;
see the evidence doc for the exact ``ref -> instance_path`` table).

``elec/domain_manifest.yaml``'s own header already states the fix: it keys
every isolator/chain declaration by ``instance_path`` -- the dotted atopile
path -- "stable across ref-designator reshuffles and across machines,
unlike the absolute path prefix." Several safety test suites do not follow
that lesson: they hardcode ref-designator string literals (``"U3"``,
``{"C6", "K1", ..., "U7"}``) as the identity of a real-board component,
so a schematic edit that reshuffles refs can leave the literal pointing at
a *different* component while the assertion keeps passing -- a green
safety test that means nothing about the parts it names. This is the same
disease as ``docs/solutions/best-practices/net-name-is-a-claim-not-an-
authority-2026-07-26.md`` (a net's *name* is not authoritative over what it
actually is) and ``.../substring-net-classification-drifts-from-ssot-
2026-07-27.md``, in a different organ: a ref designator's *string* is not
authoritative over which component it currently denotes.

What this gate does NOT do: it does not fix any test, does not touch any
safety constant/netclass/domain declaration, and is not wired into CI (see
the module's own manifest entry / the evidence doc for why -- false-positive
rate is unmeasured on its first pass, same reasoning
``check_isolation_keepout.py``'s own history argues for before hardening
any new gate to a merge-blocking status).

Discovery method -- what it finds, what it structurally cannot
----------------------------------------------------------------
1. **Ref-designator vocabulary is derived from the compiled netlist, not
   guessed.** ``discover_ref_prefixes()`` reads every component ref in
   ``elec/build/default.net`` (freshly required -- see "Freshness" below)
   and strips the trailing digits to get the live prefix set (currently
   ``C, D, F, J, K, L, PS, Q, R, RT, RV, SW, T, TP, U``). A literal is only
   a "ref-designator occurrence" if it exactly matches ``<prefix><digits>``
   for one of *this design's own* prefixes -- not a hand-typed regex that
   could silently miss a prefix this board actually uses, or match noise
   that happens to look like a ref (e.g. an arbitrary "R2" in unrelated
   prose would not match unless "R" is a live prefix, which it is here).
2. **File scope is every ``.py`` file under any directory literally named
   ``tests`` anywhere in the repo**, found by ``rglob``, not a maintained
   list of "the safety test files" -- see ``docs/solutions/best-practices/
   gate-scope-hand-maintained-blind-spot-2026-07-29.md`` for why a
   hand-maintained scope list is itself the blind spot this gate must not
   reproduce. This DOES miss: ref-designator literals in non-``tests/``
   locations (``docs/evidence/*.md`` prose, ``scripts/*.py`` gate/validator
   modules, ``elec/`` comments) -- explicitly out of scope for this pass,
   named here rather than silently dropped. It also misses ref literals
   built at runtime (``f"{prefix}{n}"``, string concatenation) -- only
   literal ``ast.Constant`` string nodes are seen.
3. **"Safety-relevant" is a keyword classifier over each candidate's
   combined context** (its own function source -- via
   ``ast.get_source_segment``, which includes comments, since it slices
   the original text -- plus its class docstring, module docstring, and
   the source of every function that (transitively, same-file) calls it).
   ``SAFETY_KEYWORDS`` is a fixed, printed-in-full vocabulary (isolation,
   barrier, creepage, clearance, mains, SELV, HV, IEC 60335/60664,
   reinforced, galvanic, dielectric, protective impedance, REQ-SAFE,
   REQ-EMC, star ground, pollution degree, ...) matched case-insensitively
   as substrings. This is a lint-grade heuristic, not a prover: **what it
   misses** is any safety-relevant test whose surrounding text uses none
   of these words (e.g. a bare numeric assertion with no prose at all).
   **What it over-includes** is any incidental use of a listed word in an
   unrelated context; the cost of that is bounded (see "Distinguishing
   safety-relevant from incidental" below) -- false-inclusion here only
   costs extra report lines, never a missed finding, matching this
   project's own stated asymmetry (``check_vacuous_gates.py``'s "Rationale
   for default-include, narrow exclude").
4. **Load-bearing vs decorative.** A ref literal only becomes a Tier-2
   ("identity assertion") finding if the AST shows it is actually *read*
   by an assertion: it sits inside an ``ast.Compare`` node (any ancestor
   depth), OR it is the value assigned to a name that is later used as a
   ``Compare`` operand or ``Subscript`` base (one hop of dataflow, with a
   bounded fixed-point over comprehension/alias chains -- see
   ``_is_load_bearing()``), OR it is a ``pytest.mark.parametrize`` value
   bound to a parameter name that is itself used the same way in the
   test body. A ref embedded in a hand-built dict that the function under
   test never reads (measured directly: see the
   ``test_temper_board_ground_plane_compliance`` finding in the evidence
   doc, where ``check_star_ground_point`` ignores the ``"ref"`` key
   entirely) is real but reported at lower confidence (Tier 1 only, not
   Tier 2) -- it is a stale-able factual claim in the test's own data, but
   changing it would not change the test's pass/fail, so it cannot itself
   produce a *silently wrong-but-green* result the way a load-bearing one
   can. **What this misses**: dataflow across more than the traced hops
   (e.g. a ref laundered through a third helper function, or a `**kwargs`
   spread) will read as "not load-bearing" when it may in fact be.
5. **Real-board-bound vs shape-only (verification tier).** A Tier-2 finding
   is additionally checked for whether its function (or its transitive
   same-file call chain) actually loads real, compiled design data --
   detected by source-text match against ``load_real_board_placement``,
   ``parse_kicad_pcb(``, ``parse_netlist(``, ``_real_board_fixture``, or a
   literal path fragment (``elec/build/default.net``,
   ``elec/domain_manifest.yaml``, ``pcb/temper.kicad_pcb``). Only
   real-board-bound findings can be run through the strong check below
   (requirement 3: verify an *actual* mismatch, not just presence). A
   Tier-2 finding that is NOT real-board-bound (synthetic geometry data
   whose ref just happens to echo a real designator, e.g.
   ``TestIntraFootprint``'s ``_comp("U1", ...)`` fixtures) is reported
   separately, unverifiable by construction -- there is no compiled
   component for this gate to compare it against.
6. **Verification** (real-board-bound Tier-2 findings only): resolve the
   literal ref against the freshly-rebuilt ``elec/build/default.net`` to
   get its CURRENT ``instance_path`` (or "ref no longer exists" -- itself
   a mismatch). Separately, scan the finding's combined context text for
   an explicit isolator/barrier-crossing claim (``CLAIM_KEYWORDS``:
   "isolator", "isolation device", "straddl", "barrier", "protective
   impedance", "genuinely straddle", ...). If the context makes that claim
   AND the current ``instance_path`` is NOT declared under
   ``elec/domain_manifest.yaml``'s ``isolators:`` or
   ``protective_impedance_chains:`` -- i.e. the manifest itself, the
   project's own stated source of truth for "what crosses the barrier",
   does not recognize this ref's current occupant as a legitimate
   crossing -- the finding is a VERIFIED MISMATCH. If the manifest DOES
   recognize it, VERIFIED MATCH (currently correct, but still keyed to an
   unstable identifier -- one more schematic edit away from drifting).
   Otherwise (no explicit claim text to check): UNVERIFIED -- found,
   real-board-bound, load-bearing, but this gate has no specific claim to
   compare against the manifest, so it does not guess one.

Freshness (read before trusting a "0 violations" run)
-------------------------------------------------------
``elec/build/`` is gitignored. This gate calls
``check_domain_partition.check_netlist_freshness`` and fails closed
(GATE ERROR) on a missing or stale netlist -- the exact failure mode noted
in this task's own brief: "a stale copy produced a false defect earlier
today." Run ``make netlist`` first.

Distinguishing safety-relevant from incidental (requirement 2)
------------------------------------------------------------------
Two independent filters must BOTH pass before a literal is reported as a
genuine (Tier >=1) finding: (a) safety-keyword context, and (b) residing in
a function that is itself, or transitively (same-file) calls, or is called
by, something containing an ``assert``. Neither filter alone is enough:
keyword-only would flag e.g. a docstring mentioning "IEC 60335" next to an
unrelated fixture; assert-only would flag ordinary non-safety unit tests
(most of this repo's ~579 scanned test files). Measured on this tree (see
the evidence doc's printed denominator), this two-filter scope is narrow:
of every ref-designator-shaped string literal found repo-wide, only a
single-digit percentage clear both filters -- most incidental refs (e.g.
``test_isolation.py``'s synthetic ``"U1"``/``"U4"`` fixtures, which use no
safety-keyword-bearing docstring at all) are correctly excluded.

Anti-vacuity (requirement 4)
-------------------------------
The report always prints, before any finding: total files scanned, total
parseable, total ref-designator-shaped literal occurrences found (the raw
denominator), how many cleared the safety-keyword filter, how many of
those are assert-reachable (Tier 1), how many of those are load-bearing
(Tier 2), how many of THOSE are real-board-bound, and how many of the
real-board-bound set carry an explicit, checkable claim (Tier 3). A run
that finds "0 violations" against a denominator of 0 at any stage is a
GATE ERROR, never printed as a clean pass -- see ``run()``.

Exit codes:
  0 - CLEAN: ran a real check; zero VERIFIED MISMATCH findings.
  3 - VIOLATION: at least one VERIFIED MISMATCH finding (a ref-designator
      identity assertion that no longer matches the design's own manifest).
  5 - GATE ERROR: netlist/manifest missing or stale, zero scan files, zero
      files parseable, or zero ref-designator-shaped literals found
      anywhere in scope (a suspicious, likely-broken-scan result -- never
      silently reported as "0 violations").

Usage:
  uv run --no-sync python scripts/check_refdes_identity_stability.py
  uv run --no-sync python scripts/check_refdes_identity_stability.py --repo-root PATH
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()
DEFAULT_NETLIST = REPO_ROOT / "elec" / "build" / "default.net"
DEFAULT_MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"
DEFAULT_SRC_DIR = REPO_ROOT / "elec" / "src"

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

# Printed in full in every report -- not a secret allowlist. See module
# docstring point 3: a substring, case-insensitive hit against the
# candidate's combined context text.
SAFETY_KEYWORDS = (
    "hv", "selv", "mains", "isolat", "creepage", "clearance", "barrier",
    "reinforced", "basic insulation", "iec 60335", "iec60335", "iec 60664",
    "req-safe", "req-emc", "galvanic", "dielectric", "star ground",
    "protective impedance", "domain_manifest", "pollution degree", "60335",
    "y1", "withstand", "dc_bus", "pwr_rtn", "domain crossing",
    "domain-crossing", "straddl", "opto",
)

# Requirement 3's "explicit claim" vocabulary: text that specifically
# asserts a ref crosses/implements the mains<->SELV barrier, as opposed to
# merely being in a safety-adjacent test file.
CLAIM_KEYWORDS = (
    "isolator", "isolation device", "isolating device", "straddl",
    "barrier", "protective impedance", "genuinely straddle",
    "cross the barrier", "crosses the barrier", "domain-crossing",
    "domain crossing", "isolation barrier",
)

# Source-text substrings that mark a function as touching REAL compiled
# design data, not synthetic fixture geometry. See module docstring point 5.
#
# Deliberately NOT a bare "kicad_pcb": this repo's prevailing style builds
# board paths with pathlib's ``/`` operator (``root / "pcb" / "temper.
# kicad_pcb"``), so ``.kicad_pcb`` alone appears constantly in synthetic
# fixture boilerplate too (e.g. ``tmp_path / "board.kicad_pcb"`` in
# scripts/tests/test_check_isolation_keepout.py's fully-synthetic
# ``write_board`` helper) -- that false-triggered every synthetic-board
# test in that file until this was narrowed to the specific call/path
# forms real-board loaders actually use.
REAL_BOARD_MARKERS = (
    "load_real_board_placement", "_real_board_fixture",
    "elec/build/default.net", "elec/domain_manifest.yaml",
    "pcb/temper.kicad_pcb",
)

# ``parse_netlist(``/``parse_kicad_pcb(`` are NOT included above: both names
# are also defined locally by OTHER, non-real-board gate modules
# (``check_footprint_drift.parse_netlist`` parses a synthetic ``tmp_path``
# netlist in its own tests, same short name as
# ``check_domain_partition.parse_netlist``). A bare call-text substring
# match cannot distinguish them -- measured directly: it produced a false
# real-board-bound classification (and a false UNVERIFIED finding) for
# ``scripts/tests/test_check_footprint_drift.py::
# test_footprint_mismatch_detected``, which imports its OWN
# ``parse_netlist`` from ``check_footprint_drift``, not
# ``check_domain_partition``. These two call markers only count when the
# file's own imports resolve the name to the real-data-loading module --
# see ``_real_parser_imports()``.
_AMBIGUOUS_CALL_MARKERS = {
    "parse_netlist(": "check_domain_partition",
    "parse_kicad_pcb(": "kicad_parser",
}


def _real_parser_imports(tree: ast.Module) -> frozenset[str]:
    """Which of ``_AMBIGUOUS_CALL_MARKERS``' call texts are backed, in
    THIS file, by an import from the real-data-loading module it names
    (matched by module-path substring, tolerant of the exact package
    prefix) -- not merely present as a same-named local helper."""
    resolved: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for call_text, module_substr in _AMBIGUOUS_CALL_MARKERS.items():
                if module_substr in node.module:
                    resolved.add(call_text)
    return frozenset(resolved)

_REF_TOKEN_RE = re.compile(r"^([A-Za-z_]+?)(\d+)$")

# This repo's evidence-doc filenames are ``YYYY-MM-DD-topic-slug.md`` and the
# slug routinely embeds a safety word for the topic it documents (e.g.
# ``2026-07-28-tank-cap-and-isolator-footprints.md``). A bare substring
# match against such a citation is not a claim about the ref sitting next
# to it in prose -- it is the *filename* of unrelated prior work. Strip doc
# citations before keyword matching (both SAFETY_KEYWORDS and
# CLAIM_KEYWORDS) so "isolator" inside a linked filename slug can't be
# mistaken for a real claim about the ref two lines away. Caught directly:
# scripts/tests/test_check_footprint_drift.py's module docstring cites
# ".../tank-cap-and-isolator-footprints.md" -- word-wrapped across the
# docstring's own line break ("docs/evidence/\n2026-07-28-tank-cap-and-
# isolator-footprints.md") -- one line above an unrelated mention of
# "C27", which produced a false MISMATCH until this allowed the citation
# pattern to span exactly the one line-wrap prose docstrings actually use.
_DOC_CITATION_RE = re.compile(r"docs/[\w./-]*(?:\n[ \t]*[\w./-]*)?\.md")


def _strip_doc_citations(text: str) -> str:
    """Blank out doc-path citations, preserving newline count so
    line-based proximity search (``_ref_has_nearby_claim``) stays aligned
    with the original text's line numbers."""
    return _DOC_CITATION_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Netlist / manifest (reused from check_domain_partition.py -- same
# cross-layer import shim precedent as
# packages/temper-placer/tests/requirements/safety/_real_board_fixture.py
# uses for the identical parsers).
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_domain_partition import GateError as _DomainGateError  # noqa: E402
from check_domain_partition import (  # noqa: E402
    Manifest,
    Netlist,
    check_netlist_freshness,
    load_manifest,
    parse_netlist,
)


def discover_ref_prefixes(netlist: Netlist) -> frozenset[str]:
    """Ref-designator prefixes actually used by THIS compiled design.

    Derived from the netlist's own component refs (never a hardcoded KiCad
    convention list) -- see module docstring point 1.
    """
    prefixes: set[str] = set()
    for ref in netlist.components:
        m = _REF_TOKEN_RE.match(ref)
        if m:
            prefixes.add(m.group(1))
    if not prefixes:
        raise GateError(
            f"discovered zero ref-designator prefixes from {len(netlist.components)} "
            "netlist component(s) -- every ref failed to match <letters><digits>; "
            "cannot build a ref-designator pattern from this netlist"
        )
    return frozenset(prefixes)


def build_ref_pattern(prefixes: frozenset[str]) -> re.Pattern[str]:
    alt = "|".join(sorted((re.escape(p) for p in prefixes), key=len, reverse=True))
    return re.compile(rf"^(?:{alt})\d+$")


def manifest_declared_paths(manifest: Manifest) -> frozenset[str]:
    """Every instance_path this manifest declares as crossing the barrier
    (an isolator, or a member of a protective-impedance chain)."""
    paths: set[str] = {iso.instance_path for iso in manifest.isolators}
    for chain in manifest.chains:
        paths.update(chain.chain)
    return frozenset(paths)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def find_scan_files(repo_root: Path) -> list[Path]:
    """Every ``.py`` file under any directory literally named ``tests``,
    anywhere in the repo. See module docstring point 2."""
    seen: set[Path] = set()
    for tests_dir in repo_root.rglob("tests"):
        if not tests_dir.is_dir():
            continue
        parts = tests_dir.relative_to(repo_root).parts
        if any(p in ("__pycache__", ".venv", "node_modules", "target", ".git") for p in parts):
            continue
        for py in tests_dir.rglob("*.py"):
            rel_parts = py.relative_to(repo_root).parts
            if any(p in ("__pycache__", ".venv", "node_modules", "target") for p in rel_parts):
                continue
            seen.add(py)
    return sorted(seen)


# ---------------------------------------------------------------------------
# AST analysis
# ---------------------------------------------------------------------------


@dataclass
class FuncInfo:
    node: ast.AST  # FunctionDef | AsyncFunctionDef
    qualname: str
    class_doc: str
    own_source: str
    has_assert: bool
    calls: set[str] = field(default_factory=set)  # local callee names, best-effort
    touches_real_board_direct: bool = False


def _decorator_sources(fn: ast.AST, text: str) -> str:
    out = []
    for deco in getattr(fn, "decorator_list", []):
        seg = ast.get_source_segment(text, deco)
        if seg:
            out.append(seg)
    return "\n".join(out)


def _local_callee_names(fn: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    return names


def _collect_functions(tree: ast.Module, text: str) -> dict[str, FuncInfo]:
    """qualname -> FuncInfo for every (possibly nested) function/method in
    the module. qualname collisions (two methods of the same short name in
    different classes) are tolerated -- see docstring's own honesty about
    call-graph resolution being best-effort, name-based, not scope-exact."""
    out: dict[str, FuncInfo] = {}
    resolved_ambiguous = _real_parser_imports(tree)
    active_markers = REAL_BOARD_MARKERS + tuple(resolved_ambiguous)

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.class_stack: list[ast.ClassDef] = []
            self.qual_stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.class_stack.append(node)
            self.qual_stack.append(node.name)
            self.generic_visit(node)
            self.qual_stack.pop()
            self.class_stack.pop()

        def _visit_func(self, node: ast.AST) -> None:
            name = node.name  # type: ignore[attr-defined]
            self.qual_stack.append(name)
            qualname = ".".join(self.qual_stack)
            class_doc = ""
            if self.class_stack:
                class_doc = ast.get_docstring(self.class_stack[-1]) or ""
            own_source = ast.get_source_segment(text, node) or ""
            deco_src = _decorator_sources(node, text)
            has_assert = any(isinstance(n, ast.Assert) for n in ast.walk(node))
            touches = any(marker in (own_source + deco_src) for marker in active_markers)
            out[qualname] = FuncInfo(
                node=node,
                qualname=qualname,
                class_doc=class_doc,
                own_source=own_source + "\n" + deco_src,
                has_assert=has_assert,
                calls=_local_callee_names(node),
                touches_real_board_direct=touches,
            )
            self.generic_visit(node)
            self.qual_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_func(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_func(node)

    Visitor().visit(tree)
    return out


def _short_names(funcs: dict[str, FuncInfo]) -> dict[str, list[str]]:
    """short (unqualified) function name -> [qualname, ...] for best-effort
    call-graph edges (a Call to ``self._foo()`` or ``foo()`` only carries
    the short name at the AST level)."""
    out: dict[str, list[str]] = {}
    for qualname in funcs:
        short = qualname.rsplit(".", 1)[-1]
        out.setdefault(short, []).append(qualname)
    return out


def _transitive(
    start: str,
    edges: dict[str, set[str]],
    max_depth: int = 12,
) -> set[str]:
    seen: set[str] = set()
    frontier = {start}
    for _ in range(max_depth):
        nxt: set[str] = set()
        for n in frontier:
            for m in edges.get(n, ()):
                if m not in seen and m != start:
                    nxt.add(m)
        if not nxt:
            break
        seen |= nxt
        frontier = nxt
    return seen


def _build_graphs(
    funcs: dict[str, FuncInfo],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Returns (calls, called_by) as qualname -> {qualname, ...} edges,
    resolved best-effort by short name (see FuncInfo docstring)."""
    short_to_quals = _short_names(funcs)
    calls: dict[str, set[str]] = {q: set() for q in funcs}
    called_by: dict[str, set[str]] = {q: set() for q in funcs}
    for qualname, info in funcs.items():
        for short in info.calls:
            for target in short_to_quals.get(short, ()):
                if target == qualname:
                    continue
                calls[qualname].add(target)
                called_by[target].add(qualname)
    return calls, called_by


@dataclass
class Occurrence:
    file: Path
    lineno: int
    ref: str
    func_qualname: str
    safety_relevant: bool = False
    assert_reachable: bool = False
    load_bearing: bool = False
    real_board_bound: bool = False
    has_claim: bool = False
    combined_context_snippet: str = ""


def _find_assign_ancestor_target(
    node: ast.AST, ancestors: list[ast.AST]
) -> str | None:
    for anc in ancestors:
        if isinstance(anc, ast.Assign) and len(anc.targets) == 1 and isinstance(
            anc.targets[0], ast.Name
        ):
            return anc.targets[0].id
    return None


def _name_used_in_compare_or_subscript(fn: ast.AST, name: str) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            if any(isinstance(o, ast.Name) and o.id == name for o in operands):
                return True
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id == name:
                return True
    return False


def _one_hop_targets(fn: ast.AST, name: str) -> set[str]:
    """Names reachable from *name* via one comprehension-iter or simple
    alias-assignment hop, within *fn*. Used to extend load-bearing
    detection through ``for r in refs`` / ``x = refs`` patterns."""
    out: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.comprehension):
            if isinstance(node.iter, ast.Name) and node.iter.id == name:
                if isinstance(node.target, ast.Name):
                    out.add(node.target.id)
        if isinstance(node, ast.Assign):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == name
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                out.add(node.targets[0].id)
    return out


def _is_load_bearing_dataflow(fn: ast.AST, seed_name: str, max_hops: int = 4) -> bool:
    tracked = {seed_name}
    for _ in range(max_hops):
        if any(_name_used_in_compare_or_subscript(fn, n) for n in tracked):
            return True
        new_names: set[str] = set()
        for n in tracked:
            new_names |= _one_hop_targets(fn, n)
        new_names -= tracked
        if not new_names:
            return False
        tracked |= new_names
    return any(_name_used_in_compare_or_subscript(fn, n) for n in tracked)


def _ref_has_nearby_claim(context: str, ref: str, window: int = 2) -> bool:
    """True if *ref* (as a whole word) and a ``CLAIM_KEYWORDS`` hit appear
    within *window* lines of each other in *context*.

    Claim detection must be scoped to the SPECIFIC ref, not "anywhere in
    the function" -- a function-wide check conflated
    ``test_generator_covers_the_tp3_u7_pair_specifically``'s claim ("U7
    genuinely straddles domains") with the OTHER ref in the same pair
    (``TP3``, a test point never claimed to be an isolator), producing a
    false MISMATCH for TP3. Line-proximity to the ref's own textual
    mention is what the claim keyword must actually be near.
    """
    lines = context.splitlines()
    ref_re = re.compile(rf"\b{re.escape(ref)}\b")
    for i, line in enumerate(lines):
        if ref_re.search(line):
            lo, hi = max(0, i - window), min(len(lines), i + window + 1)
            block = "\n".join(lines[lo:hi]).lower()
            if any(kw in block for kw in CLAIM_KEYWORDS):
                return True
    return False


def _parametrize_param_names(deco: ast.expr) -> list[str] | None:
    """For a ``@pytest.mark.parametrize("a,b,c", [...])`` decorator node,
    return ``["a", "b", "c"]``; None if not recognized as parametrize."""
    if not isinstance(deco, ast.Call):
        return None
    func = deco.func
    is_parametrize = (isinstance(func, ast.Attribute) and func.attr == "parametrize") or (
        isinstance(func, ast.Name) and func.id == "parametrize"
    )
    if not is_parametrize or not deco.args:
        return None
    first = deco.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return [p.strip() for p in first.value.split(",") if p.strip()]
    return None


def _analyze_literal(
    file: Path,
    text: str,
    const_node: ast.Constant,
    ancestors: list[ast.AST],
    fn: ast.AST,
) -> bool:
    """Direct-embedding load-bearing check: is *const_node* itself, or the
    variable it's assigned to (one dataflow hop), read by a Compare or
    Subscript inside *fn*?"""
    if any(isinstance(a, ast.Compare) for a in ancestors):
        return True
    target = _find_assign_ancestor_target(const_node, ancestors)
    if target is not None:
        return _is_load_bearing_dataflow(fn, target)
    return False


def scan_file(
    file: Path,
    repo_root: Path,
    ref_pattern: re.Pattern[str],
) -> tuple[list[Occurrence], int, bool]:
    """Returns (occurrences_with_metadata, raw_literal_count, parsed_ok)."""
    try:
        text = file.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return [], 0, False
    try:
        tree = ast.parse(text, filename=str(file))
    except SyntaxError:
        return [], 0, False

    module_doc = ast.get_docstring(tree) or ""
    funcs = _collect_functions(tree, text)
    calls_graph, called_by_graph = _build_graphs(funcs)

    # Assert-reachability: fn has one directly, or something that
    # (transitively, same file) calls it does.
    assert_reachable: dict[str, bool] = {}
    for q, info in funcs.items():
        if info.has_assert:
            assert_reachable[q] = True
            continue
        callers = _transitive(q, called_by_graph)
        assert_reachable[q] = any(funcs[c].has_assert for c in callers if c in funcs)

    # Real-board-bound: fn touches a real-board marker directly, or
    # (transitively, same file) calls something that does.
    real_board_bound: dict[str, bool] = {}
    for q, info in funcs.items():
        if info.touches_real_board_direct:
            real_board_bound[q] = True
            continue
        callees = _transitive(q, calls_graph)
        real_board_bound[q] = any(
            funcs[c].touches_real_board_direct for c in callees if c in funcs
        )

    # Combined context text: own source + class doc + module doc (capped)
    # + source of every transitive same-file caller (safety-relevance can
    # be established by the caller's docstring, e.g. a helper with no
    # prose of its own that is only ever invoked from a heavily-documented
    # safety test).
    combined_context: dict[str, str] = {}
    for q, info in funcs.items():
        callers = _transitive(q, called_by_graph)
        caller_src = "\n".join(funcs[c].own_source for c in callers if c in funcs)
        combined_context[q] = "\n".join(
            [info.own_source, info.class_doc, module_doc[:2000], caller_src]
        )

    # Parent map per function (rebuilt lazily per function subtree).
    occurrences: list[Occurrence] = []
    raw_count = 0

    for q, info in funcs.items():
        fn = info.node
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(fn):
            for child in ast.iter_child_nodes(node):
                parents[child] = node

        def ancestors_of(
            n: ast.AST, _parents: dict[ast.AST, ast.AST] = parents, _fn: ast.AST = fn
        ) -> list[ast.AST]:
            # _parents/_fn bound as default-arg values (not closed over) so
            # this genuinely uses THIS iteration's dict/node, not whatever
            # `parents`/`fn` happen to hold by the time the closure runs --
            # it always runs synchronously within the same iteration here,
            # but binding explicitly removes any doubt (and the B023 lint).
            out: list[ast.AST] = []
            cur = n
            while cur in _parents:
                cur = _parents[cur]
                out.append(cur)
                if cur is _fn:
                    break
            return out

        ctx_text = _strip_doc_citations(combined_context.get(q, ""))
        ctx_lower = ctx_text.lower()
        is_safety = any(kw in ctx_lower for kw in SAFETY_KEYWORDS)
        is_reachable = assert_reachable.get(q, False)
        is_real_board = real_board_bound.get(q, False)

        # ast.walk(fn) also descends into fn.decorator_list (it's a plain
        # child field of the FunctionDef node) -- exclude those constants
        # from this loop, since parametrize-decorator literals are handled
        # separately below (with param-name-aware load-bearing detection).
        # Without this, a parametrize literal was counted TWICE: once here
        # (with no load-bearing signal, since a bare decorator constant is
        # never a Compare/Assign operand) and once in the dedicated loop.
        decorator_ids = {id(n) for deco in fn.decorator_list for n in ast.walk(deco)}

        # Direct literal constants within this function's own body.
        for node in ast.walk(fn):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node is fn or id(node) in decorator_ids:
                    continue
                if not ref_pattern.fullmatch(node.value):
                    continue
                raw_count += 1
                load_bearing = _analyze_literal(file, text, node, ancestors_of(node), fn)
                occurrences.append(
                    Occurrence(
                        file=file,
                        lineno=getattr(node, "lineno", -1),
                        ref=node.value,
                        func_qualname=f"{file.relative_to(repo_root)}::{q}",
                        safety_relevant=is_safety,
                        assert_reachable=is_reachable,
                        load_bearing=load_bearing,
                        real_board_bound=is_real_board,
                        has_claim=_ref_has_nearby_claim(ctx_text, node.value),
                    )
                )

        # Parametrize-decorator literals: separately counted (they are not
        # inside fn's own body) and checked via the bound param name.
        for deco in getattr(fn, "decorator_list", []):
            param_names = _parametrize_param_names(deco)
            if not param_names:
                continue
            deco_call = deco
            assert isinstance(deco_call, ast.Call)
            if len(deco_call.args) < 2:
                continue
            values_arg = deco_call.args[1]
            rows: list[ast.expr]
            if isinstance(values_arg, (ast.List, ast.Tuple)):
                rows = list(values_arg.elts)
            else:
                rows = []
            for row in rows:
                elts: list[ast.expr]
                if isinstance(row, ast.Tuple):
                    elts = list(row.elts)
                elif isinstance(row, ast.Constant):
                    elts = [row]
                else:
                    continue
                for i, elt in enumerate(elts):
                    if not (isinstance(elt, ast.Constant) and isinstance(elt.value, str)):
                        continue
                    if not ref_pattern.fullmatch(elt.value):
                        continue
                    raw_count += 1
                    load_bearing = False
                    if i < len(param_names):
                        load_bearing = _is_load_bearing_dataflow(fn, param_names[i])
                    occurrences.append(
                        Occurrence(
                            file=file,
                            lineno=getattr(elt, "lineno", getattr(deco, "lineno", -1)),
                            ref=elt.value,
                            func_qualname=f"{file.relative_to(repo_root)}::{q}",
                            safety_relevant=is_safety,
                            assert_reachable=is_reachable,
                            load_bearing=load_bearing,
                            real_board_bound=is_real_board,
                            has_claim=_ref_has_nearby_claim(ctx_text, elt.value),
                        )
                    )

    return occurrences, raw_count, True


# ---------------------------------------------------------------------------
# Verification against the compiled netlist + manifest
# ---------------------------------------------------------------------------


@dataclass
class Verdict:
    occurrence: Occurrence
    current_instance_path: str | None  # None = ref not found in netlist at all
    declared_as_crossing: bool | None  # None = no claim to check
    verdict: str  # "MISMATCH" | "MATCH" | "UNVERIFIED" | "SHAPE_ONLY"


def verify(
    occurrences: list[Occurrence],
    netlist: Netlist,
    declared_paths: frozenset[str],
) -> list[Verdict]:
    out: list[Verdict] = []
    for occ in occurrences:
        if not (occ.safety_relevant and occ.assert_reachable and occ.load_bearing):
            continue
        if not occ.real_board_bound:
            out.append(Verdict(occ, None, None, "SHAPE_ONLY"))
            continue
        comp = netlist.components.get(occ.ref)
        current_path = comp.instance_path if comp else None
        if not occ.has_claim:
            out.append(Verdict(occ, current_path, None, "UNVERIFIED"))
            continue
        if current_path is None:
            out.append(Verdict(occ, None, False, "MISMATCH"))
            continue
        declared = current_path in declared_paths
        out.append(Verdict(occ, current_path, declared, "MATCH" if declared else "MISMATCH"))
    return out


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


@dataclass
class Report:
    files_found: int = 0
    files_parsed: int = 0
    raw_literal_count: int = 0
    safety_relevant_count: int = 0
    assert_reachable_count: int = 0
    load_bearing_count: int = 0
    real_board_bound_count: int = 0
    verdicts: list[Verdict] = field(default_factory=list)


def run(repo_root: Path, netlist_path: Path, manifest_path: Path, src_dir: Path) -> Report:
    # check_netlist_freshness/parse_netlist/load_manifest are reused from
    # check_domain_partition.py (same cross-layer import shim precedent as
    # _real_board_fixture.py) and raise THAT module's own GateError class,
    # not this module's -- translate so a single `except GateError` in
    # main() (and in any caller of run()) reliably catches every fail-closed
    # condition this gate can hit, not just the ones raised locally.
    try:
        check_netlist_freshness(netlist_path, src_dir)
        netlist = parse_netlist(netlist_path)
        manifest = load_manifest(manifest_path)
    except _DomainGateError as exc:
        raise GateError(str(exc)) from exc
    prefixes = discover_ref_prefixes(netlist)
    ref_pattern = build_ref_pattern(prefixes)
    declared_paths = manifest_declared_paths(manifest)

    files = find_scan_files(repo_root)
    if not files:
        raise GateError(f"found zero .py files under any 'tests' directory below {repo_root}")

    report = Report(files_found=len(files))
    all_occurrences: list[Occurrence] = []
    for f in files:
        occs, _raw, ok = scan_file(f, repo_root, ref_pattern)
        if ok:
            report.files_parsed += 1
        report.raw_literal_count += _raw
        all_occurrences.extend(occs)

    if report.raw_literal_count == 0:
        raise GateError(
            f"found zero ref-designator-shaped string literals across "
            f"{report.files_parsed} parsed file(s) (prefixes: {sorted(prefixes)}) -- "
            "this scan almost certainly broke, not that this repo's test suite "
            "contains no ref-designator literals at all"
        )

    tier1 = [o for o in all_occurrences if o.safety_relevant and o.assert_reachable]
    report.safety_relevant_count = len([o for o in all_occurrences if o.safety_relevant])
    report.assert_reachable_count = len(tier1)
    tier2 = [o for o in tier1 if o.load_bearing]
    report.load_bearing_count = len(tier2)
    report.real_board_bound_count = len([o for o in tier2 if o.real_board_bound])

    report.verdicts = verify(tier1, netlist, declared_paths)
    return report


def _print_report(report: Report) -> str:
    lines: list[str] = []

    def p(s: str = "") -> None:
        lines.append(s)
        print(s)

    p("=== Ref-Designator Identity-Stability Gate ===")
    p(
        f"Files under a 'tests' directory: {report.files_found} found, "
        f"{report.files_parsed} parsed."
    )
    p(f"Raw ref-designator-shaped string literals examined: {report.raw_literal_count}")
    p(f"  ...in safety-keyword context:           {report.safety_relevant_count}")
    p(f"  ...AND assert-reachable (Tier 1):       {report.assert_reachable_count}")
    p(f"  ...AND load-bearing (Tier 2):           {report.load_bearing_count}")
    p(f"  ...AND real-board-bound (verifiable):   {report.real_board_bound_count}")
    p()

    by_verdict: dict[str, list[Verdict]] = {}
    for v in report.verdicts:
        by_verdict.setdefault(v.verdict, []).append(v)

    for label in ("MISMATCH", "MATCH", "UNVERIFIED", "SHAPE_ONLY"):
        vs = by_verdict.get(label, [])
        if not vs:
            continue
        p(f"--- {label}: {len(vs)} ---")
        for v in vs:
            occ = v.occurrence
            path_str = v.current_instance_path if v.current_instance_path else "<ref not in netlist>"
            p(
                f"  {occ.func_qualname}:{occ.lineno}  ref={occ.ref!r}  "
                f"current_instance_path={path_str!r}  "
                f"declared_as_crossing={v.declared_as_crossing}"
            )
        p()

    mismatches = by_verdict.get("MISMATCH", [])
    if mismatches:
        p(f"FAILED -- {len(mismatches)} VERIFIED MISMATCH finding(s).")
    else:
        p(
            "PASSED -- zero VERIFIED MISMATCH findings "
            f"(over a denominator of {report.raw_literal_count} raw ref-designator "
            f"literal(s), {report.real_board_bound_count} real-board-bound-and-"
            "load-bearing)."
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--netlist", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--src-dir", type=Path, default=None)
    args = parser.parse_args()

    repo_root = args.repo_root
    netlist_path = args.netlist or (repo_root / "elec" / "build" / "default.net")
    manifest_path = args.manifest or (repo_root / "elec" / "domain_manifest.yaml")
    src_dir = args.src_dir or (repo_root / "elec" / "src")

    try:
        report = run(repo_root, netlist_path, manifest_path, src_dir)
    except GateError as exc:
        print("=== REF-DESIGNATOR IDENTITY-STABILITY GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )
        gh = get_github_summary_path()
        if gh:
            with open(gh, "a") as f:
                f.write(f"### Ref-Designator Identity-Stability Gate -- GATE ERROR\n{exc}\n")
        sys.exit(EXIT_GATE_ERROR)

    text = _print_report(report)
    gh = get_github_summary_path()
    if gh:
        with open(gh, "a") as f:
            f.write("### Ref-Designator Identity-Stability Gate\n```\n" + text + "\n```\n")

    if any(v.verdict == "MISMATCH" for v in report.verdicts):
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
