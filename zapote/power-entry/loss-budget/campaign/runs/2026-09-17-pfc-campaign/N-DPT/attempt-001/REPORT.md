# N-DPT report — independent vendor-model Eon/Eoff/Eoss vs the analytic 37.3682 W

Task **N-DPT** · attempt **attempt-001** · campaign `2026-09-17-pfc-campaign`
Base revision `b1a9ad74de50f283762a488a28c19f764830cdee` · contract C1.1
`0accd9bc55afbf875b08ed4dcdd8b7bbaf009d6f6fd1824f6b03c58797a825d6`

## 1. Question and changed variable

What Eon, Eoff and Eoss does an **independent vendor device SPICE model** predict
at the campaign operating point, and does it agree with the maintained analytic
model's **37.3682 W** switching-overlap term?
Actual changed variable: **none** — no design, model, or board edit. This is an
independent simulation instrument built in ngspice, deliberately not importing
or reproducing `zapote-erc::pfc_switching`.

## 2. Identities and what was captured

| Role | Part | Vendor model file | sha256 |
|---|---|---|---|
| Baseline DUT | IPW65R045C7 (CoolMOS C7 650 V/45 mΩ) | `raw/models/infineon_c7_650v_spice_ngspice.lib` | `d159f168…8983` |
| K-SILICON DUT | IPZ60R040C7 (CoolMOS C7 600 V/40 mΩ, Kelvin) | `raw/models/infineon_c7_600v_spice_ngspice.lib` | `6e743505…5ff3e` |
| Freewheel diode (substitute) | IDH16G65C5 (CoolSiC G5 650 V/16 A) | `raw/models/infineon_coolsic_g5_650v_ngspice.lib` | `36abbff6…c875` |
| Retained board diode | C3D20065D (Wolfspeed 650 V/20 A) | **not obtainable** | — |
| Retained board FET | STW65N65DM2AG (ST) | **not obtainable** | — |

Original vendor files and their hashes are in `inputs.json`; HTTP/byte/hash
provenance is in `raw/capture_log.txt`. The PSpice→ngspice conversion is
syntax-only (rename `if()`→`iif()` = native ternary; PSpice `PARAMS:` spacing;
`^`→`**`), element types preserved; `raw/tools/convert_infineon_pspice_to_ngspice.py`.

**Controls that reproduced** (all in `raw/logs/`):
- 10× timestep refinement — Eon 102.495 → 102.500 µJ, Eoff 104.786 → 104.777 µJ.
- Integration-window start moved 10 ns earlier — Eon unchanged, Eoff +0.087 %.
- Eoss grid 25 → 43 bias points — 9.758 → 9.762 µJ (0.04 %).
- DC sanity: DPT on-state Rds(on) = 43.4 mΩ @25 °C and 102.0 mΩ @125 °C, against
  the datasheet 45 mΩ / ≈99 mΩ hot.

## 3. Testbench (what was actually applied)

Clamped-inductive double pulse, ngspice-45.2: 400 V bus → 180 µH → switching node
→ 0 V sense element → DUT → ground; freewheel SiC diode across the DUT. Gate PWL
0→12 V through a behavioural external resistor **9.7 Ω on / 5.3 Ω off** (vendor
internal Rg = 0.82 Ω, Lg = 5 nH kept). E = ∫ v(drain)·i(dsense) dt over a 182 ns
window, integrated by ngspice `meas … integ`. Applied event currents differ from
the requested ones by ≤1.4 % and are reported per case (never scaled).

## 4. Results (µJ; f = 129107.392 Hz)

| Device, T | Eon @ I_on | Eoff @ I_off | Eoss(400 V) | (Eon+Eoff)·f | ratio / 37.3682 W | overlap-only ratio* |
|---|---|---:|---:|---:|---:|---:|
| **IPW65R045C7, 25 °C** | **102.50 @ 12.07 A** | **104.79 @ 14.99 A** | **9.76** | **26.76 W** | **0.716** | 0.682 |
| IPW65R045C7, 125 °C | 99.47 @ 12.03 A | 97.31 @ 14.94 A | 8.69 | 25.41 W | 0.680 | 0.650 |
| IPZ60R040C7, 25 °C | 78.38 @ 12.11 A | 94.94 @ 15.04 A | 10.58 | 22.38 W | 0.599 | 0.562 |
| IPZ60R040C7, 125 °C | 73.56 @ 12.07 A | 84.31 @ 15.00 A | 9.40 | 20.38 W | 0.545 | 0.513 |

\* overlap-only = (Eon − Eoss + Eoff)·f, since the DPT turn-on also dissipates
the stored output-capacitance energy that the analytic model books separately.

The vendor model puts the baseline device's switching at **0.72×** the analytic
overlap term (0.68× overlap-only) at 25 °C, and the gap widens at 125 °C.
**Verdict: the analytic 37.3682 W overlap is CONTRADICTED at ≈1.4×, i.e. the
vendor model is ~30 % lower.**

## 5. Case accounting

Devices: 3 attempted, 2 valid, 1 capture-failed (STW65N65DM2AG).
DPT cases: 4 planned (2 devices × 2 T), 4 valid, 0 failed.
Refinement/control runs: 6 attempted, 6 valid.
Eoss: 1 method failed (DC ramp, timestep collapse at the model's internal gate
node), 1 method valid (AC Coss(v)) across 4 cases + 1 grid refinement.
Solver invocations: ≈38 of the 48 budget.

Unresolved findings:
1. Vendor **Level-1/Level-3** temperature/electrothermal models do not run in
   ngspice-45 — `Timestep too small; initial timepoint: trouble with node
   e.xdut.x1.e_eds4#branch` (also `xdut.x1.d1`, `…x$cap.e_d#branch`), unchanged by
   B-source conversion, gmin/itl/reltol/trtol/gear/rshunt/uic/ramped-bus/gate-R
   and ps/all/lt compatibility modes. The 125 °C numbers are therefore the
   Level-0 model at `.temp 125` (resistor TC only), **not** the vendor
   electrothermal prediction.
2. Freewheel diode substitution changes Eon **+9.3 µJ (+10 %)** and Eoff
   **−7.3 µJ (−7 %)** but the sum only **+1.0 %** (matched-timing ideal-diode
   control), so the headline ratio is insensitive to this substitution.
3. STW65N65DM2AG is UNKNOWN (capture failure, no substitute).
4. No coordinator checker was issued for this task; `not_applicable`.

## 6. Most important caveat

The headline number is a **vendor typical-device macromodel simulation, not a
measurement and not a hardware qualification**, and the only vendor models that
solve in ngspice-45 are the **Level-0** (non-electrothermal) models: the 125 °C
entry is a temperature-scaled Level-0 result, not the vendor's hot model.

## 7. Next observation

Ask the coordinator for the **LTspice/SIMetrix** Infineon model (different
internal topology) or a vendor model confirmed to run in ngspice, and re-run the
same DPT for IPW65R045C7 at 125 °C; this is the single observation that would
convert the 125 °C entry from an approximation into an independent vendor
prediction. Otherwise the branch can be pruned: even the 25 °C vendor result is
already 0.72× the analytic overlap, and the substitution/diode sensitivities are
small compared with that gap.

## 8. Accounting

Approx. wall time ~2.5 h (ngspice compute is seconds; most time was model capture,
conversion and convergence diagnosis). Files: `inputs.json`, `result.json`,
`REPORT.md`, `manifest.json`, `raw/` (models, netlists, logs, tools, capture log).
Deadline `2026-09-18T00:20:00Z`: met. No commits, no `git stash`; output confined
to the allowed directory.
