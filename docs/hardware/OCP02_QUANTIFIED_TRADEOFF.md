<!-- provenance: commit=34aba8599898a24b3986ea3f008e90da6ec0accc (worktree-agent-a2f38e19dbc923bc5,
     fast-forward merge of worktree-agent-a79e198a124568852 + worktree-agent-aaaac157441fa01a8
     onto origin/main), dirty=false except this file and the new simulation/evidence artifacts
     listed in SS1. pcb/temper.kicad_pcb, elec/src/*.ato, and docs/hardware/BOM.md NOT modified --
     every board mutation below ran against scratch copies outside the repo, never the committed
     file. -->

# OCP-02 — Quantified Tradeoff (Option A vs Option B)

**Date:** 2026-08-07
**Reads:** `docs/hardware/OCP02_DECISION_BRIEF.md` (the original A/B/C/D decision brief) and
`docs/hardware/OCP02_CT_PLACEMENT_FEASIBILITY.md` (the CT placement study), both merged into
this branch. This document does not repeat their derivations; it fills in the numbers both
explicitly left open.

**Task:** try to collapse OCP-02 to a dominant option, or prove it can't be, with every number
filled in. **Verdict, stated up front: Option A (second CT) is dominant, and the new evidence in
this document makes that conclusion firmer than the prior brief's, not weaker** — reversing the
placement study's own closing note that the tradeoff had become "genuinely live." Section 6 has
the full reasoning; sections 2-5 are the evidence.

---

## 1. What's new in this document, and where the artifacts live

- `simulation/harness/nets/ocp02_option_a_trip_point.cir`,
  `ocp02_option_a_frontend_delay_default_model.cir`,
  `ocp02_option_a_frontend_delay_bandwidth_estimate.cir`,
  `simulation/harness/run_ocp02_option_a_sim.py` — a working ngspice harness for a candidate
  Option A circuit, mirroring `run_ocp01_sim.py`'s pattern exactly.
- `docs/evidence/2026-08-07-ocp02-option-a-sim.json` — its output, `calibrated: false`, deterministic
  across 5 runs.
- A real `kicad-cli` DRC before/after measurement of Option A's ~44mm HV run (SS3), run against
  scratch copies of the board in `/tmp` — reproduction steps in SS3.5. Not committed to the repo
  (scratch board mutations, per this task's constraints), but every number below is from an actual
  tool run, not an estimate.
- Corrected/extended datasheet figures for the AMC1300 (SS4.1) and the isolated bias supply
  (SS4.2), read directly from the vendor PDFs this session.

---

## 2. ngspice: obtained, and what it could and couldn't measure

### 2.1 Getting ngspice

The prior brief could not install it (no root, `apt-get install` denied). This session confirmed
the same `apt-get download` + `dpkg-deb -x` + `LD_LIBRARY_PATH` technique other agents used for
`kicad-cli` also works for `ngspice`: `apt-get download ngspice` succeeds without root (it only
needs archive read access, not install privileges), `dpkg-deb -x <deb> <prefix>` extracts it
without touching the system, and `LD_LIBRARY_PATH=<prefix>/usr/lib/x86_64-linux-gnu ngspice -b
<deck>` runs it standalone. Version installed: **ngspice-42+ds-3build1** (Ubuntu noble/universe).
Not committed anywhere; this is a sandbox-local userspace install, reproducible by any future
agent via the same three commands.

The same technique, plus extracting five additional `libocct-*` packages (needed for `_pcbnew.kiface`
to load) got a working **`kicad-cli 10.0.5`** running too — the placement study's other blocked
tool. SS3 uses it for a real DRC measurement neither prior document could obtain.

### 2.2 Option A trip point — measured, real, matches spec

`run_ocp02_option_a_sim.py` reuses `current_transformer.sub`'s `CT_WITH_BURDEN` subckt and
`TLV3201_ngspice.lib` exactly as `run_ocp01_sim.py` does, with `N=100, R_BURDEN=4.99` reused
read-only from OCP-01's own committed burden, and a reference divider (`r_ref_top=1020,
r_ref_bot=10000`, **not committed to elec/** — sized here only to hit `SecondaryOCPComparator`'s
stated 60.0A target) — see the netlist header for the full derivation.

**Result, deterministic across 5 ngspice runs:** simulated trip current **60.03 A**, matching
`SecondaryOCPComparator`'s 60.0A nominal design target. Worst-case analytic corner sweep (±1% E96
tolerance + ±100ppm/°C tempco at ΔT=60°C, same method `run_ocp01_sim.py` uses): **58.89–61.17 A**,
inside the 55–65A spec window. `calibrated: false` — no bench measurement exists, same caveat every
other simulated figure in this repo carries.

### 2.3 Option A front-end delay — attempted, and its own negative result is the finding

This is the number the task asked me to "try harder" on, since it was never measured for either
option. I did measure something — but it's a **methodological limitation of the available model**,
not a delay figure, and reporting that honestly is more useful than a misleading near-zero number.

**What happened:** `CT_WITH_BURDEN`'s `F_xfmr` element is an ideal current-controlled current
source (CCCS). When the primary is driven by an ideal PWL current source — this repo's own
established convention, used by `ocp01_trip_point.cir` and this file's own trip-point deck — the
CCCS forces `v_out = I_pri(t)/N * R_BURDEN` **exactly and instantaneously** (the subckt's own
comment says as much: `"Output voltage = I_primary / N * R_BURDEN"`). `L_leak` and `R_wind`
(leakage inductance, winding resistance — the two parameters that would physically set a CT's
response time) sit in a separate branch (`sec_int -> L_leak -> sec_leak -> R_wind -> gnd`) that the
same ideal CCCS also drives ideally, so whatever voltage they develop is confined to internal nodes
nothing downstream reads.

**Confirmed empirically, not just by inspection:** two decks, identical except for `LL`
(100µH subckt default vs. 1µH bandwidth-back-derived estimate — see the netlist header for that
derivation) and `RW` (50Ω default vs. 1.54Ω, the real CST3015-100ED's published secondary DCR
max, Coilcraft Document 1608-1), against a 0→80A/50ns current step (edge rate sourced from this
repo's own `DESAT_REDESIGN_SPIKE.md:120`, the IKW40N120H3's datasheet current rise time — the
fastest real edge rate documented anywhere in this repo, used here as a deliberately fast, not
representative, stand-in since **no shoot-through-fault di/dt or rise-time figure exists anywhere
in this repo** — confirmed by search): **both decks produced bit-identical `t_trip` and
`v_sense_at_trip`** to full ngspice precision. `LL` and `RW` are dynamically inert at `v_out` for
any value, confirmed, not assumed.

**Practical consequence:** `simulation/models/current_transformer.sub`, used exactly as this
repo's own established harness convention prescribes, **structurally cannot produce a
non-trivial front-end propagation delay figure for a CT**, for any parameter choice. This is a
new, real limitation of the model this repo already has — not evidence the physical
CST3015-100ED is delay-free, and not something I attempted to fix by re-plumbing the model with
an invented fault-loop impedance (that would require a loop inductance/resistance figure that
doesn't exist anywhere in this repo — the closest are a **<20nH commutation-loop design target**,
a *different* loop, and a 2.5kV/µs dV/dt derating rule, neither a fault-current di/dt — inventing
one to force a delay measurement would be exactly the kind of fabrication this task prohibits).

**Fallback, explicitly not a measurement:** the same datasheet-bandwidth-derived
order-of-magnitude estimate the original brief used, made explicit rather than left as a "10x
pessimistic guess": t ≈ 0.35/BW. Coilcraft's real, verified datasheet for this part (Document
1608-1, fetched and read directly this session) states CST3015-100ED's frequency range as
**"0.78 kHz – >1000 kHz"** — open-ended above 1MHz, so 1MHz is used as a conservative *lower*
bound (the real corner, and the real rise time, could be faster, not slower). t ≈ 0.35/1MHz =
**~350ns**. Status: **datasheet-bandwidth-derived estimate, NOT measured, NOT a guaranteed
datasheet parameter** (the datasheet does not commit to an exact upper corner past ">1MHz").

**Total Option A budget, restated with this session's numbers:** 528ns (logic/driver cascade,
real datasheet arithmetic, `OCP02_DECISION_BRIEF.md` SS3.3, unchanged) + ~350ns (CT front-end,
datasheet-bandwidth estimate, this session) + 40ns (TLV3201 typ, datasheet, not a guaranteed max)
≈ **918ns, ~4.1µs (82%) margin** to the 5µs budget. Materially unchanged from the brief's own
"~930ns" pessimistic estimate — this session's contribution is an explicit derivation and a
confirmed structural reason ngspice can't do better, not a new number that moves the conclusion.

### 2.4 Option B — no model exists, and none was built

Confirmed again this session (grep, `simulation/models/`): no SPICE model for INA240, AMC1300, or
any isolated amplifier exists in this repo. One was deliberately **not** written. A first-order
RC/behavioral model tuned to reproduce the AMC1300's *own datasheet delay number* would be
circular — it would encode, not discover, the number already in SS4.1 below, at the cost of a new
uncalibrated model this task's own honesty rules require flagging as such. The real datasheet
numbers in SS4.1 are a stronger source of truth than a model built to match them would be.

---

## 3. Option A's real HV-run cost — measured with real `kicad-cli` DRC, not estimated

The placement study flagged the ~44mm HV run from U6's `DC_BUS_RTN` pad to the domain-safe CT
site (~89, 115) as a real cost but could not measure it (`#871`'s router doesn't complete, and
`kicad-cli` wasn't available to that session). It is now.

### 3.1 Method

A scratch copy of `pcb/temper.kicad_pcb` (never the committed file) got two additions, both real
board geometry, not a Shapely estimate:

1. **A second `CST3015-100ED` footprint**, cloned verbatim from T1's own real footprint block
   (identical pads/courtyard/silkscreen — the same part, so this reuses T1's own already-correct
   local-to-world pad geometry rather than introducing new rotation arithmetic), placed at the
   placement study's own cited candidate center (89.0, 115.0), same 90° rotation as T1. All 4 pads
   forced onto net 5 (`DC_BUS_RTN`) so creepage is checked against the whole candidate footprint's
   copper, not one pad.
2. **A straight-line 3.0mm-wide track** (width matches `HighVoltage` netclass `trace_width` in
   `packages/temper-placer/configs/netclass_rules.yaml`) from U6's real `DC_BUS_RTN` pad —
   `(89.17, 159.33)`, read directly from the board, matching the placement study's own figure — to
   the candidate site, length **44.33mm** (confirming the study's ~44mm estimate to two decimal
   places). **This is a naive, unrouted straight line, not a real router's path** — flagged
   explicitly in SS3.4.

A minimal, real `.kicad_dru` containing only the exact `"HV to LV"` rule
(`scripts/generate_kicad_dru.py:467-475`, copied verbatim: `A.NetClass == 'HighVoltage' &&
B.NetClass != 'HighVoltage' && B.NetClass != 'ACMains'`, clearance 2.0mm, creepage 8.0mm) was used
for both the baseline (unmodified) and modified board, so the comparison isolates this one rule's
delta rather than mixing in the full 10-rule generator's other categories.

**Nondeterminism control:** `power_pcb_dataset/drc_ceiling.json`'s own `_march` log documents
`creepage`/`clearance`/`shorting_items` as run-to-run nondeterministic on a byte-identical board
(120-sample ceiling protocol). This session ran **8 repeated DRC passes on each of the baseline
and modified boards** (not 120 — an exploratory sample, not a ceiling-grade one, stated as such)
and kept only violations present in **all 8 modified runs and none of the 8 baseline runs** — the
subset attributable to the change, not to kicad-cli's own noise floor.

### 3.2 Result: 9 new creepage violations, real and reproducible, 7 after one correction

| Category | Baseline (8 runs) | Modified (8 runs) | Stable new (in all 8 modified, none of 8 baseline) |
|---|---|---|---|
| creepage | 155–156 | 162–163 | **9** |
| clearance | 499–502 (507 once, noise) | 499–503 | 1 |
| courtyards_overlap | 11 | 13 | 2 |
| shorting_items | 199 | 199–206 | 13 |
| solder_mask_bridge | 154 | 180 | 14 |

**The 9 stable new creepage violations, in full:**

| Pair | Actual (mm, worst observed) |
|---|---|
| T99CAND pad3 (`DC_BUS_RTN`) vs. PS1 pad1 (`+170V_BUS`) | 5.21 |
| U6 pad2 (`SW_NODE`) vs. new track | 3.2 |
| T99CAND pad1 (`DC_BUS_RTN`) vs. `safety.ovp.r_div_top1-p2` track | 0.038 |
| U7 pad1 (`ina`) vs. new track | 5.86 |
| U7 pad14 (`hb.gate_hs.driver-p2`) vs. new track | 3.28 |
| U7 pad15 (`GATE_HS`) vs. new track | 4.55 |
| U7 pad4 (`gnd`) vs. new track | 2.05 |
| U7 pad6 (`hb.gate_hs.driver-p1`) vs. new track | 0.0 |
| U7 pad8 (`+3V3`) vs. new track | 0.0 |

**A new obstacle, not previously named:** 6 of the 9 are against **U7**
(`lib:SOIC16W_Isolated`, real part `UCC21550BDWK`, `hb.gate_hs.driver` — the high-side gate driver
IC), at `(85.91, 142.43)`, **22.05mm from U6** — almost exactly on the straight line between U6
and the candidate CT site. The placement study's own "what's near U6" table (R67/C15/J1/T1/R16)
did not include U7, even though its own methodology description names U7 as a "true isolator"
example in the same sentence as T1. This is not a contradiction of that study's *landing-site*
search (U7 may well already be respected by whatever exact point its domain-aware search
validated) — it is new evidence about the **corridor**, which that study explicitly flagged as
unmeasured ("a real before/after routing comparison... is not obtainable"). U7 is a poor candidate
for relocation: it is the gate driver, and needs to stay close to the half-bridge for gate-loop
inductance reasons (the same class of constraint `CRITICAL_LOOP_DESIGN.md`'s <20nH commutation-loop
target exists to protect) — unlike a small SELV sense resistor, moving it is not a low-cost lever.

**One correction to the exact placement claim:** the candidate footprint, placed at the literal
point the study cited (89, 115), **courtyard-overlaps two real components** (C26 and PS1) in real
DRC — not "legal, courtyard-clean" as the study's Shapely-based search concluded for that region.
This does not falsify the study's broader finding (a legal domain-safe slot exists somewhere in
this ~40–44mm neighborhood; PS1 in particular is a large through-hole power module, plausibly
missed or handled differently by their obstacle set) — but it means the exact point needs a small
re-verification/nudge with real DRC before being treated as final, not just a Shapely estimate.

**One likely false-positive, confirmed by checking the actual netclass resolution, not
assumed:** `pcb/temper.kicad_pro`'s `net_settings.netclass_patterns` maps `DC_BUS*` to
`HighVoltage` (matches `DC_BUS_RTN` correctly) but has **no pattern matching `SW_NODE` or
`+170V_BUS`** — both fall through to the `Default` netclass (checked directly against the real
JSON: `fnmatch` against every pattern, zero matches for either net). Since the `"HV to LV"` rule's
condition requires `B.NetClass != 'HighVoltage'`, both of these genuinely-HV nets are — incorrectly
— treated as the "B" (non-HV) side, meaning 2 of the 9 violations above (`SW_NODE` and
`+170V_BUS`) are likely artifacts of a **pre-existing, separate classification gap in this
board's own project settings**, not a real HV-vs-SELV creepage risk. This is a real, previously
unflagged finding worth a human's attention on its own, orthogonal to the OCP-02 decision — noted
here, not fixed here (`pcb/` is off-limits to this task). **Net attributable count: 7 of 9,** once
this gap is set aside.

### 3.3 Sizing the cost against the board's real DRC ceiling

The official ceiling (`power_pcb_dataset/drc_ceiling.json`) records **188** `creepage` violations
today (full 10-rule generator, KiCad 10.0.5, 120-sample protocol). This session's reduced
single-rule ruleset measured **155–156** baseline — lower, as expected, since it omits Rule 2's
("AC Mains to LV") creepage clause and others. Because the 9 (or 7, corrected) new violations found
here are specifically attributable to the **same, verbatim** `"HV to LV"` rule the real 10-rule
generator also emits, the same violations would appear against the full ruleset too: **the real
board's creepage ceiling would rise from 188 to approximately 195–197** if this change were made
as tested (naive straight-line trace, uncorrected placement point) — a real, attributable,
individually-explained delta, not a guess.

### 3.4 What this does and does not mean for "disqualifying"

The placement study's own closing cited the brief's conditional: *"if a second CT does not fit
without a routing regression at least as bad as the one T1 caused, switch to Option B."* T1's own
measured regression (`STRATEGY.md` Rung 1b) was a **routability** hit: −1.2pp completion rate,
+22 median shorting-items, from a component-body swap that also happened to reroute a denser
neighborhood.

What this session measured is different in kind: **9 individually-named, individually-explained
creepage flags** (7 after the netclass-gap correction), not an unexplained routability collapse.
`AGENTS.md`'s own DRC-ceiling process exists exactly for this: a **measured, attributed** rise —
naming the specific component/cause for each delta — is the thing that process is built to
approve (`Ceiling-Approval:` trailer + a new `_march` entry naming the cause + fresh
measured-live provenance), not something the process treats as automatically disqualifying. A
regression this well-attributed (U7 proximity, one exact-point re-placement, one pre-existing and
unrelated netclass gap) is a materially easier ceiling-raise case than T1's own — which is itself
the precedent the brief's conditional was calibrated against.

**What this measurement does NOT establish:** a naive straight-line trace is a pessimistic proxy
for routing cost, not a real router's output (`#871` still blocks getting one) — the
`shorting_items`/`solder_mask_bridge` deltas above (13, 14) are almost certainly **overestimates**,
since a real route would curve away from direct copper overlaps. The **creepage** count is a
different story: an 8.0mm standoff is a large fraction of the free space in this corridor (the
placement study's own figure: the candidate site's nearest SELV neighbor sits only 8.6mm away —
barely legal already), so routing around obstacles reduces direct shorts far more reliably than it
reduces creepage margin violations. Treat the creepage count as the more load-bearing of the two.

### 3.5 Reproducing this analysis

```bash
# ngspice (userspace, no root):
apt-get download ngspice
dpkg-deb -x ngspice_*.deb <prefix>
LD_LIBRARY_PATH=<prefix>/usr/lib/x86_64-linux-gnu <prefix>/usr/bin/ngspice -b <deck>.cir

# kicad-cli (userspace, no root) -- needs kicad.deb, kicad-footprints.deb, and its OCCT/wx
# dependency debs, INCLUDING libocct-visualization (provides libTKService.so.7 --
# missing from a base kicad+deps extraction, confirmed this session):
apt-get download kicad kicad-footprints libocct-visualization-7.6t64 <...other libocct-*, libwxgtk*, libgit2*, etc.>
dpkg-deb -x <each>.deb <prefix>
LD_LIBRARY_PATH=<prefix>/usr/lib/x86_64-linux-gnu:<prefix>/usr/lib <prefix>/usr/bin/kicad-cli pcb drc \
  --severity-error --format json --all-track-errors -o out.json board.kicad_pcb

# Scratch board mutation: clone T1's footprint block (balanced-paren extraction, tracking
# string literals so parens inside description text don't desync the count), retarget its
# `at`, tstamp, reference, and force all 4 pads onto net 5 "DC_BUS_RTN"; append a single
# `(segment ...)` from U6's real DC_BUS_RTN pad world position to the candidate site. Never
# write back to pcb/temper.kicad_pcb.
```

---

## 4. Option B's real risk — corrected part, typ-vs-max timing, temperature dependence

### 4.1 AMC1300 — typical vs. guaranteed-max, read directly from TI's SBAS895D this session

Fetched and read `SBAS895D` (May 2018, rev. May 2022) SS7.9–7.10 directly (not a search snippet).
The switching-characteristics table (SS7.10) is specified "over operating free-air temperature
range" — **MIN/MAX are guaranteed across the full −40°C to 105°C (AMC1300) / −55°C to 125°C
(AMC1300B) range; TYP is measured at 25°C only** (SS7.9's own header). This is the datasheet's
own temperature-dependence bound, not an extrapolation:

| Parameter | AMC1300 TYP (25°C) | AMC1300 MAX (full temp range) | AMC1300B TYP | AMC1300B MAX |
|---|---|---|---|---|
| 50%–10% delay | 1.5µs | 2.2µs | 1.0µs | 1.5µs |
| 50%–50% delay | 2.0µs | 2.7µs | 1.6µs | 2.1µs |
| **50%–90% delay** | **2.7µs** | **3.4µs** | **2.5µs** | **3.0µs** |
| Output rise/fall time | 1.3µs | (not specified) | 1.3µs | (not specified) |

**Budget, using the same 528ns logic/driver cascade + 40ns TLV3201-typ front end as the brief's
own arithmetic:**

- **Typical (25°C):** 2.7µs + 528ns + 40ns = **3.268µs total, 1.732µs margin (34.6%)**
- **Guaranteed worst-case (full −40 to 105°C range):** 3.4µs + 528ns + 40ns = **3.968µs total,
  1.032µs margin (20.6%)** — this is the brief's original "~21%" figure, now precisely
  reproduced and identified as specifically the *full-temperature-range guaranteed max* case, not
  an unqualified single number.

**The practical reading:** Option B has real margin at room temperature (35%), and the number
that actually worries the brief — ~21% — is what happens at the guaranteed extremes, not typical
operation. It remains true that this number **cannot be improved by a wiring or logic choice**: it
is intrinsic to the AMC1300's delta-sigma-modulator architecture (confirmed again this session,
reading the datasheet directly), so accepting Option B means accepting that its margin genuinely
shrinks under thermal stress, by a bounded and now-precisely-known amount (0.7µs, TYP-to-MAX
spread), not an unknown one.

### 4.2 The isolated bias supply — the brief's cited part doesn't meet the isolation requirement

`OCP02_DECISION_BRIEF.md` names `UCC14140-Q1` as "a plausible real candidate." Fetched and read
its datasheet (`SLUSET7`, June 2023) directly this session: **`UCC14140-Q1` provides only BASIC
isolation** — 5657-VPK per DIN EN IEC 60747-17, 3000-VRMS UL1577, basic per CQC GB4943.1. This
board's other reinforced HV↔SELV crossings (the CT, the AMC1300 itself) are all **5000Vrms
reinforced**. A basic-isolation bias supply on a reinforced-barrier crossing does not meet the same
standard the rest of Option B's own signal chain does.

**The correct part is `UCC14141-Q1`** (fetched and read `SLUSF10B`, Feb 2023, directly this
session) — same family, same package, same electrical specs, but **reinforced**: 7071-VPK per
DIN EN IEC 60747-17, **5000-VRMS UL1577** (matching the CT and AMC1300 exactly), reinforced per
CQC GB4943.1. Real, orderable MPN: **`UCC14141QDWNRQ1`**.

| | Value | Source |
|---|---|---|
| Package | SSOP, 36-pin | TI datasheet cover page, Device Information table |
| Body size (nom) | **12.83mm × 7.50mm** (96.2mm²) | Same table |
| Output (VDD−VEE) range | **15V to 25V only**, adjustable via external resistors | Same datasheet, Features |
| Output power | 1.0–1.5W depending on Vin | Same datasheet |
| Price | ~$8.91 (1-piece) | DigiKey search snippet — **same unverified-to-repo-standard caveat the original brief already applied to the AMC1300's $6.37 figure; not independently confirmed against the live product page this session** |
| Stock | **Listed out of stock / backorder** at the time of this search | Same search result |

**It still cannot produce 5V directly.** Its adjustable range floors at 15V (VDD−VEE) — this
matches the original brief's finding, now confirmed against the correct (reinforced) part's own
datasheet rather than assumed to carry over. AMC1300's VDD1 needs 4.5–5.5V. **A real subsystem,
not a component swap:**

- `UCC14141QDWNRQ1` (96.2mm² body + pads/keepout) + its own support passives (feedback resistor
  divider, input/output caps — visible in the datasheet's own "Simplified Application" schematic,
  ~4–6 small 0603/0805 parts).
- **One additional linear regulator**, sized to drop the module's ≥15V output to AMC1300's
  4.5–5.5V VDD1. Rough dissipation at the module's minimum 15V setting: (15V − 5V) × AMC1300's own
  max `IDD1` (9.8mA at VDD1 4.5–5.5V, from the AMC1300 datasheet's own table, SS4.1's source) ≈
  **98mW** — small, but a real added part with its own footprint and thermal margin, not folded
  into any existing regulator on this board.
- **Total added board area, rough order of magnitude:** the isolated DC/DC module + its passives +
  the added LDO is smaller in total footprint than a single `CST3015-100ED` courtyard (758mm²) —
  Option B's bias-supply subsystem costs *less* board area than Option A's CT, even after this
  correction. The area argument was never Option B's problem; its timing margin and part-chain
  complexity are.

**New failure modes, concretely, not generically:**

1. **A new single point of failure for the whole OCP-02 channel.** Loss of this one isolated
   supply (its own fault, a connector/solder issue, an upstream 12V-rail brownout) blinds OCP-02
   entirely — ironic for a circuit whose entire justification is redundancy against OCP-01's
   single points of failure (`OCP02_DECISION_BRIEF.md` SS6.3). Option A has no equivalent: a CT
   is passive and has no bias-supply dependency to lose.
2. **EMI proximity risk, not yet characterized for this layout.** The module is a real switching
   converter (CMTI >150kV/µs, spread-spectrum modulation — both real, datasheet-claimed
   mitigations, neither independently verified against this board's actual analog front-end
   layout this session).
3. **Startup sequencing.** AMC1300's own analog settling time is 500µs typ (its datasheet's own
   `t_AS` figure, SS7.10) after VDD1 becomes valid — a one-time dead-time at power-up during which
   OCP-02 cannot protect, that Option A's passive CT does not have.
4. **Availability risk, current as of this session:** the correctly-specified (reinforced) part is
   listed out of stock/backorder — a real, if possibly transient, procurement risk layered on top
   of an already-thinner timing margin.

---

## 5. Variant search — why nothing found here collapses the tradeoff

**Relocating SELV parts near U6:** already tried by the placement study (R67+J1 removed from the
obstacle set only recovers to ~41mm, because C15/R16/T1 and the rest of the RTD/safety
sense-resistor field still ring U6). This session adds a reason it can't get much better:
**U7 (the gate driver) sits almost exactly on the U6-to-candidate-site line, 22mm from U6** — and
U7 is a poor relocation candidate on its own terms (needs to stay close to the half-bridge for
gate-loop inductance, the same class of constraint that already drives this board's <20nH
commutation-loop target). Moving R67/J1/C15/R16 doesn't touch this specific new obstacle at all.

**A different sense point on `DC_BUS_RTN`:** reasoned through, not measured, but the topology
argument is tight. `DC_BUS_RTN` is one large copper pour (its own zone spans roughly the whole
board, per the placement study's own figure). For a CT to sense 100% of U6's shoot-through return
current — not merely "sit on the same net" — it must be spliced into a **dedicated, narrow neck**
of copper that carries *all* of that current and nothing else; anywhere else on the pour, current
would simply flow around the sensor through the rest of the plane. That means: wherever the CT
ultimately sits, a dedicated corridor from U6's specific pad to that point is required regardless
of which point is chosen — there is no sense point that avoids this cost, only ones that vary its
length. The placement study's own search (and this session's real-DRC follow-up) already found the
shortest such corridor available given the real, measured component density around U6. A
"different sense point" is not an independent lever; it is the same lever the placement study
already pulled.

**No variant found in this session collapses the tradeoff for either reason.**

---

## 6. Verdict

**Option A (second CT) is the dominant recommendation**, and this session's evidence strengthens
that conclusion relative to both prior documents:

1. **Timing margin is large and now more precisely bounded, not less.** ~918ns total (528ns real
   logic arithmetic + ~350ns datasheet-bandwidth CT estimate + 40ns TLV3201 typ) against a 5µs
   budget is **~82% margin**, and the CT front-end term — the only unmeasured piece — is a small
   enough fraction of the total that even a 10× error in that estimate (3.5µs) would still fit the
   budget. Option B's margin, by contrast, is a hard **20.6%** in its own datasheet's
   guaranteed-worst-case-over-temperature case (34.6% at room temperature) — a real number now,
   not "~21%" — and is intrinsic to the AMC1300's architecture, not improvable.
2. **The HV-run cost is now measured, not estimated, and it is bounded.** 7–9 new creepage
   violations (real `kicad-cli` DRC, 8-run-repeated, attributable and individually named — 6
   against a newly-identified U7 obstacle, 1–2 likely artifacts of a separate, pre-existing
   netclass-pattern gap this session also found and flagged), plus one placement-point correction.
   This is smaller and far better-understood than the T1 precedent (−1.2pp completion, +22
   shorting-items) the placement study's own closing worried about matching — and it is exactly
   the kind of measured, attributed delta this repo's own DRC-ceiling-approval process
   (`AGENTS.md`) exists to accommodate, not the open-ended regression that process is meant to
   catch.
3. **Option B's own cited bias-supply part doesn't clear this board's isolation bar.**
   `UCC14140-Q1` is basic-isolation only; the reinforced part that actually matches this board's
   other 5000Vrms crossings (`UCC14141-Q1`) is a real, correctly-identified substitute — but is
   currently out of stock, on top of Option B's already-thinner margin.

**What remains for a human to close before this is committed to `elec/`/`pcb/`:** the exact CT
landing point needs a small re-verification against real DRC (SS3.2's courtyard-overlap finding),
the reference divider needs the `REF2025` fix both this and the original brief flag, and the
44mm HV run needs a real router pass once `#871` is fixed to replace this session's naive
straight-line proxy with an actual routed cost. None of these are "does it fit" questions anymore
— they are implementation-detail follow-ups on a option this document now recommends building.

**What would change this answer:** if the exact CT site cannot be re-placed clear of C26/PS1
within roughly the same ~40–44mm envelope (i.e., if the true legal displacement is materially
larger than what the placement study found), or if a real router run (post-`#871`) shows the
44mm corridor costs meaningfully more than the T1 precedent once routed rather than naively
traced. Neither has happened in this session's evidence.
