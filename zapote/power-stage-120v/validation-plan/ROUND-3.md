# Validation round 3: closing the round-2 blockers

Part of the [master plan](00-MASTER-PLAN.md). Read the master plan's ground
rules (§2) and the [simulation runbook](SIMULATION-RUNBOOK.md) first. This
document doesn't replace the task documents (`01-…md` to `09-…md`): they keep
the goals and pass criteria. It says, for each item that round 2 left open,
**what exactly is missing, how to get it, and what to hand back.**

Written 2026-09-27 against the state of PR #1615 at `930387622`.

## 0. Before you start

- **Board:** `native-15/section.kicad_pcb`, SHA-256
  `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`
  (presentation revision). Its copper is identical to native-13's
  (`native-15/verification/README.md`), so copper extracted from native-13 in
  rounds 1–2 is still valid; record the native-15 hash in every new result.
- **C1/C2 are now KEMET R463N410000N1M** (22.5 mm pitch). The round-1 task 07
  stop condition is resolved.
- **The copper solver was fixed in round 3** (`validation-results/04-board-current-thermal/round3/README.md`):
  no false joins across gaps, drilled pads and vias modelled. Use 0.125 mm
  pitch on this board.
- Run `validation-plan/sim-kit/smoke_test.py` first. It must print
  `SMOKE PASS`. Then `04-current/sheet_solver.py --selftest` must print
  `SELFTEST PASS`.
- **One worker per task, one worktree each.** These tasks use Python,
  ngspice and KiCad Python only; don't run `cargo build` or a full workspace
  build in a task worktree. Use the prebuilt binaries named in the runbook.
- Results go in `validation-results/NN-<task>/round3/`, with the report
  template from master plan §4.

### Rules that apply to every item here

1. **A number without a committed source is not an input.** Every value you
   use comes from a datasheet (URL, revision, page, SHA-256 of the saved
   PDF), a committed script's output, or is labelled **ASSUMED** with the
   range you swept. Don't read values off a plot by eye; if you digitize a
   curve, commit the digitized points, the tool, and a stated reading
   uncertainty, and label the result **digitized, heuristic**.
2. **"Bound" means it bounds.** If you can't show that a value is a limit,
   call it an estimate or a bracket.
3. **Bracketing is allowed and encouraged.** If an input can't be pinned
   down, run the low and high ends of a justified range. If the verdict is
   the same at both ends, the verdict holds, and you say it holds *for that
   range*. If it flips, report the value at which it flips; that's the
   finding.
4. **Never change the board or the source.** Findings that need a design
   change go in the report as a recommendation.
5. **Stop and report** on any contradiction between the saved board, the
   netlist and a datasheet, as round 1 did for C1/C2.

## 1. Order of work

```
Wave A (start now, in parallel)       Wave B (needs Wave A)          Wave C
-------------------------------       ---------------------          ------
A1  01: ZVS threshold + edge rates    B1  01: board-bound grid        C1  07: DM/CM
A2  01: loop and gate inductances     B2  02: F2 at gate-off, F3          spectrum and
A3  02: stalls, overdrive, thresholds B3  04: thermal (needs A6)          margins
A4  04: electrical board solve        B4  05: ZVS map (needs A1)
A5  05: capacitor rating, shunt RMS,  B5  07: model inputs (A1, A6)
        trip ring-down, full grid
A6  03: loss and thermal budget
A7  07: X-cap/choke parasitics, deck
        topology
```

Owner decisions (§4) can run alongside. Nothing in Wave A waits for them.

---

## 2. Wave A: can start now

### A1. Task 01: minimum ZVS current and switch-node edge rate

**Why this is unblocked.** Round 2's complementary deck
(`validation-results/01-switching-parasitics/round2/complementary_leg.cir`)
works, but used reference inductances. Whether a transition completes before
the incoming device turns on depends mainly on the load current, the dead time
and the MOSFETs' output capacitance, not on the few-nH loop inductances. The
same holds for the switch-node dv/dt during commutation (≈ I / (2·Coss)). So
these two quantities can be found now **if you show they're insensitive to
the inductances.**

**Steps.**
1. Copy the round-2 deck and runner into `validation-results/01-switching-parasitics/round3/`.
2. Sweep load current I = 1, 2, 3, 4, 6, 8, 10, 15, 20, 37 A; dead time 348 ns
   (nominal); VBUS = 120, 170, 198 V; both directions (DIR = 0, 1).
3. For each case record: whether the incoming die VDS is ≤ 5 % of VBUS for the
   20 ns before its command (round 2's diagnostic), the time the switch node
   takes to swing 10 %→90 %, and the peak dv/dt.
4. Find the **minimum ZVS current** at each VBUS: the smallest I at which the
   transition completes in both directions. Refine between grid points by
   bisection to ±0.25 A.
5. **Inductance sensitivity (required).** Repeat the minimum-current search
   and the edge measurements at all inductances ×0.5 and ×3 of the round-2
   reference values. If the minimum ZVS current moves by more than 10 % or
   the edge rate by more than 20 %, say so: then A1 is not independent of A2,
   and B4/B5 must wait for B1.
6. Dead-time sensitivity: repeat step 4 at 250 ns and 450 ns.

**Hand back:** `zvs_threshold.json` (per VBUS, direction and dead time: the
minimum current and the bracket), `edge_rates.csv`, and the sensitivity
table. Evidence class: simulation/model-based, reference inductances,
sensitivity shown.

### A2. Task 01: board loop and gate inductances

**What's missing.** Round 1 found the plane pair doesn't overlap along the
whole path, so the simple formula `L = μ0·d·ℓ/w` can't give the loop totals
`LD_HS`, `LS_HS`, `LD_LS`, `LS_LS`, `LCS`. The gate-loop inductance `LG` and
the local-capacitor ESL (`LCAP`, TDK B32652A0104K000) are also missing.

**Primary method: field-solve the copper with FastHenry.**
1. Build FastHenry from source: <https://github.com/ediloren/FastHenry2>
   (the Linux/Unix `fasthenry` build compiles on macOS with the system
   compiler). Record the commit hash. If it fails to build twice, go to the
   fallback and say so.
2. Validate first: model a 10 mm × 50 mm plane pair at 0.5 mm spacing and
   a single straight wire, and match the analytic inductances within 5 %.
   Commit this as `scripts/test_fasthenry.py`.
3. Convert the native-13 copper for the commutation loop of each leg to a
   FastHenry input. Use the round-1 copper census
   (`validation-results/01-switching-parasitics/inputs/copper.json.gz`) and
   via list (`inputs/vias-and-pads.json`). Include:
   - In2 BUS_P and In1 HV_RET/LEG_RET planes as meshed planes (with their
     holes);
   - F.Cu/B.Cu pours and tracks on the path;
   - vias and through-hole barrels as segments between layers;
   - ports at the C38–C41 pads and at the MOSFET drain/source pins, and the
     R5 shunt pads.
4. Solve at 10 MHz (the edge content). Report each loop's total inductance,
   then split it into the deck's parameters. Explain the split; if a term
   can't be separated, assign the whole loop to one term and say which.
5. Gate loops: for each driver output → series resistor → gate pin, and the
   return from the source pin to the driver ground, solve the loop the same
   way. Report `LG` per device.

**Fallback (only if FastHenry can't be built): bracket.**
- Low end: the covered plane-pair terms from round 1 plus, for uncovered
  lengths, a trace over its nearest reference plane at its real height.
- High end: uncovered lengths as a wire pair at the real separation of
  outgoing and return conductors (larger than the plane-over-trace value).
- Label it **heuristic bracket**, not a bound.

**Local-capacitor ESL (`LCAP`).** TDK gives no number. In order:
1. Look for a TDK SPICE or S-parameter model of B32652A0104K000 (TDK's
   product page, "Models" or "Simulation" links). If found, fit ESL from its
   impedance above self-resonance.
2. Otherwise bracket it: **5–20 nH**, labelled ASSUMED, and run B1 at both
   ends. The owner can also request the value from TDK (§4, O3).

**Hand back:** `loop_inductance_fasthenry.json` (every loop, solver inputs,
mesh settings, convergence at two mesh densities within 5 %), the deck
parameter table, and the gate-loop table.

### A3. Task 02: stalls, small-overdrive delay, thresholds, F4/F5

**A3.1 ngspice stalls.** Three CT cases stalled (see
`validation-results/02-protection-timing/outputs/blocked_cases.json`): 10 MA/s,
10 A at 1 MA/s, and 39 kHz. Diagnose in this order, one change at a time,
on the stalled case only:
1. The primary source `min(I0+SLOPE*time,150)` has a kink where it hits
   150 A (at 10 MA/s, ~11 µs). Replace `min` with a smooth cap, for example
   `150*tanh((I0+SLOPE*time)/150)` applied to the envelope, or stop the
   transient before the cap is reached. Check whether the stall time matches
   the kink.
2. Set a maximum timestep in `.tran` (for example 5 ns) without changing
   `reltol`, `abstol` or `vntol`.
3. Smooth the behavioural comparator (a larger tanh width). Keep the width
   such that the output still switches within 1 ns of the ideal crossing.

After any change, **the smoke-test references must still pass**, and three
cases that completed in round 2 must reproduce within 1 %. If one of the
changes fixes the stall, rerun the full 108-case CT grid. Don't loosen
tolerances; if nothing works, report the case as still blocked with the logs.

**A3.2 Small-overdrive delay.** *Correction (round-3 result): the premise
below is wrong. The datasheet's 55 ns maximum is a step-response
specification at 20 mV overdrive and doesn't bound an arbitrary slow ramp.
Treat "20 mV + 55 ns" as a conditional extrapolation only; see
`validation-results/02-protection-timing/round3/README.md`.* The TLV3201's 55 ns maximum is specified at
20 mV overdrive (SBOS561C p. 5), but near the threshold the input moves far
less than 20 mV in 55 ns. Use this **bound**, which follows from the
datasheet alone:

> The comparator output has switched no later than 55 ns after the input
> first exceeds the threshold by 20 mV.

1. From the netlist, derive each path's gain at the comparator input in
   mV per ampere of primary current. Round 1 implies about 0.5 mV/A for the
   shunt (trip = 60.976 A − 2000·VOS) and about 15 mV/A for the CT
   (1.5 Ω / 100). Confirm both from the circuit, not from this note.
2. For each di/dt in the sweep, compute the current at which the input is
   20 mV past the threshold, the time taken to reach it, and add 55 ns.
   That's the bounded worst-case detection time and current.
3. Also give the round-2 model value (a constant 55 ns delay at any
   overdrive) as the **typical** figure. If the datasheet has a typical
   delay-vs-overdrive figure, you may use it for a typical value, but not as
   the bound.

**Expect:** the CT bound is tight (20 mV ≈ 1.3 A of primary current), and the
shunt bound is loose (20 mV ≈ 40 A). If the shunt bound exceeds a device
limit, that's a finding: the shunt path can't be shown safe from datasheet
data, only from the bench test.

**A3.3 Threshold spread and Monte Carlo.** Do step 1 of
`02-protection-timing.md` in full: the extreme-value worst case and a
100,000-sample Monte Carlo for OCP (shunt), the CT trip and OVP. Use the
datasheet tolerances and TCRs with citations. For the shunt's own heating,
use A6's R5 dissipation if it's ready; otherwise +50 °C, labelled ASSUMED.

**A3.4 F4 and F5.** These need datasheets, not simulation. For each
input/output on the chain (TLV3201, SN74LVC1G00/1G332, ISO7710 default-high,
UCC21550 DIS/EN, AO3400A permit FETs), cite the section that gives its state
when:
- the controller is dead with PWM stuck (F4);
- HOT5 falls slowly from 5 V to 0 V (F5): at which HOT5 voltage does each
  part stop guaranteeing its output, and is BUS_FAULT still asserted at
  every point on the way down?

**Hand back:** `stall_diagnosis.md`, `frontend_sweep.json` (full grid),
`overdrive_bound.csv`, `thresholds.json`, and an F4/F5 table with citations.

### A4. Task 04: electrical board solve

**Unblocked** by the round-3 solver fix. Follow runbook §7 exactly, at
0.125 mm pitch:
1. Run `validation-results/04-board-current-thermal/round3/scripts/kit_topology_native13.py`
   at 0.125 mm and require 0 spanning components before anything else.
2. For BUS_P, HV_RET, LEG_RET, SW_A, SW_B, RES_A and COIL_FEED: build the net,
   with through-hole pads as `filled=True` and vias as `filled=False`, and
   inject at the pads the task 04 document lists. Take the pad positions from
   the copper export, not from memory.
3. Currents: 15 A plus the HF share for BUS_P/HV_RET/LEG_RET (use 19 A as the
   round-1 assumption and label it); 18.7 A rms for the tank nets. When A5
   gives a better value, rerun.
4. Report R, I²R, the maximum current per mm of width per layer with its
   location, and every via's current. Flag any via above 3 A.
5. Convergence: re-solve BUS_P at 0.25 and 0.0625 mm (region only if memory
   is short). R must agree within 3 %.

The thermal half (B3) waits for A6's heat sources.

### A5. Task 05: capacitor rating, shunt RMS, trip ring-down, full grid

**A5.1 Capacitor current rating at 34–60 kHz.** CDE gives 10.3 A (0.22 µF)
and 9.2 A (0.1 µF) only at 70 °C/100 kHz. Round 2's full-power share was
**10.77 A** in C21/C22, so this matters. Derive the rating at the operating
frequency from the datasheet, if it gives enough data:
1. Look in CDE's 942C catalogue and on CDE's website for: dissipation factor
   (or ESR) vs frequency, the maximum hot-spot temperature, and thermal
   resistance (or the power the rating assumes). Save and hash every source.
2. If you have DF(f) and the thermal limit: the allowable current is
   `I = min( sqrt(P_max / ESR(f)), V_allow(f) · 2πf·C )`, where `V_allow(f)`
   comes from the voltage-vs-frequency curve. Show both terms.
3. If CDE doesn't publish enough, **stop this item**: the rating is BLOCKED
   on the owner's request to CDE (§4, O2). Don't scale the 100 kHz value.

**A5.2 Shunt (R5) RMS current, for task 03.** In a full bridge with the
shunt in the common low-side return, the shunt carries `s(t)·i_tank(t)`,
where `s = ±1` follows the bridge state. Ignoring dead time, its RMS equals
the tank RMS current. Compute it from the saved waveforms as
`sqrt(mean((s·i)²))`, state the derivation, and state the dead-time
correction (body-diode conduction of the low-side devices during dead time
also passes through R5). Give both the line-average and the crest-interval
RMS.

**A5.3 Trip ring-down topology.** Extend `tank.cir` so that at a trip time
all four gates are off and the tank current freewheels through the body
diodes into the bus capacitors (C5/C6 + C38–C41 with their tolerances; body
diodes from the Infineon model, or ideal diodes labelled). Trip from the
worst-case capacitor voltage in the grid. Report the bus peak (for B2's F3)
and the voltage left on C21–C23 afterwards, then the bleed time to 60 V.

**A5.4 Full grid.** Once A5.1 has a rating (or is formally blocked), run the
135-case grid (`find_freq.py` without `--limit`). If A5.1 is blocked, still
run the grid and report the currents, marking the capacitor verdict BLOCKED.

### A6. Task 03: loss and thermal budget

Not started. Follow `03-loss-thermal-budget.md`. What's new since that
document:
- Use A1's result for switching loss: in ZVS the turn-on loss is ≈ 0, and the
  turn-off loss comes from the complementary deck (integrate VDS·ID at the die
  over turn-off, at each current).
- Use A5.2 for the R5 current.
- Heatsink and pad: D2 has chosen the arrangement but not the insulating pad
  or the heatsink. **Compute the requirement**: the maximum pad-plus-heatsink
  thermal resistance that keeps Tj ≤ 125 °C at 50 °C ambient. Then evaluate
  **two representative pads** (for example a 0.23 mm silicone-fibreglass pad
  and a 0.15 mm polyimide/ceramic pad; cite the exact products and their
  datasheets). For each give Rth and **the tab-to-heatsink capacitance**
  `C = ε0·εr·A/d`, using the tab area from the IPW65R018CFD7 package drawing
  (cite the page). A7 and B5 need that capacitance.

**Hand back:** `losses.csv`, `board_heat_sources.json` (x, y, W per part, for
B3), `heatsink_requirement.md`, `pad_options.json`.

### A7. Task 07: X-cap and choke parasitics, deck topology

**A7.1 C1/C2 ESR and ESL.** KEMET publishes simulation data for film
capacitors through its K-SIM tool and product pages. Look for
R463N410000N1M (or the R46 1 µF 22.5 mm row) and fetch a SPICE model or
impedance/ESR data. Fit ESR and ESL from |Z|(f) above self-resonance. Save the
raw data and the fit script. If nothing is published, bracket ESL at
**10–30 nH**, labelled ASSUMED.

**A7.2 Choke L1 (B82726S2203A020).** The datasheet has a typical impedance
curve (p. 5) but no winding-capacitance number. Digitize the curve with a
committed tool and points, fit a parallel R-L-C (per winding) to it, and
label it **digitized, heuristic**. Report the fitted self-resonant frequency.
Also check TDK's website for a SPICE/S-parameter model first.

**A7.3 Deck topology.** Round 1 found two faults in `emi_transfer.cir`: the
CM source couples to the DC return instead of to PE through the heatsink, and
a single 1 V source can't show the anti-phase cancellation. Rewrite it:
- two switch-node sources, `sw_a` and `sw_b`, anti-phase trapezoids from 0
  to VBUS with A1's edge rates;
- each low-side tab (Q3 on `sw_a`, Q6 on `sw_b`) couples to the
  **PE-bonded heatsink** through its own `C_tab` (A6); the high-side tabs
  (Q2/Q5, on BUS_P) and BR1 couple the same way;
- the heatsink is bonded to PE; PE returns through the LISN's earth;
- add the MOV (capacitance from its datasheet), BR1 junction capacitance,
  the bus capacitors' ESL, and a coil-to-earth capacitance swept
  10–100 pF (ASSUMED);
- an **asymmetry sweep**: `C_tab` mismatch ±20 %, and edge-time mismatch
  ±20 % between the legs. The residual CM current depends on these.

Validate the new deck on a case with a known answer (for example, symmetric
tabs and edges must give near-zero CM at the LISN; one leg only must give
the single-source result). Add it to `smoke_test.py` only after it passes.

---

## 3. Waves B and C

### B1. Task 01: board-bound switching grid (needs A2)

Run the grid in `01-switching-parasitics.md` with the complementary deck and
A2's inductances (both ends of any bracket). Stop at the first failed
criterion. Halve the timestep for the reported peaks (< 2 % change). Report
VDS peaks against 520 V (normal) and 585 V (fault at 280 V), off-device VGS,
and die VGS.

### B2. Task 02: F2 current at gate-off and F3 bus peak (needs A3, B1, A5.3)

With the full CT sweep, the overdrive bound, and B1's turn-off waveform,
find the tank current when the gates are actually off, for the worst CT and
shunt corners. Compare with the IPW65R018CFD7 pulse current and the T1 rating.
F3: feed A5.3's returned energy and the real chain delay into
`tools/bus_voltage_sim.py` and compare the bus peak with the D3 clamp
coordination in `DC-LINK-CLAMP.md`.

### B3. Task 04: thermal (needs A4, A6)

The 2.5-D heat solve in `04-board-current-thermal.md` step 5, with Joule heat
from A4 and part heat from A6. First validate it against a uniformly heated
strip. Report the peak board temperature and every part above its rating.

### B4. Task 05: ZVS map (needs A1, A5.4)

At each grid case's switching instants, compare the current with A1's
minimum ZVS current at that bus voltage. Produce `zvs_map.png`: the fraction
of switching events that are ZVS, per case.

### B5 / C1. Task 07: spectrum and margins (needs A1, A6, A7)

Run the new deck at 35 and 60 kHz. Compute the LISN voltages, split DM and
CM, convert to dBµV (peak, labelled "peak, not QP"), and compare with the
47 CFR 18.307 table already saved in `validation-results/07-conducted-emi/sources/`.
Report the minimum margin, its frequency, the dominant mode, and which
parameter moves it most. A shortfall is a finding, not a failure.

---

## 4. Decisions and requests for the owner

The workers can't do these. Each is independent of Wave A.

| # | What | Why | Who acts |
| --- | --- | --- | --- |
| O1 | Choose the insulating pad and heatsink (completes D2) | A6 gives the requirement; A7/B5 need the real tab capacitance | Owner, after A6 |
| O2 | Ask CDE for the 942C12P22K-F / 942C12P1K-F current rating at 35–60 kHz and 70–85 °C | C21/C22 run at 10.77 A against a 10.3 A figure given only at 100 kHz | Owner (email to CDE applications), if A5.1 can't derive it |
| O3 | Ask TDK for the B32652A0104K000 ESL / self-resonant frequency | Local-capacitor ESL sets part of the switching overshoot | Owner, optional; A2 brackets it meanwhile |
| O4 | JLCPCB: can CTI ≥ 175 V (group IIIa) be guaranteed on the order? | Fab release gate (`FAB-JLCPCB.md`) | Owner |

## 5. What to hand back (every item)

- A README from the master plan §4 template, in
  `validation-results/NN-<task>/round3/`, with the native-15 board SHA-256.
- Every script, runnable as committed, and its outputs.
- A status line for the master plan §5 table: done / partial / blocked, and
  the reason in one sentence.
- For anything still blocked: exactly which input is missing, and the
  cheapest way to get it.
