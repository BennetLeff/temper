# AR-COORD attempt-001 — fuse coordination envelope and the applicable RMS basis

Task **AR-COORD** · Attempt **attempt-001** · Campaign 2026-09-17-pfc-campaign · engineering_verification.
Contract C1.1 `0accd9bc…a825d6`. Dispatch `source_revision` `9c8c277…` is a **direct ancestor** of HEAD
`0cef82ec…`; the single intervening commit adds this dispatch and the corrected AR-PROTCKT receipt.
Source-only; no bench, no procurement, no CAD/BOM edit, no solver, no commits.

**Result in one sentence.** F2's *normal* duty clears comfortably on the RMS basis Eaton itself uses,
but a swept R–L **envelope** shows the selected FWP-50A14F has **no applicable capacitor-discharge
clearing data**, so coordination stays **UNESTABLISHED**; one same-class alternative (Mersen
A70QS50-14F) does publish a capacitor-discharge rating — the single most useful new fact.

## 1. What changed, and the controls

The changed design variable is **the fuse-selection comparison basis and the fault-impedance
treatment**, not the circuit. Frozen controls: contract C1.1 (400 V bus, 1796.31 W, 108/120/132 V),
the retained R0 waveform model, and the retained netlist. No solver was invoked, so there is no
control-case reproduction; the model's own arithmetic was checked against two independent limits (§4).

## 2. Normal-current waveform — RMS basis per candidate

F2 carries the pulsed boost-diode current. From the retained R0 model
(`raw/evidence/R0-report.json`):

| line | boost-diode **RMS** | rated bus average | rectified peak |
| --- | --- | --- | --- |
| 108 V | 8.5390 A | 4.4908 A | 7.0541 A |
| **120 V** | **9.0007 A** (worst) | 4.4908 A | 7.0541 A |
| 132 V | 8.5868 A | 4.4908 A | 7.0541 A |

Eaton's own loss correction `Kp` is a function of **RMS load current** (retained FWP sheet, p.207), so
RMS — not the 4.49 A average — is the sizing basis. An average-based size would undersize heating by
roughly half. The 129.1 kHz pulse train (period 7.75 µs) merges thermally inside the fuse element, so
RMS already carries the repetitive-pulse duty.

| candidate | rated RMS | % of rated at 9.0007 A | continuous margin |
| --- | --- | --- | --- |
| FWP-50A14F | 50 A | 18.0 % | 5.56× |
| A70QS50-14F (alternative) | 50 A | 18.0 % | 5.56× |
| FWP-25A14F (lower-rated same class) | 25 A | 36.0 % | 2.78× |

**Startup and temperature stay null.** The retained model is steady-state; the precharge/inrush duty
through F2 (NTC U4 / bypass relay U5, hot restart) is not modelled, and no ambient-temperature,
forced-cooling, conductor-size or altitude derating was captured. At 18 % of rating the margin is very
large, but that is a screening observation, not a temperature-derated rating.

## 3. Applicable clearing data (item 3)

**FWP-50A14F: none obtained.** Neither the retained 2011-2014 datasheet nor the captured current
revision publishes a capacitor-discharge rating or a DC L/R limit. The published **1800 A²s is an
AC/inductive clearing I²t at rated voltage, pf 0.15** — it does **not** apply to a capacitor discharge.
What would resolve it: an Eaton capacitor-discharge rating / let-through characteristic for FWP-50A14F.

**A70QS50-14F: obtained (class-level).** The Mersen A70QS French Cylindrical line publishes an
**890 Vdc rating for capacitor-discharge applications up to a 2.5 ms time constant**
(`raw/sources/mersen-high-speed-catalog.pdf`). At a 400 Vdc bus the voltage is covered; the condition
is the time constant.

## 4. Fault-impedance envelope (item 2)

Model: series **R–L–C** discharge, `L di/dt + R i + v_c = 0`, `v_c(0)=400 V`, `C=2240.47 µF`,
`E=179.2376 J`; swept **R ∈ [5 mΩ, 5 Ω]**, **L ∈ [20 nH, 20 µH]**, 400 points. Assumptions: single
constant lumped R; fixed L; **no arcing**; **no evolving short residual**; bank ESR not published;
fuse R ≈ 3.6 mΩ from 9 W/50 A². Independent checks: the lossless peak reproduces `V0/Z0` (1.2 % at
R = 0.1 mΩ); the large-R peak reproduces `V0/R` (2.4e-9); the action integral reproduces `E/R` to
**3.8e-14**. Total action is `E/R`, **independent of L**; L changes peak and timescale, not action.

**Melting envelope (adiabatic screen, all L):**

| candidate | melting I²t | melts iff R ≤ |
| --- | --- | --- |
| FWP-50A14F | 200 A²s | **0.896 Ω** |
| A70QS50-14F | 280 A²s | **0.640 Ω** |
| FWP-25A14F | 46.5 A²s | **3.855 Ω** |

**Peak envelope:** maximum **55.2 kA** at the R = 5 mΩ, L = 20 nH corner. The FWP 50 kA breaking
capacity is approached only for R ≲ 8.9 mΩ at the lowest L; for R ≥ 10 mΩ the peak is inside 50 kA
everywhere. That comparison is a **screen**: the 50 kA rating is a DC L/R test, not a capacitor
discharge.

**Clearing envelope:** FWP-50A14F and FWP-25A14F **null** — no applicable capacitor-discharge data.
A70QS50-14F: its stated 2.5 ms time-constant condition is `R·C ≤ 2.5 ms` (the natural capacitor-discharge
reading), i.e. R ≤ 1.116 Ω, which **contains** its 0.640 Ω melt boundary — so wherever it melts the
manufacturer's capacitor-discharge condition holds. This is **class guidance, not a demonstrated board coordination**: the let-through
I²t against the bank / PCB-copper withstand is still unsourced.

## 5. Revision reconciliation (item 4)

| revision | document | DC rating | breaking |
| --- | --- | --- | --- |
| retained | Cooper Bussmann catalogue page DS 720025, PDF 2011-03-01 / mod 2014-03-26 | **800 Vdc** | 50 kA at 800 Vdc |
| **applicable** | current Eaton product spec sheet for FWP-50A14F, generated 2023-12-04, DS 720025 | **700 Vdc** | 50 kAIC at 700 Vdc |

The part would be ordered from the current revision, so **700 Vdc / 50 kA at 700 Vdc** is the
applicable figure; 800 Vdc is the *retained revision's* value and is not presented as the part's.
(The Eaton manufacturer PDF host was unreachable — timeouts, 0 bytes, twice — so a manufacturer-authored
spec-sheet mirror was captured; failure retained in `raw/capture_failures.json`.) Both exceed 400 Vdc.

## 6. Evidence ledger, fault loop, checkers

```
zapote-claims claims.json
  No violations detected by implemented checks (29 claims, 5 protection claims, 2 promotions).
check_fault_loop.py --netlist raw/evidence/netlist_fault_loop.json \
  --loop-nets PFC_BUS_PLUS_390V,PFC_BUS_MINUS,a1 \
  --assignments raw/assignments_envelope_representative.json   -> exit 0, FAULT LOOP CONSISTENT
```

Both negative controls fail as designed: the bound-reversal ledger reports `reverses the bound
direction` + `cannot flip direction` (exit 1), and the withdrawn shunt assignment reports
`FAULT LOOP INCONSISTENT` for U12 (exit 1). All outputs retained under `raw/checker/`. A clean run
means no implemented check fired; it is not proof of correctness. The completion ladder is **not**
advanced past `part_selected`.

## 7. Quantities that remain null, and what resolves them

| Null | What resolves it |
| --- | --- |
| internal-loop R, L, prospective peak, action I²t | the high-current loop model: U10/U9 short residual, bank ESR, fuse R, layout |
| FWP clearing at 400 Vdc capacitor discharge | an FWP capacitor-discharge rating / let-through curve or Eaton guidance |
| A70QS board coordination | a sourced bank / PCB-copper withstand I²t to compare against the let-through |
| startup/inrush duty | a precharge model (NTC U4 / relay U5, hot restart) against the fuse time-current curve |
| temperature-derated ampacity | the FWP ambient / cooling / conductor / altitude derating factors |

## 8. Case counts, time, and recommendation

Source-only task: solver cases expected/attempted/valid/failed/unsupported/unrun = **0/0/0/0/0/0**;
checker side = 2 required passes + 2 negative controls, all run. Wall ≈ 40 min; solver calls 0; web
searches 5; primary sources 6; candidate parts 3. Files/hashes: `inputs.json`, `manifest.json`.

**Recommended next observation:** obtain the *internal discharge loop's* R and L (one high-current
pulse test, or a documented short-residual + ESR + layout model) and re-read the envelope. If out of
reach, request the **FWP capacitor-discharge rating** from Eaton application engineering — its
absence, not the loop impedance alone, is what keeps FWP's clearing cell null.

## Sizing envelope (the deliverable)

| candidate | normal (RMS) | melts (adiabatic) | clears (capacitor discharge) |
| --- | --- | --- | --- |
| **FWP-50A14F** | 9.0007 A = 18.0 % of 50 A | R ≤ **0.896 Ω**, all L | **null** (no applicable data) |
| **A70QS50-14F** | 9.0007 A = 18.0 % of 50 A | R ≤ **0.640 Ω**, all L | manufacturer 890 Vdc / τ ≤ 2.5 ms → **R·C ≤ 2.5 ms (R ≤ 1.116 Ω)**; not board-coordinated |
| **FWP-25A14F** | 9.0007 A = 36.0 % of 25 A | R ≤ **3.855 Ω**, all L | **null** (no applicable data) |

Peak: max 55.2 kA at R = 5 mΩ, L = 20 nH; ≤ 50 kA for R ≳ 8.9 mΩ. **Verdict: coordination
UNESTABLISHED.**

**Single most important missing input:** the internal discharge loop's high-current **R and L**
(U10/U9 failed-short residual, bank ESR at the discharge frequency, fuse resistance, layout) — which
sets `E/R`, the prospective peak and the discharge time constant, and therefore whether any candidate
both melts and stays inside a capacitor-discharge rating.
