"""Drift test: every test_*.py file is either CI-referenced or tracked.

Why this exists
----------------
CI in this repo enumerates test files/directories **by name** in per-group
`run:` steps rather than sweeping a whole tree. A file nobody remembers to
add to a job's argument list silently never runs -- indistinguishable from a
suite that passes, because nothing ever asserts it ran anything (see
`scripts/pytest_guard.py`'s own docstring for the sibling defect: a *stale*
name that got deleted, which aborts pytest before it collects anything else
in that invocation too). Two confirmed instances of the "forgotten name"
shape existed before this test:

  * `Invariant tests (router_v6 group 2)` named a deleted file
    (`tests/router_v6/test_wave4_numba_astar.py`), so the whole group
    collected zero tests while reporting green.
  * The firmware suite registered only 11 of 20 test binaries with
    `add_test()`; CI ran 70 of 385 assertions.

`docs/evidence/2026-08-07-router-v6-ci-name-enumeration-gap.md` re-derives
the router_v6 instance from scratch: 49 of router_v6's `test_*.py` files
(22 of them `*_rust_differential.py` -- the R19 pinned-oracle differentials
that justify every completed Rust migration) are referenced by no job, and
that doc actually ran all 49 to find out what running them would do. This
test is the structural fix for the class of defect, not just router_v6's
instance of it: it fails when a NEW test file goes unreferenced, or when a
NEW workflow reference points at a file that doesn't exist, rather than
requiring someone to remember to re-audit the whole tree by hand.

This is the same shape as `test_gate_input_registry.py`'s
`test_every_invoked_ci_gate_script_is_registered` (U4), which already does
this for gate *scripts*; this module does it for test *files*.

Scope note: this test's own coverage computation must itself understand
whole-directory pytest arguments (e.g. `tests/validation/`, the directory
this very file lives in) -- an earlier draft of the underlying survey didn't,
and consequently misclassified every file under `tests/validation/`,
including this one, as "unreferenced." Fixed before landing; see the doc's
§1 for the full account.

2026-08-07 follow-up (docs/evidence/2026-08-07-full-tree-ci-name-enumeration-triage.md):
`_all_test_files()`/`_referenced_files_and_dirs()` below already scan the
*entire* `packages/temper-placer/tests/` tree, not just `router_v6/` -- the
169-entry baseline snapshot this module loads (`ci_test_file_registration_baseline.txt`)
is that full-tree coverage in action, not a router_v6-only mechanism. This
follow-up actually ran all 169 of those files (all 13 pyo3/maturin Rust
extensions built fresh, `-m "not slow"` matching the CI convention, plus the
2 fully-`slow`-marked files re-run without the filter): 166 passed cleanly or
skipped for a documented environmental/fixture reason, and 3 were genuinely
failing. Those 3 are promoted out of the baseline into
`_KNOWN_UNCOVERED_OTHER_FILES` below, the same reasoned-registry treatment
router_v6's 3 failing files already got in `_KNOWN_UNCOVERED_ROUTER_V6_FILES`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _test_root() -> Path:
    return _repo_root() / "packages" / "temper-placer" / "tests"


def _all_test_files() -> frozenset[str]:
    root = _test_root()
    return frozenset(
        str(p.relative_to(root))
        for p in root.rglob("test_*.py")
        if "__pycache__" not in p.parts
    )


def _step_blocks(workflow_text: str) -> list[str]:
    """Split a workflow file into per-step text blocks.

    A step starts at a line matching ``- name:`` or ``- uses:`` at step-item
    indentation and runs until the next such line (or EOF). This is a
    line-oriented approximation of YAML step boundaries, not a real YAML
    parser -- sufficient here because we only need to know, for each block,
    whether it sets a working directory and what `tests/...` arguments it
    passes to pytest.
    """
    lines = workflow_text.splitlines()
    starts = [i for i, l in enumerate(lines) if re.match(r"^\s*- (name:|uses:)", l)]
    starts.append(len(lines))
    return ["\n".join(lines[a:b]) for a, b in zip(starts, starts[1:])]


_BARE_FILE_RE = re.compile(r"(?<![\w/.])tests/[A-Za-z0-9_./]+\.py")
_BARE_DIR_RE = re.compile(r"(?<![\w/.])tests/[A-Za-z0-9_./]+/(?=[\s\"'])")
_EXPLICIT_FILE_RE = re.compile(r"packages/temper-placer/tests/[A-Za-z0-9_./]+\.py")
_EXPLICIT_DIR_RE = re.compile(r"packages/temper-placer/tests/[A-Za-z0-9_./]+/(?=[\s\"'])")
_WD_RE = re.compile(r"working-directory:\s*(\S+)")
_CD_RE = re.compile(r"\bcd\s+(packages/[\w-]+)\s*&&")


def _referenced_files_and_dirs() -> tuple[frozenset[str], frozenset[str]]:
    """Every packages/temper-placer/tests/... file and directory any workflow
    step passes to pytest, resolved relative to the tests/ root.

    A step's *bare* `tests/...` argument only means
    `packages/temper-placer/tests/...` when that step's effective working
    directory is `packages/temper-placer` -- either an explicit
    `working-directory:` key, or an inline `cd packages/temper-placer &&`
    (one step in this repo uses that form instead). An *explicit*
    `packages/temper-placer/tests/...` argument means what it says regardless
    of working directory.
    """
    named_files: set[str] = set()
    named_dirs: set[str] = set()
    for wf in sorted((_repo_root() / ".github" / "workflows").glob("*.yml")):
        text = wf.read_text()
        for block in _step_blocks(text):
            for m in _EXPLICIT_FILE_RE.findall(block):
                named_files.add(m[len("packages/temper-placer/tests/") :])
            for m in _EXPLICIT_DIR_RE.findall(block):
                named_dirs.add(m[len("packages/temper-placer/tests/") :])

            wd_match = _WD_RE.search(block)
            cd_match = _CD_RE.search(block)
            wd = wd_match.group(1) if wd_match else (cd_match.group(1) if cd_match else None)
            if wd != "packages/temper-placer":
                continue
            for m in _BARE_FILE_RE.findall(block):
                named_files.add(m[len("tests/") :])
            for m in _BARE_DIR_RE.findall(block):
                named_dirs.add(m[len("tests/") :])
    return frozenset(named_files), frozenset(named_dirs)


def _covered(all_files: frozenset[str], named_files: frozenset[str], named_dirs: frozenset[str]) -> frozenset[str]:
    covered = set()
    for f in all_files:
        if f in named_files:
            covered.add(f)
            continue
        if any(f.startswith(d) for d in named_dirs):
            covered.add(f)
    return frozenset(covered)


def _load_baseline() -> frozenset[str]:
    path = Path(__file__).with_name("ci_test_file_registration_baseline.txt")
    entries = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(line)
    return frozenset(entries)


# --- router_v6: the 49 files actually triaged in
# docs/evidence/2026-08-07-router-v6-ci-name-enumeration-gap.md §2. All were
# built with the same Rust extensions the CI container prebuilds and run with
# `-m "not slow"`, from a fresh worktree checkout, on 2026-08-07.

_PASSING_LOCALLY = (
    "Passes locally (2026-08-07 triage, full run: 2688 passed / 3 skipped "
    "across all 49 unreferenced router_v6 files together). Pure Python/Rust "
    "unit test, no kicad-cli/ngspice/mfem dependency. Not yet wired into any "
    "CI job. See docs/evidence/2026-08-07-router-v6-ci-name-enumeration-gap.md §2/§3."
)

_KNOWN_UNCOVERED_ROUTER_V6_FILES: dict[str, str] = {
    "router_v6/test_acid_trap_generator_fix.py": _PASSING_LOCALLY,
    "router_v6/test_astar_heuristics_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_astar_kernel_pbt.py": _PASSING_LOCALLY,
    "router_v6/test_astar_kernel_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_bottleneck_geometry_metamorphic.py": _PASSING_LOCALLY,
    "router_v6/test_bottleneck_geometry_pbt.py": _PASSING_LOCALLY,
    "router_v6/test_bottleneck_geometry_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_channel_edge_identity_determinism.py": _PASSING_LOCALLY,
    "router_v6/test_channel_skeleton_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_channel_widths_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_clearance_matrix_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_congestion_defects.py": _PASSING_LOCALLY,
    "router_v6/test_congestion_pbt.py": _PASSING_LOCALLY,
    "router_v6/test_congestion_rust_differential.py": (
        "FAILING (2026-08-07 local triage): "
        "test_total_movement_bit_exact[moves6] -- oracle raises "
        "OverflowError(34, 'Numerical result out of range') "
        "(glibc strerror(ERANGE)), Rust binding raises "
        "OverflowError(34, 'Result too large'); real message-parity gap "
        "between the pinned oracle and the Rust port, not environmental "
        "(temper-NNN). Do not wire in un-deselected -- see doc §2/§3.3."
    ),
    "router_v6/test_congestion_tensor_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_constraints_geometry_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_constraints_geometry_rust_pbt.py": _PASSING_LOCALLY,
    "router_v6/test_corridor_pbt.py": _PASSING_LOCALLY,
    "router_v6/test_corridor_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_creepage_check_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_creepage_geometry_pbt.py": _PASSING_LOCALLY,
    "router_v6/test_decline_reason_contract.py": _PASSING_LOCALLY,
    "router_v6/test_dfm_pbt.py": _PASSING_LOCALLY,
    "router_v6/test_dfm_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_dfm_rust_pbt.py": _PASSING_LOCALLY,
    "router_v6/test_encoding_pruning_geographic.py": _PASSING_LOCALLY,
    "router_v6/test_escape_via_pbt.py": _PASSING_LOCALLY,
    "router_v6/test_escape_via_rust_differential.py": (
        "FAILING (2026-08-07 local triage): "
        "test_is_position_valid_bit_exact[overflow_square] -- same "
        "OverflowError message mismatch as test_congestion_rust_differential.py "
        "('Numerical result out of range' vs 'Result too large'); real "
        "message-parity gap (temper-NNN). Do not wire in un-deselected -- "
        "see doc §2/§3.3."
    ),
    "router_v6/test_layer_assignment_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_net_ordering_pbt.py": _PASSING_LOCALLY,
    "router_v6/test_net_ordering_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_net_ordering_rust_supplemental.py": _PASSING_LOCALLY,
    "router_v6/test_occupancy_grid_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_occupancy_raster_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_path_simplify_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_quality_metrics_oracle_pin.py": _PASSING_LOCALLY,
    "router_v6/test_quality_metrics_pbt.py": _PASSING_LOCALLY,
    "router_v6/test_quality_metrics_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_signature_self_test.py": _PASSING_LOCALLY,
    "router_v6/test_stage2_golden_parity.py": (
        "Module-skips locally (2026-08-07 triage): "
        "tests/fixtures/stage2_goldens/ doesn't exist on disk -- pre-existing "
        "fixture-generation gap (generate_stage2_goldens.py in the same "
        "directory was evidently never run), unrelated to CI wiring. "
        "See doc §2."
    ),
    "router_v6/test_stage4_golden_parity.py": (
        "Module-skips locally (2026-08-07 triage): "
        "tests/fixtures/stage4_goldens/ exists but its subdirectories don't "
        "match the per-board layout this loader expects. Pre-existing "
        "fixture-generation gap, unrelated to CI wiring. See doc §2."
    ),
    "router_v6/test_stage4_monolith_parity.py": (
        "Skips locally (2026-08-07 triage): 'No test boards available' -- "
        "same stage4_goldens/ layout gap as test_stage4_golden_parity.py. "
        "See doc §2."
    ),
    "router_v6/test_strip_copper.py": _PASSING_LOCALLY,
    "router_v6/test_terminal_extraction_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_terminal_tree_rust_differential.py": _PASSING_LOCALLY,
    "router_v6/test_tree_grid_layer_mismatch.py": _PASSING_LOCALLY,
    "router_v6/test_u2_stackup_role_ssot.py": _PASSING_LOCALLY,
    "router_v6/test_zero_length_segments.py": _PASSING_LOCALLY,
    "router_v6/test_zone_pour_geometry_rust_differential.py": (
        "FAILING (2026-08-07 local triage): "
        "test_tie_break_class_exists_direct_cKDTree_comparison -- fails with "
        "the test's own diagnostic message, 'the forcing coordinates no "
        "longer reproduce a scipy/first-wins disagreement -- this test no "
        "longer demonstrates the documented divergence and should be "
        "re-derived.' SciPy-version-dependent maintenance debt, not a Rust "
        "regression (temper-NNN). Do not wire in un-deselected -- see doc "
        "§2/§3.3."
    ),
}

# --- the 3 genuinely-failing files outside router_v6/, triaged in
# docs/evidence/2026-08-07-full-tree-ci-name-enumeration-triage.md §4. All
# three were promoted here out of the generic baseline snapshot because this
# pull actually ran them and has a real, specific reason for each -- the same
# treatment router_v6's 3 failing files got above. Built with the same 13
# pyo3/maturin Rust extensions the CI container prebuilds (freshly built via
# `make extensions` in this session), `-m "not slow"`, from a fresh
# `make venv-isolate` checkout, on 2026-08-07.

_KNOWN_UNCOVERED_OTHER_FILES: dict[str, str] = {
    "closure/test_router_completion.py": (
        "FAILING (2026-08-07 full-tree triage), 3 of 4 tests -- "
        "TestPostChangePromotionGate::test_closure_post_change_meets_{sm1,sm2,sm6}. "
        "Two stacked causes, both real: (A) NEW finding -- "
        "_measure_candidate_closure() does json.loads() on the full captured "
        "subprocess stdout, but temper_placer/router_v6/_astar_reconstruct.py "
        "(lines 139/241/338/356) prints per-net routing diagnostics via bare "
        "print() to stdout ahead of measure_closure.py's JSON payload, so any "
        "real board run breaks the JSON contract for this test (and any other "
        "caller of measure_closure.py) regardless of kicad-cli availability -- "
        "not environmental. (B) pre-existing, already documented in "
        "docs/evidence/2026-07-29-ci-health-after-split.md (metrics-record.yml "
        "row): router_completion_pct=0.37%, 'All strategies exhausted for "
        "phase=\"placement\"', DRC blocked on missing kicad-cli -- confirmed "
        "chronic there, not a new regression here. "
        "test_closure_pre_change_baseline_recorded (the 4th test in this file) "
        "is unaffected and passes. temper-NNN. Do not wire in un-deselected -- "
        "see doc §4.1/§6."
    ),
    "geometry/test_drc_inflate_rust_differential.py": (
        "FAILING (2026-08-07 full-tree triage): "
        "TestDRCProxyScoreDifferential::test_summation_order_is_load_bearing -- "
        "same class as router_v6's test_zone_pour_geometry_rust_differential.py "
        "finding: an anti-vacuity meta-test whose fixed corpus "
        "(np.random.default_rng(3), n=40) no longer provokes a genuine "
        "pairwise-vs-naive-sum disagreement, so the assertion "
        "'pairwise.hex() != naive.hex()' now fails on identical bit patterns. "
        "The underlying differential this meta-test guards still passes in "
        "the same run -- maintenance debt in the corpus, not a Rust-port "
        "regression. temper-NNN. Do not wire in un-deselected -- see doc §4.2."
    ),
    "manufacturing/test_tolerances_pbt.py": (
        "FAILING (2026-08-07 full-tree triage): "
        "test_p3_clearance_monotonic_in_nominal -- Hypothesis-found float64 "
        "boundary case: c1=1.0000000000000002e-06 and c2=1e-06 differ by one "
        "ULP, but worst_case_min = nominal_value - tolerance_minus with "
        "tolerance_minus~0.15 (5 orders of magnitude larger than the ULP gap), "
        "so the subtraction rounds both to the identical float and the "
        "property's strict '>' assertion cannot hold -- inherent to float64 "
        "arithmetic at this scale disparity, not a bug in analyze_clearance "
        "itself. Reproducible, not seed-flaky. temper-NNN. Do not wire in "
        "un-deselected -- see doc §4.3."
    ),
}

# --- the one dangling workflow reference confirmed in the doc's §1. ---------

_KNOWN_DANGLING_WORKFLOW_REFERENCES: dict[str, str] = {
    "router_v6/test_wave4_numba_astar.py": (
        "Named in 'Invariant tests (router_v6 group 2)' "
        "(.github/workflows/python-tests.yml:2710) but deleted in 37793e5c "
        "(post-Numba-migration cleanup; the Numba backend itself was removed "
        "in 365eb259). pytest exits 4 ('file or directory not found') before "
        "collecting anything from that invocation, so group 2 currently "
        "collects ZERO tests -- confirmed via "
        "`pytest --collect-only -q` with the group's exact argument list. "
        "Fix requires a workflow edit (remove this entry from group 2's file "
        "list) that this pull is not permitted to make; see doc §3.1. Once "
        "fixed, remove this entry -- a stale entry here means the test "
        "starts asserting a defect that no longer exists."
    ),
}


@pytest.fixture(scope="module")
def all_test_files() -> frozenset[str]:
    return _all_test_files()


@pytest.fixture(scope="module")
def referenced() -> tuple[frozenset[str], frozenset[str]]:
    return _referenced_files_and_dirs()


@pytest.fixture(scope="module")
def baseline() -> frozenset[str]:
    return _load_baseline()


def test_no_new_uncovered_test_files(all_test_files, referenced, baseline):
    """Every test_*.py file is CI-covered, router_v6-tracked, or baseline-tracked.

    A file that shows up in neither is genuinely new drift: either nobody
    wired it into a job, or (much less likely) the survey above has a
    parsing gap. Either way this must be investigated by name, not silently
    passed over.
    """
    named_files, named_dirs = referenced
    covered = _covered(all_test_files, named_files, named_dirs)
    uncovered = all_test_files - covered
    tracked = (
        frozenset(_KNOWN_UNCOVERED_ROUTER_V6_FILES)
        | frozenset(_KNOWN_UNCOVERED_OTHER_FILES)
        | baseline
    )

    new_drift = uncovered - tracked
    assert not new_drift, (
        "New CI-uncovered test file(s) found -- referenced by no workflow "
        "job (by name or by directory sweep) and absent from "
        "_KNOWN_UNCOVERED_ROUTER_V6_FILES, _KNOWN_UNCOVERED_OTHER_FILES, and "
        f"the baseline snapshot: {sorted(new_drift)}. Wire the file into a "
        "job, or add it to the appropriate registry with a reason (see this "
        "module's docstring and "
        "docs/evidence/2026-08-07-router-v6-ci-name-enumeration-gap.md / "
        "docs/evidence/2026-08-07-full-tree-ci-name-enumeration-triage.md)."
    )


def test_no_stale_tracked_entries(all_test_files, referenced, baseline):
    """Every tracked ("known uncovered") entry must still actually be uncovered.

    Catches the entry rotting the other way: a file gets wired into a job
    but nobody prunes its registry/baseline entry, so the tracking silently
    stops meaning what it says.
    """
    named_files, named_dirs = referenced
    covered = _covered(all_test_files, named_files, named_dirs)
    tracked = (
        frozenset(_KNOWN_UNCOVERED_ROUTER_V6_FILES)
        | frozenset(_KNOWN_UNCOVERED_OTHER_FILES)
        | baseline
    )

    now_covered = tracked & covered
    assert not now_covered, (
        "Tracked-as-uncovered file(s) are now actually CI-covered -- prune "
        "these from _KNOWN_UNCOVERED_ROUTER_V6_FILES, "
        f"_KNOWN_UNCOVERED_OTHER_FILES, or the baseline snapshot: {sorted(now_covered)}."
    )

    gone = tracked - all_test_files
    assert not gone, (
        "Tracked entry no longer exists on disk -- prune from "
        "_KNOWN_UNCOVERED_ROUTER_V6_FILES, _KNOWN_UNCOVERED_OTHER_FILES, or "
        f"the baseline snapshot: {sorted(gone)}."
    )


def test_router_v6_registry_entries_have_reasons():
    for name, reason in _KNOWN_UNCOVERED_ROUTER_V6_FILES.items():
        assert reason and len(reason) > 10, f"{name} registered without a real reason"


def test_other_registry_entries_have_reasons():
    for name, reason in _KNOWN_UNCOVERED_OTHER_FILES.items():
        assert reason and len(reason) > 10, f"{name} registered without a real reason"


def test_no_new_dangling_workflow_references(all_test_files):
    """Every individually-named workflow file reference must resolve on disk.

    A missing path makes pytest exit 4 before collecting ANYTHING else in
    that invocation (scripts/pytest_guard.py's own reason for existing) --
    this is the router_v6 group 2 defect's exact shape. A new dangling
    reference must be caught immediately, by name.
    """
    named_files, _named_dirs = referenced_for_dangling_check()
    root = _test_root()
    dangling = frozenset(f for f in named_files if not (root / f).is_file())

    assert dangling == frozenset(_KNOWN_DANGLING_WORKFLOW_REFERENCES), (
        "Dangling workflow test-file reference(s) changed. New ones found: "
        f"{sorted(dangling - frozenset(_KNOWN_DANGLING_WORKFLOW_REFERENCES))}. "
        "Entries tracked but no longer dangling (fixed -- prune the "
        f"registry entry): {sorted(frozenset(_KNOWN_DANGLING_WORKFLOW_REFERENCES) - dangling)}."
    )


def referenced_for_dangling_check() -> tuple[frozenset[str], frozenset[str]]:
    # Separate call (not the shared fixture) so this test's failure message
    # is self-contained even if run with `pytest -k dangling`.
    return _referenced_files_and_dirs()


def test_known_dangling_reference_reasons_non_empty():
    for name, reason in _KNOWN_DANGLING_WORKFLOW_REFERENCES.items():
        assert reason and len(reason) > 10, f"{name} registered without a real reason"


def test_baseline_and_router_v6_registry_do_not_overlap(baseline):
    overlap = frozenset(_KNOWN_UNCOVERED_ROUTER_V6_FILES) & baseline
    assert not overlap, (
        f"File(s) tracked in both the router_v6 registry and the baseline "
        f"snapshot -- remove from the baseline, the router_v6 registry is "
        f"more specific: {sorted(overlap)}"
    )


def test_baseline_and_other_registry_do_not_overlap(baseline):
    overlap = frozenset(_KNOWN_UNCOVERED_OTHER_FILES) & baseline
    assert not overlap, (
        f"File(s) tracked in both _KNOWN_UNCOVERED_OTHER_FILES and the "
        f"baseline snapshot -- remove from the baseline, the reasoned "
        f"registry is more specific: {sorted(overlap)}"
    )


def test_router_v6_and_other_registry_do_not_overlap():
    overlap = frozenset(_KNOWN_UNCOVERED_ROUTER_V6_FILES) & frozenset(
        _KNOWN_UNCOVERED_OTHER_FILES
    )
    assert not overlap, (
        f"File(s) tracked in both _KNOWN_UNCOVERED_ROUTER_V6_FILES and "
        f"_KNOWN_UNCOVERED_OTHER_FILES -- a file belongs in exactly one "
        f"reasoned registry: {sorted(overlap)}"
    )
