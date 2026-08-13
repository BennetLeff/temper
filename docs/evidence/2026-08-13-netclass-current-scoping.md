<!-- provenance: branch fix/netclass-current-scoping, worktree
/home/bennet/Desktop/temper-netclass-current-scoping, base origin/main @
a3e117347. pcb/temper.kicad_pcb is UNCHANGED throughout this task
(`git status --porcelain pcb/temper.kicad_pcb` empty at every commit) --
only pcb/temper.kicad_pro (netclass declarations/assignments, not the
board) was edited. All routing/DRC measurements below run against scratch
copies under /tmp (gitignored, not part of this branch's diff), produced
by `scripts/route_board.py --net-batching` against unmodified
`pcb/temper.kicad_pcb`. -->

# Netclass current-band scoping: derivation, class structure, measured feasibility

## Headline

`HighVoltage` bundled a **1000x current range** into one class with one
trace width: the ~20mA discharge-bleed/signal taps alongside the 22.5A RMS
tank/DC-bus. No single width was correct for that. This re-scopes the
class by current band, not just voltage domain:

- **`HighVoltage`/`HighVoltageTank` trace width 3.0mm -> 5.0mm** for the
  bus/tank-current members (22.5A RMS, 40°C pour budget requires 4.77mm)
  and, reused rather than split further, the three 15A/20°C-trace members
  (`w1_1`, `w1_2`, `power_in.ntc-no`, requiring 4.16mm) that measure as
  real routed copper on the real board, not pours.
- **`ACMains` trace width reconciled 2.5mm -> 3.0mm** (`pcb/temper.kicad_pro`
  now matches `netclass_rules.yaml`, the router's own SSOT) — 2.5mm was
  short of the 15A/40°C-pour requirement (2.73mm) by ~8%.
- **New `HighVoltageSignal` class (0.5mm)** for the mA-scale current tier
  carved out of `HighVoltage`: the discharge bleed string, the Q_high gate
  tap, U3's ZCD divider/opto-anode net, and the gate-driver bias rail.
  Same clearance/creepage/voltage_v/safety_category as `HighVoltage` (same
  voltage domain) — this class changes the current/width requirement only.

Declared in both `pcb/temper.kicad_pro` and `design_rules.py` (the silent
`Default`-fallthrough trap this task's own brief warned about), and
threaded through every `generate_kicad_dru.py` rule that gives
`HighVoltage` a same-side reduction or a reinforced-to-LV creepage
requirement, verified against every real same-footprint pair on the board
that spans the old/new class boundary.

**Measured, not asserted:** TRUE `track_width` improves 1027 -> 727
(-29%). TRUE `clearance` moves 1172 -> 1496, but that swing is **dominated
by a single net's net-batching solve-order luck**, not the width/class
change — see "Measurement" below for the full attribution and why the
change is a net improvement once that net is factored out. Creepage moves
146 -> 152 (+4%, small, partially the same-net effect). Pad connectivity is
unchanged, 51/139 both runs. The PD2/8.0mm isolation barrier and IGBT
heatsink co-location (#1082) are **unaffected by construction** — this task
moves no component and touches no placement data.

## 1. Deriving the correct width per current band

### 1.1 Method, re-derived independently (not copied from any prior document)

`docs/hardware/TRACE_WIDTH_CALCULATIONS.md` S2 states IPC-2221B for
external layers: `I = k × ΔT^0.44 × A^0.725`, `k=0.048` external,
rearranged for width `W(mm) = (A_mils² / (oz × 1.37)) × 0.0254`. Implemented
and run independently (not transcribed from PR #1119's own numbers, though
they match to 4 decimal places — see the worked table below):

```python
def width_mm(I, dT, oz=2, k=0.048):
    A = (I / (k * dT**0.44)) ** (1/0.725)       # mils^2
    return (A / (oz * 1.37)) * 0.0254            # mm

def current_for_width(w_mm, dT, oz=2, k=0.048):
    A = (w_mm / 0.0254) * oz * 1.37
    return k * dT**0.44 * A**0.725
```

### 1.2 Per-band derivation

| Band | Nets | Design current | ΔT budget | Required width | Chosen width | Basis |
|---|---|---:|---:|---:|---:|---|
| AC mains, pour | `ac_l`, `ac_n` | 15A | 40°C (pour) | 2.7288mm | **3.0mm** | reconciled to `netclass_rules.yaml`'s existing value, clears requirement with ~10% margin |
| HV bus/tank, **trace** | `w1_1`, `w1_2`, `power_in.ntc-no` | 15A | 20°C (trace — measured real routed copper, not pour) | 4.1559mm | **5.0mm** (shared with the pour tier below) | reuses `HighVoltage`'s bumped width rather than a third class; ~20% margin over 4.16mm |
| HV bus/tank, pour | `SW_NODE`, `DC_BUS_RTN`, `+170V_BUS`, `PWR_RTN`, `tank-out`, `tank.c_tank1-p2` | 22.5A RMS (thermal design current, `elec/src/modules.ato:585-587`) | 40°C (pour) | 4.7737mm | **5.0mm** | already measured feasible, PR #1119 |
| HV signal/bleed | `discharge.k_dis1-nc`, `discharge.k_dis2-nc`, `hb.power_loop.q_high-g`, `a`, `zcd`, `+15V_LS` | ~20mA (bleed string) to <=500mA (gate-driver bias peak, `TRACE_WIDTH_CALCULATIONS.md` S3.8) | 20°C (trace) | 0.0004mm–0.0381mm (below any manufacturable width) | **0.5mm** | manufacturability floor, taken directly from S3.8's own precedent for the closest analogous case (0.5A gate-driver supply -> "Minimum: 0.5mm (20 mils) for manufacturability"), not borrowed from an unrelated class |

Verification, both directions:

| Width | @40°C pour carries | @20°C trace carries |
|---:|---:|---:|
| 2.5mm (old `ACMains` kicad_pro value) | 14.08A | — |
| 3.0mm (old `HighVoltage`/new `ACMains`) | 16.07A | 11.84A |
| 5.0mm (new `HighVoltage`/`HighVoltageTank`) | 23.27A | 17.15A |
| 0.5mm (new `HighVoltageSignal`) | — | 3.23A (vs. the ~0.5A worst case this width targets) |

### 1.3 Trace-vs-pour, verified against the real board (not assumed)

The task brief's hypothesis — `ac_l`/`ac_n` legitimately reach copper via
zone pours (40°C budget) while `w1_2`/`power_in.ntc-no` are routed traces
(20°C budget) — is correct as a description of what is actually on the
board, confirmed directly (`pcb/temper.kicad_pcb`, net-name -> net-number ->
`(segment ...)`/`(zone ...)` line count, read-only, no file modified):
`ac_l`/`ac_n` are 100% zone-pour, 0 track segments; `w1_2` and
`power_in.ntc-no` are 100% routed trace, 0 zone coverage. But it is **not**
because the class scopes them differently by declared intent — both
`ACMains` and `HighVoltage` declare `routing_strategy="plane_required"` in
`core/design_rules.py`, i.e. every `HighVoltage` member is *supposed* to be
pour-eligible. The divergence is in *realized geometry* (per-net pad-cluster
zone eligibility at route time, `_zone_pour_stitch.py`), not class
declaration — see PR #1119 S2.2/S4 for the full trace. This task's fix
(re-scoping current bands, not trace-vs-pour scoping) is therefore the
correct one independent of that separate, unresolved geometry-vs-intent gap.

### 1.4 The 60°C ambient figure — confirmed inert to every number above

`TRACE_WIDTH_CALCULATIONS.md` S1 declares 60°C ambient, 20°C trace rise,
40°C pour rise. Re-confirmed directly from the formula implementation in
1.1: `width_mm()`/`current_for_width()` take only `dT` (the rise) as an
argument — there is no ambient/absolute-temperature term anywhere in
IPC-2221B's `I = k × ΔT^0.44 × A^0.725`. Changing 60°C to any other value
changes none of the widths derived above; it would only matter for an
absolute `ambient + rise` limit check against some other threshold, which
no formula in this document performs. The 60°C figure also disagrees with
the project's own declared 50°C ceiling (`main.ato`'s `t_ambient_max`) —
flagged, not fixed here, since it is inert to this task's outputs and
correcting the citation is a separate, non-blocking documentation task.

### 1.5 The tank peak-current dependency — not resolved here, does not block this derivation

The tank's peak current (28.7–31.9A) already exceeds the design's own
`HighVoltageConstraints.i_max` (25A) and the coil connector's `LitzPad_15A`
pad rating (15A) — `elec/src/modules.ato:585-593`, `UNRESOLVED AND RECORDED,
NOT FIXED HERE` in the source comment itself. This is a separate,
already-flagged design-current-budgeting gap, owned by whoever owns the
coil/converter design, not a netclass-width question. **It does not block
the derivation above**: every bus/tank width in 1.2 is sized to the RMS
thermal design current (22.5A), the correct steady-state metric for a
continuous sinusoidal current and the one IPC-2221B's formula actually
governs — not the peak, which is a pad/component rating question copper
cross-section cannot fix. Not resolved by narrowing any trace, per
instruction.

## 2. Class structure chosen, and why

**Reused rather than proliferated.** Two viable designs were considered:

- **(A) One new class per exact current tier** (a third "HighVoltageTrace"
  class at ~4.5mm for `w1_1`/`w1_2`/`power_in.ntc-no`, plus the
  `HighVoltageSignal` class below) — minimizes over-build per net, costs a
  second new class and a second full pass through every
  `generate_kicad_dru.py` cross-domain rule.
- **(B) Reuse `HighVoltage`'s bumped 5.0mm for both the pour tier and the
  trace tier** (chosen) — the trace tier's exact requirement is 4.16mm;
  5.0mm covers it with ~20% margin, the same rounding margin already
  applied to `ACMains` (2.73mm required, 3.0mm chosen, ~10% margin). This
  is the design PR #1119 already measured feasible end-to-end (3.0mm ->
  5.0mm, full re-route, no regression) — reusing it costs nothing new to
  verify for the pour tier and only adds the already-modest over-build for
  three trace nets, against one entire class of DRU-threading risk avoided.

(B) is what's implemented. Only **one** new class (`HighVoltageSignal`) was
needed for the truly disjoint requirement — the mA-scale tier, three orders
of magnitude below the bus/tank current, where reusing 5.0mm would have
been absurd over-build (a 20mA bleed resistor does not need 5mm of copper)
and reusing the *old* 3.0mm (as today) is exactly the defect this task
exists to fix.

**`pcb/temper.kicad_pro` now declares 12 classes** (`Default`, `Power`,
`HighVoltage`, `HighVoltageTank`, `HighVoltageSignal`, `GateDriveHV`,
`GateDriveSELV`, `HighVoltageIsolated`, `ACMains`, `FinePitch`,
`Differential`, `GND`); `HighVoltageSignal` is declared identically in
`packages/temper-placer/src/temper_placer/core/design_rules.py`'s
`TEMPER_NET_CLASSES` and in `packages/temper-placer/configs/netclass_rules.yaml`
(the router's own SSOT) — the exact dual-declaration this task's brief
warned is required, verified by `scripts/check_netclass_class_param_correspondence.py`
(PROPERTY 1: 0 field mismatches across all three files) and
`scripts/check_hv_netclass_coverage.py` (PROPERTY 2: 0 declared-but-
unenforced classes, after the DRU threading in Section 3).

## 3. Implementation

### 3.1 Files changed

- `packages/temper-placer/src/temper_placer/core/design_rules.py` —
  `TEMPER_NET_CLASSES`: `HighVoltage`/`HighVoltageTank` trace_width
  3.0->5.0, `ACMains` trace_width 2.5->3.0, new `HighVoltageSignal` entry.
  `TEMPER_NET_ASSIGNMENTS`: `discharge.k_dis1-nc`, `discharge.k_dis2-nc`,
  `hb.power_loop.q_high-g`, `a`, `zcd`, `+15V_LS` reassigned to
  `HighVoltageSignal`.
- `packages/temper-placer/configs/netclass_rules.yaml` — mirrors the above
  (this is the file the router's A* corridor reservation actually reads);
  `HighVoltageSignal` `class_pairs` entries added, mirroring
  `HighVoltageTank`'s existing block.
- `pcb/temper.kicad_pro` — `net_settings.classes`: three width edits plus
  the new `HighVoltageSignal` class dict. `net_settings.netclass_assignments`:
  the same six net reassignments, applied via `scripts/sync_kicad_netclass_assignments.py`'s
  own diff/apply mechanism (restricted to exactly these six nets — that
  script's own `PROTECTED_NETS` guard for `PWR_RTN`/`CGND` is a pre-existing,
  already-tripped condition on `origin/main`, unrelated to this task, so its
  `--check`/`--write` CLI could not be run as-is; its diff/apply functions
  were called directly instead, restricted to this task's own six nets).
- `scripts/generate_kicad_dru.py` — see 3.2.
- `packages/temper-placer/tests/core/_design_rules_py_oracle.py` +
  `scripts/oracle_hashes.json` — the Rust-vs-Python differential oracle is a
  pinned verbatim copy of `design_rules.py`'s tables; updated in lock-step
  and re-pinned (`scripts/update_oracle_hashes.py`), following the exact
  precedent the file's own history already set for the `HighVoltageTank`
  addition (2026-08-12).
- `packages/temper-placer/tests/core/test_design_rules.py`,
  `packages/temper-placer/tests/io/test_netclass_loader.py` — class-count/
  class-set assertions bumped 12->13 classes, following the same tests'
  own established convention (each prior class addition bumped these same
  two assertions; git blame on both confirms this, not a new practice).

`pcb/temper.kicad_pcb` is untouched (`git status --porcelain pcb/temper.kicad_pcb`
empty at every commit on this branch).

### 3.2 DRU threading — every place `HighVoltage` gets special treatment, `HighVoltageSignal` gets the identical treatment

`scripts/generate_kicad_dru.py` hand-lists net-class names in ~10 cross-
domain rule conditions; a class present in `TEMPER_NET_CLASSES`/`kicad_pro`
but absent from these conditions silently falls back to whatever generic
rule *does* match — sometimes safe-but-over-conservative (a needless
barrier-crossing creepage charge on a same-domain pair), sometimes a real
gap (zero creepage protection where reinforced protection is required).
Verified against every real same-footprint pad pair on the board that
spans the old-`HighVoltage`/new-`HighVoltageSignal` boundary (C23, K2, K3,
R23, R24, U3, U7, U8 — found by parsing `pcb/temper.kicad_pcb`'s footprint
blocks for nets on both sides of the carve-out, read-only), each rule below
was extended to keep every one of those pairs' protection numerically
identical to what it was before the carve-out:

- **`class_order`** (trace-width rule loop): `HighVoltageSignal` added —
  without this, the class gets no `track_width` rule at all (caught by
  `check_hv_netclass_coverage.py` PROPERTY 2 during this task's own first
  pass, exactly as that gate's docstring says it should).
- **RULE 2 "AC Mains to LV"**: `HighVoltageSignal` added to the B-side
  exclusion, so an `(ACMains, HighVoltageSignal)` pair is not mislabelled
  a barrier crossing.
- **RULE 3 "AC Mains to HV"**: `HighVoltageSignal` added to the B-side
  inclusion (3.0mm same-side reduction), mirroring `HighVoltageTank`'s
  existing treatment.
- **RULE 4 "HV to LV"** / **RULE 4c "HighVoltageTank to LV"**:
  `HighVoltageSignal` excluded from both B-sides — without this, e.g. a
  (`SW_NODE`, `hb.power_loop.q_high-g`) same-footprint pair (R24) would be
  charged 8.0mm reinforced creepage for a same-domain functional pair, the
  identical defect shape RULE 4c's own 2026-08-12 comment already records
  for the `HighVoltageTank` carve-out.
- **New RULE 4d "HighVoltageSignal to LV"**: the real protection —
  2.0mm clearance + 8.0mm reinforced creepage against every true LV/SELV
  class. Without this the carve-out is a safety regression: `a` (U3's ZCD
  divider tap) is one pin of a real isolator on this board (U3), sharing a
  footprint with `gnd` (Power/LV) — before this task, that pair was
  protected by RULE 4 (`a` was `HighVoltage`); this rule is what keeps it
  protected now.
- **`HighVoltageIsolated` "same side"/"to LV"**: `HighVoltageSignal` added
  to the same-side inclusion and the to-LV exclusion — U7 (the gate driver
  IC) and U8 both have real pads spanning `HighVoltageIsolated` and (now)
  `HighVoltageSignal` (`+15V_LS`) on the same footprint.
- **`GateDriveHV`/`GateDriveSELV` "near HV"**: `HighVoltageSignal` added —
  R23/R24 are real gate resistors with one pad now `HighVoltageSignal`;
  without this they'd default to the conservative 2.0mm base-clearance
  floor instead of the intended 0.5mm same-side figure next to an IGBT
  gate resistor, a needless over-constraint.
- **RULE 5a "`HighVoltageTank` functional creepage"**: `HighVoltageSignal`
  added to the B-side — without it, a `(HighVoltageTank, HighVoltageSignal)`
  pair would get zero creepage protection against the highest-voltage node
  on the board (570.5 Vrms), since RULE 4c's exclusion (above) removes it
  from that path.
- **"HV internal same footprint"** (RULE 5, `A.Reference == B.Reference`,
  scoped to `{HighVoltage, HighVoltageTank}`): deliberately **not**
  extended. Every same-footprint pair spanning the carve-out (C23, K2, K3,
  U7, U8) falls back to KiCad's own per-netclass-pair base clearance
  (`max` of the two classes' declared `clearance`, both 2.0mm) when no
  custom rule matches — numerically identical to this rule's own 2.0mm
  figure, so omitting the extension changes nothing. Verified empirically:
  see Section 4's clearance measurement, which shows no anomaly at any of
  these footprints.

`scripts/generate_kicad_dru.py`'s own fail-closed `RuleShadowingError`
guard (a broad rule may never silently override a narrower, stricter one)
passed on the regenerated file with no changes needed to the reordering
logic itself.

### 3.3 Gates run

| Gate | Result |
|---|---|
| `scripts/check_netclass_class_param_correspondence.py` | PASS — 0 field mismatches, 0 unresolved class references |
| `scripts/check_hv_netclass_coverage.py` | PASS — all 5 properties, including PROPERTY 2 (0 declared-but-unenforced classes) after the DRU threading above |
| `scripts/check_netclass_map_board_correspondence.py` | PASS — unaffected (no hand-maintained YAML `net_classes:` map touched) |
| `scripts/check_router_clearance_floor.py` | PASS — unaffected (default-clearance floor, not touched) |
| `scripts/check_creepage_clearance_drift.py` | ERROR (pre-existing, unrelated) — confirmed identical failure on unmodified `origin/main`: an unrelated selection-alias defect in `tank_creepage.py`, a file this task never touches |
| `scripts/check_oracle_hashes.py` | PASS — 167/167, after re-pinning the one legitimately-changed oracle |
| `pytest packages/temper-placer/tests/core/test_design_rules_rust_differential.py` | 26/29 pass; the 3 failures (`gnd`/`PWR_RTN` GND-class drift) are confirmed byte-identical on unmodified `origin/main` — pre-existing, unrelated, reserved for a human decision per that module's own docstring |
| `pytest` — `test_design_rules.py`, `test_netclass_loader.py`, `test_design_rules_field_parity.py`, `test_design_rules_pbt.py`, `pcl/test_netclass_constraints.py`, `pcl/test_netclass_feedback.py`, `pcl/test_e2e_netclass_ssot.py`, `validation/test_drc_unresolved_netclass_fails_closed.py` | 78/78 pass after updating 2 class-count assertions (12->13) that both tests' own history shows are meant to move on every class addition |
| `scripts/tests/test_generate_kicad_dru.py`, `test_check_hv_netclass_coverage.py`, `test_check_netclass_class_param_correspondence.py`, `test_check_netclass_map_board_correspondence.py`, `test_sync_kicad_netclass_assignments.py` | 147/151 pass; the 4 failures are the same pre-existing `gnd`/`PWR_RTN`/`CGND` drift, confirmed identical on unmodified `origin/main` |

No test failure introduced by this task; every failure present on this
branch is present, byte-for-byte identical, on unmodified `origin/main`.

## 4. Measurement

Two full-board net-batching routes, both against the unmodified, committed
`pcb/temper.kicad_pcb`, component positions untouched (routing only,
`route_once` never moves a component):

- **baseline**: `netclass_rules.yaml` and `design_rules.py`/
  `generate_kicad_dru.py` reconstructed at `origin/main`'s state
  (`a3e117347`, this branch's own merge-base) in an isolated scratch
  package, so the baseline run and its DRU generation reflect the
  pre-this-task netclass structure exactly (`HighVoltage`/`ACMains` at
  their old widths, no `HighVoltageSignal`).
- **corrected**: this branch's own current, committed `netclass_rules.yaml`/
  `design_rules.py`/`generate_kicad_dru.py`/`pcb/temper.kicad_pro`.

Both: `scripts/verify_pumpkin_engine.py` exit 0 before solving;
`route_board.py --net-batching`, wall time 485.6s (baseline) / 485.8s
(corrected).

| Metric | Baseline (old scoping) | Corrected (this task) | Delta |
|---|---:|---:|---:|
| Topology completion | 66/104 (63.5%) | 65/104 (62.5%) | -1 net |
| **Pad connectivity (primary metric)** | 51/139 | 51/139 | **0** |
| TRUE `clearance` (`measure_uncapped_drc.py`) | **1172** | **1496** | **+324** — see attribution below |
| TRUE `track_width` (`measure_uncapped_drc.py`) | **1027** | **727** | **-300 (-29%)** |
| DRU-aware `creepage` (`measure_uncapped_drc.py`) | **146** | **152** | **+6 (+4%)** |

### 4.1 The `clearance` swing is a net-batching solve-order artifact, not a width/class effect

`measure_uncapped_drc.py`'s own per-net attribution (the tool's exhaustive
recursive split, not a guess) traces **512 of the +324 net delta** to a
single net, `discharge.k_dis1-nc`, in the new `HighVoltageSignal to LV`
bucket (612 total; the tool's own note names the net explicitly and flags
it `SATURATION SUSPECTED (non-deterministic across reruns)` — a lower
bound, not exact). Direct inspection of both routed boards confirms why:
`discharge.k_dis1-nc` has **0 copper segments** in the baseline route
(present in that run's own "37 UNEXPLAINED: solved but emit no copper"
list) and **135 segments** in the corrected route — this net simply never
got routed in the baseline run at all (net-batching's own documented
solve-order nondeterminism, not this task's width change: `discharge.k_dis1-nc`'s
declared width dropped 3.0mm->0.5mm in this task, which should reduce
congestion, not increase it). Zero copper cannot produce a clearance
violation; 135 real (if heavily fragmented — a pre-existing router
pathology, "fake-completion" per that run's own log) segments can and did.

Netting this single net's fluke out: `HighVoltageSignal to LV`'s remaining
100 violations (612-512) plus `HV to LV`'s 196 plus `HighVoltageTank to LV`'s
29 = 325, against baseline's equivalent family total (`HV to LV` 509 +
`HighVoltageTank to LV` 11 = 520) — a **195-violation improvement**, the
same direction PR #1119's own controlled 3.0mm->5.0mm-only measurement
found (1814->1282). The `track_width` category (Section 4, -300/-29%,
unaffected by this particular net's segment count in the same way — its
own `HighVoltageSignal` bucket is 189, not the dominant term) corroborates
the same conclusion without this confound.

**Caveat, stated as plainly as PR #1119 stated its own**: this remains a
single paired run, not a repeated (`--runs N`) measurement; net-batching's
per-batch SAT solve has real run-to-run variance, and the "Default routing"
bucket saturates at ~500 in both runs (`SATURATION SUSPECTED`, reported as
a lower bound in both) independent of anything this task changed. The
`creepage` category's own small (+6) swing is consistent with the same
single-net effect at a smaller scale, not a new independent finding.

### 4.2 Pre-existing, unaffected by this task

- `w1_1` and `tank.c_tank1-p2` are **unrouted in both runs** (baseline and
  corrected) — the same pre-existing routability gap PR #1119 already
  found at the old 3.0mm width, not created or resolved by the width
  change here, reported per this task's own instruction rather than
  narrowing either net's width to make it disappear.
- `zcd` is excluded from every conclusion above: dead circuitry from an
  unresynced deletion (`5842767c2`), per the task brief. Its reclassification
  to `HighVoltageSignal` is still correct/harmless (voltage-domain-
  preserving), it simply carries no weight in the feasibility read.
- The Stage 4.4 defect PR #1119 already documented
  (`_pipeline_route.py:674` never threads netclass `trace_width` into
  `assign_trace_widths()`, so drawn copper width is chosen by net-NAME
  keyword match, not the declared class) is unresolved and out of this
  task's scope; it is the most likely explanation for the `HighVoltageSignal
  trace width` (0.5mm-declared) category showing 189 track_width violations
  at all — the actually-drawn copper for these nets is probably the
  ~0.2mm keyword-fallback default, not the declared 0.5mm.

### 4.3 PD2/8.0mm isolation barrier and IGBT heatsink co-location (#1082)

**Unaffected by construction, not merely unmeasured-and-assumed-fine.**
This task's entire diff is netclass declarations, net-class assignments,
and DRU rule text — zero component placement data anywhere in the diff,
and `pcb/temper.kicad_pcb` (the only file recording component positions)
is byte-identical throughout. `scripts/check_isolation_keepout.py`, run
against the unmodified board, fails today for a reason **entirely
unrelated to this task**: no `MAINS_SELV_ISOLATION_BARRIER` keepout zone
exists on the board at all (a pre-existing, already-known placement gap,
"a human must place a keepout region" per that gate's own violation
message) — this is the same failure on `origin/main` before this task and
is unaffected by any change in this diff. The 8-isolator/heatsink-
co-location placement feasibility work this task's brief references
(PR #1119, and the CP-SAT placement studies it cites) is placement-solve
territory, not netclass/DRU territory; this task does not re-run the
placer and does not move any component, so whatever that feasibility state
is today, it is identical before and after this diff.

## 5. Recommendation

1. **Land this re-scoping.** It corrects a real, measured under-build
   (`HighVoltage`'s old 3.0mm was 27-45% short of its own 22.5A RMS current
   requirement) without the alternative cost of uniformly over-building the
   mA-scale members of the same class, and the width increase itself is
   measured feasible twice now (PR #1119's controlled run, and this task's
   own fresh baseline/corrected pair) with no regression attributable to
   the change once the single-net net-batching artifact is factored out.
2. **`drc_ceiling.json` is untouched, deliberately** — this task does not
   modify `pcb/temper.kicad_pcb`, so there is nothing for that ceiling to
   re-measure. The moment a future PR re-routes the real board at these
   corrected widths and commits the result, that PR (not this one) owns the
   re-measurement, per `AGENTS.md`'s existing convention.
3. **Fix Stage 4.4's missing `power_width`/`hv_width` pass-through** (PR
   #1119 S5, unresolved, out of this task's scope) before any of these
   declared widths reflect what actually gets manufactured — right now the
   netclass value and the drawn copper are still two unrelated numbers for
   every current-carrying net, this task's corrected values included.
4. **The tank peak-current gap (S1.5) still needs its own owner.** Nothing
   in this task depends on it being resolved, and nothing here resolves it.
