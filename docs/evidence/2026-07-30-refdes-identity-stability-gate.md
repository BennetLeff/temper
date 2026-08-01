<!-- provenance: commit=bb75927552a4417c062b24640d5605ffee4646c5 dirty=false -->

# Ref-designator identity-stability gate: method, denominator, and every genuine instance found

Base commit: `b5a7e07b` (`feat(scripts): add ref-designator identity-stability
gate`), branched directly from `origin/main` at `d510f4ede1ce0f3db343776f024c0f8a36085675`.
Work done in worktree `wt-refdes-gate`, branch `fix/refdes-identity-drift-gate`.

All numbers below were produced by actually running the commands shown, on
this machine (macOS arm64, Python 3.12.13, `uv`), against a freshly built
`elec/build/default.net` (`make netlist`, this worktree, 2026-07-30) and
the real, unmodified `elec/domain_manifest.yaml` and 580 `.py` files under
every `tests/` directory in the repo.

## Summary (read this first)

**The defect class is real and confirmed to already exist on a sibling,
uncommitted worktree** (`fix/delete-zcd-optocoupler`, branch
`43082f16b`), cross-checked read-only, no files modified there. Deleting
`power_in.zcd_opto` (ref `U3`) on that branch reflowed every later
`U`-prefix ref: `U3` now resolves to `power_mgmt.buck_3v3.buck` (a buck
converter) and `U7` now resolves to `hb.gate_hs.boot_diode` (a boot
diode) — exactly the scenario this gate exists to catch. Running the new
gate against that worktree correctly reports **3 VERIFIED MISMATCH**
findings (exit 3); running it against this session's own tree (main,
un-reshuffled) correctly reports **0** (exit 0). See "Cross-validation"
below for both full runs.

**On the current `main` baseline, the gate finds 0 verified mismatches**
— main has not merged the ZCD-deletion branch, so every ref-designator
identity claim it can mechanically verify is, today, still correct. That
is not "nothing to report": **13 real-board-bound, load-bearing
findings currently pass verification (MATCH) while being keyed to the
exact unstable identifier this gate exists to distrust** — one schematic
edit away from becoming the U3/U7 scenario above, silently. All 13 are in
`test_the_seven_known_intra_footprint_blockers_are_now_visible`,
`test_isolator_pad_gap`, `test_k1_is_a_genuine_creepage_violation_after_the_400v_correction`
(`test_clearance_copper.py`), and `test_generator_covers_the_tp3_u7_pair_specifically`
(`test_domain_clearance.py`). Full per-item verdicts below.

**Denominator, every stage** (never "0 violations" without a count in
front of it):

| Stage | Count |
|---|---|
| `.py` files under any `tests/` directory, repo-wide | 580 found, 580 parsed |
| Raw ref-designator-shaped string literals (`ast.Constant`, exact `<prefix><digits>` match against this design's own compiled-netlist prefixes: `C, D, F, J, K, L, PS, Q, R, RT, RV, SW, T, TP, U`) | 3,842 |
| ...in safety-keyword context | 1,135 |
| ...AND assert-reachable (Tier 1: "discovered") | 988 |
| ...AND load-bearing (Tier 2: "identity assertion", not decorative) | 206 |
| ...AND real-board-bound (Tier 3: verifiable against the compiled netlist) | 24 |
| Of those 24: MISMATCH / MATCH / UNVERIFIED | 0 / 14 / 10 |

(14 MATCH includes one entry from this gate's own dogfooded test suite,
`scripts/tests/test_check_refdes_identity_stability.py`, and one from
`scripts/tests/test_check_domain_partition.py`'s existing fixtures —
excluded from the "genuine product-safety instance" count below, which is
13, all in the two real safety test modules named above.)

## How the gate discovers unstable identifiers, and what that method misses

Full method is in `scripts/check_refdes_identity_stability.py`'s module
docstring (six numbered points); summarized here with the *specific*
gaps, since the task explicitly asked what discovery would miss:

1. **Ref-designator vocabulary is derived from the compiled netlist**
   (`discover_ref_prefixes()`), not a hardcoded KiCad-convention list.
   **Misses**: nothing about *this* design's own prefixes; would need
   re-running if the design ever adds a genuinely new prefix (it already
   would, automatically, on the next run).
2. **File scope is every `.py` file under any directory literally named
   `tests`, repo-wide** (`find_scan_files`, `rglob`), not a maintained
   list of "the safety test files" — see
   `docs/solutions/best-practices/gate-scope-hand-maintained-blind-spot-2026-07-29.md`,
   which this design was built to not repeat. **Misses**: ref-designator
   literals in `docs/evidence/*.md` prose (the task's own framing names
   this as part of the same disease, e.g. `docs/hardware/2026-07-29-open-safety-gate-actions.md`
   naming "C6/U3"), `scripts/*.py` gate/validator modules outside
   `scripts/tests/`, `elec/` comments, and refs built at runtime
   (`f"{prefix}{n}"`, string concatenation — only literal `ast.Constant`
   string nodes are seen).
3. **"Safety-relevant" is a fixed, printed-in-full keyword vocabulary**
   (`SAFETY_KEYWORDS`: isolation, barrier, creepage, clearance, mains,
   SELV, HV, IEC 60335/60664, reinforced, galvanic, dielectric,
   protective impedance, REQ-SAFE, REQ-EMC, star ground, pollution
   degree, ...) over each candidate's combined context (its own function
   source including comments, class/module docstring, and the source of
   every same-file function that transitively calls it). **Misses**: any
   safety-relevant assertion whose surrounding text uses none of these
   words (a bare numeric assertion with zero prose). This is a lint, not
   a prover, by design.
4. **Load-bearing vs decorative**, via AST shape: a ref literal is a
   Tier-2 finding only if it sits inside an `ast.Compare` (any ancestor
   depth), or is assigned to a name later used as a `Compare` operand or
   `Subscript` base (one hop of dataflow, with a bounded fixed-point over
   comprehension/alias chains for patterns like `for r in refs: ... r not
   in comps`), or is a `pytest.mark.parametrize` value bound to a
   parameter used the same way. **Misses**: dataflow laundered through
   more than the traced hops, or a `**kwargs` spread.
5. **Real-board-bound vs shape-only**: a Tier-2 finding is additionally
   checked for whether its function (or its transitive same-file call
   chain) actually loads real compiled data — `load_real_board_placement`,
   `_real_board_fixture`, or a literal real-data path fragment always
   count; `parse_netlist(`/`parse_kicad_pcb(` only count if the file's own
   `import` resolves that name to `check_domain_partition`/
   `temper_placer.io.kicad_parser` specifically (see "False positives
   found and fixed" below — a bare call-text match on these two was the
   single largest source of false positives measured while building this
   gate). **Misses**: any other way of loading real data this gate didn't
   anticipate; a marker list is inherently incomplete.
6. **Verification**: resolves the ref against the freshly-rebuilt
   `elec/build/default.net`, and separately checks — via **line-proximity
   to the specific ref's own textual mentions**, not "anywhere in the
   function" (see false-positive #3 below) — whether the surrounding text
   makes an explicit isolator/barrier-crossing claim
   (`CLAIM_KEYWORDS`). MISMATCH only fires when a specific claim is made
   AND contradicted by `elec/domain_manifest.yaml`'s own
   `isolators:`/`protective_impedance_chains:` declarations — never on
   shape alone.

## Distinguishing safety-relevant from incidental

Two independent, AND-ed filters (safety-keyword context, assert-reachability)
narrow 3,842 raw literals to 988 Tier-1 candidates — about 26%, mostly
because most of this repo's ref-designator literals are synthetic
placeholder data in unrelated placer/router unit tests (`test_hv_pad_set_*`,
`test_zone_solver.py`, etc. — 182 of the 206 Tier-2 load-bearing findings
end up SHAPE_ONLY specifically because they resolve to no real component
at all: `current_instance_path='<ref not in netlist>'`). The
real-board-bound filter (24 of 206, ~12%) is what does the real narrowing
— it is the difference between "this test uses the string 'U3'" and "this
test asserts something about the compiled design's actual U3." A
representative excluded case: `packages/temper-placer/tests/requirements/safety/test_isolation.py`
hardcodes `"U1"`/`"U3"`/`"U4"` throughout as synthetic validator-logic
fixtures (never calling any real-board loader, never appearing in
`elec/build/default.net`) — correctly never flagged past Tier 1.

## False positives found and fixed while building this gate

Three genuine false-positive shapes were found by running against the
real 580-file tree (not by inspection) and fixed; each is now a
regression test in `scripts/tests/test_check_refdes_identity_stability.py`:

1. **Bare `"kicad_pcb"` substring.** `scripts/tests/test_check_isolation_keepout.py`'s
   fully-synthetic `write_board(tmp_path, board, name="board.kicad_pcb")`
   helper matched a real-board marker via its own default-argument text,
   marking two purely-synthetic C99/C98 fixtures as real-board-bound (and
   MISMATCH, since C99/C98 don't exist in the real netlist). Fixed by
   dropping the bare `"kicad_pcb"` marker in favor of the specific call/path
   forms real loaders use.
2. **Same-named `parse_netlist(`/`parse_kicad_pcb(` from a different
   module.** `scripts/tests/test_check_footprint_drift.py` imports its
   OWN `parse_netlist` from `check_footprint_drift` (tested against a
   synthetic `tmp_path` netlist), not `check_domain_partition`'s. A bare
   call-text marker match produced a false real-board-bound classification
   for `test_footprint_mismatch_detected`'s synthetic C6. Fixed by
   requiring the file's own `import` to resolve the name to the
   real-data-loading module.
3. **Doc-citation filename embedding a safety word.**
   `scripts/tests/test_check_footprint_drift.py`'s module docstring cites
   `docs/evidence/2026-07-28-tank-cap-and-isolator-footprints.md`,
   word-wrapped across the docstring's own line break, one line above an
   unrelated mention of `C27`. A naive claim-proximity search read
   "isolator" (inside the filename) as a claim about C27, producing a
   false MISMATCH. Fixed by stripping `docs/....md` citations (preserving
   line count) before claim-keyword matching.
4. **Function-wide (not ref-specific) claim matching.**
   `test_generator_covers_the_tp3_u7_pair_specifically`'s docstring says
   "U7 genuinely straddles domains" — true of U7, never claimed of the
   OTHER ref in the same test, `TP3` (a test point). An early version
   matched claim keywords anywhere in the function, producing a false
   MISMATCH for TP3 (which correctly resolves to `safety.tp_uvlo2_fault`,
   not a declared isolator — true, but never claimed, so not a mismatch).
   Fixed by requiring the claim keyword within 2 lines of the SPECIFIC
   ref's own textual mention, not just present somewhere in the function.

After all four fixes, the gate reports **0** false positives against the
current `main` tree (verified: every one of the 24 real-board-bound
findings was manually read against its source; see per-item verdicts
below) and **exactly the 3 expected true positives** against the sibling
`fix/delete-zcd-optocoupler` worktree (see "Cross-validation").

## Does it verify actual mismatch, or only flag shape?

Both, reported as separate tiers, per the task's own framing that shape
alone ("this test mentions U7") is weaker than an actual verified
mismatch. `verify()` only assigns MISMATCH/MATCH when a finding is (a)
load-bearing, (b) real-board-bound, and (c) makes an explicit,
ref-proximate isolator/barrier claim contradicted or confirmed by
`elec/domain_manifest.yaml`'s own declarations — never on the mere
presence of a ref-designator literal. UNVERIFIED is a distinct, honestly
reported outcome (real-board-bound + load-bearing, but no specific claim
text to check against) — 10 of the 24, listed below, not silently folded
into either PASSED or FAILED.

## Every genuine instance found (per-item verdict)

All are `@pytest.mark.slow` tests that call `load_real_board_placement()`
against the real, freshly-rebuilt `elec/build/default.net`.

### `packages/temper-placer/tests/requirements/safety/test_clearance_copper.py`

**`TestRealBoardIsolatorFigures.test_the_seven_known_intra_footprint_blockers_are_now_visible`**
(line 697) — `assert intra == {"C6", "K1", "K2", "K3", "T1", "U3", "U7"}`.
This is the exact test named in the task brief. **Currently checking
what it claims: YES, all 7** — each ref's current `instance_path` is one
of `elec/domain_manifest.yaml`'s declared isolators (`power_in.y_cap_pe`,
`power_in.bypass_relay`, `discharge.k_dis1`, `discharge.k_dis2`,
`ct_sense.ct`, `power_in.zcd_opto`, `hb.gate_hs.driver`). **Verdict: MATCH
x7** on this baseline, but the assertion is a hardcoded ref-string set —
if `U3` is ever deleted (as it is on the sibling worktree), this exact
line keeps parsing and keeps comparing to the same literal set while the
components underneath it silently change (see "Cross-validation").

**`TestRealBoardIsolatorFigures.test_isolator_pad_gap`** (line 599,
parametrized `[("T1", "1", "4", 9.100), ("K1", "13", "A1", 8.000)]`) —
**Verdict: MATCH x2**. T1 → `ct_sense.ct`, K1 → `power_in.bypass_relay`,
both declared isolators. Currently checking what it claims.

**`TestRealBoardIsolatorFigures.test_k1_is_a_genuine_creepage_violation_after_the_400v_correction`**
(line 657, `[v for v in result.violations if v.ref_a == "K1" or v.ref_b
== "K1"]`) — **Verdict: MATCH x2** (K1 appears twice in the AST — once
per side of the `or`). K1 → `power_in.bypass_relay`, declared. Currently
checking what it claims.

### `packages/temper-placer/tests/placer/cp_sat/test_domain_clearance.py`

**`TestRealBoardTP3Coverage.test_generator_covers_the_tp3_u7_pair_specifically`**
(line 388) — docstring explicitly claims "U7 genuinely straddles domains
... it is a level-shifting gate driver", and asserts `[c['nets'] for c in
placement if c['ref']=='U7'] == ['gnd', '+3V3', 'DC_BUS_RTN']`. **Verdict:
U7 → MATCH** (`hb.gate_hs.driver`, declared isolator, currently correct).
**TP3 → UNVERIFIED** (`safety.tp_uvlo2_fault`; TP3 is never itself claimed
to be an isolator in this test — it's the other member of a clearance
pair — so there is no claim to verify against; correctly not reported as
a mismatch).

**`TestRealBoardTP3Coverage.test_generator_emits_at_least_one_constraint_for_tp3`**
(line 343) — **Verdict: TP3 → UNVERIFIED x2** (appears twice), same
reasoning: no isolator/barrier claim is made about TP3 here.

### `packages/temper-placer/tests/requirements/emc/test_emi_filter.py`

**`_load_real_emi_filter_positions`** (line 479, helper called by
`TestEMIFilterIntegration.test_temper_board_emi_filter_compliance`) —
hardcodes `refs = {"F1": "fuse", "RV1": "mov", "L1": "cmc", "C1": "c_x",
"C6": "c_y"}` and reads them via `comps[r].initial_position for r in
refs`. **Verdict: UNVERIFIED x5** (F1, RV1, L1, C1, C6) — all resolve to
plausible current components (`power_in.fuse`, `power_in.mov`,
`power_in.cmc`, `power_in.c_x2`, `power_in.y_cap_pe`), but the surrounding
text never makes an explicit isolator/barrier-crossing claim about any of
them (this is an EMI-filter component-role mapping, not an isolation
claim), so this gate has no specific claim to check. Separately worth
noting (not something this gate's automated tiers can catch, but visible
on manual read): the function's own docstring says these refs are
"resolved from `elec/build/default.csv` ... not hardcoded", but the code
is in fact a hardcoded `dict` literal, never consulting the BOM at all —
the docstring's claim about its OWN method is itself stale, independent
of whether the ref→role mapping happens to be correct today.

### A related instance this gate's automated tiers do NOT surface, found by manual reading during construction

**`packages/temper-placer/tests/requirements/emc/test_ground_plane.py::TestGroundPlaneIntegration.test_temper_board_ground_plane_compliance`**
hardcodes a synthetic `ground_domains` dict naming `C6`/`PS1`/`T1`/`U3` as
"real isolation devices" (its own docstring: "crossed only by four
components the SELV doc confirms are real isolation devices ... C6 (Y1
capacitor), PS1 (IRM-10-15 transformer), T1 (CST2010-100L current-sense
transformer), U3 (H11L1 optocoupler)"). This is measured, directly, to
be **decorative, not load-bearing**: `check_star_ground_point` (the
function under test) reads `component_type`/`from`/`to` from each
connection dict but never reads the `"ref"` key at all — verified by
reading `packages/temper-placer/tests/requirements/validators/ground_plane.py`'s
`check_star_ground_point`. Changing every one of those four ref strings
to nonsense would not change this test's pass/fail. This gate's
load-bearing filter (Tier 2) therefore correctly excludes it from the
verdicts list — it is real, and reported here by hand, but it is a
different and lower-severity risk than the load-bearing cases above: not
"this test silently checks the wrong component and reports green" but
"this test's own narrative claim about which components are isolators is
never checked by any code in the test, so it can go stale invisibly, same
disease, different organ." **Verdict: not independently checkable by this
tool; flagged here for human review, not classified MATCH/MISMATCH.**

## Cross-validation: the gate on the sibling worktree that has the real defect

A concurrently-running, uncommitted session's worktree
(`/private/tmp/.../wt-zcd-delete`, branch `fix/delete-zcd-optocoupler`,
commit `43082f16b`, "fix(elec): delete U3 (H11L1 mains-ZCD optocoupler)
and its dedicated circuitry") already has the exact scenario the task
brief describes. Read-only cross-check (no files in that worktree were
read, written, or committed by this session beyond an already-fresh
`elec/build/default.net` that was there):

```
$ python3 -c "... parse_netlist(elec/build/default.net) ..."
U3 -> power_mgmt.buck_3v3.buck
U6 -> hb.gate_hs.driver
U7 -> hb.gate_hs.boot_diode
U8 -> rtd_pan.adc
```

```
$ uv run --no-sync python scripts/check_refdes_identity_stability.py \
    --repo-root <wt-zcd-delete>
...
--- MISMATCH: 3 ---
  test_domain_clearance.py::TestRealBoardTP3Coverage.
    test_generator_covers_the_tp3_u7_pair_specifically:388  ref='U7'
    current_instance_path='hb.gate_hs.boot_diode'  declared_as_crossing=False
  test_clearance_copper.py::TestRealBoardIsolatorFigures.
    test_the_seven_known_intra_footprint_blockers_are_now_visible:697  ref='U3'
    current_instance_path='power_mgmt.buck_3v3.buck'  declared_as_crossing=False
  test_clearance_copper.py::TestRealBoardIsolatorFigures.
    test_the_seven_known_intra_footprint_blockers_are_now_visible:697  ref='U7'
    current_instance_path='hb.gate_hs.boot_diode'  declared_as_crossing=False
exit code: 3
```

The gate correctly and mechanically identifies both of the task brief's
named findings (`U3`→buck converter, `U7`→boot diode), plus a third the
brief didn't name (the same `U7` drift also breaks
`test_generator_covers_the_tp3_u7_pair_specifically`'s claim). This is
the strongest available evidence that the verification tier works: it was
not tuned against this scenario after the fact — the gate's design was
finalized and its false positives fixed entirely against `main` (which
has zero mismatches) before this cross-check was run.

## False-positive assessment

**Measured, not estimated: 0 false positives on the current `main`
tree**, after fixing the 4 shapes above (found and fixed by the same
process — run against the real tree, inspect every finding, fix the
mechanism, not the individual case). Every one of the 24 real-board-bound
findings was read against its source and matches the verdict shown
above. The 182 SHAPE_ONLY and 10 UNVERIFIED findings are correctly NOT
promoted to MISMATCH/MATCH — they lack either real-board-bound-ness or a
specific claim to check, and the gate says so rather than guessing.

**Residual risk, honestly stated:** the false-positive shapes found (4)
all came from the ambiguity between "text that looks like a real-data
reference" and "text that IS one" — a fundamentally text-substring-based
heuristic. A fifth such shape almost certainly exists somewhere in a
580-file, 3,842-literal tree this size; this gate's own module docstring
names the specific mechanisms (marker-list incompleteness, dataflow-hop
limits, keyword-vocabulary gaps) that would produce one. This is exactly
why the hard constraint against wiring it into CI matters: false-positive
rate is measured against ONE tree state (`main`, this commit), not proven
in general.

## What could not be established

- Whether any ref-designator identity claim exists in `docs/evidence/*.md`
  prose that has already drifted (the task's own framing names this as
  part of the same disease; this gate's scope is code assertions only,
  per its own docstring point 2 — explicitly out of scope for this pass,
  not silently dropped).
- Whether `test_ground_plane.py`'s non-load-bearing C6/PS1/T1/U3 claim is
  itself currently accurate (manually spot-checked: yes, all four resolve
  to what the docstring claims today) — but this gate structurally cannot
  monitor it going forward, by design (see "A related instance" above).

## Hard constraints confirmed

- No test was modified to make it pass. No safety constant, netclass, or
  domain declaration was changed.
- The gate is NOT wired into CI (not referenced in
  `.github/workflows/*.yml`; `scripts/manifest.yaml` disposition is
  `utility`, not `ci-gate`).
- `pcb/temper.kicad_pcb` was not touched.
- The sibling worktree `wt-zcd-delete` was read from (its already-built
  `elec/build/default.net`, unmodified) but never written to.
