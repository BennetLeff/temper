<!-- provenance: commit=caec25d61 (main, HEAD at start of this task), worktree agent-aa0fd3a4b1b6f7aa2.
pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1
verified unchanged before, during, and after this task (read-only against the board;
never opened for writing). Venv: `make venv-isolate` in THIS worktree only (unset
CONDA_PREFIX was required first -- both VIRTUAL_ENV and CONDA_PREFIX were set). All
measurements below are live, run in this worktree's own .venv against the real
committed board, not estimated. -->

# `netclass_constraints.py` manifest-backed classification + `IECCreepageGate`/`DeltaMapper` stale-6.0mm fix

Per `docs/evidence/2026-08-17-placer-creepage-constraint-spike.md` (PR #1317)
recommendation items 3 and 4. Two independent commits, one concern each:

- `22876b7b7` — `netclass_constraints.py` classifier fix
- `48393b2b6` — `IECCreepageGate` SSOT threshold + dead-constant removal
- `9c0e75e9c` — one pre-existing test fixed to keep exercising the real code path

Out of scope (a sibling's work, confirmed untouched): `domain_clearance.py`,
`solve_placement()`'s main constraint wiring.

---

## 1. `netclass_constraints.py`: classify from `DesignRules`, not net-name keywords

### The defect, confirmed on the real board

`_resolve_component_net_class()` classified every pin's net via
`core.net_classification.classify_net_type()` — a 4-bucket
(ground/power/hv/signal) net-**name** keyword heuristic — then mapped the
result onto one of 4 `DesignRules` class names. Probed directly:

```
power_in.ntc-no  -> classify_net_type -> "signal"   (K1's HV relay contact)
w1_2             -> classify_net_type -> "signal"   (K1's HV relay contact)
rtd_force_p      -> classify_net_type -> "signal"   (J1's SELV RTD net)
```

`elec/domain_manifest.yaml` declares `power_in.ntc-no`/`w1_1`/`w1_2` **HV**
(lines 105-106, 187) and J1's RTD nets **SELV**. `pcb/temper.kicad_pro`'s
`net_settings.netclass_assignments` (corrected by #1279) agrees:
`power_in.ntc-no`/`w1_1`/`w1_2` → `HighVoltage`, `rtd_force_p`/`rtd_sense_p`/
`rtd_sense_n` → `FinePitch`. The keyword heuristic disagreed with both.
Same-class pairs are skipped
(`generate_netclass_separated_constraints`: `if ca == cb: continue`), so K1
and J1 landed in the same bucket ("signal") and got **zero** separation
constraint — the exact defect the spike doc traced to this file.

### The fix

`_resolve_component_net_class()` now calls
`design_rules.get_rules_for_net(net_name)` — the same
`TEMPER_NET_ASSIGNMENTS`-backed, manifest/kicad_pro-consistent classifier
every other `DesignRules` consumer in the codebase already uses
(router_v6, DRU generation, `scripts/check_hv_netclass_coverage.py`,
`scripts/check_placement_pair_creepage.py`'s prototype). Verified directly:

```
design_rules.get_rules_for_net("power_in.ntc-no").name == "HighVoltage"
design_rules.get_rules_for_net("w1_1").name            == "HighVoltage"
design_rules.get_rules_for_net("w1_2").name             == "HighVoltage"
design_rules.get_rules_for_net("rtd_force_p").name       == "Default"   (see below)
```

A resolved name of `"Default"` (the fallback tier for any net with no
per-net override, no explicit assignment, and no pattern-cascade match) is
normalized to `"Signal"` inside `_resolve_component_net_class()`. This is
load-bearing, not cosmetic: `netclass_rules.yaml`'s `class_pairs` table
(e.g. `HighVoltage-Signal: 6.0mm`) is keyed on literal class names and has
no `"Default"` row. Leaving unclassified nets as `"Default"` would silently
drop their cross-class protection from the intended 6.0mm down to
`max(HighVoltage.clearance, Default.clearance)` = 2.0mm for every net
without an explicit assignment — a loosening. Verified this normalization
is necessary and sufficient: every pre-existing unit test in
`test_netclass_constraints.py` and `test_e2e_netclass_ssot.py` that encodes
a `6.0mm` expectation for a generic-LV-vs-HV pair passes unchanged with it,
and fails without it.

The severity-rank used to pick one representative class per multi-pin
component was rebuilt on `NetClassRules.safety_category` (`AC`/`HV`/`LV`,
already present on every class) with `.clearance` as a tiebreaker, replacing
the old fixed `{"HighVoltage":4,"Power":3,"GND":2,"Signal":1}` table, which
only had 4 entries and could not rank any of the other 9 real classes
(`ACMains`, `FinePitch`, `GateDriveHV`, `GateDriveSELV`, `HighCurrent`,
`HighVoltageTank`, `HighVoltageSignal`, `HighVoltageIsolated`, `HighSpeed`).

### Verified fix: J1↔K1

Measured directly against the real board and the real production
`DesignRules` (`load_netclass_rules(configs/netclass_rules.yaml).design_rules`
— the exact object `_encoder_core.encode_constraints` passes in production,
including its `class_pairs` table, which a bare `DesignRules()` does not
carry):

| | Before | After |
|---|---|---|
| J1↔K1 `SeparatedConstraint` | **absent** | **6.0mm** |

Total pairwise constraints generated across the real board (169 components):
**9,693 (old) → 8,978 (new)**. 1,666 pairs newly constrained, 2,381 pairs no
longer constrained (same-class pairs that were previously split across the
crude 4-bucket space by accident and are now correctly recognized as
same-domain).

### Every net whose resolved class changed — direction, reported per the task's hard rule

139 pad-bearing nets on the board; **44 changed class**. Comparison metric:
each net's resolved class's own `.clearance` value in mm (the literal field
this mechanism consumes), not an invented severity number.

**31 STRICTER** (the safe direction) — includes the defect's own nets:

| Net | Old class (mm) | New class (mm) |
|---|---|---|
| `power_in.ntc-no` | Signal (0.15) | **HighVoltage (2.00)** |
| `w1_1` | Signal (0.15) | **HighVoltage (2.00)** |
| `w1_2` | Signal (0.15) | **HighVoltage (2.00)** |
| `+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `tank-out` | Signal (0.15) | HighVoltage (2.00) |
| `GATE_HS`, `GATE_LS` | Signal (0.15) | GateDriveHV (0.25) |
| `hb.gate_hs.driver-p1-1`, `hb.gate_hs.driver-p2` | Signal (0.15) | HighVoltageIsolated (6.00) |
| `tank.c_tank1-p2` | Signal (0.15) | HighVoltageTank (2.00) |
| `ac_l`, `ac_n` | HighVoltage (2.00) | **ACMains (6.00)** |
| `gnd` | GND (0.30) | Power (0.50) *(pre-existing `TEMPER_NET_ASSIGNMENTS["gnd"]="Power"` entry, see §1a)* |
| `+15V_LS`, `discharge.k_dis1-nc`, `discharge.k_dis2-nc`, `hb.power_loop.q_high-g` | Power/Signal | HighVoltageSignal (2.00) |
| `safety.ovp.r_{adc,div}_{top1,top2}-p2` (4 nets) | Signal (0.15) | HighVoltage (2.00) |
| `V_BUS_SENSE`, `discharge.k_dis{1,2}-coil{1,2}`, `power_in.bypass_relay-coil{1,2}` | Signal (0.15) | Power (0.50) |
| `PWM_HS`, `PWM_LS` | Signal (0.15) | GateDriveSELV (0.25) |

**13 LOOSER**, all `Signal (0.15mm) → FinePitch (0.10mm)`, all same
`safety_category` (`LV→LV`, no domain change): `RTD_CS_N`, `RTD_DRDY`,
`RTD_HW_FAULT`, `RTD_SCK`, `RTD_SDI`, `RTD_SDO`, `bias`, `cs_n`, `refin_n`,
`sclk`, `sdi`, `sdo`, `vbias`. **Not safety-relevant**: verified every one of
these 13 matches `pcb/temper.kicad_pro`'s own `netclass_assignments` exactly
(the fab-authoritative source), and their *cross-domain* protection is
unaffected — `class_pairs` carries `HighVoltage-FinePitch: 6.0mm` and
`ACMains-FinePitch: 6.0mm`, identical to the `HighVoltage-Signal`/
`ACMains-Signal` rows these nets used before. The 0.15→0.10mm delta only
ever applies to same-class FinePitch↔FinePitch pairs (e.g. these RTD SPI
lines among themselves), which is what kicad_pro's own declared clearance
for that class already is.

**0 SAME-CLEARANCE.**

### A secondary finding this fix exposes but does not fix: `class_pairs` has no `GateDriveHV`/`GateDriveSELV` rows

Comparing the OLD vs NEW **pairwise** constraint set (not just per-net
class) surfaced 135 pairs where the emitted clearance value went down.
102 of these are same-HV-domain pairs (e.g. `C23↔C26`, both floating on
`SW_NODE`/tank/gate-drive nets) that were **accidentally** getting the
6.0mm cross-domain figure under the old scheme, purely because one side's
misclassified net (e.g. `hb-gnd`, `+15V_LS`) happened to fall into the old
crude "Signal"/"GND" bucket — not a deliberate protection. These are
corrections, matching `netclass_rules.yaml`'s own documented intent that
same-HV-domain pairs are "the DRU's business" (kicad-cli's own 2.0mm
same-side figure), not `class_pairs`'.

The remaining **33 pairs are genuinely cross-domain** (one side resolves
`HV`/`AC`, the other `LV`) and got weaker, e.g. `J1↔R23`: 0.30mm → 0.25mm.
Root-caused precisely: **every one of the 33** involves `GateDriveHV` or
`GateDriveSELV` on at least one side, and `netclass_rules.yaml`'s
`class_pairs` table (21 entries) has rows for `ACMains-*`, `HighVoltage-*`,
`HighVoltageTank-*`, `HighVoltageIsolated-*`, `HighVoltageSignal-*` — but
**zero** rows for `GateDriveHV`/`GateDriveSELV`/`HighCurrent` on either
side. Confirmed by grep of the YAML file. This gap **pre-dates this fix**
(these three classes were never resolvable by `netclass_constraints.py` at
all before today — everything HV-adjacent fell into the coarse 4-bucket
space, which happened to route most of these pairs through the
`HighVoltage-Signal`/`GND-Signal` fallback instead). My fix makes the gap
**newly operative** for the first time, because it is the first time
`netclass_constraints.py` ever resolves a component to `GateDriveHV`/
`GateDriveSELV` at all.

**I did not fix this.** Adding `class_pairs` rows for these three classes
requires a clearance-value decision — the task's hard rule forbids
inventing a standards value, and this specific gap is exactly the kind of
"reconcile the three classifiers" work the spike doc's own §7.5 defers as
separate, smaller follow-up work. Flagging loudly per the task's
instruction: **`GateDriveHV`/`GateDriveSELV`-adjacent cross-domain pairs
(33 on the real board, including one touching J1) get materially less
placer-side separation bias than `HighVoltage`-adjacent pairs of the same
domain shape.** This is a placer-feasibility (pre-route, CP-SAT bias) model
only — it does not touch the fab-authoritative DRC/DRU enforcement
(`scripts/generate_kicad_dru.py`), which is unaffected by anything in this
file.

### 1a. A related, NOT introduced by this fix, pre-existing gap: `hb-gnd`

Investigating the `gnd`/`hb-gnd` net family surfaced that
`design_rules.get_rules_for_net("hb-gnd")` currently resolves to `"GND"`
(LV, 0.3mm) on **both** the old and new classifier — `core.net_classification.
classify_net_type("hb-gnd")` also returns `"ground"`. This is the exact net
the handoff (§15) singles out as HV ("the half-bridge low-side switch's
return conductor, ~-170V... one CT-primary-winding from `DC_BUS_RTN`") and
`docs/evidence/2026-08-17-hb-gnd-classification-stale-test.md` (PR #1300)
confirms is genuinely HV per `elec/domain_manifest.yaml` (added there by
PR #1145). PR #1300 fixed a **test** in
`router_v6/clearance_check.py`'s `_classify_net_class()` — a **third**,
separate net classifier that checks `elec/domain_manifest.yaml` membership
*first*, before any keyword cascade, and correctly returns `"HV"` for
`hb-gnd`. `core/design_rules.py`'s `TEMPER_NET_ASSIGNMENTS` table (the one
`netclass_constraints.py` now uses) has **no manifest-consulting step at
all** and has no explicit `"hb-gnd"` entry, so it falls through to the
ground-keyword-pattern tier and gets `"GND"`.

**This is unchanged by my fix** (identically `"GND"` before and after,
confirmed) — it is not a regression I introduced. It does not affect the
J1/K1 result (R23, the one component in this investigation carrying
`hb-gnd`, also carries `GATE_LS`, which correctly resolves `GateDriveHV`/HV
and wins the severity-max, so R23's own representative class is correctly
HV regardless of `hb-gnd`'s individual misclassification). Flagged because
it is real, live, and directly on-topic: `core/design_rules.py`'s
`TEMPER_NET_ASSIGNMENTS`/pattern-cascade classifier is **not** the same
thing as "the manifest" despite both files' own claims to be *the*
authoritative source — a fourth instance of the handoff's "one fact, many
homes" pattern, on top of the three (`netclass_constraints.py`,
`clearance_check.py`, `gates.py`'s own `_is_hv_net`, §2 below) this task
already found. Not fixed here: `TEMPER_NET_ASSIGNMENTS` is a widely-shared
SSOT (`design_rules.py`) outside this task's assigned files
(`netclass_constraints.py`, `gates.py`, `delta_mapper.py`), and PR #1300's
own investigation already flagged the deeper reconciliation as future work.

---

## 2. `IECCreepageGate`: revived with the SSOT figure, not deleted

### Liveness — corrected from the task's source spike

The spike doc (§2) states `IECCreepageGate()` is "instantiated only inside
their own unit test files... never in production code." **This is not what
the current source shows, and I verified it by reading, not by trusting the
claim** (per this task's hard rule: establish liveness by call sites, never
by naming or by a prior doc's prose).

`gates.py:1063-1070`, inside `PhysicsGate.check()` (production code, no
mocks, no test scaffolding):

```python
creepage_gate = IECCreepageGate()
creepage_result = creepage_gate.check(state)
...
violations.extend(creepage_result.violations)
```

`PhysicsGate` **is** one of the 5 gates registered under `--all-gates`
(`_loop_core.py:190`, confirmed unchanged since the spike). So
`IECCreepageGate.check()` is reachable, in production, whenever a caller
passes `--all-gates` (the CLI flag) or an explicit `gates=` list including
`PhysicsGate` to `PlaceRouteLoop`. It is genuinely true, and matches the
task's framing, that: (a) `IECCreepageGate` is **never a directly-registered
top-level gate** in either of `loop.py`'s two fixed lists (confirmed:
`all_gates=False` → `[DrcGate, RoutingGate]`; `all_gates=True` →
`[DrcGate, RoutingGate, StackupGate, PhysicsGate, QualityGate]` — the class
name `IECCreepageGate` appears in neither), and (b) `--all-gates` is not
wired into any CI workflow or `Makefile` target (confirmed by grep of
`.github/workflows/*.yml` and `Makefile`) — so it is live in the sense of
"reachable from production code with no test scaffolding," not in the sense
of "automatically exercised."

**Decision: revive with the SSOT figure. Do not delete.** Its verification
(routed-board `kicad-cli` DRC, filtered to clearance violations that cross
an HV↔LV net boundary) is real, useful, and has no other home in this
codebase — deleting it would remove the one place a post-route HV/LV
creepage check exists at all outside the fab-authoritative
`generate_kicad_dru.py` path.

### The stale value, fixed

`IECCreepageGate.check()` hardcoded `severity=6.0, threshold=6.0,
context={"required_mm": 6.0}` with no citation. 6.0mm is not a value in any
recovered IEC 60335-1 table (same debunking already on record for the
identical figure in `core/design_rules.py`'s old `ACMains`/`HighVoltage`
`creepage_mm` fields) and is superseded by this project's own PD3 decision:
12.6mm reinforced (PR #1219/#1224).

Fixed by reading from the SSOT — not inventing a new figure, per the hard
rule. New module constant:

```python
HV_LV_CREEPAGE_MM: float = (
    _tdb.creepage_table_lookup(3, "IIIa/IIIb", ">250-400", "17").value_mm() * 2.0
)
```

This is the **identical call** `scripts/generate_kicad_dru.py`'s own
`HV_CREEPAGE_ENFORCED_MM` (the fab-authoritative figure) uses: PD3, material
group IIIa/IIIb, >250-400V, recovered Table 17, doubled for reinforced
insulation per cl. 29.2. Verified directly: `HV_LV_CREEPAGE_MM == 12.6`.

`PhysicsGate` also carried a **dead** `_CREEPAGE_MIN_MM: float = 6.0` class
attribute, commented "SSOT — do not duplicate" while being an actual,
unused, also-stale duplicate — confirmed by grep, zero read sites anywhere
in the file. Sub-check 4 ("Creepage ≥ 6mm") has always gotten its real
number from `IECCreepageGate.check()`'s own internal call, never from this
constant. Removed rather than updated, since nothing reads it — this is
deleting genuinely dead code, not weakening a live check.

### Proof the stale 6.0mm no longer reaches `DeltaMapper`

`DeltaMapper.map()`'s `CREEPAGE` branch (`delta_mapper.py:148-167`) itself
needed **no code change** — it already forwards `violation.threshold`
verbatim (`min_dist = violation.threshold`), a correct, generic dispatch.
The stale value lived entirely in the *producer* (`IECCreepageGate`), not
the *consumer* (`DeltaMapper`). Verified end-to-end, live, in this
worktree's venv:

```python
>>> from temper_placer.placer.cp_sat.gates import IECCreepageGate, HV_LV_CREEPAGE_MM
>>> HV_LV_CREEPAGE_MM
12.6
>>> # IECCreepageGate().check() on a mocked HV/LV clearance violation:
>>> violation.severity, violation.threshold, violation.context
(12.6, 12.6, {'required_mm': 12.6, 'rule': 'clearance'})
>>> # fed into the real DeltaMapper.map():
>>> DeltaMapper.map(violation).constraint.min_distance_mm
12.6
```

Before this fix, the same trace produced `6.0` at every step. Confirmed by
temporarily re-deriving the old code path (not committed): identical
`Violation`/`DeltaMapper` plumbing, `severity=6.0, threshold=6.0` in,
`min_distance_mm == 6.0` out.

### Flagged, not fixed: `_is_hv_net()`'s own local keyword list

`IECCreepageGate.check()` classifies DRC-violation net **names** (strings
from `kicad-cli`'s error output, e.g. `"Pad 2 [power_in.ntc-no] of K1..."`)
via a **fourth**, independently-maintained HV keyword set local to this
gate:

```python
_HV_NET_PATTERNS = frozenset({"DC_BUS+","DC_BUS-","SW_NODE","SW_NODE_DC+",
                               "SW_NODE_DC-","AC_L","AC_N"})
```

This does not include `power_in.ntc-no`, `w1_1`, or `w1_2` — the exact
three nets whose misclassification in `netclass_constraints.py` is this
task's primary defect. A DRC clearance violation naming one of these three
would silently not be recognized as HV↔LV by this gate. This is the same
defect shape, in the same class (`IECCreepageGate`), that I fixed in §1 —
but reconciling it requires threading a `DesignRules` instance into a
function that currently has none available (`_is_hv_net(name: str)` takes
only a bare string), a materially larger change than this task's assigned
scope (the threshold value + the `DeltaMapper` leak). Documented in the
code itself (see `_is_hv_net`'s docstring) and flagged here so it is not
mistaken for fixed.

---

## 3. Test verification

Ran in this worktree's own `.venv` (`make venv-isolate`, all pyo3
extensions rebuilt here, none touched in the shared repo `.venv`).

**Directly relevant to this change, all green:**

- `tests/pcl/test_netclass_constraints.py` — 8/8 (2 tests updated for the
  new 3-arg `_resolve_component_net_class` signature and the `Default`
  net's correct comment; assertions unchanged)
- `tests/pcl/test_e2e_netclass_ssot.py` — 4/4 (unchanged)
- `tests/core/test_coverage_paydown_v22.py` — all netclass/gate tests pass,
  including one fixed (`test_generate_cross_class_constraints`, see below)
- `tests/placer/cp_sat/test_physics_gate.py` — all `IECCreepageGate`/
  `PhysicsGate` tests that don't require live `kicad-cli` output pass;
  `test_creepage_violation_hv_to_lv`'s threshold assertion updated
  `6.0 → HV_LV_CREEPAGE_MM`
- `tests/placer/cp_sat/test_delta_mapper.py` — 100% pass, unchanged (its
  `threshold=6.0` values are synthetic test inputs exercising generic
  dispatch, not real `IECCreepageGate` output — confirmed by reading; no
  update needed)
- `tests/placer/cp_sat/test_gates_rust_differential.py` — 100% pass,
  unchanged (pinned oracle `_gates_py_oracle.py`, untouched; its
  `threshold=6.0`/`severity=6.0` values are arbitrary round-trip test data
  for the `Violation` container, not `IECCreepageGate`'s real output —
  confirmed by reading)

**One pre-existing test fixed** (`test_coverage_paydown_v22.py::
TestNetclassSeparatedConstraints::test_generate_cross_class_constraints`):
called `generate_netclass_separated_constraints` with a bare, empty
`DesignRules()`. Harmless before this fix (the old classifier never
consulted `design_rules`'s own tables at all); after this fix, an empty
`DesignRules()` correctly has no classes to resolve against and both test
components collapse to `"Default"`, silently erasing the cross-class pair
the test means to exercise. Updated to `create_temper_design_rules()`,
matching every other test in the same file and the function's real caller.

**7 pre-existing failures, confirmed unrelated** (none of the 3 files this
task touches — `netclass_constraints.py`, `gates.py`, `delta_mapper.py` —
appear in `git log` for the failing tests' dependencies more recently than
this task's own HEAD):

- 6× `test_physics_gate.py::test_creepage_*` — `run_drc()` now fail-closed
  refuses to DRC any `.kicad_pcb` without a resolvable `.kicad_pro` sidecar
  (`67e04601f`, "fail loud on unresolvable KiCad project context", predates
  this task). The test helper `_write_pcb()` writes a bare `.kicad_pcb`
  with no sidecar. Reproduced the identical failure standalone, calling
  `run_drc()` directly with zero `gates.py` involvement — proves this is
  independent of anything in this diff.
- 1× `test_e2e_netclass_ssot.py::test_class_pairs_contain_safety_critical_entries`
  — asserts `"IEC 60335-1" in class_pairs[("ACMains","Signal")]["because"]`;
  the actual text (unmodified by me, in `netclass_rules.yaml`, last touched
  `968d1a33d`/`c61db4710`, both before this task's HEAD) now reads
  "UNSOURCED legacy 6.0mm... debunked... placer-feasibility model only" —
  a stale assertion left behind by the 2026-08-15 safety-citation audit,
  same shape as the `hb-gnd` test PR #1300 fixed, but a different file, not
  in this task's assigned scope.

**Broader sweep** (`tests/placer/cp_sat/`, 913 tests): 24 failed before my
`test_coverage_paydown_v22.py` fix (23 after), 863-889 passed. Spot-checked
5 of the remaining unrelated failures individually
(`test_erc_gate.py` — missing `KICAD7_FOOTPRINT_DIR` in this sandbox;
`test_tank_creepage.py::test_other_hv_refs_excludes_tank_refs` — a
pre-existing board-state assumption mismatch in `tank_creepage.py`, a file
this task does not touch; `test_body_collision.py`, `test_heatsink_colocation.py`,
`test_fixed_copper_builder_rust_differential.py` — same pattern). None
reference `netclass_constraints`, `IECCreepageGate`, `HV_LV_CREEPAGE_MM`, or
`_CREEPAGE_MIN_MM` (confirmed by grep). `git diff --stat HEAD` for this
task touches exactly 5 files total; none of the failing tests' own
dependency files are among them.

**No new honest reds were introduced by this work.** The reds found are
pre-existing and orthogonal; the classifier and threshold fixes themselves
are fully green against their own real, non-mocked unit and end-to-end
coverage.

---

## Files touched

- `packages/temper-placer/src/temper_placer/placer/cp_sat/netclass_constraints.py`
- `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py`
- `packages/temper-placer/tests/pcl/test_netclass_constraints.py`
- `packages/temper-placer/tests/placer/cp_sat/test_physics_gate.py`
- `packages/temper-placer/tests/core/test_coverage_paydown_v22.py`

## Files read, not touched (confirmed out of scope / owned elsewhere)

- `packages/temper-placer/src/temper_placer/placer/cp_sat/delta_mapper.py` — needed no
  code change, verified by direct test (§2)
- `packages/temper-placer/src/temper_placer/core/design_rules.py` — `TEMPER_NET_ASSIGNMENTS`
  SSOT, has its own pre-existing gaps (§1a) not fixed here
- `packages/temper-placer/configs/netclass_rules.yaml` — `class_pairs` gap (§1) not
  fixed here
- `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py` — sibling's
  file
- `pcb/temper.kicad_pcb` — sha256 verified unchanged (see provenance header)
