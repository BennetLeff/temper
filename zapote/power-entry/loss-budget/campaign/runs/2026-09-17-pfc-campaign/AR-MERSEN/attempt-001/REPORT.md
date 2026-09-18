# AR-MERSEN attempt-001 — mapping the fault-impedance envelope onto Mersen's capacitor-discharge conditions

Task **AR-MERSEN** · Attempt **attempt-001** · Campaign 2026-09-17-pfc-campaign · engineering_verification.
Contract C1.1 `0accd9bc…a825d6`. Dispatch `source_revision` `3d557e40…` **equals** worktree HEAD.
Source-only; no bench, no procurement, no CAD/BOM edit, no solver, no commits.
Output directory: `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-MERSEN/attempt-001/`.

**Hypothesis.** The AR-COORD envelope can be mapped onto Mersen's stated conditions for A70QS50-14F
once the manufacturer's time constant is read as **L/R** (not R·C). Result: the mapping is defined and
its qualifying region is **nonempty**, but coordination is **not** demonstrated — "coordination
unestablished" stands.

**Actual changed variable.** The definition of the manufacturer time constant (L/R replacing R·C), and
the treatment of the melt column as an **L-independent pre-arcing ACTION screen** evaluated **jointly**
with the L-dependent manufacturer condition. The circuit and the frozen envelope are unchanged.

## 1. The applicable Mersen condition, and its basis

The catalogue's DC time constant is **L/R** — stated literally as `*Time Constant: L/R ≤1ms`
(D100QS p.3/HS2, D70QS p.7/HS6) and used interchangeably on the A70QS page (`L/R ≤10ms` and
`10ms time constant`). The sentence scoped to capacitor discharge is (PDF p.20 / HS 20):

> "…IEC rated 690VAC, 200kA Interrupting and 700VDC, 100kA interrupting at 10ms time constant. In
> addition, these fuses have an **890 VDC rating for capacitor discharge applications up to 2.5ms
> time constant**."

So the condition that applies to a capacitor discharge is **890 VDC, L/R ≤ 2.5 ms**. The 700 VDC /
L/R ≤ 10 ms figure on the same page is the general DC-protection rating; the 1 ms figures are
different product lines. **R·C is not the manufacturer's time constant.** At the envelope corner
R = 5 mΩ, L = 20 µH: L/R = **4.000 ms** vs R·C = **11.20 µs** (357×; the 714× in the dispatch is
**2L/R** = 8.000 ms), and ζ = **0.02646** — heavily underdamped, so an RC-decay reading does not
describe the waveform. AR-COORD's `R·C ≤ 1.43 ms` comparison against the 2.5 ms figure is withdrawn.

## 2. Remaining application conditions for A70QS50-14F (catalogue p.21 / HS 21)

| condition | value | status |
| --- | --- | --- |
| capacitor-discharge voltage | 890 VDC (p.20) | obtained |
| capacitor-discharge time constant | L/R ≤ 2.5 ms (p.20) | obtained |
| pre-arcing I²t ("Melting I2t Max") | 0.28×10³ = **280 A²s** | obtained (a **max**, not min) |
| clearing I²t @ 700 VAC | 1.50×10³ = **1500 A²s** | obtained (AC, **not** the cap-discharge condition) |
| DC interrupting I.R. | **100 kA** (footnote `*100kA, L/R = 11.6ms`; highlights say 10 ms) | obtained |
| watts loss @ 50 A | 11.6 W | obtained |
| **MBC (minimum breaking capacity)** | **null** | not published for A70QS |
| **DC / cap-discharge clearing I²t, let-through** | **null** | not published |
| **cap-discharge-specific peak current limit** | **null** | not published |

## 3. Joint mapping of the 400-point (R, L) envelope

Rule: a cell qualifies iff the **action screen** (L-independent) is met **and** **L/R ≤ 2.5 ms**
(L-dependent) **and** the voltage/current limits are respected.

* Action screen: `E/R ≥ 280 A²s` → **R ≤ 0.64013 Ω** (E = 179.2376 J). 144 cells.
* Manufacturer time constant: `L/R ≤ 2.5 ms` → **R ≥ 400·L**. 2 of the 144 action-met cells fail
  it: (R = 5 mΩ, L = 12.62 µH, L/R = 2.52 ms) and (R = 5 mΩ, L = 20 µH, L/R = 4.00 ms).
* Voltage: 400 V ≤ 890 V — all cells.
* Current: peak ≤ 100 kA — all cells (max peak 55.23 kA at R = 5 mΩ, L = 20 nH).

**Qualifying region: 142 of 400 cells — NOT empty.**
`{400·L ≤ R ≤ 0.64013 Ω}` on the grid, i.e. **R ∈ [5 mΩ, 0.5 Ω], L ∈ [20 nH, 20 µH]**.
Under the withdrawn R·C reading all 144 action-met cells would have "qualified", so the correction
bites exactly at the low-R / high-L corner.

**Why this is not coordination.** The region is a *model-screen intersection*, not a board location:
the real loop (R, L) is unmeasured. And even a located qualifying cell is not a demonstrated
coordination — no DC/cap-discharge let-through is published, and the bank/copper withstand I²t is
unsourced. For the two Eaton candidates the mapping is **undefined** (no manufacturer
capacitor-discharge condition), which is distinct from an empty region.

## 4. Controls and case counts

Controls reproduced: the model constants (C = 2240.47 µF, V = 400 V, E = 179.2376 J), the identical
400-point grid, and the three arithmetic oracles (peak → V0/Z0 within **1.2 %**, peak → V0/R within
**2.4e-9**, action → E/R within **3.8e-14**). Source-only task, so solver cases expected/attempted/
valid/failed/unsupported/unrun = **0/0/0/0/0/0**. No new nominal-current statement is made here:
AR-COORD's RMS screening (9.0007 A worst line, 18.0 % of a 50 A rating) is inherited unchanged and
remains a **screening** result with **startup/inrush and temperature-derated ampacity open**.

## 5. Evidence, checks, unresolved findings

* `raw/compute_mersen_mapping.py` → `raw/compute_result.json` / `raw/compute_stdout.txt`.
* `raw/a70qs-conditions.json`, `raw/mersen-extract.txt` (quotes + PDF/catalogue page numbers).
* `zapote-claims claims.json` → **exit 0**, "No violations detected by implemented checks
  (23 claims, 4 protection claims, 2 promotions)" (`raw/checker/out_claims.txt`). Negative control
  (MAX pre-arcing I²t restated as MIN melting I²t) fails with the bound-reversal diagnostic
  (`raw/checker/out_claims_negative_control.txt`, exit 1).
* `check_fault_loop.py --netlist raw/evidence/netlist_fault_loop.json
  --loop-nets PFC_BUS_PLUS_390V,PFC_BUS_MINUS,a1 --assignments raw/assignments_qualifying_cell.json`
  → **exit 0, FAULT LOOP CONSISTENT** (representative peak 4501.09 A at the qualifying cell
  R = 0.05 Ω, L = 5 µH). The U12 negative control is rejected (exit 1).
* **Oracle scope (explicit):** the RLC oracles validate the **calculation only**. They do **not**
  validate its translation into Mersen's qualification conditions; class guidance is not
  demonstrated coordination.
* Unresolved: the action column is a **screen, not melting**; no arc / evolving-resistance is
  modelled; MBC, DC let-through and the downstream withstand remain null; the current limit used is
  the general DC I.R. at L/R = 11.6 ms, not a cap-discharge-specific one.

A clean checker run means no implemented check fired; it is not proof of correctness. The completion
ladder is **not** advanced past `part_selected`.

## 6. Recommended next observation

Measure or defensibly bound the **internal discharge loop's high-current R and L** (U10/U9
short residual, bank ESR at the discharge frequency, fuse R, layout) and locate the operating cell in
the mapped region; then obtain the **A70QS capacitor-discharge let-through I²t** and the
**bank/PCB-copper withstand I²t**.

## 7. Budget, provenance

Wall ≈ 25 min; solver invocations **0**; web searches **0**; primary source: the delivered Mersen
catalogue (sha256 `e0e5b788…`, PDF p.20/p.21, captured 2026-09-18). Files and hashes: `manifest.json`.
No capture failures (`raw/capture_failures.json`: the catalogue was delivered pre-captured and
hash-verified; no new network capture was required).

---

**Qualifying region: NONEMPTY — 142 of 400 cells, `{400·L ≤ R ≤ 0.64013 Ω}` (R ∈ [5 mΩ, 0.5 Ω],
L ∈ [20 nH, 20 µH]), conditional on the single-lumped-R model and the general DC I.R. — but
coordination is UNESTABLISHED and clearing is demonstrated for no candidate.**

**Single most important missing input:** the internal discharge loop's high-current **R and L** at the
fault (U10/U9 failed-short residual, bank ESR at the discharge frequency, fuse resistance, layout) —
it decides which envelope cell the real discharge occupies, and therefore whether the nonempty
qualifying region actually contains the fault. Paired second: a DC/capacitor-discharge let-through I²t
for A70QS50-14F and a sourced bank/copper withstand I²t.
