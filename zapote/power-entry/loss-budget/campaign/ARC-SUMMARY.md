# Arc summary — PFC loss and heat investigation, 2026-09-17/18

This explains what was done, in the order it happened, and what it leaves
settled versus open. It is a map, not a substitute for the artifacts it points
at. Every number below is traceable to a file in §7.

## 1. The question

The cooker's PFC input was losing more power and producing more heat than
expected. The available instrument was a retained analytic model. The work was to
find out where the loss actually is, whether the model can be trusted to rank
design changes, and what would have to be measured or sourced to decide.

## 2. The instrument, and its limits

The model's baseline at C1 nominal (120 V, 400 V bus, 1796.31 W requested) was
**45.5023 W** of switch-and-gate loss, of which **37.37 W** was switching
overlap. That number was doing almost all the work in every comparison, and it
rested on an analytic Miller-plateau structure plus datasheet typicals — with no
external anchor.

Two things were established early and shaped everything after:

- **The model could not answer one of the plan's central questions.** At fixed
  `L·f` every current moment is invariant, so the planned six-point frequency
  sweep was a monotone walk from 15.55 W to 60.88 W with a predetermined winner.
  Measured, not argued.
- **An independent vendor device model disagreed with it.** A clamped-inductive
  double-pulse in ngspice gave `(Eon+Eoff)·f` = **26.76 W** for the baseline
  device against the analytic 37.37 W overlap — a ratio of **0.72**. Reproduced
  with a byte-identical control.

That disagreement is a **discrepancy at one device and one condition**, not a
calibration. It does not license a correction factor, and it says nothing about
terms it did not compare. Corrected accounting put the conditional switch/gate
subtotal at **33.38 W**, not 34.64 W — the first closeout double-counted output
capacitance.

## 3. What the campaign found

| Term | Value | Evidence class |
| --- | ---: | --- |
| Boost switch/conduction/gate | analytic 45.50 W; 25.50-26.76 W switching independently modelled | model + independent model |
| Input bridge | **28.30 W** (bracketed 23-35 W) | source-bound, one test point |
| Boost inductor, DC only | 4.50 W | source-bound |
| Shunt + relay + bleeders + divider | 3.43 W | source-bound |

The heat is concentrated in the switch and the bridge. Three sourcing tasks hit
the same wall: **the decisive inputs are not published.** No candidate device
publishes Eon/Eoff; no catalog choke publishes core loss at bias; two of three
device datasheets omit the Miller plateau. Both independent references returned
INSUFFICIENT_EVIDENCE and named the same missing observation.

## 4. The bridge plan, and one abandoned unit

A requirements-only plan was written and enriched to implementation-ready for
pinning the bridge's loss. Enrichment found the plan's own premises were wrong in
two ways: the constant-drop term existed in **four** homes, not one, and the
quoted 28.30 W came from a different module than the plan's scope named.

Three units completed:

- **The kernel** — `zapote-erc::pfc_losses::ForwardDropCurve` plus
  `forward_drop_w`, owning forward-drop-as-a-function-of-current. Six tests,
  including the flat-curve identity and a tie to the existing moment form.
- **The claim correction** — the retained GBJ2510 datasheet **does** publish a
  per-element forward-characteristics curve (page 3, Fig. 2). The model recorded
  it as absent because `pdftotext` returns numeric tables and drops plots.
- **The bench protocol** — a DC forward-drop sweep, specified but not authorized.

**One unit was abandoned, correctly.** Tracing Fig. 2's raster plot gave three
answers at 12.5 A — 0.833, 0.961 and 1.100 V — against a datasheet maximum of
1.05 V. The spread was ~5× the effect the curve had to resolve. No curve was
committed, and the unit now carries a point-check gate at 12.5 A / 25 °C.

## 5. Where the leverage actually turned out to be

Estimating each rectifier alternative's **achievable net saving** from the
committed screen reframed the problem:

- Passive alternatives recover only **0-4.5 W** of the bridge's 28.30 W, and each
  saving is a difference between two parts' curves.
- Active rectification has the only large lever, gated on a **hot Rds(on)** curve
  the datum lacks.

The AR-* chain then assessed one concrete candidate.

**Circuit.** Four-MOSFET synchronous full bridge driven by the **NXP TEA2209T/1**.
Two devices conduct in the line path; high-side gates run off a floating
bootstrap.

**Gate bias** (an early claim was corrected here): the controller's regulated
supply is *not* the MOSFET VGS. Computed self-consistently, the high side sees
**~8.5 V typ** and **7.592 V conditional worst** at 220 nF, the low side
**9.906 V minimum**, so the 10 V resistance data does not simply apply. The
worst case is **conditional, not a bound**, because `Qg` has no published maximum.

**Thermal** (also corrected): junction temperature is an **output**. Sharing the
heatsink across four devices, each averages **1.95 W** — not 3.91 W — giving
**Tj ≈ 45.4 / 46.2 / 50.6 °C**.

**Result.** `P_saved` across the bridge bracket:

| Basis | @23 W | @28.30 W | @35 W |
| --- | ---: | ---: | ---: |
| typical | 15.23 | **20.54** | 27.23 |
| 98 % curve (a percentile, not a max) | 14.05 | 19.36 | 26.05 |

Recovery, inrush and EMI remain **unknown and not subtracted**, so these are
upper-side estimates.

**MOV.** The V150LA10AP clamps at **395 V maximum at 50 A, 8/20 µs** — an
*upper* bound, at that current only. The clamp at the surge current **cannot be
bounded in either direction** from this specification: a device could clamp at
350 V at 50 A and 380 V at a higher current while satisfying both statements.
The MOV current is also not the generator's prospective ~500 A figure. So the
surge verdict is **unknown**, and the surge contract itself is **assumed, not
adopted**.

## 6. The finding that is not a measurement

A fault assessment refuted a claimed **586.7 V** device stress — it was
`400 + 186.676`, a sum of two node potentials, and corresponds to no real node.
The real switch-short stress is **current and energy**:

- Bus bank **2240.47 µF**, **179.24 J** stored at 400 V.
- The internal discharge loop (capacitors → shorted boost diode → switch →
  capacitors) **bypasses both the shunt and F1**. Its physical timescale, peak
  current and energy distribution are **unresolved**: an illustrative RC
  calculation gives 94.1 µs, but it assumes normal-device resistance describes a
  destructive fault.
- The **line-fed** loop: gate shutdown cannot open it, because with all drivers
  off the bridge's body diodes conduct. And because the active bridge conducts
  through channels rather than ~2 diode drops, it **lowers** the loop impedance
  and **raises** the prospective current.
- The **internal** loop is device-state dependent, and two cases must be kept
  apart: a *healthy* switch may potentially be turned off after the diode shorts,
  subject to an unquantified detection-and-latency budget, while an
  *already-failed-short* switch cannot. In the failed-short case nothing
  interrupts the loop.
- F1 (16 A time-lag) publishes 1,638 A²s melting I²t at 10× rated and 160 A
  breaking capacity — which **do not** establish safe interruption at matching
  conditions.

So: **600 V remains a candidate rating, not a qualification**, and the design has
a protection gap independent of any measurement.

## 7. Artifact map

| What | Where |
| --- | --- |
| Campaign plan | `docs/plans/2026-09-17-1342-pfc-experiment-campaign-plan.md` |
| Bridge plan (implementation-ready) | `docs/plans/2026-09-17-001-feat-pfc-bridge-loss-pinning-plan.md` |
| Campaign answer, census, ledger | `zapote/power-entry/loss-budget/campaign/CLOSEOUT.md` |
| Corrected loss accounting | `zapote/power-entry/loss-budget/campaign/LOSS-ACCOUNTING-AUDIT.md` |
| Corrected campaign adapter | `zapote/power-entry/loss-budget/campaign/G0.md` |
| Switching measurement proposal | `zapote/power-entry/loss-budget/campaign/PHYSICAL-TEST-PLAN.md` |
| Admission rules | `zapote/power-entry/loss-budget/campaign/ADMISSION.md` |
| Rectifier net savings | `zapote/power-entry/loss-budget/2026-09-17-rectifier-alternative-net-savings.md` |
| Bridge bench protocol | `zapote/power-entry/loss-budget/2026-09-17-bridge-vf-sweep-protocol.md` |
| Per-task attempts | `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/<TASK>/attempt-001/` |
| Reusable learnings | `docs/solutions/best-practices/datasheet-curves-hide-in-plots-raster-traces-can-mislead-2026-09-17.md` and `docs/solutions/best-practices/plan-premises-are-claims-verify-home-and-number-2026-09-17.md` |

Each attempt directory holds `dispatch.json`, `inputs.json`, `result.json`,
`REPORT.md`, `raw/`, `manifest.json` and — where the coordinator reviewed it — a
`coordinator-receipt.md`. Manifests were re-verified against bytes; handbacks
without a checker are recorded as evidence rather than validated runs.

## 8. Enforcement added

Three things that were previously noticed after the fact are now machine-checked:

- `zapote/tools/check_campaign_dispatch.py` — rejects a dispatch issued after its
  own deadline, and refuses to count a handback as a validated run without a
  checker receipt.
- `zapote-erc::fault_loop` (Rust, CLI `zapote-fault-loop`, Python thin wrapper) —
  rejects an energy model that assigns current to an element that cannot conduct
  in the declared loop. It is a **necessary connectivity check only**, and says
  so in its own output.
- `zapote-erc::evidence_claims` (Rust, CLI `zapote-claims`) — rejects a derivation
  that reverses a **bound direction**, drops a **source condition**, or changes a
  **device state** without justification. The three error classes from the
  withdrawn AR-MOV and AR-PROTECT claims are reproduced as a negative control in
  `zapote/power-entry/loss-budget/campaign/claims/`.

The recurring lesson, now encoded: **preserve bound direction, source conditions
and device state in structured evidence.** The connectivity gate catches one
mistake and cannot serve as the acceptance gate for a whole assessment — and
neither can this third check: it rejects unsound *derivations*, not false claims.

## 9. What is settled, and what is not

**Settled:** the heat is concentrated in the switch and the bridge; the analytic
switching model is contradicted by an independent model at the tested condition;
the input bridge's forward-drop band rests on a test point the datasheet
contradicts; the active rectifier's nominal conduction opportunity is ~20 W
typical; the 586.7 V fault claim is refuted; and — on protection — the bus bank
stores ~179 J, the internal fault bypasses both the shunt and F1, and **adequate
protection has not been demonstrated**.

**Open, and each needs a specific input:**

| Open question | Input it needs |
| --- | --- |
| Is the active rectifier worth building? | a committed surge/transient contract, and the MOV clamp at the current it produces |
| Is the bridge's true loss 23, 28 or 35 W? | a candidate bridge part, characterized on the same basis |
| Does the real switching loss match any model? | a device-level clamped-inductive measurement |
| Is the frequency axis worth revisiting? | a sourced choke's core and AC loss at bias |
| Is the design protected against an internal short? | one concrete protection circuit with named parts and explicit fault cases |

**Not done:** no bench or powered operation, no procurement, and no CAD or BOM
change. No candidate is qualified; `hardware_qualification` is NOT_PERFORMED
everywhere.
