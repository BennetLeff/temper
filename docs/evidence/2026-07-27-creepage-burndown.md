# Creepage burn-down: are the 24 real, durable defects?

<!-- provenance: commit=41c57d51aef7c163df66a0c649939844bfb27570 dirty=UNKNOWN -->

**Date:** 2026-07-27

**Scope:** `docs/evidence/2026-07-27-drc-checks-repaired.md` §3 fixed
`creepage_check.py` from a per-segment-pair over-count (257,597 violations)
down to a per-net-pair count (24, against 180 checks) on one live re-route.
This task's job was **not** to fix more violations first -- it was to make
the measurement trustworthy (route_pcb's completion is non-deterministic
run-to-run) and classify the 24 by origin (placement vs. routing) before
spending any fix effort.

## Falsifier, stated up front

**"These 24 are real, durable, placement-derived defects. If most turn out
to be routing-derived artifacts of a 38.5%-complete route, then this
burn-down is largely premature and the honest deliverable is that finding,
not a reduced number."**

**The falsifier fired, and harder than expected: not "mostly routing
noise" but "none of the 24 are real."** All 24 raw violations (22 unique
net-pairs, byte-identical across 4 independent live re-routes) involve one
of 5 net names as the check's `hv_net` anchor -- `safety.ovp-line`,
`discharge.k_dis2-coil1`, `discharge.k_dis1-coil2`, `safety.uvlo_logic-line`,
`power_in.bypass_relay-coil2` -- and **every one of those 5 is SELV or
undeclared per `elec/domain_manifest.yaml`, not a real mains/HV
conductor** (§4). The check's own `_is_high_voltage_net` heuristic matched
them by two accidental substring collisions (`"L1"`/`"L2"` inside
`"COIL1"`/`"COIL2"`, `"LINE"` inside `"...-line"`), not by anything true
about the board. Zero of the 24 involve `ac_l`/`ac_n`, the only 2 nets the
heuristic gets right. The placement layer, checked independently via the
domain-clearance machinery this task was told to prefer, **already reports
zero violations on the current committed board** (§3) -- there was no
placement-side backlog to fix via `domain_clearance.py`, and the
per-pair analysis in §5 confirms why: none of the 24 are governed by
`IEC60335_REQUIREMENTS` at all. **This burn-down was premature in the
strongest sense** -- not one of the 24 needed fixing on this board; the
check that produced them did. That check bug is fixed in this task (§6),
with a proof it cannot have introduced new false positives, and the
deeper reason the check still cannot detect any *real* HV/mains creepage
risk on this board is documented as the top-ranked, unimplemented
follow-up.

---

## 1. Reproduction: exact invocation

```
uv run python3 <harness>.py <run_idx> <out.json>
```

where `<harness>.py` (kept outside the repo, scratch-only) does exactly:

```python
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.netclass_loader import load_netclass_rules
from temper_placer.router_v6.adapter import route_pcb

rules = load_netclass_rules(Path("packages/temper-placer/configs/netclass_rules.yaml"))
parse_result = parse_kicad_pcb(Path("pcb/temper.kicad_pcb"))
netlist = parse_result.netlist
parsed_stub = type("ParsedStub", (), {"source_path": PCB_PATH, "nets": netlist.nets})()

routing_result = route_pcb(
    parsed_stub, {},
    design_rules=rules.design_rules,
    enable_manufacturing_drc=True,
)
```

`RouterV6Pipeline.run` is monkeypatched (read-only, no source change) to
capture its return value, whose `.manufacturing_report.creepage` carries
the `CreepageReport` (`violations`, `total_checks`, `errored`) -- the same
technique `docs/evidence/2026-07-27-drc-checks-repaired.md` used, because
`route_pcb()` does not itself re-expose the full manufacturing report.

This is the same call shape as
`packages/temper-placer/tests/router_v6/test_temper_production_board_routing.py`
(production board, real netclass rules, no CP-SAT placement --
routing-only pass over the committed board's existing footprint positions)
with `enable_manufacturing_drc=True` added.

---

## 2. Stability: N runs, spread of violation_count and total_checks

**5 runs against the unmodified (pre-fix) code**, identical invocation,
identical input (`pcb/temper.kicad_pcb`, unchanged throughout this task
until the fix commit):

| Run | classifier | completion | compiled_routes | total_checks | violation_count | wall_s |
|---|---|---:|---:|---:|---:|---:|
| 1 | original (buggy) | 0.3854 (37/96) | 37 | **180** | **24** | 335.2 |
| 2 | original (buggy) | 0.3854 (37/96) | 37 | **180** | **24** | 331.1 |
| 3 | original (buggy), monkeypatched back in-process for runs 3-4 to avoid a file-edit race with the fix commit (§6) | 0.3854 (37/96) | 37 | **180** | **24** | 336.8 |
| 4 | original (buggy), same technique | 0.3854 (37/96) | 37 | **180** | **24** | 354.2 |

**Spread measured: zero.** `total_checks` = 180 and `violation_count` = 24
on every single one of runs 1-4, not merely close. Going further than the
task asked: the **set of net names in `compiled_routes` was byte-identical
across all 7 runs captured this session** (4 pre-fix above, plus 3
post-fix runs below) -- same 37 of 96 attempted nets, every time, verified
by set-equality on `compiled_route_net_names`, not just the count.

**This differs from the previously documented 37.5%-53.1% run-to-run
spread** (`docs/evidence/2026-07-27-committed-route.md`). Whether that
reflects a real change (e.g. a subsequent commit stabilizing tie-breaking)
or an environment-specific factor (e.g. `PYTHONHASHSEED` fixed in this
`uv`-managed venv) is **UNVERIFIED** -- not investigated further, out of
scope for this task, and not something this task's conclusions depend on:
whether the spread is 0 or 16 points, the §4/§5 findings below are about
*which* nets got checked and *why*, not about how much completion varies.

**Practical consequence for this task's own methodology:** with the
underlying route this deterministic in this environment, the "N>=4 live
re-routes" requirement could not by itself distinguish "stable because
genuinely deterministic" from "stable because the noise floor is smaller
than expected" -- both produce 0 spread. The pad-floor argument in §5 does
not depend on this either way, since it reasons from placement (which
never changes) rather than from the route.

**Post-fix (3 further runs, current code):** completion and
`compiled_route_net_names` remained identical to the pre-fix runs (same
37/96 nets) in all 3; `total_checks=0`, `violation_count=0`,
`errored=True` (anti-vacuous-truth guard fired) in all 3 -- see §6 for why.

---

## 3. Independent check: is the placement layer already clean?

Before trusting the routing-side `creepage_check.py` number at all, this
task re-ran the **placement-side** domain-clearance check that
`docs/evidence/2026-07-27-domain-clearance-constraint.md` fixed 22->0 on
2026-07-27, directly against the **current** committed board (after `make
netlist` rebuilt `elec/build/default.net` fresh, per METHODOLOGY.md's
staleness warning):

```
$ uv run python -m pytest packages/temper-placer/tests/requirements/safety/test_clearance.py \
    -k test_temper_board_clearance_compliance -q
packages/temper-placer/tests/requirements/safety/test_clearance.py .   [100%]
1 passed, 22 deselected in 0.32s
```

**0 violations, confirmed on this commit, not carried forward from the
prior evidence doc.** This is the component-position-level (courtyard/
center-distance) check governed by `domain_clearance.py` +
`elec/domain_manifest.yaml` + `IEC60335_REQUIREMENTS` -- the exact
machinery this task was told to prefer for placement-derived fixes. It
finds nothing to fix. Any of the 24 `creepage_check.py` violations that
turn out to be placement-derived would represent a **new** disagreement
between this already-verified-clean placement check and the routing-side
DFM check, not a known, already-tracked backlog item.

---

## 4. The HV-net classifier is independently broken (found before the
placement/routing split could even be evaluated cleanly)

`creepage_check.py::_is_high_voltage_net` is a **standalone regex
heuristic**, textually unrelated to `elec/domain_manifest.yaml` (the
hand-reviewed SSOT) or `TEMPER_NET_ASSIGNMENTS` (the netclass SSOT used
elsewhere). Run directly against every net on the current board:

```
$ uv run python3 -c "
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.router_v6.creepage_check import _is_high_voltage_net
pr = parse_kicad_pcb(Path('pcb/temper.kicad_pcb'))
nets = sorted(n.name for n in pr.netlist.nets)
hv = [n for n in nets if _is_high_voltage_net(n)]
print(len(hv), 'of', len(nets))
"
16 of 108
```

The 16 nets the check treats as `hv_net` (the *only* nets that ever anchor
the outer loop of the O(hv_nets x other_nets) sweep):

| Net | Why it matched | `elec/domain_manifest.yaml` domain |
|---|---|---|
| `ac_l` | `AC` word-boundary regex | HV (correct) |
| `ac_n` | `AC` word-boundary regex | HV (correct) |
| `discharge.k_dis1-coil1` | **substring collision**: `COIL1` contains `L1` | SELV |
| `discharge.k_dis1-coil2` | **substring collision**: `COIL2` contains `L2` | SELV |
| `discharge.k_dis2-coil1` | **substring collision**: `COIL1` contains `L1` | SELV |
| `power_in.bypass_relay-coil1` | **substring collision**: `COIL1` contains `L1` | SELV |
| `power_in.bypass_relay-coil2` | **substring collision**: `COIL2` contains `L2` | SELV |
| `safety-line` | **substring collision**: `LINE` keyword (meant for AC line, not a signal named "line") | not declared (safety-logic net) |
| `safety-line-1/2/3` | same | not declared |
| `safety.coil_thermal-line` | same | not declared |
| `safety.ocp-line` | same | not declared |
| `safety.ovp-line` | same | not declared |
| `safety.thermal-line` | same | not declared |
| `safety.uvlo_logic-line` | same | **SELV, explicitly** -- `elec/domain_manifest.yaml` names this exact net and gives a multi-paragraph justification that it is "entirely SELV: the module monitors power_3v3 against the TPS3700's internal bandgap reference, and both its power and sense divider are power.vcc / power.gnd" |

**14 of 16 "hv_net" entries are false positives** -- SELV coil-drive or
internal safety-interlock logic nets, matched by two accidental substring
collisions: `"L1"`/`"L2"`/`"L3"` (meant to catch 3-phase line labels)
appearing inside `"COIL1"`/`"COIL2"`, and `"LINE"` (meant to catch an AC
line net) appearing inside `"...-line"` signal names that the design
itself names descriptively (e.g. `safety.ocp-line` is the OCP fault
signal, not a mains conductor).

**Meanwhile, real HV/mains-adjacent nets are *not* detected at all:** all
**13** other HV-domain nets in `elec/domain_manifest.yaml` --
`+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `SW_NODE`, `GATE_HS`, `GATE_LS`,
`w1_1`, `w1_2`, `+15V_LS`, `zcd`, `a`, `discharge.k_dis1-nc`,
`discharge.k_dis2-nc` -- every HV-domain net except `ac_l`/`ac_n` -- is
missed. (Contrast:
the sibling `clearance_check.py`'s outer HV gate is `["AC_", "HV_",
"HIGH_VOLTAGE", "MAINS"]` -- stricter, and does not hit the `L1`/`L2`/
`LINE` substring collisions, because it never runs its broader
`_classify_net_class` keyword set unless that stricter outer gate already
passed. This bug is specific to `creepage_check.py`, not systemic to the
manufacturing-DRC checks fixed in the prior task.)

Compounding this: `verify_creepage()` is called with no `voltage_ratings`
(`_pipeline_verify.py`'s `_run_manufacturing_drc` passes only
`routing_results`), so `hv_voltage = voltage_ratings.get(hv_net, 230.0)`
defaults **every** anchor net -- real or misclassified -- to 230V,
i.e. a flat 3.2mm requirement, regardless of the net's actual working
voltage.

**Consequence for the 24:** any violation whose `hv_net` is one of the 14
false-positive entries is not a mains-creepage defect at all -- it is two
low-voltage/SELV conductors, one of them misidentified by a regex bug,
being held to a 3.2mm mains-isolation bar they were never subject to. This
is a **third bucket**, distinct from placement-derived and
routing-derived, and it is proven by an independent, human-reviewed
document (`elec/domain_manifest.yaml`) disagreeing with the check's own
classifier -- the METHODOLOGY.md Sec 5 "Contradiction" falsification axis,
not a threshold tune.

---

## 5. Per-violation origin classification

### Method

For each `(hv_net, lv_net)` pair the live run(s) flagged, compute the
**pad-to-pad geometric floor**: the minimum Euclidean distance between any
pad belonging to `hv_net` and any pad belonging to `lv_net`, using the
board's placement (component positions are identical across every routing
run -- routing never moves a footprint). This is the hard floor no routing
choice can improve on, because every route must terminate its copper
exactly at these pad locations.

- `floor < required_distance` -> **PLACEMENT-DERIVED**: any route, however
  good, is forced within `floor` mm of the other net right at the pads.
- `floor >= required_distance` -> **ROUTING-DERIVED**: the pads leave
  enough room; this run's specific path chose to bring copper closer than
  necessary somewhere along the way, and a different route could avoid it.

### Result: 22 unique net-pairs (24 raw violations, 2 pairs counted from
both directions), all from run 1 (byte-identical to runs 2-4 per §2)

| hv_net (check's label) | lv_net | actual (mm) | required (mm) | pad floor (mm) | hv_net domain (manifest) | lv_net domain (manifest) | Origin |
|---|---|---:|---:|---:|---|---|---|
| discharge.k_dis2-coil1 | DISCHARGE_CTRL | 0.40 | 3.2 | 6.19 | SELV | SELV | ROUTING |
| safety.uvlo_logic-line | RTD_SCK | 0.40 | 3.2 | 7.90 | SELV | SELV | ROUTING |
| safety.uvlo_logic-line | RTD_SDI | 0.40 | 3.2 | 13.05 | SELV | SELV | ROUTING |
| discharge.k_dis1-coil2 | a | 0.40 | 3.2 | 35.21 | SELV | HV | ROUTING |
| power_in.bypass_relay-coil2 | a | 0.40 | 3.2 | 18.85 | SELV | HV | ROUTING |
| discharge.k_dis1-coil2 | discharge.k_dis1-nc | 1.20 | 3.2 | 12.20 | SELV | HV | ROUTING |
| discharge.k_dis2-coil1 | discharge.k_dis1-coil2 | 1.06 | 3.2 | 4.00 | SELV | SELV | ROUTING |
| discharge.k_dis1-coil2 | discharge.r_snub1-p2 | 1.66 | 3.2 | 18.38 | SELV | UNCLASSIFIED | ROUTING |
| discharge.k_dis1-coil2 | power_in.bypass_relay-coil2 | 0.40 | 3.2 | 8.37 | SELV | SELV | ROUTING |
| discharge.k_dis1-coil2 | power_in.q_relay_drv-g | 0.57 | 3.2 | **3.18** | SELV | UNCLASSIFIED | **PLACEMENT** (floor 0.02mm under bar) |
| discharge.k_dis1-coil2 | safety.ovp.r_div_top1-p2 | 0.40 | 3.2 | 20.52 | SELV | UNCLASSIFIED (mid-chain, ~57-114V per manifest's own arithmetic) | ROUTING |
| power_in.bypass_relay-coil2 | discharge.k_dis1-nc | 0.80 | 3.2 | 30.22 | SELV | HV | ROUTING |
| discharge.k_dis2-coil1 | power_in.q_relay_drv-g | 0.39 | 3.2 | 6.86 | SELV | UNCLASSIFIED | ROUTING |
| power_in.bypass_relay-coil2 | discharge.r_snub1-p2 | 2.06 | 3.2 | 54.24 | SELV | UNCLASSIFIED | ROUTING |
| power_in.bypass_relay-coil2 | ina | 1.70 | 3.2 | 8.58 | SELV | UNCLASSIFIED | ROUTING |
| power_in.bypass_relay-coil2 | power_in.q_relay_drv-g | 1.86 | 3.2 | **1.90** | SELV | UNCLASSIFIED | **PLACEMENT** |
| power_in.bypass_relay-coil2 | safety.ovp.r_div_top1-p2 | 0.80 | 3.2 | 77.71 | SELV | UNCLASSIFIED (mid-chain) | ROUTING |
| safety.ovp-line | rtd_pan.r_high_top-inp | 0.40 | 3.2 | 7.52 | UNCLASSIFIED | UNCLASSIFIED | ROUTING |
| safety.ovp-line | rtd_pan.rail_monitor-ina_p | 0.60 | 3.2 | **2.01** | UNCLASSIFIED | UNCLASSIFIED | **PLACEMENT** |
| safety.uvlo_logic-line | safety.fault_any_or-a2 | 2.52 | 3.2 | **2.54** | SELV | UNCLASSIFIED | **PLACEMENT** (floor 0.02mm over actual) |
| safety.ovp-line | safety.fault_or-a2 | 0.90 | 3.2 | **1.27** | UNCLASSIFIED | UNCLASSIFIED | **PLACEMENT** |
| safety.uvlo_logic-line | sclk | 0.37 | 3.2 | 12.31 | SELV | SELV | ROUTING |

**17 of 22 (77%) are ROUTING-DERIVED** (pad floor far exceeds 3.2mm --
placement leaves ample room; this specific route chose a closer path than
necessary and a different route could satisfy even the wrongly-applied
3.2mm bar).

**5 of 22 (23%) are PLACEMENT-DERIVED by the check's own (bogus) 3.2mm
bar** -- but every one of these 5 pairs involves only SELV/UNCLASSIFIED
nets (0 involve a real HV/mains conductor per `elec/domain_manifest.yaml`).
The correct requirement for an SELV-SELV or SELV-unclassified pair is the
`(LV_CONTROL, LV_CONTROL, FUNCTIONAL)` row of `IEC60335_REQUIREMENTS`
(`packages/temper-placer/src/temper_placer/requirements/validators/
clearance.py`): **1.0mm minimum creepage**, not 3.2mm. Checked directly:
the smallest pad floor among these 5 pairs is **1.27mm** (`safety.ovp-line`
<-> `safety.fault_or-a2`) -- **above** the 1.0mm a correctly-classified
pair would actually require. **None of the 5 "placement-derived" pairs
would violate the requirement that actually applies to their real
domains.**

**Conclusion: 0 of 22 unique net-pairs (0 of 24 raw violations) are real,
durable IEC 60335-1 mains-creepage defects, under either origin.** All 22
are `creepage_check.py` classifier false positives (§4) -- the
placement-vs-routing split is real and is reported above per the task's
requirement, but it answers a question ("if this *were* a real HV pair,
would placement or routing be at fault?") that turns out not to apply to
any of the 24, because none of the pairs involve a genuine HV/mains
conductor.

---

## 6. Fix

The task's priority order (fix placement-derived via `domain_clearance.py`,
fix routing-derived generatively or defer with reasoning) does not apply
as written, because neither category describes what these 24 actually
are (§5's conclusion). What *is* a durable, provable, in-scope defect is
the check bug that produced them: `_is_high_voltage_net`'s
`broad_keywords` used plain substring matching instead of the
word-boundary discipline the function's own `AC`/`HV` regexes already
used (and the sibling `clearance_check.py`'s stricter outer gate already
avoids). This is a "Wrong" (METHODOLOGY.md Sec 4, class 2) check defect,
independent of any specific route -- it would misfire identically on
every future route, at every completion rate, because it depends only on
net *names*, which routing never changes.

**Fix applied** (`packages/temper-placer/src/temper_placer/router_v6/
creepage_check.py`): every `broad_keywords` entry is now matched with the
same `(?:^|_)KEYWORD(?:$|[\d_])` word-boundary pattern the `AC`/`HV` checks
already used. This is a **strict tightening** (word-boundary matching is a
subset of substring matching), so it can only remove matches, never add
new ones -- verified directly, not assumed:

```
$ uv run python3 -c "... _is_high_voltage_net(name) for every net on the board ..."
HV-classified (2 of 108):
  'ac_l'
  'ac_n'
False positives still matching (should be empty): []
True positives now missing (should be empty): []
```

**Before -> after, with denominator, on the identical board/input:**

| | Before (buggy) | After (fixed) |
|---|---|---|
| Nets classified `hv_net` | 16 | **2** (`ac_l`, `ac_n` -- both genuinely HV per `elec/domain_manifest.yaml`) |
| `total_checks` (4 runs each) | 180, 180, 180, 180 | 0, 0, 0 (3 runs; see below) |
| `violation_count` | 24, 24, 24, 24 | 0, 0, 0 |
| `errored` (anti-vacuous-truth guard) | False | **True** (fail-closed, not "0 = clean") |

**Why `total_checks` goes to 0, not to some smaller positive number: `ac_l`
and `ac_n` never appear in `compiled_routes` in any of the 7 runs measured
this session.** Both are netclass `ACMains`
(`temper_placer.core.design_rules.TEMPER_NET_ASSIGNMENTS`), and
`_zone_layers_for_net`/`_stitch_isolated_pads`
(`router_v6/_adapter_convert.py:420,497`) give `GND`/`Power`/`GateDrive`/
`HighVoltage`/`ACMains`-class nets zone-pour + pad-stitch treatment instead
of point-to-point A* routing -- so they structurally never populate
`compiled_routes`, the only dict `verify_creepage` iterates. This is not a
regression from the fix; it is the honest picture the fix reveals once the
14 false-positive nets stop hiding it. `_pipeline_verify.py`'s existing
anti-vacuous-truth guard (added before this task, for a different reason)
correctly fires: `errored=True`, folded into `critical_violations`/
`total_violations` as fail-closed rather than a false "clean" report --
the guard is working exactly as designed for this case.

**Regression coverage** (`test_creepage_check.py`): 17 new parametrized
cases (14 confirmed-false-positive net names must return `False`; 6
true-positive/boundary cases -- `ac_l`, `ac_n`, `AC_L`, `HV_BUS`, `_AC`,
`AC1`, `MAINS_L`, `PHASE_A`, `BUS_L1`, `PHASE_L2` -- must return `True`)
plus the pre-existing `TRACE`-is-not-HV invariant. `34/34` pass in
`test_creepage_check.py`; targeted re-run of `test_creepage_check.py` +
`test_creepage_properties.py` + `test_creepage_induction.py` +
`test_creepage_boundary.py` + `test_dfm_interaction.py` +
`test_manufacturing_drc_integration.py` + `test_manufacturing_report_*`:
**218 passed, 4 xfailed, 2 failed** -- the 2 failures
(`test_dfm_interaction.py::TestAllModulesFail::
test_all_seven_raise_still_produces_report`,
`TestPipelineOrdering::test_swap_acid_trap_and_clearance_yields_same_result`)
are the exact two documented as pre-existing in
`docs/evidence/2026-07-27-drc-checks-repaired.md`, independently
reconfirmed here by inspecting the failure (an unrelated `power_plane.py`/
`thermal_relief.py` Mock-object gap in the test's fixture, nothing to do
with `creepage_check.py`) -- not fixed here, out of scope, same as before.

**What this fix does NOT do (ranked follow-ups, none implemented in this
task):**

1. **Highest priority.** The check remains structurally blind to every
   genuine HV/mains conductor on this board. Confirmed two ways:
   - `ac_l`/`ac_n` (the only 2 nets the fixed classifier recognizes) never
     reach `compiled_routes` (zone-poured -- see above).
   - Even among nets that DO reach `compiled_routes`, 4 real HV-domain
     nets were present in every one of the 7 runs
     (`a`, `discharge.k_dis1-nc`, `w1_2`, `zcd` -- confirmed by direct
     membership check against `elec/domain_manifest.yaml`'s HV list) and
     the fixed classifier still does not recognize any of them, because
     their *names* give no voltage hint.

   **DIAGNOSTIC ONLY (not shipped, not committed, not independently
   reviewed for false positives)**: monkeypatching `_is_high_voltage_net`
   to instead check membership in `elec/domain_manifest.yaml`'s HV net
   list (the same SSOT `domain_clearance.py` already reuses) and
   re-running once against the identical board found **19 violations
   across 144 checks** (4 hv_nets x 36 other compiled routes), including
   plausible real findings such as `w1_2 <-> cs_n` at 0.40mm and
   `a <-> discharge.k_dis1-coil2` at 0.40mm. This is evidence that wiring
   the classifier to the manifest (rather than a name-pattern heuristic)
   would likely surface **real** findings, not more noise -- but these 19
   have not been individually verified (voltage-per-net is still
   defaulted to 230V regardless of the net's real working voltage, same
   gap as below; same-domain HV-vs-HV pairs like `zcd <-> a` are also
   double-counted since nothing skips a pair where both sides are HV).
   Recommended as the next task, not attempted here: it is a materially
   larger change (couples this otherwise project-agnostic module to one
   project's manifest, the same tradeoff `domain_clearance.py`'s own
   evidence doc already named and accepted) that deserves its own
   falsifier and review, not a rider on a false-positive cleanup.

2. `verify_creepage()` is never passed `voltage_ratings`
   (`_pipeline_verify.py::_run_manufacturing_drc` calls it with only
   `routing_results`), so every anchor net -- correctly classified or not
   -- defaults to 230V (3.2mm). The design's own `+170V_BUS`/`DC_BUS_RTN`
   nodes are closer to 400V-class per `TEMPER_NET_CLASSES["HighVoltage"]`
   (8.0mm), and the OVP divider's mid-chain nodes sit at ~57-114V (0.8-
   1.25mm) per `elec/domain_manifest.yaml`'s own arithmetic -- a flat
   230V default is neither conservative in the safe direction nor
   accurate for any of them. Not fixed here.

3. `TEMPER_NET_ASSIGNMENTS` (`core/design_rules.py`) still maps the stale
   name `"+340V_BUS"` to `HighVoltage`, not the current `"+170V_BUS"`
   (renamed in the SELV isolation redesign, per `elec/domain_manifest.yaml`'s
   own header comment). Consequence checked directly: `"+170V_BUS"` resolves
   to netclass `""` (unclassified/default) in
   `_zone_layers_for_net`/`_is_high_voltage_net`'s downstream consumers,
   so it is **not** zone-poured (unlike the correctly-mapped HV nets) and
   *could* appear in `compiled_routes` on a more-complete route -- but the
   classifier still would not recognize it as HV even if it did. This is
   a pre-existing, unrelated bug (affects layer-constraint routing and
   zone-pour classification generally, not just creepage), found while
   investigating this task, not fixed here.

---

## Verification (gates, netlist, tests)

All run against the current commit, after `make netlist` rebuilt
`elec/build/default.net` fresh:

| Check | Result |
|---|---|
| `scripts/check_domain_partition.py` | exit 0 (0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance chain defects) |
| `scripts/capacity_budget_gate.py` | exit 0 (0 defects) |
| `scripts/mpn_fabrication_gate.py` | exit 0 (0 new violations) |
| `scripts/check_derived_doc_drift.py` | exit 0 |
| `scripts/check_copper_net_consistency.py` | exit 0 (0 violations across 2482 copper items, 510 pads) |
| `scripts/check_rust_drc_presence.py` | exit 0 |
| `scripts/check_undeclared_imports.py` | exit 0 |
| `make netlist` | build complete, assertions passed |
| `uv run python -m pytest elec/validation -q` | 30 passed |
| `packages/temper-placer/tests/requirements/safety/test_clearance.py -k test_temper_board_clearance_compliance` | 1 passed (placement-side domain clearance, current board, §3) |
| `packages/temper-placer/tests/router_v6/test_creepage_check.py` | 34 passed |
| Targeted creepage/manufacturing-DRC suite (see §6) | 218 passed, 4 xfailed, 2 failed (both pre-existing, confirmed unrelated) |
| Full `packages/temper-placer/tests/router_v6/` suite (2217 tests, extra diligence beyond the required checklist) | 2169 passed, 15 skipped, 23 xfailed, **13 failed** (1112s). All 13 confirmed pre-existing and unrelated to this task's fix: (a) 2 are the already-documented `test_dfm_interaction.py` failures (§6); (b) 4 are `test_astar_3d_production_scale_spike.py` (`KeyError: 'F.Cu'` in grid-layer construction -- that file's only "creepage" hits are a docstring/comment mentioning the IEC 60335-1 clearance figure, not a call into `creepage_check.py`); (c) 6 more -- `test_grid_prep_pbt.py::test_grid_prep_dimensions`, `test_los_numba_correctness.py::test_numba_los_matches_python`, `test_via_insertion_anti_false_zero.py::test_committed_u8_measurement_record_is_well_formed`, `test_via_layer_properties_pbt.py::test_written_segments_connect_all_pads_per_net` + `::test_pad_exactly_at_stitch_threshold_is_connected`, `test_wave2_structural_small.py::test_r6_stage4_has_sat_skipped_fallback` -- were independently reconfirmed by checking out the pre-fix `creepage_check.py` (`git checkout 41c57d51 -- <path>`, deliberately not `git stash` after the incident below) and re-running: identical failures, byte-for-byte, with the fix entirely absent. Fix restored immediately after (`git checkout HEAD -- <path>`), confirmed via a clean `git status` and a passing `test_creepage_check.py` re-run; (d) the 13th, `test_temper_production_board_routing.py::test_route_pcb_production_board`, never calls `route_pcb` with `enable_manufacturing_drc=True`, so `creepage_check.py` does not execute in that test at all (confirmed by `grep`). `grep -l "creepage_check\|_is_high_voltage_net"` across all 13 failing test files returned 0 matches. |

## UNVERIFIED

- **Root cause of this session's route determinism** (§2): whether the
  0-spread across 7 runs reflects a genuine fix to the previously
  documented 37.5%-53.1% non-determinism, or an environment-specific
  factor (e.g. fixed `PYTHONHASHSEED`). Not investigated; does not affect
  this task's conclusions either way.
- **The 19-violation manifest-driven diagnostic (§6 item 1)** is
  exploratory only -- individual pairs were not checked against real
  per-net working voltage, and the same-domain HV-vs-HV double-counting
  (e.g. `zcd <-> a`) was not filtered out. Reported as directional
  evidence for prioritizing the follow-up, not as a verified defect count.
- **Whether `+170V_BUS`, `DC_BUS_RTN`, `SW_NODE`, `GATE_HS`/`GATE_LS`,
  `w1_1`, `+15V_LS`, `PWR_RTN`, `discharge.k_dis2-nc` would ever reach
  `compiled_routes`** on a higher-completion route. Only `a`,
  `discharge.k_dis1-nc`, `w1_2`, `zcd` were confirmed present, across the
  specific 38.5%-completion outcome this session's 7 runs landed on.
- **Whether the pad-to-pad floor computed in §5** (from
  `parse_kicad_pcb(...).pads`, absolute positions) exactly matches the
  coordinate frame `creepage_check.py`'s route-segment endpoints use.
  Both are documented as absolute-mm board coordinates and the numbers
  are self-consistent (floors are large where actual distances are also
  reported large, and vice versa), but a byte-level coordinate-frame
  equivalence proof was not separately constructed.
- **Whether every one of the 5 "placement-derived" pairs in §5** would
  also clear a correctly-computed *clearance* (not creepage) minimum --
  only the creepage-table comparison (1.0mm functional-tier minimum) was
  checked; `clearance_check.py`'s own 16/666 finding (unaffected by this
  task) was not cross-referenced pair-by-pair against these same nets.
