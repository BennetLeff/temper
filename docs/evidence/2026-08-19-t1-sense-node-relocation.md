<!-- provenance: branch analysis/t1-sense-node-relocation, based on origin/main tip eb5022510.
     pcb/temper.kicad_pcb sha256 = 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b,
     verified identical before and after this session -- never opened for write.
     elec/**/*.ato read only. No clearance, creepage, copper-weight, loop-area, ampacity or
     DRU threshold was changed or proposed for change. power_pcb_dataset/drc_ceiling.json
     untouched. No `_*_py_oracle.py` oracle deleted or re-pinned. No manufacturer, lab or
     certification body was contacted.
     Inputs read: bd39eb10a (per-pairing creepage implementation) and 0cbc04248 (Table 17/18
     row determination), both on origin/feat/per-pairing-creepage-derivation.
     ENVIRONMENT NOTE, per instruction: this document is prose. Every geometric figure in it
     was computed by hand from the pad table printed verbatim out of pcb/temper.kicad_pcb with
     grep/awk. No Python was run, no compiled extension was loaded, no placer or DRC job was
     started, so `make venv-isolate` was deliberately skipped and no memory was competed for. -->

# T1's sensing node: the function does not need to move, because `tank-out` was never at tank potential

## Verdict up front

**The measurand does not have to move, and no alternative node is needed.**

T1's failing pad is `tank-out`. `tank-out` is the node between the coil's far terminal and
T1's own primary winding. It is separated from `PWR_RTN` by exactly one thing — the CST3015
primary, a single turn whose voltage the part's own volt-time rating caps at **≤ 0.600 V** at
47 kHz, and whose calculated drop at the OCP-01 trip point is **~30 mV**. It is a two-pad net.
Nothing else touches it.

`PWR_RTN` is declared `MAINS`, 120 V r.m.s., 60 Hz → **`MAINS↔SELV` = 4.8 mm**.

So the barrier crossing at T1's primary is, physically, a 120 V crossing standing off 9.100 mm.

The clearest way to see it is inside T1's own footprint. Its two primary pads sit at **identical
9.100 mm** from the secondary. One passes with 4.3 mm to spare; the other fails by ≥10.9 mm:

| T1 pad pair | nets | declared pairing | required | measured | verdict |
|---|---|---|---:|---:|---|
| pad 2 ↔ pad 3 | `PWR_RTN` ↔ `I_SENSE` | `MAINS↔SELV` | 4.8 | **9.100** | PASS (+4.3) |
| pad 1 ↔ pad 4 | `tank-out` ↔ `gnd` | `SELV↔TANK` | ≥20.0, indeterminate | **9.100** | **FAIL (≥−10.9)** |

Same package, same copper, same 9.100 mm, opposite verdicts — decided entirely by which side
of the sense winding the group boundary was drawn.

**This is not a proposal to lower a threshold.** 4.8 mm and 20.0 mm are both correctly derived
from their declared inputs, and neither should change. The claim here is narrower and purely
factual: **the declared working-voltage input for `tank-out` is not supported by the document
it cites.** Every one of the 20 places the 570.5 V r.m.s. figure appears in
`docs/evidence/2026-08-12-hv-clearance-adequacy.md` measures **`tank.c_tank1-p2`** — the
capacitor↔coil junction, the *other* net in the `TANK` group. `tank-out` appears there four
times, and never once carrying a voltage. **No document in this repository has ever measured or
derived the working voltage of `tank-out`.** §3.4 shows the point at which that gap was
recorded and then closed against a different node.

**What the owner must decide** is not an architecture. It is whether a one-turn sense winding
carrying ≤0.6 V constitutes a group boundary. §6 names the single bench measurement that
settles it — the same measurement `elec/insulation_manifest.yaml` already flags as missing.

---

## 1. What T1 senses, and who consumes it

Traced from source, not from netclass labels.

| property | value | source |
|---|---|---|
| Sensor | Coilcraft **CST3015-100ED**, 1:100, 88 A sensed, 5000 V r.m.s. reinforced | `elec/src/components.ato:124-158` |
| Measurand | **Instantaneous tank return current**, bipolar, unrectified, unaveraged | `elec/src/main.ato:823-824` |
| Burden | 4.99 Ω ±1% → 49.9 mV per primary amp | `elec/src/modules.ato:1703-1706` |
| Bandwidth | 100 nF C0G across burden → 319 kHz corner; ~1 % attenuation at the 47 kHz fundamental | `modules.ato:1721-1726`; `docs/evidence/2026-08-15-ocp-threshold-decision.md` §1 |
| Bias | 1.65 V mid-rail, 10 k/10 k, so the ADC sees a bipolar waveform on a pedestal | `modules.ato:1738-1753` |

`I_SENSE` fans out to exactly **two** consumers:

1. **OCP-01 hardware comparator** (TLV3201, ref 2.4925 V) — trips at **50.1 A peak nominal**,
   worst case 48.77–51.16 A, acceptance window **45–55 A peak, <1 µs, latched**
   (`modules.ato:1662-1719`, `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.1). This is the fast path,
   and its actuator is `SHUTDOWN → UCC21550 DIS` (`main.ato:898`).
2. **ESP32-S3 ADC** on GPIO1 (`main.ato:833-834`, `modules.ato:3566`).

Two facts about consumer 2 matter for everything downstream:

- **It is not implemented.** `read_dc_bus_current()` is `extern`-declared in
  `firmware/main/state_machine.c:75` and `state_handlers.c:46` with no ESP32 body anywhere in
  `firmware/components/hal/esp32/`; the only definition is the simulation stub at
  `firmware/components/safety/safety.c:114`.
- **It saturates below the operating point.** `V_I_SENSE = 1.65 ± (I/100)×4.99` reaches the
  ESP32's practical linear top (~3.1 V) at **~29 A peak**, against a committed 1800 W operating
  peak of **31.9 A** (`docs/evidence/2026-08-15-ocp-threshold-decision.md` §1, §2).

**Pan detection does not use it.** `firmware/components/control/pan_detect.c` is a
pulse-and-listen edge counter on an MCPWM capture channel, not an ADC consumer. Neither does
the PLL/ZVS path. So the entire live dependency on T1 today is **OCP-01's hardware comparator**.

Committed operating point, for reference throughout: **22.5 A r.m.s. / 31.9 A peak** at 1800 W,
36 % margin to the 50.1 A trip.

---

## 2. The topology, from source

`elec/src/modules.ato:625-632` (`in ~ c_tank1.p1`, `c_tank1.p2 ~ inductor_conn.p1`,
`inductor_conn.p2 ~ out`) and `main.ato:817,823-824`:

```
SW_NODE ──┤ c_tank1‖c_tank2‖c_tank3 (3×100nF) ├── tank.c_tank1-p2 ──[ L coil 88µH ]── tank-out ──[ T1 primary ]── PWR_RTN
             ^ 340 Vpp switched                    ^ 570.5 V r.m.s. / 923.7 V pk        ^ ?                        ^ MAINS, 120 V
```

This diagram is **not mine** — it is reproduced verbatim from
`docs/evidence/2026-08-12-hv-clearance-adequacy.md:99`, and the same document's net table at
line 69 reads:

> \| `tank-out` \| Coil far end → CT primary → `PWR_RTN` \| `main.ato:823-824` \|

The repository has therefore *already documented* that `tank-out` is one winding away from
`PWR_RTN`. What it has never done is derive a voltage for it.

### 2.1 `tank-out` is a two-pad net

Extracted directly from `pcb/temper.kicad_pcb`. Net 151 `tank-out` appears on exactly **two
pads** (the third occurrence of the string is the net declaration at line 210, not a pad):

| pad | component | role |
|---|---|---|
| R30 pad 2, `(at 13 0)`, Ø8 THT | litz coil termination (`LitzPad_15A`) | coil far terminal |
| T1 pad 1, `(at 7.68 -6.85)`, 9×4.8 SMD | `ct_sense.ct` P1 | CT primary in |

There is no divider, no snubber, no bleeder, no test point. The node's only path to the rest of
the circuit at any frequency below the CT's self-resonance is **through the primary winding**.

---

## 3. Bounding the primary winding voltage

This is the whole quantitative question: how far can `tank-out` depart from `PWR_RTN`?

### 3.1 Calculated, at the OCP-01 trip point

Ideal-transformer reflection of the burden voltage, using only committed values:

```
V_secondary at trip = 2.4925 V              (OCPComparator reference, modules.ato:1708-1719)
V_primary  = 2.4925 / 100                   = 24.9 mV
V_DCR      = 0.0001 Ω × 50 A                =  5.0 mV      (primary DCR, components.ato:134)
                                            -----------
                                            ≈ 30 mV
```

At the 31.9 A operating peak it is ~21 mV. The primary leakage reactance is **not published in
the datasheet extract committed at `components.ato:124-158`**, so it is not estimated here.

### 3.2 Bounded, from the part's own rating — no leakage figure needed

The datasheet volt-time product is **638 V-µs** (`components.ato:133`). That is a secondary
rating; referred through the 1:100 ratio it is **6.38 V-µs** on the primary. At f_sw = 47 kHz
the half-period is 10.638 µs, so:

```
V_primary(mean, half-cycle) ≤ 6.38 V-µs / 10.638 µs = 0.600 V
```

**Any primary voltage above 0.600 V would exceed the part's rated volt-time product** — i.e.
the part would be operating outside its own specification before `tank-out` could reach even
one volt above `PWR_RTN`. This bound is independent of leakage inductance, coil value, pan
coupling, load, and operating point. The recorded demand is 18× inside it
(`components.ato:133`: "638 V-µs vs 35.7 V-µs at the trip point").

### 3.3 Composition against earth, and row sensitivity

`gnd ~ pe` (`main.ato:753`), so an HV↔SELV pairing is physically HV↔earth. `PWR_RTN` is
declared at 120 V r.m.s. against earth (`elec/insulation_manifest.yaml`, `MAINS` group, on the
cl. 29.2 neutral-NOTE basis — no earth credit is taken for the neutral connection). Composing
the winding drop onto it, using the manifest's own r.m.s.-composition method:

| primary drop assumed | composed V against earth | Table 17 row | required (reinforced) |
|---|---:|---|---:|
| 30 mV (calculated, §3.1) | 120.00 | ii, `>50-125` | 4.8 mm |
| 0.600 V (rated bound, §3.2) | 120.0015 | ii, `>50-125` | 4.8 mm |
| 6.0 V (10× the rated bound) | 120.15 | ii, `>50-125` | 4.8 mm |
| 35 V (58× the rated bound) | 125.0 | ii boundary | 4.8 mm |

The row boundary is at 125 V. It takes **58× the part's own rated volt-time ceiling** to reach
it. This conclusion is not sensitive to the estimate.

### 3.4 Where the gap entered the record

`docs/evidence/2026-08-12-hv-clearance-adequacy.md:418` quotes an older open item:

> *"Peak working voltage at the `tank-out` node (T1's HV pad) was not derived. If the resonant
> tank exceeds ~1170 V peak, the clearance figure moves up a step."*

and immediately answers:

> **This document closes that item.** The answer is that the tank node reaches 923.7 V peak…

The 923.7 V peak is measured at **`tank.c_tank1-p2`** — every one of that document's 20
voltage rows names that net (§4.3 grid, line 152: `tank.c_tank1-p2 ↔ DC_BUS_RTN`; §5 row,
line 306: `tank.c_tank1-p2 ↔ rails`). The item was raised about `tank-out` and closed with a
measurement of a different node.

The ngspice deck those figures come from does not contain a `tank-out` node at all.
`simulation/harness/nets/zvs_margin_sweep.cir:328-330` is:

```
C_TANK   sw        tank_mid   {C_TANK}
V_ISENSE tank_mid  tank_mid2  DC 0
X_PAN    tank_mid2 0          PANLOAD_TRANSFORMER ...
```

The coil returns to **node 0**. The simulation models the coil's far end as ground, which is
precisely the claim of this section — and it is the model every committed tank voltage figure
was produced from.

`0cbc04248`'s determination then carried the pair forward jointly — its §6.1 pairing 7 is
written *"`tank-out` / `tank.c_tank1-p2` ↔ SELV/PE"*, one row for two nets — and
`elec/insulation_manifest.yaml`'s `TANK` group inherited that, declaring 570.5 V for both on a
basis line that reads *"The resonant tank's two measured nets."* One of the two was measured.

To its credit, the determination flags the residue itself: *"**The tank↔SELV working voltage
has never been measured in this repository.** That is a measurement gap, not a standards gap,
and it is cheap to close."*

---

## 4. What changes if `tank-out` is reclassified, computed pad by pad

All figures below are edge-to-edge, computed by hand from T1's pad table as printed from
`pcb/temper.kicad_pcb`. Pad rotation is 90° absolute against a footprint placed at 90°, i.e.
**zero local rotation**, so extents are axis-aligned:

```
pad 1  tank-out   c=( 7.68,-6.85)  9.0×4.8  →  x[  3.18, 12.18]  y[-9.25,-4.45]
pad 2  PWR_RTN    c=(-7.68,-6.85)  9.0×4.8  →  x[-12.18, -3.18]  y[-9.25,-4.45]
pad 3  I_SENSE    c=(-6.88, 6.95)  3.0×4.6  →  x[ -8.38, -5.38]  y[ 4.65, 9.25]
pad 4  gnd        c=( 6.88, 6.95)  3.0×4.6  →  x[  5.38,  8.38]  y[ 4.65, 9.25]
```

**This reproduces the committed 9.100 mm exactly**: pad 1 ↔ pad 4 overlap in x, so the gap is
purely `4.65 − (−4.45) = 9.100`. Independent confirmation of the per-pairing measurement, from
the board file, by a different method. T2's footprint is pad-for-pad identical (0° placement,
0° pad rotation) and yields the same 9.100 mm.

| pair | gap (mm) | pairing today | verdict today | pairing if `tank-out`→`MAINS` | verdict |
|---|---:|---|---|---|---|
| 1↔4 `tank-out`↔`gnd` | **9.100** | `SELV↔TANK`, ≥20.0 indet. | **FAIL** | `MAINS↔SELV`, 4.8 | **PASS** (+4.3) |
| 1↔3 `tank-out`↔`I_SENSE` | 12.493 | `SELV↔TANK`, ≥20.0 indet. | **FAIL** | `MAINS↔SELV`, 4.8 | **PASS** (+7.7) |
| 1↔2 `tank-out`↔`PWR_RTN` | **6.360** | `MAINS↔TANK`, ≥10.0 indet. | **FAIL** | `MAINS↔MAINS`, 2.2 | **PASS** (+4.2) |
| 2↔3 `PWR_RTN`↔`I_SENSE` | 9.100 | `MAINS↔SELV`, 4.8 | PASS | unchanged | PASS |
| 2↔4 `PWR_RTN`↔`gnd` | 12.493 | `MAINS↔SELV`, 4.8 | PASS | unchanged | PASS |
| 3↔4 `I_SENSE`↔`gnd` | 10.760 | `SELV↔SELV`, 1.8 | PASS | unchanged | PASS |

**No pairing anywhere gets a lower requirement than its physics supports, and none regresses.**
The reclassification also resolves rows 1↔3 and 1↔2, which are not in the five-row summary the
task carries — see §7.1, they may not be reported by the current consumer.

### 4.1 The one pairing it does *not* fix

R30's own two pads carry the coil's two ends, which genuinely do stand off the full resonant
swing:

```
R30 pad 1 (tank.c_tank1-p2) at (0,0)   Ø8 THT
R30 pad 2 (tank-out)        at (13,0)  Ø8 THT
edge-to-edge = 13.0 − 4.0 − 4.0 = 5.000 mm
```

Today that is `TANK↔TANK` (functional, 570.5 V, indeterminate, **floor 10.0 mm**) — 5.000 mm
against a 10.0 mm floor. After reclassification it becomes `MAINS↔TANK` (functional, 570.5 V,
indeterminate, **floor 10.0 mm**) — identical requirement, identical shortfall. **Unchanged in
both directions.** It is flagged here because this analysis surfaced it, it is a real HV↔HV
gap on a live net pair, and it is not in the five-row table. It is outside this task's scope
and is **not** verified against `scripts/check_insulation_pairings.py` (§7.1).

---

## 5. The alternatives the task asked to be evaluated on their merits

These were worked before the §3 finding landed. They are kept because the owner may reject the
reclassification, in which case this is the fallback menu — and because two of them turn out to
carry findings that stand on their own.

### 5.1 AC line ahead of the bridge rectifier — `MAINS↔SELV`, 4.8 mm. **Not a substitute.**

Geometrically trivial: 4.8 mm required, 9.100 mm available. Functionally it does not do
OCP-01's job, for a reason that is structural rather than a matter of degree.

Between any line-side CT and the IGBTs sit **7200 µF** of bulk capacitance —
`c_bus1`/`c_bus1b`/`c_bus2`/`c_bus2b`, 4 × 1800 µF, `modules.ato:819-846`. At 47 kHz that bank
presents under a milliohm. The tank current does not reach the line; it circulates between the
tank and the bulk caps. And on a fault timescale the situation is worse, not better: a
shoot-through is supplied *by the bulk capacitors*, and a line CT registers essentially nothing
for milliseconds against OCP-01's **<1 µs** acceptance budget.

A line CT measures **input power**. That is a genuinely useful control input — plausibly what
ZFBC13F uses one for — but it is a different measurand, not a lower-voltage version of this
one. **What is lost: the entire protective function.**

### 5.2 DC bus return — `DC_BUS↔SELV`, 8.0 mm. Already built. Better than expected, still not equivalent.

This is where the design already went. **OCP-02 exists**: `SecondaryOCPComparator`
(`modules.ato:2640+`), a second CST3015-100ED (T2) spliced into `DC_BUS_RTN` between
`hb.dc_bus.hv_minus` and the bulk rail (`main.ato:794-795`), 4.12 Ω burden, REF2025 2.5 V
reference, 60.68 A nominal trip, worst case 59.31–62.10 A. Fully wired in `elec/`, staged
off-board in `pcb/` at (100, 300).

**What T2's primary actually carries — derived here, and stronger than the record claims.**
`power_loop.q_low.E ~ dc_bus.hv_minus` (`modules.ato:378`), and T2 is spliced immediately
downstream, so T2's primary carries **the low-side IGBT's emitter current**. Working the
current paths:

- **Low-side conducting**: tank current returns `tank → PWR_RTN → C_bus2 → dc_bus_minus →
  T2 → hb-gnd → q_low (IGBT or antiparallel diode) → SW_NODE`. T2 sees the **full
  instantaneous tank current, both polarities**, via the IGBT one way and the diode the other.
- **High-side conducting**: the path is `dc_bus_plus → q_high → SW_NODE → tank → PWR_RTN →
  C_bus1 → dc_bus_plus`. It closes without touching `hb-gnd` or `dc_bus_minus`. T2 sees ~0.

So **T2's waveform is the tank current gated by the low-side conduction interval, at full
amplitude** — not the ~6 A bus average that
`docs/evidence/2026-08-15-ocp-threshold-decision.md` §3 correctly warns against confusing with
tank current. In a symmetric 50 % half-bridge the tank current's negative peak falls inside
that interval, so T2 observes one of the two peaks per switching cycle at full magnitude.

The local bypass does not spoil this. `c_dc_hf` (470 nF PP) shunts `dc_bus_plus ↔ hb-gnd`
(`modules.ato:348-355`), i.e. it bridges *around* T2. At 47 kHz its 7.2 Ω sits against a bulk
return path of roughly 25 mΩ (7200 µF plus snap-in ESR plus strays), so **under 0.4 %** of the
fundamental is diverted. At MHz switching-edge content `c_dc_hf` does dominate, so T2 sees a
slew-limited edge — irrelevant to a 47 kHz-fundamental peak trip.

**What is lost, precisely:**

1. **Up to a half switching period of detection latency** — 10.64 µs at 47 kHz. If the
   excursion begins during the high-side interval, T2 cannot see it until the low-side turns
   on. Against OCP-01's **<1 µs** acceptance criterion (`FUNCTIONAL_TEST_CRITERIA.md` §2.1)
   **this alone disqualifies bus-return sensing as an OCP-01 replacement.** It is why OCP-02
   carries a <5 µs budget and OCP-01 carries <1 µs; they were never interchangeable.
2. **Core reset / flux walking.** The gated waveform has a nonzero per-cycle mean, so the core
   must reset through the burden during the high-side interval. The 638 V-µs rating makes it
   plausible — demand at the 60 A trip is 2.47 V × 10.64 µs ≈ **26.3 V-µs**, a 24× margin —
   but **no simulation of the gated waveform exists in this repository** and the existing
   `ocp02_option_a_trip_point.cir` does not model it.
3. **The ADC path degrades to a chopped waveform**, so it could not serve as a tank-current
   measurement even once implemented.

**What is gained:** T2 sees **shoot-through**, which T1 cannot — a shoot-through never enters
the tank (`OCP02_DECISION_BRIEF.md` §3.1). The two channels are genuinely complementary.

### 5.3 Shunt + isolated amplifier — dominated

`AMC1301`: 8.5 mm creepage, 3.4 µs datasheet-max propagation, requires a second isolated bias
supply that is unspecified (`OCP02_DECISION_BRIEF.md` §3, option B; figures second-hand from
`docs/evidence/2026-08-16-cert-lab-and-ocp02-spike.md`, not re-verified here). Against the new
`DC_BUS↔SELV` = 8.0 mm it now clears, at 0.5 mm margin versus T2's 1.1 mm — while costing more
parts, an unspecified supply, and a tighter timing budget. **Strictly dominated by §5.2.**

### 5.4 A finding that stands on its own: OCP-02's de-scope rests on a deleted threshold

`docs/evidence/2026-08-16-ocp02-descope-implementation.md` de-scoped OCP-02 on one stated
ground, repeated in its §1 table, in `firmware/config.yaml:250-257`, and in `STRATEGY.md:233`:

> the CST3015 CT's 9.100 mm intrinsic primary↔secondary creepage **cannot reach the 12.6 mm
> PD3 reinforced bar** … no alternative mechanism clears it

`MIN_BARRIER_WIDTH_MM = 12.6` **no longer exists.** The per-pairing derivation (`bd39eb10a`)
replaced it, and T2's actual pairing — `DC_BUS↔SELV`, `hb-gnd ↔ gnd` — resolves to **8.0 mm**,
which T2's 9.100 mm clears by 1.1 mm. Every alternative-mechanism row in that table was also
scored against 12.6 mm.

**The de-scope's sole technical premise is void.** That does not automatically reinstate
OCP-02 — the timing, reset, and BOM questions in §5.2 are real and unresolved, and de-scoping
was also argued on "not clause-mandated" grounds — but it does mean the decision was taken
against a number that no longer governs and is owed a fresh look on its merits. Flagged, not
acted on.

---

## 6. The measurement that settles §3

One bench measurement, on the existing board, closes this:

> **Scope `tank-out` against PE**, at the 1800 W operating point, with `PWR_RTN` measured
> simultaneously on a second channel. Report the r.m.s. and peak of `V(tank-out) − V(PE)` and
> of `V(tank-out) − V(PWR_RTN)`.

Predictions, so the measurement can falsify this document rather than confirm it:

- `V(tank-out) − V(PWR_RTN)`: **≤ 0.6 V** (§3.2 bound), expected ~30 mV (§3.1). **If this
  exceeds ~1 V, §3 is wrong** and the `TANK` classification should stand.
- `V(tank-out) − V(PE)`: **≈ V(PWR_RTN) − V(PE)**, i.e. the 120 V mains class, *not* 570 V.

This is the same measurement `elec/insulation_manifest.yaml`'s `SELV↔TANK` basis already calls
out (*"the tank↔SELV working voltage has NEVER been measured in this repository … the number
is inferred and the measurement is cheap"*) and that `0cbc04248` §6.2 names as its own
third-ranked confidence gap. It was already the right thing to do; §3 raises the stakes on it.

Until it is done, the correct state is what the manifest already encodes: an explicit
`IndeterminateWithFloor` that **cannot produce a PASS from any consumer at any measured
distance**, and CI exiting 6. Nothing in this document should be read as licence to relax that
before the measurement exists.

---

## 7. T2's status: unaffected, and the reasoning is sound

**T2 is not affected. `hb-gnd` is correctly classified `DC_BUS` at 0 Hz, and its requirement
does not become indeterminate.**

`hb-gnd` is `hb.dc_bus.hv_minus` — the low-side IGBT emitter (`modules.ato:378`), the
UCC21550's `VSSB` (`modules.ato:425`), `c_dc_hf`'s low terminal, and `power_15v_ls`'s
reference. It is **not** a switching node:

- Its potential is clamped to `PWR_RTN` by **3600 µF** (`c_bus2` ‖ `c_bus2b`,
  `modules.ato:922-925`) at −170 V d.c. `SW_NODE`, by contrast, swings the full 340 V pp at
  47 kHz — which is why `SW_NODE` is in `SWITCHING` and `hb-gnd` is not.
- The manifest's own basis states exactly this distinction and applies it deliberately: *"the
  switching current flows in the half-bridge loop, and the rails' potential against earth is
  set by the doubler, not by the switch node. Nets that FLOAT on the switch node are in
  SWITCHING below, not here."* That reasoning is correct, and — note — **it is the same
  reasoning §3 applies to `tank-out`**: current at 47 kHz does not make a node a switching
  node; creepage is dimensioned on voltage.
- Composed against earth, `hb-gnd` is `√(170² + 120²) = 208.1 V r.m.s.`, which the manifest
  already computed and placed in row iii (`>125-250`) with 42 V of headroom.

**One caveat, stated because it is the only thing that could move T2.** `hb-gnd` does carry a
47 kHz ripple from the bulk bank's ESR and the return inductance — order 1 V at the operating
point on a first-pass estimate, but **this repository has never measured it**. It would take
tens of volts of 47 kHz content before "a d.c. rail with ripple" became "a node at 47 kHz",
and the 42 V of row headroom absorbs a great deal — but the honest statement is that the
classification is well-argued and unmeasured. The §6 measurement should pick up `hb-gnd`
against `PWR_RTN` on a third channel while the scope is already connected; it is free.

T2's current standing: **9.100 mm against 8.0 mm required, PASS, +1.1 mm.** Same intra-package
geometry as T1, verified pad-for-pad in §4.

---

### 7.1 What this document does not establish

- **It was not run against `scripts/check_insulation_pairings.py`.** That tool lives on
  `origin/feat/per-pairing-creepage-derivation` and needs the venv plus the rebuilt pyo3
  extension; another agent is running the placer and this session did not compete for memory.
  Every number here is hand-computed from the board file's own pad table, which is why §4
  re-derives the committed 9.100 mm from scratch as a cross-check. **The claim that pairs 1↔3
  and 1↔2 currently FAIL, and that R30's 5.000 mm pair does, is derived from the manifest's
  published requirements, not observed from the checker's output.**
- **The FCC schematics were not retrieved.** The documented recipe returns **HTTP 403** from
  this environment on every route attempted: cookie-seeded `curl` against
  `GenericSearch.cfm` (403 on the seed itself), `GetApplicationAttachment.html?id=1459989`
  with a browser UA and `Referer`, and `WebFetch` against both that URL and the `fccid.io`
  mirror. **The peer session's findings on ZFBC13F, ZBNTI3B and ZBNC18-13 therefore remain
  SECOND-HAND and are not verified by this document.** §5.1 does not depend on them: it
  disqualifies line-side sensing from this board's own bulk-capacitance and timing figures,
  which would hold whatever ZFBC13F does.
- **IEC 60664-4 remains UNOBTAINABLE.** No requirement above 30 kHz is derived, asserted, or
  guessed anywhere in this document. §3's argument runs the other way — it removes a pairing
  from the >30 kHz regime by showing its voltage is not the tank's, rather than dimensioning
  anything inside it.
- **No datasheet value, part number or standards clause is invented.** The 638 V-µs, 1:100,
  0.0001 Ω and 5000 V r.m.s. figures are quoted from `components.ato:124-158`, which records
  them as verified against Coilcraft Document 1608-1; they were not re-fetched this session.

---

## 8. If the owner rejects §3: what protects the half-bridge

Answered because it was asked, and because it is the fallback if the measurement contradicts §3.

**The UCC21550 offers nothing.** Its pinout is exhaustively enumerated at
`components.ato:62-80` from TI SLUSE89C: `INA, INB, VCCI_1, GNDI, DIS, DT, VCCI_2, VSSB, OUTB,
VDDB, VSSA, OUTA, VDDA`. **There is no DESAT pin, no cycle-by-cycle current-limit input, no
fault output, and no soft-shutdown pin.** It is a plain dual isolated driver with a disable and
a dead-time programming resistor. The only actuator it exposes is `DIS`, which `SHUTDOWN`
already drives (`main.ato:898`). Nothing in the existing part can be leaned on.

Desaturation detection was **formally de-scoped 2026-07-26** (`STRATEGY.md:51`, BOM rev 1.4,
19 BOM lines removed with residual risk accepted in writing).

So without tank sensing the chain reduces to: OCP-02 at ~10.64 µs worst-case latency (§5.2, and
currently de-scoped, §5.4), OVP-01 on the bus, the thermal interlocks, and a firmware layer
whose ADC input does not exist and would saturate at ~29 A if it did (§1). That is materially
weaker than today's <1 µs latched peak trip, and rebuilding equivalent protection would mean
reinstating DESAT — the option this project already priced and rejected.

**This is the cost of treating a one-turn, ≤0.6 V sense winding as a group boundary**, and it
is why §6's measurement is worth doing before any architecture is redrawn.
