<!-- provenance: commit=8d17cfe5ffa9662577c2cdc6aa7e3b379f5ab7f3 dirty=true -->

# Net-classification-by-substring CI gate

Base commit: `466c7724` (`merge: clearance's HV gate under-matched; copper
area figure was correct after all`), branch `docs/methodology-loop-discipline`.
Work done in worktree `agent-a952dedb2a1b22bc4`, branch
`fix/net-classification-gate`, checked out directly at that commit.

All numbers below were produced by actually running the commands shown, on
this machine (macOS arm64, Python 3.12.13, `uv`), not inferred.

## The defect class

Safety-relevant net classification (HV vs. SELV) decided by testing whether
a short keyword is a **substring** of a net's (uppercased) name, maintained
by hand in a list that lives beside -- and never reads from --
`elec/domain_manifest.yaml`, this project's canonical, human-reviewed
HV/SELV declaration. Confirmed three times before this change, twice on
2026-07-27, in opposite directions:

1. **`creepage_check.py`** (fixed in merge `5076e715`) -- FALSE POSITIVES.
   `broad_keywords` contained `"L1"`, `"L2"`, `"LINE"`, matched via plain
   `kw in name_upper`, under a comment asserting "substring match is safe
   for these". `"L1"` matched `COIL1`, `"L2"` matched `COIL2`, `"LINE"`
   matched `safety.ovp-line`. All 24 reported creepage violations on the
   live board were false positives on SELV nets; the real mains nets
   `ac_l`/`ac_n` matched no broad keyword at all.
2. **`clearance_check.py`** (fixed in merge `466c7724`) -- FALSE NEGATIVES,
   the mirror image. HV was classified by four substrings (`AC_`, `HV_`,
   `HIGH_VOLTAGE`, `MAINS`) that, on this board, matched only `ac_l`/`ac_n`.
   Eleven real HV-domain nets declared in the manifest silently fell
   through to a 0.127mm default instead of the IEC 60335 requirement -- one
   confirmed pair moved from 0.127mm to 14.0mm once fixed.
3. **`clearance_engine.py:125`** -- STILL LIVE, unfixed until this change.
   `any(kw in upper for kw in ("HIGH_VOLTAGE", "HV", "MAINS_240V", "MAINS",
   "AC"))`.

## What was found auditing the rest of the codebase for the same shape

Fixing instance 3 and then asking "where else does this exact shape occur"
(both by hand and, once built, by running the new gate against the tree)
surfaced **six more** live instances, all fixed in this change:

| # | File:function | Bug shape | Live collision proven? |
|---|---|---|---|
| 4 | `clearance_check.py:726 _classify_net_class` | `hv_keywords` includes `"L1"`,`"L2"`,`"L3"`,`"LINE"` -- the *identical* substrings already fixed in `creepage_check.py`, reintroduced in a sibling function since commit `1e99a151` (predates merge `466c7724`; not introduced by it) | **Yes** -- matches `discharge.k_dis1-coil1/coil2`, `power_in.bypass_relay-coil1/coil2`, `safety.uvlo_logic-line` (all declared SELV in the manifest) |
| 5 | `clearance_check.py:690 _get_required_clearance` | `hv_keywords = ["AC_","HV_","HIGH_VOLTAGE","MAINS"]` left unfixed by merge `466c7724` (which ORed in manifest membership but never touched this line) | No live collision proven; redundant now that manifest membership gives full coverage |
| 6 | `core/design_rules.py:230 _is_high_current_net` | bare `"COIL"` | **Yes** -- matches the same four SELV coil nets as #4 |
| 7 | `core/design_rules.py:223 _is_gate_net` | bare `"GATE"`,`"PWM"`,`"SW_NODE"` | No live collision proven |
| 8 | `router_v6/net_classification.py` (`_matches_any`) | bare `"PE"` in `HV_NET_PATTERNS` -- this module's own docstring calls it "the single source of truth" | No live collision (the `pe` net was merged into `gnd`, per the manifest) but a landmine for any future net containing "PE" |
| 9 | `core/net_classification.py` (`_matches_any`) | a **near-duplicate module** of #8, same patterns, same bug, still unfixed | Same as #8 -- found only because the new gate could not statically resolve its `patterns` parameter and reported it UNRESOLVED rather than silently safe |

Seven more call sites across the codebase shared the exact syntactic shape
(bare `"HV"`/`"GATE"`/`"BUS"`/`"DC_BUS"`/`"MAINS"` substring tests feeding
real clearance/trace-width/zone decisions) and were fixed the same way:
`core/priority.py:132,134`, `deterministic/stages/zone_aware_slot_generation.py:389`,
`router_v6/constraints_design_rules.py:411` (feeds the live DRC oracle,
`constraints_drc_oracle.py`), `router_v6/trace_width_assignment.py:113,129`,
`io/net_class_manager.py:330`, `_constraint_types/config.py:452` (feeds the
deterministic pipeline's phase-rotation HV check), and
`clearance_engine.py:177,181` (the `MAINS`/`120`/`240` refinement left as
unanchored substrings in the instance-3 fix, closed with a
trailing-"V"-aware boundary regex instead of left unanchored).

**Nine confirmed instances of the same defect class, fixed in nine
commits on this branch.**

## Fixes: proof each removes only false matches and adds none

Every fix uses the same technique the two historical fixes already
established: word-boundary regex, `re.search(r"(?:^|_)KEYWORD(?:$|[\d_])",
upper)`, delimited by `_` or start/end of the uppercased name (mirroring
`creepage_check.py`'s already-fixed `AC`/`HV` checks, which used this
exact pattern before the rest of that function did).

### `clearance_check._classify_net_class` (differential proof)

```
$ uv run --no-sync python3 -c "..."   # old plain-substring vs new anchored, against every manifest net
=== SELV nets: old vs new ===
  FIXED false positive: 'safety.uvlo_logic-line' old=True new=False
  FIXED false positive: 'discharge.k_dis1-coil1' old=True new=False
  FIXED false positive: 'discharge.k_dis1-coil2' old=True new=False
  FIXED false positive: 'discharge.k_dis2-coil1' old=True new=False
  FIXED false positive: 'power_in.bypass_relay-coil1' old=True new=False
  FIXED false positive: 'power_in.bypass_relay-coil2' old=True new=False
SELV false positives removed: 6, remaining: 0
=== HV manifest nets: keyword-based classification unchanged (ac_l, ac_n, SW_NODE still True; manifest-membership path unaffected) ===
```

### `clearance_engine._net_class_to_voltage_class` (differential proof)

```
=== canonical labels (only inputs ever passed by the real caller): old vs new agree on all 9 tested, except: ===
  'SELV': old(hv=False,lv=True) new(hv=False,lv=False)   # bonus fix: old code
          misrouted the literal label "SELV" to LOW_VOLTAGE via a bare "LV"
          substring match inside "SELV" -- never triggered by the live
          caller, but the function's own docstring documents "SELV" as an
          expected input
=== synthetic proof: bare HV/AC substring risk this closes ===
  'BLACKOUT': old_hv=True new_hv=False
  'IMPACT':   old_hv=True new_hv=False
  'MACRO':    old_hv=True new_hv=False
  'HVAC_ZONE':old_hv=True new_hv=False
```

### `router_v6/net_classification.py` / `core/net_classification.py` (differential proof)

```
=== synthetic proof: bare "PE" collision closed ===
  'SPEED_SENSE':    old_hv=True new_hv=False
  'TYPE_A':         old_hv=True new_hv=False
  'OPEN_DRAIN':     old_hv=True new_hv=False
  'EXPECT_ACK':     old_hv=True new_hv=False
  'PERIPHERAL_CLK': old_hv=True new_hv=False
=== manifest SELV nets: 0 old-vs-new differences (no accidental collision was live on this board) ===
```

### `core/design_rules._is_high_current_net` (proof of the live collision)

```
$ uv run --no-sync python3 -c "..."
discharge.k_dis1-coil1 ['COIL']
discharge.k_dis1-coil2 ['COIL']
power_in.bypass_relay-coil1 ['COIL']
power_in.bypass_relay-coil2 ['COIL']
safety.uvlo_logic-line []
```
(all four `COIL` hits are declared SELV "coil drive" nets in the manifest;
fixed with the same word-boundary technique.)

Every fix was verified against the real test files covering the module it
touched, not just re-derived by inspection:

- `clearance_engine.py` / `clearance_check.py` (all four functions
  touched): `tests/router_v6/test_clearance_boundary.py`,
  `test_clearance_check.py`, `test_clearance_induction.py`,
  `test_clearance_segment_dist.py`, `test_clearance_rust_differential.py`,
  `test_creepage_properties.py`, `test_creepage_induction.py`,
  `test_creepage_boundary.py`, `test_creepage_check.py`,
  `tests/requirements/safety/test_clearance.py` -- **363 passed, 14
  xfailed**, both before and after every one of the four commits touching
  this file family.
- `core/design_rules.py`: `tests/core/test_design_rules.py` -- 24 passed.
- `router_v6/net_classification.py`: `tests/router_v6/test_wave1_easy_wins.py`,
  `test_phase1_anti_false_zero.py` -- 15 passed, 1 skipped.
- `core/net_classification.py`: `tests/placer/cp_sat/test_feedback.py`,
  `tests/pcl/test_netclass_constraints.py`, `test_e2e_netclass_ssot.py`,
  `test_netclass_feedback.py`, `tests/placer/cp_sat/test_compound_loop.py`
  -- 48 passed.
- `_constraint_types/config.py`, `trace_width_assignment.py`,
  `net_class_manager.py`: `tests/router_v6/test_trace_width_assignment.py`,
  `tests/constraint_types/test_placement_constraints.py`,
  `test_config.py`, `tests/deterministic/test_isolation_slots_in_slot_generation.py`
  -- 58 passed, 1 skipped.

Three unrelated pre-existing failures were encountered during this work
(`test_via_layer_properties_pbt.py::test_written_segments_connect_all_pads_per_net`,
`test_mcu_subsystem.py::test_mcu_subsystem_heuristic`,
`test_drc_validation.py`'s `Track.to_segment`/`Pad.rot_rect`
`AttributeError`s) and confirmed present against the unmodified,
pre-this-change files too (temporarily restored via `git show <commit>:<path>`,
re-ran, identical failures, restored the fix). Not touched by this change.

## The gate: `scripts/check_net_classification.py`

**Design decision, AST-level over regex-over-source-text**: a regex
scanning source text for `any(\w+ in \w+ for \w+ in` would be fragile
against reformatting, would miss the equivalent explicit `for`-loop shape
(a future instance need not use `any()`), and cannot resolve a keyword
collection referenced by name several lines from the comparison. The gate
walks the AST tracking `for`/comprehension loop-variable bindings and same-file
constant-collection assignments, and flags any `Compare(in)` node where a
keyword (either a loop-bound variable resolving to a literal list/tuple/
set/frozenset, or a bare literal) matches a scoped HV/SELV vocabulary
(`HV`, `AC`, `MAINS`, `LINE`, `COIL`, `GATE`, `PHASE`, ... -- not every
net-class keyword in the codebase, since `elec/domain_manifest.yaml`
declares exactly the HV/SELV boundary, not a general taxonomy).

**Denominators, every run**: files inspected, `in`-operator call sites
discovered (resolved vs. unresolved, never silently dropped), candidates
matching the vocabulary, allowlisted, violations. Current clean state:

```
Net-classification-by-substring gate -- 3 scan target(s), 520 file(s), 495
'in'-operator call site(s) discovered (430 resolved, 65 unresolved)
  candidates (vocab match): 12  allowlisted: 12  violations: 0
Net-classification-by-substring gate passed
```

**Anti-vacuous-truth**: zero files or zero call sites discovered anywhere
in the scan is a hard TOOL ERROR (exit 5), never folded into "0
violations" -- unit-tested in `TestAntiVacuity`.

**Allowlist** (`.net-classification-allowlist`, 10 entries covering the 12
flagged-but-justified call sites): every entry is `qualname::file-glob  #
justification`, reviewed by hand. Categories: component ref-designator
classification (not a net name), config-schema-value parsing (not a net
name), silkscreen warning-label text / BOM value text (phrase-presence
detection in prose, a different problem than net-name classification),
connector-placement and routing-order heuristics (no clearance/creepage
consequence), one external-reference-design heuristic (no manifest
counterpart to parallel), and one dict-key-membership test the detector's
`Compare(in)` heuristic cannot distinguish from string substring matching
(documented as a known detector limitation, not a safety claim).

**Known detector limitation** (documented, not hidden): the gate cannot
statically distinguish `x in some_dict_or_set` (exact membership) from
`x in some_string` (substring test) -- both are `ast.Compare(ops=[In])`.
One allowlist entry
(`check_critical_loop_areas::.../layout.py`) exists purely for this
reason. This was judged an acceptable false-positive rate for a
high-recall gate resolved via a per-entry-justified allowlist, rather than
a narrower heuristic that risks missing a real future instance -- see
"Design stance" in the gate's own docstring reasoning.

## Falsifier

> "This gate catches all three historical instances. If it cannot flag the
> pre-fix `creepage_check.py`, the pre-fix `clearance_check.py`, and the
> live `clearance_engine.py`, it does not work."

Proven by retrieving each pre-fix file with `git checkout <commit> --
<path>` (no `git stash` used, per this task's hard rule), running the
gate, and restoring:

```
$ git checkout f9edf80e^ -- packages/.../creepage_check.py   # pre-fix (merge 5076e715)
$ git checkout 7ad5b15c^ -- packages/.../clearance_check.py  # pre-fix (merge 466c7724)
$ git checkout 466c7724  -- packages/.../clearance_engine.py # branch base, instance-3 unfixed
$ uv run --no-sync python scripts/check_net_classification.py
...
  VIOLATION .../clearance_check.py:627 in _get_required_clearance -- ...
  VIOLATION .../clearance_check.py:628 in _get_required_clearance -- ...
  VIOLATION .../clearance_check.py:677 in _classify_net_class -- ...
  VIOLATION .../clearance_engine.py:125 in _net_class_to_voltage_class -- ...
  VIOLATION .../clearance_engine.py:129 in _net_class_to_voltage_class -- ...
  VIOLATION .../clearance_engine.py:133 in _net_class_to_voltage_class -- ...
  VIOLATION .../creepage_check.py:183 in _is_high_voltage_net -- ...
$ echo $?
3
```

All three named files are among the 7 violations reported; **REAL EXIT
CODE: 3**. Restoring the fixed tree (`git checkout HEAD -- <the three
paths>`) and re-running:

```
$ uv run --no-sync python scripts/check_net_classification.py
...
Net-classification-by-substring gate passed
$ echo $?
0
```

**The falsifier did not fire.** The gate fails on all three historical
pre-fix instances and passes on the fixed tree. `git status --short` was
confirmed empty (working tree restored) before continuing.

## Should these checks classify nets from `elec/domain_manifest.yaml`
## alone, rather than keeping any keyword heuristic?

**Recommendation: not for the final safety-verification gates
(`clearance_check.py`/`creepage_check.py`), but a stronger case exists for
some of the routing-decision call sites -- and the trade-off differs by
which of the two roles the code plays.**

**Two different roles exist in this codebase, and they should not be
forced onto one answer:**

1. **Final safety verification** (`clearance_check.py`, `creepage_check.py`,
   and now `constraints_design_rules.ClearanceMatrix` via the live DRC
   oracle): the code that decides whether a design PASSES or FAILS a
   safety standard. This is exactly where `clearance_check._classify_net_class`
   already ORs manifest membership in ahead of the keyword fallback
   (`if net_name in hv_manifest_nets: return "HV"`, checked *first*).
2. **Routing/placement decisions** (trace width, via template, priority
   order, zone-clearance-override lookup): heuristics that pick a
   *reasonable* value for something the final verification stage will
   independently check anyway.

**For role 1, making the manifest authoritative (dropping the keyword
fallback entirely) trades a false-positive/false-negative risk for a
different failure mode: silent non-coverage.** `elec/domain_manifest.yaml`
declares 48 nets total (14 HV + the rest SELV, per this board's current
`check_domain_partition` run). This project's compiled netlist has more
records than that (164 compiled nets in the same run, many with zero
connected pins or non-HV-relevant). A net absent from the manifest is not
necessarily SELV -- it could be a **new HV-domain net the manifest hasn't
been updated for yet** (the exact failure mode `clearance_check.py`'s
false-negative bug already demonstrated: eleven real HV nets were once
silently under-classified). If the manifest is made the *sole* authority
with no keyword fallback, that failure mode becomes:  a HV-domain net not
yet added to the manifest gets the SELV/default clearance with **zero
heuristic backstop** -- worse than today's OR'd combination, not better.
The manifest is human-maintained and reviewed, but so was the keyword list
before each of the three historical bugs; being human-maintained doesn't
make an SSOT self-updating.

**The keyword fallback, properly anchored (this change), is a legitimate
second opinion for role 1** -- not a competing source of truth, a
defense-in-depth net beneath it. `elec/domain_manifest.yaml` should stay
authoritative (checked first, as it already is in `_classify_net_class`)
and the anchored keyword match should stay as the thing that fires when
the manifest hasn't caught up yet -- exactly the shape merge `466c7724`
already converged on for `_get_required_clearance`. Removing the
keyword path entirely would require a process guarantee (a CI gate
requiring every new net to be added to the manifest before merge) that
does not exist today; `check_domain_partition.py` verifies the manifest is
*internally consistent* with the compiled netlist's declared domains, but
nothing currently blocks a brand-new net from being compiled without a
manifest entry at all (it would show up as one of the "zero connected
pins" or simply an unclassified net, not a hard failure).

**For role 2 (routing/placement heuristics), the case for manifest-only is
stronger** -- these already tolerate imprecision (a wrong trace-width
guess doesn't cause a silent safety gap; the final verification stage
independently re-derives what matters), so trading heuristic coverage for
manifest precision has a smaller downside. This is a real design decision
this task does not make: some of these call sites (e.g.
`_constraint_types/config.py.get_net_class`, feeding
`SignalToHVClearance`/the phase-rotation HV check) sit close enough to
role 1 that manifest-first with a narrower anchored fallback (as done
here) may already be the right compromise; others
(`_astar_ordering.cluster_sort_key`, a pure routing-order tiebreaker) have
no safety consequence at all and are not worth the coupling cost of a
manifest dependency.

**What happens to nets absent from the manifest, concretely, under each
design:**

| Design | Net absent from manifest, keyword collides | Net absent from manifest, keyword doesn't collide |
|---|---|---|
| Keyword-only (pre-this-change) | False positive/negative (proven 3x) | Correctly falls to default |
| Manifest-OR-anchored-keyword (this change, role 1) | Anchored keyword still tries to classify it -- correct if it's a genuinely HV-shaped name, silent default if not | Silent default (same residual risk as manifest-only, bounded by the keyword net) |
| Manifest-only (not implemented) | N/A -- manifest doesn't classify what it doesn't declare | Silent default, with zero heuristic backstop |

## UNVERIFIED

- Whether `IEC 60335-1` (or any cited standard) formally distinguishes
  degrees of substring-classification risk by keyword length -- the
  `SAFETY_VOCAB` scoping in the gate is an engineering judgment call
  (terms proven or plausible as accidental-substring risks in this
  specific codebase), not derived from a standard.
- Whether every one of the 65 `UNRESOLVED` call sites the gate reports on
  the current tree is genuinely non-safety-relevant -- each was
  spot-checked by category (constraint compiler slot scoring, DAG
  topological sort, pathfinding, thermal/loop-inductance estimation) but
  not individually read line-by-line the way the 21 vocabulary-matching
  candidates were. None matched the HV/SELV vocabulary, which is the
  gate's actual signal; "unresolved and not vocab-matching" is a much
  weaker claim than "confirmed non-safety."
- `scripts/manifest.yaml`'s `_meta.total_scripts`/`counts.keep` were
  updated based on a single re-read at the time of this change (69->70,
  68->69); a concurrent sibling task changing the same file could produce
  a merge conflict or stale count by the time this branch is reviewed.
- `check_manifest_gate.py` currently fails on an unrelated,
  pre-existing gap: `check_copper_net_consistency.py` (introduced in
  commit `af91e10a`, predating this branch's base) has no
  `scripts/manifest.yaml` entry. Confirmed not introduced by this change
  and out of this task's explicit scope (not one of the eight named
  gates); not fixed here.
