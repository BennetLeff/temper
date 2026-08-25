<!-- provenance: commit=73c8db9aa517366d42d9645d3be8f84fe6198f10 dirty=UNKNOWN -->
analysis/track-width-violations, based on origin/main cc732df2b, merged with
origin/feat/uncapped-drc-measurement (68bf5c31f/9b14c7d5d, PR #1111) and
origin/fix/dru-rule-precedence (11b344c65.., PR #1110) to obtain the exhaustive-
partition tooling and the corrected .kicad_dru generator -- neither PR touches
pcb/temper.kicad_pcb or pcb/temper.kicad_pro (verified: `git diff main...<branch>
--stat` for both, checked before merging). pcb/temper.kicad_pcb sha256=
6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64, pcb/temper.kicad_pro
sha256=f2d90755af04fea40357be3ba2ef94368a01b1afc34c450b42fad0b9e15a51ac -- BYTE-IDENTICAL
to the board #1110 and #1111 measured, and unchanged by this document (`git status
--porcelain pcb/` clean throughout). power_pcb_dataset/drc_ceiling.json is read-only
here, per the task's own instruction ("a fourth re-derivation is pending"). kicad-cli
10.0.5. No subagents were dispatched (single-agent task, per instruction). Raw
itemized violation data (all 490 rows: net, layer, actual/required width, length,
position, uuid) preserved alongside this document as
docs/evidence/2026-08-12-track-width-violations.csv. -->

# `track_width` = 490 (reported: 199): ten nets, all severely undersized, two of them the mains input current path

**Verdict up front.**

1. **All 490 violations trace to exactly 10 real nets**, split across exactly two
   netclasses: `HighVoltage` (341, on 7 nets) and `Power` (149, on 3 nets). No other
   netclass (`HighVoltageTank`, `ACMains`, `GND`, `HighCurrent`, `GateDriveHV`,
   `GateDriveSELV`, `Signal`, `HighSpeed`, `FinePitch`) contributes anything —
   reproduced independently in this session (matches PR #1111 sec 5.2 exactly).
2. **None of the 490 is a marginal violation.** Every single one of the 10 nets
   measures between **8.3% and 50.8% of its netclass's required minimum width** —
   i.e. every violating segment is 2x to 12x too narrow, not 5%-under-the-bar DFM
   noise (sec 3).
3. **Two of the ten nets carry the appliance's actual mains input current, and are
   the most severe violations found: 8.3% and 16.9% of their required width.**
   `w1_2` (the common-mode-choke output that feeds both the inrush-limiting NTC and
   the bypass relay — i.e. 100% of the device's AC input current flows through it
   once running) is routed at **0.25mm** against a required **3.0mm** (91.7% short).
   `power_in.ntc-no` (the bypass-relay contact that carries the same current after
   the NTC is shorted out) is routed at **0.508mm** against the same **3.0mm**
   (83.1% short). This board's own IPC-2221B trace-width methodology
   (`docs/hardware/TRACE_WIDTH_CALCULATIONS.md`) computes an ampacity of roughly
   **1–4A** for copper this narrow at 2oz/40°C-rise — against a **15A design
   current, 16A fuse, and 20A-rated bypass relay contact** on this exact path
   (`elec/src/modules.ato`, `elec/src/constraints.ato`). **This is a real heating
   and fusing hazard on the mains input of a mains-powered appliance**, not a
   cosmetic DFM nit (sec 4).
4. **This is the same defect already diagnosed and documented once before, now
   larger.** `docs/evidence/2026-08-11-track-width-shorting-root-cause.md`
   (2026-08-11) traced the then-199-capped `track_width` count to one root cause:
   the router's Stage 4.4 width assignment (`assign_trace_widths` /
   `temper_geometry::determine_trace_width`) picks a net's copper width from a
   **3-bucket keyword match on the net's own name string**, completely independent
   of `design_rules.TEMPER_NET_CLASSES` — the same table the DRU generator and the
   DRC gate actually enforce. That defect was never fixed (disposition in that
   document: "no code change lands," see its sec 3). Confirmed still present and
   still the operative mechanism today (sec 5): every violating segment on every
   one of the 10 nets sits at one of only **three fixed magic-number widths**
   (0.25mm / 0.3048mm / 0.508mm), uniformly across 100% of that net's segments,
   regardless of which real netclass (0.4mm–3.0mm required) the net belongs to. Two
   of those three numbers (0.508mm, 0.3048mm = 0.508 × 0.6) are the function's own
   hardcoded literal defaults, verified byte-exact by direct call. **Grep-confirmed:
   there is no code path in the router that reads a net's real per-class
   `trace_width` when it assigns the width of the copper it lays** — the one place
   in the whole placer/router tree that does read `.trace_width` from the real
   class table (`constraints_design_rules.py`'s `get_track_width`) is wired only
   into differential-pair clearance arithmetic, never into what gets written to a
   `(segment ... (width ...))` line (sec 5). **This is one defect, not 490
   independent ones** — exactly the shape the task asked to check for.
5. **The board grew from 199 (capped, 9 nets, 2026-08-11) to 490 (true, 10 nets,
   today) partly because today's own netclass-parameter-reconciliation fix is
   correct and exposed more of the same pre-existing bug**, not because new copper
   was drawn: `Power`'s DRU-enforced minimum was corrected today from 0.5mm to the
   correct 1.0mm (`docs/evidence/2026-08-12-netclass-param-reconciliation.md`);
   that alone turns 38 previously-compliant `power_in.bypass_relay-coil2` segments
   (routed at 0.508mm, ≥ the old wrong 0.5mm floor) into new violations (sec 6).
   The rest of the growth is purely the reporting-cap effect PR #1111 already
   established board-wide.
6. **100% of the 490 is router-pipeline output; there is no separate "pre-existing,
   hand-drawn copper" category to net out.** `pcb/temper.kicad_pcb`'s own header
   declares `(generator kiutils)` — the whole file, all 2,290 segments and 48 vias,
   is machine-exported by the placer/router toolchain, not hand-edited in the KiCad
   GUI. Stripping every segment and via and re-measuring (the same technique PR
   #1110 used for `clearance`) drops `track_width` to **0** and reproduces #1110's
   `clearance 48 = 48` exactly on the same stripped board, confirming the harness
   and the stripping method agree with the prior measurement (sec 7).

---

## 1. Method

Reused PR #1111's `scripts/measure_uncapped_drc.py` machinery directly (imported,
not reimplemented) against the fixed `.kicad_dru` generator from PR #1110
(`fix/dru-rule-precedence`, merged into this task's own worktree branch — see the
provenance header). First reproduced the exhaustive `track_width` total:

```bash
uv run --all-packages python scripts/measure_uncapped_drc.py dru-category track_width \
  --dru-generator scripts/generate_kicad_dru.py \
  --scratch-dir <scratch>/tw --json <scratch>/tw_result.json
```

```
TRUE track_width: 490
HighVoltage trace width = 341  [split on real net names of class 'HighVoltage' (14 nets)]
  HighVoltage trace width [HighVoltage 7/14] = 146
  HighVoltage trace width [HighVoltage 7/14] = 195  [further split]
    ... [HighVoltage 3/7] = 99
    ... [HighVoltage 4/7] = 96
Power trace width = 149
(every other net class = 0)
```

Exact match to PR #1111 sec 5.2 (490 = 341 + 149; 341 = 146 + 99 + 96), independently
reproduced in this session, not carried over unverified.

`measure_category_exhaustive`'s own bisection only preserves **counts**, not the
underlying kicad-cli violation records — sec 5.2's per-rule bisection already proved
each of the three `HighVoltage` sub-groups (146, 99, 96) and the whole `Power` class
(149) sit **under** the 199 `ERROR_LIMIT` cap on their own (each below the tool's own
`safe_ceiling = 179` threshold, and none flagged non-deterministic). That means a
single, non-capped kicad-cli run against each of those four already-proven-exhaustive
groups returns kicad-cli's **complete, untruncated** violation JSON for that group —
no further splitting needed to get itemized data. Ran exactly those four isolation
DRUs (same `isolation_dru()` helper PR #1111 uses, same net-name pools its own
bisection produced) and parsed every violation's `description` (`"...min width X mm;
actual Y mm)"`) and its item's `description` (`"Track [<net>] on <layer>, length
<mm>"`) for all 490 rows:

```bash
uv run --all-packages python - <<'PY'
# builds the 4 isolation DRUs (HighVoltage split into the same 3 net-name pools
# measure_category_exhaustive's bisection produced: {+15V_LS,+170V_BUS,DC_BUS_RTN,
# PWR_RTN,SW_NODE,a,discharge.k_dis1-nc}, {discharge.k_dis2-nc,hb.power_loop.q_high-g,
# power_in.ntc-no}, {tank-out,w1_1,w1_2,zcd}; Power as the full 9-net class), runs
# kicad-cli once per group, and parses every violation record.
PY
```

Totals reproduced exactly (146+99+96+149 = 490); full script and raw JSON preserved
in this session's scratch output; the flattened, itemized result is
`docs/evidence/2026-08-12-track-width-violations.csv` (490 rows: netclass, net,
layer, required/actual width, segment length, position, uuid).

---

## 2. Breakdown by netclass and net

| netclass | required min | net | violations | actual width (mm) | % of required |
|---|---:|---|---:|---:|---:|
| **HighVoltage** | 3.0mm | `discharge.k_dis1-nc` | 104 | 0.25 | 8.3% |
| HighVoltage | 3.0mm | `hb.power_loop.q_high-g` | 68 | 0.508 | 16.9% |
| HighVoltage | 3.0mm | `zcd` | 55 | 0.25 | 8.3% |
| HighVoltage | 3.0mm | `a` | 42 | 0.25 | 8.3% |
| HighVoltage | 3.0mm | **`w1_2`** | 41 | 0.25 | **8.3%** |
| HighVoltage | 3.0mm | **`power_in.ntc-no`** | 31 | 0.508 | **16.9%** |
| HighVoltage subtotal | | | **341** | | |
| **Power** | 1.0mm | `discharge.k_dis1-coil2` | 47 | 0.25 | 25.0% |
| Power | 1.0mm | `discharge.k_dis1-coil1` | 39 | 0.3048 | 30.5% |
| Power | 1.0mm | `power_in.bypass_relay-coil2` | 38 | 0.508 | 50.8% |
| Power | 1.0mm | `discharge.k_dis2-coil1` | 25 | 0.25 | 25.0% |
| Power subtotal | | | **149** | | |
| **TOTAL** | | | **490** | | |

Every other net class present on the board (`HighVoltageTank`, `ACMains`, `GND`,
`HighCurrent`, `GateDriveHV`, `GateDriveSELV`, `Signal`, `HighSpeed`, `FinePitch`)
contributes **zero** — confirmed by isolating each rule directly, not merely inferred
from the total.

**Bold** = the two mains-current-carrying nets, see sec 4.

Cross-checked against the real board directly (independent of kicad-cli): every one
of these 10 nets has **100% of its own `segment` entries at the single width shown**
— e.g. all 104 `discharge.k_dis1-nc` segments are 0.25mm, all 68
`hb.power_loop.q_high-g` segments are 0.508mm. No net in this list has a mix of
compliant and non-compliant segments. Layer split: 292 on `F.Cu`, 198 on `B.Cu`.

**Every other HighVoltage/Power net on the board has zero `segment` entries at all**
(`+15V_LS`, `+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `SW_NODE`, `w1_1`, `tank-out`,
`+15V`, `+3V3`, `vcc`, `V_BUS_SENSE`, `discharge.k_dis1-coil1`†,
`discharge.k_dis2-nc`, `power_in.bypass_relay-coil1`) — these are compliant only in
the vacuous sense that they carry no discrete `Track` copper at all (routed as zone
pour instead, consistent with `HighVoltage`/`GND`'s `routing_strategy:
plane_required`/`plane_preferred`), not because the router sized a track correctly
for them. (†note: `discharge.k_dis1-coil1` *does* have 39 segments and *is* in the
violation table above — the zero-segment list above is the sibling net
`power_in.bypass_relay-coil1`, not a duplicate; kept both spelled out to avoid a
copy-paste ambiguity between similarly-named coil nets.)

---

## 3. Shortfall distribution — how short is each?

```
Net                              netclass   required  actual   %-of-min  short-by
discharge.k_dis1-nc              HighVoltage  3.000   0.2500     8.3%     91.7%
zcd                               HighVoltage  3.000   0.2500     8.3%     91.7%
a                                 HighVoltage  3.000   0.2500     8.3%     91.7%
w1_2                              HighVoltage  3.000   0.2500     8.3%     91.7%
hb.power_loop.q_high-g            HighVoltage  3.000   0.5080    16.9%     83.1%
power_in.ntc-no                   HighVoltage  3.000   0.5080    16.9%     83.1%
discharge.k_dis1-coil2            Power        1.000   0.2500    25.0%     75.0%
discharge.k_dis2-coil1            Power        1.000   0.2500    25.0%     75.0%
discharge.k_dis1-coil1            Power        1.000   0.3048    30.5%     69.5%
power_in.bypass_relay-coil2       Power        1.000   0.5080    50.8%     49.2%
```

**None of the 490 is a 5%-under-the-bar case.** The mildest shortfall on the whole
board is `power_in.bypass_relay-coil2` at 49.2% short (routed at just over half its
required width); the worst is 91.7% short (routed at roughly 1/12th the required
width). The distribution clusters at exactly **three** values (0.25mm, 0.3048mm,
0.508mm) because — see sec 5 — the router assigns one of three fixed magic numbers
per net, not a continuum; the "% of required" spread comes entirely from which
netclass (1.0mm vs 3.0mm minimum) each net happens to belong to, not from any
variation in what the router actually drew.

---

## 4. Which of the 10 nets carry real current — the mains-input hazard

Cross-referenced every violating net against `elec/src/modules.ato` (`PowerInput`,
`BusDischarge`) and `elec/src/constraints.ato`:

| net | role | actual current path | design current | trace at fault |
|---|---|---|---|---|
| **`w1_2`** | CMC (common-mode choke) line-side output → feeds `ntc.p1` (inrush limiter) **and** `bypass_relay.COM` | **100% of the device's AC mains input current**, both during inrush (through the NTC) and in steady-state (through the bypass relay once closed) | `ACMainsConstraints.i_max = 15A`; `fuse.current_rating = 16A`; `cmc.current_rating >= 15A` (assert) | **0.25mm vs 3.0mm required (8.3%)** |
| **`power_in.ntc-no`** | `bypass_relay.NO` → `d1.A` (bridge rectifier input) | Same mains input current, after the NTC is bypassed | `bypass_relay.contact_current = 20A` | **0.508mm vs 3.0mm required (16.9%)** |
| `discharge.k_dis1-nc` | `k_dis1` (bus discharge relay) NC contact, in series with `r_dis1a`+`r_dis1b` (≈7.8kΩ total) across one half-bus (170V) | Resistor-limited discharge current, ≈170V / 7.8kΩ ≈ **22mA** | `k_dis1.contact_current = 10A` (switching rating, not actual duty here) | 0.25mm vs 3.0mm (8.3%) — narrow, but current-limited by design; the width shortfall is a mechanical/creepage-robustness concern for a 445.9mm-long HV-domain run, not a heating one |
| `hb.power_loop.q_high-g` | Q_high (half-bridge high-side switch) gate node, one resistor from `GATE_HS`; classed `HighVoltage` because it floats on `SW_NODE`, not for current | Gate-drive charge/discharge pulses only (µs-scale, low RMS) | n/a (signal, not power) | 0.508mm vs 3.0mm (16.9%) — an isolation-domain concern, not a fusing one |
| `zcd`, `a` | Zero-cross-detection divider tap / opto-isolator LED anode | Resistor-set µA–mA sensing/LED current | n/a | Isolation-domain concern only |
| `discharge.k_dis1-coil1/coil2`, `discharge.k_dis2-coil1`, `power_in.bypass_relay-coil2` | Relay actuation coils, driven through `q_relay_drv` (AO3400A) | `power_15v.vcc` (12V rail) coil current — Omron G4A ≈ 75mA per `modules.ato`'s own comment ("RELAY_CTRL ... cannot drive the 75mA/12V coil directly"); Schrack RT314012 coil ≈ 12V/360Ω ≈ 33mA | n/a | Low-current; undersized relative to `Power` class but not a heating hazard at these currents |

**`w1_2` and `power_in.ntc-no` are the two nets that matter most.** They are
literally the copper the appliance's entire input current flows through. Using this
board's own trace-width methodology
(`docs/hardware/TRACE_WIDTH_CALCULATIONS.md` sec 2, IPC-2221B, `I = k × ΔT^0.44 ×
A^0.725`, `k=0.048` external, this board's own stated 2oz/70µm outer copper and
40°C-rise budget for power paths):

```
w1_2:            0.25mm (9.84mil) × 2oz (2.74mil) → A = 26.96 mils²
                 I = 0.048 × 40^0.44 × 26.96^0.725 ≈ 2.4A ampacity

power_in.ntc-no: 0.508mm (20mil) × 2oz (2.74mil)  → A = 54.8 mils²
                 I = 0.048 × 40^0.44 × 54.8^0.725  ≈ 4.0A ampacity
```

against a **15A design current / 16A fuse / 20A relay contact rating** on the exact
same path — a **4–8× ampacity deficit** even under the board's own generous 2oz/40°C
assumptions (a 1oz assumption, which the board's inner layers actually use, roughly
halves both figures again). This board's own methodology doc independently derives
**5.0mm** as its recommended minimum for a comparable 22A/2oz/40°C HighVoltage power
path (sec 3.1) — `w1_2` is missing not just the class's 3.0mm bar but the project's
own more conservative 5.0mm recommendation by an even larger margin.

**This is a real heating-and-fusing hazard, not a cosmetic DFM nit,** on the AC mains
input path of a mains-powered induction cooktop. It is flagged prominently per the
task's own instruction.

---

## 5. Same defect class as the router/DRC divergence found earlier today — confirmed

### 5.1 The mechanism, re-verified against today's board

`docs/evidence/2026-08-11-track-width-shorting-root-cause.md` (one day prior) already
diagnosed this exact mechanism for a smaller (9-net, 199-capped) instance of the same
problem: Stage 4.4's `assign_trace_widths`
(`packages/temper-placer/src/temper_placer/router_v6/trace_width_assignment.py`)
delegates to `temper_geometry::determine_trace_width`
(`packages/temper-geometry/src/trace_width_assignment.rs:59-82`), which classifies a
net's width by a **keyword match on the net's own name string** — not by looking up
`design_rules.TEMPER_NET_CLASSES[net_class].trace_width`:

```rust
if kw_boundary_match(name_upper, ["AC_", "HV_", "HIGH_VOLTAGE"]) { return hv_width }
if kw_boundary_match(name_upper, ["GND","VCC","VDD","VSS","POWER"]) || starts_with('+') { return power_width }
if kw_boundary_match(name_upper, ["GATE","DRIVE"]) { return power_width * 0.6 }
return default_width
```

The single call site (`router_v6/_pipeline_route.py:674-677`) threads only
`default_width=pcb.design_rules.default_trace_width_mm` (a flat 0.2mm scalar);
`power_width` and `hv_width` are **left at the function's own hardcoded literal
defaults** (`trace_width_assignment.py:72-74`: `power_width: float = 0.508`,
`hv_width: float = 0.635`) — never sourced from `TEMPER_NET_CLASSES` at all, for
any net, regardless of its real netclass's 0.4mm–3.0mm requirement.

### 5.2 Confirmed still the operative mechanism today, not superseded

Called `determine_trace_width_py` directly (same PyO3 entry point Stage 4.4 uses)
against every one of the 10 violating nets, with the exact parameters the real call
site uses:

```python
>>> import temper_geometry as tg
>>> tg.determine_trace_width_py("power_in.bypass_relay-coil2", 0.2, 0.508, 0.635)
(0.508, 'Power net requires wider trace for current capacity')   # matches board exactly
>>> tg.determine_trace_width_py("power_in.ntc-no", 0.2, 0.508, 0.635)
(0.508, 'Power net requires wider trace for current capacity')   # matches board exactly
```

Every measured on-board width in the "Power" keyword bucket (0.508mm) matches this
call exactly. The remaining widths on the board (0.25mm, 0.3048mm) do not reproduce
byte-exact from *today's* `default_trace_width_mm=0.2` input, indicating the
committed copper was generated under a still-earlier parameterization of the same
keyword-bucket mechanism (this repo carries at least two other independently
hardcoded `default_trace_width = 0.25` literals —
`packages/temper-placer/src/temper_placer/io/_parse_nets.py:133` and
`io/kicad_exporter.py:390` — plausibly the actual source of the 0.25mm/0.3048mm
figures on this specific board revision). **Which exact literal produced which
number is a secondary detail; the load-bearing fact — that every one of these
widths is a small, fixed, keyword-or-path-selected magic number with no relationship
to the net's real class minimum — holds regardless of which of the pipeline's several
independent hardcoded defaults is the specific source.**

### 5.3 Grep-confirmed: the router never reads the real per-class width when laying copper

Searched every `.trace_width` read in `packages/temper-placer/src/temper_placer/`:

- `router_v6/constraints_design_rules.py:277` (`get_track_width`) — **the only place
  in the router that correctly looks up a net's real class `trace_width`** — but it
  is wired exclusively into `add_differential_pair`'s clearance-budget arithmetic
  (`constraints_design_rules.py:363`), never into what width gets written to a
  segment. Confirmed by its only caller: a differential-pair helper, not the
  Stage 4.4 width-assignment path.
- `router_v6/_adapter_convert.py:1041`, `placer/cp_sat/_loop_routing.py:43` — both
  inside f-string debug/log messages, not consumed for sizing copper.
- `core/design_rules.py`, `core/netclass_rules_gen.py` — the table definitions
  themselves.
- `regression/drc_ratchet.py` — DRC-side, not routing-side.

**No code path in the placer/router pipeline reads `TEMPER_NET_CLASSES[cls].trace_width`
when assigning the width of copper it actually lays.** The DRU generator
(`scripts/generate_kicad_dru.py`) and the DRC gate read it correctly; the router that
produces the copper the DRC gate checks does not. This is the exact shape the task
flagged as "the router's own model diverged from the DRC model" for clearance
earlier today (0.15mm reserved against a 0.2mm bar; `.clearance_mm`-only reads with
per-pair tables unused) — **track width is a third instance of the identical
systemic pattern, not a new, independent defect.** `assign_trace_widths` runs in
Stage 4.4, strictly *after* Stage 4's A* pathfinding has already committed to a
centerline with zero clearance-margin corridor reservation
(`docs/evidence/2026-08-11-track-width-shorting-root-cause.md` sec 3) — so, as that
document already found and this session reconfirms, patching the width label alone
(without also making Stage 2/4's corridor sizing width-and-class-aware) is not safe
to ship standalone: it trades ~490 `track_width` violations for a larger `clearance`/
`creepage`/`hole_clearance`/`solder_mask_bridge` regression, because the corridor
these nets were actually routed through was only ever cleared for their current
(wrong) width. **No code change is made by this document** — the task was to
characterize, and per its own instruction, a router-internals fix (implementing the
documented-but-unbuilt `wide_trace` routing strategy, or otherwise making Stage 2/4
class-and-width-aware) is out of this task's scope.

*Secondary, unexplained anomaly (does not affect the 490 count, flagged for
completeness): `GATE_LS` (net id 8, `GateDriveHV` class, required 0.4mm) has 39
segments on the board at 0.3048mm — genuinely narrower than its class minimum — but
did not appear in `track_width` violations under any isolation probe tried in this
session, including a maximally permissive `(min 10mm)` sanity check that should have
caught it trivially. It does appear in `clearance`/`shorting_items`/
`silk_over_copper`/`solder_mask_bridge` checks, confirming kicad-cli evaluates this
net's copper generally. Whatever suppresses it from `track_width` specifically was
not identified in the time available and does not change any total in this document
— `GateDriveHV`'s true `track_width` contribution is measured at 0 by every method
tried, consistently.*

---

## 6. Why 490 now and not before — reporting cap vs. today's own netclass fix

Two separate effects compound here:

1. **The reporting-cap effect** (PR #1111, board-wide): `track_width`'s true count
   has been ≥199 (and specifically 490, on this exact committed board) for as long
   as the underlying router bug (sec 5) and the current netclass assignments have
   coexisted — kicad-cli's `ERROR_LIMIT=199` simply never let more than 199 through
   in any single report, so 291 of the 490 were never visible in any report from any
   prior CI run.
2. **Today's own correction added new true violations.**
   `docs/evidence/2026-08-12-netclass-param-reconciliation.md` fixed `Power`'s
   `trace_width` from an incorrect 0.5mm (a copy of `HighCurrent`'s figure) to the
   correct 1.0mm (matching `pcb/temper.kicad_pro`, `elec/src/constraints.ato`, and
   `docs/specs/NET_CLASS_SPECIFICATION.md`). Under the old, wrong 0.5mm floor, the
   38 `power_in.bypass_relay-coil2` segments (routed at 0.508mm) were **compliant**
   (0.508 ≥ 0.5); under the corrected, real 1.0mm floor they are violations. The
   other 111 `Power`-class violations (72 at 0.25mm, 39 at 0.3048mm — both nets)
   already violated the old 0.5mm floor too, so they were always true violations,
   just invisible behind the reporting cap alongside the rest.

Net effect: this session's fix to `Power`'s parameter correctness is itself correct
and not implicated in causing a hazard — it only makes an existing hazard (the
router's keyword-bucket width bug, sec 5) visible for one more net that the cap was
already hiding everything else behind.

---

## 7. Routed vs. pre-existing copper

The task asked to separate router-authored copper from anything that predates the
router, using the same strip-and-remeasure technique PR #1110 used for `clearance`.

**There is nothing to separate.** `pcb/temper.kicad_pcb`'s own header:

```
(kicad_pcb (version 20211014) (generator kiutils)
```

`kiutils` is this repo's own board-export library
(`packages/temper-placer/src/temper_placer/io/kicad_exporter.py` and siblings) — the
entire committed board file, every one of its 2,290 `segment` entries and 48 `via`
entries, is machine-generated pipeline output, not a hand-edited KiCad-GUI board with
a router-added layer on top of manually-drawn copper. There is no second, independent
"pre-existing" copper source on this board to net the 490 against.

Confirmed by measurement anyway, exactly as instructed:

```bash
# Strip all 2,290 segments and 48 vias from a scratch copy (never touches the
# committed file), regenerate the current .kicad_dru, re-run DRC:
```

| category | stripped-board result |
|---|---:|
| `track_width` | **0** |
| `clearance` | **48** |

`clearance = 48` on the stripped board reproduces PR #1110's own `48 = 48` result
**exactly**, on the identical stripped-board technique, cross-validating this
session's harness against that prior, independently-run measurement.
`track_width = 0` is the expected, trivial confirmation that the category fires only
on `Track` items — with no tracks left, `track_width`'s true count is 490 routed / 0
pre-existing / 490 total: **100% of the 490 is attributable to router-pipeline
output**, because 100% of the board's copper is router-pipeline output.

---

## 8. What this document does not do

- Does not modify `pcb/temper.kicad_pcb` or `pcb/temper.kicad_pro` (verified clean
  throughout; hashes above match #1110/#1111's).
- Does not modify `power_pcb_dataset/drc_ceiling.json` — read only. Per PR #1111 sec
  7, `track_width: 199` in that file already sits exactly on `ERROR_LIMIT` and is a
  gate that cannot fire; this document adds the netclass/net breakdown and the
  current-carrying safety analysis PR #1111 flagged as not yet done, but leaves the
  actual ceiling number to the pending re-derivation task.
- Does not fix the router's width-assignment bug (sec 5) — `docs/evidence/
  2026-08-11-track-width-shorting-root-cause.md` already measured that the
  mechanical fix, shipped alone, trades ~199 (now ~490) `track_width` violations for
  a larger regression elsewhere (`clearance +132`, `creepage +32`,
  `hole_clearance +38`, `solder_mask_bridge +45` in that document's own controlled
  experiment) because Stage 2/4's corridor reservation was never sized for the
  correct width. The real fix (implementing the documented-but-unbuilt `wide_trace`
  routing strategy, or otherwise making corridor reservation class-and-width-aware)
  is router-internals work, explicitly out of this task's scope, same disposition as
  that prior document reached.

---

## 9. Reproduction

```bash
git worktree add <path> -b analysis/track-width-violations origin/main
cd <path>
git merge origin/feat/uncapped-drc-measurement origin/fix/dru-rule-precedence  # PRs #1111, #1110

export UNCAPPED_DRC_REPO_ROOT="$(pwd)"
<venv>/bin/python scripts/measure_uncapped_drc.py dru-category track_width \
  --dru-generator scripts/generate_kicad_dru.py \
  --scratch-dir /tmp/scratch/tw --json /tmp/scratch/tw_result.json
# TRUE track_width: 490

# Itemized breakdown (sec 1's script) -> docs/evidence/2026-08-12-track-width-violations.csv

# Strip-and-remeasure (sec 7):
<venv>/bin/python -c "
import re
text = open('pcb/temper.kicad_pcb').read()
lines = text.splitlines(keepends=True)
stripped = [l for l in lines if '(segment ' not in l and not re.match(r'\s*\(via ', l)]
open('/tmp/scratch/stripped.kicad_pcb', 'w').writelines(stripped)
"
# then run the same dru-category / physical-category harness against the stripped copy

# Router-width defect (sec 5):
<venv>/bin/python -c "
import temper_geometry as tg
print(tg.determine_trace_width_py('power_in.ntc-no', 0.2, 0.508, 0.635))
"
grep -rn '\.trace_width\b' packages/temper-placer/src/temper_placer/  # confirms get_track_width is the only real-table reader, and is orphaned from routing
```

Sources: `docs/evidence/2026-08-12-uncapped-drc-measurement.md` (PR #1111);
`docs/evidence/2026-08-12-dru-rule-precedence.md` (PR #1110); `docs/evidence/
2026-08-11-track-width-shorting-root-cause.md`; `docs/evidence/
2026-08-12-netclass-param-reconciliation.md`; `packages/temper-placer/src/
temper_placer/core/design_rules.py`; `packages/temper-geometry/src/
trace_width_assignment.rs`; `packages/temper-placer/src/temper_placer/router_v6/
trace_width_assignment.py`, `_pipeline_route.py`, `constraints_design_rules.py`;
`elec/src/modules.ato`, `elec/src/constraints.ato`; `docs/hardware/
TRACE_WIDTH_CALCULATIONS.md`; `pcb/temper.kicad_pcb`, `pcb/temper.kicad_pro`
(read-only throughout).
