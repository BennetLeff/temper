#!/usr/bin/env python3
"""Transition-table mutation driver (R40, P1).

Proves that the generated transition-table tests bite: every transition row
in the *test-side* manifest (``TRANSITIONS`` in
``firmware/test/gen_transition_table.py``) is mutated (wrong target, wrong
guard) and the regenerated tests must fail against the real state machine.
See docs/plans/2026-08-02-030-feat-transition-table-mutation-plan.md (KTD1-4).

Design notes
------------
- KTD1: the driver imports the generator and writes scratch output only. The
  committed ``firmware/test/test_transition_table_generated.c`` is never
  touched; each mutation is applied in memory, emitted to a scratch build
  directory, built, and run there.
- KTD2: one canonical mutation set per row:
    wrong_target  - target replaced by a canonical alternate state
    guard_swap    - fault code swapped to a different fault code
    guard_drop    - fault code dropped (assertion deleted)
    guard_add     - fault code added to a benign row
  Same-value mutations are classified ``equivalent`` and excluded.
- KTD3: a live mutant is a test defect, never a spec approval. The generator's
  test recipe always asserts the fault code (FAULT_NONE for benign rows) so
  guard-drop/guard-swap/guard-add all die; see gen_transition_table.py.
- KTD4: one scratch CMake build tree is reused across mutants; only the
  generated C file changes between runs, so rebuilds are incremental.

Usage
-----
  python3 mutate_transition_table.py --sweep [--report PATH] [--scratch-dir DIR]
  python3 mutate_transition_table.py --row N [--op wrong_target|guard_swap|guard_drop|guard_add]
  python3 mutate_transition_table.py --baseline-only
"""

from __future__ import annotations

import argparse
import copy
import datetime
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_SCRATCH_DIR = SCRIPT_DIR / "build" / "mutations"
DEFAULT_REPORT = DEFAULT_SCRATCH_DIR / "report.json"
COMMITTED_GENERATED = SCRIPT_DIR / "test_transition_table_generated.c"
GENERATOR = SCRIPT_DIR / "gen_transition_table.py"

# Scratch binary target name (mirrors the test_state_machine_only source set
# from firmware/test/CMakeLists.txt).
SCRATCH_TARGET = "test_transition_mutant"
SCRATCH_CMAKE = "CMakeLists.txt"
SCRATCH_GENERATED_C = "test_transition_table_generated.c"
SCRATCH_BINARY = SCRATCH_TARGET

# ---------------------------------------------------------------------------
# Canonical mutation operators (KTD2)
# ---------------------------------------------------------------------------

# Canonical alternate target for a wrong-target mutation: STATE_FAULT is the
# canonical "wrong" target for every non-fault target (a transition must never
# land in FAULT by accident), and STATE_INIT is the canonical wrong target for
# rows whose target already is STATE_FAULT. For (STATE_PREHEAT, NEAR_TARGET)
# this yields STATE_FAULT, the known-kill mutation in the plan.
WRONG_TARGET_FAULT = "STATE_FAULT"
WRONG_TARGET_INIT = "STATE_INIT"

# Canonical guard codes.
GUARD_ADD_CODE = "FAULT_OVER_TEMP"  # added to benign rows
GUARD_SWAP_FALLBACK = "FAULT_OVER_CURRENT"  # used when current code is GUARD_ADD_CODE


def _wrong_target(row):
    """(from, event, to, fault, needs) -> wrong-target mutation."""
    from_s, event, to_s, fault, needs = row
    alt = WRONG_TARGET_FAULT if to_s != WRONG_TARGET_FAULT else WRONG_TARGET_INIT
    return (from_s, event, alt, fault, needs)


def _guard_swap(row):
    """Fault code swapped to a different fault code (same-value if None)."""
    from_s, event, to_s, fault, needs = row
    if fault is None:
        return row  # same-value -> classified equivalent upstream
    alt = GUARD_SWAP_FALLBACK if fault == GUARD_ADD_CODE else GUARD_ADD_CODE
    return (from_s, event, to_s, alt, needs)


def _guard_drop(row):
    """Fault code dropped (assertion deleted; same-value if already None)."""
    from_s, event, to_s, fault, needs = row
    if fault is None:
        return row  # same-value -> classified equivalent upstream
    return (from_s, event, to_s, None, needs)


def _guard_add(row):
    """Fault code added to a benign row (same-value if already set)."""
    from_s, event, to_s, fault, needs = row
    if fault is not None:
        return row  # same-value -> classified equivalent upstream
    return (from_s, event, to_s, GUARD_ADD_CODE, needs)


OPERATORS = (
    ("wrong_target", _wrong_target,
     "target replaced by canonical alternate state"),
    ("guard_swap", _guard_swap, "fault code swapped to a different fault code"),
    ("guard_drop", _guard_drop, "fault code dropped (assertion deleted)"),
    ("guard_add", _guard_add, "fault code added to a benign row"),
)
OPERATOR_NAMES = tuple(op for op, _, _ in OPERATORS)
OPERATOR_BY_NAME = {op: fn for op, fn, _ in OPERATORS}


def canonical_mutations_for_row(row):
    """Return [(op_name, mutated_row)] for one expanded row.

    Every canonical operator is listed; a mutation whose result is identical
    to the original row (e.g. guard_drop on an already-benign row) is a
    same-value mutation, which the sweep classifies ``equivalent`` and excludes
    from the score. Callers use ``mutated == row`` to detect it.
    """
    out = []
    for op_name, fn, _ in OPERATORS:
        out.append((op_name, fn(row)))
    return out


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def load_generator():
    """Import firmware/test/gen_transition_table.py as a module."""
    spec = importlib.util.spec_from_file_location(
        "gen_transition_table", str(GENERATOR)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expand_transitions(transitions, active_states):
    """Expand '*' wildcard rows into explicit per-active-state rows.

    Each expanded row gets a stable index that matches the emitted C table
    order (gen_transition_table._c_table_rows expands wildcards the same way),
    so mutating expanded-list index N mutates exactly the N-th emitted row.
    """
    out = []
    for from_s, event, to_s, fault, needs in transitions:
        if from_s == "*":
            for active_state in active_states:
                out.append((active_state, event, to_s, fault, needs))
        else:
            out.append((from_s, event, to_s, fault, needs))
    return out


def apply_mutation_at(expanded, idx, op_name):
    """Return a new expanded list with row ``idx`` mutated by ``op_name``."""
    mutated_list = copy.deepcopy(expanded)
    row = mutated_list[idx]
    fn = OPERATOR_BY_NAME[op_name]
    mutated_list[idx] = fn(row)
    return mutated_list


# ---------------------------------------------------------------------------
# Scratch build orchestration (KTD4)
# ---------------------------------------------------------------------------

# Mirrors the test_state_machine_only source set and compile options from
# firmware/test/CMakeLists.txt. {TEST_DIR} / {SCRATCH_DIR} are absolute paths
# substituted at write time.
SCRATCH_CMAKE_TEMPLATE = """\
# AUTO-GENERATED by firmware/test/mutate_transition_table.py -- do not edit.
# Scratch build mirroring the `test_state_machine_only` target source set
# (firmware/test/CMakeLists.txt) with a mutated generated C file.
cmake_minimum_required(VERSION 3.16)
project(temper_mutation_tests C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
add_compile_options(-Wall -Wextra -Wpedantic)
set(CMAKE_BUILD_TYPE Debug)

add_definitions(-DHOST_BUILD)
add_definitions(
    -DOCP_THRESHOLD_AMPS=50.0f
    -DOVP_THRESHOLD_VOLTS=390.0f
    -DTHERMAL_SHUTDOWN_C=85.0f
    -DWATCHDOG_TIMEOUT_MS=1600
    -DTEMP_PRECISION_C=0.5f
    -DFREQ_MIN_KHZ=38.0f
    -DFREQ_MAX_KHZ=50.0f
    -DDEAD_TIME_NS=500
    -DPAN_VALID_MIN_AMPS=3.0f
    -DPAN_VALID_MAX_AMPS=15.0f
    -DPAN_NO_LOAD_AMPS=20.0f
)

set(TEST_DIR "{TEST_DIR}")
set(SCRATCH_DIR "{SCRATCH_DIR}")

add_executable({TARGET}
    ${{TEST_DIR}}/unity/unity.c
    ${{TEST_DIR}}/../main/state_machine.c
    ${{TEST_DIR}}/../main/state_handlers.c
    ${{TEST_DIR}}/../components/control/low_temp_control.c
    ${{TEST_DIR}}/../components/control/pid_control.c
    ${{TEST_DIR}}/../components/control/thermal_mass.c
    ${{TEST_DIR}}/../components/control/profiles.c
    ${{TEST_DIR}}/state_machine_stubs.c
    ${{TEST_DIR}}/test_state_machine.c
    ${{TEST_DIR}}/test_main_state_machine.c
    ${{SCRATCH_DIR}}/{GENERATED_C}
)

target_include_directories({TARGET} PRIVATE
    ${{TEST_DIR}}
    ${{TEST_DIR}}/..
    ${{TEST_DIR}}/unity
    ${{TEST_DIR}}/../components/hal/include
    ${{TEST_DIR}}/../components/hal/mock
    ${{TEST_DIR}}/../components/control
    ${{TEST_DIR}}/../components/safety
    ${{TEST_DIR}}/../main
)
target_link_libraries({TARGET} m)
"""


def write_scratch_cmake(scratch_dir):
    """Write the scratch CMakeLists.txt (idempotent; path-dependent)."""
    scratch_dir.mkdir(parents=True, exist_ok=True)
    text = SCRATCH_CMAKE_TEMPLATE.format(
        TEST_DIR=str(SCRIPT_DIR),
        SCRATCH_DIR=str(scratch_dir),
        TARGET=SCRATCH_TARGET,
        GENERATED_C=SCRATCH_GENERATED_C,
    )
    cmake_path = scratch_dir / SCRATCH_CMAKE
    if cmake_path.exists() and cmake_path.read_text() == text:
        return cmake_path
    cmake_path.write_text(text)
    return cmake_path


def ensure_configured(scratch_dir):
    """Configure the scratch build once; returns (configure_ran, ok)."""
    write_scratch_cmake(scratch_dir)
    cache = scratch_dir / "CMakeCache.txt"
    if cache.exists():
        return True
    proc = subprocess.run(
        ["cmake", "-S", str(scratch_dir), "-B", str(scratch_dir)],
        capture_output=True, text=True,
    )
    return proc.returncode == 0


def _force_rebuild(scratch_dir):
    """Delete the generated-C object and the binary before building.

    make's up-to-date check uses filesystem mtime granularity (1s on macOS /
    Linux tmpfs); when the baseline build and the first mutant emit land within
    the same second, make considers the object current and the binary would run
    the *previous* (unmutated) table -- a stale-binary false 'live'. Deleting
    the object and the binary before every build makes recompilation
    deterministic (and guarantees a failed build cannot leave a stale binary to
    run).
    """
    obj = scratch_dir / "CMakeFiles" / (SCRATCH_TARGET + ".dir") / (
        SCRATCH_GENERATED_C + ".o"
    )
    if obj.exists():
        obj.unlink()
    binary = scratch_dir / SCRATCH_BINARY
    if binary.exists():
        binary.unlink()


def build_mutant(scratch_dir):
    """Incrementally rebuild the scratch binary; returns (ok, stderr_tail)."""
    _force_rebuild(scratch_dir)
    proc = subprocess.run(
        ["cmake", "--build", str(scratch_dir), "--target", SCRATCH_TARGET,
         "-j", str(os.cpu_count() or 2)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-25:])
        return False, tail
    return True, ""


def run_mutant_binary(scratch_dir, timeout_s=60):
    """Run the scratch binary; returns (returncode, stdout_tail)."""
    binary = scratch_dir / SCRATCH_BINARY
    proc = subprocess.run(
        [str(binary)], cwd=str(scratch_dir), capture_output=True, text=True,
        timeout=timeout_s,
    )
    output = proc.stdout + proc.stderr
    tail = "\n".join(output.splitlines()[-20:])
    return proc.returncode, tail


def emit_mutated_c(gen, mutated_transitions, scratch_dir):
    """Emit the mutated table into the scratch dir; returns scratch C path.

    The generator's emission functions take the transitions list explicitly
    (see gen_transition_table._c_table_rows/_c_event_stubs), so no module
    global is mutated and the committed generated file can never be affected.
    """
    scratch_dir.mkdir(parents=True, exist_ok=True)
    scratch_c = scratch_dir / SCRATCH_GENERATED_C
    gen.generate_c_output(mutated_transitions, str(scratch_c))
    return scratch_c


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

OUTCOME_KILLED = "killed"
OUTCOME_LIVE = "live"
OUTCOME_EQUIVALENT = "equivalent"
OUTCOME_ERROR = "error"

REASON_STUB_NEVER_FIRES = "stub-never-fires"
REASON_PRECONDITION_MASK = "precondition-mask"
REASON_DRAIN_MASK = "drain-mask"
REASON_TIMING = "timing"
REASON_ASSERTION_GAP = "assertion-gap"
REASON_UNCLASSIFIED = "unclassified"


def classify_live_reason(row, op_name, run_stdout):
    """Attribute a reason class to a live mutant (KTD3 triage).

    Runs only for mutants the regenerated tests failed to kill. Heuristic
    classes (mirroring the plan's triage taxonomy):

      - assertion-gap:      the mutated field is not asserted by the generated
                            test recipe for this row (structural signal).
      - stub-never-fires:   the row's event stub is empty / no-op, so the event
                            cannot change machine behaviour.
      - precondition-mask:  the row's from-state precondition already steers
                            the machine to the mutated expectation.
      - drain-mask:         the row's transition lands on the expected state via
                            the message-drain fallback regardless of the spec.
      - timing:             the row depends on elapsed-time thresholds the
                            mutation does not disturb.
    """
    from_s, event, to_s, fault, _ = row
    # assertion-gap: mutated value is the exact value the machine happens to
    # produce for an unrelated reason -- structurally undetectable without
    # reading the machine; flagged when the target/fault is not what the
    # generator asserts for this row's recipe.
    if op_name == "wrong_target" and to_s == WRONG_TARGET_FAULT:
        return REASON_DRAIN_MASK
    if op_name in ("guard_drop", "guard_swap", "guard_add") and fault is None:
        return REASON_ASSERTION_GAP
    if op_name in ("guard_drop", "guard_swap", "guard_add"):
        return REASON_PRECONDITION_MASK
    return REASON_UNCLASSIFIED


def classify_mutation(gen, expanded, idx, op_name, mutated_row, scratch_dir,
                      build=True):
    """Run one mutation through generate -> build -> run -> classify.

    Returns a dict describing the outcome. A mutation is ``killed`` when the
    regenerated test binary exits non-zero, ``live`` when it passes,
    ``equivalent`` when the mutated row is byte-identical to the original
    (excluded before reaching here by callers), and ``error`` when generation
    or build failed (the reason is captured, never counted live).
    """
    from_s, event, to_s, fault, _ = mutated_row
    entry = {
        "row_index": idx,
        "from": from_s,
        "event": event,
        "op": op_name,
        "mutated_target": to_s,
        "mutated_fault": fault,
        "outcome": None,
        "exit_code": None,
        "evidence": "",
    }
    try:
        mutated_list = apply_mutation_at(expanded, idx, op_name)
        emit_mutated_c(gen, mutated_list, scratch_dir)
        if not build:
            entry["outcome"] = OUTCOME_ERROR
            entry["evidence"] = "build disabled (--no-build): cannot classify"
            return entry
        ok, err = build_mutant(scratch_dir)
        if not ok:
            entry["outcome"] = OUTCOME_ERROR
            entry["evidence"] = f"build failed:\n{err}"
            return entry
        ret, tail = run_mutant_binary(scratch_dir)
        entry["exit_code"] = ret
        if ret != 0:
            entry["outcome"] = OUTCOME_KILLED
            entry["evidence"] = tail
        else:
            entry["outcome"] = OUTCOME_LIVE
            entry["evidence"] = tail
    except Exception as exc:  # noqa: BLE001 - classify as error, not live
        entry["outcome"] = OUTCOME_ERROR
        entry["evidence"] = f"generation/run failed: {exc}"
    return entry


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

def run_sweep(gen=None, scratch_dir=None, report_path=None, build=True,
              rows=None, progress=None):
    """Run the canonical mutation set over every expanded row.

    ``rows`` optionally restricts the sweep to a subset of expanded row
    indices (used by tests and by the CI gate's mutated-rows-only fallback).
    Returns the report dict (also written to ``report_path`` when given).
    """
    gen = gen or load_generator()
    scratch_dir = Path(scratch_dir or DEFAULT_SCRATCH_DIR)
    report_path = Path(report_path) if report_path else None

    transitions = list(gen.TRANSITIONS)
    expanded = expand_transitions(transitions, gen.ACTIVE_STATES)

    # Baseline: the unmutated table must pass in the scratch harness, otherwise
    # every 'killed' classification is meaningless (killed by a broken harness).
    baseline_pass = True
    if build:
        # Emit the baseline C first: the scratch CMakeLists lists the generated
        # C as a target source, so configure needs it to exist.
        emit_mutated_c(gen, expanded, scratch_dir)
        if not ensure_configured(scratch_dir):
            raise RuntimeError(
                f"cmake configure failed in {scratch_dir} (see its output)"
            )
        ok, err = build_mutant(scratch_dir)
        if not ok:
            baseline_pass = False
            baseline_error = f"baseline build failed:\n{err}"
        else:
            ret, tail = run_mutant_binary(scratch_dir)
            if ret != 0:
                baseline_pass = False
                baseline_error = f"baseline run FAILED (exit {ret}):\n{tail}"
        if not baseline_pass:
            raise RuntimeError(baseline_error)

    rows_to_sweep = rows if rows is not None else range(len(expanded))

    rows_report = []
    live_mutants = []
    error_entries = []
    totals = {OUTCOME_KILLED: 0, OUTCOME_LIVE: 0,
              OUTCOME_EQUIVALENT: 0, OUTCOME_ERROR: 0}
    rows_covered = 0

    for idx in rows_to_sweep:
        row = expanded[idx]
        row_entry = {
            "row_index": idx,
            "from": row[0],
            "event": row[1],
            "target": row[2],
            "fault": row[3],
            "mutations": [],
        }
        for op_name, mutated_row in canonical_mutations_for_row(row):
            if mutated_row == row:
                totals[OUTCOME_EQUIVALENT] += 1
                row_entry["mutations"].append({
                    "row_index": idx,
                    "op": op_name,
                    "outcome": OUTCOME_EQUIVALENT,
                    "mutated_target": row[2],
                    "mutated_fault": row[3],
                    "exit_code": None,
                    "evidence": "same-value mutation (excluded)",
                })
                continue
            result = classify_mutation(
                gen, expanded, idx, op_name, mutated_row, scratch_dir, build=build
            )
            totals[result["outcome"]] += 1
            row_entry["mutations"].append(result)
            if result["outcome"] == OUTCOME_LIVE:
                live_mutants.append(result)
            elif result["outcome"] == OUTCOME_ERROR:
                error_entries.append(result)
            if progress:
                progress(idx, op_name, result["outcome"])
        if row_entry["mutations"]:
            rows_covered += 1
        rows_report.append(row_entry)

    mutants_total = sum(totals.values())
    non_equivalent = totals[OUTCOME_KILLED] + totals[OUTCOME_LIVE] + totals[OUTCOME_ERROR]
    score = (
        totals[OUTCOME_KILLED] / non_equivalent
        if non_equivalent else 1.0
    )

    report = {
        "schema_version": 1,
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "generator": str(SCRIPT_DIR / "mutate_transition_table.py"),
        "manifest_source": "firmware/test/gen_transition_table.py TRANSITIONS",
        "rows_total": len(expanded),
        "rows_covered": rows_covered,
        "rows_swept": len(rows_to_sweep),
        "mutants_total": mutants_total,
        "killed": totals[OUTCOME_KILLED],
        "live": totals[OUTCOME_LIVE],
        "equivalent": totals[OUTCOME_EQUIVALENT],
        "errors": totals[OUTCOME_ERROR],
        "mutation_score": round(score, 4),
        "baseline_pass": baseline_pass,
        "live_mutants": [
            {
                "row_index": m["row_index"],
                "from": m["from"],
                "event": m["event"],
                "op": m["op"],
                "mutated_target": m["mutated_target"],
                "mutated_fault": m["mutated_fault"],
                "reason": classify_live_reason(
                    expanded[m["row_index"]], m["op"], m.get("evidence", "")
                ),
                "evidence": m.get("evidence", ""),
            }
            for m in live_mutants
        ],
        "errors_list": [
            {
                "row_index": e["row_index"],
                "event": e["event"],
                "op": e["op"],
                "evidence": e.get("evidence", ""),
            }
            for e in error_entries
        ],
        "rows": rows_report,
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


def read_report(report_path):
    """Load a sweep report JSON; returns None if missing or malformed."""
    path = Path(report_path)
    if not path.exists():
        return None
    try:
        report = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return report if isinstance(report, dict) else None


def print_report_summary(report):
    """Human-readable sweep summary."""
    print(f"rows: {report['rows_covered']}/{report['rows_total']} covered "
          f"({report['rows_swept']} swept)")
    print(f"mutants: {report['mutants_total']} total, "
          f"{report['killed']} killed, {report['live']} live, "
          f"{report['equivalent']} equivalent, {report['errors']} errors")
    print(f"mutation score: {report['mutation_score']}")
    if report["live_mutants"]:
        print("LIVE MUTANTS:")
        for m in report["live_mutants"]:
            print(f"  row {m['row_index']} ({m['from']} + {m['event']}) "
                  f"op={m['op']} reason={m['reason']}")
    if report["errors_list"]:
        print("ERRORS:")
        for e in report["errors_list"]:
            print(f"  row {e['row_index']} op={e['op']}: {e['evidence'][:200]}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Transition-table mutation driver (R40).",
    )
    parser.add_argument(
        "--sweep", action="store_true",
        help="run the canonical mutation set over every expanded row",
    )
    parser.add_argument(
        "--row", type=int, default=None,
        help="mutate only the given expanded row index (with --sweep: restrict "
             "the sweep to this row)",
    )
    parser.add_argument(
        "--op", choices=OPERATOR_NAMES, default=None,
        help="single mutation operator to run for --row",
    )
    parser.add_argument(
        "--baseline-only", action="store_true",
        help="build the scratch binary with the unmutated table and run it",
    )
    parser.add_argument(
        "--scratch-dir", type=str, default=str(DEFAULT_SCRATCH_DIR),
        help=f"scratch build directory (default: {DEFAULT_SCRATCH_DIR})",
    )
    parser.add_argument(
        "--report", type=str, default=str(DEFAULT_REPORT),
        help=f"report output path (default: {DEFAULT_REPORT})",
    )
    parser.add_argument(
        "--no-build", action="store_true",
        help="generate only; do not build or run (classifies as killed/live "
             "never happens; for unit tests)",
    )
    args = parser.parse_args(argv)

    scratch_dir = Path(args.scratch_dir)
    build = not args.no_build

    if args.baseline_only:
        gen = load_generator()
        expanded = expand_transitions(list(gen.TRANSITIONS), gen.ACTIVE_STATES)
        emit_mutated_c(gen, expanded, scratch_dir)
        if not ensure_configured(scratch_dir):
            print("cmake configure failed", file=sys.stderr)
            return 3
        ok, err = build_mutant(scratch_dir)
        if not ok:
            print(f"baseline build failed:\n{err}", file=sys.stderr)
            return 3
        ret, tail = run_mutant_binary(scratch_dir)
        print(tail)
        if ret != 0:
            print(f"baseline run FAILED (exit {ret})", file=sys.stderr)
            return 1
        print("baseline PASS")
        return 0

    if args.row is not None and not args.sweep:
        # Single-mutation run: apply the op (or all ops) to one row and report.
        gen = load_generator()
        expanded = expand_transitions(list(gen.TRANSITIONS), gen.ACTIVE_STATES)
        if not (0 <= args.row < len(expanded)):
            print(f"row {args.row} out of range (0..{len(expanded) - 1})",
                  file=sys.stderr)
            return 2
        row = expanded[args.row]
        print(f"row {args.row}: {row}")
        for op_name, mutated_row in canonical_mutations_for_row(row):
            if args.op and op_name != args.op:
                continue
            if mutated_row == row:
                print(f"  {op_name}: equivalent (same-value, excluded)")
                continue
            print(f"  {op_name}: {row} -> {mutated_row}")
            result = classify_mutation(
                gen, expanded, args.row, op_name, mutated_row, scratch_dir,
                build=build,
            )
            print(f"    outcome={result['outcome']} exit={result['exit_code']}")
            if result["evidence"]:
                print(f"    evidence:\n{result['evidence']}")
        return 0

    if args.sweep:
        rows = [args.row] if args.row is not None else None

        def progress(idx, op_name, outcome):
            print(f"  row {idx} {op_name}: {outcome}", flush=True)

        report = run_sweep(
            scratch_dir=scratch_dir,
            report_path=Path(args.report),
            build=build,
            rows=rows,
            progress=progress,
        )
        print_report_summary(report)
        return 0 if (report["live"] == 0 and report["errors"] == 0
                     and report["rows_covered"] == report["rows_total"]) else 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
