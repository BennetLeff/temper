<!-- provenance: commit=765859caaef56b879ba5d699eaf38449ff6f5eee dirty=false (base of branch analysis/hv-clearance-adequacy, = origin/main at measurement time). pcb/temper.kicad_pcb sha256=6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64, identical to power_pcb_dataset/drc_ceiling.json's recorded provenance input hash (board unchanged since 2026-08-08). pcb/** was read-only for the whole of this work: every clearance/netclass variant measured below was applied to a scratch copy of temper.kicad_pcb/.kicad_pro/.kicad_dru outside the repo, never written back. kicad-cli 10.0.5 (/home/bennet/.local/opt/kicad-10.0.5/root/usr/bin/kicad-cli), measured live, MaximumThreads=1 pinned per temper_placer.validation._drc_api._single_threaded_kicad_env. Circuit voltages measured live with ngspice-42 (KLU) against simulation/harness/nets/zvs_margin_sweep.cir at origin/main, unmodified except for added .meas cards (listed in Sec 2.2) and .param sweeps; the deck's own committed topology, models and .options were not touched. IEC 60335-1 Table 15/16/17 and clause 29.1/29.1.3/29.1.5 text quoted from docs/evidence/2026-07-28-creepage-determination-brainstorm.md at commit 880405ed9, read first-hand this session (that file is NOT on main -- see Sec 6.1). -->

# 2.0mm is adequate for every `HighVoltage` pair on this board — but only just, and only because OCP-01 and the 44 kHz PLL floor hold. The real deficiency at the tank node is creepage, which is not enforced at all.

**Verdict, up front.**

1. **2.0mm clearance is adequate.** The worst same-domain `HighVoltage` pair on
   this board is the resonant-tank cap↔coil junction (`tank.c_tank1-p2`) against
   the DC bus rails. Measured peak working voltage across the entire legal
   operating envelope, worst tolerance corner included, that OCP-01 permits:
   **923.7 V peak**. IEC 60335-1 clause 29.1.5 (the clause that explicitly names
   "if there is a resonant voltage") gives a determining voltage of 2 254 V →
   Table 16 basic clearance 1.5mm at the 2 500 V step (1.25mm interpolated),
   plus clause 29.1's +0.5mm soldered-construction adder = **2.0mm**. The
   committed value is exactly the requirement.
2. **The hypothesis that the tank swings to 1–2 kV is only half right.** It does
   swing far above the bus — 2.5–3.8× the 340 V bus, not the 400 V that
   `elec/src/modules.ato:534` declares — but it does not reach 1–2 kV inside the
   protected envelope. This is a *series*-resonant half-bridge run *above*
   resonance at a loaded ratio of ~1.25, not a quasi-resonant single-switch
   flyback tank, and that topology choice is what keeps the number down.
3. **2.0mm is not adequate with slack; it is adequate at the step boundary.**
   The Table 16 step moves from 1.5mm to 3.0mm at 1 169.7 V peak working
   voltage. Worst OCP-passing measured point is 923.7 V — **1.27× margin**. One
   real parameter combination inside purchased-part tolerance (L −10%, C −10% at
   the 44 kHz PLL floor) reaches **1 289.4 V**, which *exceeds* the step and
   would require 3.5mm — it is prevented only by OCP-01 tripping at 68.7 A
   peak against its 50.1 A threshold. The clearance is guarded by a protection
   function, not by geometry. See Sec 4.3.
4. **The actual under-specification at the tank node is creepage, not
   clearance.** `HighVoltage`↔`HighVoltage` pairs have **no creepage constraint
   emitted at all** (Sec 3.2). At 570.5 V rms the tank↔rail pair lands in
   IEC 60335-1 Table 17 **row vi** (>500 and ≤800 V), where basic creepage at
   PD2/material group IIIa-IIIb is **6.3mm**, and at PD3 — which
   `docs/evidence/2026-08-11-pd2-decision-record.md:40-58` says governs the
   as-built board today — is **10.0mm**. What the board provides on a flat,
   ungrooved, uncoated surface is the clearance figure, 2.0mm. That is a **3.2×
   (PD2) to 5.0× (PD3) shortfall** on a distance nothing currently checks.
5. **Do not raise `HighVoltage` wholesale.** Measured: 2.0→3.0mm costs +5
   clearance violations and breaches both the category and aggregate DRC
   ceilings. A separate netclass carrying only `tank.c_tank1-p2` costs **zero**
   additional violations up to 4.0mm and +1 at 6.0mm. Sec 5.
6. **Separate finding, reported because this is a mains appliance:** `PWR_RTN`
   is declared HV-domain in `elec/domain_manifest.yaml:95` but has **no netclass
   assignment** in `pcb/temper.kicad_pro`. It falls to `Default` (0.2mm) and is
   invisible to every HV↔LV clearance and creepage rule in the generated DRU.
   Sec 6.3.

**No clearance value is changed by this PR.** Per the brief, the determination
lands first; any change is separate and follows review.

---

## 1. Which nets carry the `HighVoltage` class

Cross-referenced three ways: `pcb/temper.kicad_pro`'s `netclass_assignments`
(what kicad-cli enforces), `packages/temper-placer/src/temper_placer/core/design_rules.py`'s
`NET_CLASS_ASSIGNMENTS` (what the placer models), and the board's own `(net …)`
declarations in `pcb/temper.kicad_pcb` (what actually exists).

**14 `HighVoltage`-class nets exist on the committed board:**

| Net | Circuit node | Source for its identity |
|---|---|---|
| `+170V_BUS` | Doubler positive rail, referenced to `PWR_RTN` | `elec/src/main.ato:511-520` |
| `DC_BUS_RTN` | Doubler negative rail (−170 V wrt `PWR_RTN`) | `main.ato:521-522` |
| `SW_NODE` | Half-bridge switch node = `tank.in` | `main.ato:817` |
| `tank.c_tank1-p2` | **Tank capacitor bank ↔ coil junction** | `elec/src/modules.ato:551-557` |
| `tank-out` | Coil far end → CT primary → `PWR_RTN` | `main.ato:823-824` |
| `w1_1`, `w1_2` | CMC winding taps, line side (raw AC) | `design_rules.py:323-324` |
| `zcd` | `power_in` internal HV-side ZCD divider tap | `design_rules.py:325` |
| `a` | HV-side node in `power_in` | `design_rules.py:310` |
| `+15V_LS` | Isolated low-side gate driver supply, HV-referenced | `main.ato:531-532` |
| `power_in.ntc-no` | Bypass-relay NO contact → rectified mains | `design_rules.py:328` |
| `discharge.k_dis1-nc`, `discharge.k_dis2-nc` | Discharge relay NC contacts, HV bus | `design_rules.py:329-330` |
| `hb.power_loop.q_high-g` | Q_high gate, one resistor from `GATE_HS` | `design_rules.py:331` |

**Three assignments in `pcb/temper.kicad_pro` are dead** — `DC_BUS+`, `DC_BUS-`,
`SWITCH_NODE` name nets that do not exist on `pcb/temper.kicad_pcb`. Harmless,
but they are why a reader scanning the `.kicad_pro` sees 17 `HighVoltage`
entries and the board has 14.

**One HV-domain net is missing from the class entirely:** `PWR_RTN`. Sec 6.3.

**Adjacent, deliberately excluded:** `GATE_HS`/`GATE_LS` (class `GateDriveHV`,
0.25mm) and `+5V_ISO`/`VBOOT_H`/`VBOOT_L` (class `HighVoltageIsolated`, 6.0mm)
are HV-domain per `elec/domain_manifest.yaml` but are not in scope here — the
question asked is about `HighVoltage`↔`HighVoltage`.

---

## 2. The actual peak working voltage on each, derived from the circuit

### 2.1 Topology — why the tank node is the one that matters

From source, not from the netclass label:

```
SW_NODE ──┤ c_tank1‖c_tank2‖c_tank3 (3 × 100nF) ├── tank.c_tank1-p2 ──[ L coil 88µH ]── tank-out ──[CT pri]── PWR_RTN
```

`elec/src/modules.ato:551-557` (`in ~ c_tank1.p1`, `c_tank1.p2 ~
inductor_conn.p1`, `inductor_conn.p2 ~ out`), `main.ato:817` (`hb.switch_node ~
tank.in`), `main.ato:823-824` (`tank.out ~ ct_sense.primary_in`,
`ct_sense.primary_out ~ power_return`).

This is a **series**-resonant half-bridge across a split ±170 V bus, driven
**above** resonance (`main.ato:161-163`: *"This is a SERIES-resonant inverter:
above resonance the tank is inductive… below resonance the tank is CAPACITIVE and
the bridge hard-switches"*), at f_sw/f_res_loaded ≈ 1.25.

The consequence for insulation: `SW_NODE` is *clamped* — it can only swing rail
to rail, and measurement confirms it (±173 V, i.e. the 340 V bus, at every
operating point). The node that is **not** clamped is `tank.c_tank1-p2`, the
cap↔coil junction, which carries the full inductive drop `I·ωL_loaded`. Because
it sits between the two reactances, its potential relative to *either* bus rail
is the coil voltage plus a rail offset. **That is the pair the design's own
`v_tank_peak = 400V` declaration (`modules.ato:534`) does not describe.**

### 2.2 Measurement

The repo's own committed ZVS harness already measures `v_sw_max`/`v_sw_min` and
the capacitor differential `V(sw)-V(tank_mid)`, but
`docs/evidence/2026-08-07-zvs-margin-sweep.json` records neither the tank-node
potential nor the tank↔rail differentials — the quantities insulation
coordination needs. They are recoverable from the same deck without touching it:
`simulation/harness/nets/zvs_margin_sweep.cir` was copied to scratch and given
six additional `.meas` cards, changing nothing else:

```
.meas tran v_tankmid_max/min  MAX/MIN V(tank_mid)
.meas tran v_tm_hvp_max/min   MAX/MIN PAR('V(tank_mid)-V(hvp)')     ; tank ↔ +170V_BUS
.meas tran v_tm_hvn_max/min   MAX/MIN PAR('V(tank_mid)-V(hvn)')     ; tank ↔ DC_BUS_RTN
```

plus RMS variants for the creepage question. Node mapping: the deck's `hvp` =
`+170V_BUS`, `hvn` = `DC_BUS_RTN`, node `0` = `PWR_RTN` (doubler midpoint),
`sw` = `SW_NODE`, `tank_mid` = `tank.c_tank1-p2`.

Pan coupling, coil and capacitance are the deck's own committed values as
re-derived by `docs/evidence/2026-08-07-zvs-margin-sweep.md` §2 (K=0.6136,
L2=97.13 µH, RPAN=10 Ω, L1=88 µH, C=300 nF). Tolerance corners applied to L and C
only, at `l_tank_tolerance`/`c_tank_tolerance` = 0.10 each (`main.ato:450,487`).

### 2.3 Results — peak working voltage per pair

Cast-iron/stainless pan (the worst-coupled, highest-current preset). Full grid in
Sec 4.3; the declared nominal operating point and the two envelope extremes here:

| `HighVoltage` pair | 47 kHz declared nominal | 44 kHz PLL floor | Worst OCP-passing point |
|---|---:|---:|---:|
| `tank.c_tank1-p2` ↔ `DC_BUS_RTN` | **699.9 V pk** | **837.7 V pk** | **923.7 V pk** |
| `tank.c_tank1-p2` ↔ `+170V_BUS` | 699.5 V pk | 837.2 V pk | 923.1 V pk |
| `tank.c_tank1-p2` ↔ `PWR_RTN` | 529.9 V pk | 667.7 V pk | 753.7 V pk |
| `tank.c_tank1-p2` ↔ `SW_NODE` (across the tank caps) | 360.0 V pk | 497.8 V pk | 583.9 V pk |
| `SW_NODE` ↔ either rail | 343.4 V pk | 344.4 V pk | 344.2 V pk |
| `+170V_BUS` ↔ `DC_BUS_RTN` (full bus) | 340 V DC | 340 V DC | 400 V (`main.ato:50` `v_bus_abs_max`) |
| `w1_1`/`w1_2`/`a`/`zcd`/`power_in.ntc-no`/`discharge.k_dis*-nc`/`+15V_LS`/`hb.power_loop.q_high-g` — all rectifier-side or bus-referenced | ≤ 400 V | ≤ 400 V | ≤ 400 V |

Worst OCP-passing point = L −10%, C −10%, 48 kHz (Sec 4.3).

**Corroboration that these are not a simulation artifact.** `elec/src/modules.ato:495`
records an independent per-capacitor stress figure of *"234 Vrms / 331 V peak"*
across a tank cap; this measurement gives 255.5 Vrms / 360.0 V peak across the
same capacitor at the same 47 kHz declared nominal — the same quantity, ~9%
apart, consistent with the first-harmonic hand-solve that figure came from.
The tank-node-to-rail numbers are the same measurement read at a different node
pair; nothing new is assumed to obtain them.

**Two design declarations this contradicts, reported not fixed:**

- `elec/src/modules.ato:534`, `v_tank_peak: voltage = 400V`. Measured capacitor
  peak is 360 V at the declared nominal but **497.8 V at the 44 kHz PLL floor**
  and ~584 V at the worst tolerance corner. The declaration is only true at one
  point in the legal band. It is used for `assert c_tank*.voltage_rating >=
  v_tank_peak * 1.43`, which passes with enormous margin either way (1600 V
  parts), so nothing downstream breaks — but the number is not the working
  voltage of that node.
- `pcb/temper.kicad_pro`'s `HighVoltage` description, *"DC bus, switch node,
  resonant tank. 340V, 22A peak."* The class does cover the resonant tank, and
  the resonant tank is not 340 V.

---

## 3. The required clearance for that voltage

### 3.1 Clearance — IEC 60335-1 clause 29.1.5, the resonant-voltage clause

Every clause and table value below is quoted from
`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §3 at commit
`880405ed9`, which labels them CITED-PRIMARY (read from the IS 302-1:2008 text
layer). I re-read that file first-hand this session. **It is not on `main`** —
Sec 6.1.

Inputs:

| Quantity | Value | Source |
|---|---|---|
| Rated voltage | 120 V | `elec/src/main.ato:52` `v_ac_nominal = 120V` |
| Overvoltage category | II | cl. 29.1: *"Appliances are in overvoltage category II."* |
| Rated impulse voltage | **1 500 V** | Table 15, row ii (>50 and ≤150 V), OVC II column |
| Peak rated voltage | 169.7 V | 120 × √2 |
| Pollution degree | 2 selected, PD3 as built | `docs/evidence/2026-08-11-pd2-decision-record.md:19-30, 40-58` |

Clause 29.1.5 (CITED-PRIMARY), the governing clause and the reason this analysis
exists:

> "For appliances having higher working voltages than rated voltage, for example
> on the secondary side of a step-up transformer, **or if there is a resonant
> voltage**, the voltage used for determining clearances from Table 16 shall be
> the sum of the rated impulse voltage and the difference between the peak value
> of the working voltage and the peak value of the rated voltage."
> Note 1: "Clearances for intermediate values of Table 16 may be determined by
> interpolation."

So `V_det = 1500 + (V_pk_working − 169.7)`.

IEC 60335-1 **Table 16, Minimum Clearances** (CITED-PRIMARY), the rows this
lands between:

| Rated impulse voltage (V) | Minimum clearance (mm) |
|---:|---:|
| 1 500 | 0.5 *(footnote: increased to 0.8 mm for pollution degree 3)* |
| 2 500 | 1.5 |
| 4 000 | 3.0 |

Clause 29.1 (CITED-PRIMARY), the adder:

> "if the construction is such that the distances could be affected by wear, by
> distortion, by movement of the parts or during assembly, the clearances for
> rated impulse voltages of 1 500 V and above are increased by 0.5 mm and the
> impulse voltage test is not applicable" … "Examples of constructions in which
> distances are likely to be affected are those involving **soldering**, snap-on
> and screw terminals and clearances from motor windings."

This is a soldered PCB, one of the clause's own named examples — the same
reading `HV_INTERNAL_CLEARANCE_MM` already applies (`scripts/generate_kicad_dru.py:56-63`).

**Derivation at the worst OCP-passing pair, `tank.c_tank1-p2` ↔ `DC_BUS_RTN`:**

```
V_pk_working = 923.7 V                       (measured, Sec 4.3)
V_det        = 1500 + (923.7 − 169.7) = 2254 V
Table 16     → interpolated:  0.5 + (2254−1500)/1000 × (1.5−0.5) = 1.25 mm  basic
             → step reading (round up to the 2500 V row):          1.50 mm  basic
+ cl. 29.1 soldered-construction adder                            +0.50 mm
─────────────────────────────────────────────────────────────────────────────
REQUIRED CLEARANCE = 1.75 mm (interpolated) / 2.00 mm (step reading)
```

**Committed value: 2.0mm. Requirement: 2.0mm on the conservative reading.
Adequate.**

**Insulation grade.** `HighVoltage`↔`HighVoltage` at different potentials is
**functional** insulation — both sides are hazardous-live, neither is an
accessible or SELV part, so no shock barrier is crossed.
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:118-123` defines the Functional tier
as governing "within same voltage domain" and never populates it with a figure;
that is the hole this document fills. The derivation above uses the **basic**
insulation column of Table 16, which is the conservative choice for a functional
gap (functional requirements are never above basic). Clause 29.1.3's reinforced
"next higher step" rule is *not* applied and is not required here — applying it
would give 3.0 + 0.5 = 3.5mm, but nothing in the standard asks for reinforced
insulation between two nodes of the same hazardous-live domain.

### 3.2 Creepage — a separate distance, not currently constrained for this pair

**Clearance is through air; creepage is over the insulating surface.** They are
dimensioned from different quantities (clearance from the impulse/determining
voltage, creepage from the rms working voltage) and against different tables. On
a flat, ungrooved, uncoated PCB with no slot between the pads, the shortest
surface path and the shortest air path are the **same physical distance**, so the
larger of the two requirements is what the copper must actually provide.
`COATING_QUALIFIED = False` (`scripts/generate_kicad_dru.py:42`) and there is no
slot between these nets, so that identity holds here.

**What is enforced today for `HighVoltage`↔`HighVoltage`:** the 2.0mm netclass
clearance, and nothing else. Verified two ways:

- Rule inventory. `scripts/generate_kicad_dru.py` emits `creepage` constraints in
  exactly three rules — "AC Mains to LV" (`:451`), "HV to LV" (`:542`),
  "HighVoltageIsolated to LV" (`:743`). All three require one side to be
  non-HV. The only HV-internal rule, "HV internal same footprint" (`:814-821`),
  is clearance-only *and* additionally conditioned on `A.Reference ==
  B.Reference`, so it does not even reach pads on different components.
- Empirically. Raising the `HighVoltage` netclass clearance to 20mm on a scratch
  copy moves the clearance count 386 → 499 (Sec 5), confirming the netclass
  figure is what binds these pairs and is not shadowed by the generic
  `Default routing` 0.2mm rule. No creepage count moves with it.

**What Table 17 asks for.** IEC 60335-1 **Table 17, Minimum Creepage Distances
for Basic Insulation** (CITED-PRIMARY; independently re-verified from a 150 dpi
page render in `docs/evidence/2026-07-30-pd2-creepage-row-determination.md:73-98`,
the strongest transcription in the repo), rows v and vi:

| Working voltage (V) | PD2 IIIa/IIIb | PD3 IIIa/IIIb |
|---|---:|---:|
| >250 and ≤400 (row iv) | 4.0 | 6.3 |
| >400 and ≤500 (row v) | 5.0 | 8.0 |
| >500 and ≤800 (row vi) | **6.3** | **10.0** |

Measured rms working voltages (same runs, same deck):

| Pair | Declared nominal 47 kHz | 44 kHz PLL floor | Worst OCP-passing | Table 17 row | PD2 basic | PD3 basic |
|---|---:|---:|---:|---|---:|---:|
| `tank.c_tank1-p2` ↔ rails | 438.8 Vrms | 517.8 Vrms | **570.5 Vrms** | vi | **6.3mm** | **10.0mm** |
| `tank.c_tank1-p2` ↔ `PWR_RTN` | 404.6 | 489.1 | 544.6 | vi | 6.3 | 10.0 |
| `tank.c_tank1-p2` ↔ `SW_NODE` | 255.5 | 351.3 | 411.5 | v | 5.0 | 8.0 |
| `SW_NODE` ↔ rails | 240.1 | 240.0 | 240.2 | iii | 2.5 | 4.0 |
| `+170V_BUS` ↔ `DC_BUS_RTN` | 340 (DC) | 340 | 400 | iv | 4.0 | 6.3 |

**Provided: 2.0mm. Required at the tank node: 6.3mm (PD2) / 10.0mm (PD3).**
`docs/evidence/2026-08-11-pd2-decision-record.md:40-58` states that the PD2
enclosure prerequisite is not implemented and that **"PD3/12.6mm governs the
as-built construction today"** — so 10.0mm is the figure that applies to the
board as it exists, and 6.3mm the figure that applies after the sealed
compartment lands.

**The honest caveat on this number, stated precisely.** Table 17's own header is
*"Minimum Creepage Distances for **Basic** Insulation"*. This pair is functional
insulation. IEC 60335-1 clause **29.2.4** carries a short-circuit-test exemption
for functional insulation, referenced three times in this repo as unresolved
(`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:207-214`;
`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py:251`;
`docs/evidence/2026-07-30-pollution-degree-determination.md:472`) and **whose text
is recorded nowhere in this repository — I have not read it and do not assert its
content.** Two outcomes are possible and a qualified reviewer must pick between
them:
- If 29.2.4's exemption applies and the appliance passes clause 19 with this
  creepage distance short-circuited, the 6.3/10.0mm figure does not bind. Note
  what "short-circuited" means physically here: a dead short from the tank node
  to a bus rail across a running 1.8 kW resonant converter.
- If it does not apply, the board is short by 3.2× (PD2) to 5.0× (PD3) on a
  distance that no gate in this repository measures.

Either way the current state is *unknown*, not *compliant*, and it is unknown
because nothing is checked, not because a check passes.

### 3.3 What I could not close: IEC 60664-4

This tank runs at 44–50 kHz. **IEC 60664-4 (*Insulation coordination — Part 4:
Consideration of high-frequency voltage stress*) governs insulation coordination
above 30 kHz**, and both the clearance and creepage tables used above come from
standards whose scope is power-frequency stress. I searched the repository: the
string `60664-4` appears **zero times**, in any file, on any branch reachable
from `origin/main`. No document in this project has considered whether the
switching frequency invokes it.

**I did not derive a high-frequency figure and I am not going to invent one.**
What a qualified reviewer needs to check, precisely:

1. Whether IEC 60664-4's frequency-dependent reduction factors apply to a
   PCB-internal functional-insulation gap at 44–50 kHz, and if so, what factor
   applies to a ~2mm air gap at that frequency.
2. Whether partial-discharge inception is a consideration at 923.7 V peak
   recurring at 44–50 kHz on a 2mm gap. The only PD-adjacent statement anywhere
   in this repo is IEC 60335-1 Annex J 6.8.6's note (recorded at
   `7994ce7dc:docs/evidence/2026-07-28-conformal-coating-pd1.md:143-146`) that
   *"Partial discharges do not normally occur at voltages lower than 700 V
   peak"* — 923.7 V is **above** that threshold. That note is written about
   coating qualification, not about bare-board air gaps, so it does not settle
   the question; it does establish that the tank node sits in a voltage range
   where the standard itself considers PD worth a note.
   `packages/temper-drc-rs/src/rules/routing/partial_discharge.rs` applies a
   1.5× inner-layer multiplier above 60 V and cites no standard at all.
3. Whether IEC 60335-1 Table 15's Note 2 (CITED-PRIMARY: *"The values are based
   on the assumption that the appliance will not generate higher overvoltages
   than those specified. If higher overvoltages are generated, the clearances
   have to be increased accordingly."*) is discharged by clause 29.1.5's
   arithmetic, or imposes something further. My reading is that 29.1.5 *is* the
   mechanism Note 2 points at, and that is the reading Sec 3.1 uses; the standard
   does not say so explicitly.

This is the largest open item in this document. It could only move the answer
in the direction of requiring **more** clearance, never less.

---

## 4. The verdict on 2.0mm

### 4.1 Adequate — the derivation, restated compactly

| Pair | V_pk (worst OCP-passing) | V_det | Table 16 basic | +0.5mm adder | Required | Provided | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| `tank.c_tank1-p2` ↔ bus rails | 923.7 V | 2 254 V | 1.5 (step) / 1.25 (interp) | +0.5 | **2.00 / 1.75mm** | 2.0mm | **OK** |
| `tank.c_tank1-p2` ↔ `PWR_RTN` | 753.7 V | 2 084 V | 1.5 / 1.08 | +0.5 | 2.00 / 1.58mm | 2.0mm | OK |
| `tank.c_tank1-p2` ↔ `SW_NODE` | 583.9 V | 1 914 V | 1.5 / 0.91 | +0.5 | 2.00 / 1.41mm | 2.0mm | OK |
| `SW_NODE` ↔ rails | 344.2 V | 1 675 V | 1.5 / 0.67 | +0.5 | 2.00 / 1.17mm | 2.0mm | OK |
| Bus / rectifier-side pairs | ≤400 V | ≤1 730 V | 1.5 / 0.73 | +0.5 | 2.00 / 1.23mm | 2.0mm | OK |

On the interpolated reading (which Table 16 Note 1 expressly permits) every pair
has real margin. On the conservative step reading every pair lands on exactly
2.0mm. **There is no subset of `HighVoltage` pairs on this board that requires
more than 2.0mm of clearance inside the protected operating envelope.**

Note the shape of this result: the step reading gives 2.0mm for *everything*
from 170 V to 1 169.7 V peak, because the whole range maps into one Table 16
step. That is why the existing `HV_INTERNAL_CLEARANCE_MM` derivation — which
never considered the tank at all — nevertheless landed on the right number. It
got there by a route (reinforced doubling at 1 500 V) that does not describe
this pair, and it would not have caught a tank node above 1 170 V. **The number
was right; the reasoning did not cover the case.** That is worth fixing in the
comment even though the constant does not move.

### 4.2 Where 2.0mm stops being adequate

Solving `V_det = 2500` (the next Table 16 step) for the working voltage:

```
V_pk_working = 2500 − 1500 + 169.7 = 1169.7 V peak
```

Above 1 169.7 V peak across any `HighVoltage` pair, Table 16 moves to the 4 000 V
row: 3.0mm basic + 0.5mm adder = **3.5mm required**.

`880405ed9:docs/evidence/2026-07-28-creepage-determination-brainstorm.md:762-763`
flagged exactly this, as an explicit UNVERIFIED item: *"Peak working voltage at
the `tank-out` node (T1's HV pad) was not derived. If the resonant tank exceeds
~1170 V peak, the clearance figure moves up a step."* **This document closes that
item.** The answer is that the tank node reaches 923.7 V peak — 1.27× below the
threshold — inside the protected envelope, and 1 289.4 V peak, *above* it,
outside.

### 4.3 The margin is held by OCP-01, not by geometry — full grid

Cast-iron/stainless preset, all three L/C tolerance corners, across the firmware's
legal 44–50 kHz PLL range (`main.ato` `f_pll_tracking_min/max`,
`firmware/components/control/pll_control.h`). `OCP` column screens against
OCP-01's 50.1 A peak trip (`docs/STRATEGY.md` §OCP-01). Peak is
`tank.c_tank1-p2` ↔ the further bus rail.

| L/C corner | f_sw | i_tank pk (A) | OCP | tank↔rail pk (V) | V_det (V) | Table 16 step |
|---|---:|---:|---|---:|---:|---|
| L−10%, C−10% | 44 000 | 68.7 | **TRIP** | **1 289.4** | 2 620 | **4 000 → 3.5mm needed** |
| L−10%, C−10% | 46 000 | 56.3 | **TRIP** | 1 086.8 | 2 417 | 2 500 → 2.0mm |
| L−10%, C−10% | 47 000 | 51.0 | **TRIP** | 998.9 | 2 329 | 2 500 → 2.0mm |
| L−10%, C−10% | 48 000 | 46.4 | pass | **923.7** | 2 254 | 2 500 → 2.0mm |
| L−10%, C−10% | 50 000 | 39.3 | pass | 806.6 | 2 137 | 2 500 → 2.0mm |
| nominal | 44 000 | 40.5 | pass | 837.7 | 2 168 | 2 500 → 2.0mm |
| nominal | 46 000 | 34.5 | pass | 738.2 | 2 069 | 2 500 → 2.0mm |
| nominal | 47 000 (declared) | 32.2 | pass | 699.9 | 2 030 | 2 500 → 2.0mm |
| nominal | 48 000 | 30.3 | pass | 667.3 | 1 998 | 2 500 → 2.0mm |
| nominal | 50 000 | 27.2 | pass | 615.1 | 1 945 | 2 500 → 2.0mm |
| L+10%, C+10% | 44 000 | 28.5 | pass | 644.6 | 1 975 | 2 500 → 2.0mm |
| L+10%, C+10% | 50 000 | 21.4 | pass | 527.4 | 1 858 | 2 500 → 2.0mm |

Below the PLL floor the numbers keep climbing — nominal L/C at 42 kHz gives
979.4 V (48.9 A, just under trip), 40 kHz gives 1 169.8 V (60.3 A, trips),
38 kHz gives 1 347.8 V (71.1 A, trips). Those frequencies are not commandable:
`PLL_MIN_FREQ_HZ` = 44 kHz, cross-checked against `main.ato` by
`scripts/check_pll_range_consistency.py`.

**What this means, stated plainly.** Three independent things keep the tank node
below 1 170 V peak, and none of them is copper geometry:

1. The firmware PLL floor at 44 kHz.
2. OCP-01's 50.1 A peak trip.
3. The series-resonant-above-resonance topology, which makes tank voltage fall
   monotonically with frequency across the legal band.

At the worst purchased-part tolerance corner — **L and C both at −10%, which is
inside their declared tolerances** (`main.ato:450,487`) — commanding the bottom
of the legal PLL range produces 1 289.4 V peak, above the step boundary, and
68.7 A, 1.37× the OCP trip. The converter would trip rather than run. That is
the protection system doing its job, and the reason the clearance stays
adequate; it is not a margin the board's layout provides on its own.

**Two consequences worth someone else's attention, reported not adjudicated:**

- If OCP-01's trip threshold is ever raised, or its detection delayed, the
  clearance determination in this document weakens with it. A note to that effect
  belongs on `HV_INTERNAL_CLEARANCE_MM` and on the OCP-01 threshold.
- At the L−10%/C−10% corner the appliance cannot use the bottom 3–4 kHz of its
  own PLL range without an over-current trip. That is a functional/yield
  finding, not a safety one, and it belongs to whoever owns the PLL range and the
  tank tolerance stack — surfaced here because the same measurement produces it.

### 4.4 What would refute this

The measurement inherits every caveat
`docs/evidence/2026-08-07-zvs-margin-sweep.md` §7 already states, and they matter
more for a voltage figure than for an ordinal ZVS margin:

- `calibrated: false`. The IGBT macromodel has fixed, non-Vce-dependent
  capacitances. That affects switching-transition detail; the tank-node voltage
  is set by the L-C-R divider and the ±170 V drive, which the model represents
  directly, so the peaks are far less model-sensitive than the ZVS margins are.
- **88 µH is a chart reading of a different coil**; K = 0.6136 / L2 = 97.13 µH are
  constraint-satisfying, not measured. If the real coil's loaded inductance is
  higher than modelled, the tank voltage rises proportionally. The tolerance
  corners here span ±10% on L, which is the *declared part tolerance* — **not**
  the uncertainty in whether 88 µH is the right centre value at all. A coil 30%
  off the assumed value would move the tank node ~30% and could cross 1 170 V.
  The bench LCR measurement in `docs/hardware/TANK_COIL_SPECIFICATION.md` §2
  closes this and is the single measurement that would make this determination
  solid rather than model-based.
- `RPAN = 10 Ω` is an inherited, uncited placeholder. A lower RPAN raises Q and
  raises the tank voltage.
- Startup and transient behaviour was not simulated — this is a 25-cycle
  steady-state deck. Pan removal during operation, pan drop-on, and PLL
  acquisition transients are not covered.

---

## 5. Blast radius — measured

kicad-cli 10.0.5, `--all-track-errors --format json`, `MaximumThreads=1` pinned,
against a scratch copy of the committed board (sha256 `6928b7c8…`, matching
`drc_ceiling.json`'s recorded input hash) with the regenerated `.kicad_dru`.
3 samples per variant. `pcb/**` never written.

**Baseline reproduces the committed record exactly** — clearance 386/386/386
(deterministic, as `drc_ceiling.json` records), creepage 183/184/183 (inside the
recorded 182–184 band), total errors 1263/1264/1263 against `error_ceiling` 1266.

| Variant | clearance | Δ vs 386 | creepage | total errors | vs `error_ceiling` 1266 |
|---|---:|---:|---:|---:|---|
| **Baseline (`HighVoltage` = 2.0mm)** | **386** | — | 183–184 | 1263–1264 | pass |
| `HighVoltage` → 3.0mm | 391 | **+5** | 184 | 1269 | **BREACH** |
| `HighVoltage` → 4.0mm | 393 | **+7** | 184 | 1271 | **BREACH** |
| `HighVoltage` → 6.0mm | 411 | **+25** | 182–184 | 1287–1289 | **BREACH** |
| `HighVoltage` → 20.0mm *(binding probe)* | 499 | +113 | 183–184 | 1376–1377 | — |
| **New `HighVoltageTank` class, `tank.c_tank1-p2` only → 3.0mm** | **386** | **0** | 182 | 1262 | pass |
| **… → 4.0mm** | **386** | **0** | 182 | 1262 | pass |
| … → 6.0mm | 387 | +1 | 181–182 | 1262–1263 | pass |
| … → 10.0mm *(binding probe)* | 399 | +13 | 181–182 | 1274–1275 | pass |
| … → 20.0mm *(binding probe)* | 462 | +76 | 182 | 1338 | — |

The 20mm probes exist to prove both levers actually bind — a variant that changes
nothing could mean "already compliant" or "rule never fired", and these
distinguish the two. Both bind.

**Ceiling impact.** `power_pcb_dataset/drc_ceiling.json` records
`violations_by_type.clearance = 386` and `error_ceiling = 1266`. Per that file's
own `_goal`, ceilings may only decrease; raising one needs a `Ceiling-Approval:`
trailer plus a fresh ≥120-sample measured-live record. **Any wholesale raise of
`HighVoltage` breaches both the clearance category ceiling and the aggregate**,
even the smallest step. The +25 figure at 6.0mm reproduces
`docs/evidence/2026-08-12-highvoltage-clearance-discrepancy.md:81` exactly, which
is a useful independent check that this harness matches the one that record was
taken with.

### 5.1 Is a separate netclass the right structure?

**Yes — and the measurement is unusually clean about it.** A `HighVoltageTank`
class carrying only `tank.c_tank1-p2` costs **zero** additional violations at up
to 4.0mm and +1 at 6.0mm, against +5 for the smallest wholesale raise. The
existing layout already provides ≥4mm around the tank node; it is the *other*
`HighVoltage` nets — bus, relay contacts, rectifier-side — that are packed
tighter, and those are the ones a wholesale raise would newly flag despite
carrying at most 400 V.

That is the structural argument stated in engineering terms rather than DRC
terms: **the `HighVoltage` class conflates a 340–400 V bus with a 924 V resonant
node, and 2.0mm is the correct figure for both only because they happen to share
one Table 16 step.** They do not share a Table 17 row (iv vs vi), which is
exactly why the creepage requirement in Sec 3.2 differs by two rows across nets
that carry the same class today. A class split is the right structure for the
creepage work whether or not the clearance figure ever moves.

**But note what this does and does not buy.** No clearance change is required by
this analysis. The class split matters for creepage, where the tank node needs
6.3–10.0mm and the bus nets need 4.0–6.3mm, and where nothing is enforced today
at all. Splitting the class to raise a clearance that is already adequate would
be exactly the unnecessarily strict global rule that makes placement
infeasible — this project has a documented history of that
(`docs/evidence/2026-08-11-pd2-decision-record.md:19-30`: PD3/12.6mm was
measured *not established feasible*, 196 violating pad-pairs, at least one
isolator UNSAT even after part substitution). Do not spend that budget on a
number that does not need to move.

---

## 6. Findings adjacent to the question, reported because this is a mains appliance

### 6.1 The primary-text record this determination rests on is not on `main`

`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` — the only file
in this project containing IEC 60335-1 Tables 15 and 16 and clauses
29.1/29.1.3/29.1.5 — **exists only at commit `880405ed9`**, on
`origin/feat/provable-safety-place-and-route` and two other unmerged branches.
`docs/evidence/2026-07-28-conformal-coating-pd1.md` is likewise only at
`7994ce7dc`. `scripts/generate_kicad_dru.py` cites both as if present, at lines
26, 33, 51, 62 and 159 — **dangling citations on `main`**. The clearance constant
this board is fabricated to therefore traces, on `main`, to a file that is not
there. Merging those two documents is a prerequisite for anyone auditing this
determination.

### 6.2 The OVC II / OVC III contradiction is unresolved and this analysis assumes OVC II

`scripts/generate_kicad_dru.py:56-63`, `docs/ENVIRONMENTAL_SPEC.md:46` and
IEC 60335-1 cl. 29.1's own text all give **OVC II → 1 500 V**.
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:86` and
`docs/evidence/2026-08-07-creepage-authority-and-pullback-analysis.md:133-137`
give **OVC III → 2 500 V**. Nothing reconciles them.

**This document uses OVC II / 1 500 V**, because that is what the standard's own
quoted text says for appliances and what the enforced constant is derived from.
**If OVC III were correct the answer changes:** V_det at the tank node becomes
2 500 + (923.7 − 169.7) = 3 254 V, which is above Table 16's 2 500 V step, giving
3.0mm basic + 0.5mm = **3.5mm required, and 2.0mm would be inadequate.** This is
the single input that most cheaply flips the verdict, and it is currently
ambiguous in the repo. A reviewer should settle it before relying on Sec 4.

### 6.3 `PWR_RTN` is HV-domain and has no netclass

`elec/domain_manifest.yaml:95` declares `PWR_RTN` an HV-domain net (*"power_return,
the doubler midpoint"*). It exists on the board as net 13. It has **no entry** in
`pcb/temper.kicad_pro`'s `netclass_assignments` — it falls to `Default`, 0.2mm.
`packages/temper-placer/src/temper_placer/core/design_rules.py:397` separately
maps it to `"GND"`.

Consequence: every DRU rule of the form `A.NetClass == 'HighVoltage' &&
B.NetClass == 'LV-ish'` — which is where the 8.0mm reinforced creepage and the
2.0mm HV↔LV clearance live — **does not fire for `PWR_RTN` against any SELV net**.
`PWR_RTN` sits at the doubler midpoint, is one Y-cap away from `gnd`/`pe`
(`elec/domain_manifest.yaml:502-505`), and carries the full tank return current.
Against SELV it is a mains-referenced conductor with a *reinforced* isolation
requirement, and it is currently checked at the generic 0.2mm floor.

This does **not** weaken any conclusion in this document — pairs where the other
side is `HighVoltage` still get 2.0mm, because KiCad takes the higher of the two
netclass figures. It is reported because the HV↔SELV barrier is the barrier that
protects a person, and this is a hole in it. It is a `netclass_assignments`
omission of the same species as the 23 corrections landed by
`scripts/sync_kicad_netclass_assignments.py` in the 2026-08-11 full sync, which
did not catch this one. **It should be verified and fixed independently of
anything in this document, and it warrants its own measurement** — adding
`PWR_RTN` to `HighVoltage` will move the DRC counts and the ceiling.

### 6.4 Nothing found suggests the board is unsafe *through the clearance mechanism*

To be explicit, because the brief asks: within the operating envelope the
protection system enforces, and on the OVC II reading, **the air-gap clearance on
this board is sufficient at every `HighVoltage` pair.** The hazards this analysis
did surface are (a) an unenforced creepage distance at the tank node, short by
3.2–5.0× (Sec 3.2), (b) an unconsidered high-frequency standard (Sec 3.3), (c) a
verdict that flips on an unresolved OVC ambiguity (Sec 6.2), and (d) an HV-domain
net outside the HV netclass (Sec 6.3). None of these is "2.0mm is too small".

---

## 7. Recommendations (none of them made in this PR)

1. **Do not change `HV_INTERNAL_CLEARANCE_MM` or the `HighVoltage` netclass
   clearance.** 2.0mm is correct.
2. **Do fix the reasoning attached to it.** The current comment derives 2.0mm
   from reinforced insulation at 1 500 V. Replace it with the clause 29.1.5
   derivation in Sec 3.1, which is what actually covers this board's worst pair,
   and record the 1 169.7 V ceiling the figure is valid to, so a future tank
   change is caught.
3. **Settle OVC II vs OVC III** (Sec 6.2) before treating Sec 4 as final.
4. **Open the creepage question for `HighVoltage`↔`HighVoltage`** (Sec 3.2): read
   clause 29.2.4, decide whether the functional-insulation exemption applies, and
   if it does not, size the tank node's creepage against Table 17 row vi. A
   `HighVoltageTank` class split is the right vehicle; Sec 5 shows it is
   affordable on clearance, and its creepage cost is unmeasured.
5. **Check IEC 60664-4** (Sec 3.3). Zero coverage today.
6. **Fix `PWR_RTN`'s netclass** (Sec 6.3), with its own re-measurement.
7. **Merge `880405ed9`'s and `7994ce7dc`'s evidence documents to `main`**
   (Sec 6.1).
8. **Bench-measure the coil** (Sec 4.4). It is the one measurement that converts
   this from a model-based determination into a real one, and it is already
   specified in `docs/hardware/TANK_COIL_SPECIFICATION.md` §2.

---

## 8. Reproduction

Circuit voltages (requires ngspice on PATH; this session extracted ngspice-42
from the Ubuntu noble package into a scratch prefix, no root):

```
# scratch copy of the committed deck + the .meas cards listed in Sec 2.2
cp simulation/harness/nets/zvs_margin_sweep.cir $SCRATCH/tankv.cir
# then sweep .param PAN_L1 / C_TANK / F_SW per the Sec 4.3 grid
ngspice -b $SCRATCH/tankv.cir
```

DRC (requires kicad-cli 10.0.5 at `/home/bennet/.local/opt/kicad-10.0.5`; note
`libspnav.so.0` is not in that prefix and must be supplied on
`LD_LIBRARY_PATH`):

```
# scratch copy of pcb/temper.kicad_pcb + .kicad_pro + regenerated .kicad_dru
python3 scripts/generate_kicad_dru.py          # writes pcb/temper.kicad_dru (gitignored)
kicad-cli pcb drc --all-track-errors --format json --output drc.json $SCRATCH/temper.kicad_pcb
```

with `KICAD_CONFIG_HOME` pointed at a throwaway settings tree carrying
`MaximumThreads=1`, per `temper_placer.validation._drc_api`.
