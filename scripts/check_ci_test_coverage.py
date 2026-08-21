#!/usr/bin/env python3
"""Fail when CI and the test tree disagree about which tests exist.

WHY THIS EXISTS
---------------
Two silent drifts, in opposite directions, have both bitten this repo.

DIRECTION A -- a CI job names a test file that does not exist.
    pytest treats a nonexistent PATH as a *usage error*: it exits 4 having
    collected ZERO items, and ``--continue-on-collection-errors`` does not
    rescue it (that flag covers collection errors, not usage errors). So a
    single stale filename in a 46-file list does not skip one file -- it
    zeroes the entire step.

    This has now happened twice. `python-tests.yml` documents the first
    verbatim, at the `invariant-router-v6-2` job: that step "ran ZERO tests
    since 2026-07-31" because the list named
    `tests/router_v6/test_wave4_numba_astar.py`, deleted in 37793e5c. The
    `pytest_guard.py` anti-vacuity floor CORRECTLY FAILED -- and a
    `continue-on-error: true` sitting on top of it discarded that failure
    and reported the job green. It was fixed by hand and written up. Then
    #1314 deleted seven more test files, left them in the lists, and it
    recurred; those eight were again removed by hand.

    Nothing prevented the next occurrence. This gate does. Direction A is a
    HARD FAILURE with no ledger and no allowlist: a CI job naming a
    nonexistent path is never correct, there is no legitimate instance of
    it, and it silently zeroes a whole step.

DIRECTION B -- a test file exists and is named by no CI job at all.
    Measured by hand before this gate existed: 142 files, ~4,310 tests, ten
    of them failing -- tests that were written, committed, and then never
    run again. Separately, five firmware CTest *binaries*
    (`test_ntc_guard_only`, `test_adc_guard_only`, `test_fan_guard_only`,
    `test_coil_guard_only`, `test_pwm_guard_only`) build and pass and are
    registered with neither `add_test()` nor any CI `ctest -R` selector.
    One of them was hiding a thermistor conversion wrong by ~60 degrees C,
    found only when a human read it.

    Direction B has a large true population, so it is a SHRINK-ONLY
    RATCHET over a committed inventory -- the same shape as
    `.hash-order-inventory`, `.unwired-kernel-inventory`, and
    `.orphaned-python-module-inventory`. The inventory starts at the honest
    number. It is not this gate's job to fix them.

METHOD -- and why the working-directory resolution is the crux
--------------------------------------------------------------
"Which paths does CI name" is not a grep. In this repo a test path reaches
pytest through at least five spellings, each resolved against a DIFFERENT
effective working directory:

  1. `working-directory: packages/temper-placer` on the step, then
     `uv run pytest tests/core/`.
  2. `defaults: {run: {working-directory: ...}}` on the job.
  3. `cd packages/temper-placer && uv run python ../../scripts/pytest_guard.py
     ... -- tests/placer/cp_sat/` inside a `run:` block, at repo root.
  4. A `cd` inside a SUBSHELL --
     `(cd packages/temper-workflow && uv run pytest tests/ ...) &` -- whose
     effect ends at the closing paren, so the next background job in the
     same block is back at the repo root.
  5. Repo-root-relative absolute-ish paths in a step with no wd at all
     (`uv run pytest scripts/tests/test_x.py packages/temper-placer/tests/...`).

Resolving every path against one package is exactly the mistake that must
not be made: doing so by hand reported 10 dead references when the true
number was 8 -- two of the ten resolved correctly against
`packages/temper-workflow`, and one against a `cd` in its own run block.
So this gate walks each `run:` script as a shell script, maintaining a cwd
that a `cd` mutates and a `(`/`)` pair saves and restores, and resolves
every argument against the cwd in force AT THAT COMMAND.

Argument kinds are distinguished, because they mean different things:

    TARGET    a positional path handed to pytest. Must exist (direction A);
              covers the file, or every `test_*.py` beneath it if a
              directory (direction B).
    DESELECT  `--deselect path::Class::test`. The FILE must exist
              (direction A -- a `--deselect` naming a deleted file is dead
              weight and hides the fact that the test is gone), but a
              deselect does NOT remove the file from coverage: its other
              tests still run.
    IGNORE    `--ignore=path` / `--ignore-glob=`. The path must exist
              (direction A), and it REMOVES coverage (direction B) -- an
              ignored file is a file CI does not run, which is the whole
              point of this gate. A file ignored in one job but named as a
              target in another is still covered, because coverage is a
              union over jobs and ignores are subtracted per-invocation.

CTEST IS COVERED TOO, in both directions:
    A firmware `add_executable(test_*)` target with no `add_test(NAME ...
    COMMAND <it>)` can never be run by ctest at all -- direction B, and the
    shape that hid the thermistor bug. A registered `add_test` name that no
    CI `ctest -R <regex>` selects is also direction B: registered, and
    still never run. And a CI `ctest -R` whose regex matches NO registered
    test name is direction A -- `ctest` exits 0 on an empty selection
    unless `--no-tests=error` is passed, so it is silent by default.

ANTI-VACUITY ON THE DENOMINATOR
-------------------------------
Both counts are printed on EVERY run, pass or fail. If either collapses to
zero -- no CI-referenced tests found, or no test files found on disk --
that is a TOOL ERROR (exit 2), never a pass. A gate that reports "0 dead
references" because its parser broke and found no references at all is
precisely the instrument this repo already has too many of; see
`scripts/check_vacuous_gates.py` and PR #1392, where 74 of 86 assertions
could not fail.

KNOWN BLIND SPOTS (state them; do not pretend this is exhaustive)
-----------------------------------------------------------------
  - A path built from a shell variable or a `${{ }}` expression is not
    resolved. No current pytest/ctest invocation in this repo uses one; if
    one is added, its paths are simply not seen (they are not reported as
    dead -- unresolvable is not the same as nonexistent).
  - `-k` / `-m` expressions are NOT modelled. A file selected as a target
    but fully filtered out by `-m "not slow"` counts as covered. This gate
    answers "does CI name it", not "does CI execute at least one test in
    it" -- that second question is what `pytest_guard.py --min-tests`
    floors already answer, per-job.
  - A workflow that is never triggered (wrong `paths:` filter, dead cron)
    still counts as coverage. Trigger reachability is a different gate.
  - Coverage is per-FILE, not per-test. A file whose tests are all
    deselected one by one would still count as covered.
  - Rust `#[test]`s and wasm suites are out of scope; `cargo test` selects
    by crate, not by path, so the drift this gate detects cannot occur
    there in the same shape.

THE RATCHET
-----------
`.ci-test-coverage-inventory`, shrink-only:

    NEW_UNCOVERED  a test file (or unregistered/unselected ctest target)
                   not named by any CI job and not in the ledger. Hard
                   fail. Either wire it into a job, delete it, or ledger it
                   WITH A REASON.
    STALE_ENTRY    a ledgered entry that IS now covered, or that no longer
                   exists. Hard fail -- paid-down debt that stays on the
                   books hides the next regression. Rerun with
                   `--write-inventory` and commit the shrunk ledger.

USAGE
    uv run python scripts/check_ci_test_coverage.py
    uv run python scripts/check_ci_test_coverage.py --write-inventory

EXIT CODES
    0  no dead CI references, and every uncovered test is ledgered
    1  a dead CI reference (direction A), or a new uncovered test /
       stale ledger entry (direction B)
    2  TOOL ERROR -- the scan itself is not trustworthy (zero references
       enumerated, zero test files found, unparseable workflow)
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
INVENTORY = REPO_ROOT / ".ci-test-coverage-inventory"
WORKFLOWS = Path(".github/workflows")
FIRMWARE_CMAKE = Path("firmware/test/CMakeLists.txt")


class ToolError(RuntimeError):
    """The scan itself is untrustworthy. Never reported as a pass."""


# ---------------------------------------------------------------------------
# Where test files live.
#
# Declared explicitly rather than globbed for `test_*.py` repo-wide, because
# the direction-B denominator must be a stable, reviewable set: a new root
# appearing should be a deliberate edit here, visible in a diff, not a silent
# widening or narrowing of what the ratchet measures. Every root that any CI
# job currently names is present -- otherwise the gate would credit coverage
# to files it does not count, and the two halves would not be comparable.
# ---------------------------------------------------------------------------
TEST_ROOT_GLOBS = (
    "packages/*/tests",
    "scripts/tests",
    "tests",
    "elec/validation",
    "firmware/test",
    "firmware/tools",
)

# Top-level loose test modules that live beside their subject rather than in a
# tests/ directory. `scripts/test_root_hygiene.py` is one, and CI runs it.
LOOSE_TEST_GLOBS = ("scripts/test_*.py",)

TEST_FILE_PATTERNS = ("test_*.py",)

# Directory names that are build output or vendored code, never the source of
# truth for "does this test file exist". Keeps the ratchet's denominator from
# depending on whether someone has run cmake or created a venv in this checkout.
EXCLUDED_DIR_PARTS = frozenset(
    {"build", "target", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache"}
)

# Files that match TEST_FILE_PATTERNS but are not pytest modules.
NON_TEST_NAME_PATTERNS = (
    "test_*_generated.c",  # not python; defensive
)

# pytest options that consume the FOLLOWING token as their value, so that
# token must not be mistaken for a path. `--deselect` and `--ignore` are in
# here too but are intercepted before this set is consulted.
SEPARATE_VALUE_OPTS = frozenset(
    {
        "-m",
        "-k",
        "-p",
        "-n",
        "-c",
        "-o",
        "-W",
        "-r",
        "--dist",
        "--tb",
        "--maxfail",
        "--timeout",
        "--rootdir",
        "--junitxml",
        "--cov",
        "--cov-report",
        "--cov-config",
        "--numprocesses",
        "--durations",
        "--min-tests",
        "--max-report-age-seconds",
        "--report",
        "--scratch-dir",
        "--cluster",
    }
)

DESELECT_OPTS = frozenset({"--deselect"})
IGNORE_OPTS = frozenset({"--ignore", "--ignore-glob"})

SHELL_OPERATORS = frozenset({"&&", "||", ";", "|", "&"})

KIND_TARGET = "target"
KIND_DESELECT = "deselect"
KIND_IGNORE = "ignore"


@dataclass(frozen=True)
class CIReference:
    """One path a CI step hands to pytest, already resolved to repo-relative."""

    workflow: str
    job: str
    step: str
    kind: str
    raw: str
    path: str  # repo-relative posix path, file part only (no ::nodeid)
    nodeid: str  # the ::Class::test suffix, or "" -- kept for the report
    cwd: str  # the effective working directory it was resolved against

    @property
    def where(self) -> str:
        return f"{self.workflow}::{self.job}::{self.step}"


@dataclass(frozen=True)
class CTestBinary:
    target: str
    registered_as: tuple[str, ...]  # add_test NAMEs whose COMMAND is this target


@dataclass(frozen=True)
class CTestSelector:
    workflow: str
    job: str
    step: str
    regex: str


# ---------------------------------------------------------------------------
# Shell walking
# ---------------------------------------------------------------------------


def _strip_line_continuations(script: str) -> str:
    return re.sub(r"\\\n[ \t]*", " ", script)


def _strip_comment(line: str) -> str:
    """Drop a trailing `# ...` comment, respecting quotes.

    Deliberately simple: this only has to survive the shell fragments this
    repo's workflows actually contain. A `#` inside a quoted string is kept.
    """
    out: list[str] = []
    quote: str | None = None
    prev = ""
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote and prev != "\\":
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "#" and (not out or out[-1].isspace()):
            break
        else:
            out.append(ch)
        prev = ch
    return "".join(out)


def _tokenize(line: str) -> list[str]:
    lexer = shlex.shlex(line, posix=True, punctuation_chars="();&|<>")
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        # Unbalanced quote in a fragment we do not need to understand.
        return line.split()


def _normalize(cwd: str, arg: str) -> str:
    joined = arg if arg.startswith("/") else os.path.join(cwd, arg)
    norm = os.path.normpath(joined)
    return "." if norm in ("", ".") else norm


def _is_pytest_token(tok: str) -> bool:
    base = tok.rsplit("/", 1)[-1]
    return base == "pytest" or base == "pytest_guard.py"


def _is_ctest_token(tok: str) -> bool:
    return tok.rsplit("/", 1)[-1] == "ctest"


def _looks_like_path(tok: str) -> bool:
    if not tok or tok.startswith("-"):
        return False
    if "$" in tok or "{" in tok:
        return False  # unresolvable; see KNOWN BLIND SPOTS
    return "/" in tok or tok.endswith(".py")


def _split_nodeid(tok: str) -> tuple[str, str]:
    if "::" in tok:
        head, sep, tail = tok.partition("::")
        return head, sep + tail
    return tok, ""


def _pytest_args(tokens: list[str]) -> list[str]:
    """The argv pytest itself sees, given a full command's tokens.

    For a bare `pytest` / `-m pytest` invocation that is everything after the
    `pytest` token. For `scripts/pytest_guard.py --min-tests N -- <argv>` the
    guard's own options come first and the `--` separates them, so only what
    follows the separator is pytest's.
    """
    for i, tok in enumerate(tokens):
        if not _is_pytest_token(tok):
            continue
        rest = tokens[i + 1 :]
        if tok.rsplit("/", 1)[-1] == "pytest_guard.py" and "--" in rest:
            return rest[rest.index("--") + 1 :]
        return rest
    return []


def extract_paths(argv: list[str]) -> list[tuple[str, str]]:
    """(kind, raw-token) for every path-bearing argument in a pytest argv."""
    found: list[tuple[str, str]] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        opt, sep, attached = tok.partition("=")
        if opt in DESELECT_OPTS or opt in IGNORE_OPTS:
            kind = KIND_DESELECT if opt in DESELECT_OPTS else KIND_IGNORE
            if sep:
                value = attached
                i += 1
            else:
                value = argv[i + 1] if i + 1 < len(argv) else ""
                i += 2
            if value:
                found.append((kind, value))
            continue
        if sep and opt.startswith("-"):
            i += 1  # --tb=short, --cov=temper_placer: value is attached, not a path
            continue
        if tok in SEPARATE_VALUE_OPTS:
            i += 2
            continue
        if tok.startswith("-") or tok == "--":
            i += 1
            continue
        if _looks_like_path(tok):
            found.append((KIND_TARGET, tok))
        i += 1
    return found


def _ctest_regexes(tokens: list[str]) -> list[str]:
    out: list[str] = []
    for i, tok in enumerate(tokens):
        if tok in ("-R", "--tests-regex") and i + 1 < len(tokens):
            out.append(tokens[i + 1])
        elif tok.startswith("-R") and len(tok) > 2:
            out.append(tok[2:])
    return out


def _apply_cd(cwd: str, tokens: list[str]) -> str:
    if tokens and tokens[0] == "cd" and len(tokens) > 1:
        target = tokens[1]
        if "$" in target or "{" in target:
            return cwd
        return _normalize(cwd, target)
    return cwd


def commands_with_cwd(script: str, start_cwd: str) -> list[tuple[str, list[str]]]:
    """Walk a `run:` block as a shell script, yielding (cwd, command tokens).

    The cwd is the one in force AT that command: `cd` mutates it, `(` saves it
    and `)` restores it. This is the part that must not be approximated --
    resolving every path against a single package is what produced a hand
    count of 10 dead references where the truth was 8.
    """
    out: list[tuple[str, list[str]]] = []
    cwd = start_cwd
    stack: list[str] = []
    for raw_line in _strip_line_continuations(script).splitlines():
        line = _strip_comment(raw_line).strip()
        if not line:
            continue
        command: list[str] = []
        for tok in _tokenize(line):
            if tok in ("(", ")") or tok in SHELL_OPERATORS:
                if command:
                    out.append((cwd, command))
                    cwd = _apply_cd(cwd, command)
                    command = []
                if tok == "(":
                    stack.append(cwd)
                elif tok == ")":
                    cwd = stack.pop() if stack else cwd
                continue
            command.append(tok)
        if command:
            out.append((cwd, command))
            cwd = _apply_cd(cwd, command)
    return out


# ---------------------------------------------------------------------------
# Workflow parsing
# ---------------------------------------------------------------------------


def _steps(workflow: dict):
    for job_id, job in (workflow.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        job_wd = ((job.get("defaults") or {}).get("run") or {}).get("working-directory")
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            run = step.get("run")
            if not isinstance(run, str):
                continue
            wd = step.get("working-directory") or job_wd or "."
            yield job_id, str(step.get("name") or "<unnamed>"), str(wd), run


def parse_workflows(repo_root: Path) -> tuple[list[CIReference], list[CTestSelector]]:
    refs: list[CIReference] = []
    selectors: list[CTestSelector] = []
    wf_dir = repo_root / WORKFLOWS
    if not wf_dir.is_dir():
        raise ToolError(f"no workflow directory at {wf_dir}")
    paths = sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml"))
    if not paths:
        raise ToolError(f"no workflow files under {wf_dir}")
    for wf_path in paths:
        try:
            doc = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ToolError(f"{wf_path.name}: unparseable YAML: {exc}") from exc
        if not isinstance(doc, dict):
            continue
        for job_id, step_name, wd, run in _steps(doc):
            start = _normalize(".", wd)
            for cwd, tokens in commands_with_cwd(run, start):
                if any(_is_ctest_token(t) for t in tokens):
                    for rx in _ctest_regexes(tokens):
                        selectors.append(
                            CTestSelector(wf_path.name, job_id, step_name, rx)
                        )
                argv = _pytest_args(tokens)
                if not argv:
                    continue
                for kind, raw in extract_paths(argv):
                    head, nodeid = _split_nodeid(raw)
                    refs.append(
                        CIReference(
                            workflow=wf_path.name,
                            job=job_id,
                            step=step_name,
                            kind=kind,
                            raw=raw,
                            path=_normalize(cwd, head),
                            nodeid=nodeid,
                            cwd=cwd,
                        )
                    )
    return refs, selectors


# ---------------------------------------------------------------------------
# Direction A -- dead CI references
# ---------------------------------------------------------------------------


def dead_references(refs: list[CIReference], repo_root: Path) -> list[CIReference]:
    """Every reference whose path does not exist on disk.

    THE comparison for direction A. Neutering it (returning `[]`, or
    reversing the existence test) must turn
    `test_direction_a_detects_a_deleted_file` red; that is proved by
    `scripts/tests/test_check_ci_test_coverage.py`.
    """
    dead: list[CIReference] = []
    for ref in refs:
        if not (repo_root / ref.path).exists():
            dead.append(ref)
    return dead


# ---------------------------------------------------------------------------
# Test-file discovery
# ---------------------------------------------------------------------------


def _is_test_file(path: Path) -> bool:
    name = path.name
    if not any(fnmatch.fnmatch(name, pat) for pat in TEST_FILE_PATTERNS):
        return False
    if any(fnmatch.fnmatch(name, pat) for pat in NON_TEST_NAME_PATTERNS):
        return False
    return path.suffix == ".py"


def discover_test_files(repo_root: Path) -> set[str]:
    found: set[str] = set()
    for root_glob in TEST_ROOT_GLOBS:
        for root in sorted(repo_root.glob(root_glob)):
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*.py")):
                # A COPY of a test file inside a build tree is not a test file
                # the repository owns. `firmware/test/build/` in particular is
                # created by the firmware job's own `cmake -B firmware/test/build
                # firmware/test`, so without this the ratchet's denominator
                # would depend on whether anyone had run cmake in this checkout.
                if set(path.parts) & EXCLUDED_DIR_PARTS:
                    continue
                if _is_test_file(path):
                    found.add(path.relative_to(repo_root).as_posix())
    for loose in LOOSE_TEST_GLOBS:
        for path in sorted(repo_root.glob(loose)):
            if path.is_file() and _is_test_file(path):
                found.add(path.relative_to(repo_root).as_posix())
    return found


# ---------------------------------------------------------------------------
# Direction B -- test files no CI job runs
# ---------------------------------------------------------------------------


def _expand(ref_path: str, repo_root: Path, universe: set[str]) -> set[str]:
    """Which known test files a single reference selects."""
    abs_path = repo_root / ref_path
    if abs_path.is_dir():
        prefix = ref_path.rstrip("/") + "/"
        return {f for f in universe if f.startswith(prefix)}
    if ref_path in universe:
        return {ref_path}
    if any(ch in ref_path for ch in "*?["):
        return {f for f in universe if fnmatch.fnmatch(f, ref_path)}
    return set()


def covered_test_files(
    refs: list[CIReference], repo_root: Path, universe: set[str]
) -> set[str]:
    """Which test files at least one CI invocation actually runs.

    THE comparison for direction B. Coverage is a UNION over invocations;
    `--ignore` subtracts only within the invocation that carries it, so a
    file ignored by one job and targeted by another is covered. `--deselect`
    never subtracts a file: its remaining tests still run.
    """
    by_invocation: dict[tuple[str, str, str], list[CIReference]] = {}
    for ref in refs:
        by_invocation.setdefault((ref.workflow, ref.job, ref.step), []).append(ref)

    covered: set[str] = set()
    for group in by_invocation.values():
        selected: set[str] = set()
        ignored: set[str] = set()
        for ref in group:
            if ref.kind == KIND_TARGET:
                selected |= _expand(ref.path, repo_root, universe)
            elif ref.kind == KIND_IGNORE:
                ignored |= _expand(ref.path, repo_root, universe)
        covered |= selected - ignored
    return covered


# ---------------------------------------------------------------------------
# CTest
# ---------------------------------------------------------------------------

_ADD_EXECUTABLE = re.compile(r"add_executable\s*\(\s*([A-Za-z0-9_]+)", re.MULTILINE)
_ADD_TEST = re.compile(
    r"add_test\s*\(\s*NAME\s+([A-Za-z0-9_]+)\s+COMMAND\s+([A-Za-z0-9_${}]+)",
    re.MULTILINE | re.DOTALL,
)


def parse_ctest(repo_root: Path) -> tuple[list[CTestBinary], dict[str, str]]:
    """(test binaries with their registrations, {add_test NAME: target}).

    A binary named `test_*` that no `add_test(... COMMAND it)` names can
    never be selected by ctest under any `-R`, no matter what CI asks for --
    that is the shape that hid a thermistor conversion wrong by ~60 C.
    """
    cmake = repo_root / FIRMWARE_CMAKE
    if not cmake.is_file():
        return [], {}
    text = cmake.read_text(encoding="utf-8")
    text = re.sub(r"(?m)#.*$", "", text)
    registrations: dict[str, str] = dict(_ADD_TEST.findall(text))
    by_target: dict[str, list[str]] = {}
    for name, target in registrations.items():
        by_target.setdefault(target, []).append(name)
    binaries = [
        CTestBinary(target=t, registered_as=tuple(sorted(by_target.get(t, []))))
        for t in sorted(set(_ADD_EXECUTABLE.findall(text)))
        if t.startswith("test_")
    ]
    return binaries, registrations


def ctest_selected(
    registrations: dict[str, str], selectors: list[CTestSelector]
) -> set[str]:
    selected: set[str] = set()
    for name in registrations:
        for sel in selectors:
            try:
                if re.search(sel.regex, name):
                    selected.add(name)
                    break
            except re.error:
                continue
    return selected


def top_level_alternatives(regex: str) -> list[str]:
    """Split a regex on `|` at nesting depth zero.

    `ctest -R "state_machine|fault_list"` is TWO requests, and an alternation
    hides a dead one perfectly: the whole pattern still matches something, so
    a whole-pattern check reports it green while one half selects nothing.
    That is not hypothetical here -- see `dead_ctest_selectors`.
    """
    parts: list[str] = []
    depth = 0
    in_class = False
    current: list[str] = []
    prev = ""
    for ch in regex:
        if prev == "\\":
            current.append(ch)
            prev = ""
            continue
        if ch == "\\":
            current.append(ch)
            prev = ch
            continue
        if in_class:
            current.append(ch)
            if ch == "]":
                in_class = False
            continue
        if ch == "[":
            in_class = True
            current.append(ch)
        elif ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p for p in parts if p]


def dead_ctest_selectors(
    registrations: dict[str, str], selectors: list[CTestSelector]
) -> list[CTestSelector]:
    """CI `ctest -R <regex>` requests that select no registered test.

    Direction A for ctest: `ctest` exits 0 on an empty selection unless
    `--no-tests=error` is passed, so this is silent by default.

    Each TOP-LEVEL ALTERNATIVE is checked separately, not just the pattern as
    a whole. `firmware-tests.yml` builds `test_state_machine_only` and
    `test_fault_list_only` and then runs
    `ctest -R "state_machine|fault_list"` -- but `firmware/test/CMakeLists.txt`
    registers no `add_test` whose NAME contains `fault_list`, so that half
    selects nothing, the binary that was just compiled is never executed, and
    the whole-pattern check would call it green because the OTHER half
    matches.
    """
    dead: list[CTestSelector] = []
    for sel in selectors:
        for alternative in top_level_alternatives(sel.regex):
            try:
                if not any(re.search(alternative, name) for name in registrations):
                    dead.append(
                        sel
                        if alternative == sel.regex
                        else CTestSelector(
                            sel.workflow, sel.job, sel.step, alternative
                        )
                    )
            except re.error:
                dead.append(
                    CTestSelector(sel.workflow, sel.job, sel.step, alternative)
                )
    return dead


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

INVENTORY_HEADER = """\
# Tests that exist and that NO CI job runs (direction B of
# scripts/check_ci_test_coverage.py -- see that script's docstring).
#
# Three kinds, tab-separated `<kind>\\t<identifier>\\t<reason>`:
#
#   pytest-uncovered      a test_*.py under a declared TEST_ROOT_GLOBS root
#                         that no CI pytest invocation names.
#   ctest-unregistered    a firmware add_executable(test_*) target with no
#                         add_test(NAME ... COMMAND it) -- ctest cannot run
#                         it under ANY -R.
#   ctest-unselected      a registered add_test NAME that no CI
#                         `ctest -R <regex>` selects.
#
# SHRINK-ONLY. A new entry is a hard failure: wire it into a job, delete it,
# or add it here WITH A REASON. An entry that becomes covered -- or whose
# file stops existing -- is ALSO a failure, so paid-down debt shows up in a
# diff instead of rotting on the books.
#
# This ledger is the honest count at the moment the gate landed. It is
# deliberately NOT pre-shrunk: some of these are legitimately excluded
# (nightly-only, hardware-dependent, superseded) and some are real gaps, and
# a ratchet that starts at the true number is the only one that can be
# trusted to move. Sorting them apart is separate work.
#
# Generated by: uv run python scripts/check_ci_test_coverage.py --write-inventory
"""

DEFAULT_REASON = "unsorted-at-gate-landing"


def read_inventory(path: Path) -> dict[tuple[str, str], str]:
    entries: dict[tuple[str, str], str] = {}
    if not path.is_file():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("\t")
        if len(parts) < 2:
            raise ToolError(f"{path.name}: malformed entry (needs tabs): {line!r}")
        kind, ident = parts[0].strip(), parts[1].strip()
        reason = parts[2].strip() if len(parts) > 2 else ""
        entries[(kind, ident)] = reason
    return entries


def write_inventory(
    path: Path, current: list[tuple[str, str]], previous: dict[tuple[str, str], str]
) -> None:
    lines = [INVENTORY_HEADER]
    for kind, ident in sorted(current):
        reason = previous.get((kind, ident)) or DEFAULT_REASON
        lines.append(f"{kind}\t{ident}\t{reason}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Anti-vacuity on the denominator
# ---------------------------------------------------------------------------


def require_nonvacuous(
    refs: list[CIReference], universe: set[str], covered: set[str]
) -> None:
    """Raise unless the scan produced something to compare.

    A collapsed count is a TOOL ERROR, never a clean run: "0 dead references"
    computed over 0 enumerated references is the exact shape of the
    instruments this repo already has too many of.

    The three checks are LAYERED ON PURPOSE and each one subsumes the next,
    so no single one of them is individually falsifiable -- deleting the
    `refs` check alone still leaves the `covered` check to catch an empty
    scan. That is defence in depth, and it is why the mutation suite in
    `scripts/tests/test_check_ci_test_coverage.py` mutates this function as a
    WHOLE (`anti-vacuity-strip-all-guards`) rather than pretending a
    single-line strip is a killable mutant. A mutation that cannot be killed
    is not evidence, and this file does not carry any.
    """
    if not refs:
        raise ToolError(
            "enumerated ZERO CI-referenced test paths -- the workflow parser is "
            "broken or the workflows moved. This is a tool error, not a pass."
        )
    if not universe:
        raise ToolError(
            "enumerated ZERO test files on disk -- TEST_ROOT_GLOBS is broken or "
            "the tree moved. This is a tool error, not a pass."
        )
    if not covered:
        raise ToolError(
            "ZERO test files matched by any CI reference, though both counts are "
            "non-empty -- path resolution is broken. This is a tool error."
        )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class Result:
    referenced_paths: int
    covered_files: int
    test_files: int
    dead_refs: list[CIReference]
    dead_selectors: list[CTestSelector]
    uncovered: list[tuple[str, str]]
    new_uncovered: list[tuple[str, str]]
    stale_entries: list[tuple[str, str]]

    @property
    def ok(self) -> bool:
        return not (
            self.dead_refs
            or self.dead_selectors
            or self.new_uncovered
            or self.stale_entries
        )


def analyze(repo_root: Path, inventory_path: Path) -> Result:
    refs, selectors = parse_workflows(repo_root)
    universe = discover_test_files(repo_root)

    covered = covered_test_files(refs, repo_root, universe)
    require_nonvacuous(refs, universe, covered)

    binaries, registrations = parse_ctest(repo_root)
    selected = ctest_selected(registrations, selectors)

    uncovered: list[tuple[str, str]] = [
        ("pytest-uncovered", f) for f in sorted(universe - covered)
    ]
    uncovered += [
        ("ctest-unregistered", b.target)
        for b in binaries
        if not b.registered_as
    ]
    uncovered += [
        ("ctest-unselected", name)
        for name in sorted(registrations)
        if name not in selected
    ]

    previous = read_inventory(inventory_path)
    current = set(uncovered)
    new_uncovered = sorted(current - set(previous))
    stale_entries = sorted(set(previous) - current)

    return Result(
        referenced_paths=len(refs),
        covered_files=len(covered),
        test_files=len(universe),
        dead_refs=dead_references(refs, repo_root),
        dead_selectors=dead_ctest_selectors(registrations, selectors),
        uncovered=uncovered,
        new_uncovered=new_uncovered,
        stale_entries=stale_entries,
    )


def report(result: Result, out=None) -> None:
    # Resolved at CALL time, not at import time: a default of `sys.stdout`
    # binds the interpreter's original stream and would silently bypass any
    # later redirection -- including pytest's capture, which would leave the
    # "are both counts printed" test asserting against an empty string.
    stream = sys.stdout if out is None else out
    p = lambda *a: print(*a, file=stream)  # noqa: E731
    p("CI <-> test-tree coverage")
    p("=" * 72)
    # Printed on EVERY run, pass or fail: a denominator collapsing to zero
    # must be visible, not inferable.
    p(f"  CI-referenced test paths enumerated : {result.referenced_paths}")
    p(f"  test files on disk                  : {result.test_files}")
    p(f"  test files at least one CI job runs : {result.covered_files}")
    p("")

    p(f"DIRECTION A -- dead CI references: {len(result.dead_refs) + len(result.dead_selectors)}")
    if result.dead_refs or result.dead_selectors:
        for ref in result.dead_refs:
            p(f"  DEAD  {ref.path}")
            p(f"        named as {ref.kind!r} ({ref.raw})")
            p(f"        in {ref.where}")
            p(f"        resolved against working directory {ref.cwd!r}")
            p(
                "        pytest exits 4 with ZERO tests collected on a "
                "nonexistent path -- this step runs NOTHING."
            )
        for sel in result.dead_selectors:
            p(f"  DEAD  ctest -R {sel.regex!r} matches no registered test")
            p(f"        in {sel.workflow}::{sel.job}::{sel.step}")
            p("        ctest exits 0 on an empty selection -- silent by default.")
    else:
        p("  (none -- every path a CI job names exists)")
    p("")

    p(f"DIRECTION B -- test files no CI job runs: {len(result.uncovered)}")
    p(f"  ledgered  : {len(result.uncovered) - len(result.new_uncovered)}")
    p(f"  NEW       : {len(result.new_uncovered)}")
    p(f"  stale     : {len(result.stale_entries)}")
    for kind, ident in result.new_uncovered:
        p(f"  NEW_UNCOVERED  [{kind}] {ident}")
    for kind, ident in result.stale_entries:
        p(f"  STALE_ENTRY    [{kind}] {ident} -- now covered or gone; rerun "
          "--write-inventory")
    p("")
    p("VERDICT: " + ("PASS" if result.ok else "FAIL"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--inventory", type=Path, default=None)
    parser.add_argument(
        "--write-inventory",
        action="store_true",
        help="rewrite the direction-B ledger to the current true set",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    inventory = args.inventory or (repo_root / INVENTORY.name)

    try:
        result = analyze(repo_root, inventory)
    except ToolError as exc:
        print(f"TOOL ERROR: {exc}", file=sys.stderr)
        return 2

    if args.write_inventory:
        write_inventory(inventory, result.uncovered, read_inventory(inventory))
        print(f"wrote {len(result.uncovered)} entries to {inventory}")
        result = analyze(repo_root, inventory)

    report(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
