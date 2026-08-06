#!/usr/bin/env python3
"""Mutation-testing harness for packages/temper-io-types/src/dag_expr.rs.

Built for PR #731's mutation-corpus gate (>= 15 mutants evaluated), and kept
here so the gate is re-runnable rather than a one-off scratchpad script that
disappears the moment the disk fills up (which is exactly what happened to
the original harness).

Each ``Mutant`` below is a set of line-range ``Hunk``s against the CURRENT
text of dag_expr.rs. Applying a mutant is a three-step, per-mutant cycle:

    1. Verify every hunk's ``expected`` lines match the file on disk EXACTLY
       (line-for-line). If they don't, the source has drifted since this
       mutant was written and the harness refuses to guess -- it aborts
       loudly rather than silently mutating the wrong text or no-opping.
    2. Rebuild ONLY the temper-io-types pyo3 extension
       (`maturin develop --release`) and run the three dag_expr verification
       suites under pytest.
    3. Revert the file to the pristine original and byte-compare it back,
       before moving to the next mutant.

Verdict rules (see the module docstring's "two traps" below for why these
matter):
  - build failure to compile          -> KILLED (build)
  - pytest exits nonzero              -> KILLED, cites the first FAILED test id
  - pytest exits zero AND the total
    collected-test count matches the
    pinned baseline                   -> SURVIVED
  - pytest exits zero but the
    collected count does NOT match    -> INCONCLUSIVE (never silently SURVIVED)

Two traps this harness exists to defend against (both cost real time on this
PR's first pass):
  1. A mutation that does not actually land on disk proves nothing. Every
     hunk's ``expected`` text is checked against the live file before AND
     after mutation, and the file is byte-compared back to the pristine
     original after revert.
  2. A test that merely touches the mutated code is not the same as a test
     that discriminates the defect. A SURVIVED verdict is reported as-is --
     it is a finding about corpus coverage, not something to be swapped away
     by picking an easier mutant.

Usage:
    source scripts/cargo_shared_env.sh
    uv run --no-sync python tools/mutation/dag_expr_mutants.py
    uv run --no-sync python tools/mutation/dag_expr_mutants.py --list
    uv run --no-sync python tools/mutation/dag_expr_mutants.py --only nbsp_not_stripped cmp_swap_lt_gt
"""

from __future__ import annotations

import argparse
import dataclasses
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET_FILE = REPO_ROOT / "packages" / "temper-io-types" / "src" / "dag_expr.rs"
CARGO_MANIFEST = REPO_ROOT / "packages" / "temper-io-types" / "Cargo.toml"
PERF_TEST_PATH = "packages/temper-placer/tests/pipeline/test_dag_expr_perf.py"
CORRECTNESS_TEST_PATHS = (
    "packages/temper-placer/tests/pipeline/test_dag_expr_rust_differential.py",
    "packages/temper-placer/tests/pipeline/test_dag_expr_properties.py",
)
TEST_PATHS = (*CORRECTNESS_TEST_PATHS, PERF_TEST_PATH)
#: Pinned by a baseline run on a clean checkout. If pytest ever collects a
#: different number of tests than this, something about the suite's
#: collection changed and a SURVIVED verdict from that run is not trustworthy
#: -- report INCONCLUSIVE instead of quietly treating it as a pass.
BASELINE_COLLECTED = 230
#: Stop rather than risk repeating the disk-full incident that originally
#: killed this PR's gate run.
MIN_FREE_GB = 8.0

#: The two perf-suite tests each carry TWO assertions: a genuine parity
#: check ("arms diverged DURING the timed run", reusing the same corpus as
#: the differential) and a timing-ratio check ("... SLOWER than Python").
#: The ratio check is measured, empirically, to be FLAKY on a loaded
#: development machine: it fails on a completely clean, unmutated checkout
#: in 2 of 3 repeated runs (machine contention from concurrent worktrees,
#: not the code under test). A mutant whose ONLY failure is that ratio
#: assertion is not a trustworthy kill -- see `_perf_ratio_only_failure`.
_PERF_RATIO_MARKER = "SLOWER than Python"
_PERF_PARITY_MARKER = "diverged DURING the timed run"
_PERF_TEST_IDS = {
    f"{PERF_TEST_PATH}::test_parse_perf_ab_with_parity",
    f"{PERF_TEST_PATH}::test_eval_perf_ab_with_parity",
}


class MutationError(RuntimeError):
    """The source on disk does not match what a mutant expects."""


@dataclasses.dataclass(frozen=True)
class Hunk:
    """A contiguous, 1-indexed inclusive line range to replace."""

    start_line: int
    end_line: int
    expected: tuple[str, ...]
    replacement: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.end_line - self.start_line + 1 != len(self.expected):
            raise ValueError(f"hunk at {self.start_line}-{self.end_line} expected-length mismatch")
        if self.expected == self.replacement:
            raise ValueError(f"hunk at {self.start_line}-{self.end_line} is a no-op mutation")


@dataclasses.dataclass(frozen=True)
class Mutant:
    id: str
    category: str
    description: str
    hunks: tuple[Hunk, ...]


# ---------------------------------------------------------------------------
# The mutant catalog
# ---------------------------------------------------------------------------
#
# Deliberately NOT the five already killed on the PR (python_strip charset,
# tokenizer keyword \b order, the '' wart, byte-vs-char positions, error
# message wording) -- these target adjacent, distinct mechanisms in the same
# territory. Re-confirming the original five is fine but is not what these
# are for.

MUTANTS: list[Mutant] = [
    Mutant(
        id="nbsp_not_stripped",
        category="is_python_space / python_strip",
        description="Drop NBSP (U+00A0) from is_python_space's charset, so a "
        "NBSP-padded expression is no longer stripped before tokenizing.",
        hunks=(
            Hunk(
                101,
                101,
                ("            | '\\u{a0}'            // NO-BREAK SPACE",),
                (),
            ),
        ),
    ),
    Mutant(
        id="strip_leading_only",
        category="is_python_space / python_strip",
        description="python_strip only trims the LEADING whitespace run "
        "(trim_start_matches instead of trim_matches), leaving trailing "
        "whitespace like the U+001C pad unstripped.",
        hunks=(
            Hunk(
                114,
                114,
                ("    s.trim_matches(is_python_space)",),
                ("    s.trim_start_matches(is_python_space)",),
            ),
        ),
    ),
    Mutant(
        id="dot_before_number",
        category="TokKind ordering / longest match",
        description="Swap the NUMBER and DOT matchers' positions in the "
        "tokenizer's alternation chain, so a leading-dot float like '.5' "
        "tokenizes as DOT then NUMBER('5') instead of one NUMBER token.",
        hunks=(
            Hunk(
                256,
                256,
                ("            .or_else(|| match_simple(&pats.number, TokKind::Num, source, bpos))",),
                ('            .or_else(|| match_literal(".", TokKind::Dot, source, bpos))',),
            ),
            Hunk(
                271,
                271,
                ('            .or_else(|| match_literal(".", TokKind::Dot, source, bpos))',),
                ("            .or_else(|| match_simple(&pats.number, TokKind::Num, source, bpos))",),
            ),
        ),
    ),
    Mutant(
        id="ident_before_keywords",
        category="TokKind ordering / longest match",
        description="Try IDENT before any of the \\b-terminated keyword "
        "matchers, so 'true'/'false'/'null'/'and'/'or'/'not' all tokenize as "
        "plain identifiers instead of their keyword kinds.",
        hunks=(
            Hunk(
                256,
                256,
                ("            .or_else(|| match_simple(&pats.number, TokKind::Num, source, bpos))",),
                ("            .or_else(|| match_simple(&pats.ident, TokKind::Ident, source, bpos))",),
            ),
            Hunk(
                272,
                272,
                ("            .or_else(|| match_simple(&pats.ident, TokKind::Ident, source, bpos))",),
                ("            .or_else(|| match_simple(&pats.number, TokKind::Num, source, bpos))",),
            ),
        ),
    ),
    Mutant(
        id="lt_before_lte",
        category="match_literal boundary / ordering",
        description="Try the single-char '<' literal before the two-char "
        "'<=' literal, so '<=' tokenizes as LT then an unmatched '=' "
        "character instead of one LTE token.",
        hunks=(
            Hunk(
                265,
                265,
                ('            .or_else(|| match_literal("<=", TokKind::Lte, source, bpos))',),
                ('            .or_else(|| match_literal("<", TokKind::Lt, source, bpos))',),
            ),
            Hunk(
                267,
                267,
                ('            .or_else(|| match_literal("<", TokKind::Lt, source, bpos))',),
                ('            .or_else(|| match_literal("<=", TokKind::Lte, source, bpos))',),
            ),
        ),
    ),
    Mutant(
        id="skip_tabs_only",
        category="match_skip boundary",
        description="SKIP only consumes tabs ([\\t]+), not plain spaces, so "
        "any space-separated expression raises 'Unexpected character' on "
        "the first space.",
        hunks=(
            Hunk(
                229,
                229,
                ('                skip: Regex::new(r"[ \\t]+").ok()?,',),
                ('                skip: Regex::new(r"[\\t]+").ok()?,',),
            ),
        ),
    ),
    Mutant(
        id="string_empty_check_inverted",
        category="match_string boundary",
        description="Invert the group(1)-truthiness check in match_string, "
        "so a NON-empty single-quoted string like 'abc' falls through to "
        "None (the empty-string wart applied to the wrong case) instead of "
        "keeping its text.",
        hunks=(
            Hunk(
                348,
                348,
                ("        Some(s) if !s.is_empty() => Some(s.to_string()),",),
                ("        Some(s) if s.is_empty() => Some(s.to_string()),",),
            ),
        ),
    ),
    Mutant(
        id="match_simple_anchor_removed",
        category="match_simple boundary",
        description="Drop match_simple's `m.start() != bpos` anchor check, "
        "so a regex-based matcher (NUMBER/keywords/IDENT) may match "
        "somewhere AFTER the cursor and silently swallow intervening "
        "unexpected characters instead of raising on them.",
        hunks=(
            Hunk(
                311,
                313,
                (
                    "    if m.start() != bpos {",
                    "        return None;",
                    "    }",
                ),
                (),
            ),
        ),
    ),
    Mutant(
        id="cpos_increment_by_one",
        category="char_len / byte-vs-char arithmetic",
        description="Advance the character cursor by 1 per token instead of "
        "by the token's actual character length, so every reported error "
        "position after the first multi-char token is wrong.",
        hunks=(
            Hunk(
                282,
                282,
                ("                cpos += consumed;",),
                ("                cpos += 1;",),
            ),
        ),
    ),
    Mutant(
        id="cmp_swap_lt_gt",
        category="CmpOp comparison",
        description="Map the LT token to CmpOp::Gt and the GT token to "
        "CmpOp::Lt in the parser's comparison(), so '<' and '>' parse with "
        "swapped semantics.",
        hunks=(
            Hunk(
                549,
                549,
                ("            TokKind::Lt => Some(CmpOp::Lt),",),
                ("            TokKind::Lt => Some(CmpOp::Gt),",),
            ),
            Hunk(
                550,
                550,
                ("            TokKind::Gt => Some(CmpOp::Gt),",),
                ("            TokKind::Gt => Some(CmpOp::Lt),",),
            ),
        ),
    ),
    Mutant(
        id="not_chain_parity_cancel",
        category="negation",
        description="Collapse a chain of 'not' by PARITY (wrap once if odd "
        "count, not at all if even) instead of wrapping once per literal "
        "'not' token, so 'not not true' parses to a bare Bool(true) instead "
        "of nested UnaryOp(Not, UnaryOp(Not, ...)).",
        hunks=(
            Hunk(
                536,
                539,
                (
                    "        for _ in 0..nots {",
                    "            node = Node::Not(Box::new(node));",
                    "            self.leave();",
                    "        }",
                ),
                (
                    "        if nots % 2 == 1 {",
                    "            node = Node::Not(Box::new(node));",
                    "        }",
                    "        for _ in 0..nots {",
                    "            self.leave();",
                    "        }",
                ),
            ),
        ),
    ),
    Mutant(
        id="or_operand_swap",
        category="Parser associativity",
        description="Swap the operand order when building an Or node in "
        "expr(), so 'a or b' builds Or(b, a) instead of Or(a, b) -- breaks "
        "left-associativity and evaluation order.",
        hunks=(
            Hunk(
                506,
                506,
                ("            left = Node::Or(Box::new(left), Box::new(right));",),
                ("            left = Node::Or(Box::new(right), Box::new(left));",),
            ),
        ),
    ),
    Mutant(
        id="and_operand_swap",
        category="Parser associativity",
        description="Swap the operand order when building an And node in "
        "and_expr(), so 'a and b' builds And(b, a) instead of And(a, b).",
        hunks=(
            Hunk(
                518,
                518,
                ("            left = Node::And(Box::new(left), Box::new(right));",),
                ("            left = Node::And(Box::new(right), Box::new(left));",),
            ),
        ),
    ),
    Mutant(
        id="missing_rparen_check",
        category="Parser error paths",
        description="Drop the expect(RPAREN) check after parsing a "
        "parenthesised sub-expression, so '(true' (missing close paren) "
        "parses successfully instead of raising a syntax error.",
        hunks=(
            Hunk(
                573,
                573,
                ("                self.expect(TokKind::RParen)?;",),
                (),
            ),
        ),
    ),
    Mutant(
        id="accessor_field_unchecked",
        category="Parser error paths",
        description="Accept any token (not just IDENT) as the field name "
        "after 'ns.', so 'config..a' (double dot) parses partway instead of "
        "raising 'Expected IDENT, got DOT'.",
        hunks=(
            Hunk(
                598,
                598,
                ("                    let field = self.expect(TokKind::Ident)?;",),
                ("                    let field = self.advance()?;",),
            ),
        ),
    ),
    Mutant(
        id="bare_ident_error_kind_flip",
        category="ExprError type",
        description="Raise the bare-identifier error as ErrKind::Runtime "
        "(-> DAGExprError) instead of ErrKind::Syntax (-> "
        "DAGExprSyntaxError), changing the exception CLASS while keeping "
        "the message text identical.",
        hunks=(
            Hunk(
                601,
                601,
                ("                    return Err(ExprError::syntax(format!(",),
                ("                    return Err(ExprError::runtime(format!(",),
            ),
        ),
    ),
    Mutant(
        id="recursion_limit_error_kind_flip",
        category="ExprError type",
        description="Raise the parser recursion-limit error as "
        "ErrKind::Syntax (-> DAGExprSyntaxError) instead of "
        "ErrKind::Runtime (-> DAGExprError).",
        hunks=(
            Hunk(
                483,
                483,
                ("            return Err(ExprError::runtime(format!(",),
                ("            return Err(ExprError::syntax(format!(",),
            ),
        ),
    ),
    Mutant(
        id="resolve_attr_single_read",
        category="pyo3 boundary: attribute resolution",
        description="Reuse the first getattr() result instead of "
        "re-fetching, collapsing resolve_attr's deliberate double read "
        "(hasattr-then-getattr) into a single read -- observable only via a "
        "property with side effects.",
        hunks=(
            Hunk(
                758,
                758,
                ("            Ok(_) => Ok(obj.getattr(field)?.unbind()),",),
                ("            Ok(v) => Ok(v.unbind()),",),
            ),
        ),
    ),
    Mutant(
        id="and_short_circuit_removed",
        category="pyo3 boundary: eval short-circuit",
        description="Always evaluate BOTH operands of 'and' before "
        "combining (logically correct result, but the RHS is evaluated "
        "even when the LHS is falsy) -- observable only via a "
        "side-effecting RHS.",
        hunks=(
            Hunk(
                782,
                790,
                (
                    "            CNode::And(l, r) => {",
                    "                let lv = eval(py, l, config, state, context)?;",
                    "                if !lv.bind(py).is_truthy()? {",
                    "                    return Ok(PyBool::new(py, false).to_owned().into_any().unbind());",
                    "                }",
                    "                let rv = eval(py, r, config, state, context)?;",
                    "                let t = rv.bind(py).is_truthy()?;",
                    "                Ok(PyBool::new(py, t).to_owned().into_any().unbind())",
                    "            }",
                ),
                (
                    "            CNode::And(l, r) => {",
                    "                let lv = eval(py, l, config, state, context)?;",
                    "                let lt = lv.bind(py).is_truthy()?;",
                    "                let rv = eval(py, r, config, state, context)?;",
                    "                let rt = rv.bind(py).is_truthy()?;",
                    "                Ok(PyBool::new(py, lt && rt).to_owned().into_any().unbind())",
                    "            }",
                ),
            ),
        ),
    ),
    Mutant(
        id="max_depth_off_by_one",
        category="Parser recursion ceiling (boundary probe)",
        description="Reject at depth >= MAX_DEPTH instead of > MAX_DEPTH, "
        "tightening the recursion ceiling by exactly one frame. The "
        "differential's deepest nested case is 120 levels (~480 frames, "
        "well under 1000) and the witness case is 5000 levels (~20000 "
        "frames, hits the ceiling either way) -- this probes whether "
        "anything tests the exact MAX_DEPTH boundary itself.",
        hunks=(
            Hunk(
                482,
                482,
                ("        if self.depth > MAX_DEPTH {",),
                ("        if self.depth >= MAX_DEPTH {",),
            ),
        ),
    ),
    Mutant(
        id="or_ignores_left_operand",
        category="pyo3 boundary: eval short-circuit",
        description="Drop the early truthy-LHS return in 'or' evaluation "
        "without recombining, so the result is just the RHS's truthiness -- "
        "'true or false' evaluates to False instead of True.",
        hunks=(
            Hunk(
                793,
                801,
                (
                    "            CNode::Or(l, r) => {",
                    "                let lv = eval(py, l, config, state, context)?;",
                    "                if lv.bind(py).is_truthy()? {",
                    "                    return Ok(PyBool::new(py, true).to_owned().into_any().unbind());",
                    "                }",
                    "                let rv = eval(py, r, config, state, context)?;",
                    "                let t = rv.bind(py).is_truthy()?;",
                    "                Ok(PyBool::new(py, t).to_owned().into_any().unbind())",
                    "            }",
                ),
                (
                    "            CNode::Or(l, r) => {",
                    "                let _lv = eval(py, l, config, state, context)?;",
                    "                let rv = eval(py, r, config, state, context)?;",
                    "                let t = rv.bind(py).is_truthy()?;",
                    "                Ok(PyBool::new(py, t).to_owned().into_any().unbind())",
                    "            }",
                ),
            ),
        ),
    ),
]

_IDS = [m.id for m in MUTANTS]
assert len(_IDS) == len(set(_IDS)), "duplicate mutant id"


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def read_lines(path: Path) -> tuple[list[str], bool]:
    text = path.read_text(encoding="utf-8")
    trailing_newline = text.endswith("\n")
    lines = text.split("\n")
    if trailing_newline:
        lines = lines[:-1]
    return lines, trailing_newline


def write_lines(path: Path, lines: list[str], trailing_newline: bool) -> None:
    text = "\n".join(lines) + ("\n" if trailing_newline else "")
    path.write_text(text, encoding="utf-8")


def apply_mutant(lines: list[str], mutant: Mutant) -> list[str]:
    """Return a NEW list with `mutant`'s hunks applied, bottom-up.

    Bottom-up (highest start_line first) so that a hunk whose replacement
    has a different line count doesn't shift the line numbers of hunks
    still to be applied within the same mutant.
    """
    out = list(lines)
    for hunk in sorted(mutant.hunks, key=lambda h: h.start_line, reverse=True):
        actual = tuple(out[hunk.start_line - 1 : hunk.end_line])
        if actual != hunk.expected:
            raise MutationError(
                f"mutant {mutant.id!r}: hunk {hunk.start_line}-{hunk.end_line} "
                f"does not match the file on disk.\n  expected: {hunk.expected!r}\n  actual:   {actual!r}\n"
                "The source has drifted since this mutant was written; fix the hunk before trusting any verdict."
            )
        out[hunk.start_line - 1 : hunk.end_line] = list(hunk.replacement)
    return out


def validate_all(lines: list[str]) -> None:
    """Dry-run every mutant's hunks against the pristine file before doing
    any building at all, so a transcription error aborts immediately."""
    for mutant in MUTANTS:
        apply_mutant(lines, mutant)


# ---------------------------------------------------------------------------
# Build / test execution
# ---------------------------------------------------------------------------


def free_gb(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return usage.free / (1024**3)


def check_disk() -> None:
    free = free_gb(REPO_ROOT)
    if free < MIN_FREE_GB:
        print(
            f"ABORT: only {free:.1f} GB free at {REPO_ROOT}, below the "
            f"{MIN_FREE_GB} GB floor. Refusing to build -- this is exactly "
            "the failure mode that killed this PR's original gate run.",
            file=sys.stderr,
        )
        sys.exit(2)


def build_extension() -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "uv",
            "run",
            "--no-sync",
            "maturin",
            "develop",
            "--release",
            "--manifest-path",
            str(CARGO_MANIFEST),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )


def run_pytest(paths: tuple[str, ...] = TEST_PATHS) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "--no-sync", "python", "-m", "pytest", *paths, "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )


def perf_ratio_only_failure(summary: dict, raw_output: str) -> bool:
    """True if every failing test is one of the two perf-suite tests AND
    none of them failed on the genuine parity assertion those tests also
    carry -- i.e. the only thing that fired is the flaky timing-ratio
    check. See the `_PERF_RATIO_MARKER` module comment for why this
    distinction exists and is not test-weakening."""
    failed = summary["failed_ids"]
    if not failed or not set(failed) <= _PERF_TEST_IDS:
        return False
    if _PERF_PARITY_MARKER in raw_output:
        return False
    return _PERF_RATIO_MARKER in raw_output


_FAILED_RE = re.compile(r"^FAILED (\S+)")
_COLLECTED_RE = re.compile(r"collected (\d+) item")
_SUMMARY_RE = re.compile(r"^(\d+) passed(?:, (\d+) failed)?.*in [\d.]+s")


def summarize_pytest(result: subprocess.CompletedProcess) -> dict:
    out = result.stdout + result.stderr
    failed_ids = [m.group(1) for line in out.splitlines() if (m := _FAILED_RE.match(line))]
    collected = None
    if m := _COLLECTED_RE.search(out):
        collected = int(m.group(1))
    passed = failed = None
    for line in out.splitlines():
        if m := _SUMMARY_RE.match(line.strip()):
            passed = int(m.group(1))
            failed = int(m.group(2)) if m.group(2) else 0
    return {
        "returncode": result.returncode,
        "failed_ids": failed_ids,
        "collected": collected,
        "passed": passed,
        "failed": failed,
        "raw_tail": "\n".join(out.strip().splitlines()[-15:]),
    }


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Verdict:
    mutant: Mutant
    status: str  # "KILLED" | "SURVIVED" | "INCONCLUSIVE"
    detail: str
    elapsed_s: float


CARGO_MANIFEST = "packages/temper-io-types/Cargo.toml"


def run_cargo_tests() -> subprocess.CompletedProcess:
    """Run the crate's own Rust test suite.

    Some behaviour has NO Python-visible counterpart and so cannot be held by
    the pytest suites at all. `MAX_DEPTH` is the worked example: the oracle is
    CPython, which raises RecursionError at nesting depth ~199, so the
    differential's inputs stop three-quarters of the way to the 1000-frame
    ceiling and a one-frame shift in it is unreachable from Python.

    A harness that consulted only pytest reported exactly that mutant as
    SURVIVED while a Rust test was failing on it -- a false negative in the
    gate, which is worse than a missing gate because it reads as evidence.
    """
    return subprocess.run(
        ["cargo", "test", "--manifest-path", CARGO_MANIFEST],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


def first_failed_rust_test(result: subprocess.CompletedProcess) -> str:
    ids = re.findall(r"^test (\S+) \.\.\. FAILED$", result.stdout, re.M)
    if not ids:
        return "cargo test failed (no test id parsed)"
    return f"{ids[0]} (+{len(ids) - 1} more)" if len(ids) > 1 else ids[0]


def run_one(mutant: Mutant, original_lines: list[str], trailing_newline: bool) -> Verdict:
    t0 = time.monotonic()
    original_text = "\n".join(original_lines) + ("\n" if trailing_newline else "")

    mutated_lines = apply_mutant(original_lines, mutant)
    write_lines(TARGET_FILE, mutated_lines, trailing_newline)

    # Trap #1 defense: confirm the write actually landed before building.
    on_disk = TARGET_FILE.read_text(encoding="utf-8")
    if on_disk == original_text:
        write_lines(TARGET_FILE, original_lines, trailing_newline)
        raise MutationError(f"mutant {mutant.id!r}: file unchanged after write -- mutation did not apply")

    try:
        check_disk()
        build = build_extension()
        if build.returncode != 0:
            status = "KILLED"
            detail = "build (compile error): " + "\n".join(build.stderr.strip().splitlines()[-8:])
        else:
            check_disk()
            test = run_pytest()
            summary = summarize_pytest(test)
            raw_output = test.stdout + test.stderr
            if summary["returncode"] != 0 and perf_ratio_only_failure(summary, raw_output):
                # The only thing that fired is the flaky timing-ratio
                # assertion (reproduces on a clean, unmutated checkout
                # under machine load -- see perf_ratio_only_failure). Not
                # trustworthy as a kill by itself: re-run the CORRECTNESS
                # suites alone and use that as the real verdict.
                retest = run_pytest(CORRECTNESS_TEST_PATHS)
                retest_summary = summarize_pytest(retest)
                if retest_summary["returncode"] != 0:
                    status = "KILLED"
                    first = retest_summary["failed_ids"][0] if retest_summary["failed_ids"] else "?"
                    n = len(retest_summary["failed_ids"])
                    detail = f"{first} (+{n - 1} more)" if n > 1 else first
                else:
                    status = "SURVIVED"
                    detail = (
                        "perf ratio assertion fired but is a known-flaky timing check on this "
                        "machine (reproduces on the clean baseline under load); differential + "
                        "properties suites pass with the defect present"
                    )
            elif summary["returncode"] != 0:
                status = "KILLED"
                first = summary["failed_ids"][0] if summary["failed_ids"] else "?"
                detail = f"{first} (+{len(summary['failed_ids']) - 1} more)" if len(summary["failed_ids"]) > 1 else first
            elif summary["collected"] is not None and summary["collected"] != BASELINE_COLLECTED:
                status = "INCONCLUSIVE"
                detail = (
                    f"pytest exited 0 but collected {summary['collected']} tests, "
                    f"not the baseline {BASELINE_COLLECTED} -- collection changed, verdict untrustworthy"
                )
            else:
                status = "SURVIVED"
                detail = f"all {summary['passed']} tests passed"

            # pytest cannot see behaviour with no Python-visible counterpart,
            # so a SURVIVED verdict is not final until the Rust suite agrees.
            if status == "SURVIVED":
                rust = run_cargo_tests()
                if rust.returncode != 0:
                    status = "KILLED"
                    detail = "cargo test: " + first_failed_rust_test(rust)
    finally:
        # Revert unconditionally, even if the build/test step raised.
        write_lines(TARGET_FILE, original_lines, trailing_newline)
        reverted = TARGET_FILE.read_text(encoding="utf-8")
        if reverted != original_text:
            raise MutationError(f"mutant {mutant.id!r}: FAILED TO REVERT CLEANLY -- fix by hand immediately")

    return Verdict(mutant=mutant, status=status, detail=detail, elapsed_s=time.monotonic() - t0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="*", help="restrict to these mutant ids")
    parser.add_argument("--list", action="store_true", help="list mutant ids and descriptions, then exit")
    parser.add_argument(
        "--min-killed",
        type=int,
        default=15,
        help="exit nonzero if fewer than this many mutants are KILLED (default 15)",
    )
    args = parser.parse_args()

    if args.list:
        for m in MUTANTS:
            print(f"{m.id:32s} [{m.category}]\n    {m.description}")
        return 0

    selected = MUTANTS
    if args.only:
        wanted = set(args.only)
        selected = [m for m in MUTANTS if m.id in wanted]
        missing = wanted - {m.id for m in selected}
        if missing:
            print(f"unknown mutant id(s): {sorted(missing)}", file=sys.stderr)
            return 2

    check_disk()
    original_lines, trailing_newline = read_lines(TARGET_FILE)
    print(f"Validating {len(MUTANTS)} mutant hunk set(s) against the pristine file...")
    validate_all(original_lines)
    print("All hunks match. Free disk: %.1f GB" % free_gb(REPO_ROOT))

    # A kill signal is only evidence if it is SILENT on the pristine tree.
    # `run_cargo_tests` can now upgrade SURVIVED to KILLED, so a Rust suite
    # that is already red would report all 21 mutants KILLED and the run
    # would look like its best result ever while proving nothing.
    print("Checking the Rust suite is green on the pristine file...")
    baseline = run_cargo_tests()
    if baseline.returncode != 0:
        print(
            "FAIL: cargo test is already failing on the UNMUTATED file -- every\n"
            "      mutant would be reported KILLED by a signal that has nothing\n"
            "      to do with the mutation. Fix the Rust suite before trusting\n"
            "      any verdict from this harness.\n\n"
            f"      first failure: {first_failed_rust_test(baseline)}",
            file=sys.stderr,
        )
        return 2
    print("Rust suite green.\n")

    verdicts: list[Verdict] = []
    for i, mutant in enumerate(selected, 1):
        print(f"[{i}/{len(selected)}] {mutant.id} -- {mutant.description}")
        try:
            v = run_one(mutant, original_lines, trailing_newline)
        except MutationError as exc:
            print(f"  ABORT: {exc}", file=sys.stderr)
            return 3
        verdicts.append(v)
        print(f"  {v.status} ({v.elapsed_s:.1f}s): {v.detail}\n")

    # Final sanity: the file must be back to pristine.
    final_lines, final_trailing = read_lines(TARGET_FILE)
    if final_lines != original_lines or final_trailing != trailing_newline:
        print("ABORT: dag_expr.rs is not byte-identical to the pristine original after the run.", file=sys.stderr)
        return 3

    # Rebuild the clean extension so the working tree's installed .so
    # matches the (reverted) source before this process exits.
    print("Rebuilding the clean extension...")
    clean_build = build_extension()
    if clean_build.returncode != 0:
        print("WARNING: final clean rebuild failed:\n" + clean_build.stderr, file=sys.stderr)

    killed = [v for v in verdicts if v.status == "KILLED"]
    survived = [v for v in verdicts if v.status == "SURVIVED"]
    inconclusive = [v for v in verdicts if v.status == "INCONCLUSIVE"]

    print("=" * 72)
    print(f"{len(verdicts)} mutants evaluated: {len(killed)} KILLED, {len(survived)} SURVIVED, "
          f"{len(inconclusive)} INCONCLUSIVE")
    for v in verdicts:
        print(f"  [{v.status:12s}] {v.mutant.id:32s} {v.detail}")
    print("=" * 72)

    if len(killed) < args.min_killed:
        print(f"FAIL: only {len(killed)} killed, need >= {args.min_killed}", file=sys.stderr)
        return 1
    if inconclusive:
        print(f"WARNING: {len(inconclusive)} mutant(s) were INCONCLUSIVE -- investigate before trusting this run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
