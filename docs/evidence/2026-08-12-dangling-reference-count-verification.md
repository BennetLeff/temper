<!-- provenance: commit=07bb75af2e67e9560b17d2c268ff969f47514328 dirty=UNKNOWN -->

# Dangling-reference count verification: 347 copper-net violations and 151/167 unexamined @req annotations

**Verdict up front:** both headline numbers reproduce. **347 is exact** --
ran the real gate against a freshly-built netlist and got exactly 347, and
the gate is sound, not over-broad: every sampled violation was independently
confirmed against the raw board/netlist data, and all three "orphaned net"
names trace to one real, dated, un-resynced elec change (`5842767c2`,
deleting the ZCD circuit). **The `@req` scope-gap claim is directionally
correct but was measuring the wrong denominator.** The prior agent's "151 of
167 never examined" undercounts the real problem: measuring directly, this
repo has **164 `@req(...)` annotation call-sites across 61 files**, of which
only **12 are ever scanned by any gate** (152 unchecked, not 151/167 — a
92% miss rate, slightly higher than claimed). But *why* they're unchecked is
different from what "opt-in by design" suggests: **144 of the 164** use a
plan-id containing a hyphen (a date-stamped ID like `2026-06-23-004`), which
`check_traceability.py`'s own regex (`\w+` only) can **never** match, in or
out of scope — a structural blind spot, not a scope choice. Hand-verifying a
representative sample of those 144 against the actual plan documents found
the overwhelming majority (103 of 144, all 16 distinct plan-id groups
sampled) are **real, resolvable citations to real requirements** the
tooling simply cannot see. A minority are genuinely broken: **15
confirmed-dangling annotations** (2 nonexistent plans, 1 plan whose cited
sub-requirement IDs were never defined, 1 un-attributable bare unit-label),
plus **28 annotations whose plan-id prefix is structurally ambiguous**
(matches 2-3 different plan documents created the same day). Full
breakdown below.

---

## 1. Copper-net consistency: 347 confirmed exact, gate is sound

### 1.1 The script and what it checks

`scripts/check_copper_net_consistency.py` (547 lines, exists on `origin/main`)
reads `pcb/temper.kicad_pcb` directly (via `kiutils`) and a freshly compiled
`elec/build/default.net`, and runs three checks over every copper item
(segment/arc/via/zone) and every footprint pad:

1. **`dangling-ordinal`** (`:371-381`) -- the copper item's net ordinal
   resolves against the board's *own* net table.
2. **`orphaned-net`** (`:395-405`) -- the resolved net *name* exists in the
   compiled netlist.
3. **`pad-mismatch`** (`:407-425`) -- for every pad with an *exact*
   `(Reference, pad_number)` match in the compiled netlist, the pad's
   on-board net name equals what the netlist declares for that pin. Pads
   without an exact match are reported as `SKIPPED`, not silently passed
   (`:410-414`) -- this is the one check with no analogue elsewhere in CI
   (`check_domain_partition.py` reads the netlist only; clearance checks
   read positions only; `mpn_fabrication_gate` reads part identity only).

Fail-closed contract (`:49-72`): exits 5 (GATE ERROR), never 0, if the board
is missing/unparseable, the netlist is stale/empty, or the board/netlist has
zero copper/nets/pads. This contract was exercised for real during this
verification: the worktree's freshly-created `.venv` (from `make netlist`)
had no `kiutils` installed, and the gate correctly refused to report "0
violations" -- it raised `GateError: kiutils is not installed` (exit 5).
Re-running with the repo's real venv (`/home/bennet/Desktop/temper/.venv/bin/python`,
which has `kiutils`) produced a real result.

### 1.2 Reproduction

```
$ cd /home/bennet/Desktop/temper-verify-dangling
$ make netlist                     # fresh build; ends "[write-build-stamp] ... digest 8cfd715e60a3…"
$ /home/bennet/Desktop/temper/.venv/bin/python scripts/check_copper_net_consistency.py
Board: pcb/temper.kicad_pcb
Netlist: elec/build/default.net
Copper: 2434 item(s) total (Segment=2290, Via=48, Zone=96), 2434 checked (net != 0), 0 skipped (net == 0, no-net).
Pads: 478 checked (exact ref+pin match in netlist), 49 skipped (no exact match).

=== VIOLATIONS: 347 ===
  [orphaned-net] 145 violation(s): ...
  [pad-mismatch] 202 violation(s): ...
FAILED -- 347 violation(s)
$ echo $?
3
```

145 + 202 = **347**, exact match to the prior agent's number.

### 1.3 Root cause, verified by hand -- not by the gate's own output

The 145 `orphaned-net` violations resolve to only **3 distinct dangling net
names**, not 145 independent problems:

| Net name | Copper items | 
|---|---|
| `zcd` | 57 |
| `power_in.r_zcd_top1-p2` | 46 |
| `a` | 42 |

All three are remnants of the ZCD (mains zero-cross-detect) circuit deleted
in `5842767c2` (`fix(elec): delete U3 (H11L1 mains-ZCD optocoupler) and its
dedicated circuitry`, 2026-08-07). Confirmed independently of the gate:

```
$ grep -io 'zcd[a-z_]*' elec/build/default.net | sort -u
(no output -- confirms 'zcd' truly absent from the fresh netlist)
```
```python
>>> from kiutils.board import Board
>>> b = Board.from_file('pcb/temper.kicad_pcb')
>>> {'zcd','power_in.r_zcd_top1-p2','a'} <= {n.name for n in b.nets}
True   # all three exist in the BOARD's own net table -- confirms real, on-board copper
```

The board was never resynced after `5842767c2` (2026-08-07 15:49) or the
subsequent `c617e0d08` (`feat(elec): implement OCP-02 as Option A (second
CT)`, 2026-08-07 21:53), which is the second half of the story: OCP-02
inserted a new component mid-schematic, and atopile assigns designators
sequentially by declaration order (same mechanism as the prior `C27`
incident, `docs/evidence/2026-07-30-copper-net-consistency-drift.md`) --
this reflowed a large contiguous run of `C`/`R`/`D`-series designators. The
only commit to touch `pcb/temper.kicad_pcb` since (`c4956df66`) is proven,
in its own commit message, to be a 2-token layer-type edit with "no other
bytes in the file changed" -- not a resync.

**Hand-verified sample (5 of 347, cross-checked against raw `kiutils`
output, not the gate's own code path):**

| Ref/pin | Gate says (board / netlist) | Independent `kiutils` read | Verdict |
|---|---|---|---|
| C23 pad 2 | `DC_BUS_RTN` / `hb-gnd` | `DC_BUS_RTN` | REAL |
| C24 pad 2 | `DC_BUS_RTN` / `hb-gnd` | `DC_BUS_RTN` | REAL |
| R10 pad 1 | `+3V3` / `+15V` | `+3V3` | REAL |
| R10 pad 2 | `ZCD_ISO` / `discharge.k_dis1-coil1` | `ZCD_ISO` | REAL |
| D2 pad 1 | `zcd` / `discharge.k_dis1-coil1` | `zcd` | REAL |

All 5 confirmed: the board's actual on-file net name (read via a fresh
`kiutils.Board.from_file()` call, independent of `check_copper_net_consistency.py`'s
own code) matches exactly what the gate reported, and disagrees with the
compiled netlist, which is itself fresh (`make netlist` immediately prior).

**Verdict: 347 is exact, and the gate is sound, not over-broad.** This is
not a miscalibrated check inflating a small problem -- it is 3 dangling net
names (real, un-resynced ZCD deletion) plus one large cascading designator
reflow (real, un-resynced OCP-02 insertion), both traced to specific,
dated, real commits, independently confirmed against raw board/netlist
data rather than the gate's own reporting path.

---

## 2. `@req` traceability: real number is 164/61, not 167/63 -- and the miss rate is structural, not scope

### 2.1 What exists and how it's wired

`docs/TRACEABILITY.md` describes a **per-directory `TRACEABILITY` sentinel
opt-in** model. `scripts/check_traceability.py`'s own module docstring
(`:12-60`) says this was **rewritten on 2026-07-27** to a **registry-scope-driven**
model instead: the scan universe is the union of every plan's `scope:` list
in `docs/traceability-registry.yaml`, not "whichever directories happen to
have a sentinel file." **`docs/TRACEABILITY.md` was never updated to match**
-- it still describes the pre-rewrite sentinel-gates-everything model. This
is a real, distinct doc/code drift, orthogonal to the two claims below.

`check_traceability.py` is `disposition: utility` in `scripts/manifest.yaml:1142`
(an honest label, not a false `ci-gate` claim), and:

```
$ grep -rn "check_traceability" .github/workflows/
(no output)
```

Zero workflows invoke it -- confirmed. `docs/TRACEABILITY.md`'s own "Local
Development" section cites `packages/temper-drc/tests/test_traceability_gate.py`,
which does not exist -- `packages/temper-drc/` was deleted (`f438ca0e4`,
`2122544d7`), confirmed by `git log --all --diff-filter=D`. Nobody runs
this tool at all, by any path, today.

### 2.2 Running it live

```
$ /home/bennet/Desktop/temper/.venv/bin/python scripts/check_traceability.py --all
VIOLATION: .../conftest.py:3: requirement 'U1' not defined in docs/plans/2026-06-28-004-...md
VIOLATION: .../test_clearance_induction.py:3: requirement 'U2' not defined in ...
VIOLATION: .../test_clearance_segment_dist.py:3: requirement 'U4' not defined in ...
VIOLATION: .../test_induction_base.py:26: requirement 'U3' not defined in ...
VIOLATION: .../test_all_pad_tree_routing.py:1: plan 'APC1' has status 'completed', expected 'active'
  ... (6 total plan-status mismatches, all APC1 R3/R4)
Scanned 332 file(s) across 8 of 11 registered plan(s)' declared scope in docs/traceability-registry.yaml; found 12 @req annotation(s).
FAIL (closed): ... Zero non-deferred requirement(s) parsed ...
SCOPE ISSUE: APC1: scope entry '.../all_pad_evidence.py' is not tracked by git
SCOPE ISSUE: APC1: scope entry 'packages/temper-placer/tests/router_v6/' is not tracked by git
SCOPE ISSUE: N2/N4: scope entry 'packages/temper-drc/...' is not tracked by git  (5 total)
```

This exactly reproduces the prior agent's numbers for the gate's own
output: 332 files scanned, 12 annotations found, 6 R2 violations (4
false-positive `U1-U4`-not-recognized + 2×3 `APC1 completed` status
mismatches = 6 lines shown, all real per §2.4), and 7 registry SCOPE ISSUE
lines. **One of those 7 SCOPE ISSUE lines is itself a false positive in the
checker** -- see §2.5.

### 2.3 The real total: 164 annotations / 61 files, not 167/63

Measured independently of the gate, against every git-tracked `.py`/`.c`/`.h`
file (the gate's own declared source suffixes, `check_traceability.py:72`):

```
$ git ls-files | grep -E '\.(py|c|h)$' | xargs grep -l '@req('  # substring probe
61 files
$ python3 -c "count every '@req(...)' call-site via regex r'@req\(([^)]*)\)'"
164 call-sites, 61 files
```

164/61 is close to but not identical to the prior agent's 167/63. The small
gap is most likely a counting-convention difference: this repo actually
uses **several distinct `@req` syntactic dialects** (see the partition in
§2.4), and some individual call-sites contain multiple requirement-IDs at
once (`@req(2026-06-23-001, FR1, FR2, FR3, FR6, FR7, FR8, FR9)` in
`hv_lv_partition.py` is one call-site with 7 IDs) -- counting IDs instead of
call-sites would inflate the total above 164. I did not attempt to match
the prior number exactly; 164 call-sites is what this repo's `@req(...)`
text directly contains today, and is the number this report uses throughout.

Only **12 of the 164** (7.3%) live inside a file the traceability gate ever
scans (the union of the 11 registered plans' `scope:` lists, 332 files).
**152 of 164 (92.7%) are unchecked** by the live gate -- higher than the
prior agent's 151/167 (90.4%), because the correct denominator is smaller.

### 2.4 Why they're unchecked: structural blind spot, not (mainly) scope choice

This is the part the prior agent's framing undersells. Breaking down all
164 call-sites by *why* the gate can or can't see them (a full,
non-overlapping partition, verified to sum exactly to 164):

| Category | Count | Files | Why |
|---|---|---|---|
| **A. Scanned and checked today** | 12 | 4 | comment-prefixed, `\w+`-only plan/req IDs (`N10`, `APC1`), AND inside a registered plan's declared `scope:` |
| **B. Registered-ID form, but plan-id not in registry** | 2 | 2 | `@req(U9, R1)` -- `U9` is not one of the 11 registered plan-ids (see §2.4.3) |
| **C. Hyphenated (date-stamped) plan-id, exactly 2 fields** | 144 | 44 | `check_traceability.py`'s own regex is `#\s*@req\((\w+),\s*(\w+)\)` (`:139-140`) -- `\w` excludes `-`, so `@req(2026-06-23-004, R4)` **can never match this regex**, regardless of scope |
| **D. No comment marker at all (2-field, non-hyphenated)** | 1 | 1 | bare `@req(...)` inside a docstring body, e.g. `test_bottleneck_map.py:3` (`"""...\n@req(2026-06-23-004, R3)\n"""`) -- no `#`/`//` precedes it on the line, so the regex's required comment-marker prefix never matches either (this one also happens to be hyphenated, so it's doubly invisible -- shown separately only to keep the partition non-overlapping) |
| **E. Multi-field call form** | 5 | 4 | `@req(plan_id, R1, R2, R3, ...)` -- 3+ comma-separated fields, doesn't fit the checker's fixed 2-argument shape at all |

A fourth, even narrower dialect surfaced during hand-verification and is
counted inside C, not broken out separately: `@req(2026-06-23-007, R2/K4)`
(4 occurrences) packs two IDs into the second field with `/` instead of a
comma. Checked by hand: both `R2` and `K4` are real, defined in that exact
plan (`docs/plans/...isolation-slots-slotgen-plan.md:46,51`).

The regex responsible for C (structurally, the majority of the miss) is
`check_traceability.py:139-140`:
```python
_PYTHON_REQ_RE = _re.compile(r"#\s*@req\((\w+),\s*(\w+)\):?(.*)")
_C_REQ_RE = _re.compile(r"//\s*@req\((\w+),\s*(\w+)\):?(.*)")
```
`\w+` matches `[A-Za-z0-9_]+` only. A plan-id of `2026-06-23-004` fails to
match at the very first hyphen -- this is true **before** the scope
question is even asked. Category C's 144 annotations would remain invisible
to R2/R3 even if every file in the repo were added to every plan's
registered scope. This is the same class of bug the prior agent's own
survey found once already (N10's `U1-U4` requirement IDs, which the
*requirement-parsing* regex `^-\s*(R\d+)[.:]` can't recognize because it's
`R`-only) -- here it recurs one level up, in the *annotation*-parsing
regex, against `-`-containing plan-ids instead of `U`-prefixed req-ids.

#### 2.4.1 Hand-verifying category C: mostly real, not mostly noise

The task calls for hand-verification above ~20 items. Category C is 144
annotations grouped into 16 distinct plan-id values; I resolved every one
of the 16 groups by hand against the actual plan document(s) in
`docs/plans/`, which collectively covers well over 100 of the 144 raw
instances (the two largest groups, `2026-06-23-004` and `2026-06-23-007`,
account for 30 and 38 instances respectively, and I checked every distinct
requirement-ID cited within both, not just one representative):

| Plan-id (n) | Resolution | Requirement cited | Found in plan doc? |
|---|---|---|---|
| `2026-06-23-004` (30) | unique | R1,R2,R3,R4,R5,R6,R7,K1-K4,R-D5 | **all present**, e.g. `docs/plans/...seed-filtering-plan.md:98` `"Requirements: R4."` |
| `2026-06-23-005` (12) | unique | R1,R2,R8,U2,U3 | **all present** |
| `2026-06-23-007` (38) | unique | R1,R2,R3,R4,R6, R2/K4 (slash dialect) | **all present**, e.g. `:40` `"Requirements: R2, R6"`; `K4` at `:46,51` |
| `2026-06-28-011` (3) | unique | U8-1, U8-2, U8-3 | **NOT present** -- plan has `### U8.` with `Requirements: R9, R10`, no `U8-1/2/3` subdivision anywhere. **DANGLING.** |
| `2026-06-29-001` (2) | unique | R5 | present, `:57` `"R5. Fallback: ..."` |
| `2026-07-03-001` (2) | unique | R7 | present, `:43` `"R7. CP-SAT output is scored..."` |
| `2026-07-08-005` (2) | unique | R4 | present, and the plan's own frontmatter self-cites `"@req(2026-07-08-005, R4/R5) tags"` |
| `2026-07-08-006` (2) | unique | R5 | present, plan frontmatter self-cites `"@req(2026-07-08-006, R5/R6)"` |
| `2026-07-09-001-...` (10) | unique (full filename given) | R1 | present; plan frontmatter self-cites these exact tags |
| `2026-08-02-004` (5) | unique | R20 | present, `:40` `"R20. Soundness-proof register..."` |
| `2026-06-23-001` (1) | **ambiguous** (3 candidate plans share this date-prefix) | U4 | resolves in `hv-lv-guard-strip-plan.md:128` (`### U4. Unit, Integration, and Golden-Fixture Tests`), the topically-matching candidate |
| `2026-06-28-001` (15) | **ambiguous** (3 candidates) | R7, R21 | R7 resolves in `astar-pathfinding-validation-plan.md:1005` (a table row: `| R7 | U1 | Dijkstra oracle implementation |` -- matches the annotation's own note verbatim) |
| `2026-06-28-006` (11) | **ambiguous** (2 candidates) | FR-LANG2, FR-ADOPT1, FR-BMC1, FR-ENUM1, FR-ENUM3, FR-CI5 | all resolve, but only in `railway-bmc-encoding-correctness-plan.md`, **not** the other same-date candidate `sat-encoding-optimization-experiment-plan.md` |
| `2026-07-23-001` (1) | **ambiguous** (2 candidates) | R2 | resolves in `finish-the-board-drc-erc-guard-plan.md:77`, not the other candidate |
| `2026-06-29-feat-los-bb` (5) | **no plan exists** | R1,R3,R4 | `ls docs/plans/ \| grep '^2026-06-29-feat-los-bb'` and `git log --all --diff-filter=A -- "docs/plans/2026-06-29*"` both empty. **DANGLING.** |
| `2026-07-22-005` (5) | **no plan exists** | R1,R2,R6 | same check, empty. Two other files (`.github/workflows/python-tests.yml:2113`, `scripts/manifest.yaml:1757`) cite "plan 2026-07-22-005" in prose too, but no document by that name has ever existed at any commit on any branch. **DANGLING.** |

**Result: of the 16 distinct plan-id groups sampled (144 raw instances),
13 resolve cleanly to a real, existing requirement; 1 group (3 instances,
`2026-06-28-011`/U8-1..3) is dangling at the requirement-ID level (plan is
real, sub-IDs were never defined); 2 groups (10 instances) are dangling at
the plan level (no such plan document has ever existed, on any branch);
4 groups (28 instances) resolve correctly but only after manually
disambiguating between 2-3 candidate plan documents that share the same
date-prefix** -- a distinct defect (unresolvable-by-machine ambiguity, not
absence) from either "dangling" bucket.

#### 2.4.2 Category D example

```python
# packages/temper-placer/tests/deterministic/test_bottleneck_map.py:1-3
"""Tests for BottleneckMap dataclass and load_bottleneck_map loader.

@req(2026-06-23-004, R3)
"""
```
Real plan, real requirement (`R3` is in the seed-filtering plan's
requirements list, confirmed in §2.4.1's table) -- but it's prose inside a
module docstring, not a `#`-prefixed comment, so `_PYTHON_REQ_RE` cannot
match it even disregarding the hyphen problem.

#### 2.4.3 Category B: `U9` is a confirmed-dangling plan-id, for an unusual reason

```
packages/temper-placer/src/temper_placer/validation/drc_oracle.py:250:
    # @req(U9, R1): Call temper_drc_rs.run_drc() instead of Python CheckRunner
packages/temper-placer/tests/validation/_drc_oracle_py_oracle.py:195:  (same)
```
`U9` is not one of the 11 registered plan-ids (`N1`-`N10`, `APC1`). It also
isn't a usable plan-id under *either* of this repo's other two conventions:
it's not a `docs/plans/YYYY-MM-DD-NNN...` filename prefix, and while `### U9.`
*is* a common internal section label -- it independently exists as the 9th
unit in **at least 24 different plan documents** (`grep -c '^### U9\.'
docs/plans/*.md`), so as a bare token it cannot identify which plan's `U9`
is meant. This looks like the author dropped the actual plan-id and wrote
only the requirement's own internal sub-unit label into the plan-id slot --
**dangling, and unresolvable even by hand**, unlike the date-prefix
ambiguity cases above (which *do* resolve with topical judgment).

### 2.5 A false positive found in `check_traceability.py` itself, while verifying its output

`--check-registry-scope`'s violation list (§2.2) includes:
```
SCOPE ISSUE: APC1: scope entry 'packages/temper-placer/tests/router_v6/' is not tracked by git
```
This is wrong. The directory has 310 real, git-tracked files under it:
```
$ git ls-files | grep -c '^packages/temper-placer/tests/router_v6/'
310
```
The check (`check_traceability.py:190-194`) does:
```python
for scope_entry in plan_entry.get("scope", []):
    if scope_entry not in git_files_set:
        violations.append(f"{plan_id}: scope entry '{scope_entry}' is not tracked by git")
```
`git_files_set` is built from `git ls-files` output, which lists **files
only** -- git does not track directories, so a directory-shaped scope entry
(`.../router_v6/`, trailing slash, matching the `_iter_source_files`
directory-glob convention used elsewhere in the same file, `:98-104`) can
**never** be a member of `git_files_set`, regardless of whether it or its
contents exist. Every directory-shaped scope entry in the registry will
fail this specific check unconditionally. Of the 7 SCOPE ISSUE lines the
gate reports, **6 are real** (5 for `N2`/`N4` pointing into the deleted
`packages/temper-drc/`, confirmed via `git log --diff-filter=D`; 1 for
APC1's `all_pad_evidence.py`, confirmed retired in `3f01f558b`) and **1 is
this false positive**.

---

## 3. Answering the task's specific questions

**Claim 1 (347):** Real, exact, reproduced with the command shown. The
check is sound, not over-broad -- hand-verified against raw board/netlist
reads independent of the gate's own code, and the root cause traces to two
specific, dated, real elec commits (`5842767c2` ZCD deletion,
`c617e0d08` OCP-02 insertion) with no intervening resync.

**Claim 2 (151/167):** Directionally right, numerically off (real number:
152/164, a 92.7% miss rate vs. the claimed 90.4%). More importantly, the
*mechanism* claimed ("opt-in scope, so unchecked-by-design") is only a
small part of the true picture: of the 152 unchecked, only 2 (`U9`) are
well-formed-but-unregistered -- the closest thing to a genuine scope/registry
gap; the other 150 (144 hyphenated + 1 no-marker + 5 multi-field) are
**structurally invisible** to the checker's own regex regardless of any
scope decision. That's a tooling defect (unhandled ID-format cases), not
evidence of a working opt-in policy being exercised as designed.

**Dangling vs. unchecked, summarized:**
- **Unchecked but real** (majority): 109 of 152 (152 unchecked minus 15
  dangling minus 28 ambiguous) -- annotations citing real plans and real
  requirements that the gate cannot see, for one of the mechanical reasons
  in §2.4's partition table.
- **Genuinely dangling**: 15 confirmed by hand (`U8-1/2/3` x3,
  `2026-06-29-feat-los-bb` x5, `2026-07-22-005` x5, `U9` x2) -- a plan or
  requirement that does not exist, named directly.
- **Ambiguous** (neither clearly dangling nor clearly checked): 28 --
  resolve to a real target only after manual disambiguation among
  same-date sibling plans; no mechanical check today can perform that
  disambiguation.
- **Actually scanned and validated today**: 12, of which 6 fail (4 false
  positives from the `R\d+`-only requirement-parser missing real `U1-U4`
  IDs in an active plan, confirmed by reading the plan directly; 2×3
  correctly-flagged `APC1`-is-`completed` status mismatches, which is the
  gate working as documented, not a defect).

No `pcb/**` file was modified during this verification. All commands and
their raw output are reproducible from the commit pinned in this file's
provenance header.
