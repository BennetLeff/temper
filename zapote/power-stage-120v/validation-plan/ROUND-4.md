# Validation round 4: current ceiling, board inductance, dead time

Part of the [master plan](00-MASTER-PLAN.md). Read the master plan's ground
rules (§2), the [simulation runbook](SIMULATION-RUNBOOK.md), and the
[round-3 decision review](../validation-results/round3-coordination/decision-review/README.md)
first. This round carries out the owner's decisions of 2026-09-28:

| Item | Owner decision | This round |
| --- | --- | --- |
| A | Proceed | §2: derated operating grid under a 42 A actual-current ceiling |
| D | Proceed | §3: field-solved board and gate-loop inductance, then a diagnostic rerun of the switching cases |
| C | Evaluate only | §4: 450 ns dead time across tolerance, with diode losses |
| B | **Hold** | Not in this round. Don't propose R34/R35 values |

Written 2026-09-28 against PR #1615 at `dae39a538`.

**Not in scope:** F4 (a stuck PWM cleared only by the 0.9–2.5 s watchdog)
and F5 (BUS_FAULT not guaranteed through a slow HOT5 brownout) remain open
gaps, tracked separately. The capacitor current rating still waits on CDE
(ROUND-3 §4, O2). No board, source, firmware or part change is made in
this round; findings go in the reports as recommendations.

## 0. Before you start

- **Board:** `native-15/section.kicad_pcb`, SHA-256
  `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`.
- **Round-3 raw evidence.** Several inputs here are round-3 raw files (for
  example `05-resonant-tank-envelope/round3/outputs/switching-events.csv` and
  the A1 run directories). They aren't in git. Get them one of two ways,
  then check them:
  1. If the release `ps120-validation-round3-raw-v1` is published: run
     `validation-results/round3-coordination/raw-evidence/restore.sh`.
  2. Otherwise copy `zapote/power-stage-120v/validation-results/` from the
     worktree `/Users/bennet/Desktop/temper/worktrees/ps-r3-integration`
     (read-only; don't write there).

  Either way, `python3 validation-results/round3-coordination/raw-evidence/verify.py validation-results`
  must print `3327/3327 files verified`. If it doesn't, stop.
- Run `validation-plan/sim-kit/smoke_test.py` (`SMOKE PASS`).
- **Workers:** one per item (A, D1, C; then D2), each in its own worktree.
  Python, ngspice, KiCad Python and FastHenry only; no `cargo build` or full
  workspace build.
- **Results:** `validation-results/NN-<task>/round4/<item>/`, with the
  master plan §4 report template. Put per-case raw runs under
  `outputs/runs/`; `.gitignore` keeps those, `*.npz`, `*.raw` and `*.raw.gz`
  out of git for round 4 as for round 3.
- **Commits:** workers hand back uncommitted. The coordinator reviews and
  commits, ending each message with
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

### Rules carried over from round 3 (ROUND-3 §0)

A number without a committed source isn't an input. "Bound" only when it
bounds. Bracket what you can't pin down and report where a verdict flips.
Never change the board or source. Stop and report on a contradiction.

Two corrections from round 3 apply here:
- The TLV3201's 55 ns maximum is a step-response specification at 20 mV
  overdrive; it doesn't bound an arbitrary ramp.
- The 724 V B1 event is **not** shown to be shoot-through or false turn-on.
  At the peak, the low-side die VGS was −2.1 V. Treat its cause as unknown
  until §3 D2 decides it.

## 1. Order of work

```
Wave 1 (in parallel)                     Wave 2
--------------------                     ------
A   derated operating grid         --->  C2  dead-time loss comparison
                                         (uses A's derated switching events)
C1  dead-time ZVS thresholds,
    tolerance and low-bus coverage
D1  FastHenry board extraction     --->  D2  switching cases on extracted L;
                                         cause of the 724 V event
```

---

## 2. Item A: derated operating grid under a 42 A ceiling

**Goal.** Replace round 3's "requested power at any current" grid with the
power the stage can deliver when the **actual tank peak current** stays at
or below a ceiling. Report which pans lose power, and by how much.

**What 42 A means.** 42 A is a provisional ceiling on *actual* peak tank
current, used for analysis. It isn't a firmware setpoint: a controller has
to command a lower value, below the ceiling by its sensing and control error
and a transient allowance. Those errors aren't known yet, so run two
ceilings:
- **42 A**: the provisional ceiling;
- **40.45 A**: 20 % below the lowest static CT trip (50.56 A, task 02
  round 3), a stand-in for a command with margin.

Label every result with its ceiling.

**Steps.**
1. Copy `05-resonant-tank-envelope/round3/scripts/find_freq.py` and its
   deck to `05-resonant-tank-envelope/round4/a-derated/`. Keep the same 135
   cases: five pan classes, three L/R corners, 108/120/140 V, and
   1710/855/300 W requests.
2. For each case, run the round-3 solution. If its peak tank current is at
   or below the ceiling, keep it unchanged.
3. Otherwise, raise the frequency until the peak tank current over the line
   half-cycle equals the ceiling (bisection to ±0.2 A). Record the delivered
   power, frequency, tank RMS, capacitor voltage peak and RMS, and the
   C21/C22/C23 current shares.
4. If the ceiling can't be met at or below 60 kHz (the deck's search limit),
   **don't extend the frequency.** Record the case as "needs burst or phase
   shift", with its current at 60 kHz. Frequency-only control can't reach
   it, and this deck doesn't model the other modes.
5. For every retained or derated case, regenerate the switching events
   (`switching_events.py`) and the R5 RMS (`shunt_waveform.py`). C2 needs
   them.
6. Screen each case against the static trip bands from task 02 round 3:
   CT 50.56–60.01 A, shunt 38.44–85.55 A. Report how many derated cases sit
   above the lowest shunt trip. That's the evidence for the held item B.

**Hand back:** `derated_cases.csv` (both ceilings); a table of delivered power
by pan class and line voltage; the "needs burst/phase shift" list; the
switching-event and R5 files; and the trip-band screen.

**Evidence class:** simulation/model-based (ideal frequency-control deck, no
dead time or MOSFET drops), the same as round 3. Physical confirmation is the
tank current waveform per pan class at bring-up.

---

## 3. Item D: board inductance, then the switching cases

### D1. FastHenry extraction of the commutation and gate loops

**Tool.** Build FastHenry2 with the recipe in
`validation-results/round3-coordination/decision-review/README.md` (commit
`363e43ed57ad3b9affa11cba5a86624fad0edaa9`, unmodified source). Rerun the
round-3 fixtures first (`decision-review/fieldsolver/`) and require the same
results within 0.1 %. The warning-suppressed build is a usable executable,
not a proven one. Keep the plane-pair fixture as a check in every run.

**What to extract.** Use one coupled model per leg (A: Q2/Q3; B: Q5/Q6), not
separate scalar inductances. Round 3's A2 scenarios may double-count shared
returns because each branch was estimated alone.

1. **Geometry.** Start from A2's connected-copper tooling and port list
   (`01-switching-parasitics/round3/a2-inductance/scripts/trace_connected_copper.py`,
   `outputs/annotated_ports.json`) and the hole-aware copper exports in its
   `inputs/`. Model:
   - In1 (HV_RET/LEG_RET) and In2 (BUS_P) as FastHenry ground planes
     (`G` elements), with their holes and antipads;
   - F.Cu and B.Cu pours and tracks on the loop as planes or segments;
   - each via and through-hole barrel as a vertical segment between layer
     heights from `stackup.json`;
   - copper thickness 70 µm outer and 61 µm inner.
2. **Ports.** One port per branch of the commutation cell, at real pad
   positions:
   - C38–C41 pads to the Q2/Q5 drain (the high-side drain branch);
   - Q2/Q5 source to the Q3/Q6 drain (the switch node);
   - Q3/Q6 source to R5 (the low-side source branch, including the shared
     return);
   - the R5 pads to the C38–C41 return pads;
   - each **gate loop**: driver output pin → series resistor → gate pin, and
     source pin → driver ground return. The TO-247-3 has no Kelvin source
     pin, so part of the source return is shared with the power loop.
3. **Solve** at 1, 10 and 30 MHz. Output the port impedance matrix and
   convert it to self-inductances and **mutual inductances**. In particular,
   get the mutual between each gate loop and the power-loop source branch:
   the common-source inductance.
4. **Convergence.** Solve at two mesh densities (at least 2× apart). Every
   self and every mutual larger than 10 % of its self term must change by
   ≤ 5 %. If not, refine again and report.
5. **Local capacitor ESL.** Still unknown (ROUND-3 A2). Keep the 5–20 nH
   ASSUMED bracket for C38–C41 and C5/C6's internal ESL; don't fold it into
   the copper result.

**Hand back:** `extraction/` (FastHenry input decks, logs, build log and
fixture rerun), `inductance_matrix.json` (per leg and frequency: port
definitions, L and M in nH, R in mΩ, both meshes), and `spice_coupled.inc`:
the matrix as SPICE `L` and `K` statements for D2. Include a README
explaining which deck node each port maps to.

**Evidence class:** model-based field solution of the committed copper.
Physical confirmation is VDS and gate waveforms at staged low-voltage
bring-up.

### D2. Switching cases on the extracted inductance; the 724 V cause

**Deck.** Copy `01-switching-parasitics/round3/b1-board-grid/complementary_leg.cir`.
Replace the scalar board-inductance knobs with D1's `spice_coupled.inc`.
Keep the package inductances inside the Infineon model (don't add them
again). Local-capacitor ESL: run both ends of the 5–20 nH bracket.

**Save more than round 3 did.** In every run, save:
- both devices' die VDS and die VGS;
- both devices' **channel, body-diode and external drain currents** (the
  L1 model's internal current probes; round 3 saved only one side);
- the switch node, the bus at the capacitor pads, and the driver outputs.

Keep the complete raw waveform for the first 1 µs after each command in
`outputs/runs/`.

**Step 1: decide the cause of the 724 V event.** Rerun the round-3 case (leg
A, 170 V, 37 A, DIR 0, 348 ns) with D1's extracted inductance. Then, one
change at a time:
1. **Ideal off-gate:** hold the low-side die gate at 0 V through an ideal
   source while it's commanded off. If the peak persists, false turn-on
   isn't its cause.
2. **Common-source mutual set to zero** (K removed).
3. **Local-capacitor ESL** at 5 and at 20 nH.
4. **Round-3 A2 "min" scalar values** in place of the matrix, to reproduce the
   723.9 V result and show it's the same deck.

From the saved currents, say whether both devices conducted at the same
time, and when. Report the peak VDS, when it occurs relative to each command,
and which change removes or keeps it. If the extracted inductance doesn't
reproduce a large peak, say so plainly: the round-3 value came from
heuristic inputs.

**Step 2: the grid.** Run the round-3 B1 grid (170/198/280 V; 37, 61/71,
2/5/10, 20 A; both directions; legs A and B; 348 ns; ESL bracket), with the
extracted matrix instead of the min/max scenarios. Gate-loop scaling isn't
needed now that the loops are extracted. Stop and report at the first failed
criterion **with the cause from Step 1's method**, then run the remaining
cases anyway for the record. Halve the timestep for every reported peak
(< 2 % change).

**Hand back:** `cause_724v.md` with the comparison table and waveforms;
`grid-results.json`; per-criterion verdicts (S1–S4) against 520 V, 585 V,
off-gate < 3.0 V and die VGS ±30 V; and the gate-off timing for B2, with
whether it's a sustained off or a first crossing.

---

## 4. Item C: evaluate a 450 ns dead time (no hardware change)

The driver's dead time comes from RDT on each UCC21550 (R9/R17, 39 kΩ now).
The TI datasheet's nominal relation gives about 348 ns at 39 kΩ and about
452 ns at 51 kΩ. TI characterizes 50 kΩ at **399 / 443 / 487 ns**
(min/typ/max). Take those numbers from the datasheet
(<https://www.ti.com/lit/ds/symlink/ucc21550.pdf>) with page and table, and
find the equivalent characterized spread for 39 kΩ. If only one RDT is
characterized, scale its relative spread and label that ASSUMED.

Driver-output dead time isn't the MOSFET's effective dead time: most of it
goes to the outgoing device's turn-off delay (A1). Evaluate at the die.

### C1. ZVS thresholds across tolerance and bus voltage

1. With A1's deck (`01-switching-parasitics/round3/a1-zvs/`) at reference
   inductance, find the minimum ZVS current at driver dead times of
   **min, typ and max** for both 39 kΩ and 51 kΩ (six values), both
   directions.
2. **Extend the bus voltage down.** Round 3 covered only 120/170/198 V, but
   the bus follows the rectified line to near zero. Add 10, 30, 60 and 90 V.
   Near the line zero the bus is tiny and the currents are small; report the
   thresholds there, and don't extrapolate below 10 V.
3. Repeat the threshold search at inductance ×0.5 and ×3 for the typical
   values. Once D1 is done, rerun it once with D1's matrix (both legs) and
   report the change.

**Hand back:** `zvs_thresholds_c1.json` (dead time × bus voltage ×
direction, with brackets) and the sensitivity table.

### C2. Loss comparison, 348 vs 450 ns (needs A)

Use A's derated switching events (both ceilings). For every switching event,
classify it as ZVS or hard-switched using C1's threshold at that event's bus
voltage and dead time. Then compute per case, at min/typ/max dead time for
both resistor values:

- **Body-diode dwell loss:** for ZVS events, the diode conducts from the end
  of the transition to the incoming gate's turn-on. Take the dwell time from
  C1's waveforms (not dead time minus a guess). Loss is Vf(I, Tj)·I·t_dwell,
  with Vf from the IPW65R018CFD7 datasheet at 25 °C and 125 °C.
- **Reverse recovery:** hard-switched events, with Qrr and trr for the CFD7
  body diode from the datasheet at the stated di/dt. State the di/dt you
  used and whether the datasheet condition matches it.
- **Hard turn-on loss:** Eoss(V) plus the recovery energy, per hard event.
- **Turn-off loss:** from A1's `turnoff_energy.csv`
  (`turnoff_model_dissipative_sum_j`), per event current.

Sum over a line half-cycle, average, and report the total MOSFET switching
and diode loss per case for 348 and 450 ns, at min/typ/max. Report the fraction
of hard-switched events for each.

**Verdict to give:** whether 450 ns lowers the total loss over the derated
grid, at *every* tolerance corner, and where it doesn't. Also check the
opposite risk: at the maximum dead time and the lowest ZVS currents, does
the tank current reverse before the incoming gate turns on (loss of ZVS
from too much dead time)? Report those cases.

**Hand back:** `deadtime_losses.csv`, a summary table, and a recommendation.
This is evaluation only; RDT isn't changed.

---

## 5. Decisions this round may ask the owner for

| # | Question | Raised by |
| --- | --- | --- |
| O5 | Command current and allowance under the 42 A ceiling | A's derated table and the CT tolerance |
| O6 | Whether to change RDT to 51 kΩ | C2's verdict |
| O7 | Gate-drive or layout change, if D2 shows false turn-on or excess VDS on extracted inductance | D2 |
| O8 | Backup shunt architecture (held item B) | D2's gate-off timing and fault currents; A's trip-band screen |

Open from round 3: O1 (pad and heatsink), O2 (CDE rating), O3 (TDK ESL),
O4 (JLCPCB CTI).

## 6. What to hand back (every item)

- A README from the master plan §4 template, with the native-15 hash and the
  round-3 raw-evidence verification line.
- Every script, runnable as committed; summary outputs in git; raw runs under
  `outputs/runs/`.
- A status line for master plan §5.
- For anything blocked: the missing input, and the cheapest way to get it.
