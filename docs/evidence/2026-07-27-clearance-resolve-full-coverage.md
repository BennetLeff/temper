# Clearance re-solve at full domain-classification coverage: 17 -> 0 REQ-SAFE-01 violations

**Date:** 2026-07-27
**Scope:** `pcb/temper.kicad_pcb` (re-solved and rewritten). No `elec/src/*.ato` changes, no gate
script changes. Driver scripts used to run the constraint-generation/solve/write/audit pipeline
were scratch files under `/private/tmp/.../scratchpad/` (not committed) -- this doc reports their
exact invocations and output.

**Base:** worktree started on `worktree-agent-ac248dfa8513b0fc5`, 265 commits behind /
1 commit ahead of `docs/methodology-loop-discipline` (stale squash-merge artifacts, same pattern
documented in the prior 2026-07-27 evidence docs). Fixed via repoint, not rebase: `git fetch origin
&& git checkout -B worktree-agent-ac248dfa8513b0fc5 origin/docs/methodology-loop-discipline`.
`scripts/assert-base.sh docs/methodology-loop-discipline` confirmed exit 0 (HEAD `9ddd7059`) before
any implementation. Mid-session, the shared branch advanced by one commit (a gate-script baseline
fix, `a3e83fb2`, touching only `power_pcb_dataset/baselines/`, not `pcb/` or `elec/`) -- fast-forwarded
cleanly (`git merge --ff-only`) before committing this work.

---

## 0. Why this task exists

`docs/evidence/2026-07-27-domain-classification-coverage.md` (prior task, same branch) rewrote
`_real_board_fixture.py` to derive its `VoltageDomain` classification from
`elec/domain_manifest.yaml` (47 nets, 156/170 components, 91.8% coverage) instead of a
hand-maintained, independently-drifted 10-net dict (127/170 components, 74.7% coverage). Feeding
the wider classification into `verify_iec60335_compliance` against the then-current board surfaced
**17 REQ-SAFE-01 violations across 9 component pairs** (worst 2.262mm where 3.0-6.0mm is required)
-- real placement defects that the previous CP-SAT solve, having only ever seen the narrow 10-net
boundary set, was never asked to avoid. That task's own board was explicitly read-only (a
concurrent agent was routing it), so it reported the finding without fixing it. This task performs
the re-solve.

---

## 1. Falsifier (stated before starting) and whether it fired

**Falsifier (as suggested by the task):** *"the constraint set already covered these pairs, so a
re-solve changes nothing"* -- i.e. the previous solve's constraint set (generated from the legacy
10-net classification) already contained `SeparatedConstraint`s for the 9 violating pairs, so a
re-solve using the full classification would add nothing new.

**Checked directly, before touching the board:** generated both constraint sets
(`generate_domain_clearance_constraints`) against the then-current board -- legacy (10-net,
**7843** constraints, matching the previous solve's own count) and full (47-net, **11725**
constraints) -- and checked whether each of the 9 violating pairs appears in each set:

| pair | in legacy set (what the previous solve saw) | in full set (what a re-solve would see) |
|---|---|---|
| R27<->C28 | **False** | True |
| R27<->R70 | **False** | True |
| R58<->R60 | **False** | True |
| C23<->D3 | **False** | True |
| R23<->R69 | **False** | True |
| R27<->U9 | **False** | True |
| R28<->R25 | **False** | True |
| R4<->R53 | **False** | True |
| R7<->R2 | **False** | True |

**FALSIFIER DID NOT FIRE.** None of the 9 pairs were in the legacy set the previous solve actually
used -- confirming the previous solve was structurally incapable of avoiding these violations (it
was never asked to), and that widening the constraint set and re-solving is the correct next step,
not a no-op. Directly re-confirmed the 17-violation/9-pair figure at this point too:
`verify_iec60335_compliance` against the full classification and the (still unmodified) board:
`passed=False, error_count=17` -- exact match to the prior evidence doc's Sec 5 table.

---

## 2. Re-solve

### 2.1 Constraint generation

Two groups of `SeparatedConstraint`s were generated and combined into one `extra_constraints` list
for a single CP-SAT solve (not two solves):

1. **Primary domain-clearance constraints** -- `generate_domain_clearance_constraints(full_placement,
   full_voltage_domains, component_refs=...)` against the full 47-net manifest classification:
   **11725 constraints** (up from the previous solve's 7843, tracking the classified-component
   increase 127->156).
2. **Keep-away constraints (added in this pass, see Sec 3 for why)** -- one `SeparatedConstraint`
   per (unclassified component, HV-classified component) pair, at `MAX_IEC_MARGIN_MM` (8.0mm --
   computed from `IEC60335_REQUIREMENTS`, not hardcoded), excluding pairs that are both members of
   the same declared `protective_impedance_chains` entry (the same structural exemption
   `_real_board_fixture.py`'s fail-closed proximity check already uses, reused via its own
   `_chain_sibling_exempt_pairs` helper, not reimplemented): **684 constraints** (14 unclassified
   refs x 49 HV-classified refs, minus 6 exempt pairs).

Total: **12409 constraints** fed to `solve_placement`.

### 2.2 Solve

```
solve_placement(netlist=..., board=..., extra_constraints=all_constraints,
                 timeout_ms=180_000, seed=0)
```

No other PCL constraints loaded (`configs/pcl/temper_production.yaml` is stale against the current
netlist, same scope decision the prior R24 passes made and documented in their own evidence docs;
re-authoring it is a separate, out-of-scope follow-up).

**Result:**

```
Solver status: optimal   solve_time_ms=35976   wall=36.0s
Placed refs: 170 / 170
components_updated=170  components_skipped=0
```

`status=optimal`, 170/170 placed, well under the timeout budget. **Feasibility in 152x234mm
confirmed** -- the "infeasible/unknown" failure mode did not fire.

### 2.3 Write-back

Same origin-offset workaround as the two prior domain-clearance evidence docs (the CLI's
`optimize --no-loop` path has a known, still-unfixed bug that omits this offset; not fixed here,
out of scope): `solve_placement()` returns positions in the CP-SAT model's local `(0,0)`-based
frame; board origin is `(20, 20)` (confirmed: `parse_kicad_pcb(...).board.origin == (20, 20)`).
The write driver adds `board.origin` explicitly before constructing each `PlacementUpdate`, and
passes `components=netlist.components` to `write_placements_to_pcb` so the bounding-box-center ->
footprint-origin conversion (via each component's `_center_offset_x/_y` attributes, set by the
parser) is applied correctly.

---

## 3. A falsifier-style finding mid-implementation: the first solve attempt regressed a *different*
check

The first re-solve pass used only the primary 11725 domain-clearance constraints (Sec 2.1 item 1).
It correctly drove the 17 REQ-SAFE-01 violations to 0 (confirmed both in-memory and via a fresh
`load_real_board_placement()` re-parse of the written board), but running the full test suite
afterward surfaced a regression in `test_clearance.py`'s **fail-closed unclassified-near-HV
proximity assertion** -- a check this task's own instructions say must survive:

```
AssertionError: 1 unclassified component(s) sit closer than the largest IEC margin (8.0mm) to a
declared-HV component, with no exemption on record: R52 (safety.ovp.r_div_top2) at 6.521mm from
C14 (aux_supply.c_in_bulk)
```

**Root cause, verified directly:** R52 (an interior OVP-divider node, deliberately left
unclassified per the prior coverage-gap doc's own reasoning -- neither HV nor SELV by voltage) has
no classified net, so `generate_domain_clearance_constraints` can never emit a constraint
involving it (the generator pairs strictly on classified-net membership). The first solve, doing a
full 170-component reshuffle with no warm start, was therefore completely free to place R52
anywhere relative to C14 (a genuinely HV/DC_BUS-classified part) -- and coincidentally placed it
6.521mm away, under the 8.0mm margin. (Before either solve, R52's nearest HV neighbour was C4 at
11.117mm, comfortably clear -- confirmed against the pre-resolve board backup.) This was a new
regression introduced by the first solve attempt, not a pre-existing condition.

**Fix:** added the keep-away constraint group (Sec 2.1 item 2) and re-ran the solve from the
original (unmodified) board a second time with both constraint groups combined in one solve. This
mirrors the exact margin and exact "nearest HV neighbour" relationship the fail-closed proximity
check already enforces post-hoc, as a hard CP-SAT constraint enforced *during* the solve, for every
unclassified component against every HV-classified component (not just the one pair that happened
to regress) -- so the fix is general, not a point patch for R52/C14 specifically. The chain-sibling
exemption (`R59<->R58`, etc.) is preserved by construction (reused, not reimplemented).

---

## 4. R24 post-solve audit (`audit_domain_clearance`)

Regenerated all 12409 constraints (primary + keep-away) fresh, then recomputed real Euclidean
center-to-center distance from the *solved, written* absolute coordinates (not the solver's own
"optimal" claim) for every one:

```
constraints audited (candidates): 12409
AUDIT mismatches: 0
```

**0 mismatches across 12409 constraints.** Independently re-verified a second, stronger way: fresh
process, fresh `parse_kicad_pcb` read of the *written* `pcb/temper.kicad_pcb` from disk (both
normalized and absolute-coordinate reads), fresh constraint regeneration, fresh audit call --
**0 mismatches / 11725** (the primary-only re-check) and confirmed **0 components outside the
`(20,20)-(172,254)` outline** from the raw absolute-coordinate parse (range: x=[21.23,169.80],
y=[21.23,252.67]).

---

## 5. Before / after violation counts

| Measurement | Before (original board, full classification) | After (re-solved + rewritten board) |
|---|---|---|
| `verify_iec60335_compliance` (full, 47-net) | `passed=False, error_count=17` | `passed=True, error_count=0` |
| Violating pairs | 9 (R27<->C28, R27<->R70, R58<->R60, C23<->D3, R23<->R69, R27<->U9, R28<->R25, R4<->R53, R7<->R2) | **0** |
| Non-exempt unclassified-near-HV proximity findings | 0 (pre-existing state) | 0 (confirmed to *stay* 0 after the keep-away-constraint fix; regressed to 1 in an intermediate, uncommitted solve attempt -- Sec 3) |
| `matched_components_in_placement_full` | 156/170 | 156/170 (unchanged -- classification, not placement, is what determines this) |

**17 -> 0.** All 9 previously-invisible violating pairs are now separated at or above their
required margin.

---

## 6. Test suite and gates

| Check | Result |
|---|---|
| `make netlist` | **76/76 assertions PASSED**, exit 0 |
| `scripts/check_domain_partition.py` | **exit 0** -- 0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance chain defects, over 47 declared nets / 2 domains / 10 isolators / 2 chains / 165 compiled nets / 170 components |
| `scripts/capacity_budget_gate.py` | **exit 0** -- 0 defects (3 packages / 165 nets / 36 pins / 27 SET-path inputs) |
| `scripts/mpn_fabrication_gate.py` | **exit 0** -- 0 new violations (120 parts inspected, 10 pre-existing allowlist entries, 17 unchecked-prefix MPNs reported not silently passed) |
| `scripts/check_derived_doc_drift.py` | **exit 0** -- 3 documents, 44 tables, 52 gate rows matched, 132 fields checked |
| `test_clearance.py::test_temper_board_clearance_compliance` | **PASSED** -- coverage printed (`156 of 170 components classified (91.8%), 47 of 165 compiled nets classified`), `coverage_ratio >= 0.85` guard satisfied (91.8%), fail-closed unclassified-near-HV proximity assertion satisfied (0 non-exempt findings), and the informational full-coverage check now prints **`0 REQ-SAFE-01 violation(s)`** (was 17) |
| `test_clearance.py` + `test_isolation.py` + `test_domain_clearance.py` (full files) | **67 passed, 2 failed** (see Sec 7 -- both failures are pre-existing and classification-only, not caused by this re-solve) |

---

## 7. UNVERIFIED / pre-existing, out-of-scope findings

- **`test_domain_clearance.py::TestRealBoardTP3Coverage` (2 tests) fail, both before and after this
  re-solve.** Root cause, verified via `git log`: commit `b1e5f89c` ("fix(placer): classify TP3's
  UVLO line so domain-clearance covers it") added `safety.uvlo_logic-line` to the fixture's old,
  hand-maintained `_NET_DOMAINS` dict and a companion test
  (`test_clearance.py::test_tp3_uvlo_line_is_classified`). A **later** commit, `70503e6d`
  ("fix(safety): close domain-clearance coverage gap..." -- the prior task on this branch),
  rewrote `_real_board_fixture.py` to derive classification from `elec/domain_manifest.yaml`
  instead, and `safety.uvlo_logic-line` was never added to the manifest -- so that net's
  classification, and the companion test that checked it, were silently lost in the rewrite
  (confirmed: `test_tp3_uvlo_line_is_classified` no longer exists in `test_clearance.py`, and
  `grep -n uvlo elec/domain_manifest.yaml` returns nothing). This is a **classification-only**
  regression (both failing assertions call `generate_domain_clearance_constraints` on `TP3`'s net
  membership, not on any board position) -- it fails identically regardless of board state,
  confirmed by the fact that it failed identically on both the pre-resolve and both re-solve
  attempts in this session. **Out of scope for this task** (re-solving placement cannot fix a
  missing manifest net declaration), not fixed here, and predates this session (both commits are
  ancestors of the branch tip this session started from). Flagged as a real, live gap for a future
  manifest-focused task, not silently left in a doc no one reads: `safety.uvlo_logic-line` should
  be added to `elec/domain_manifest.yaml`'s `SELV: nets:` list (it is documented in
  `docs/hardware/SELV_ISOLATION_REDESIGN.md` Sec 6 row 13 as "entirely SELV... no HV node
  referenced," per `b1e5f89c`'s own commit message).
- **The 684 keep-away constraints (Sec 2.1 item 2, Sec 3) are a solve-time addition invented in
  this session, not a pre-existing, R24-documented mechanism.** They reuse the exact margin and
  exemption logic the fail-closed proximity check already enforces post-hoc (not a new number or a
  new exemption), and are covered by the same `audit_domain_clearance` post-solve audit (their
  `id`s share the `domain_clearance_` prefix), but they were not present in either prior
  domain-clearance evidence doc's solve and are not (yet) generated by a reusable, tested function
  in `src/` the way `generate_domain_clearance_constraints` is -- they were assembled directly in
  this session's scratch driver script. Promoting them into a proper, tested function (with their
  own BMC-style validation, per `AGENTS.md`'s R24 discipline) is a reasonable follow-up, not done
  here to stay within this task's stated scope (re-solve the placement, not extend the constraint
  generator's shipped API surface).
- **`configs/pcl/temper_production.yaml`** -- still stale against the current netlist (carried
  forward from every prior R24/domain-clearance pass on this branch); not loaded into this
  re-solve, same scope decision as before.
- **`cli/__init__.py`'s `optimize --no-loop` origin-offset bug** -- still present and unfixed
  (documented by two prior evidence docs, re-confirmed present by inspection here, not
  re-exercised against the CLI directly). This re-solve's own driver script works around it
  (Sec 2.3) rather than fixing the CLI path.
- **`test_production_board_drc_regression`** (`test_regression_drc.py`) -- checked its `BOARD_PATH`
  and found it points at `power_pcb_dataset/corpus/temper/temper.kicad_pcb`, a **separate corpus
  copy**, not `pcb/temper.kicad_pcb` -- confirmed unaffected by, and irrelevant to, this task's
  change. Not run.
- **Whether the wholesale 170/170 repositioning (no warm-start, twice in this session) changed
  anything relevant to future routing quality** -- not evaluated; routing is untouched (0
  segments/vias/zones, confirmed before and after) and out of scope.
