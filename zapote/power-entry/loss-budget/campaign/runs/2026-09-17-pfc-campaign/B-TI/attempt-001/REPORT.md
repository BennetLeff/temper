# B-TI applicability study — TI TIDA-00779 / TIDUBE1D Rev D

- **Task / attempt:** B-TI / attempt-001 (kind: reference_research, source-only)
- **Changed variable:** none — no solver run, no model edit, no bench work (`max_solver_invocations: 0`)
- **Hypothesis:** the retained TI reference can test the maintained model's ~37 W
  switching-overlap loss on the boost switch at 120 V / 15 A / 400 V / 129.107 kHz.
- **Status axes:** task_completion FINISHED; numerical_status NOT_RUN;
  physical_applicability INDETERMINATE; hardware_qualification NOT_PERFORMED;
  evidence_status NOT_REVIEWED (coordinator receipt absent).

## 1. Identity of the reference

| Item | Value |
|---|---|
| Document | TIDUBE1D, Rev D (August 2024; original January 2016) |
| Title | 230-V, 3.5-kW PFC With >98% Efficiency, Optimized for BOM and Size Reference Design |
| Retained copy | `raw/TIDUBE1D.pdf` (byte-identical to `benchmark/TIDUBE1D.pdf`; `cmp` clean) |
| SHA-256 (full) | `1f2abaf8f7460ec110186d59f3d01624bdbd260d57ae7b7b698d0754c717d465` |
| Header | `%PDF-1.4`; pdfinfo version 1.6; 17 pages (letter) |
| Extracted text | `raw/TIDUBE1D.pdftotext.txt` (pdftotext -layout) |

Baseline identity (model side, read not run):
`zapote/power-entry/loss-budget/options/experiment-02/evidence/report.json`
(`3805a41c…`), contract `campaign/runs/contract-C1.json` (`3bf1125f…`). The
contract no-assist subtotal is 45.5023 W; the report's equivalent no-assist
scenario lists `overlap_w = 37.518 W` (turn-on 11.927 A, turn-off 15.027 A,
switch RMS 11.999 A). **Controls reproduced: N/A** — no solver case was run.

## 2. What TIDUBE1D actually populates

- **Topology:** single-phase, **non-interleaved, non-bridgeless CCM boost** PFC
  with a diode-bridge front end (p.1).
- **Controller:** UCC28180. **Gate driver:** UCC27524 (5 A source / 5 A sink
  peak *ratings*). **Bias:** on-board UCC28881, 15 V rail; gate clamp 15.2 V.
- **Boost switch:** IPW60R099P6, 600 V / 37.9 A @25 °C / 24 A @100 °C, at **two
  populated positions Q1 and Q6** (shared heatsink, p.8) — parallel pair
  **inferred**, not stated verbatim; the schematic/BOM are external downloads,
  so the connection and current-sharing ratio are unresolved.
- **Boost diode:** D1, D3 (type not stated). **Gate network:** 22 Ω series +
  antiparallel Schottky, 10 kΩ gate-to-ground (p.7).
- **Magnetics:** 180 µH boost inductor (p.6); 2040 µF output.
- **Frequency:** 45 kHz design / **44 kHz actual** (47 kΩ FREQ resistor, p.5).
- **Output:** boost follower, 380 V nominal, measured bus 337.2 V (150 VAC) →
  406.2 V (275 VAC) (Table 3-3, p.10).

## 3. What the reference does and does not expose

It publishes **whole-board** Pin/Pout/PF/THDi (Table 3-1 p.9, Yokogawa WT500;
Table 3-2 p.10, Hioki PW8001) and image-only thermal/startup plots.

It does **not** publish: per-switch event currents, duty-weighted switch RMS,
measured Eon/Eoff, drain-current waveforms, gate-current waveforms, per-device
loss, device charges/plateau/Eoss, loop inductance, RDS(on), or numeric device
temperatures.

**Explicit:** Table 3-1/3-2 efficiency is whole-board, whole-line-cycle
efficiency from a power analyzer. Whole-board efficiency **is not** per-device
Eon/Eoff and was not used as one. Figures 3-6/3-7 ("turn on/off MOSFET", p.13)
carry gate voltage, AC input voltage, Vds and **AC input current** — no switch
drain current, no numeric time base or amplitude values, and no stated line
phase/load — so no event energy is extractable.

## 4. Applicability table (each maintained `pfc_switching::Config` input)

| Model input | Model case | From TIDUBE1D | Status |
|---|---|---|---|
| `bus_v` | 400 V | 381.17 V @226 VAC … 400.85–403.28 V @267–270 VAC | SOURCED_BUT_NO_MATCHING_POINT |
| `switching_hz` | 129.107 kHz | 45 kHz design / 44 kHz actual | SOURCED_MISMATCH |
| `turn_on_current_a` | 11.927 A | — | UNKNOWN |
| `turn_off_current_a` | 15.027 A | — | UNKNOWN |
| `switch_rms_a` | 11.999 A | — | UNKNOWN |
| `gate_bias_v` | 12.6 V | 15 V rail / 15.2 V clamp (label, not waveform) | SOURCED_APPROXIMATE_MISMATCH |
| `qg_c`, `qgd_c` | 93 nC, 15 nC | not in document | UNKNOWN |
| `current_transfer_charge_c` | 10 nC | not published (and not Qg−Qgd) | UNKNOWN |
| `gate_plateau_v` | 5.4 V | not published | UNKNOWN |
| `external_gate_r_ohm` | 10 Ω + hypothetical driver assist | 22 Ω | SOURCED_MISMATCH |
| `intrinsic_gate_r_ohm` | 0.85 Ω | not published | UNKNOWN |
| `driver_source/sink_peak_a` | 5 A / 5 A | 5 A / 5 A (rating) | SOURCED_RATING_ONLY |
| `coss_energy_j` | 11.7 µJ | not published | UNKNOWN |
| `loop_inductance_h` | 10 nH | not published | UNKNOWN |
| `rds_on_ohm` | 45/90 mΩ | not published | UNKNOWN |
| `timestep_s` | 250 ps | n/a (model choice) | NOT_APPLICABLE |
| GatePath on/off external R | 10.86/15.0/18.5 Ω; 5.8/10.6/11.1 Ω | 22 Ω turn-on; turn-off is a diode | SOURCED / UNKNOWN |
| `line_rms_v` | 120 V | 226–270 V only | SOURCED_NO_MATCHING_POINT |
| `input_power_w` | 1796.31 W | ≤ 3832.5 W whole-board | SOURCED_BUT_DIFFERENT_ASSEMBLY |

Full row-by-row citations are in `inputs.json` (`applicability_table`).

## 5. Verdict — INSUFFICIENT_EVIDENCE

The reference **cannot test** the ~37 W switching-overlap claim. Independent
failures, any one sufficient: (1) **operating point** — no TI row at 120 V
line, and the follower bus reaches 400 V only near 270 V line; (2)
**frequency** — 45 kHz vs 129.107 kHz (2.87×), overlap scales with f; (3)
**device** — IPW60R099P6 vs model IPW65R045C7; (4) **population** — 2 parallel
MOSFETs vs a single-device partial loss; (5) **observability** — no event
current, no switch RMS, no Eon/Eoff, no drain-current waveform, no per-device
loss.

Whole-board Pin−Pout (72.3 W / 86.4 W at 226 V) is **not** a valid bound on the
model's 45.50 W *partial* subtotal: different device, point, frequency,
parallel count and accounting boundary. Fitting hidden charges/resistances to
make the published efficiency match is expressly not done here.

**What the reference does support:** an architecture/whole-board plausibility
reference — a conventional CCM boost with parallel FETs and a 180 µH inductor
reaches 97.71–98.13 % whole-board at 226–230 V / ≤3.78 kW. That validates no
switching-energy term.

## 6. Source failures (excluded, retained with reasons)

- Table 3-1, 227.33 V (p.9): Pout 2560.7 W > Pin 2513.6 W at 97.974 %.
- Table 3-1, 229.80 / 229.31 / 227.62 V (p.9): P = V·I·PF identity violated.
- Table 3-2 (p.10) decimal-field defects: 268.45 V (`POUT=2.0102`), 268.32 V
  (`PIN=2.1985`, Pout>Pin), 267.91 V (`POUT==PIN=2687.4`).
- Schematic/BOM are external to the retained PDF (p.15), so parallelism cannot
  be confirmed from the retained bytes.

## 7. Missing terms, case counts, budget

Device charges, Eoss, loop inductance, RDS(on) and every event current are
unknown; device junction temperatures are image-only. **No subtotal or
efficiency is published** — unknowns stay null in `result.json`. Case counts:
expected 0 · attempted 0 · valid 0 · failed 0 · unsupported 0 · unrun 0; no
assembly rank is emitted.

## 8. One recommended next observation

Capture **one** boost-switch switching transition (or the parallel pair as a
whole) with **simultaneous drain current and Vds on a stated time base**, at a
stated line phase, load and junction temperature, and integrate vDS·iD over the
identified turn-on and turn-off events. That single row is the most important
missing source row. Absent it, this reference branch is prunable for switching
energy and retained only as a whole-board architecture reference.

## 9. Evidence, budget, touched files

Checker: G0 unimplemented; `checker_receipt` null; no machine acceptance
claimed. Unresolved findings are the source failures in §6. Invocations: 0
solver; source reads only. Deadline 2026-09-17T22:30:00Z — met (elapsed in
`result.json` `budget.elapsed_seconds`). Touched files, all inside the allowed
output directory: `raw/TIDUBE1D.pdf`, `raw/TIDUBE1D.sha256`,
`raw/TIDUBE1D.pdftotext.txt`, `inputs.json`, `result.json`, `REPORT.md`,
`manifest.json`. No commit, no stash, no edits outside the directory.
