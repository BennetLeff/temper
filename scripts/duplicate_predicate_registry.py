"""Duplicate-predicate registry — the SSOT for which duplication is
accidental (consolidated, must not regrow a copy) vs. deliberate (a pinned
oracle or an intentional independent cross-check, must stay duplicated).

Why this file exists
---------------------
Four defect families investigated on 2026-08-13
(``docs/evidence/2026-08-13-defect-multiplier-duplication-audit.md``) share
one shape: the same logic independently reimplemented in several places, so
one defect becomes N. In each case the fix required finding every copy, and
in each case at least one copy was initially missed. A test suite proves a
*known* copy behaves correctly; it does not stop a *new* copy from being
written. This registry plus ``check_duplicate_predicates.py`` is the
structural backstop: every family that has been consolidated onto one
implementation is registered here with a scan that fails closed if an
un-delegating copy of its def name reappears anywhere in the scanned
surface — named, not just counted.

Two registries, deliberately kept apart (mirrors
``gate_input_registry.py``'s gates/ci_scripts/tracked_findings split):

1. ``CONSOLIDATED_FAMILIES`` — accidental duplication that has been fixed:
   one shared implementation (the SSOT), with every other historical copy
   now either deleted or reduced to a thin delegating shim. Guarded by
   :func:`scan_family`: any definition of the family's name found outside
   the SSOT module, in the family's scan path, whose body does not call
   the SSOT, is a violation — a new copy, or a regression back to an
   inline reimplementation.

2. ``OPEN_FINDINGS`` — duplication that has been *identified* as
   accidental (not a pinned oracle, not an intentional cross-check) but is
   **not yet consolidated**. Registered so the finding survives past the
   PR that found it, with an explicit reason it was left alone (usually:
   touches creepage/clearance/DRC-adjacent Rust geometry, out of the
   hard-constraint-safe surface for a dedup-only change). These are NOT
   gated — there is nothing to protect yet, only something to not forget.

This registry is deliberately silent about the file-level duplication that
IS load-bearing: the ~167 ``_*_py_oracle.py`` pins under ``packages/*/tests``
already have their own registry and fail-closed gate
(``scripts/oracle_hashes.json`` / ``scripts/check_oracle_hashes.py``,
decision 2026-08-06). Re-registering them here would be a second, competing
SSOT for the same fact — the anti-pattern this whole file exists to avoid.
``DELIBERATE_DUPLICATE_REGISTRIES`` below just points at that existing
registry by name, per this repo's "follow the existing convention, don't
invent a new file format" rule.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.repo import find_repo_root  # noqa: E402


@dataclass(frozen=True)
class ConsolidatedFamily:
    """An accidental-duplication family that has been consolidated onto a
    single SSOT implementation.

    Attributes:
        name: Registry key (also used in test/CLI output).
        ssot: ``"module:function_or_Class.method"`` — the canonical
            implementation every other copy must delegate to.
        ssot_file: Repo-relative path of the module that defines ``ssot``.
            Excluded from the "must delegate" scan (it IS the
            implementation, so it may legitimately not call itself).
        def_names: Function/method names that have historically carried
            independent copies of this predicate (e.g. a private
            ``_foo`` alias alongside the public ``foo``).
        delegate_call_name: The name that must appear as a ``Call`` inside
            a matching definition's body for it to count as a legitimate
            thin delegate rather than an independent reimplementation.
        scan_paths: Repo-relative files or directories to scan. Kept
            explicit (not "the whole repo") so the gate's coverage is a
            visible, reviewable decision — mirrors
            ``check_no_raw_rotation_trig.py``'s ``GUARDED_FILES`` and its
            "an enumerated list ... is directly falsifiable" rationale.
        evidence: Where this family's incident/consolidation is documented.
        consolidated_on: ISO date of the consolidation.
    """

    name: str
    ssot: str
    ssot_file: str
    def_names: tuple[str, ...]
    delegate_call_name: str
    scan_paths: tuple[str, ...]
    evidence: str
    consolidated_on: str


@dataclass(frozen=True)
class OpenFinding:
    """Identified accidental duplication, NOT yet consolidated.

    Attributes:
        name: Registry key.
        sites: ``"file:line"`` or ``"module:function"`` locations of the
            known independent copies.
        diverged: True when the copies are already known to behave
            differently for the same input (the highest-priority shape —
            one of them is wrong today).
        why_not_fixed: Why this PR did not consolidate it (usually a hard
            constraint: touches creepage/clearance/DRC-safety-adjacent
            code, which this change explicitly must not touch).
        evidence: Where this finding is documented.
    """

    name: str
    sites: tuple[str, ...]
    diverged: bool
    why_not_fixed: str
    evidence: str


# --- Consolidated (accidental, now fixed, gated) --------------------------

CONSOLIDATED_FAMILIES: tuple[ConsolidatedFamily, ...] = (
    ConsolidatedFamily(
        name="net_pad_positions",
        ssot="temper_placer.core.pin_geometry:net_pad_positions",
        ssot_file="packages/temper-placer/src/temper_placer/core/pin_geometry.py",
        def_names=("_net_pad_positions", "net_pad_positions"),
        delegate_call_name="net_pad_positions",
        scan_paths=(
            "packages/temper-placer/src/temper_placer/router_v6/_pipeline_grid.py",
            "packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py",
            "packages/temper-placer/src/temper_placer/router_v6/bundle_analyzer.py",
            "packages/temper-placer/src/temper_placer/router_v6/capacity_check.py",
        ),
        evidence="docs/evidence/2026-08-13-defect-multiplier-duplication-audit.md",
        consolidated_on="2026-08-13",
    ),
    ConsolidatedFamily(
        name="thermal_fdm_point_to_segment_distance",
        # There is no delegating shim to require here — the dead copy was
        # deleted outright (no live call site existed to redirect; see the
        # NOTE left in thermal_fdm.py). The SSOT for THIS family is
        # therefore "no local definition at all"; ``delegate_call_name``
        # names the module-level marker (the family's own former def name)
        # so the scan still fires if the exact dead shape reappears.
        ssot="temper_geometry:point_to_segment_distance_py",
        ssot_file="packages/temper-geometry/src/creepage_check.rs",
        def_names=("_point_to_segment_distance",),
        delegate_call_name="point_to_segment_distance_py",
        scan_paths=(
            "packages/temper-placer/src/temper_placer/physics/thermal_fdm.py",
        ),
        evidence="docs/evidence/2026-08-13-defect-multiplier-duplication-audit.md",
        consolidated_on="2026-08-13",
    ),
)


# --- Deliberate (must stay duplicated) -------------------------------------
#
# Pointer registries, not a re-implementation of them. Each entry names an
# EXISTING registry/gate elsewhere in the repo that is the actual SSOT for
# that deliberate-duplication bucket, per this repo's convention of one
# registry per fact, never two.

DELIBERATE_DUPLICATE_REGISTRIES: tuple[dict[str, str], ...] = (
    {
        "bucket": "pinned python oracles (Rust-port differential testing)",
        "registry": "scripts/oracle_hashes.json",
        "gate": "scripts/check_oracle_hashes.py",
        "count_at_audit": "167 _*_py_oracle.py files under packages/*/tests (2026-08-13)",
        "why_deliberate": (
            "each is a byte-pinned pre-migration Python implementation the "
            "Wave-4 differential suites compare a Rust port against; "
            "consolidating a pin with its Rust counterpart destroys the "
            "independent-implementation property the differential test "
            "relies on (decision 2026-08-06, issues #754 P2-2, #758)."
        ),
        "shared_bug_risk_tracked": (
            "PARTIAL — check_oracle_hashes.py proves the oracle file's "
            "*content* has not silently drifted from its pinned hash; it "
            "does not and cannot prove the oracle and its Rust port do not "
            "share the same bug at the moment the pin was taken (the #1179 "
            "shape: fp_circle dropped from bounds in both arms, already "
            "being fixed on branch fix/circle-poly-bounds — not "
            "re-fixed here). That risk is per-oracle and requires a human "
            "audit of each pin's original derivation, not a mechanical "
            "gate. Not attempted here; flagged, not assumed away, per this "
            "file's own brief. A CONFIRMED, VERIFIED gap in this registry's "
            "own coverage (2026-08-13): its glob "
            "(update_oracle_hashes.py:ORACLE_GLOB = '_*_py_oracle.py') only "
            "matches FILES named exactly '..._py_oracle.py'. "
            "packages/temper-placer/tests/io/_parse_engine_py_oracle/ is a "
            "PACKAGE (directory) of 8 files (kicad_parser.py, "
            "_parse_nets.py, _kicad_types.py, kicad_metadata.py, "
            "_parse_zones.py, _parse_modules.py, __init__.py, "
            "_parse_board.py, _parse_tracks.py) pinning the KiCad parse "
            "engine's pre-migration reference -- none of them individually "
            "match the glob, so the entire package is invisible to "
            "check_oracle_hashes.py's drift detection. This is exactly the "
            "kind of gap the #1179 finding warns about: a differential "
            "test whose reference arm can drift silently. NOT fixed in "
            "this PR (widening a sibling gate's discovery glob is outside "
            "duplicate-predicate scope and needs its own verification that "
            "no other multi-file oracle package exists) -- flagged as the "
            "single highest-priority follow-up this audit found."
        ),
    },
    {
        "bucket": "fixed_copper.rs's own point_segment_distance (renamed copy)",
        "registry": "packages/temper-geometry/src/fixed_copper.rs (module header comment)",
        "gate": "scripts/oracle_hashes.json / scripts/check_oracle_hashes.py (protects its Python source, _fixed_copper_py_oracle.py, commit-pinned)",
        "count_at_audit": "1 Rust kernel, function named point_segment_distance (no underscore between point/segment -- a rename that makes name-based duplicate search miss it, exactly the way a name search for the pad bug initially missed independent copies)",
        "why_deliberate": (
            "The module's own header states this explicitly: '`_point_segment_distance` "
            "in THIS file has ITS OWN degenerate check (`dx == 0.0 and dy == 0.0`, exact "
            "equality) -- deliberately NOT the same function as `creepage_check.rs`/"
            "`drc_constraints_geometry.rs`'s point-to-segment distance (those use an "
            "epsilon threshold on `seg_len_sq`). The two references genuinely disagree "
            "at the boundary; a \"de-duplication\" that reused one for the other would "
            "be a silent behaviour change.' This is a verbatim transcription of a "
            "commit-pinned Python oracle (_fixed_copper_py_oracle.py) -- textbook "
            "deliberate duplication, correctly self-documented at the point of risk. "
            "Registered here specifically so it is NOT mistaken for one of the "
            "undocumented, accidental point_to_segment_distance divergences in "
            "OPEN_FINDINGS below."
        ),
        "shared_bug_risk_tracked": (
            "LOW — the divergence is explicit, load-bearing, and explained inline; "
            "this is the opposite of the #1179 shape (that shape is an UNDOCUMENTED "
            "shared bug masquerading as agreement; this is a DOCUMENTED, deliberate "
            "disagreement)."
        ),
    },
)


# --- Identified, accidental, NOT consolidated (flagged, not fixed) --------

OPEN_FINDINGS: tuple[OpenFinding, ...] = (
    OpenFinding(
        name="point_to_segment_distance",
        sites=(
            "ACCIDENTAL, undiverged-vs-undocumented (the concern, ranked #1):",
            "packages/temper-geometry/src/creepage_check.rs:61 (canonical kernel per issue #987's own execution doc; point_to_segment_distance_py binding)",
            "packages/temper-geometry/src/drc_constraints_geometry.rs:107 (own kernel, seg_len_sq < 1e-10, no documented rationale for differing; drc_point_to_segment_distance_py binding, called by router_v6/constraints_geometry.py -- DRC-adjacent)",
            "packages/temper-geometry/src/geometry_kernels.rs:100 (own native kernel, len2 < 1e-12, no documented rationale for differing; Python binding retired with the orphaned requirements/validators/_geometry.py shim)",
            "packages/temper-constraint-compiler/src/constraints/mod.rs:324 (own kernel, exact ab_len_sq == 0.0, no documented rationale for differing; constraint_point_to_segment_distance binding, called by constraints/compiler.py)",
            "packages/temper-rust-router-core/src/pruning.rs:74 (own kernel, not py-bound, not compared)",
            "6+ pinned Python oracles (DELIBERATE, not a concern -- e.g. "
            "_placement_validation_run_py_oracle.py, "
            "_zone_aware_slot_generation_py_oracle.py, _drc_leaf_py_oracle.py, "
            "constraints/_compiler_py_oracle.py, constraints/_reporter_py_oracle.py, "
            "_zone_aware_slot_generation_run_py_oracle.py -- registered in "
            "scripts/oracle_hashes.json, gated by check_oracle_hashes.py)",
            "packages/temper-geometry/src/fixed_copper.rs::point_segment_distance "
            "(DELIBERATE, renamed -- no underscore between point/segment, which is "
            "WHY a name-based sweep for this family initially missed it; see "
            "DELIBERATE_DUPLICATE_REGISTRIES for its explicitly self-documented "
            "divergence rationale -- NOT part of the accidental cluster above)",
        ),
        diverged=True,
        why_not_fixed=(
            "Issue #987 (docs/evidence/2026-08-11-point-to-segment-distance-dedupe-execution.md) "
            "already consolidated 3 Wave-4 Python shims onto the canonical "
            "temper-geometry kernel, but (at least) 4 independent, UNDOCUMENTED "
            "Rust kernel bodies remain beyond the canonical one -- confirmed "
            "each with a DIFFERENT degenerate-segment epsilon threshold "
            "(1e-10, 1e-12, exact ==0.0, and the canonical's "
            "denom==0.0-or-non-finite check), none of them carrying the kind "
            "of explicit divergence rationale fixed_copper.rs's own header "
            "gives for ITS deliberately-different copy -- a real, "
            "demonstrable divergence for segments whose squared length falls "
            "between two thresholds, not just a style difference, and not "
            "shown to be intentional. Two of the accidental call sites are "
            "creepage/DRC-adjacent (constraints_geometry.py feeds router_v6 "
            "DRC; _geometry.py is under requirements/validators/, the "
            "REQ-SAFE package). Consolidating Rust geometry kernels that "
            "feed clearance/creepage computation is explicitly out of scope "
            "for this change (hard constraint: do not touch "
            "clearance/creepage/safety values) — flagged prominently "
            "instead, per this task's Part 1.2. A safe follow-up would "
            "differentially test all 4 against the canonical kernel across "
            "the degenerate-segment boundary BEFORE touching any of them, "
            "the same falsification step #987's own spike did for the 3 it "
            "already merged."
        ),
        evidence="docs/evidence/2026-08-13-defect-multiplier-duplication-audit.md",
    ),
    OpenFinding(
        name="kw_boundary_match_py (Rust symbol shadowing, not just duplication)",
        sites=(
            "packages/temper-geometry/src/trace_width_assignment.rs:90 (registered first, lib.rs:343 -- SHADOWED, effectively dead)",
            "packages/temper-geometry/src/via_clearance.rs:410 (registered second, lib.rs:346 -- WINS, this is what _tg.kw_boundary_match_py actually resolves to)",
        ),
        diverged=False,
        why_not_fixed=(
            "Confirmed via lib.rs registration order (trace_width_assignment::register "
            "at line 343, via_clearance::register at line 346 -- pyo3's "
            "m.add_function silently overwrites, last registration wins): two "
            "independent Rust implementations of the SAME predicate are "
            "registered under the IDENTICAL pyo3 symbol name in the same "
            "module, so one is live production code and one is unreachable "
            "dead code that nothing will ever call, yet still compiles, "
            "still has its own unit tests (giving false confidence that it "
            "is exercised), and would SILENTLY become live if via_clearance's "
            "registration were ever reordered or removed. Both were read and "
            "found behaviorally equivalent for the documented "
            "alphanumeric-keyword contract (verified this audit, not a "
            "residual concern re: correctness today) -- the risk is entirely "
            "in the shadowing itself, not a current behavior divergence. Not "
            "fixed here: this is a Rust-level dead-code/registration bug, not "
            "a Python-AST-scannable duplicate-predicate case, and this "
            "audit's gate (check_duplicate_predicates.py) only scans Python. "
            "A real fix (delete one, keep the other, verify no differential "
            "test pins the dead one specifically) needs its own Rust "
            "rebuild+test cycle -- flagged, not attempted, per this task's "
            "time-boxing instruction."
        ),
        evidence="docs/evidence/2026-08-13-defect-multiplier-duplication-audit.md",
    ),
    OpenFinding(
        name="get_rules_for_net",
        sites=(
            "packages/temper-placer/src/temper_placer/router_v6/net_batching.py:709",
            "packages/temper-placer/src/temper_placer/router_v6/stage0_data.py:106",
        ),
        diverged=False,
        why_not_fixed=(
            "Two independently-maintained net-name -> NetClassRules "
            "resolvers found by name-frequency sweep; NOT byte-compared "
            "against each other in this PR (time-boxed). Net-classification "
            "is exactly the shape of PR #1162/#1174's hyphen-boundary "
            "family (a net-name keyword match feeding netclass -> creepage "
            "rules), so a divergence here would be high-value and this "
            "should be the first follow-up, not deprioritized."
        ),
        evidence="docs/evidence/2026-08-13-defect-multiplier-duplication-audit.md",
    ),
    OpenFinding(
        name="hv_keyword_boundary_match (deliberately re-diverged, registry was stale)",
        sites=(
            "packages/temper-placer/src/temper_placer/router_v6/clearance_check.py:857 "
            "(_is_hv_keyword_match -- boundary is (?:^|[_-])kw(?:$|[\\d_-]), BOTH "
            "'_' and '-' are boundary characters)",
            "packages/temper-geometry/src/via_clearance.rs:208 (kw_boundary_match_py, "
            "via word_bounded at :168 -- boundary is (?:^|_)kw(?:$|[\\d_]), '_' ONLY, "
            "'-' is never a boundary character)",
            "packages/temper-placer/src/temper_placer/router_v6/clearance_engine.py:144 "
            "(_kw_boundary_match -- thin delegate to kw_boundary_match_py above, so it "
            "inherits the '_'-only boundary)",
        ),
        diverged=True,
        why_not_fixed=(
            "2026-08-17 (agent/priority1-gate-inductance, PR #1304 follow-up): "
            "check_duplicate_predicates.py had a live violation "
            "(hv_keyword_boundary_match) asserting clearance_check.py's "
            "_is_hv_keyword_match must delegate to kw_boundary_match_py. Investigated: "
            "the registry entry was consolidated 2026-08-13, but a SAME-DAY fix "
            "(the 'Family C' hyphen-boundary defect -- clearance_check.py:7's own "
            "bug-history docstring) deliberately RE-diverged it, and the registry was "
            "never reconciled afterward. Both sides are independently correct, "
            "deliberate, and already documented in their own module docstrings, not a "
            "fresh editorial call: (1) _is_hv_keyword_match MUST use the wider "
            "'_'/'-' boundary -- 85 of 162 real net names on the production board mix "
            "'-' and '_' as word separators (atopile's compiled net names), and every "
            "one was invisible to the '_'-only boundary whenever the matching keyword "
            "sat on the hyphen side (a real under-classification defect, the dangerous "
            "direction for HV/LV creepage rule selection -- fixed by widening, with the "
            "resulting 14-net SELV over-match caught and mitigated by "
            "_SELV_LINE_NET_OVERRIDES, checked first). (2) kw_boundary_match_py MUST "
            "stay '_'-only -- clearance_engine.py:50's own 'Bug history (2026-08-13), "
            "URGENT -- audited, deliberately NOT widened' docstring records that this "
            "kernel's only callers (_kw_boundary_match, _net_class_to_voltage_class) "
            "receive already-classified short net-CLASS labels ('HV', 'Signal', ...) "
            "produced by clearance_check._classify_net_class, never raw hyphenated net "
            "NAMES directly -- board-wide simulation of all 162 real net names "
            "confirmed zero live exposure through this narrower path, and widening it "
            "would break test_via_clearance_tier2_rust_differential.py's byte-verbatim "
            "oracle pin (_ORACLE_PIN_SHA = 'f1ffc013') with no documented safe update "
            "path. RESOLVED (registry only, no logic touched): removed the "
            "hv_keyword_boundary_match ConsolidatedFamily -- clearance_check.py's copy "
            "is a deliberate, permanent, DIFFERENT-contract implementation, not an "
            "accidental reimplementation of the same predicate that regressed away "
            "from delegating, so 'must call kw_boundary_match_py' was never the right "
            "check for it. Recorded here instead so the divergence stays visible. If a "
            "single shared implementation is ever wanted, that is a genuine new safety "
            "call for a human owner: widening kw_boundary_match_py needs the oracle-pin "
            "update this fix did not have a safe path for, and narrowing "
            "_is_hv_keyword_match back down would reintroduce the confirmed Family C "
            "under-classification on real board net names -- neither side should move "
            "without that decision being made explicitly, not as a side effect of a "
            "registry-consolidation gate."
        ),
        evidence=(
            "docs/evidence/2026-08-13-hyphen-boundary-clearance-creepage-defect.md; "
            "docs/evidence/2026-08-17-gate-inductance-and-unwired-kernels.md"
        ),
    ),
    OpenFinding(
        name="load_allowlist (CI gate config loaders)",
        sites=(
            "14 near-identical loaders across scripts/check_*.py "
            "(each gate hand-rolls its own YAML/JSON allowlist reader with "
            "a bespoke per-script dataclass shape)",
        ),
        diverged=False,
        why_not_fixed=(
            "Boilerplate duplication in CI-gate config loading, not "
            "physics/geometry/safety logic — low blast radius if one copy "
            "is subtly wrong (worst case: a gate under- or over-allowlists "
            "its own findings, which is visible in that gate's own CI "
            "output). scripts/_lib/gate_allowlist.py already exists as a "
            "shared-lib candidate; migrating 14 call sites onto it is real "
            "but mechanical follow-up work, scoped out of this PR."
        ),
        evidence="docs/evidence/2026-08-13-defect-multiplier-duplication-audit.md",
    ),
)


# --- Scanning ----------------------------------------------------------------


class RegistryError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


@dataclass(frozen=True)
class Violation:
    family: str
    path: str
    lineno: int
    detail: str


def _calls_name(node: ast.AST, name: str) -> bool:
    """True if any ``Call`` inside *node* invokes something literally named
    *name* (bare ``name(...)`` or qualified ``x.name(...)``)."""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name) and func.id == name:
            return True
        if isinstance(func, ast.Attribute) and func.attr == name:
            return True
    return False


def scan_family(family: ConsolidatedFamily, repo_root: Path) -> list[Violation]:
    """Scan ``family.scan_paths`` for a definition of any ``def_names``
    whose body does not call ``delegate_call_name`` anywhere -- i.e. an
    independent reimplementation rather than a thin delegating shim.

    The SSOT file itself is skipped (it legitimately does not call its own
    name via this pattern) when it appears in ``scan_paths``.
    """
    ssot_path = repo_root / family.ssot_file
    if not ssot_path.is_file():
        raise RegistryError(
            f"family '{family.name}': ssot_file '{family.ssot_file}' does not exist"
        )
    if ssot_path.suffix == ".py":
        try:
            ssot_tree = ast.parse(ssot_path.read_text(), filename=str(ssot_path))
        except SyntaxError as e:
            raise RegistryError(f"family '{family.name}': ssot_file unparseable: {e}") from None
        ssot_func_name = family.ssot.rpartition(":")[2].rpartition(".")[2]
        defines_ssot = any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == ssot_func_name
            for n in ast.walk(ssot_tree)
        )
        if not defines_ssot:
            raise RegistryError(
                f"family '{family.name}': ssot_file '{family.ssot_file}' does not define "
                f"'{ssot_func_name}' -- registry has drifted from the SSOT it names"
            )
    # A Rust SSOT (ssot_file ends .rs) is not parsed here; its presence on
    # disk is the only mechanical check available from Python.

    if not family.scan_paths:
        raise RegistryError(f"family '{family.name}': scan_paths is empty -- vacuous scan")

    violations: list[Violation] = []
    for rel in family.scan_paths:
        path = repo_root / rel
        if not path.is_file():
            raise RegistryError(
                f"family '{family.name}': scan path '{rel}' does not exist -- "
                "a rename/move must update this registry, not silently shrink its coverage"
            )
        if rel == family.ssot_file:
            continue
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError as e:
            raise RegistryError(f"family '{family.name}': '{rel}' unparseable: {e}") from None
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in family.def_names:
                continue
            if _calls_name(node, family.delegate_call_name):
                continue
            violations.append(
                Violation(
                    family=family.name,
                    path=rel,
                    lineno=node.lineno,
                    detail=(
                        f"def {node.name}(...) does not call "
                        f"'{family.delegate_call_name}' anywhere in its body -- "
                        f"looks like an independent reimplementation of the "
                        f"'{family.name}' family, not a delegating shim to "
                        f"{family.ssot}"
                    ),
                )
            )
    return violations


def scan_all(repo_root: Path | None = None) -> list[Violation]:
    root = repo_root if repo_root is not None else find_repo_root()
    violations: list[Violation] = []
    for family in CONSOLIDATED_FAMILIES:
        violations.extend(scan_family(family, root))
    return violations
