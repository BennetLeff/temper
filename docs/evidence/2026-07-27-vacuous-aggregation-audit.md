# Vacuous-aggregation audit — the 13 `check_vacuous_gates.py` findings

Date: 2026-07-27
Scope: the 13 unguarded `all()` calls reported by `python3 scripts/check_vacuous_gates.py`
after its 2026-07-27 widening from 52 to 526 files.

## Falsifier

Stated before starting: **"all 13 are safe-by-construction, so the widened gate
found only noise."**

**This did not fire.** 6 of the 13 are genuinely vacuous — reachable empty
collections that the code currently treats as a passing/clean verdict. 7 are
safe by construction or not gates at all. The widened gate found real defects,
not just noise; a narrow scope (the pre-rewrite behavior) would have kept
hiding them.

## Summary

| Classification | Count | Findings |
|---|---|---|
| Genuinely vacuous (fixed) | 6 | `_constraint_parser.py:68,79`, `tiers.py:81`, `check_derived_doc_drift.py:201,405`, `mpn_fabrication_gate.py:407` |
| Safe by construction / not a gate (proved + guarded) | 7 | `check_derived_doc_drift.py:197,216`, `ci_identity_check.py:76`, `import_linter_gate.py:79`, `mpn_fabrication_gate.py:402`, `dag_expr.py:253`, `spc_rules.py:51` |

**No separate allowlist file was added.** `scripts/check_vacuous_gates.py`'s own
docstring states this gate deliberately has no allowlist mechanism, citing the
precedent of collapsing `import-linter-baseline.yaml` once it reached zero
(commit `df862924`) for the same reason: an allowlist requires a maintainer to
remember to keep it current, which is the exact failure mode a widened,
default-include gate exists to remove. Introducing an allowlist file now would
directly contradict a design decision written into the gate itself on the same
day as this task. Instead, every "safe by construction" and "not a gate" finding
was given a real, in-code guard (an `assert` or `if not`) that the gate's own
existing heuristic recognizes — this is strictly stronger than a documentation-only
allowlist entry, because the guard is enforced at runtime and will loudly break
(`AssertionError`) if a future change ever violates the invariant it documents,
rather than silently going stale.

## Per-finding detail

### 1. `packages/temper-placer/src/temper_placer/pcl/_constraint_parser.py:68` — GENUINELY VACUOUS

`_is_resolved()`'s `EnclosingConstraint` branch: `inner_ok = all(... for ref in
constraint.inner)`. `EnclosingConstraint.__init__` enforces no minimum length on
`inner` (unlike `AlignedConstraint`, which raises `ValueError` below 2
components), and the `"enclosing"` parse path in the same file passes
`data["inner"]` straight through with no length check. A PCL author can write
`inner: []` and reach this line with `constraint.inner == []`.

**What the gate reported on empty input (before fix):** `all()` over `[]` is
vacuously `True`, so `inner_ok` was `True` and `_is_resolved()` returned `True` —
a zero-component enclosing constraint was reported "resolved" and passed on to
`ConstraintCollection.compile()` instead of being rejected as degenerate.

**Fix:** `if not constraint.inner: return False` before the `all()`.

**Test:** `test_is_resolved_rejects_empty_enclosing_inner` in
`packages/temper-placer/tests/pcl/test_parser.py`. Before fix: `AssertionError:
assert True is False`. After fix: passes.

### 2. `_constraint_parser.py:79` — GENUINELY VACUOUS

Same function, `(AlignedConstraint, OnSideConstraint)` branch. `AlignedConstraint.__init__`
raises `ValueError` below 2 components, so that half of the `isinstance` check is
safe — but `OnSideConstraint.__init__` enforces no minimum, and the `"on_side"`
parse path passes `data["components"]` through unchecked. `components: []` is
reachable for `OnSideConstraint` specifically.

**What the gate reported on empty input (before fix):** vacuously `True`, same
failure shape as #1.

**Fix:** `if not constraint.components: return False` before the `all()`.

**Test:** `test_is_resolved_rejects_empty_on_side_components`, same file. Before
fix: `AssertionError: assert True is False`. After fix: passes. A third test,
`test_is_resolved_still_resolves_non_empty_enclosing_and_on_side`, guards
against over-correction (non-empty, genuinely-resolvable/unresolvable cases
still behave as before).

### 3. `packages/temper-placer/src/temper_placer/pcl/tiers.py:81` — GENUINELY VACUOUS

`ConstraintStatus.check_escalation()`: `window =
self.violation_history[-config.persistence_window:]` then `all(v > 0 for v in
window)`. The preceding guard is `len(self.violation_history) >=
config.persistence_window`. With `persistence_window <= 0`, Python's
negative-slice-of-zero (`lst[-0:]`) equals `lst[0:]`; combined with an *empty*
`violation_history`, `len([]) >= 0` is trivially true and `window = [][0:] ==
[]`. `EscalationConfig` had no validation on `persistence_window` — nothing
prevented a caller from constructing `EscalationConfig(persistence_window=0)`.

**What the gate reported on empty input (before fix):** `all()` over `[]` is
vacuously `True`, so `check_escalation()` reported `PERSISTENT` escalation —
"this constraint has been violated for N consecutive iterations" — for a
constraint with **zero recorded violations**.

**Fix:** `EscalationConfig.__post_init__` now raises `ValueError` if
`persistence_window < 1`; a redundant `if not window: return False` was also
added immediately before the `all()` call as defense in depth (the config-level
guard is the real fix; the local guard documents the invariant at the point
that actually matters and is what the mechanical gate recognizes).

**Test:** `test_persistence_window_zero_rejected` and
`test_persistence_window_negative_rejected` in
`packages/temper-placer/tests/pcl/test_tiers.py`. Before fix: `Failed: DID NOT
RAISE ValueError` (both). After fix: both pass. Full `test_tiers.py` suite: 34
passed.

### 4. `packages/temper-placer/src/temper_placer/pipeline/dag_expr.py:253` — NOT A GATE / SAFE BY CONSTRUCTION

`evaluate_skip_expr._eval_boolop()`: `all(_eval(v) for v in node.values)` for an
`ast.BoolOp(And)` node. Two independent reasons this is not a defect:

1. **Safe by construction:** the only code that builds an `ast.BoolOp` for this
   grammar is `_Parser._and_expr`/`_or_expr`, which is strictly left-associative
   binary (`ast.BoolOp(op=..., values=[left, right])`) — it never constructs a
   unary or nullary `BoolOp`. `node.values` is always exactly length 2 here.
   `evaluate_skip_expr` is only ever called with an `ast.Expression` produced by
   `parse_skip_expr`'s own `_Parser` (see `dag_engine.py`), never an
   externally-constructed AST.
2. **Not a gate at all:** even hypothetically, `all()` over an empty conjunction
   returning `True` is correct boolean-algebra semantics ("no conjuncts to
   violate"), not a verification gate whose "pass" is supposed to mean
   "something was checked."

**Fix:** documented both reasons in a comment, plus `assert node.values, "..."`
immediately before the `all()` — trivially true given (1), and would loudly
fail if grammar #1's invariant were ever broken by a future refactor.

### 5. `scripts/check_derived_doc_drift.py:197` and `:216` — SAFE BY CONSTRUCTION

`find_rows_by_locator`/`find_rows_by_exact_cell`: `norm_header_filter =
[normalize(s) for s in header_contains] if header_contains else None`. Because
an empty list is falsy in Python, `header_contains == []` yields
`norm_header_filter = None`, not an empty list — the ternary can only produce a
non-None `norm_header_filter` when `header_contains` was itself truthy
(non-empty), and a list comprehension preserves length. So whenever code
reaches `if norm_header_filter is not None:`, `norm_header_filter` is
guaranteed non-empty.

**Fix:** `assert norm_header_filter` added immediately inside the `is not
None` branch in both functions, proving the invariant the gate's own heuristic
can check (the "is not None" check itself isn't one of the gate's recognized
guard patterns, so this needed an explicit assert rather than being
auto-recognized).

### 6. `check_derived_doc_drift.py:201` — GENUINELY VACUOUS

`find_rows_by_locator`: `if all(loc in ctx for loc in norm_locator): matches.append(...)`.
`norm_locator` comes from the `locator` parameter with **no emptiness check** —
unlike `header_contains` above, there is no falsy-collapse-to-None trick here.
`locator` is populated directly from config (`gate_cfg["source_row_locator"]`
or `check["row_locator"]`), which has no schema-level minimum-length
enforcement. Today's `scripts/derived_doc_gates.yaml` happens to have only
non-empty locators, but nothing in the code prevents a future config typo
`source_row_locator: []`.

**What the gate reported on empty input:** `all()` over `[]` is vacuously
`True` — every row of every table would "match" the (empty) locator. Combined
with the caller's `if len(matches) != 1:` check, this is only caught when a
table doesn't happen to have exactly one row; a source/derived table with
exactly one row and an accidentally-empty locator would silently report a
clean match.

**Fix:** `find_rows_by_locator` now raises `ValueError` if `norm_locator` is
empty. `run()` wraps the per-config-processing block in a `try/except
ValueError` that converts this into a `ToolError`, keeping the file's
documented 0/3/5 exit-code contract intact instead of an undocumented bare
crash.

**Test:** `test_empty_source_row_locator_fails_closed` in
`scripts/tests/test_check_derived_doc_drift.py`. Before fix: `assert False` (no
tool_error naming the empty locator was produced — the vacuous match went
through silently). After fix: passes (`state == "tool_error"`).

### 7. `check_derived_doc_drift.py:405` — GENUINELY VACUOUS

`check_consistency()`: `stale_present = all(normalize(t) in ctx for t in
check["stale_tokens"])`. Same shape as #6: `stale_tokens` comes straight from
`consistency_checks:` config entries with no minimum-length enforcement.

**What the gate reported on empty input:** vacuously `True` — every row would
be reported as containing a "stale" claim regardless of actual content,
inverting the check's purpose (a false "stale, unmitigated" verdict on rows
that never mentioned the stale claim at all).

**Fix:** raises `ValueError` if `stale_tokens` is empty, caught by the same
`run()` wrapper as #6 and converted to `tool_error`.

**Test:** `test_empty_stale_tokens_fails_closed`, same file. Before fix: `assert
False` (no matching tool_error). After fix: passes.

### 8. `scripts/ci_identity_check.py:76` — SAFE BY CONSTRUCTION

`results = [check_fixture_rejected(), check_production_board_if_present()]` —
a fixed two-element literal, never built from runtime-variable-length data.

**Fix:** `assert results` added with a comment explaining why this can never
be empty, forcing a future refactor (e.g. a for-loop over a list of checks) to
reconsider the guard.

### 9. `scripts/import_linter_gate.py:79` — SAFE BY CONSTRUCTION (already correctly guarded, checker blind spot)

`parse_violations()`: `if next_line and all(c == "-" for c in next_line):`. This
was **already correct** — Python's `and` short-circuits, so `all()` never runs
when `next_line` is empty/falsy. The gate's heuristic only recognizes `if not
X:`/`assert X`-shaped guards on a *preceding* line or in the same statement via
a `not X` substring search; `X and predicate(X)` (truthy check, not negated) is
a real, working guard the checker's syntactic pattern-matching doesn't cover.

**Fix:** restructured (behavior-preserving) into an explicit `if not next_line:
pass` / `elif all(...):` — the checker now recognizes the standalone `if not
next_line:` line. Verified identical `lint-imports` output before and after
this restructure (`2 kept, 1 broken`, `1 suppressed`, `0 new violations`, exit
0) via `git stash` A/B comparison.

### 10. `scripts/mpn_fabrication_gate.py:402` — SAFE BY CONSTRUCTION

`load_allowlist()`: `required = ("file", "ref", "mpn", "checks", "reason")` then
`all(k in e for k in required)`. `required` is a fixed 5-element literal written
on the line directly above — never derived from config/runtime data.

**Fix:** `assert required` added with a comment.

### 11. `mpn_fabrication_gate.py:407` — GENUINELY VACUOUS

Same function: `checks = e["checks"]`; if it's a string it's wrapped in a
single-element list, but if the YAML entry itself has `checks: []` (a list
literal), `checks` remains `[]`. Then `not isinstance(checks, list) or not
all(c in ("eseries", "decode") for c in checks)` — with `checks == []`, `not
isinstance(...)` is `False` and `not all(...)` is vacuously `False` (since
`all([])` is `True`), so the whole condition is `False` and the malformed entry
is **not rejected**.

**Why this matters even though it isn't a security bypass:** `allowlist_covers()`
checks `check in e.checks`; with `e.checks == set()` this is always `False`, so
an entry with empty `checks` covers nothing and grants no bypass. But it *is* a
validator that fails to validate — a schema-invalid, dead-weight entry silently
accepted into a file whose whole design principle (per its own header comment)
is "hand-curated only, reviewed PR, every entry cites verification" — an
entry that can never match anything should be rejected as malformed, not
silently kept.

**Fix:** split the combined `isinstance`/`all()` condition into
`if not isinstance(checks, list): return None` followed by a standalone `if not
checks: return None` (recognized by the gate's heuristic) before the
`all(c in (...) for c in checks)` check.

**Re-run:** `mpn_fabrication_gate.py` — 120 parts inspected, 120 values
checked, 103 MPNs decoded, 17 unrecognized-prefix (reported, not silently
passed), 10 allowlist entries loaded (all pre-existing, all non-empty
`checks`), **0 new violations, PASSED**. Unchanged from the pre-fix baseline —
no live entry in `mpn-fabrication-allowlist.yaml` has an empty `checks` list
today, so this fix changes nothing about today's result; it only closes a
schema hole for future entries.

### 12. `packages/temper-placer/src/temper_placer/pipeline` — see #4 above (dag_expr.py, already covered)

### 13. `scripts/spc_rules.py:51` — SAFE BY CONSTRUCTION

`rule_8consecutive()`: `if len(values) < 8: return False` guards `last8 =
values[-8:]`, then `all(v > mean for v in last8) or all(v < mean for v in
last8)`. Since `len(values) >= 8` is enforced first, `values[-8:]` always
returns exactly 8 elements — but the gate's heuristic checks the guard against
the exact collection the `all()` iterates (`last8`), not the pre-slice
`values`, so it couldn't see the (real) guarantee.

**Fix:** `assert len(last8) == 8` added immediately after the slice, restating
the invariant in terms of the variable the `all()` actually consumes.

## Gate re-runs (counts, not bare exit codes)

| Gate | Before | After | Changed? |
|---|---|---|---|
| `check_vacuous_gates.py` | 13 findings, exit 1 | **0 violations**, 532 files scanned, exit 0 | fixed |
| `mpn_fabrication_gate.py` | 0 findings (today's baseline) | 120 parts, 103 decoded, 17 unrecognized, 10 allowlisted, **0 new violations**, exit 0 | **unchanged** |
| `check_derived_doc_drift.py` | 132 fields clean | 3 documents, 44 tables, 52 gate rows, **132 fields checked**, clean, exit 0 | **unchanged** |
| `import_linter_gate.py` | environment tool_error (pre-existing, see below) | `2 kept, 1 broken`, 1 suppressed, **0 new violations**, exit 0 | resolved (see note) |
| `make netlist` | — | **76/76 assertions PASSED**, 0 failed, exit 0 | unchanged (verification only) |
| `check_domain_partition.py` | — | 47 nets / 2 domains / 10 isolators, **0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance defects**, exit 0 | unchanged |
| `capacity_budget_gate.py` | — | **0 defects**, exit 0 | unchanged |

**No gate's reported violation/finding count changed as a result of these
fixes.** `import_linter_gate.py` initially failed with `tool_error` (exit 5,
"Could not find package 'temper_placer' in your Python path") in this worktree
— confirmed via `git stash` A/B that this is a **pre-existing environment gap**
unrelated to this task: the root `uv sync` did not install workspace member
packages that aren't direct dependencies of the root project (`temper-placer`,
`temper-drc-rs`, `temper-rust-router`, etc.); `uv sync --all-packages` resolved
it by building and installing all workspace members. This is an environment
fix, not a code change, and does not touch `packages/temper-rust-router-core/`
source (it only builds/installs it into the shared venv, which another
concurrent agent working that package would also need). After the environment
fix, `import_linter_gate.py`'s own logic (my restructure of `parse_violations`,
finding #9) produces byte-identical output to the pre-fix version of that
function — verified via `git stash` A/B on `scripts/import_linter_gate.py`
alone, both giving `2 kept, 1 broken`, `1 suppressed`, `0 new violations`.

## What remains UNVERIFIED

- Whether the real CI environment (as opposed to this worktree) has the same
  `uv sync` gap that made `import_linter_gate.py` initially report a
  tool_error here. If CI's environment setup step differs from a bare `uv
  sync` at the repo root (e.g. it already runs `uv sync --all-packages` or an
  equivalent), this may never have been a live problem in CI — but I did not
  have access to CI's actual environment-setup step to confirm either way.
- Whether any config author has, in a branch not visible from this worktree,
  already written an empty `source_row_locator`, `row_locator`, or
  `stale_tokens` list, or an allowlist entry with empty `checks`, that would
  now start failing closed (as `tool_error`) where it previously passed
  silently. A repo-wide search of `scripts/derived_doc_gates.yaml` and
  `mpn-fabrication-allowlist.yaml` in this worktree found no such entries
  today, but that is a point-in-time check of this branch only.
- Whether `EscalationConfig(persistence_window=0-or-negative)` is constructed
  anywhere outside this package today (a repo-wide grep found none outside
  `tests/pcl/test_tiers.py`, all using positive values) — this fix could
  reject a legitimate call site elsewhere in the workspace that this search
  didn't reach (e.g. a future caller in `packages/temper-rust-router-core/`,
  which is out of scope for this task and was not searched).

## Files touched

- `packages/temper-placer/src/temper_placer/pcl/_constraint_parser.py` (fix)
- `packages/temper-placer/src/temper_placer/pcl/tiers.py` (fix)
- `packages/temper-placer/src/temper_placer/pipeline/dag_expr.py` (proof + guard)
- `packages/temper-placer/tests/pcl/test_parser.py` (new tests)
- `packages/temper-placer/tests/pcl/test_tiers.py` (new tests)
- `scripts/check_derived_doc_drift.py` (2 fixes, 2 proofs + guards)
- `scripts/tests/test_check_derived_doc_drift.py` (new tests)
- `scripts/ci_identity_check.py` (proof + guard)
- `scripts/import_linter_gate.py` (behavior-preserving restructure)
- `scripts/mpn_fabrication_gate.py` (1 fix, 1 proof + guard)
- `scripts/spc_rules.py` (proof + guard)
