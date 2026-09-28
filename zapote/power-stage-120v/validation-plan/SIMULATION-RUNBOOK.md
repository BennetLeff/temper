# Simulation runbook (tasks 01, 02, 04, 05, 07)

**Read this whole file before running anything.** It is the step-by-step
procedure for the simulation tasks in the [master plan](00-MASTER-PLAN.md).
The task documents (01, 02, 04, 05, 07) say *what* to find and the pass
criteria. This file says *how*, using the tested starter kit in
[`sim-kit/`](sim-kit/). The master plan's ground rules still apply. The key
ones:

- Don't change the board or source.
- Stop and report when blocked.
- Label evidence classes.
- Every number must come from a committed script.

All paths are relative to `zapote/power-stage-120v/` unless stated.

## 0. What is already known (2026-09-27)

- **Board:** `native-13/section.kicad_pcb`. The electrical record is
  `native-13/verification/README.md` (board `ce1cf636…`). The active file is
  the presentation revision (`8056fc95…`), with identical copper.
  **Record the SHA-256 of the file you read.**
- **Changes since the task docs were written:**
  - **Tank-CT detector:** added. T1 is burdened on-board by R39 (1.5 Ω) and
    C42 (100 nF). U10 and U11 trip at ≈55 A; U12 is the zero-cross; U13 ORs
    both CT trips with the isolated bus fault onto J4.10.
  - **Clamps:** D4/D5 are BAS116H.
  - **Permit/DIS network:** R14/R6 = 100 Ω and R16/R8 = 1 kΩ, which makes the
    PERMIT → DIS link fast.
  - **Task 02:** already has bounded delay sums in
    `validation-results/02-protection-timing/`. Your SPICE results must be
    compared against them.
- **Parts:** `frozen/default.csv` and `frozen/resolved-components.json`.
  **Nets:** `frozen/default.net`.

## 1. Setup (do this once, in order)

1. `cd validation-plan/sim-kit`
2. `./models/fetch_models.sh`
   - It downloads Infineon's official CFD7 650 V SPICE library and checks
     two SHA-256 hashes. It must print `OK`.
   - If the download or the hash fails, **stop and report**. Don't use a
     different model file.
3. `python3 smoke_test.py`
   - It must end with `SMOKE PASS`. It runs every deck with fixed inputs and
     compares against reference numbers.
   - **If any line says FAIL, stop and report the full output.** A different
     ngspice version or model file changes results.
4. **Tools:**
   - ngspice 45.2: `/opt/homebrew/bin/ngspice`.
   - Python: `python3` for the decks. Use `/Users/bennet/Miniforge3/bin/python3`
     for anything needing numpy, scipy, shapely or matplotlib.
   - KiCad Python for board reads:
     `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`.

### How to run a deck

```sh
python3 common/run_ngspice.py <deck.cir> NAME=VALUE ... [--keep DIR] [--raw]
```

- **Output:** JSON with `"meas"` (the deck's `.meas` results),
  `"aborted"`, `"failed"` and `"log_tail"`.
- **`--keep DIR`:** keeps the run directory. You can then rerun
  `ngspice -b <deck>` there by hand to see the full log.
- **`--raw`:** also saves every waveform to `DIR/waves.raw`. Load it in
  Python with `read_raw()` from `common/run_ngspice.py`. Transient values are
  floats; AC values are complex, so use `abs()`.

### Rules the kit already encodes (do not undo them)

| Trap | What happens | Kit's fix |
| --- | --- | --- |
| Infineon models need PSpice syntax | Parse errors | `.spiceinit` gets `set ngbehavior=psa` (the runner writes it) |
| Default solver options | "Timestep too small … trouble with node …g_g_rd_int1" at t = 0 | `common/options.inc` (gear, relaxed tolerances). Every deck includes it |
| Full load current at t = 0 | DC operating point fails at ≥ 61 A | The load current ramps from 0 over 1 µs; the event happens at T1 = 2 µs |
| `uic` | Internal model nodes start inconsistent and the run aborts | Never use `uic` with the MOSFET models |
| `.meas` with `v(a,b)` | "failed" | Use `par('v(a)-v(b)')` |
| `.meas ... PARAM='x-y'` that uses other measures | Fatal error in PSpice mode | Subtract in Python |
| `.meas` in AC | `vdb()`/`vm()` don't parse; `v()` gives the real part only | Use `--raw` and a post-processor (`07-emi/post_emi.py`) |
| `-r rawfile` in batch mode | ngspice disables `.meas` | The runner runs the deck twice when `--raw` is given |
| MOSFET pin order | Infineon subcircuits are **drain, gate, source** | Keep it |
| Package inductance | The L1 model already contains Ld 1.88 nH, Ls 2.82 nH, Lg 8.32 nH and Rg,int 2.7 Ω | Deck L parameters are **board copper and ESL only** |
| Pin vs die voltages | Pin-level VGS includes lead L·di/dt spikes (tens of volts) | Judge gate oxide and avalanche with the `*_die_*` measures (nodes `xq?.g`, `xq?.s`, `xq?.dd`) |
| Timestep | An unresolved edge under-reports overshoot | For any reported peak, halve the max step (`.tran 0.1n …`) once. The peak must change by < 2 % |

If a run aborts despite this, don't loosen tolerances further on your own.
Report the deck, parameters and the last 20 lines of the log.

## 2. Order of work

1. Task 01 step A: extract loop inductances from the board. Everything else
   uses them.
2. Task 01 step B: switching sweeps. Then task 02, which needs 01's inductances.
3. Task 05 (tank), in any order relative to 01/02.
4. Task 07 (EMI), which needs 01's edge times and task 03's pad choice (or
   the placeholders, marked as such).
5. Task 04 (copper current), which needs task 03's heat sources, or run
   Joule-only.

Commit after each task: the scripts, the result `README.md` and the raw
outputs, under `validation-results/NN-*/`, using the master plan's template.

## 3. Task 01: switching transient

### Step A: loop inductance from the board (analytic)

Write `validation-results/01-switching-parasitics/scripts/loop_inductance.py`:

1. **Dump the copper** with KiCad Python:
   `tools/copper_dump.py native-13/section.kicad_pcb /tmp/copper.json`.
   Items have `kind` (pad, track, via, zone), `net`, `layers`, `ref` (pads,
   e.g. `"Q3.2"`) and geometry.
2. **Find the pad centres** of the commutation loop for each leg:
   - Leg A: C38/C39 (the BUS_P pad and the HV_RET pad), Q2.2 (drain, BUS_P),
     Q2.3 and Q3.2 (SW_A), Q3.3 (LEG_RET), and R5 pads 1 and 4.
   - Leg B: the same with C40/C41, Q5 and Q6 (SW_B).
3. **Plane-pair sections.** For each straight run (for example C38's BUS_P pad
   → Q2.2 on In2 over In1's HV_RET), use `L = μ0·d·ℓ/w`:
   - `d` is the dielectric between the two conductors. In1–In2 is 0.5 mm, and
     F.Cu–In1 is 0.4355 mm (`stackup.json`).
   - `ℓ` is the pad-centre distance.
   - `w` is the overlap width. Take it with shapely: the width of the
     intersection of the two nets' filled zones, perpendicular to the path, at
     its narrowest.
   - μ0 = 4π·10⁻⁷ H/m.
4. **Vias** in a current path: `L ≈ (μ0·h/2π)·(ln(4h/d) + 1)`, with h = the
   via length and d = the drill. Banks of n vias act in parallel (divide by n).
5. **Capacitor ESL** comes from the TDK datasheets (B32652A0104K000 for the
   0.1 µF local caps). Download them and put the file and hash in `sources/`.
6. **Write `outputs/loop_inductance.json`:**
   - one entry per term, with its source
   - a **low / nominal / high** total per leg, where low = 0.7 × nominal and
     high = 1.5 × nominal, unless you measured better
   - the split into the deck parameters LD_HS, LS_HS, LD_LS, LS_LS (board
     copper on each side of each device), LCAP and LCS (the part of LS_LS
     shared with the driver return: driver U1.9 → Q3.3, U2.9 → Q6.3)
7. **Gate loops, the same way:** trace over plane,
   `L ≈ μ0·h·ℓ/(w + 2h)`, driver pin → series resistor → gate pin → back via
   the source return. The lengths are in
   `native-06/verification/gate-lengths.json`; re-measure them on native-13.
   Output the per-gate LG.

Sanity check: the leg's total board loop should come out at a few nH to a
few tens of nH. If you get < 1 nH or > 100 nH, recheck units (mm vs m) before
continuing.

(Optional step A2: build FastHenry2 from https://github.com/ediloren/FastHenry2
for a field-solver cross-check. Skip it after two failed attempts and say so.)

### Step B: sweeps with `01-switching/leg.cir`

Parameters (defaults in the deck header) and their meaning:

| Parameter | Meaning |
| --- | --- |
| VBUS | DC bus voltage |
| IL | Load current at the switching instant |
| EVENT_ON | 0 = low side turns off (overshoot); 1 = low side hard turn-on (reverse recovery) |
| LD_HS, LS_HS, LD_LS, LS_LS, LCAP, LBULK, LCS | Board inductances from step A |
| LG | Gate loop inductance |
| RG | 3.9 Ω (R10/R12/R18/R20) |
| ROL / ROH | 0.55 / 5 Ω (UCC21550 SLUSE89C) |
| CSNUB | 1 nF (C12/C13/C19/C20) |

Write `scripts/sweep_01.py`. It loops over the grid below, calls
`common/run_ngspice.py` (import `run()` from it), and writes one CSV row per
run with every `meas` value plus the inputs.

- **VBUS:** 170, 198, 280
- **IL (EVENT_ON = 0):** 10, 20, 37, 61, 71
- **IL (EVENT_ON = 1):** 2, 5, 10, 20
- **Inductance corner:** low, nominal, high (all L values scaled together)
- **LG:** from step A, then ×0.5 and ×2

That's 3 × (5 + 4) × 3 × 3 = 243 runs, at about 0.3 s each.

**Read the results against task 01's criteria:**

| Criterion | Measure |
| --- | --- |
| VDS limits | `vds_ls_die_pk` (EVENT_ON = 0) and `vds_hs_die_pk` (EVENT_ON = 1), against 520 V (normal) and 585 V (fault turn-off at 61/71 A, 280 V) |
| False turn-on | `vgs_hs_die_max` (EVENT_ON = 0) and `vgs_hs_die_max` of the off device (EVENT_ON = 1), against VGS(th) min minus 0.5 V. Get VGS(th) min from the IPW65R018CFD7 datasheet, and record page and table |
| Gate oxide | `vgs_*_die_min/max` within the datasheet VGS limits |
| Edge rate | `sw_edge_s` is the 20–80 % time; use the absolute value (it's negative for falling edges). It goes to task 07 |
| Energy | `e_ls_j`, the LS switching energy per event. It goes to task 03 |

**Expect the reference cases to look like this.** With the deck defaults,
which are placeholder inductances:

| Case | Result |
| --- | --- |
| EVENT_ON = 0, IL = 37 A | `vds_ls_die_pk` ≈ 226 V at 198 V bus |
| EVENT_ON = 0, IL = 61 A | ≈ 283 V |
| EVENT_ON = 1, IL = 20 A | `vds_hs_die_pk` ≈ 554 V. That's the hard-commutated body-diode spike ZVS is meant to avoid |

If your board inductances give much lower numbers, fine. If they give
EVENT_ON = 1 peaks above 585 V, that is a **finding**: report the light-load
current range where ZVS is lost (from task 05) and the resulting spike.

**Timestep check (required).** Re-run the three worst cases with the deck's
`.tran 0.2n` changed to `0.1n` (copy the deck under `scripts/`). Report the
change.

**Plots.** Use `--raw` for the worst EVENT_ON = 0 and EVENT_ON = 1 cases.
Plot `v(sw)`, the die VDS/VGS (`v(xql.dd)-v(xql.s)` and so on) and `i(vids)`
against time with matplotlib (Miniforge Python). Save PNGs to `outputs/`.

Out of scope for this deck: the full tank load (use task 05), temperature
(the L1 model runs at 27 °C; the L3 model adds self-heating and is optional),
and distributed layout effects.

## 4. Task 02: protection timing (SPICE part)

The bounded delay sums already exist in
`validation-results/02-protection-timing/`. This step replaces the analog
front-end parts of that budget with simulation. Keep the digital links (logic
tpd, the PERMIT path, the driver) from `scripts/detector_chain.py`, updated
to the native-13 values (R14 = 100 Ω, R16 = 1 kΩ). That script already
computes both the old and the new values.

### Tank-CT path: `02-chain/ct_frontend.cir`

- **Primary current:** `(I0 + SLOPE·t)·sin(2π·FREQ·t)`.
- **Measures (absolute times):**
  - `t_ip_trip`: the primary first reaches ITRIP = 55.17 A
  - `t_pos_trip`: U10 output rises
  - `t_or`: the OR output rises
  - `t_ip_zero` / `t_zc`: the third rising zero crossing and U12's edge
- **Delays:** compute them in Python as `t_or - t_ip_trip` and so on.
  **Negative polarity:** if the negative comparator fires first, `t_or` is
  earlier than `t_ip_trip`. Define the trip reference as the first time
  `|i| ≥ ITRIP`. Get it from `--raw`, or add
  `.meas tran t_in_trip WHEN v(ipri)=-{ITRIP} FALL=1` to a copy of the deck,
  and take the earlier of the two.
- **Sweep:**
  - FREQ: 33k, 39k, 60k
  - I0: 37 (full power), 10 (light load)
  - SLOPE: 1e6, 3e6, 1e7 A/s (the fault growth rate; 2.8e6 ≈ 198 V/70 µH)
  - VOS: −4 mV, 0, +4 mV (TLV3201 offset over temperature)
  - TPD: 45n, 55n
- **Report:** detection delay, the primary current at `t_or`, and the ZC lag
  in ns and in degrees (`lag·FREQ·360`).
- **Cross-check:** the bounded calculation says a 1.5° lag at 33 kHz from C42
  plus 55 ns comparator delay. The reference run gives about 194 ns at 35 kHz.
  Explain any difference over 20 %.

### Shunt path: `02-chain/ocp_frontend.cir`

- **Current:** the leg current ramps at SLOPE.
- **Measures:** `t_i_trip` (the current reaches 61 A) and `t_ok_low` (U6
  output falls). The delay is `t_ok_low − t_i_trip`, and the current at
  detection is `SLOPE × t_ok_low`.
- **Sweep:**
  - SLOPE: 1e6, 3e6, 1e7, 1e8, 1e9 A/s
  - VOS: ±5 mV (U6 at 5 V; see the datasheet table at 5 V)
  - TPD: 55n
- **References:** 3e6 → about 547 ns and 62.6 A; 1e8 → about 493 ns and
  110 A.

### Total chain and verdict

**Total = front-end delay (from SPICE) + downstream links.** The downstream
links are in `detector_chain.py`: the OR/NAND/isolator tpd, the harness, the
interlock logic, PERMIT → DIS (native-13: 100 Ω / 1 kΩ), the driver
tPD_DIS, and the gate discharge. Replace the gate discharge with task 01's
simulated turn-off time where you have it.

For each fault scenario in task 02's table, compute the current at gate-off
and compare it with the limits there (T1 88 A, ID,pulse, task 01's VDS at
that current).

Don't re-derive the driver interlock. It's already quoted: with RDT = 39 kΩ,
the UCC21550 forces both outputs low when both inputs are high. F1 (hard
shoot-through) is answered by that quote.

## 5. Task 05: tank envelope with `05-tank/tank.cir`

The deck drives an ideal ±Vbus square wave into R-L-C over one 60 Hz
half-cycle (Vbus = |Vpk·sin|, unfiltered bus).

- **Parameters:**
  - VRMS
  - FREQ
  - LLOAD: the loaded coil inductance
  - RPAN40: the pan resistance at 40 kHz, scaled by √(f/40k) inside the deck
  - RCOIL
  - CRES = 0.54 µF
- **Pan and coil ranges** for the 70 µH coil, from
  `docs/hardware/power-section-120v/coil_mc.rs`:

| Parameter | Formula | Range |
| --- | --- | --- |
| LLOAD | 70 µH × kl | kl from 0.58 (low-R Silargan-like) to 0.90 (offset/small pan) → 40.6–63 µH |
| RPAN40 | 70 × r40 | r40 from 0.012 to 0.052 Ω/µH → 0.84–3.64 Ω |
| RCOIL | 70 × q | q 0.0015–0.0060 → 0.105–0.42 Ω |

  Use pan-class pairs from the `PANS` table in `coil_mc.rs`:
  - cast iron: kl 0.74–0.86, r40 0.036–0.052
  - carbon/430 steel: kl 0.66–0.80, r40 0.029–0.041
  - tri-ply (a guess): kl 0.66–0.82, r40 0.018–0.032
  - Silargan-like: kl 0.58–0.68, r40 0.020–0.029
  - offset/small: kl 0.80–0.90, r40 0.012–0.022

  Run each class's low-L/low-R, mid and high-L/high-R corners.
- **Operating frequency** is set by power. For each pan and line voltage (108,
  120, 140 V rms), find FREQ between the resonance and 60 kHz where `p_avg`
  equals the target by bisection:
  - targets: 1,710 W (full power), 855 W and 300 W
  - write `scripts/find_freq.py` using `run()`
  - never go below resonance, `1/(2π√(LLOAD·CRES))`; stay on the inductive
    side
  - if full power can't be reached above resonance within 60 kHz, record
    "power-limited", as coil_mc.rs does
- **Record per case:**
  - `i_rms`, `i_pk`, `vc_pk`, `vc_rms`, FREQ
  - with `--raw`: the tank current at the switching instants (sample
    `i(vim)` where `v(drv)` crosses 0), which is what ZVS needs. ZVS holds
    if that current has the right sign and is ≥ task 01's minimum ZVS
    current, taken from EVENT_ON = 1 runs where the spike disappears
- **Reference:** the deck defaults (120 V, 35 kHz, 50 µH, 2.0 Ω, 0.25 Ω) give
  `i_rms` ≈ 32.4 A, `vc_pk` ≈ 547 V and `p_avg` ≈ 2.23 kW. The defaults are
  above the target power, which is expected.
- **Criteria:** task 05's table.
  - Resonant capacitor voltage and current use CDE 942C curves at the
    operating frequency; download them and record the source.
  - T1 88 A.
  - Bleed resistors R22–R25 see V_Cpk/4 each against the 1206 working voltage.

## 6. Task 07: conducted EMI with `07-emi/emi_transfer.cir`

The approach is transfer function × source spectrum. A long switching
transient is too slow for 150 kHz–30 MHz resolution.

1. **Fill the FILL_ME values** in a copy of the deck, from datasheets saved to
   `sources/`:
   - L1 B82726S2203A020: common-mode inductance, leakage (DM) inductance,
     winding capacitance (from its impedance curve's self-resonance) and
     resistance
   - X capacitors R463N410000N1M (native-15; was R463R410000M1M): ESR and ESL
   - CPE: the switch-node-to-heatsink capacitance through the TO-247 tab
     insulating pad, `ε0·εr·A/d`. Take the exposed tab area A from the
     PG-TO247-3 package drawing in the IPW65R018CFD7 datasheet (record the
     page), and the pad from task 03, or two representative pads.

   The defaults are placeholders, and any result using them must say so.
2. **Run DM (MODE=0) and CM (MODE=1)** with `--raw`, then `07-emi/post_emi.py
   <run dir>`, which gives `lisn_l_db` and `lisn_n_db` per 1 V of source.
   Reference with placeholders: DM −39 dB at 150 kHz; CM −54.6 dB at 30 MHz.
3. **Source spectrum.** For a trapezoid switch node with amplitude V (the bus),
   switching frequency f_s, duty 0.5 and rise time t_r (task 01's
   `sw_edge_s` ÷ 0.6 for 0–100 %), the harmonic envelope is:
   - flat at `2·V·D` up to `1/(π·D·T)`
   - −20 dB/dec up to `1/(π·t_r)`
   - −40 dB/dec beyond that

   For CM, the source is each switch node's voltage (sw_a and sw_b: the
   low-side tabs are on the switch nodes) coupling through CPE. For DM, the
   source is the bus ripple current × bus-capacitor impedance. A simpler
   bound is the switch-node voltage through the DM path of the deck.
4. **Emission:** emission (dBµV) = source (dBµV) + transfer (dB). Compare with
   the conducted limit from the official eCFR 47 CFR 18.307 table (fetch it
   and save it to `sources/`), and with CISPR 11/14-1 if you can cite them.
   Write `margins.csv` with the frequency, the prediction, the limit and the
   margin.
5. **Sensitivity:** CPE ×2, LCM × 0.7 and t_r × 0.5.

Criteria: task 07. This is a coarse prediction, so present it as such.

## 7. Task 04: copper current with `04-current/sheet_solver.py`

Use the Miniforge Python.

1. Run `sheet_solver.py --selftest`. It must print `SELFTEST PASS`.
2. **For each power net** (bus_p, hv_ret, leg_ret, sw_a, sw_b), from the
   copper export (use `tools/export_power_copper.py`, which is `FlashLayer`-aware;
   `tools/copper_dump.py` over-counts unconnected pad rings):
   - one `add_layer()` per layer, with that net's filled zone polygons plus
     its tracks buffered to their width (shapely)
   - 70 µm outer and **61 µm inner** thickness
   - `add_via()` for every via of that net, with its real drill from the
     copper dump, 18 µm plating (JLCPCB average) and 1.6 mm length. Leave
     `filled=False`: an empty via is a thin tube, and current passing it in a
     plane goes around the hole
   - `add_via(..., filled=True)` for every through-hole pad (C5/C6, C38–C41,
     the TO-247 pins, J-links): the soldered lead makes the hole
     equipotential. Inject at the pad centre; the solver attaches a point
     inside a filled drill to the barrel and **refuses** a point inside an
     empty via drill
   - SMD pads are copper polygons; inject at a point on the pad copper
   - don't subtract drills yourself: the solver removes every barrel's
     drill from each layer it passes
   - pads as injection points: the capacitor pads and MOSFET pins the task 04
     doc lists
3. **Check for zone holes first:** run
   `native-06/verification/power-probes/copper_zones_with_holes.py` under
   KiCad Python on native-13. The copper dump's polygons don't subtract holes.
4. **Pitch: 0.125 mm on native-13.** Run
   `validation-results/04-board-current-thermal/round3/scripts/kit_topology_native13.py`
   first. At 0.25 mm the grid never joins separate copper, but it splits real
   necks narrower than the pitch (leg_ret: 49 grid components vs 24 physical
   on F.Cu). At 0.125 mm every net and layer matches. If you change pitch,
   rerun it: grid components must equal physical components, and none may
   span two.
5. **Report** the path resistance, I²R per net, via currents and the maximum
   current per mm of width per layer.
6. **Convergence check (required):** re-solve one net at pitch 0.25 and
   0.0625 mm (the region around it only, if memory is short). R must converge to within 3 %, or report it didn't.
7. **Thermal:** extend with a 2.5-D finite-difference heat solve as task 04
   describes. This isn't in the kit; write it, and test it against the
   analytic temperature rise of a uniformly heated strip first.

## 8. When something goes wrong

| Symptom | Action |
| --- | --- |
| `smoke_test.py` FAIL | Stop. Report ngspice version, model hash and the full output |
| A deck aborts after you changed parameters | Re-run the deck defaults. If they pass, bisect your parameter change and report which value breaks it. Don't loosen solver options |
| A `.meas` shows in "failed" | The signal never crossed the level. Check the time window and level; with `--raw`, plot the waveform |
| Results jump between neighbouring parameters | The timestep isn't resolved. Halve `.tran` max step and re-run |
| A datasheet value is missing | Say "BLOCKED: <value>". Don't guess or use a similar part |
| Anything suggests changing the board | Report it. Only the owner changes the board |

## 9. What to hand back per task

Use `validation-results/NN-*/README.md` in the master plan's template,
**plus**:

- the exact kit commit you used (`git rev-parse HEAD`)
- the `smoke_test.py` output
- every parameter file or CSV
- the raw JSON from each run (or a script that regenerates it)
- a list of every placeholder still in use, and which conclusions depend on it
