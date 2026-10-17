> **Taken by Claude (owner request 2026-10-05: "instead of delegating, can you just do it"). Do not start a separate run.**

# D-31: protection closure — timing ledger, DC fuse, precharge pulses, DC contactors (supersedes D-17)

**Read [README.md](README.md) first (ground rules, board facts).**
Supersedes [D-17](D17-protection-gate-off.md), which never returned: do D-17's
tasks as part 1 of this brief.

## Why it matters

Task 02 round 3 left the gate-off chain and device survival BLOCKED and
the shunt-OCP minimum (38.44 A) below its 44 A criterion at +85 °C; the
owner's R34/R35 retune (round-3 decision B) is on hold until fault current,
device energy and actual gate-off timing are known. The prototype line then
added a catch circuit, dual contactors (KPA/KPB, LC1D18BD), a DC fuse (FC1,
Eaton FWP-10A14F) and a precharge network (two HS400 25 Ω branches with G4
cutoffs). The round-6 investigation (`prototype-closure/round6-investigation/circuit-review.md`,
P1 rows; that report is being moved onto this branch) found three P1 gaps:
FC1's published 22 A²s total clearing is at rated **AC** voltage and
`protection/interface.json` leaves `dc_total_clearing_a2s` and `fuse_arc_model`
null; the precharge resistors can see repeated loaded-proof pulses up to the
500 ms source-present bound with no hot/repeated pulse check; and the
contactors are not shown to make/break the installed DC fault current.

## Task

1. **Gate-off and survival (D-17's tasks 1–4):** the full threshold-to-gates-off
   delay for the CT and shunt-OCP paths (round-3 A3/A5 front end, U8 → U9 →
   J4.10 → interlock → PERMIT → Q1/Q4 → UCC21550 DIS → loaded gate discharge on
   the native-19 best matrix `d2/legA-h0-best-n19.matrix.txt`); fault scenarios
   per `validation-plan/02-protection-timing.md` at both trip corners and
   170/198/280 V; current at actual gate-off, peak die VDS (650 V; 520 V
   screen), device energy and avalanche, T1 vs 88 A, returned energy; the
   R34/R35 retune question (decision B), proposal only.
2. **Timing ledger:** one table from each fault source to (a) gates off and
   (b) current extinction: sensor RC/isolation/filter delay and uncertainty,
   comparator/isolator/latch, PERMIT fan-out, DIS network, loaded gate
   discharge, firmware paths where they matter, contactor coil and contact
   times (exact LC1D18BD data), fuse pre-arc/arcing. Min/typ/max with
   citations; mark allocations as allocations.
3. **FC1 on DC:** from Eaton/Bussmann data for FWP-10A14F (DC ratings,
   time-current and I²t curves, any DC test data or application notes), bound
   pre-arc and total clearing I²t and arc voltage/time at this bus (≤ 280 V
   DC, the installed loop L from the FEM/catch model) for the fault currents of
   part 1; say what cannot be established without vendor confirmation.
4. **Precharge pulses:** from the HS400 datasheet pulse/energy curves and
   the G4 cutoff data, the repeated-pulse capability at hot ambient for the
   firmware's worst legal sequence (repeated loaded proofs up to 500 ms, and a
   faulty repeat); pass/fail with margin, and any firmware limit it implies.
5. **Contactors on DC:** LC1D18BD DC making/breaking capability (utilisation
   category, voltage, current, time constant) vs the installed fault current
   and L/R; whether a contact may be asked to break DC fault current, and what
   the sequencing must guarantee if not.

## Deliverable

`round17/delegation/out-D31/README.md` (one-line answer per part first), the
ledger, the survival table, FC1/precharge/contactor assessments with
citations, runner and raw outputs (no licensed models). Simulation, analysis
and proposals only: no board, netlist, `elec/`, `pcb/`, firmware or
`prototype-closure` hardware edits.

## Acceptance

Every delay, rating and curve cites the exact-part datasheet or vendor
document (page/figure); bounds are stated as bounds only when worst cases are
stacked; vendor-only unknowns are named as such; the switching baseline
reproduces `d2/results/native19-carryover` for a matching non-fault case;
aborts are indeterminate.
