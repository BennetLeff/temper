<!-- provenance: commit=610d09cf165a5d9128017a7018ff56ec6c8169bd dirty=false
     (branch analysis/output-rating-decision, cut from origin/main
     eb5022510d8f1272adf0a27d76c849aa2bb6e210, with fe9cf6752 cherry-picked
     as the input this builds on).
     pcb/temper.kicad_pcb sha256=26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
     -- verified before and after this analysis; the board file was never
     opened for writing.  NO clearance, creepage, copper-weight, loop-area,
     ampacity or DRU threshold was changed.  MIN_BARRIER_WIDTH_MM is untouched
     and is shown below to be UNCHANGED in every scenario anyway.  No elec/*.ato
     file was edited.  power_pcb_dataset/drc_ceiling.json untouched.  No
     _*_py_oracle.py touched, deleted or re-pinned.  No test skipped, xfailed,
     relaxed or allowlisted.  git stash never invoked.  No pushed history
     rewritten.  Two files are added: this document and its companion script. -->
---
module: power
tags: [power-input, output-rating, supply-scenarios, pfc, branch-circuit, creepage, regulatory, analysis-only, decision-input]
problem_type: engineering-analysis
---

# Decision table: what output rating is actually available, on which supply, and what each one costs

**This is an analysis. It changes nothing and decides nothing. `main.ato:494`
is left exactly as it is, because the correct value is the owner's choice and
§6 makes that choice mechanical.**

Reproduce with (pure stdlib; reads no repo state except the prior committed
evidence script; `make venv-isolate` **not** required — stated explicitly per
the task's environment rule):

```
python3 docs/evidence/2026-08-19-output-rating-decision-table.py     # ~18 s
```

---

## 0. THE DECISION TABLE

Every cell is a bracket across the same three bracket cases the prior
derivation used (`stiffest-line` η 0.92 / `central` η 0.90 / `softest-line`
η 0.85), and **every cell names the constraint that stops you.**

Columns are **cumulative**: (b) includes (a)'s fixes, (b+) includes (b)'s,
(c) includes (b)'s.

| supply | plug | rectifier | **(a) as it stands** | **(b) + cap/HF defects fixed** | **(b+) + rectifier uprated** | **(c) = (b) + PFC @ 0.95** |
|---|---|---|---|---|---|---|
| **120 V / 15 A** 60 Hz | NEMA 5-15P | doubler | **287–297 W**<br>`C_BUS×4 ripple` | **390–701 W**<br>`MUR1560 I_FRM` | **843–955 W**<br>`branch 15 A` | **1454–1573 W**<br>`branch 15 A` |
| **120 V / 20 A** 60 Hz | NEMA 5-20P | doubler | **287–297 W**<br>`C_BUS×4 ripple` | **390–701 W**<br>`MUR1560 I_FRM` | **909–1026 W**<br>`F1/L1 16 A` | **1550–1678 W**<br>`F1/L1 16 A` |
| **240 V / 15 A** 60 Hz | NEMA 6-15P | **bridge** | **329–342 W**<br>`C_BUS×4 ripple` | **642–1079 W**<br>`MUR1560 I_FRM` | **1588–1774 W**<br>`branch 15 A` | **2907–3146 W**<br>`branch 15 A` |
| **240 V / 20 A** 60 Hz | NEMA 6-20P | **bridge** | **329–342 W**<br>`C_BUS×4 ripple` | **642–1079 W**<br>`MUR1560 I_FRM` | **1717–1910 W**<br>`F1/L1 16 A` | **3101–3356 W**<br>`F1/L1 16 A` |
| **240 V / 30 A** 60 Hz | NEMA 6-30P | **bridge** | **329–342 W**<br>`C_BUS×4 ripple` | **642–1079 W**<br>`MUR1560 I_FRM` | **1717–1910 W**<br>`F1/L1 16 A` | **3101–3356 W**<br>`F1/L1 16 A` |
| **230 V / 16 A** 50 Hz | CEE 7/7 | **bridge** | **319–332 W**<br>`C_BUS×4 ripple` | **641–1059 W**<br>`MUR1560 I_FRM` | **1680–1841 W**<br>`branch 16 A` | **2972–3216 W**<br>`branch 16 A` |
| **230 V / 13 A** 50 Hz | BS 1363 | **bridge** | **319–332 W**<br>`C_BUS×4 ripple` | **641–1059 W**<br>`MUR1560 I_FRM` | **1309–1453 W**<br>`branch 13 A` | **2414–2613 W**<br>`branch 13 A` |

**Columns (b), (b+) and (c) are CONDITIONAL and none of them is available
today.** (b) depends on work two other agents have not landed and whose
outcome I was told not to assume — it is modelled from the physics as a
*what-if*, not reported as a result. (b+) and (c) additionally require BOM and
topology changes the owner has not agreed to. Only column (a) describes the
design that exists.

### 0.1 Three things this table says that the arithmetic alone does not

1. **The supply barely matters in column (a).** 287 W to 342 W across a 2×
   voltage range and a 2× current range. The reason is §1: the binding term is
   the 47 kHz tank current landing on the bus electrolytics, and *that current
   is set by the resonant tank and the pan, not by the mains.* **You cannot
   buy your way out of column (a) with a different wall socket.**

2. **240 V does not make 1800 W free, because the power factor gets *worse*,
   not better.** A bridge rectifier at 240 V draws a *narrower* pulse than the
   doubler does at 120 V: simulated conduction angle 29–43° vs 43–71°, and
   **PF 0.50–0.62 vs 0.59–0.76.** At 1800 W output the 240 V draw is
   **15.2–16.6 A rms**, which still exceeds a 15 A branch and still touches the
   existing 16 A fuse. The current halves; the *badness* of the waveform
   partly eats the gain.

3. **1800 W is reachable without PFC on exactly one of these rows** —
   240 V / 20 A, and only in column (b+), i.e. only after the capacitor bank,
   the HF bypass *and* the rectifier are all fixed, and even then the bracket
   is 1717–1910 W, so **the stiff-line corner still trips the 16 A fuse.**
   Making it unconditional needs F1/L1/K1 uprated from 16 A to 20 A as well.

### 0.2 The absolute arithmetic bound, for orientation only

`P_out = V · I · PF · η` at the physically unreachable `PF = 1.000`:

| supply | branch VA | ceiling at PF = 1.000, η 0.85–0.92 |
|---|---|---|
| 120 V / 15 A | 1800 | **1530 – 1656 W** |
| 120 V / 20 A | 2400 | 2040 – 2208 W |
| 240 V / 15 A | 3600 | 3060 – 3312 W |
| 240 V / 20 A | 4800 | 4080 – 4416 W |
| 240 V / 30 A | 7200 | 6120 – 6624 W |
| 230 V / 16 A | 3680 | 3128 – 3386 W |
| 230 V / 13 A | 2990 | 2542 – 2751 W |

**The declared 1800 W exceeds the 120 V / 15 A row's absolute bound.** That is
the prior derivation's headline and it survives unchanged: no topology, no
part, no PFC and no efficiency inside the repo's own bracket reaches it.

---

## 1. Why the supply hardly moves column (a)

The per-capacitor ripple has two terms. The prior derivation established that
the HF term is flat against capacitance and against PFC. **It is also flat
against the mains**, and for the same reason: `I_tank` at a given output power
is fixed by the tank and the reflected pan resistance (`P = I_tank² · R_eff`),
so it does not know what the wall socket is.

| tank variant | HF/cap at 1800 W | × the 2.70 A rating | HF term **alone** hits 2.70 A at |
|---|---|---|---|
| **committed** (20.7–22.5 A) | 4.89–5.31 A eq | 1.81–1.97× | **465 – 550 W** |
| superseded (35.4–40.0 A) | 8.36–9.44 A eq | 3.09–3.50× | 147 – 188 W |

Those ceilings are hard caps on column (a) **on every supply in the table**.
The remaining spread (287→342 W) is entirely the LF recharge term, which *is*
supply-dependent — a bridge at 240 V recharges twice per cycle into an
effective 1800 µF instead of once per cycle into 3600 µF, which is modestly
gentler.

### 1.1 A correction to the input derivation, and it moves column (a) by 2×

`fe9cf6752` took `I_tank(1800 W) = 35.4–40.0 A` from
`docs/evidence/2026-07-26-ocp01-vs-full-power-current.md`. **That document is
superseded in-tree.** `docs/evidence/2026-08-15-ocp-threshold-decision.md` §2
says so in as many words:

> "The interlocks audit's current-band numbers (35.4 A RMS / 50.0 A peak at
> R_eff = 1.44 Ω, 56.6 A peak at R_eff = 1.12 Ω) come from the **pre-coil-spec
> state of the repo**. The coil is now specified"

and gives the committed operating point as **22.5 A rms / 31.9 A peak**
(first-harmonic solve at R_eff 3.55 Ω), with this repo's own ngspice harness at
**20.7 A rms / 28.7 A peak**. The same table marks the 1.12 Ω back-calculation
that yields 40 A **"UNCITED, not corroborated."** 22.5 A rms is also the number
committed in `elec/src/modules.ato:585-593`.

Separately: **35.4 A is recognisable as `main.ato:625 i_ocp_trip_rms = 35.4A`,
the OCP *trip* level** — a protection threshold, not an operating current.

Consequence: the prior document's headline **146 W (133–158 W)** should read
**292 W (287–297 W)** on the same supply. I reproduce its 133–157 W exactly
when I feed it the superseded tank bracket (§7), so this is a difference of
input, not of method. **Its verdict is unaffected** — 292 W is still 6× short
of 1800 W, and the branch-circuit arithmetic that carries its conclusion never
touched the tank current at all.

**Both variants are carried side by side in the script and neither is blended
into the other.** The `committed` variant is used for every headline here.

---

## 2. What each scenario actually requires

### 2.1 The topology is forced, not chosen

- **≤130 V ⇒ doubler.** A bridge would give a ~170 V bus; the 47 kHz tank, the
  ZVS margin and the 1200 V half-bridge are all built around 340 V
  (`main.ato:49, 65-66`).
- **≥200 V ⇒ bridge.** A Delon doubler on 240 V produces **~680 V**.
  `main.ato:601` asserts `v_bus_max <= 400V`; the bus capacitors are 250 V
  parts. Not survivable, not arguable.

The standard way to keep one BOM is the classic **voltage-doubler / bridge
selector link** (link closed = doubler on 120 V, link open = bridge on 240 V),
which lands the same 340 V bus either way. That is a real option and it is why
the DC side is even a candidate for survival — but a mis-set link puts 680 V on
250 V capacitors, so it is a safety-critical selector and would itself need an
interlock or auto-sensing. **Named as an option; not recommended here.**

### 2.2 Does the BOM survive?

| item | 120 V / 15 A | 120 V / 20 A | 240 V (any) | 230 V (any) |
|---|---|---|---|---|
| **Rectifier D1/D2 MUR1560** | survives topologically; **I_FRM already exceeded** (col. b) | same | **needs 4 devices, not 2**; I_FRM still binds | same as 240 V |
| **Bus caps 4× 250 V EKMQ** | survives *voltage*-wise (two banks in series across 340 V either way); ripple already failing | same | **survives**, same 340 V bus | same |
| **MOV `V150LA10AP`, 150 Vrms** (`modules.ato`) | OK | OK | **MUST BE REPLACED** — 150 Vrms part on a 240 V line | **MUST BE REPLACED** |
| **X2 cap `B32922C3224M289`, declared 310 V** | OK | OK | **re-verify** the AC rating at 240 V; X2 parts are commonly 305 VAC, which is marginal-to-adequate — datasheet not read this session | **re-verify** |
| **F1 fuse 16 A, L1 CMC 16 A, K1 16 A IEC** | OK (branch binds first) | **BINDS at 16 A** — caps the 20 A branch to 1026 W / 1678 W | **BINDS at 16 A** in cols. b+/c | binds at 16 A ≈ branch |
| **NTC RT1 SL32 10015, 15 A** | OK | needs review at >15 A | inrush energy rises with V² — **re-derive**, 150 J is a 120 V sizing | re-derive |
| **AC inlet: Schurter 4798.9000 IEC C20, 16 A / 250 V** | OK | **16 A caps it** | **voltage OK**, 16 A caps it | OK at 16 A, caps 13 A row trivially |
| **IGBTs IKW40N120H3 (1200 V)** | huge margin | huge margin | **unchanged** — bus stays 340 V | unchanged |
| **Bleeders, Y-cap, gate drive, control** | OK | OK | Y-cap is a 250 VAC-class part; **re-verify** | **re-verify** |

Two BOM facts worth pulling out:

- **The inlet is already a 16 A / 250 V IEC C20 with a C19 cord**
  (`docs/CONNECTORS_AND_WIRING.md:13`). It is *voltage*-ready for every row in
  the table. It is also **not present in `elec/src/*.ato` at all** — the
  schematic has no AC inlet component — so the C20/C19 spec and `main.ato:56`'s
  `# NEMA 5-15 tolerance` have never been reconciled. Whichever row is chosen,
  that gap must be closed before it means anything.
- **The 16 A trio (F1, L1, K1-IEC) is the single most repeated blocker in the
  table.** It is what stops a 20 A branch from being worth having, on both
  120 V and 240 V. Uprating it is a small, self-contained change compared with
  anything else on this page.

### 2.3 The architectural cost nobody has priced: `power_return` stops being neutral

Today `power_return` (net `PWR_RTN`) **is the AC neutral**:
`modules.ato:918-919` wires `ac_n ~ cmc.W2_1; cmc.W2_2 ~ dc_bus.gnd_ref`, and
`gnd_ref` is the doubler midpoint and the tank return. `modules.ato:1024` then
bonds that midpoint to PE through a Y1 capacitor.

**On a bridge there is no neutral and no midpoint.** `power_return` becomes a
floating capacitor-divider tap sitting ~170 V below `hv_plus` and swinging with
the switching. That relocates:

- the net's own voltage class and therefore its netclass assignment,
- the Y-cap PE-bonding strategy and the touch-current budget that rides on it
  (§3.3),
- the ground architecture documented in
  `docs/hardware/SELV_ISOLATION_REDESIGN.md`,
- and the star-point reasoning in `main.ato:713` and `:750`.

**This is the largest hidden cost of any 240 V row, and it is a redesign of the
grounding architecture, not a part swap.** It is flagged, not solved.

---

## 3. Regulatory consequences

Provenance discipline: **IEC 60335-1 Annex L and IEC 60664-4 are paywalled and
were not obtained. Nothing below is reconstructed from them.** Every dimension
quoted comes from the repo's own verbatim recovery of IS 302-1:2008 (the BIS
identical adoption of IEC 60335-1) — Tables 15/16/17/18 — cited to file and
line. Where the standard is not in hand, the row says so.

### 3.1 Creepage — IEC 60335-1 Table 17, as recovered in-tree

Source: `packages/temper-design-bundle/src/safety_value.rs:505` (`TABLE_17`),
transcribed verbatim at
`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §3.3, and
cross-checked cell-for-cell against Broadcom's IEC 60664-1 reproduction. The
tables are **not interpolated** — a working voltage rounds *up* into its
bracket.

Material group IIIa/IIIb, **PD3** (the enforced classification per
`docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`; PD2 is conditional
on a sealed compartment this board does not have):

| working voltage bracket | applies to | Table 17 **basic** | **reinforced** (cl. 29.2.3: "at least double") |
|---|---|---|---|
| >50 and ≤125 V | **the AC-mains domain today (120 V)** | 2.4 mm | **4.8 mm** |
| >125 and ≤250 V | **the AC-mains domain at 230 V or 240 V** | 4.0 mm | **8.0 mm** |
| >250 and ≤400 V | **the 340 V DC bus, in every scenario** | 6.3 mm | **12.6 mm** |

**Consequences, stated precisely:**

- **`MIN_BARRIER_WIDTH_MM = 12.6` does not change in any scenario.** It is
  keyed to the >250–400 V bus, and the bus stays at 340 V whether the front end
  is a 120 V doubler or a 240 V bridge. The immutable constant stays correct on
  its own terms. (Confirmed against
  `packages/temper-placer/src/temper_placer/core/isolation_constants.py:47`.)
- **The `ACMains` netclass is what moves.** `constraints.ato:47-53` currently
  declares `v_max = 135V`, `creepage = 5.0mm`, `air_clearance = 3.0mm`. At
  240 V the working voltage crosses into the >125–250 V row, whose reinforced
  figure is **8.0 mm** — above the declared 5.0 mm. `v_max = 135V` would also
  have to move.
- The repo has already anticipated this: `packages/temper-drc-rs/src/
  router_clearance.rs` encodes `Mains120V = 4.8` and `Mains240V = 8.0`, exactly
  the doubled Table 17 rows above. **The 240 V figure is already in-tree and
  already agrees with the recovered table.**

### 3.2 Clearance — Table 15 → Table 16, and this one is board-wide

Clearance is *not* keyed to working voltage; it is keyed to **rated impulse
voltage**, which Table 15 derives from the supply voltage. `scripts/
generate_kicad_dru.py:92-98` already carries the derivation, flagged and not
silently applied:

> "**RATED-VOLTAGE CAVEAT** (flagged, not silently changed): the chain above is
> keyed to 120 V nominal (rated impulse 1500 V). **At 240 V nominal the chain
> (2500 V rated impulse → next step 4000 V = 3.0 mm + 0.5 mm) gives 3.5 mm**;
> the 2.0 mm figure is also a REINFORCED mains↔PELV derivation applied as this
> board's same-class HV↔HV internal floor."

So `HV_INTERNAL_CLEARANCE_MM` goes **2.0 mm → 3.5 mm** on any 240 V row, and
that applies to the *whole* HV domain, not just the mains nets, because the
rated impulse voltage is a property of the installation, not of a net.

**This is the single most expensive regulatory consequence in the table: a
75 % increase in the board-wide HV clearance floor is a relayout, and this
board's routing gap is already the subject of open work (`eb5022510`).** It is
not a component substitution.

### 3.3 IEC 60335-2-6 / 60335-1 clauses that key on the *rated input*

**Scope.** IEC 60335-2-6 covers appliances "their rated voltage being not more
than **250 V** for single-phase appliances connected between one phase and
neutral, and **480 V** for other appliances." A 230 V single-phase-to-neutral
appliance is in scope. A North-American **240 V split-phase** appliance has two
ungrounded conductors and no neutral, so it falls under the 480 V "other
appliances" limb and is also in scope. **No row in the table leaves the
standard's scope.** `[standard]`, sourced from the IEC webstore scope abstract
this session — the clause text itself is paywalled and was not obtained.

**The clause that actually moves with the rating** is the touch-current limit.
`docs/evidence/2026-07-30-c6-touch-current-budget-and-part2-routes.md:50`
carries it verbatim as CITED-PRIMARY:

> "stationary class I heating appliances: 0,75 mA **or 0,75 mA per kW rated
> power input** … whichever is higher" (maximum 5 mA)

| rated **input** | touch-current limit | note |
|---|---|---|
| ≤ 1.0 kW | **0.75 mA** | the floor binds — **no relief below 1 kW** |
| 1.2 kW | 0.90 mA | |
| 1.44 kW | 1.08 mA | |
| 1.5 kW | 1.125 mA | |
| **1.8 kW** | **1.35 mA** | as declared today (`elec/domain_manifest.yaml:913`) |
| 2.0 kW | 1.50 mA | |
| 3.0 kW | 2.25 mA | |

**Read this the right way round: dropping the rating TIGHTENS this limit.**
Going from 1.8 kW to 900 W cuts the allowed touch current from 1.35 mA to
0.75 mA — a **44 % reduction in Y-capacitor budget** — while the Y-cap that
spends it (`modules.ato:1024`) is unchanged. A rating cut is not free here.
Conversely a 240 V row at the same *input* power gets the same limit, but the
same Y-capacitance leaks roughly twice the current at twice the voltage.
**Neither effect is quantified against the as-built Y-cap in this analysis;
both are flagged.**

### 3.4 Plug, cord and marking

| supply | plug / cord | notes |
|---|---|---|
| 120 V / 15 A | NEMA 5-15P, 15 A/125 V, to the C19 cord | the installed base |
| 120 V / 20 A | **NEMA 5-20P** | a 5-20P **will not enter a 5-15R** — this is a *different* installed base, not a superset. Commercially this is close to a dedicated-circuit product. |
| 240 V (NA) | NEMA 6-15P / 6-20P / 6-30P | 6-series receptacles are rare in residential kitchens outside range circuits; typically an installation, not a plug-in |
| 230 V EU | CEE 7/7 | 16 A available on ordinary sockets |
| 230 V UK | BS 1363 | the **13 A plug fuse** binds, not the 32 A ring final |

Marking: `docs/REGULATORY_COMPLIANCE.md` §3.1 already specifies a rating plate
of **"1800 W (US) / 2000 W (EU)"** at "120 V AC (US) / 230 V AC (EU)".

### 3.5 Two committed statements that a scenario change would falsify

Both are dated, formal, and currently on the record:

1. `docs/cert-lab-inquiry-final-2026-08-16.md:40` tells a test house:
   **"120 V RMS ±10 %, 60 Hz only … max 15 A continuous; input ≤1900 W. No
   240 V variant is designed — the voltage-doubler exists specifically so no
   240 V input is needed."** Any 240 V row **retracts a submitted statement to
   a certification body.**
2. That same table lists **"Max output power 1.8 kW"** alongside **"input
   ≤1900 W"**. Those two are inconsistent with each other by the same
   arithmetic as `main.ato:494`: 1900 VA in, at the repo's η, is 1615–1748 W
   out at unity PF. **The 1800 W figure has been stated to a cert lab as an
   output while the input beside it cannot support it.**

And a third, internal: `REGULATORY_COMPLIANCE.md` §3.1 declares a **230 V /
2000 W EU rating plate** while the cert-lab letter says no 240 V variant
exists. **The repo already contains both answers to the question being asked
here.** Whichever row is chosen, one of these documents is wrong today.

---

## 4. The 80 % continuous-load rule — what it actually is

The prior agent labelled this `[uncited-standard]`. **It is now cited, but the
citation is a different section than the one the script's comment named, and
its applicability is genuinely conditional.** It stays out of every headline.

**What was located this session** `[standard]`:

- **NEC Article 100** defines a *continuous load* as one "where the maximum
  current is expected to continue for **three hours or more**."
- **NEC 210.20(A)** — where a branch circuit supplies continuous loads, the
  overcurrent device rating shall be not less than the noncontinuous load plus
  **125 %** of the continuous load. **210.19(A)(1)** applies the same 125 % to
  the conductors. 125 % of the load ≤ the rating is the same statement as
  load ≤ 80 % of the rating.
- **NEC 210.23(B)(1)** (2023 edition; 210.23(A)(2) in older editions) — "the
  rating of any one **cord-and-plug-connected utilization equipment not
  fastened in place** shall not exceed **80 percent of the branch-circuit
  ampere rating**." The commonly published worked example is a 1500 W / 120 V
  portable heater: 80 % of 1800 VA is 1440 VA, so it does not belong on a 15 A
  circuit.

**Which one applies to Temper, and the honest answer:**

- **210.23 is the sharper hook** and it is the one the repo's own single NEC
  mention already reached (`docs/reports/2026-08-07-parallel-session-index.md:
  314-318`, which names "NEC 210.23(A)'s 80 %-continuous-load rule for
  cord-and-plug-connected branch circuits (12 A cap on a 15 A circuit)"). A
  cord-and-plug countertop cooktop is exactly "utilization equipment not
  fastened in place."
- **But 210.23 governs *multiple-outlet* branch circuits.** On an *individual*
  branch circuit dedicated to the appliance it does not apply, and you fall
  back to 210.20(A), which then turns on whether a cooktop is a *continuous*
  load.
- **Whether a cooktop is a continuous load is not settled and I could not
  settle it.** The three-hour test is about *maximum current* continuing, and
  induction cooktops modulate hard. Practitioner discussion runs both ways.
  **I did not find an authoritative determination, and I am not inventing
  one.**
- **All three rules bind the installer and the branch circuit, not the
  appliance manufacturer** — except 210.23, which is written as a limit on the
  equipment's *rating* and is therefore the one that actually reaches a
  nameplate.

**Verdict: keep it labelled.** It is a real code section, correctly quoted,
whose applicability depends on a fact about the installation (multiple-outlet
vs individual circuit) and a fact about usage (three hours at maximum current)
that this project has not determined. The numbers below are carried
**separately and never folded into a headline**, exactly as the prior agent
did — the improvement is that the section number is now real.

**NEC-80 % ceilings, PFC assumed (PF 0.95), NA rows only** — no IEC equivalent
exists and none is invented:

| supply | I_cont | ceiling |
|---|---|---|
| 120 V / 15 A | 12 A | 1163 – 1259 W |
| 120 V / 20 A | 16 A | 1550 – 1678 W |
| 240 V / 15 A | 12 A | 2326 – 2517 W |
| 240 V / 20 A | 16 A | 3101 – 3356 W |
| 240 V / 30 A | 24 A | 4651 – 5034 W |
| 230 V / 16 A, 230 V / 13 A | — | **n/a — NEC does not apply** |

Note the 120 V / 15 A row: **1163–1259 W.** If this rule is held to apply, it
is a stronger constraint than anything in column (c) for the flagship
scenario, and it lands very close to where the market's honest products sit
(§5).

---

## 5. What the product *is* at each rating — MARKET CONTEXT ONLY

> **This section is `[market]`. It is separated deliberately, it played no part
> in any derivation above, and no number in §0–§4 depends on it. Read it after
> deciding, not before.**

Commercial 120 V single-burner induction cooktops are marketed at **1800 W**
with near-total uniformity — Duxtop P961LS, Abangdun, ANHANE, Chushifu,
ChangBERT and others all advertise "1800 W, 120 V, 15 A." Built-in 240 V
induction cooktops are a different product class: 30-inch units are commonly
**7200–8400 W total connected load** on a 40 A circuit, 36-inch units
**10 kW+** on 50 A.

**The one observation that matters for this decision, and it is a caution, not
a target:** the market's "1800 W" is derived the same way the repo's comment
derives it — 120 V × 15 A = 1800 **VA** — which makes it a **nameplate *input*
figure, not a delivered-to-the-pan output figure.** Vendor listings mix
"1800 W" with power *settings* ("power levels 100–1800 W"), so which quantity
is being marked is not consistently disclosed and **I could not establish it
from a nameplate photograph or a certification listing.** Treat this as
unresolved.

If the owner's intent was the market's convention, then the repo's variable is
misnamed rather than mis-valued: **1800 W belongs in an input variable**, and
`p_output_max` would be ≈ 1530–1656 W — and PFC becomes mandatory, because
drawing 1800 VA from a 15 A branch requires PF ≈ 1.0. That reading reconciles
the declared number with the market **and** with the physics, and it is the
only reading that does. **It is a hypothesis about intent, not a finding.**

Competitively: **287–342 W (column a) is not a cooktop, it is a warming
plate.** 850–950 W is a small single burner. 1450–1570 W is a credible 120 V
product. 1800 W on 120 V requires PFC and still lands at or above the branch's
honest ceiling.

---

## 6. `main.ato:494-495`, made mechanical

**Not fixed here. This section states what to write once the row is chosen.**

The defect: `p_output_max = 1800W` with
`assert p_output_max within 1500W to 1800W  # 15A circuit limit`. The value
sits at the **unreachable endpoint of its own assertion** — 1800 W out of an
1800 VA branch needs `PF × η = 1.000`.

There are **two** declarations, and both must move together, or the
inconsistency simply relocates:

- `main.ato:53` — `power_max = 1800W`
- `main.ato:494-495` — `p_output_max` + its assertion

Three further assertions gate any non-120 V / non-60 Hz row and are part of the
same mechanical edit:

- `main.ato:56` — `assert v_ac_nominal within 100V to 130V  # NEMA 5-15 tolerance`
- `main.ato:63` — `assert f_line within 59Hz to 61Hz  # US grid tolerance`
- `constraints.ato:10-12` — `ACMainsConstraints: v_max = 135V; i_max = 15A`

**What the assertion should say, per row.** The band should *bracket* the
chosen value across the η bracket, not straddle an unreachable end. Tank
variant `committed` throughout:

| supply | if (b) is the target, no PFC | if (c) is the target, PFC @ 0.95 | if the NEC-80 % line is honoured |
|---|---|---|---|
| 120 V / 15 A | `within 390W to 701W` | `within 1454W to 1573W` | `within 1163W to 1259W` |
| 120 V / 20 A | `within 390W to 701W` | `within 1550W to 1678W` | `within 1550W to 1678W` |
| 240 V / 15 A | `within 642W to 1079W` | `within 2907W to 3146W` | `within 2326W to 2517W` |
| 240 V / 20 A | `within 642W to 1079W` | `within 3101W to 3356W` | `within 3101W to 3356W` |
| 240 V / 30 A | `within 642W to 1079W` | `within 3101W to 3356W` | `within 3101W to 3356W` † |
| 230 V / 16 A | `within 641W to 1059W` | `within 2972W to 3216W` | n/a (IEC) |
| 230 V / 13 A | `within 641W to 1059W` | `within 2414W to 2613W` | n/a (IEC) |

† On 240 V / 30 A the NEC-80 % line (4651–5034 W, §4) is *weaker* than the
hardware, so the hardware governs and the two right-hand columns coincide.
Every other row's NEC column is the binding one of the two.

**And the comment must change too.** `# 15A circuit limit` is what made the
present line self-contradictory: it names a *VA* limit and then asserts an
*output power* against it. Whatever value is chosen, the comment should name
the binding constraint from the table — e.g.
`# bus-cap ripple + MUR1560 I_FRM, not the branch` — so the next reader cannot
repeat the mistake.

**If nothing else changes**, the only value consistent with the design as it
stands today is **column (a): `p_output_max = 292W`,
`assert p_output_max within 287W to 297W`**, with the comment naming
`C_BUS1/1B/2/2B` ripple current. Stating that is not a recommendation to ship
it; it is what the assertion would have to say to stop being false.

---

## 7. Cross-checks

| check | result |
|---|---|
| Reproduce `fe9cf6752` §1, 120 V/15 A central, 1800 W | prior: I_rms 26.61 A, PF 0.697, θ 58.0°, V_bus 292.4 V. **Here: 26.62 A, 0.696, 58.0°, 292.4 V.** |
| Reproduce `fe9cf6752`'s column-(a) headline on the superseded tank bracket | prior: 133–158 W. **Here: 133–157 W.** Method agreement; the 287–297 W difference is §1.1's input correction, nothing else. |
| Grid/step convergence, 2000→8000 samples & 30→60 cycles | I_rms moves 0.028–0.076 %, θ ≤ 0.05°, LF-equivalent ≤ 0.07 % |
| Lumped-tail spectral method vs exact 100-harmonic sum | agrees to **+0.00 %** on all three topologies; the lump uses the smallest divisor in the tail, so it errs conservative by construction |
| `pcb/temper.kicad_pcb` sha256 before / after | `26981fea…c110b` / `26981fea…c110b` — **identical** |

---

## 8. Provenance and honesty ledger

### `[repo]` — committed values, used as inputs
`main.ato:49,52-53,56,62-63,65-66,494-495,500-501,601,625`;
`constraints.ato:8,12,31-53`; `modules.ato:585-593,658,752,760-768,918-919,
1024`, MOV/X2 part numbers and ratings; `isolation_constants.py:47`
(`MIN_BARRIER_WIDTH_MM = 12.6`, read only); `generate_kicad_dru.py:92-100`;
`router_clearance.rs` `Mains120V/Mains240V`; tank operating point from
`2026-08-15-ocp-threshold-decision.md` §2; the three bracket cases, series
resistances and efficiency bracket inherited unchanged from `fe9cf6752`.

### `[datasheet]` — inherited from the prior derivation, not re-fetched
MUR1560 `I_FRM` 30 A / `I_F(AV)` 15 A; Chemi-Con KMQ 2.70 A rms @ 105 °C/120 Hz
and its frequency-multiplier table; TDK B82726S2163N030 16 A / 7.1 mΩ;
Schurter FST 16 A resistance; Ametherm SL32 10015 15 A / 150 J.

### `[standard]` — located this session, with section numbers
NEC Article 100 (continuous load, three hours); NEC 210.20(A) / 210.19(A)(1)
(125 %); **NEC 210.23(B)(1)** (80 %, cord-and-plug, not fastened in place);
IEC 60335-2-6 **scope** (250 V single-phase-to-neutral / 480 V other) from the
IEC webstore abstract. IEC 60335-1 Tables 15/16/17/18 are quoted **only** from
the repo's own verbatim in-tree recovery, cited to file and line in §3.

### `[estimated]` — never blended into a datasheet figure
Series-resistance bracket, K1 contact resistance 5–20 mΩ, PCB copper 3–15 mΩ,
external branch impedance 50–400 mΩ, MUR1560 knee/slope split — **all
inherited unchanged from `fe9cf6752`**, including its external-branch bracket
applied unmodified to the 240 V and 230 V rows, where a different installation
impedance would be more realistic. The verdicts are insensitive to it for the
same reason the prior derivation established.

### `[market]` — §5 only, never an engineering input
Commercial 120 V cooktop ratings and 240 V built-in connected loads, from
vendor listings. **Whether the market's "1800 W" is an input or an output
figure is UNRESOLVED**; that ambiguity is stated, not resolved.

### `[UNOBTAINABLE]` — named, not reconstructed
- **IEC 60335-1 Annex L and IEC 60664-4** — paywalled, not obtained. Nothing
  here derives from them. "Not obtainable" is the answer.
- **IEC 60335-2-6 clause text** — paywalled. Only the published scope statement
  is used. **Whether any 2-6 clause other than the touch-current rule keys on
  rated input is therefore UNKNOWN**, not "no".
- **IEC 60335-1 cl. 10 rated-input deviation tolerance** — not obtained; no
  tolerance figure is quoted anywhere above.
- **Whether a cooktop is a NEC "continuous load"** — no authoritative
  determination found. §4 says so plainly.
- **Bus-capacitor ESR, KMQ hotspot/life, Ametherm derating curve, D1/D2 case
  temperature, bench PF/η/θ** — unchanged from `fe9cf6752` §6.
- **X2, Y-cap and MOV datasheets at 240 V** — not read this session. §2.2 says
  "re-verify" rather than asserting a pass or a fail.
- **`R_eff`** — the reflected pan resistance, on which the entire
  current-vs-power mapping depends, is not computable from this repo and has
  never been measured. §1.1's correction rests on the repo's *committed* value
  for it, which is itself a first-harmonic solve, not a measurement.

### Falsifiers
1. *If the mains supply materially changed column (a), the "wrong problem"
   framing would collapse.* **Checked: false.** 287–342 W across every row —
   a 19 % spread against a 2× voltage and 2.3× current range.
2. *If 240 V improved the power factor, the current saving would be better than
   proportional.* **Checked: false, it is worse.** PF falls from 0.59–0.76
   (doubler at 120 V) to 0.50–0.62 (bridge at 240 V); the conduction angle
   narrows from 43–71° to 29–43°.
3. *If the superseded tank figure had been right, §1.1 would be noise.*
   **Checked: it is a 2× change in column (a)** — 146 W → 292 W central. Both
   variants are reported; neither is blended.

---

## 9. What is *not* claimed

No rating is recommended. No `.ato`, no PCB file, no threshold, no netclass,
no test and no oracle was modified. Columns (b), (b+) and (c) are conditional
on work that has not landed and on changes the owner has not approved, and are
labelled as such in every table they appear in. The 240 V rows are costed for
their *electrical* consequences and their *documented* insulation-coordination
consequences; the grounding-architecture redesign in §2.3 is identified but not
scoped, and the Y-capacitor and touch-current arithmetic in §3.3 is flagged but
not evaluated against the as-built part.

No instruction embedded in any repository file or tool output attempted to
redirect this task.
