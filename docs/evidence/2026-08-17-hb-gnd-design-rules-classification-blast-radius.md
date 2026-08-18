<!-- provenance: commit=8157b4344881ccd607ebaad5ba73c80ea85e97a8 dirty=true
     (worktree carries this doc's own companion code/test changes on top of
     this commit; see "Files changed" at the end)
     board sha256 (verified unchanged before, during, and after this
     investigation -- read-only against pcb/temper.kicad_pcb throughout,
     never opened for writing):
     6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1 -->

# `hb-gnd` classification divergence: `elec/domain_manifest.yaml`/`clearance_check` (HV) vs `TEMPER_NET_ASSIGNMENTS` (unclassified) vs `pcb/temper.kicad_pro` (unassigned)

## Verdict, up front

**`hb-gnd` is genuinely HV** (confirmed independently from `elec/src/*.ato`
topology, not merely trusted from the manifest's own trace). Of its **four**
classification homes, two already agreed (`elec/domain_manifest.yaml`,
`router_v6.clearance_check._classify_net_class`); a third
(`core.design_rules.TEMPER_NET_ASSIGNMENTS`) had **no entry at all** and is
**fixed by this change**; the fourth (`pcb/temper.kicad_pro`'s real
`netclass_assignments` — the file `kicad-cli`'s DRC actually reads) is
**still missing and deliberately left that way**, because syncing it
surfaces 28 previously-invisible real DRC violations that need routing
remediation (moving copper), which is out of scope for a classification fix.
`scripts/check_hv_netclass_coverage.py` already catches both gaps, live, as
a currently-red, CI-blocking gate — this was not a silent/dark defect.

## 1. `hb-gnd`'s electrical potential, derived from the schematic source

`elec/domain_manifest.yaml` (PR #1145) traces `hb-gnd` to the compiled net
atopile assigns to `hb.dc_bus.hv_minus` and claims it sits "at the same
~-170V potential relative to signal ground" as the already-declared HV net
`DC_BUS_RTN`. Per the task's explicit instruction not to trust the
manifest's own trace uncritically, this was re-derived independently from
`elec/src/*.ato`:

- `elec/src/modules.ato:376-379` (the `HalfBridge` module's power-stage
  wiring): `dc_bus.hv_plus ~ power_loop.q_high.C`; `power_loop.q_high.E ~
  switch_node`; `switch_node ~ power_loop.q_low.C`; `power_loop.q_low.E ~
  dc_bus.hv_minus`. This is the half-bridge's DC-bus-referenced power stage:
  `hv_minus` is literally the low-side switch's (`q_low`) **Emitter/return
  node** — the fixed rail the bridge leg bottoms out on when the low side is
  conducting, not the switching node itself (`switch_node` is what floats at
  44-50kHz; `hv_minus` is the DC rail it switches against).
- `elec/src/modules.ato:424,436`: `dc_bus.hv_minus ~ gate_hs.driver.VSSB`
  and `power_15v_ls.gnd ~ dc_bus.hv_minus # Referenced to hv_minus, NOT
  logic gnd` — the low-side gate driver's own secondary-side reference is
  explicitly, commentedly *not* logic ground.
- `elec/src/main.ato:794-795`: `hb.dc_bus.hv_minus ~ safety.ocp2_bus_in`;
  `safety.ocp2_bus_out ~ dc_bus_minus` — `hb.dc_bus.hv_minus` (the net
  compiled as `hb-gnd`) connects to the board-level `dc_bus_minus` net
  (`override_net_name = "DC_BUS_RTN"`, line 522) through OCP-02's current
  transformer primary — a two-terminal, non-isolating splice (a few
  milliohms), not a galvanic isolation boundary.
- `elec/src/main.ato:759-771` (comment on this exact connection, written
  independently of the manifest, dated 2026-08-07): *"this is a
  voltage-doubler topology: `power_return` IS the doubler midpoint and IS
  signal ground, so `DC_BUS_RTN` sits at roughly -170V with respect to it"*.
  `power_return` (`override_net_name = "PWR_RTN"`, line 528) is the AC-input
  voltage doubler's midpoint, and the schematic's own prose calls it "signal
  ground" for exactly this comparison.
- `elec/src/main.ato:504-507,753`: the *other* candidate "ground" on this
  board, `gnd` (SELV control-domain ground), is explicitly bonded to
  protective earth (`gnd ~ pe`) and DC-isolated from `power_return`/PWR_RTN
  (only Y-cap AC/EMI coupling remains). Whichever of `gnd` or `power_return`
  is meant by "signal ground," `hb-gnd`/`DC_BUS_RTN` sits ~170V away from it,
  with no isolation boundary in between — it does not float relative to
  either.

**Conclusion: `hb-gnd` is a DC (non-switching) rail at ~-170V relative to
the board's signal-ground reference, one non-isolating splice from the
already-declared HV net `DC_BUS_RTN`.** The manifest's trace is correct, not
merely asserted — this was independently re-derived from the `.ato` source
before reading the manifest's own justification a second time.

## 2. What each of the four homes is actually consumed by

Traced by call site and CI wiring, per the task's rule against trusting a
name.

| # | Home | Current value for `hb-gnd` | Consumed by | Reaches real DRC geometry? |
|---|---|---|---|---|
| 1 | `elec/domain_manifest.yaml` HV domain list | HV | `scripts/check_domain_partition.py`, `check_hv_netclass_coverage.py`, `router_v6.clearance_check._load_manifest_hv_net_names()` | Indirectly (via #2) |
| 2 | `router_v6.clearance_check._classify_net_class` (Python + Rust `router_clearance.rs`) | HV | `verify_clearance()` → `_run_manufacturing_drc()`, Stage 5.7 of `RouterV6Pipeline` — confirmed live in PR #1300's own investigation (§4 of `docs/evidence/2026-08-17-hb-gnd-classification-stale-test.md`) | **Yes** — this is a real, production DFM clearance/creepage check on Router V6's own routed output, backend `"auto"` (Rust when available) |
| 3 | `core.design_rules.TEMPER_NET_ASSIGNMENTS` | *(none, before this change)* → **HighVoltage** | `scripts/sync_kicad_netclass_assignments.py` (propagates into #4, for nets with an **explicit** entry only — cascade-resolved classes are never synced), `netclass_constraints.py` (CP-SAT placer-feasibility, PR #1322 in flight), `router_v6/_zone_pour_stitch.py`, `constraints_design_rules.py`, and others | **Yes, but only for nets with an explicit entry** — see below |
| 4 | `pcb/temper.kicad_pro`'s `net_settings.netclass_assignments` | *(absent — falls to KiCad's "Default" class)* | **`kicad-cli pcb drc` directly** — this is the file KiCad's own DRC engine reads to resolve every net's class, which combines with `pcb/temper.kicad_dru`'s class-pair rules to produce the enforced clearance/creepage figures | **Yes — this is the fab-authoritative path** |

**Key finding, not stated anywhere before this investigation: `TEMPER_NET_ASSIGNMENTS` is NOT a "placer-feasibility model only" table — unlike `netclass_rules.yaml`'s `class_pairs` (which the task correctly warns is self-documented as placer-feasibility-only), `TEMPER_NET_ASSIGNMENTS` is the DECLARED SSOT that `scripts/sync_kicad_netclass_assignments.py` propagates into `pcb/temper.kicad_pro`, which `kicad-cli`'s DRC reads directly.** This makes `TEMPER_NET_ASSIGNMENTS` genuinely safety-relevant, not merely a CP-SAT solver hint — confirmed by reading the sync script's own docstring and `scripts/check_hv_netclass_coverage.py` PROPERTY 3, which exists specifically to catch nets present in `TEMPER_NET_ASSIGNMENTS` but absent from `kicad_pro` (the exact shape this investigation found for `hb-gnd`, previously documented for `PWR_RTN`).

However, the propagation only fires for nets with an **explicit key** in `TEMPER_NET_ASSIGNMENTS`. `sync_kicad_netclass_assignments.py`'s `compute_target_assignments()` iterates `TEMPER_NET_ASSIGNMENTS.items()` directly — it never runs the pattern-cascade (`is_ground_net`/`is_power_net`/keyword tiers) that `DesignRules.get_rules_for_net()` falls through to for an unlisted net. **This is why `hb-gnd` was never synced to `kicad_pro` even though the live cascade already resolved it to `"GND"`** (confirmed: `design_rules.get_rules_for_net("hb-gnd")` → `"GND"` on current main, via the Rust `is_ground_net("hb-gnd")` → `True`, live since PR #1174's 2026-08-13 hyphen-boundary fix widened the ground-pattern boundary to include `-`; PR #1145's own manifest comment, written ~10 seconds before #1174 merged, is stale on this specific point — it says `is_ground_net("hb-gnd") -> False` and predicts a `"Default"` cascade result, which was true for the ten seconds before #1174 landed and has not been true since). The cascade result (`"GND"`) was *also* wrong (LV instead of HV) but structurally invisible to the sync mechanism either way, because only explicit keys propagate.

**The real, fab-authoritative classification `kicad-cli`'s DRC enforces for `hb-gnd`, before this change, was neither "HV" nor "GND" — it was KiCad's `"Default"` class (0.2mm clearance, no creepage protection), the weakest tier on the board.** Confirmed directly: `json.load(open("pcb/temper.kicad_pro"))["net_settings"]["netclass_assignments"]` has no `"hb-gnd"` key (99 entries, none for this net).

## 3. Which table is authoritative, and why

They are not equivalent, contrary to how the task's framing table describes them ("classification" as a single axis): **`elec/domain_manifest.yaml` is authoritative for domain membership** (a human-reviewed netlist trace); **`router_v6.clearance_check._classify_net_class` is authoritative for Router V6's own Stage-5.7 DFM check** (correctly manifest-first, already right); **`TEMPER_NET_ASSIGNMENTS` is authoritative for everything downstream of `create_temper_design_rules()`**, including — via the sync script — **`pcb/temper.kicad_pro`, which is authoritative for what `kicad-cli`'s DRC actually enforces on the committed board.** For `hb-gnd`, home #3 was simply absent (a gap, not a disagreement), and that gap silently broke the chain into home #4. The manifest is correct; `TEMPER_NET_ASSIGNMENTS` needed the missing entry to catch up, and this is precisely what `scripts/check_hv_netclass_coverage.py` (already CI-wired, PROPERTY 1 and PROPERTY 3) already exists to catch — confirmed by running it live against the unmodified repo before making any change:

```
=== PROPERTY 1: UNCLASSIFIED HV NETS: 8 ===
  VIOLATION net 'hb-gnd' is declared under elec/domain_manifest.yaml's HV domain
  but has NO entry in TEMPER_NET_ASSIGNMENTS ...
  (+ discharge.k_dis1-no, discharge.k_dis2-no, discharge.r_dis1a-p2,
     discharge.r_dis2a-p2, discharge.r_snub1-p2, discharge.r_snub2-p2, input
     -- all PRE-EXISTING, unrelated to hb-gnd, NOT touched by this change)

=== PROPERTY 3 (BLOCKING): unassigned in kicad_pro: 8 ===
  VIOLATION net 'hb-gnd' ... falls to Default (0.2mm) ...
  (same other 7 nets)

FAILED -- 8 unclassified HV net(s) (PROPERTY 1), ... 8 HV-domain net(s)
unassigned in kicad_pro (PROPERTY 3) ...
```

This gate was **already red on main, already CI-blocking, before this investigation started** — `hb-gnd` was one of 8 flagged nets. This was not a dark/silent defect; it was a known, mechanically-detected, unresolved finding.

## 4. Blast radius — measured, not estimated

### The `TEMPER_NET_ASSIGNMENTS` fix in isolation (applied)

Adding `"hb-gnd": "HighVoltage"` (matching `DC_BUS_RTN`'s existing entry,
the same physical node one CT-winding away) closes PROPERTY 1's `hb-gnd`
violation. PROPERTY 3 remains open (see below) — deliberately.

### The `pcb/temper.kicad_pro` propagation, measured on a scratch copy (NOT applied)

Per the task's methodology (full project context — `.kicad_pro`/`.kicad_dru`
sidecars beside a **scratch copy** of the real, unmodified `pcb/temper.
kicad_pcb`; `kicad-cli 10.0.5`; `--severity-all --all-track-errors`; with
and without `--refill-zones`; 5 runs' worth of category cross-checks). The
real board sha256 was verified unchanged before and after every run (only
scratch copies under `/tmp` were ever written).

Isolated diff: exactly one line added to a scratch `pcb/temper.kicad_pro`
copy (`"hb-gnd": "HighVoltage"`), nothing else — verified via `diff` against
the unmodified file. `pcb/temper.kicad_dru` was regenerated and is
byte-identical before/after (class-pair rules depend on class *names*, not
net *assignments* — confirmed).

| | no `--refill-zones` | `--refill-zones` |
|---|---|---|
| **Before** (real, matches task's stated baseline) | **1086** | 1024 |
| **After** (hb-gnd synced, isolated) | **1111** (+25) | 1050 (+26) |
| clearance | 224 → 238 (+14) | 225 → 239 (+14) |
| creepage | 100 → 111 (+11) | 120 → 132 (+12) |
| every other category | unchanged | unchanged |

100% of the delta is in `clearance`/`creepage` — exactly the categories a
netclass reassignment can touch, and nothing else moved (confirms the
isolated-diff methodology is sound).

Per-violation reconciliation (no-refill; hb-gnd-involved violations 11 → 36):

- **8 REMOVED** (false positives, cleared): `hb-gnd` was being misread as
  the **LV side** of a cross-domain pair against its own HV domain-mates —
  `+170V_BUS` (9.96mm), `DC_BUS_RTN` (5.19mm), `PWR_RTN` (8.86mm),
  `SW_NODE` (3.95mm), `w1_1` (10.73mm), `+15V_LS` (0.65mm), and the
  gate-driver isolated rails `hb.gate_hs.driver-p1-1`/`-p2` (0.91mm,
  5.75mm) — all now correctly recognized as same-HV-domain (2.0mm DRU
  figure, not the 12.6mm cross-domain figure) once `hb-gnd` classifies HV.
- **28 NEW** (genuine, previously invisible): `hb-gnd`'s routed copper sits
  physically close (0.65mm–12.53mm actual, against a 2.0mm clearance /
  12.6mm PD3 creepage requirement) to **18 distinct LV/SELV nets**:
  `WDT_KICK` (8 separate violations), `input`, `+3V3`, `I_SENSE`,
  `OCP2_VREF_2V5`, `RTD_HW_FAULT`, `RTD_SDI`, `SHUTDOWN`,
  `discharge.r_dis2a-p2`, `gnd`, `hb.gate_hs.driver-p1`, `i2c_sda_ui`,
  `ina`, `inb`, `nc_7`, `safety.coil_thermal.comp-inp`,
  `safety.fault_any_or-a2`, `safety.ovp.r_adc_top1-p2`,
  `thermal.j_fan-p1`. These are **real, physical exposure that was always
  present and simply invisible to DRC** because `hb-gnd` had no HV
  protection at all before this fix (KiCad's `"Default"` 0.2mm class, not
  even a generic LV class's 0.3mm) — not new false positives introduced by
  the classification.

### Is this inside handoff §9.6's PWR_RTN/CGND reservation? No.

§9.6 (`scripts/check_hv_netclass_coverage.py`'s own docstring) reserves
`PWR_RTN`/`CGND` specifically because of "an order-of-magnitude larger
blast radius" — `PWR_RTN` is the doubler-midpoint high-current return net
with far more copper (a dedicated zone pour) than any net that gate's
sibling sync script otherwise touches. `hb-gnd` is a 6-pad net (`R23`,
`U6.9`, `C23.2`, `C24.2`, `U5.3`, and the OCP-02 CT primary) with no zone
pour of its own. The measured propagation impact — 25 net new DRC
violations (~2.3% of the board's 1086-violation baseline), localized to
copper physically adjacent to `hb-gnd`'s own small footprint — is
real but **not** order-of-magnitude comparable to `PWR_RTN`'s reservation.
`hb-gnd` is not `PWR_RTN` or `CGND`, and `sync_kicad_netclass_assignments.
py`'s own `PROTECTED_NETS` (which structurally guards exactly those two
names) is untouched by this change — confirmed both nets are absent from
this diff and the protection logic still fires unmodified for them (see
§6 below, an unrelated pre-existing finding this investigation surfaced).

**Verdict: `hb-gnd` does NOT fall inside the PWR_RTN/CGND reservation.**
The `TEMPER_NET_ASSIGNMENTS` classification fix is applied. The `kicad_pro`
propagation (PROPERTY 3) is a separate, smaller-but-still-real decision,
reported here with its full measured impact, **not applied** — because
resolving the 28 newly-surfaced violations requires moving copper
(routing/placement remediation), which this task's hard rules forbid an
agent from doing unilaterally, and applying the sync without a remediation
plan would leave production DRC redder with no path to green. That is
exactly the shape the task's step 4 describes as an owner decision.

## 5. What was changed

**`packages/temper-placer/src/temper_placer/core/design_rules.py`** —
added `"hb-gnd": "HighVoltage"` to `TEMPER_NET_ASSIGNMENTS`, with a comment
recording the schematic derivation, the measured blast radius, and the
oracle consequence (below). No clearance, creepage, copper-weight, or DRU
threshold changed. `pcb/temper.kicad_pcb` untouched (sha256 verified
unchanged, see header). `pcb/temper.kicad_pro` untouched (the propagation
step, §4, is deliberately not applied).

**Necessary, honest consequence — 2 pinned-oracle differential tests now
red, left red, not fixed:** `TEMPER_NET_ASSIGNMENTS`'s module-level dict is
differentially compared, bit-for-bit, against a content-hash-pinned
snapshot (`packages/temper-placer/tests/core/_design_rules_py_oracle.py`,
pinned in `scripts/oracle_hashes.json`) by
`test_design_rules_rust_differential.py::test_module_constants_identical`
and `::test_create_temper_design_rules_identical`. Adding the `hb-gnd`
entry makes the live table diverge from that frozen snapshot, so both tests
now fail (`Left contains 1 more item: {'hb-gnd': 'HighVoltage'}`). **This
task's hard rules forbid touching a pinned oracle or re-pinning any hash**,
so the oracle file itself is untouched — `scripts/check_oracle_hashes.py`
still reports **167/167 byte-identical to its pins** (verified before and
after) — only the *differential-parity comparison* is newly red. This
mirrors this repo's own established convention for exactly this tradeoff
(`hv_lv_separation_gate_threshold_mm`'s registry entry, §2026-08-17 session
2: "KNOWN RED, NOT FIXED... requires the standing oracle re-pin ceremony").
Reconciling requires that ceremony (exhaustive-divergence evidence,
deliberately committed) as separate follow-up work, not silently avoided by
leaving the classification wrong.

**One legitimately-fixed, non-oracle test:**
`packages/temper-placer/tests/core/test_design_rules_pbt.py`'s
`_NET_ALPHABET` carried the real net `"hb-gnd"` as a pattern-cascade
example (predicting `"GND"` via the keyword cascade, deliberately, per its
own 2026-08-13 comment). This file's own established precedent (already
applied once, to `"discharge.k_dis1-coil1"`, when that net gained an
explicit assignment) is: when a net in this alphabet gains an explicit
`TEMPER_NET_ASSIGNMENTS` entry, it legitimately disagrees with the
pattern-cascade-only reference and must be replaced with a synthetic name
that still isolates the property under test. Replaced `"hb-gnd"` with
`"TEST-GND"` (a synthetic, never-assigned name exercising the identical
hyphen-boundary ground-pattern property), following that exact precedent —
not touching any pinned oracle, not weakening the test (it still requires
the hyphen-boundary fix to hold). `test_p3_classification_matches_reference`
now passes.

**`scripts/check_fact_registry_drift.py` / `scripts/tests/test_check_fact_registry_drift.py`** — see §6.

## 6. Unrelated, pre-existing findings surfaced along the way (not fixed, flagged)

- `scripts/sync_kicad_netclass_assignments.py --check`/`--write` currently
  refuses to run **at all** (exit 5, tool error) against the real repo,
  independent of this change: its `PROTECTED_NETS` defense-in-depth check
  (`PWR_RTN`/`CGND`) now fires because `pcb/temper.kicad_pro` has since
  gained real `"HighVoltage"` and `"GND"` declared classes — contradicting
  the script's own docstring claim ("`pcb/temper.kicad_pro` has no
  'Ground' (or any other) declared netclass corresponding to it"). Verified
  this is **not** caused by this change (reproduced against the real repo
  before making any edit). `test_sync_kicad_netclass_assignments.py::
  TestRealRepoInvariant::test_pwr_rtn_protected_now_that_gnd_is_declared`
  independently confirms `TEMPER_NET_ASSIGNMENTS["PWR_RTN"]` is already
  `"HighVoltage"` (not the `"GND"` value that test's own name/assertion
  still expects) — a stale test from before an earlier PR (#1083, per
  `design_rules.py`'s own comment) already corrected `PWR_RTN`'s
  classification. Also pre-existing, also not fixed here (out of scope:
  neither file this investigation touches).
- 4 other HV-domain nets besides `hb-gnd` are unclassified in
  `TEMPER_NET_ASSIGNMENTS`/unassigned in `kicad_pro`
  (`discharge.k_dis1-no`, `discharge.k_dis2-no`, `discharge.r_dis1a-p2`,
  `discharge.r_dis2a-p2`, `discharge.r_snub1-p2`, `discharge.r_snub2-p2`,
  `input` — 7 total, all pre-existing, none touched by this change).
- `test_e2e_netclass_ssot.py::test_class_pairs_contain_safety_critical_entries`
  and `test_netclass_feedback.py::test_yaml_loaded_carries_because_text`
  fail on unmodified main (pre-existing, confirmed) — both assert a stale
  `"IEC 60335"` citation string in `netclass_rules.yaml`'s `class_pairs`
  `"because"` field that a 2026-08-15 safety-citation audit already
  rewrote to `"UNSOURCED legacy 6.0mm... placer-feasibility model only"`.
  Same shape as the `hb-gnd` test PR #1300 fixed, different file, not this
  investigation's scope (already flagged in PR #1322's evidence doc).
- `scripts/check_netclass_class_param_correspondence.py`'s real-repo gate
  test fails on unmodified main (pre-existing, confirmed): a
  `HighVoltageSignal.via_diameter` mismatch (1.0 in `design_rules.py` vs
  0.8 in `kicad_pro`), unrelated to net assignments or `hb-gnd`.

None of the above are touched by this change; all were independently
reproduced against the unmodified repo before any edit, to confirm
attribution.

## 7. Registered invariant

`scripts/check_fact_registry_drift.py` (35→37 facts / 76→80 site checks)
gained two facts, split by vocabulary (mirrors why `check_hv_netclass_
coverage.py` keeps PROPERTY 1 and PROPERTY 3 separate — different homes
spell the same verdict differently):

- **`hb_gnd_hv_domain_membership`** (`value_kind="str"`, authoritative
  `"hb-gnd"`) — `elec/domain_manifest.yaml`'s HV domain list entry +
  `test_clearance_check.py`'s corrected PR #1300 assertion. Both patterns
  require the literal `"HV"` verdict to be present in the matched text for
  the regex to match at all — a regression to a weaker class (e.g. the
  pre-#1300 stale `"GND"` assertion) makes the pattern fail to match
  entirely (TOOL ERROR), not silently compare a wrong value. **CLEAN**
  (2/2 homes) — this was already true before this change; now pinned as a
  regression guard.
- **`hb_gnd_temper_net_assignment_class`** (`value_kind="str"`,
  authoritative `"HighVoltage"`) — `design_rules.py`'s
  `TEMPER_NET_ASSIGNMENTS['hb-gnd']` (now **OK**, this change) vs.
  `pcb/temper.kicad_pro`'s `net_settings.netclass_assignments['hb-gnd']`
  (still a **TOOL ERROR** — no entry exists, deliberately not synced, per
  §4). Registers the invariant *and* keeps the still-open propagation gap
  mechanically visible, rather than only registering the part that's fixed.

Non-vacuity proof: `scripts/tests/test_check_fact_registry_drift.py` gained
`test_hb_gnd_hv_domain_membership_is_clean_regression_guard` (asserts both
homes `matches is True`) and
`test_hb_gnd_temper_net_assignment_is_fixed_but_kicad_pro_sync_is_known_red`
(asserts the `design_rules.py` home is fixed AND the `kicad_pro` home is
still a `TOOL ERROR` — a genuine two-sided pin, mirroring this gate's
existing bar set by `test_gate_drive_net_names_agree_regression_guard`
(clean) / `test_gate_net_current_citations_are_known_tool_errors` (red)).
27/27 tests in this file pass. The gate's overall exit code (5, TOOL ERROR)
is unchanged by this addition — it was already 5 before this change, driven
by the pre-existing `gate_h*_net_current_rating_a` facts; the new `hb-gnd`
kicad_pro TOOL ERROR adds a second, independent reason, correctly reported
rather than hidden behind the first.

## 8. Verification run

```
$ sha256sum pcb/temper.kicad_pcb   # before AND after this investigation
6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1  pcb/temper.kicad_pcb

$ .venv/bin/python scripts/check_oracle_hashes.py
oracle content-hash gate: 167/167 oracle files OK (registry: 167 entries)

$ .venv/bin/python -m pytest scripts/tests/test_check_fact_registry_drift.py -q
27 passed

$ .venv/bin/python -m pytest packages/temper-placer/tests/core/test_design_rules_pbt.py -q
13 passed

$ .venv/bin/python -m pytest packages/temper-placer/tests/core/ packages/temper-placer/tests/pcl/ \
    scripts/tests/test_check_fact_registry_drift.py scripts/tests/test_check_creepage_clearance_drift.py \
    scripts/tests/test_check_netclass_class_param_correspondence.py scripts/tests/test_generate_kicad_dru.py \
    scripts/tests/test_sync_kicad_netclass_assignments.py scripts/tests/test_check_hv_netclass_coverage.py -q
10 failed, 4777 passed, 6 skipped
# 2 of the 10 are this change's own, documented, oracle-differential consequence
# (test_module_constants_identical, test_create_temper_design_rules_identical).
# 8 are pre-existing and independently reproduced against unmodified main
# before any edit (see §6).
```

## Files changed

- `packages/temper-placer/src/temper_placer/core/design_rules.py` —
  `TEMPER_NET_ASSIGNMENTS["hb-gnd"] = "HighVoltage"`.
- `packages/temper-placer/tests/core/test_design_rules_pbt.py` —
  `_NET_ALPHABET`: `"hb-gnd"` → `"TEST-GND"` (precedented, non-oracle test
  maintenance).
- `scripts/check_fact_registry_drift.py` — 2 new facts (§7).
- `scripts/tests/test_check_fact_registry_drift.py` — 2 new pinning tests
  (§7).

## Files read, not touched

- `pcb/temper.kicad_pcb` — sha256 verified unchanged (see header).
- `pcb/temper.kicad_pro` — real file untouched; impact measured only on
  scratch copies under `/tmp` (§4).
- `packages/temper-placer/tests/core/_design_rules_py_oracle.py` — pinned
  oracle, untouched (§5); `scripts/oracle_hashes.json` untouched, no hash
  re-pinned.
- `scripts/sync_kicad_netclass_assignments.py` — pre-existing gate-error
  condition confirmed unrelated (§6), not fixed.
