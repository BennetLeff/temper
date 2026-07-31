#!/usr/bin/env python3
"""Creepage/clearance safety-constant SSOT-drift gate.

Motivation
----------
The board's insulation figures (how many millimetres of surface path or
through-air gap are required across the mains<->SELV boundary) are declared
independently in at least four places that must agree, and nothing before
this gate cross-checked them:

  - ``elec/src/constraints.ato`` -- the compiled netlist's own source of
    truth (``HighVoltage.creepage``, ``HV_to_LV.min_creepage``, ...).
  - ``scripts/check_isolation_keepout.py`` -- ``MIN_BARRIER_WIDTH_MM``, the
    physical keepout-width gate.
  - ``scripts/generate_kicad_dru.py`` -- the emitted KiCad DRC rule text
    (``HV_CREEPAGE_*_MM``).
  - ``packages/temper-placer/configs/pcl/temper_production.yaml`` -- the
    placer's ``separated`` constraints, whose ``because`` fields cite the
    ``.ato`` block they claim to mirror.

This drifted for real: the pollution-degree retarget from PD2 (8.0mm) to
PD3 (12.6mm) -- see ``docs/ENVIRONMENTAL_SPEC.md`` Sec 3.1 and commit
``c58c94d8`` -- updated ``check_isolation_keepout.py`` and
``generate_kicad_dru.py`` but never touched ``constraints.ato`` or the pcl
yaml. The board's DRC keepout gate and the netlist it's supposedly
guarding disagree about the number, silently, on a mains-connected design.
``docs/brainstorms/2026-06-21-safety-constant-ssot-requirements.md``
predicted exactly this shape of drift a month earlier; this gate is the
mechanism that document asked for, not another doc.

Why discovery, not a file list
-------------------------------
A checker that reads its universe of "files to compare" from a
hand-maintained list has the list as its blind spot -- the list itself can
drift out of sync with the real set of declaration sites, invisibly, even
while the check's own logic stays correct (see
``docs/solutions/best-practices/gate-scope-hand-maintained-blind-spot-2026-07-29.md``,
which documents exactly this failure mode on this project's own DRU
generator). This gate instead *discovers* every creepage/clearance
declaration under ``elec/``, ``scripts/``, ``packages/``, ``configs/`` by
walking the actual source (``.ato`` line/module structure, Python module
top-level ASTs, YAML key-value lines), independent of which specific files
happen to hold them today. Adding a fifth site that declares a creepage or
clearance figure is picked up automatically on the next run; nobody has to
remember to add it to a list.

The discovery is deliberately *not* "grep every file for the substring
clearance" -- this codebase is a KiCad autorouter, and hundreds of files use
"clearance" as an ordinary per-call routing-engine variable (computed
per-pad, per-net, inside function bodies) that has nothing to do with a
declared IEC insulation figure. Scanning those would drown the real
findings in noise and produce exactly the "cries wolf, gets disabled"
outcome this gate must avoid. So the scan is scoped to *declaration sites*:

  - ``.ato``: any ``(min_|air_)?(creepage|clearance) = <N>mm`` module
    attribute -- the only place this DSL expresses such a thing.
  - Python: module- or class-level (never inside a function/lambda body --
    that is where a per-call local variable would live, and it is
    deliberately excluded) constant assignments, plus keyword arguments
    inside module-level dataclass-construction calls (the
    ``TEMPER_NET_CLASSES = {"ACMains": NetClassRules(clearance=6.0, ...)}``
    shape).
  - YAML: mapping keys that are themselves ``creepage``/``clearance``-named
    (direct), or a numeric field (e.g. ``min_distance_mm``) whose ``because``
    text explicitly cites a creepage/clearance figure by value (indirect --
    see "Indirect YAML matching" below).

Not conflating distinct quantities
------------------------------------
Creepage (surface path) and clearance (through-air) are different physical
metrics and are NEVER compared to each other. Within one metric, REINFORCED
insulation is twice BASIC insulation by IEC 60335-1 cl. 29.2.3, and
"working" isolation (a third, looser figure this codebase's own
``check_isolation_keepout.py`` docstring already distinguishes from
"reinforced") is a fourth. Forcing all "clearance"-named numbers to agree
would be wrong on its face -- e.g. ``constraints.ato``'s ACMains/AC_to_LV
5.0mm creepage figures are *correctly* different from HighVoltage/HV_to_LV's
8.0mm figures; conflating them would be a false positive that trains
reviewers to ignore the gate.

So every discovered declaration is classified into a **family** =
``(metric, tier)`` where ``metric in {"creepage", "clearance"}`` and
``tier in {"reinforced", "basic", "working", "unspecified"}``. The tier is
read from the text actually attached to the declaration (a same-line
comment, the contiguous comment block immediately above it, or -- for
``.ato`` -- the enclosing module's own doc-comment, or -- for YAML -- a
sibling ``because``/``reason``/``description`` field) rather than guessed
from the declaration's name or location. Only declarations whose tier is
explicitly stated (``reinforced``/``basic``/``working``) are compared for
agreement; a family is asserted internally consistent (all its members
carry the same ``value_mm``) or reported as a VIOLATION naming every site
and value. Declarations with an unresolvable tier (``unspecified``) are
never silently dropped -- they are discovered, counted in the denominator,
and printed in their own "needs human classification" section, never
force-compared against anything.

Indirect YAML matching (the pcl-yaml case)
--------------------------------------------
``packages/temper-placer/configs/pcl/temper_production.yaml``'s
``separated`` constraints carry the real figure in ``min_distance_mm``, but
the key name alone gives no metric. The entry's own ``because`` text does:
e.g. ``"IEC 60335-1 reinforced-insulation creepage, HV tank cap ... to MCU
(constraints.ato HV_to_LV)"``. The gate resolves the metric for such a field
by (1) looking for an explicit ``<metric>=<value>mm`` mention in the nearby
text whose value matches the field's own value (the strongest signal -- the
pcl yaml literally writes ``min_creepage=8.0mm`` inside its own
justification), then (2) falling back to whichever of creepage/clearance is
the only keyword present, then (3) whichever keyword appears first in the
text if both are present with no numeric confirmation -- this last case is
marked with ``metric_confidence="heuristic-order"`` and is excluded from
automatic equality assertions (reported separately, not guessed into a
family).

Known blind spots (stated, not hidden)
-----------------------------------------
- A Python constant is only picked up if its name is an EXACT
  ``(min_|air_)?(creepage|clearance)(_mm)?`` token, OR it ends in ``_MM``/``mm``
  (this codebase's own unit-marking convention) AND its attached comment
  text names "creepage" or "clearance" explicitly. A value with neither
  signal (e.g. a dimensionless ratio like
  ``INTERNAL_LAYER_CREEPAGE_FACTOR = 0.30``, which is not itself a
  millimetre figure) is deliberately excluded rather than guessed into the
  mm comparison -- see ``_is_mm_named``.
- Local/per-call variables inside function bodies are structurally excluded
  everywhere (AST scan skips function/lambda bodies entirely). This is a
  routing-engine codebase; "clearance" as a runtime-computed local is the
  overwhelming majority of the word's occurrences and is not a declared
  constant.
- The tier classifier is a keyword search, not a citation parser: text that
  discusses "reinforced" and "basic" insulation in the same paragraph
  without a clean nearest-occurrence signal can be misclassified. Any
  declaration whose tier or metric was resolved via a low-confidence path
  is surfaced separately in the report, never silently folded into a family.
- The tier classifier cannot distinguish "this VALUE is the reinforced
  figure" from "this value's own justification text happens to MENTION a
  reinforced barrier as context". E.g.
  ``packages/temper-placer/configs/netclass_rules.yaml``'s ``GateDriveHV``
  class carries ``clearance: 0.25`` (an ordinary intra-class routing
  spacing) with a ``because`` field explaining that the class sits on the
  HV side of a *reinforced* barrier -- the 0.25mm figure is not itself a
  barrier-crossing distance, but it is tier-tagged "reinforced" anyway and
  would otherwise be compared against real barrier-crossing figures (2.0mm,
  6.0mm). This produces a family with a mix of "the barrier distance
  itself" and "a same-side routing spacing that merely cites the barrier's
  existence". This is a real, observed limitation (not a hypothetical one),
  and resolving it *mechanically, in general* would require parsing which
  noun phrase in a free-text justification the number actually refers to,
  which is out of reach for a keyword search -- that general problem is NOT
  solved here.

  What IS done: the two specific sites this shape was found on
  (``GateDriveHV.clearance``, ``GateDriveSELV.clearance``, both 0.25mm) were
  investigated by hand 2026-07-29 and confirmed to be ordinary intra-class
  routing spacing -- consistent with every LV-tier sibling class in the same
  file (FinePitch 0.1mm, Power 0.25mm, GND 0.3mm, none tier-tagged), and
  categorically too small to be a barrier-crossing figure under any voltage
  domain this board declares (the smallest REINFORCED clearance this
  project's own tables carry, at 50V, is 1.0mm -- see
  ``docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`` Sec 4.1). Those two exact
  sites are carried in ``KNOWN_TIER_MISCLASSIFICATIONS`` below and excluded
  from family comparison, so they read in the report as a named, cited
  "known blind spot" rather than a live MISMATCH a reviewer has to
  re-investigate on every run. This is a closed set of two, not a general
  "ignore reinforced near GateDrive" rule -- see that constant's own
  docstring for why it is deliberately narrow and how it guards against
  becoming its own hand-maintained blind spot (the failure mode
  ``docs/solutions/best-practices/gate-scope-hand-maintained-blind-spot-
  2026-07-29.md`` documents).
- A tier label alone ("basic", "reinforced", ...) does not imply two
  same-tier declarations govern the same voltage pair or the same kind of
  requirement. Investigated 2026-07-29: ``elec/src/constraints.ato``'s
  ``AC_to_LV`` (3.0mm clearance / 5.0mm creepage, "Basic insulation") and
  ``configs/temper_deterministic_config.yaml``'s
  ``net_class_rules.HighVoltage`` (6.0mm / 6.0mm, "Table 17 (basic
  insulation)") both land in the ``[clearance/basic]``/``[creepage/basic]``
  families and both genuinely say "basic" -- but they are not the same
  requirement. ``AC_to_LV`` is the atopile-compiled SSOT's own
  cross-domain-pair barrier between the 135V ACMains net class
  (``elec/src/constraints.ato``'s ``ACMainsConstraints.v_max``) and
  Default/LV. ``net_class_rules.HighVoltage`` is a single net class's own
  general routing-clearance figure consumed only by the separate, legacy
  deterministic-placement pipeline (``scripts/run_feedback_loop.py`` ->
  ``temper_placer.io.config_loader``), and that class lumps AC_L/AC_N
  together with DC_BUS+/DC_BUS-/SW_NODE under one higher voltage bucket
  (``voltage_class: mains_240v`` in that same file) -- i.e. a materially
  higher working voltage than the 135V AC_to_LV pair governs. IEC 60335-1's
  basic-insulation clearance/creepage figures are working-voltage-indexed
  (``docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`` Sec 4.1/5.1's own tables),
  so a larger "basic" figure at a higher declared voltage bucket is the
  expected direction, not drift. This gate still reports the two as a
  MISMATCH (deliberately -- see below) rather than special-casing them the
  way ``KNOWN_TIER_MISCLASSIFICATIONS`` special-cases GateDriveHV/SELV:
  those two are a confirmed classifier bug on a single field whose own
  value cannot plausibly be the tier it was tagged; this pair is two
  different subsystems each correctly describing their own genuinely
  different requirement, and collapsing "basic" into a
  voltage/subsystem-aware family key would require the same kind of
  free-text-provenance parsing already ruled out above, on every future
  "basic"-tagged pair, not just this one. Investigated and left flagged for
  continued human review, not silently resolved.

Declared candidates vs. an enforced selection alias
-----------------------------------------------------
A module may deliberately declare more than one candidate figure for the
same requirement -- e.g. ``scripts/generate_kicad_dru.py`` declares BOTH
``HV_CREEPAGE_PD2_MM = 8.0`` and ``HV_CREEPAGE_PD3_MM = 12.6`` (an open,
unresolved pollution-degree call) and then picks ONE via
``HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD2_MM``. Two same-tier, same-metric
literals in one file would normally be a real MISMATCH, and would be here
too, except that the second assignment structurally selects between them:
its RHS is a bare name referring to another already-declared, literal
module-level constant, not a literal itself -- the exact same shape this
gate already treats specially for any non-literal RHS (see
``DEFAULT_CORRIDOR_WIDTH_MM``, historically a ``BinOp``, moved to
"unresolved, not compared"; a bare-``Name`` RHS is resolved to that name's
own value instead of being left unresolved). See
``_resolve_selection_aliases`` for the full mechanism: this is detected
structurally (any ``NAME2 = NAME1`` where NAME1 is a declared in-file
literal), never by matching the substring "ENFORCED" or any other naming
convention, precisely so renaming the selector cannot silently stop it
working. The selected candidate keeps participating in its family exactly
as before; every OTHER same-file, same-family candidate is excluded from
comparison and reported under a "declared but not enforced" heading naming
the value that IS enforced instead -- discovered and counted, never
silently dropped.

Fail-closed contract
---------------------
- Discovery running over zero files (a scan root missing) or finding zero
  declarations at all is a GATE ERROR (exit 5), never "0 violations" --
  the anti-vacuous-truth rule this repo's other gates already follow (see
  ``scripts/check_vacuous_gates.py``, ``scripts/check_evidence_provenance.py``).
- A file that cannot be parsed (malformed YAML, a Python syntax error) is a
  per-file VIOLATION, not silently skipped -- matching
  ``check_evidence_provenance.py``'s convention.
- The report always states its denominator: how many files were scanned,
  how many declarations were found, how many were compared vs. flagged
  vs. excluded, so a clean run can never be mistaken for a scan that found
  nothing.

Exit codes
----------
  0 - OK: at least one declaration found, every family (metric, explicit
      tier) with 2+ members carries exactly one distinct value.
  3 - VIOLATION: a file failed to parse, or a family has more than one
      distinct value among its members.
  5 - GATE ERROR: a scan root is missing, or discovery found zero
      declarations anywhere (the check did not actually run).

Usage
-----
  uv run --no-sync python scripts/check_creepage_clearance_drift.py
  uv run --no-sync python scripts/check_creepage_clearance_drift.py --repo-root PATH
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

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

SCAN_ROOT_NAMES = ("elec", "scripts", "packages", "configs")

# Directory-*shape* excludes (never a per-file list): synthetic test
# fixtures, scratch spikes, demo scripts, and caches are not authoritative
# declarations of a real board constant, and including them would produce
# spurious families full of arbitrary test values. This mirrors
# check_vacuous_gates.py's own "denylist known non-authoritative
# conventions, default-include everything else" scoping rationale.
NOISE_DIR_NAMES = frozenset(
    {
        "tests",
        "test",
        "fixtures",
        "experiments",
        "spikes",
        "examples",
        ".cache",
        "__pycache__",
        "ablation_feature_tests",
        "node_modules",
        ".git",
    }
)

TIER_ORDER = ("reinforced", "basic", "working")  # most-specific first

_NAME_TOKEN_RE = re.compile(r"(?:^|_)(creepage|clearance)(?:_mm)?(?:_|$)", re.IGNORECASE)
_MM_SUFFIX_RE = re.compile(r"(?:^|_)mm$", re.IGNORECASE)

# Known, human-reviewed tier misclassifications -- see the module docstring
# "Known blind spots" section for the full investigation. This is
# deliberately NOT a hand-maintained *scope* list (discovery above always
# walks every file under SCAN_ROOT_NAMES; nothing here shrinks what is
# found, counted, or reported) -- it is a narrow override of the TIER this
# gate's own keyword classifier assigned to two already-discovered
# declarations, applied only after discovery, and verified in
# build_families() so it cannot become the silent, stale-but-still-applied
# blind spot ``docs/solutions/best-practices/gate-scope-hand-maintained-
# blind-spot-2026-07-29.md`` warns about: the gate ERRORS (fails closed) if
# a listed site IS discovered but no longer classifies as "reinforced" on
# its own (the override would then be silently protecting nothing, or
# worse, hiding a since-changed value). A listed site simply not appearing
# in a given run (a synthetic test tree, or a real tree -- e.g.
# origin/main -- that predates the GateDrive/HV split this override
# targets) is not an error: this override can only narrow an
# already-discovered declaration, so its absence changes nothing.
#
# Each entry is (file, name) exactly as Declaration.file/.name render them.
KNOWN_TIER_MISCLASSIFICATIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (
            "packages/temper-placer/configs/netclass_rules.yaml",
            "classes.GateDriveHV.clearance",
        ),
        (
            "packages/temper-placer/configs/netclass_rules.yaml",
            "classes.GateDriveSELV.clearance",
        ),
    }
)


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


@dataclass
class Declaration:
    file: str
    line: int
    name: str
    metric: str  # "creepage" | "clearance" | "" (unresolved)
    metric_confidence: str  # "direct" | "numeric-match" | "single-keyword" | "heuristic-order" | "error"
    tier: str  # "reinforced" | "basic" | "working" | "unspecified"
    value_mm: float | None
    raw: str
    context: str
    # Set only by _resolve_selection_aliases (Python discovery): this
    # declaration is a sibling candidate that a same-file *selection alias*
    # (see that function's docstring) did NOT select. It is a live,
    # discovered declaration -- never dropped -- but is excluded from
    # cross-file family comparison because the codebase itself says this
    # value is not the one enforced. enforced_value_mm/enforced_site/
    # enforcing_alias name the alias and the value it selected instead, so
    # the report can always show "declared X, but Y is enforced via Z".
    declared_not_enforced: bool = False
    enforced_value_mm: float | None = None
    enforced_site: str | None = None
    enforcing_alias: str | None = None

    @property
    def site(self) -> str:
        return f"{self.file}:{self.line} ({self.name})"


@dataclass
class Report:
    files_scanned: int = 0
    parse_errors: list[tuple[str, str]] = field(default_factory=list)
    declarations: list[Declaration] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared text-classification helpers
# ---------------------------------------------------------------------------


def _is_noise_path(path: Path) -> bool:
    return any(part in NOISE_DIR_NAMES for part in path.parts)


def _classify_tier(text: str) -> str:
    lower = text.lower()
    if "reinforced" in lower:
        return "reinforced"
    if "basic insulation" in lower or re.search(r"\bbasic\b", lower):
        return "basic"
    if "working insulation" in lower or re.search(r"\bworking\b", lower):
        return "working"
    return "unspecified"


def _resolve_metric(text: str, target_value: float | None) -> tuple[str, str]:
    """Resolve which metric (creepage/clearance) a piece of context text is
    about. Returns (metric, confidence); metric == "" means unresolved."""
    lower = text.lower()
    has_creepage = "creepage" in lower
    has_clearance = "clearance" in lower
    if has_creepage and not has_clearance:
        return "creepage", "single-keyword"
    if has_clearance and not has_creepage:
        return "clearance", "single-keyword"
    if not has_creepage and not has_clearance:
        return "", "none"
    # Both present. Strongest signal: this declaration's own value appears
    # in the text as an explicit "<N>mm" mention, with a creepage/clearance
    # keyword *before* it (not just anywhere in the paragraph) -- e.g.
    # check_isolation_keepout.py's own derivation reads "...REINFORCED
    # creepage... top of the plan's stated 3.0-8.0mm range", where "8.0mm"
    # is the declaration's value and "creepage" is the nearest keyword
    # preceding it (a later, unrelated "clearance" reference elsewhere in
    # the same paragraph must not win just because it's also present).
    # Only a *preceding* keyword counts as confirmation -- if neither
    # keyword precedes the matched number, this is not real disambiguation
    # (e.g. "10mm creepage and clearance" has the number before both words
    # equally; that is a genuinely ambiguous statement, not a resolved
    # one) and the heuristic-order fallback below is used instead.
    if target_value is not None:
        for num_m in re.finditer(r"([\d.]+)\s*mm", lower):
            try:
                if abs(float(num_m.group(1)) - target_value) >= 1e-6:
                    continue
            except ValueError:
                continue
            pos = num_m.start()
            idx_creep = lower.rfind("creepage", 0, pos)
            idx_clear = lower.rfind("clearance", 0, pos)
            if idx_creep == -1 and idx_clear == -1:
                continue
            return ("creepage", "numeric-match") if idx_creep > idx_clear else ("clearance", "numeric-match")
    # No numeric confirmation: fall back to first-occurrence order, but mark
    # the confidence low so it is excluded from automatic equality checks.
    idx_creep = lower.find("creepage")
    idx_clear = lower.find("clearance")
    return ("creepage", "heuristic-order") if idx_creep < idx_clear else ("clearance", "heuristic-order")


def _contiguous_comment_block_above(lines: list[str], idx: int, comment_prefix: str = "#") -> str:
    """Text of the contiguous comment lines immediately above lines[idx],
    stopping at the first blank or non-comment line. Never crosses a blank
    line -- that is what keeps a module's own doc-comment from bleeding
    into an unrelated section banner above it."""
    out: list[str] = []
    i = idx - 1
    while i >= 0:
        stripped = lines[i].strip()
        if stripped.startswith(comment_prefix):
            out.append(stripped.lstrip(comment_prefix).strip())
            i -= 1
        else:
            break
    out.reverse()
    return " ".join(out)


# ---------------------------------------------------------------------------
# .ato extractor
# ---------------------------------------------------------------------------

_ATO_ATTR_RE = re.compile(
    r"^(?P<indent>\s*)(?P<name>(?:min_|air_)?(?:creepage|clearance))"
    r"\s*=\s*(?P<value>[\d.]+)\s*mm\s*(?:#\s*(?P<comment>.*))?$",
    re.IGNORECASE,
)
_ATO_MODULE_RE = re.compile(r"^(?P<indent>\s*)module\s+(?P<name>\w+)\s*:")


def discover_ato(repo_root: Path) -> list[Declaration]:
    decls: list[Declaration] = []
    ato_root = repo_root / "elec"
    if not ato_root.is_dir():
        return decls
    for path in sorted(ato_root.rglob("*.ato")):
        if _is_noise_path(path.relative_to(repo_root)):
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        rel = str(path.relative_to(repo_root))
        module_stack: list[tuple[int, str, str]] = []  # (indent_len, name, doc_text)
        for i, line in enumerate(lines):
            mod_m = _ATO_MODULE_RE.match(line)
            if mod_m:
                indent_len = len(mod_m.group("indent"))
                while module_stack and module_stack[-1][0] >= indent_len:
                    module_stack.pop()
                doc = _contiguous_comment_block_above(lines, i)
                module_stack.append((indent_len, mod_m.group("name"), doc))
                continue
            attr_m = _ATO_ATTR_RE.match(line)
            if not attr_m:
                continue
            indent_len = len(attr_m.group("indent"))
            while module_stack and module_stack[-1][0] >= indent_len:
                module_stack.pop()
            enclosing_name = module_stack[-1][1] if module_stack else "<top-level>"
            enclosing_doc = module_stack[-1][2] if module_stack else ""
            name_token = attr_m.group("name").lower()
            metric = "creepage" if "creepage" in name_token else "clearance"
            value = float(attr_m.group("value"))
            own_comment = attr_m.group("comment") or ""
            own_block = _contiguous_comment_block_above(lines, i)
            context = " ".join(filter(None, [own_comment, own_block, enclosing_doc]))
            tier = _classify_tier(context)
            decls.append(
                Declaration(
                    file=rel,
                    line=i + 1,
                    name=f"{enclosing_name}.{name_token}",
                    metric=metric,
                    metric_confidence="direct",
                    tier=tier,
                    value_mm=value,
                    raw=line.strip(),
                    context=context.strip(),
                )
            )
    return decls


# ---------------------------------------------------------------------------
# Python extractor
# ---------------------------------------------------------------------------


def _py_scan_roots(repo_root: Path) -> list[Path]:
    roots = []
    for name in SCAN_ROOT_NAMES:
        d = repo_root / name
        if d.is_dir():
            roots.append(d)
    return roots


class _PyDeclCollector(ast.NodeVisitor):
    """Walks module/class-level statements only -- function and lambda
    bodies are skipped entirely (that is where a per-call routing-engine
    local variable named "clearance" would live; it is not a declared
    constant and must not be discovered as one)."""

    def __init__(self, rel_path: str, lines: list[str]):
        self.rel_path = rel_path
        self.lines = lines
        self.decls: list[Declaration] = []
        self._suppress = 0  # >0 while inside a function/lambda body

    # -- scope control ----------------------------------------------------
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._suppress += 1
        self.generic_visit(node)
        self._suppress -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._suppress += 1
        self.generic_visit(node)
        self._suppress -= 1

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        self._suppress += 1
        self.generic_visit(node)
        self._suppress -= 1

    # -- declarations -------------------------------------------------------
    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        if self._suppress == 0:
            self._handle_assign(node.targets, node.value, node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        if self._suppress == 0 and node.value is not None:
            self._handle_assign([node.target], node.value, node.lineno)
        self.generic_visit(node)

    def _context_for(self, lineno: int) -> str:
        idx = lineno - 1
        same_line = ""
        if 0 <= idx < len(self.lines):
            line = self.lines[idx]
            if "#" in line:
                same_line = line.split("#", 1)[1].strip()
        block = _contiguous_comment_block_above(self.lines, idx)
        return " ".join(filter(None, [same_line, block]))

    def _literal_value(self, value_node: ast.expr) -> float | None:
        if isinstance(value_node, ast.Constant) and isinstance(value_node.value, (int, float)) and not isinstance(
            value_node.value, bool
        ):
            return float(value_node.value)
        if isinstance(value_node, ast.UnaryOp) and isinstance(value_node.op, ast.USub):
            inner = self._literal_value(value_node.operand)
            return -inner if inner is not None else None
        return None

    def _raw(self, node: ast.expr) -> str:
        try:
            return ast.unparse(node)
        except Exception:  # pragma: no cover - defensive
            return "<unparseable>"

    def _handle_assign(self, targets: list[ast.expr], value_node: ast.expr, lineno: int) -> None:
        if len(targets) == 1 and isinstance(targets[0], ast.Name):
            name = targets[0].id
            name_token = None
            m = _NAME_TOKEN_RE.search(name)
            if m:
                name_token = m.group(1).lower()
            is_mm = bool(_MM_SUFFIX_RE.search(name))

            if name_token is not None and is_mm:
                # Direct: the name itself names the metric and its own unit.
                self._record(name, name_token, "direct", value_node, lineno)
            elif is_mm:
                # Comment-fallback: name gives no metric, but is unit-marked
                # -- consult attached text. See module docstring "Known
                # blind spots" for why _MM is required here (excludes
                # dimensionless ratios like *_FACTOR/*_THRESHOLD).
                context = self._context_for(lineno)
                target_value = self._literal_value(value_node)
                metric, confidence = _resolve_metric(context, target_value)
                if metric:
                    self._record(name, metric, confidence, value_node, lineno, context_override=context)
            # else: neither signal -- not a candidate at all (e.g. a plain
            # ratio/threshold with no mm marker and no metric in its name).

        # Regardless of the target shape, also walk the RHS for nested
        # dataclass-construction keywords (TEMPER_NET_CLASSES's
        # {"ACMains": NetClassRules(clearance=6.0, creepage_mm=6.0, ...)}
        # shape) -- this does not depend on the *outer* variable's name at
        # all, which is what lets it find declarations regardless of how
        # the containing dict/list happens to be named.
        path_label = targets[0].id if len(targets) == 1 and isinstance(targets[0], ast.Name) else "<assign>"
        self._walk_for_calls(value_node, [path_label])

    def _walk_for_calls(self, node: ast.expr, path: list[str]) -> None:
        if isinstance(node, ast.Dict):
            for key, val in zip(node.keys, node.values, strict=True):
                label = ast.literal_eval(key) if isinstance(key, ast.Constant) else "?"
                self._walk_for_calls(val, path + [str(label)])
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            for elt in node.elts:
                self._walk_for_calls(elt, path)
        elif isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg is None:
                    continue
                kw_m = _NAME_TOKEN_RE.search(kw.arg)
                if kw_m:
                    metric = kw_m.group(1).lower()
                    qualname = ".".join(path + [kw.arg])
                    self._record(qualname, metric, "direct", kw.value, kw.value.lineno, name_is_qualname=True)
                # Recurse in case a keyword's own value is itself a
                # structure worth walking (defensive; not exercised by any
                # known site today).
                self._walk_for_calls(kw.value, path)
            for arg in node.args:
                self._walk_for_calls(arg, path)

    def _record(
        self,
        name: str,
        metric: str,
        confidence: str,
        value_node: ast.expr,
        lineno: int,
        context_override: str | None = None,
        name_is_qualname: bool = False,
    ) -> None:
        value = self._literal_value(value_node)
        alias_of: str | None = None
        if value is None and isinstance(value_node, ast.Name):
            alias_of = value_node.id  # resolved in a second pass
        context = context_override if context_override is not None else self._context_for(lineno)
        tier = _classify_tier(context)
        display_name = name if name_is_qualname else name
        self.decls.append(
            Declaration(
                file=self.rel_path,
                line=lineno,
                name=display_name,
                metric=metric,
                metric_confidence=confidence,
                tier=tier,
                value_mm=value,
                raw=self._raw(value_node) if alias_of is None else f"= {alias_of} (alias)",
                context=context.strip(),
            )
        )
        if alias_of is not None:
            # Stash the alias target on the Declaration via a private attr
            # for the second-pass resolver below.
            self.decls[-1].__dict__["_alias_of"] = alias_of


def _resolve_python_aliases(decls: list[Declaration], all_literal_by_name: dict[str, float]) -> None:
    """Second pass: resolve `NAME2 = NAME1` aliases to NAME1's literal
    value, transitively, within the same file's already-collected literal
    names (e.g. HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM)."""
    for d in decls:
        alias_of = d.__dict__.get("_alias_of")
        seen = set()
        while alias_of is not None and alias_of not in seen:
            seen.add(alias_of)
            if alias_of in all_literal_by_name:
                d.value_mm = all_literal_by_name[alias_of]
                d.raw = f"{d.raw} -> resolved via {alias_of} = {d.value_mm}"
                break
            alias_of = None


def _propagate_sibling_tier(decls: list[Declaration]) -> None:
    """A run of back-to-back constant declarations with no separating
    comment (e.g. ``HV_CREEPAGE_PD2_MM = 8.0`` immediately followed by
    ``HV_CREEPAGE_PD3_MM = 12.6  # flagged default per IEC 60335-2-6 cl.
    29.2; UNRESOLVED``) shares ONE explanatory comment block, attached only
    to the first line of the run. ``_contiguous_comment_block_above`` finds
    that block for the first declaration and (correctly) finds nothing for
    the second, since the immediately-preceding line is code, not a
    comment. Without this pass the second constant's tier reads as
    "unspecified" even though it is textually one editorial unit with the
    first -- measured directly on ``scripts/generate_kicad_dru.py``'s
    ``HV_CREEPAGE_PD3_MM``, which sits directly below ``HV_CREEPAGE_PD2_MM``
    and shares its "reinforced creepage" comment block.

    Deliberately narrow: only fires when the two declarations are on
    *exactly* consecutive lines within the same file (no blank line, no
    unrelated statement between them) and the earlier one already has a
    resolved tier. It never invents agreement between declarations that are
    merely nearby -- see ``_yaml_window``'s docstring for the sibling-bleed
    failure this project already hit once by being looser than that."""
    by_line = {d.line: d for d in decls}
    for d in sorted(decls, key=lambda x: x.line):
        if d.tier != "unspecified":
            continue
        prev = by_line.get(d.line - 1)
        if prev is not None and prev.tier != "unspecified":
            d.tier = prev.tier
            d.context = f"{d.context} [tier inherited from adjacent declaration at line {prev.line}]".strip()


def _resolve_selection_aliases(decls: list[Declaration]) -> None:
    """Third pass, within one file: mark unselected sibling candidates for
    each *selection alias*.

    A selection alias is nothing new -- it is the exact same structural
    shape ``_resolve_python_aliases`` (two passes above this one) already
    detects and resolves: an assignment whose RHS is a bare ``ast.Name``
    referring to another declared, literal-valued, direct-metric constant in
    the same file (recorded as ``_alias_of`` on the Declaration by
    ``_PyDeclCollector._record`` when the RHS is an ``ast.Name`` rather than
    a ``Constant``). There is deliberately no separate "is this an ENFORCED
    constant" detector and no substring match on the assigned name --
    ``HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD2_MM`` is detected the same way
    ``HV_CREEPAGE_ACTIVE_MM = HV_CREEPAGE_PD2_MM`` or
    ``foo = HV_CREEPAGE_PD2_MM`` would be: any bare-name RHS pointing at
    another in-file literal constant is, structurally, a selection between
    that constant and whatever else shares its (metric, tier) family. This
    is what keeps the mechanism from rotting the way a name-convention rule
    would the day someone renames or adds a differently-named selector.

    Given a selection alias A whose RHS resolves (via ``_alias_of``, already
    populated with a literal value by ``_resolve_python_aliases``) to target
    T, every OTHER literal, non-alias declaration in the SAME FILE sharing
    T's already-classified (metric, tier) is a *declared but unselected
    candidate*: T is the value A actually enforces, so cross-comparing the
    others against T -- or against declarations in other files -- would be
    comparing a figure the module's own source says is not live. Those
    candidates are marked ``declared_not_enforced`` (never removed from
    ``decls``, never hidden): ``build_families`` pulls them out of the
    comparable pool by that flag and ``_print_report`` lists them under a
    dedicated "declared but not enforced" heading, each tagged with T's
    resolved value and site -- so a genuinely stale candidate cannot go
    quiet, it can only stop being force-compared against a value it was
    never actually enforcing.

    T itself is untouched by this pass -- it keeps whatever (metric, tier)
    its own attached text already gave it, and continues to participate in
    family comparison exactly as any other declaration does. That is what
    satisfies "the enforced value still participates in its family and must
    still be compared against constants in other files": no special-casing
    is needed for T, only for the candidates it is being distinguished from.
    ``build_families`` additionally verifies T actually lands in a
    comparable family (self-verification: see its docstring) -- if a future
    refactor strips T's own tier/metric context, that must surface as a
    GateError, not silently stop enforcing anything."""
    literal_by_name: dict[str, Declaration] = {
        d.name: d
        for d in decls
        if d.value_mm is not None
        and d.__dict__.get("_alias_of") is None
        and "." not in d.name
        and " " not in d.name
    }
    for alias in decls:
        alias_of = alias.__dict__.get("_alias_of")
        if alias_of is None or alias.value_mm is None:
            continue
        target = literal_by_name.get(alias_of)
        if target is None:
            # The alias's RHS name did not resolve to an in-file literal
            # constant this pass can see. `_resolve_python_aliases` already
            # leaves such an alias's own value_mm as None when this happens
            # (e.g. the RHS names an imported symbol), so it is reported
            # under UNRESOLVED, not silently treated as a clean enforced
            # figure -- nothing further to mark here.
            continue
        for other in decls:
            if other is target or other is alias:
                continue
            if other.__dict__.get("_alias_of") is not None:
                continue  # aliases are selectors, not candidates themselves
            if other.value_mm is None:
                continue
            if other.metric == target.metric and other.tier == target.tier:
                other.declared_not_enforced = True
                other.enforced_value_mm = target.value_mm
                other.enforced_site = target.site
                other.enforcing_alias = alias.name


def discover_python(repo_root: Path) -> tuple[list[Declaration], list[tuple[str, str]]]:
    decls: list[Declaration] = []
    errors: list[tuple[str, str]] = []
    seen_files: set[Path] = set()
    for root in _py_scan_roots(repo_root):
        for path in sorted(root.rglob("*.py")):
            if _is_noise_path(path.relative_to(repo_root)):
                continue
            if path in seen_files:
                continue
            seen_files.add(path)
            rel = str(path.relative_to(repo_root))
            try:
                text = path.read_text(encoding="utf-8")
                tree = ast.parse(text, filename=rel)
            except (SyntaxError, UnicodeDecodeError) as exc:
                errors.append((rel, f"could not parse: {exc}"))
                continue
            lines = text.splitlines()
            collector = _PyDeclCollector(rel, lines)
            collector.visit(tree)
            # Build a name->literal-value map for alias resolution, using
            # every direct-name-matched, literal-valued declaration in this
            # file (module-level simple constants only -- qualnames from the
            # Call-keyword walk are not valid alias targets in Python source
            # anyway, since `NAME2 = NAME1` refers to a bare name).
            literal_by_name = {
                d.name: d.value_mm
                for d in collector.decls
                if d.value_mm is not None and "." not in d.name and " " not in d.name
            }
            _resolve_python_aliases(collector.decls, literal_by_name)
            _propagate_sibling_tier(collector.decls)
            _resolve_selection_aliases(collector.decls)
            decls.extend(collector.decls)
    return decls, errors


# ---------------------------------------------------------------------------
# YAML extractor (line-based -- see module docstring "Indirect YAML
# matching"; a line-based scan is used instead of a line-number-preserving
# YAML parser so direct and indirect matches share one implementation and
# every finding keeps an exact file:line for humans to check).
# ---------------------------------------------------------------------------

_YAML_KV_RE = re.compile(
    r'^(?P<indent>\s*)(?:-\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*'
    r'(?P<value>-?[\d.]+)\s*(?:#\s*(?P<comment>.*))?\s*$'
)
_YAML_ANCESTOR_RE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_\-]*)\s*:\s*$")
_YAML_ID_RE = re.compile(r'^\s*id:\s*["\']?([\w\-]+)["\']?\s*$')

# A numeric field only becomes an *indirect* creepage/clearance candidate
# (metric resolved from nearby prose, not from its own key) if its key is
# itself distance/gap/separation-shaped. Without this restriction, a window
# search around any `clearance_mm: 6.0` sibling line sweeps in every other
# numeric field in the same block -- trace_width, via_diameter, voltage_v,
# loss-function weights, priority tiers -- because the word "clearance"
# appears somewhere within the window, not because that field is itself a
# distance. This was measured directly: an earlier version of this gate
# flagged `voltage_v: 400` as a "clearance value of 400.0mm" for exactly
# this reason. The direct-key path (key itself named creepage/clearance)
# has no such restriction since the key's own name is the evidence.
_INDIRECT_KEY_RE = re.compile(r"^(?:min_|max_|required_)?(distance|gap|separation)(?:_mm)?$", re.IGNORECASE)


def _yaml_window(lines: list[str], idx: int) -> str:
    """Text of the current YAML block only -- lines[idx] plus its sibling
    keys (same or deeper indentation, contiguous, no blank line crossed),
    bounded by the nearest dedent or blank line in each direction.

    A fixed +/-N-line window (the earlier version of this function) reads
    past the block's own boundary into a *sibling* mapping's fields --
    measured directly: with a 6-line window, `FinePitch.clearance: 0.1`
    (netclass_rules.yaml) picked up "working isolation" from the
    `HighVoltage` class five lines above it, tagging an unrelated
    fine-pitch trace-spacing value as tier=working. Bounding the window to
    the block (stop at first line with indentation less than lines[idx]'s,
    or at a blank line) keeps tier/metric context scoped to the one
    declaration it actually describes.
    """
    this_indent = len(lines[idx]) - len(lines[idx].lstrip(" "))
    start = idx
    i = idx - 1
    while i >= 0:
        stripped = lines[i].strip()
        if not stripped:
            break
        indent = len(lines[i]) - len(lines[i].lstrip(" "))
        if indent < this_indent:
            break
        start = i
        i -= 1
    end = idx
    i = idx + 1
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            break
        indent = len(lines[i]) - len(lines[i].lstrip(" "))
        if indent < this_indent:
            break
        end = i
        i += 1
    return " ".join(lines[start : end + 1])


def _yaml_label(lines: list[str], idx: int, key: str) -> str:
    # Prefer a sibling "id:" field within a small window -- pcl-style list
    # items carry one and it is the most human-legible handle.
    lo = max(0, idx - 6)
    hi = min(len(lines), idx + 7)
    for line in lines[lo:hi]:
        m = _YAML_ID_RE.match(line)
        if m:
            return f"[id={m.group(1)}].{key}"
    # Otherwise walk upward for the nearest bare "name:" mapping header at a
    # strictly smaller indent -- gives e.g. "net_class_rules.HighVoltage".
    this_indent = len(lines[idx]) - len(lines[idx].lstrip(" "))
    ancestors: list[str] = []
    cur_indent = this_indent
    i = idx - 1
    while i >= 0 and len(ancestors) < 2:
        m = _YAML_ANCESTOR_RE.match(lines[i])
        if m:
            ind = len(m.group("indent"))
            if ind < cur_indent:
                ancestors.append(m.group("key"))
                cur_indent = ind
        i -= 1
    ancestors.reverse()
    return ".".join([*ancestors, key]) if ancestors else key


def discover_yaml(repo_root: Path) -> tuple[list[Declaration], list[tuple[str, str]]]:
    decls: list[Declaration] = []
    errors: list[tuple[str, str]] = []
    seen_files: set[Path] = set()
    for root_name in SCAN_ROOT_NAMES:
        root = repo_root / root_name
        if not root.is_dir():
            continue
        for pattern in ("*.yaml", "*.yml"):
            for path in sorted(root.rglob(pattern)):
                if _is_noise_path(path.relative_to(repo_root)):
                    continue
                if path in seen_files:
                    continue
                seen_files.add(path)
                rel = str(path.relative_to(repo_root))
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError as exc:
                    errors.append((rel, f"could not read: {exc}"))
                    continue
                # A lightweight parse-validity check (this gate's own
                # findings are line-based, but a file that is not even
                # valid YAML must still fail closed, not silently
                # contribute zero declarations).
                try:
                    import yaml

                    yaml.safe_load(text)
                except Exception as exc:  # noqa: BLE001 - any parse failure fails closed
                    errors.append((rel, f"invalid YAML: {exc}"))
                    continue

                lines = text.splitlines()
                for i, line in enumerate(lines):
                    m = _YAML_KV_RE.match(line)
                    if not m:
                        continue
                    key = m.group("key")
                    try:
                        value = float(m.group("value"))
                    except ValueError:
                        continue
                    comment = m.group("comment") or ""
                    label = _yaml_label(lines, i, key)

                    direct_m = _NAME_TOKEN_RE.search(key)
                    if direct_m:
                        metric = direct_m.group(1).lower()
                        window = _yaml_window(lines, i)
                        tier_text = " ".join(filter(None, [comment, window]))
                        decls.append(
                            Declaration(
                                file=rel,
                                line=i + 1,
                                name=label,
                                metric=metric,
                                metric_confidence="direct",
                                tier=_classify_tier(tier_text),
                                value_mm=value,
                                raw=line.strip(),
                                context=tier_text.strip(),
                            )
                        )
                        continue

                    # Indirect: key itself is not creepage/clearance-named,
                    # but is shaped like a distance/gap/separation field
                    # (e.g. "min_distance_mm") -- only then look for an
                    # explicit justification nearby. See _INDIRECT_KEY_RE's
                    # comment for why this restriction exists.
                    if not _INDIRECT_KEY_RE.match(key):
                        continue
                    window = _yaml_window(lines, i)
                    full_context = " ".join(filter(None, [comment, window]))
                    if not re.search(r"creepage|clearance", full_context, re.IGNORECASE):
                        continue
                    metric, confidence = _resolve_metric(full_context, value)
                    if not metric:
                        continue
                    decls.append(
                        Declaration(
                            file=rel,
                            line=i + 1,
                            name=label,
                            metric=metric,
                            metric_confidence=confidence,
                            tier=_classify_tier(full_context),
                            value_mm=value,
                            raw=line.strip(),
                            context=full_context.strip(),
                        )
                    )
    return decls, errors


# ---------------------------------------------------------------------------
# Aggregation / comparison
# ---------------------------------------------------------------------------

HIGH_CONFIDENCE = frozenset({"direct", "numeric-match", "single-keyword"})


@dataclass
class FamilyResult:
    metric: str
    tier: str
    members: list[Declaration]

    @property
    def distinct_values(self) -> dict[float, list[Declaration]]:
        out: dict[float, list[Declaration]] = {}
        for d in self.members:
            # build_families() only ever adds a Declaration to a family
            # after checking value_mm is not None (unresolved-value members
            # go to a separate list) -- this assert documents that
            # invariant for readers/type-checkers rather than silently
            # coercing None to a bogus 0.0.
            assert d.value_mm is not None
            out.setdefault(round(d.value_mm, 6), []).append(d)
        return out

    @property
    def is_consistent(self) -> bool:
        return len(self.distinct_values) <= 1


def build_families(
    decls: list[Declaration],
) -> tuple[list[FamilyResult], list[Declaration], list[Declaration], list[Declaration], list[Declaration]]:
    """Returns (families, flagged_low_confidence, unresolved_no_value,
    known_blind_spots, declared_not_enforced).

    Only declarations with tier in {reinforced, basic, working}, a resolved
    numeric value, and high-confidence metric classification participate in
    a family comparison. Everything else is reported separately -- never
    silently dropped, never silently force-compared.

    ``known_blind_spots`` holds the (small, closed) set of declarations
    matching ``KNOWN_TIER_MISCLASSIFICATIONS`` -- pulled out of the
    comparable pool entirely (not into ``flagged``, which is for
    low-confidence/unspecified-tier findings still worth a human glance;
    these have already had that glance, 2026-07-29, see the module
    docstring) and reported under their own heading.

    Raises GateError if a registered ``KNOWN_TIER_MISCLASSIFICATIONS`` entry
    IS found among ``decls`` but no longer classifies as tier ==
    "reinforced" -- that means the override no longer applies to what it
    claims to (the classifier's own behaviour or the site's own comment
    text changed) and must be re-reviewed rather than silently kept. The
    opposite case -- an entry simply not present at all in a given run
    (e.g. a synthetic test tree, a --repo-root subset, or a real tree
    predating the netclass split this override targets, such as
    ``origin/main``) is deliberately NOT an error: this override only ever
    narrows an already-matched declaration's classification, so a run
    where it never matches anything is identical to a run without the
    override at all -- safe by construction, not silent (the excluded
    declarations simply don't exist in that run to be silently dropped).
    Only a *matched-but-wrong* override is a correctness risk worth failing
    on. See that constant's own comment for the rest of this reasoning.

    ``declared_not_enforced`` holds declarations ``_resolve_selection_aliases``
    (Python discovery) marked as an unselected sibling of some same-file
    selection alias's target -- e.g. ``HV_CREEPAGE_PD3_MM`` when
    ``HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD2_MM`` selects the other
    candidate. Pulled out of the comparable pool the same way
    ``known_blind_spots`` is (a live, discovered declaration, just not one
    to cross-compare) and reported under its own heading, each entry naming
    the value and site that IS enforced instead.

    Self-verification for that mechanism: for every ``declared_not_enforced``
    entry, the site its alias resolved to (``enforced_site``) must actually
    appear as a member of that same (metric, tier) family in ``comparable``.
    If it does not -- e.g. a refactor stripped the enforced target's own
    tier/metric context so it now lands in ``flagged`` instead -- the
    selection-alias mechanism has silently stopped keeping the enforced
    value in comparison at all, which is worse than never having special-
    cased it (requirement: the enforced value must still participate in its
    family). That is raised as a GateError, not silently accepted, exactly
    as a stale ``KNOWN_TIER_MISCLASSIFICATIONS`` entry is."""
    comparable: dict[tuple[str, str], list[Declaration]] = {}
    flagged: list[Declaration] = []
    unresolved: list[Declaration] = []
    known_blind_spots: list[Declaration] = []
    declared_not_enforced: list[Declaration] = []

    for d in decls:
        if d.value_mm is None:
            unresolved.append(d)
            continue
        if d.declared_not_enforced:
            # A live declaration, deliberately excluded from cross-file
            # comparison because a same-file selection alias named a
            # different sibling as enforced -- see
            # _resolve_selection_aliases. Reported, not dropped.
            declared_not_enforced.append(d)
            continue
        key = (d.file, d.name)
        if key in KNOWN_TIER_MISCLASSIFICATIONS:
            if d.tier != "reinforced":
                raise GateError(
                    f"KNOWN_TIER_MISCLASSIFICATIONS entry {key} no longer classifies as "
                    f"tier='reinforced' (now tier={d.tier!r}) -- the override is stale and "
                    "must be re-reviewed, not silently kept (see check_creepage_clearance_drift.py's "
                    "KNOWN_TIER_MISCLASSIFICATIONS docstring)"
                )
            known_blind_spots.append(d)
            continue
        if d.tier == "unspecified":
            flagged.append(d)
            continue
        if d.metric_confidence not in HIGH_CONFIDENCE:
            flagged.append(d)
            continue
        if not d.metric:
            flagged.append(d)
            continue
        comparable.setdefault((d.metric, d.tier), []).append(d)

    for d in declared_not_enforced:
        family_members = comparable.get((d.metric, d.tier), [])
        if not any(m.site == d.enforced_site for m in family_members):
            raise GateError(
                f"selection alias {d.enforcing_alias!r} in {d.file} resolves {d.site} to "
                f"enforced site {d.enforced_site!r} (value {d.enforced_value_mm}mm), but that "
                "site does not participate in a comparable (metric, tier) family -- the "
                "selection-alias mechanism has silently stopped keeping the enforced value in "
                "comparison (e.g. a refactor stripped its own tier/metric context). This must "
                "be re-reviewed, not silently accepted (see "
                "check_creepage_clearance_drift.py's _resolve_selection_aliases docstring)."
            )

    families = [FamilyResult(metric=m, tier=t, members=members) for (m, t), members in sorted(comparable.items())]
    return families, flagged, unresolved, known_blind_spots, declared_not_enforced


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run(
    repo_root: Path,
) -> tuple[
    str, Report, list[FamilyResult], list[Declaration], list[Declaration], list[Declaration], list[Declaration]
]:
    for name in SCAN_ROOT_NAMES:
        if not (repo_root / name).is_dir():
            raise GateError(f"scan root missing: {repo_root / name}")

    report = Report()

    ato_decls = discover_ato(repo_root)
    py_decls, py_errors = discover_python(repo_root)
    yaml_decls, yaml_errors = discover_yaml(repo_root)

    report.declarations = ato_decls + py_decls + yaml_decls
    report.parse_errors = py_errors + yaml_errors
    report.files_scanned = len(
        {d.file for d in report.declarations} | {f for f, _ in report.parse_errors}
    )

    if not report.declarations and not report.parse_errors:
        raise GateError(
            "discovery found zero creepage/clearance declarations anywhere under "
            f"{', '.join(SCAN_ROOT_NAMES)} -- the check did not actually run "
            "(anti-vacuous-truth: this is a gate error, not '0 violations')"
        )

    families, flagged, unresolved, known_blind_spots, declared_not_enforced = build_families(report.declarations)

    state = "clean"
    if report.parse_errors:
        state = "violation"
    for fam in families:
        if not fam.is_consistent:
            state = "violation"

    return state, report, families, flagged, unresolved, known_blind_spots, declared_not_enforced


def _print_report(
    state: str,
    report: Report,
    families: list[FamilyResult],
    flagged: list[Declaration],
    unresolved: list[Declaration],
    known_blind_spots: list[Declaration],
    declared_not_enforced: list[Declaration],
    repo_root: Path,
) -> None:
    print(f"Repo root: {repo_root}")
    print(
        f"Files contributing a finding: {report.files_scanned}. "
        f"Declarations discovered: {len(report.declarations)}. "
        f"Parse errors: {len(report.parse_errors)}. "
        f"Comparable families: {len(families)} "
        f"(members: {sum(len(f.members) for f in families)}). "
        f"Flagged low-confidence/unspecified-tier: {len(flagged)}. "
        f"Unresolved (non-literal) values: {len(unresolved)}. "
        f"Known blind spots (reviewed, excluded from comparison): {len(known_blind_spots)}. "
        f"Declared but not enforced (superseded by a same-file selection alias): "
        f"{len(declared_not_enforced)}."
    )

    if report.parse_errors:
        print(f"\n=== PARSE ERRORS: {len(report.parse_errors)} ===")
        for name, reason in report.parse_errors:
            print(f"  FAIL: {name}: {reason}")

    print(f"\n=== FAMILIES: {len(families)} ===")
    violations = 0
    for fam in families:
        tag = "OK" if fam.is_consistent else "MISMATCH"
        if not fam.is_consistent:
            violations += 1
        print(f"\n  [{fam.metric}/{fam.tier}] {tag} -- {len(fam.members)} declaration(s)")
        for value, members in sorted(fam.distinct_values.items()):
            print(f"    {value}mm:")
            for m in members:
                print(f"      {m.site}")

    if flagged:
        print(f"\n=== FLAGGED (needs human classification): {len(flagged)} ===")
        for d in flagged:
            reason = "unspecified tier" if d.tier == "unspecified" else f"low-confidence metric ({d.metric_confidence})"
            print(f"  {d.site}: metric={d.metric or '?'} value={d.value_mm}mm ({reason})")

    if unresolved:
        print(f"\n=== UNRESOLVED (non-literal expression, not compared): {len(unresolved)} ===")
        for d in unresolved:
            print(f"  {d.site}: {d.raw}")

    if known_blind_spots:
        print(
            f"\n=== KNOWN BLIND SPOTS (tier misclassification, human-reviewed "
            f"2026-07-29, excluded from comparison): {len(known_blind_spots)} ==="
        )
        for d in known_blind_spots:
            print(
                f"  {d.site}: metric={d.metric} tier={d.tier} value={d.value_mm}mm -- "
                "own value is an intra-class routing spacing, not the barrier-crossing "
                "figure its 'because' text mentions; see KNOWN_TIER_MISCLASSIFICATIONS "
                "in this gate's source"
            )

    if declared_not_enforced:
        print(
            f"\n=== DECLARED BUT NOT ENFORCED (unselected candidate of a same-file "
            f"selection alias): {len(declared_not_enforced)} ==="
        )
        for d in declared_not_enforced:
            print(
                f"  {d.site}: metric={d.metric} tier={d.tier} value={d.value_mm}mm -- "
                f"NOT enforced; {d.enforcing_alias!r} in {d.file} selects "
                f"{d.enforced_site} = {d.enforced_value_mm}mm instead"
            )

    gh = get_github_summary_path()
    if state == "clean":
        msg = (
            f"PASSED -- {len(report.declarations)} declaration(s) discovered across "
            f"{report.files_scanned} file(s); {len(families)} comparable famil(y/ies), "
            f"0 mismatched. {len(flagged)} flagged for human classification, "
            f"{len(unresolved)} unresolved, {len(known_blind_spots)} known blind spot(s), "
            f"{len(declared_not_enforced)} declared-but-not-enforced candidate(s)."
        )
        print(f"\n{msg}")
        if gh:
            with open(gh, "a") as f:
                f.write(f"### Creepage/Clearance Drift Gate -- PASSED\n{msg}\n")
        return

    msg_parts = []
    if report.parse_errors:
        msg_parts.append(f"{len(report.parse_errors)} parse error(s)")
    if violations:
        msg_parts.append(f"{violations} family/families with mismatched values")
    print(f"\nFAILED -- {', '.join(msg_parts)}")
    if gh:
        with open(gh, "a") as f:
            f.write(f"### Creepage/Clearance Drift Gate -- FAILED\n{', '.join(msg_parts)}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args()

    repo_root = args.repo_root or find_repo_root()

    try:
        state, report, families, flagged, unresolved, known_blind_spots, declared_not_enforced = run(repo_root)
    except GateError as exc:
        print("=== CREEPAGE/CLEARANCE DRIFT GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. The gate could "
            "not run a trustworthy check.",
            file=sys.stderr,
        )
        gh = get_github_summary_path()
        if gh:
            with open(gh, "a") as f:
                f.write(f"### Creepage/Clearance Drift Gate -- GATE ERROR\n{exc}\n")
        sys.exit(EXIT_GATE_ERROR)

    _print_report(state, report, families, flagged, unresolved, known_blind_spots, declared_not_enforced, repo_root)

    sys.exit(EXIT_OK if state == "clean" else EXIT_VIOLATION)


if __name__ == "__main__":
    main()
