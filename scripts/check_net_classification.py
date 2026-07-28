#!/usr/bin/env python3
"""Safety-relevant net-classification-by-substring CI gate.

Motivating defect class -- confirmed three times in this repo, twice on
2026-07-27, in opposite directions:

1. ``creepage_check.py`` (fixed in merge ``5076e715``) -- FALSE POSITIVES.
   ``broad_keywords`` contained ``"L1"``, ``"L2"``, ``"LINE"`` matched via
   ``kw in name_upper``, under a comment asserting "substring match is safe
   for these". ``"L1"`` matched ``COIL1``, ``"L2"`` matched ``COIL2``,
   ``"LINE"`` matched ``safety.ovp-line`` -- all confirmed SELV in
   ``elec/domain_manifest.yaml``. All 24 reported creepage violations on
   the live board were false positives on SELV nets; the real mains nets
   ``ac_l``/``ac_n`` matched no broad keyword at all.
2. ``clearance_check.py`` (fixed in merge ``466c7724``) -- FALSE
   NEGATIVES, the mirror image. HV was classified by four substrings
   (``AC_``, ``HV_``, ``HIGH_VOLTAGE``, ``MAINS``) that, on this board,
   matched only ``ac_l``/``ac_n``. Eleven real HV-domain nets declared in
   the manifest silently fell through to a 0.127mm default instead of the
   IEC 60335 requirement -- one confirmed pair moved from 0.127mm to
   14.0mm once fixed.
3. ``clearance_engine.py`` -- a third, previously-unfixed instance found
   auditing this same class (``_net_class_to_voltage_class`` matched bare
   ``"HV"``/``"AC"`` as substrings), plus a fourth and fifth found the same
   way (``clearance_check._classify_net_class``, pre-existing since commit
   ``1e99a151``, reintroduced the exact ``"L1"``/``"L2"``/``"LINE"`` bug
   already fixed once in ``creepage_check.py``; ``core/design_rules.py``'s
   ``_is_high_current_net`` matched bare ``"COIL"``, misclassifying the
   same four SELV relay-coil nets; ``router_v6/net_classification.py`` --
   this repo's own documented "single source of truth" -- matched bare
   ``"PE"``). All fixed in this same change; see
   ``docs/evidence/2026-07-27-net-classification-gate.md`` for the full
   before/after proof of each.

Every instance shares one root shape: a net's HV/SELV-adjacent electrical
domain is decided by testing whether a short keyword is a **substring** of
the (uppercased) net name (``kw in name_upper``), maintained by hand,
living beside -- never reading from -- ``elec/domain_manifest.yaml``, this
project's canonical, human-reviewed HV/SELV declaration. A substring test
has no concept of a word boundary: it fails silently in BOTH directions
depending only on what other net names happen to exist on the board,
which changes across boards and across revisions of the same board.

Design decision: AST-level detection, not regex over source text
-------------------------------------------------------------------
A regex scanning source text for something like ``r'\\bany\\(\\w+ in \\w+
for \\w+ in'`` would be fragile against reformatting (black/ruff line
wraps), miss the equivalent explicit ``for``-loop form
(``for kw in KEYWORDS: if kw in upper: ...`` -- creepage_check.py's
pre-fix shape used the comprehension form, but nothing prevents a future
instance from using the loop form), and cannot resolve the keyword
collection when it is a module-level constant referenced by name several
lines away from the comparison. The AST gives an exact, formatting-
independent structural match: a ``Compare`` node whose operator is ``in``,
where one operand is bound by an enclosing ``for``/comprehension clause
iterating over a literal collection of string constants (or is itself a
literal string constant), tried against the collection's *contents*
(resolved through simple same-file constant tracking) rather than
guessing from surrounding text. This is the same reasoning
``check_undeclared_imports.py`` and ``check_stale_extensions.py`` give for
preferring ``ast``/``importlib`` introspection over text pattern matching
elsewhere in this gate family.

Detection rule
--------------
A call site is a candidate if it is a ``Compare`` node with exactly one
``In`` operator where:

  - one operand is a plain string literal that matches an entry in
    ``SAFETY_VOCAB`` (a direct, un-looped substring test), OR
  - one operand is a ``Name`` bound by an enclosing ``for``/comprehension
    clause (``for kw in KEYWORDS``), and ``KEYWORDS`` resolves (as an
    inline literal, or via same-file constant tracking for a
    ``list``/``tuple``/``set``/``frozenset`` literal bound to a ``Name``)
    to a collection containing at least one string matching
    ``SAFETY_VOCAB``.

``SAFETY_VOCAB`` was originally scoped to the HV/SELV mains-adjacent
vocabulary this defect class first surfaced with (``HV``, ``AC``,
``MAINS``, ``LINE``, ``COIL``, ``GATE``, ``PHASE``, ...) -- not every
net-class keyword in the codebase, and ``GND``/``VCC``/``PWR``-style
low-voltage-domain checks were explicitly called out of scope: the
defect class was understood as "the HV/SELV boundary specifically", per
``elec/domain_manifest.yaml``'s two declared domains.

FOURTH INSTANCE, 2026-07-28, that scoping was too narrow: identical
unanchored ``Compare(in)`` shape, same root cause (a hand-maintained
keyword list drifting from an SSOT), but for a *different* classification
question -- not "is this net HV or SELV" but "does this net's copper make
its physical layer non-routable" (``_extract_stackup()``'s plane-detection
heuristic, ``packages/temper-placer/src/temper_placer/io/_parse_board.py``,
fixed the same day this gate was extended). A single bare
``"+" in zone.netName`` matched ``+3V3`` (a Power-class net with no
plane-worthy current budget) and flipped an entire outer copper layer to
non-routable -- see
``docs/evidence/2026-07-28-zone-layer-classification-fix.md``. This
confirmed the pattern generalizes beyond the HV/SELV boundary to *any*
safety- or routing-behavior-relevant net classification, so ``GND``,
``VCC``, ``PWR``, and the single-character ``+`` (a real, if unusual,
keyword literal in the pre-fix code -- short keywords are exactly the
highest-risk case this gate exists to catch) were added to the matched
vocabulary rather than kept out of scope. ``VDD``/``POWER`` remain
unlisted only because no confirmed instance has used them yet as a bare
``Compare(in)`` literal or loop-bound keyword -- add them the next time
one does, per the "ask where else this shape occurs" discipline in
``docs/solutions/best-practices/substring-net-classification-drifts-from-ssot-2026-07-27.md``.

This still keeps the gate from flagging genuinely unrelated substring
classification (via impedance-class keywords like ``USB``/``SPI``/
``CLK``, or footprint-name keywords like ``soic``/``qfp``) that happens
to share the "keyword list + substring test" shape but has nothing to do
with any net's safety/routing classification -- see
``docs/evidence/2026-07-27-net-classification-gate.md`` for the specific
files this was checked against.

Every ``Compare(in)`` call site found (matching the vocabulary or not) is
counted in the denominators this gate prints -- unresolvable keyword
collections (a ``Name`` whose binding could not be traced to a literal,
e.g. loaded at runtime) are reported as their own bucket, never silently
dropped and never silently counted as "safe".

A ``Compare(in)`` node is, by Python semantics, always an unanchored
substring test when both operands are strings -- there is no "safe"
configuration of the plain ``in`` operator for this purpose. The fix
pattern in every historical instance replaced it with
``re.search(r"(?:^|_)KEYWORD(?:$|[\\d_])", upper)`` (or exact manifest-set
membership, which has a structurally different AST shape -- see below).
So this gate does not attempt to also validate word-boundary-ness of an
already-anchored regex; it only needs to prove the offending ``in`` test
is gone.

Why the manifest-membership pattern is not a false positive here: the fix
pattern ``net_name in hv_manifest_nets`` (an exact-membership test against
a set of full net names loaded from ``elec/domain_manifest.yaml``) has NO
enclosing ``for kw in KEYWORDS`` binding at all -- the left operand is the
*whole* net name, not a loop-bound keyword fragment, and the right operand
is not a small literal collection of short substrings. This gate's
loop-binding requirement excludes it by construction, without needing to
special-case it.

Scope: which files
-------------------
Default-include, narrow documented-exclude (the pattern
``check_vacuous_gates.py`` converged on in its 2026-07-27 rewrite, after
its own predecessor's include-list missed most of the real surface):

  1. Every ``.py`` file under ``packages/temper-placer/src/temper_placer/``
     (recursive) -- production placer/router code, where all five
     confirmed instances live.
  2. Every ``.py`` file under
     ``packages/temper-placer/tests/requirements/validators/`` (recursive,
     excluding ``test_*.py``/``*_test.py``/``conftest.py``) --
     ``check_vacuous_gates.py`` documents this directory as containing
     real *implementation* modules (``isolation.py``, ``clearance_check.py``,
     ...) that happen to live under a ``tests/`` tree; the same scoping
     gap would silently exclude them here too.
  3. Every ``.py`` file under ``elec/validation/`` (recursive) -- mirrors
     ``check_undeclared_imports.py``'s scan-target list for
     project-specific electrical validation code.

Anti-vacuous-truth contract
-----------------------------
"Discovered nothing to check" is a FAILURE here, not a pass --
``docs/solutions/best-practices/`` documents this repo's history of gates
that silently checked an empty or partial set and reported success. Exits
non-zero (GATE_ERROR) for every one of:

  - zero files found across all scan targets
  - zero ``Compare(in)`` call sites discovered across every parsed file
  - a scan target directory that does not exist
  - a file that fails to parse
  - an allowlist entry with no scope or no justification

Allowlist
---------
``.net-classification-allowlist`` entries are
``qualname::file-glob  # justification`` (mirrors
``.undeclared-imports-allowlist``'s ``module::file-glob`` format), where
``qualname`` is ``function_name`` or ``ClassName.method_name`` containing
the flagged call site. Both the qualname and the file glob must match.
Every entry requires a ``#`` justification; unjustified or unscoped
entries are a hard error.

Exit codes:
  0 - PASSED: at least one call site was discovered and checked, and every
      non-allowlisted candidate site uses an anchored/manifest-driven
      classification (no bare substring test against the HV/SELV
      vocabulary).
  3 - VIOLATION: at least one non-allowlisted candidate call site is a
      bare substring test against the HV/SELV vocabulary.
  5 - GATE ERROR: zero files or zero call sites discovered, a scan target
      is missing, a file failed to parse, or the allowlist is malformed --
      never conflated with "0 violations".

Usage:
  uv run python scripts/check_net_classification.py
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

DEFAULT_ALLOWLIST_NAME = ".net-classification-allowlist"

# HV/SELV mains-adjacent vocabulary -- see module docstring "Detection
# rule" for why this is scoped to the HV/SELV boundary specifically
# rather than every net-class keyword in the codebase. Matched
# case-insensitively (call sites and their collections are uppercased
# before comparison).
SAFETY_VOCAB: frozenset[str] = frozenset(
    {
        "HV",
        "AC",
        "AC_",
        "HV_",
        "MAINS",
        "MAINS_240V",
        "MAINS_120V",
        "HIGH_VOLTAGE",
        "LINE",
        "NEUTRAL",
        "PRIMARY",
        "HOT",
        "PHASE",
        "L1",
        "L2",
        "L3",
        "VBUS",
        "B+",
        "COIL",
        "GATE",
        "DRV",
        "DRIVE",
        "DC_BUS",
        "DC_BUS+",
        "DC_BUS-",
        "SW_NODE",
        "SELV",
        "RECT",
        "PE",
        # Added 2026-07-28 -- fourth confirmed instance, a *different*
        # classification question (plane/pour eligibility, not HV/SELV
        # domain) sharing the identical bare-Compare(in) shape. See the
        # module docstring's "FOURTH INSTANCE" note above.
        "GND",
        "VCC",
        "PWR",
        "+",
    }
)


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Scan targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScanTarget:
    label: str
    root: Path
    pattern: str
    exclude_test_files: bool  # skip test_*.py / *_test.py / conftest.py


def build_scan_targets(repo_root: Path) -> list[ScanTarget]:
    placer_src = repo_root / "packages" / "temper-placer" / "src" / "temper_placer"
    validators = repo_root / "packages" / "temper-placer" / "tests" / "requirements" / "validators"
    elec_validation = repo_root / "elec" / "validation"
    return [
        ScanTarget("packages/temper-placer/src/temper_placer/**/*.py", placer_src, "**/*.py", False),
        ScanTarget(
            "packages/temper-placer/tests/requirements/validators/**/*.py",
            validators,
            "**/*.py",
            True,
        ),
        ScanTarget("elec/validation/**/*.py", elec_validation, "**/*.py", False),
    ]


def _is_test_file(path: Path) -> bool:
    name = path.name
    return name == "conftest.py" or name.startswith("test_") or name.endswith("_test.py")


# ---------------------------------------------------------------------------
# Same-file literal-collection resolution
# ---------------------------------------------------------------------------


def _string_elements(node: ast.AST) -> list[str] | None:
    """Return the string constants in a List/Tuple/Set literal, or a call
    to ``frozenset``/``set``/``list``/``tuple`` wrapping one.

    Returns ``None`` if *node* is not a resolvable literal collection, or
    if it contains any non-string-constant element (conservative: a
    partially-dynamic collection is not claimed to be fully understood).
    """
    if isinstance(node, ast.Call):
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in ("frozenset", "set", "list", "tuple")
            and len(node.args) == 1
        ):
            return _string_elements(node.args[0])
        return None
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        out: list[str] = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.append(elt.value)
            else:
                return None
        return out
    return None


class _ConstantCollector(ast.NodeVisitor):
    """Collects every ``name = <literal collection>`` /
    ``name: T = <literal collection>`` binding in a file, keyed by name.

    Deliberately flat (not scope-aware): a function-local binding can
    shadow a module-level one of the same name in real Python, but for
    this gate's purpose (resolving "what does this keyword list contain"
    for a human-reviewable report) a later assignment simply overwrites
    the earlier entry, which is safe in the direction that matters -- it
    never turns an unresolvable/dynamic collection into a falsely
    resolved one, it can only pick the wrong same-shaped literal in a
    contrived shadowing case this codebase does not exhibit.
    """

    def __init__(self) -> None:
        self.bindings: dict[str, list[str]] = {}

    def visit_Assign(self, node: ast.Assign) -> None:
        elements = _string_elements(node.value)
        if elements is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.bindings[target.id] = elements
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            elements = _string_elements(node.value)
            if elements is not None and isinstance(node.target, ast.Name):
                self.bindings[node.target.id] = elements
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Call-site detection
# ---------------------------------------------------------------------------


@dataclass
class CallSite:
    file: str
    lineno: int
    qualname: str
    keywords: list[str]  # the resolved (or partially known) keyword text
    matched_vocab: list[str]
    resolved: bool  # False if the keyword collection could not be traced


@dataclass
class ScanResult:
    call_sites_discovered: int = 0
    call_sites_resolved: int = 0
    call_sites_unresolved: int = 0
    candidates: list[CallSite] = field(default_factory=list)  # vocab-matching, resolved
    unresolved_sites: list[CallSite] = field(default_factory=list)


def _enclosing_qualname(stack: list[str]) -> str:
    return ".".join(stack) if stack else "<module>"


class _CompareVisitor(ast.NodeVisitor):
    """Walks one file's AST tracking enclosing function/class names and
    active ``for``/comprehension loop-variable bindings, and records
    every ``Compare(in)`` call site found -- resolved or not.
    """

    def __init__(self, bindings: dict[str, list[str]], file_rel: str, result: ScanResult) -> None:
        self.bindings = bindings
        self.file_rel = file_rel
        self.result = result
        self.name_stack: list[str] = []
        self.loop_stack: list[dict[str, ast.AST]] = []

    # -- scope tracking ----------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.name_stack.append(node.name)
        self.generic_visit(node)
        self.name_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.name_stack.append(node.name)
        self.generic_visit(node)
        self.name_stack.pop()

    # -- loop-binding tracking ----------------------------------------------

    def _push_generators(self, generators: list[ast.comprehension]) -> int:
        pushed = 0
        for comp in generators:
            if isinstance(comp.target, ast.Name):
                self.loop_stack.append({comp.target.id: comp.iter})
                pushed += 1
        return pushed

    def _visit_comp(self, node: ast.GeneratorExp | ast.ListComp | ast.SetComp) -> None:
        pushed = self._push_generators(node.generators)
        for comp in node.generators:
            for cond in comp.ifs:
                self.visit(cond)
        self.visit(node.elt)
        for _ in range(pushed):
            self.loop_stack.pop()

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comp(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comp(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comp(node)

    def visit_For(self, node: ast.For) -> None:
        pushed = 0
        if isinstance(node.target, ast.Name):
            self.loop_stack.append({node.target.id: node.iter})
            pushed = 1
        self.generic_visit(node)
        for _ in range(pushed):
            self.loop_stack.pop()

    # -- the actual detection ------------------------------------------------

    def _resolve_loop_iter(self, name: str) -> ast.AST | None:
        for frame in reversed(self.loop_stack):
            if name in frame:
                return frame[name]
        return None

    def _resolve_keywords(self, iter_node: ast.AST) -> list[str] | None:
        elements = _string_elements(iter_node)
        if elements is not None:
            return elements
        if isinstance(iter_node, ast.Name):
            return self.bindings.get(iter_node.id)
        return None

    def visit_Compare(self, node: ast.Compare) -> None:
        self.generic_visit(node)
        if len(node.ops) != 1 or not isinstance(node.ops[0], ast.In):
            return

        operands = [node.left, *node.comparators]
        qualname = _enclosing_qualname(self.name_stack)

        # Case 1: direct literal string compared with `in` (no loop).
        for operand in operands:
            if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                self.result.call_sites_discovered += 1
                self.result.call_sites_resolved += 1
                kw = operand.value
                matched = [kw] if kw.upper() in SAFETY_VOCAB else []
                site = CallSite(
                    file=self.file_rel,
                    lineno=node.lineno,
                    qualname=qualname,
                    keywords=[kw],
                    matched_vocab=matched,
                    resolved=True,
                )
                if matched:
                    self.result.candidates.append(site)
                return  # one Compare node = one call site

        # Case 2: one side is a loop-bound Name; resolve its iterable.
        for operand in operands:
            if isinstance(operand, ast.Name):
                iter_node = self._resolve_loop_iter(operand.id)
                if iter_node is None:
                    continue
                self.result.call_sites_discovered += 1
                keywords = self._resolve_keywords(iter_node)
                if keywords is None:
                    self.result.call_sites_unresolved += 1
                    self.result.unresolved_sites.append(
                        CallSite(
                            file=self.file_rel,
                            lineno=node.lineno,
                            qualname=qualname,
                            keywords=[],
                            matched_vocab=[],
                            resolved=False,
                        )
                    )
                    return
                self.result.call_sites_resolved += 1
                matched = sorted({kw for kw in keywords if kw.upper() in SAFETY_VOCAB})
                site = CallSite(
                    file=self.file_rel,
                    lineno=node.lineno,
                    qualname=qualname,
                    keywords=keywords,
                    matched_vocab=matched,
                    resolved=True,
                )
                if matched:
                    self.result.candidates.append(site)
                return


def scan_file(path: Path, file_rel: str, result: ScanResult) -> None:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        raise GateError(f"{file_rel}: could not parse file: {e}") from e

    collector = _ConstantCollector()
    collector.visit(tree)

    visitor = _CompareVisitor(collector.bindings, file_rel, result)
    visitor.visit(tree)


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AllowlistEntry:
    qualname: str
    file_glob: str
    justification: str


def load_allowlist(path: Path) -> list[AllowlistEntry]:
    """Parse the allowlist. Missing file -> empty list (no allowlist is a
    valid, common state). Format mirrors
    ``.undeclared-imports-allowlist``: ``qualname::file-glob  #
    justification``. A line missing the ``::`` scope separator, missing a
    ``#`` justification, or with an empty qualname/glob/justification is a
    hard error (fail closed).
    """
    if not path.is_file():
        return []
    entries: list[AllowlistEntry] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "#" not in stripped:
            raise GateError(
                f"{path}:{lineno}: allowlist entry {stripped!r} has no "
                "'# justification' comment -- unjustified entries are not allowed"
            )
        key_part, justification = stripped.split("#", 1)
        justification = justification.strip()
        if not justification:
            raise GateError(
                f"{path}:{lineno}: allowlist entry {key_part.strip()!r} has an "
                "empty justification comment"
            )
        key_part = key_part.strip()
        if "::" not in key_part:
            raise GateError(
                f"{path}:{lineno}: allowlist entry {key_part!r} is missing the "
                "'qualname::file-glob' separator -- a bare qualname would exempt "
                "every file, which this gate does not allow"
            )
        qualname, file_glob = key_part.split("::", 1)
        qualname = qualname.strip()
        file_glob = file_glob.strip()
        if not qualname:
            raise GateError(f"{path}:{lineno}: allowlist entry has no qualname")
        if not file_glob:
            raise GateError(f"{path}:{lineno}: allowlist entry for {qualname!r} has no file glob")
        entries.append(AllowlistEntry(qualname, file_glob, justification))
    return entries


def matches_allowlist(qualname: str, file_rel: str, entries: list[AllowlistEntry]) -> bool:
    return any(
        fnmatch.fnmatch(qualname, e.qualname) and fnmatch.fnmatch(file_rel, e.file_glob)
        for e in entries
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


@dataclass
class Report:
    targets_inspected: list[str] = field(default_factory=list)
    files_inspected: int = 0
    call_sites_discovered: int = 0
    call_sites_resolved: int = 0
    call_sites_unresolved: int = 0
    unresolved_sites: list[CallSite] = field(default_factory=list)
    allowlisted: list[CallSite] = field(default_factory=list)
    violations: list[CallSite] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)


def run(
    repo_root: Path,
    allowlist_path: Path,
    scan_targets: list[ScanTarget] | None = None,
) -> tuple[str, Report]:
    """Returns (state, report), state in 'clean' | 'violation' | 'tool_error'."""
    report = Report()
    targets = scan_targets if scan_targets is not None else build_scan_targets(repo_root)

    try:
        allowlist = load_allowlist(allowlist_path)
    except GateError as e:
        report.tool_errors.append(str(e))
        return "tool_error", report

    if not targets:
        report.tool_errors.append("zero scan targets configured")
        return "tool_error", report

    all_files: list[Path] = []
    for target in targets:
        report.targets_inspected.append(target.label)
        if not target.root.is_dir():
            report.tool_errors.append(f"{target.label}: scan root does not exist: {target.root}")
            continue
        files = sorted(target.root.glob(target.pattern))
        files = [f for f in files if f.is_file() and "__pycache__" not in f.parts]
        if target.exclude_test_files:
            files = [f for f in files if not _is_test_file(f)]
        all_files.extend(files)

    if not all_files:
        report.tool_errors.append(
            "zero files found to inspect across all scan targets -- scan "
            "misconfigured or every scan root is empty"
        )
        return "tool_error", report

    report.files_inspected = len(all_files)

    result = ScanResult()
    for file_path in all_files:
        rel = str(file_path.relative_to(repo_root))
        try:
            scan_file(file_path, rel, result)
        except GateError as e:
            report.tool_errors.append(str(e))

    report.call_sites_discovered = result.call_sites_discovered
    report.call_sites_resolved = result.call_sites_resolved
    report.call_sites_unresolved = result.call_sites_unresolved
    report.unresolved_sites = result.unresolved_sites

    for site in result.candidates:
        if matches_allowlist(site.qualname, site.file, allowlist):
            report.allowlisted.append(site)
        else:
            report.violations.append(site)

    # Anti-vacuous-truth backstop: zero Compare(in) call sites discovered
    # across every parsed file, on a codebase with dozens of net-class
    # keyword lists, means the scan itself is broken -- never a
    # legitimate "nothing to check".
    if report.call_sites_discovered == 0 and not report.tool_errors:
        report.tool_errors.append(
            f"0 'in'-operator call sites discovered across {report.files_inspected} "
            "file(s) -- vacuous run, not a clean pass"
        )

    if report.tool_errors:
        return "tool_error", report
    if report.violations:
        return "violation", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report) -> None:
    print(
        f"Net-classification-by-substring gate -- {len(report.targets_inspected)} scan "
        f"target(s), {report.files_inspected} file(s), {report.call_sites_discovered} "
        f"'in'-operator call site(s) discovered "
        f"({report.call_sites_resolved} resolved, {report.call_sites_unresolved} unresolved)"
    )
    for t in report.targets_inspected:
        print(f"  - {t}")
    print(
        f"  candidates (vocab match): {len(report.violations) + len(report.allowlisted)}  "
        f"allowlisted: {len(report.allowlisted)}  violations: {len(report.violations)}"
    )

    if report.unresolved_sites:
        print(f"{len(report.unresolved_sites)} UNRESOLVED call site(s) (not counted as safe):")
        for s in report.unresolved_sites:
            print(f"  UNRESOLVED {s.file}:{s.lineno} in {s.qualname}")

    if report.tool_errors:
        print(f"{len(report.tool_errors)} TOOL ERROR(S)")
        for e in report.tool_errors:
            print(f"  TOOL_ERROR {e}")

    if report.violations:
        print(f"{len(report.violations)} VIOLATION(S)")
        for v in report.violations:
            print(
                f"  VIOLATION {v.file}:{v.lineno} in {v.qualname} -- plain substring "
                f"'in' test against HV/SELV keyword(s) {v.matched_vocab} (full keyword "
                f"list: {v.keywords}). Replace with a word-boundary regex "
                "(re.search(r'(?:^|_)KEYWORD(?:$|[\\d_])', upper)) or classify from "
                "elec/domain_manifest.yaml's exact net-name set. If this is a "
                "justified non-safety use, add a scoped, justified entry to "
                f"{DEFAULT_ALLOWLIST_NAME}."
            )

    if state == "clean":
        print("Net-classification-by-substring gate passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help=f"Path to allowlist (default: repo_root/{DEFAULT_ALLOWLIST_NAME})",
    )
    args = parser.parse_args()

    repo_root = find_repo_root()
    allowlist_path = args.allowlist or (repo_root / DEFAULT_ALLOWLIST_NAME)

    state, report = run(repo_root, allowlist_path)
    _print_report(state, report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### Net-classification-by-substring gate: {state}\n")
            f.write(
                f"- Scan targets: {len(report.targets_inspected)}\n"
                f"- Files inspected: {report.files_inspected}\n"
                f"- 'in' call sites discovered: {report.call_sites_discovered} "
                f"({report.call_sites_resolved} resolved, "
                f"{report.call_sites_unresolved} unresolved)\n"
                f"- Allowlisted: {len(report.allowlisted)}\n"
                f"- Violations: {len(report.violations)}\n"
                f"- Tool errors: {len(report.tool_errors)}\n"
            )

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
